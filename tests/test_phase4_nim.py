import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
from pathlib import Path

from models.nim_cluster import SupremeNIMCluster, LLMArbiterDecision, NIMClusterExhausted
from config.settings import NIM_MODELS

class TestPhase4NIM(unittest.TestCase):

    def setUp(self):
        # Use system temp dir — never leaks into project data/
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self._tmp_dir.name) / f'test_phase4_{os.getpid()}_{id(self)}.db'
        os.environ["APRS_DB_PATH"] = str(self.test_db)
        from core.database import init_db
        init_db()
        self.cluster = SupremeNIMCluster()

    def tearDown(self):
        os.environ.pop("APRS_DB_PATH", None)
        try:
            self._tmp_dir.cleanup()
        except Exception:
            pass

    def test_fallback_is_cached(self):
        """Verify that a successful NIM response is LRU-cached and returned on 2nd call."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "AI-generated analysis"}}]
        }
        with patch("requests.post", return_value=mock_resp) as mock_post:
            r1 = self.cluster.query("test caching", timeout=5.0)
            r2 = self.cluster.query("test caching", timeout=5.0)

        # r1: real call, r2: from LRU cache
        self.assertTrue(r1.get("success"))
        self.assertFalse(r1.get("cached"))
        self.assertTrue(r2.get("cached"))
        self.assertEqual(r1["content"], r2["content"])
        # Second call should NOT hit requests.post (LRU cache hit)
        self.assertEqual(mock_post.call_count, 1)

    def test_model_name_validation(self):
        """Invalid task_type must raise ValueError immediately."""
        with self.assertRaises(ValueError):
            self.cluster.query("test", task_type="nonexistent_task")

    def test_all_keys_exhausted_raises(self):
        """When all 3 keys fail, NIMClusterExhausted must be raised — never silent fallback."""
        with patch("requests.post", side_effect=ConnectionError("Simulated network failure")):
            with self.assertRaises(NIMClusterExhausted) as ctx:
                self.cluster.query("test exhausted keys", timeout=1.0)
        self.assertIn("All NIM API keys exhausted", str(ctx.exception))

    def test_arbiter_prompt_no_example(self):
        """Pydantic LLMArbiterDecision schema validates correctly."""
        decision = LLMArbiterDecision(
            status="PASS",
            overall_score=85.0,
            landed_cogs=10.0,
            gross_margin_pct=75.0,
            est_cac=15.0,
            net_profit_pct=30.0,
            worst_case_stress_margin_pct=15.0,
            consensus_status="CONSENSUS_PASS",
            action_plan="Test plan"
        )
        self.assertEqual(decision.status, "PASS")
        self.assertEqual(decision.overall_score, 85.0)

    def test_fallback_caching(self):
        """Verify LRU cache stores and returns responses on repeated identical prompts."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Cached response content"}}]
        }
        with patch("requests.post", return_value=mock_resp) as mock_post:
            r1 = self.cluster.query("identical prompt", timeout=5.0)
            r2 = self.cluster.query("identical prompt", timeout=5.0)

        self.assertTrue(r1.get("success"))
        self.assertTrue(r2.get("cached"))
        self.assertEqual(r2["content"], "Cached response content")
        # LRU cache should prevent 2nd network call
        self.assertEqual(mock_post.call_count, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)