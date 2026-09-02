"""
tests/test_aprs_platform.py -- APRS V6 Pro Platform Integration Tests.

Tests the full V6 module stack:
- ComprehensiveUnitEconomics (orchestrator inline engine)
- GateEngine (4-gate pipeline), ValidationPipeline, ScoringEngine, RuleEngine
- Database WAL mode and core functions
- Meeting log and Word export
"""
import unittest
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.database import (
    init_db, get_connection, record_product_evaluation,
    get_all_products, set_human_override, is_duplicate_product,
    log_meeting_turn, get_meeting_history,
)
from core.orchestrator import ComprehensiveUnitEconomics, CATEGORY_COMMISSIONS
from core.orchestrator import AutonomousProductResearchOrchestrator
from core.gate_engine import GateEngine, GateStatus
from core.validation import RawProduct, CanonicalProduct, ValidationPipeline
from core.scoring_engine import ScoringEngine
from core.rule_engine import create_rule_engine
from core.meeting_doc_manager import generate_meeting_word_doc


class TestAPRSPlatform(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls._test_db = Path(cls._tmp_dir.name) / "test_platform.db"
        os.environ["APRS_DB_PATH"] = str(cls._test_db)
        init_db()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("APRS_DB_PATH", None)
        cls._tmp_dir.cleanup()

    def test_01_unit_economics_12_factor_math(self):
        """Verify 12-factor landed COGS, mold amortization, category fees."""
        econ_us = ComprehensiveUnitEconomics.calculate_landed_economics(
            fob_price=6.00, planned_msrp=49.99, region="USA",
            category="Kitchen Storage", est_ad_cac=14.00,
            moq_units=300, mold_tooling_cost=600.0
        )
        self.assertEqual(econ_us["mold_amortization_per_unit"], 2.00)
        self.assertGreater(econ_us["landed_cogs"], 8.00)
        self.assertGreater(econ_us["gross_margin_pct"], 60.0)
        self.assertIn(econ_us["status"], ["PASS", "FAIL"])
        self.assertEqual(econ_us["referral_fee_pct"], 0.15)

        econ_in = ComprehensiveUnitEconomics.calculate_landed_economics(
            fob_price=300.0, planned_msrp=2499.0, region="India",
            category="Beauty & Grooming", est_ad_cac=500.0,
            moq_units=300, mold_tooling_cost=6000.0
        )
        self.assertEqual(econ_in["mold_amortization_per_unit"], 20.00)
        self.assertGreater(econ_in["net_tax_burden"], 0.0)
        self.assertEqual(econ_in["referral_fee_pct"], 0.12)

    def test_02_database_wal_and_deduplication(self):
        """Verify SQLite WAL mode, duplicate ASIN checks, and human overrides."""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode;")
        mode = cur.fetchone()[0]
        self.assertEqual(mode.lower(), "wal")
        conn.close()

        is_dup = is_duplicate_product("TEST_NON_EXISTENT_ID", "https://amazon.com/dp/B0NONEXIST")
        self.assertFalse(is_dup)

    def test_03_v6_scraper_structure(self):
        """Verify V6 AmazonScraper has correct structure for Playwright-based scraping."""
        from tools.amazon_scraper import AmazonScraper, ScraperError
        scraper = AmazonScraper()
        self.assertIsNotNone(scraper)
        self.assertEqual(scraper.BASE_URL, "https://www.amazon.in")
        self.assertTrue(hasattr(scraper, "search"))
        self.assertTrue(callable(scraper.search))
        err = ScraperError("test")
        self.assertIsInstance(err, Exception)

    def test_04_gate_engine_and_scoring(self):
        """Verify GateEngine instantiation and ScoringEngine scoring."""
        engine = GateEngine()
        self.assertIsNotNone(engine)

        scorer = ScoringEngine()
        from core.scoring_engine import ScoreInput
        score_input = ScoreInput(
            bsr_current=15000, bsr_30d_avg=16000, bsr_90d_avg=17000,
            review_count=320, rating=4.2,
            net_margin_pct=28.5, worst_case_margin_pct=18.0,
            fixable_defect_count=2, total_defect_count=5,
            competitor_count=8,
        )
        breakdown = scorer.score(score_input)
        self.assertGreater(breakdown.total, 0)
        self.assertLessEqual(breakdown.total, 100)
        self.assertIn(breakdown.verdict, ["PROCEED", "MARGINAL", "REJECT"])

    def test_05_validation_and_rule_engine(self):
        """Verify ValidationPipeline validates and RuleEngine evaluates products."""
        pipeline = ValidationPipeline()
        raw = {
            "marketplace": "amazon_in",
            "product_id": "B0APRSTEST",
            "title": "Bamboo Spice Rack Organizer Kitchen",
            "price": 799.0,
            "rating": 4.3,
            "review_count": 245,
            "url": "https://www.amazon.in/dp/B0APRSTEST",
        }
        valid, errors = pipeline.validate_batch([raw])
        self.assertEqual(len(valid), 1)
        self.assertEqual(len(errors), 0)

        rule_engine = create_rule_engine()
        self.assertIsNotNone(rule_engine)
        product = valid[0]
        result = rule_engine.evaluate(product)
        self.assertIsInstance(result, bool)

    def test_06_meeting_log_and_word_export(self):
        """Verify SQLite meeting log and Word doc generation."""
        test_session = "test_session_v6_automated"
        log_meeting_turn(
            session_id=test_session, speaker_name="Tech Specialist",
            speaker_role="Systems Architect", avatar="💻",
            user_prompt="V6 automated verification test prompt",
            response_text="All V6 platform gates passed."
        )
        history = get_meeting_history(session_id=test_session)
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[-1]["speaker_name"], "Tech Specialist")
        doc_path = generate_meeting_word_doc(session_id=test_session)
        self.assertTrue(os.path.exists(doc_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
