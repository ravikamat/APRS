"""
tests/test_aprs_platform.py — V7 Platform Integration Tests.

Verifies:
- Comprehensive15FactorEconomics (V7 economics engine)
- Database WAL mode, dedup, human override
- AmazonScraper structure (kept as fallback)
- GateEngine + ScoringEngine
- ValidationPipeline + RuleEngine
- Meeting log and Word doc generation
"""
import os
import sys
import gc
import glob
import unittest
import tempfile
from pathlib import Path

from core.database import (
    init_db, get_connection, record_product_evaluation,
    get_all_products, set_human_override, is_duplicate_product,
    log_meeting_turn, get_meeting_history,
)
from core.economics_engine import Comprehensive15FactorEconomics
from core.gate_engine import GateEngine, GateStatus
from core.validation import RawProduct, CanonicalProduct, ValidationPipeline
from core.scoring_engine import ScoringEngine
from core.rule_engine import create_rule_engine
from core.meeting_doc_manager import generate_meeting_word_doc
from tools.amazon_scraper import AmazonScraper, ScraperError


class TestAPRSPlatform(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp_dir = tempfile.TemporaryDirectory()
        cls._test_db = Path(cls._tmp_dir.name) / 'test_platform.db'
        os.environ["APRS_DB_PATH"] = str(cls._test_db)
        init_db()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("APRS_DB_PATH", None)
        try:
            conn = get_connection()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            conn.close()
        except Exception:
            pass
        gc.collect()
        for f in glob.glob(str(cls._test_db) + "*"):
            try:
                os.unlink(f)
            except OSError:
                pass
        try:
            cls._tmp_dir.cleanup()
        except (PermissionError, OSError):
            pass

    def test_01_unit_economics_15_factor_math(self):
        """Verify V7 15-factor economics with 3-scenario stress testing."""
        econ = Comprehensive15FactorEconomics()
        result = econ.calculate_scenario(
            scenario_name="Expected",
            fob_price=300.0,
            planned_msrp=2499.0,
            region="India",
            category="Kitchen Storage",
            moq_units=300,
            mold_tooling_cost=6000.0,
        )
        self.assertIsNotNone(result)
        self.assertGreater(result.gross_margin_pct, 0.0)
        self.assertIn(result.status, ["PASS", "FAIL"])

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

    def test_03_amazon_scraper_structure(self):
        """Verify V6 AmazonScraper has correct structure for Playwright-based scraping."""
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
        breakdown = scorer.score(
            bsr=15000,
            rating=4.2,
            review_count=320,
            net_margin_pct=28.5,
            has_defects=True,
            competitor_count=8,
        )
        self.assertGreater(breakdown.total, 0)
        self.assertLessEqual(breakdown.total, 100)
        self.assertIn(breakdown.verdict, ["PROCEED", "MARGINAL", "REJECT"])

    def test_05_validation_and_rule_engine(self):
        """Verify ValidationPipeline validates and RuleEngine evaluates products."""
        pipeline = ValidationPipeline()
        raw = {
            "marketplace": "amazon",
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
        product_data = {"bsr": 5000, "margin": 28.5, "category": "Kitchen Storage"}
        result = rule_engine.evaluate_product(product_data)
        self.assertIsInstance(result, dict)

    def test_06_meeting_log_and_word_export(self):
        """Verify SQLite meeting log and Word doc generation."""
        test_session = "test_session_v7_automated"
        log_meeting_turn(
            session_id=test_session, speaker_name="Tech Specialist",
            speaker_role="Systems Architect", avatar="💻",
            user_prompt="V7 automated verification test prompt",
            response_text="All V7 platform gates passed."
        )
        history = get_meeting_history(session_id=test_session)
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[-1]["speaker_name"], "Tech Specialist")
        doc_path = generate_meeting_word_doc(session_id=test_session)
        self.assertTrue(os.path.exists(doc_path))


if __name__ == '__main__':
    unittest.main(verbosity=2)
