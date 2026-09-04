"""
tests/test_phase4_nim.py — V6 Gate Engine Tests.
Replaces old NIM swarm tests with 4-gate pipeline tests.
"""
import unittest
import asyncio
from unittest.mock import MagicMock, patch
import tempfile
import os
from pathlib import Path

from core.gate_engine import GateEngine
from core.validation import CanonicalProduct
from core.economics_engine import Comprehensive15FactorEconomics


class TestV6GateEngine(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self._tmp_dir.name) / f'test_gate_{os.getpid()}_{id(self)}.db'
        os.environ["APRS_DB_PATH"] = str(self.test_db)
        from core.database import init_db
        init_db()
        self.engine = GateEngine()

    def tearDown(self):
        os.environ.pop("APRS_DB_PATH", None)
        try:
            self._tmp_dir.cleanup()
        except Exception:
            pass

    def test_gate1_signal_passes_low_bsr(self):
        """Gate 1 passes when BSR < threshold and price CV < threshold."""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_bsr=10000,
            rating=4.5,
            review_count=200,
        )
        result = self.engine.run_gate_1_signal(
            product=product,
            bsr_current=10000,
            price_current=1299.0,
            price_30d_ago=1280.0,
        )
        self.assertTrue(result.passed)
        self.assertEqual(result.gate_number, 1)

    def test_gate1_signal_fails_high_bsr(self):
        """Gate 1 fails when BSR >= threshold."""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            rating=4.5,
            review_count=200,
        )
        result = self.engine.run_gate_1_signal(
            product=product,
            bsr_current=60000,
            price_current=1299.0,
            price_30d_ago=1280.0,
        )
        self.assertFalse(result.passed)

    def test_gate1_signal_fails_high_cv(self):
        """Gate 1 fails when price CV >= threshold."""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            rating=4.5,
            review_count=200,
        )
        result = self.engine.run_gate_1_signal(
            product=product,
            bsr_current=10000,
            price_current=1299.0,
            price_30d_ago=800.0,  # ~62% change
        )
        self.assertFalse(result.passed)

    def test_gate3_economics_passes_viable_product(self):
        """Gate 3 passes for product with >=15% net margin (actual fee structure)."""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_bsr=15000,
            rating=4.5,
            review_count=200,
        )
        # Use engine with lower margin threshold for test
        engine = GateEngine(min_margin_pct=15.0)
        result = engine.run_gate_3_economics(
            product=product,
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.details["expected"]["net_margin_pct"], 15.0)

    def test_gate3_economics_fails_low_margin(self):
        """Gate 3 fails when net margin < threshold."""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            rating=4.5,
            review_count=200,
        )
        engine = GateEngine(min_margin_pct=15.0)
        result = engine.run_gate_3_economics(
            product=product,
            fob_price=800.0,  # High FOB = low margin
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
        )
        self.assertFalse(result.passed)

    def test_gate4_scoring_passes_high_score(self):
        """Gate 4 passes when score >= 75."""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_bsr=10000,
            rating=4.5,
            review_count=200,
        )
        result = self.engine.run_gate_4_scoring(
            product=product,
            bsr=10000,
            rating=4.5,
            review_count=200,
            net_margin_pct=30.0,
            has_defects=True,
            competitor_count=3,
        )
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.details["total_score"], 75)

    def test_gate4_scoring_fails_low_score(self):
        """Gate 4 fails when score < 75."""
        product = CanonicalProduct(
            canonical_title="Test Product",
            category="Kitchen",
            retail_price_inr=1299.0,
            rating=3.5,
            review_count=30,
        )
        result = self.engine.run_gate_4_scoring(
            product=product,
            bsr=50000,
            rating=3.5,
            review_count=30,
            net_margin_pct=15.0,
            has_defects=False,
            competitor_count=15,
        )
        self.assertFalse(result.passed)

    def test_full_pipeline_proceed(self):
        """Full 4-gate pipeline returns PROCEED for viable product."""
        product = CanonicalProduct(
            canonical_title="Stainless Steel Water Bottle",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_bsr=15000,
            rating=4.5,
            review_count=200,
        )
        mock_reviews = [
            "Great bottle but lid leaks after a week",
            "Insulation good but paint chips easily",
        ]
        # Mock the review_miner to avoid Ollama dependency
        async def mock_extract_defects(product_title, reviews):
            return {
                "defects": [
                    {"defect": "Lid leaks", "severity": "major", "frequency": "common", "suggested_fix": "Better seal"}
                ],
                "v2_spec": {"improvement_1": "Leak-proof lid"}
            }
        
        # Use GateEngine with lower margin threshold for test
        engine = GateEngine(min_margin_pct=15.0)

        async def mock_gate_5(*args, **kwargs):
            from core.gate_engine import GateResult, GateStatus
            return GateResult(
                gate_number=5,
                gate_name="NIM Arbiter",
                status=GateStatus.PASS,
                details={"verdict": "CONFIRM", "confidence": 95},
            )

        with patch.object(engine.review_miner, 'extract_defects', side_effect=mock_extract_defects), \
             patch.object(engine, 'run_gate_5_arbiter', side_effect=mock_gate_5):
            result = asyncio.run(engine.run_full_pipeline(
                product=product,
                bsr_current=15000,
                price_current=1299.0,
                reviews_3star=mock_reviews,
                fob_price=280.0,  # Lower FOB to achieve >20% margin for scoring
                planned_msrp=1299.0,
                region="India",
                category="Kitchen",
                marketplace="amazon",
                competitor_count=5,
            ))
        self.assertEqual(result.final_verdict, "PROCEED")
        self.assertEqual(len(result.gate_results), 5)
        self.assertTrue(all(g.passed for g in result.gate_results))

    def test_economics_passes_gate_method(self):
        """Test the passes_gate convenience method."""
        passes, details = Comprehensive15FactorEconomics.passes_gate(
            fob_price=350.0,
            planned_msrp=1299.0,
            region="India",
            category="Kitchen",
            marketplace="amazon",
            min_margin_pct=15.0,  # Updated to match actual fee structure (11% referral)
        )
        self.assertTrue(passes)
        self.assertTrue(details["gate_passed"])
        self.assertGreaterEqual(details["expected"]["net_margin_pct"], 15.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)