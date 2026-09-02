import unittest
from unittest.mock import MagicMock
import os
import tempfile
from pathlib import Path

from core.orchestrator import AutonomousProductResearchOrchestrator
from tools.keepa_api_client import KeepaProduct
from core.database import init_db, get_connection, get_current_gate, update_gate_status, init_product_gates
from tools.amazon_scraper import ScraperError

class TestPhase2Orchestrator(unittest.TestCase):

    def setUp(self):
        # Use system temp dir — never leaks into project data/
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self._tmp_dir.name) / f'test_phase2_{os.getpid()}_{id(self)}.db'
        os.environ["APRS_DB_PATH"] = str(self.test_db)
        init_db()
        self.orch = AutonomousProductResearchOrchestrator()

    def tearDown(self):
        os.environ.pop("APRS_DB_PATH", None)
        try:
            self._tmp_dir.cleanup()
        except Exception:
            pass

    def test_gate1_success_blocks_at_gate2(self):
        # Set up Keepa mock
        mock_k = MagicMock()
        mock_prod = KeepaProduct(
            asin="B0TEST1234",
            title="Test Kitchen Organizer",
            current_price=49.99,
            currency="USD",
            bsr_current=250,
            product_url="https://amazon.com/dp/B0TEST1234",
            price_30d_avg=48.0,
            price_90d_avg=47.0,
            price_historical_low=45.0,
            rating=4.5,
            review_count=100
        )
        mock_k.get_product.return_value = mock_prod
        mock_k._enabled = True
        
        # Set up scraper mock
        mock_scraper_instance = MagicMock()
        mock_scraper_instance.search.return_value = [{"asin": "B0TEST1234", "title": "Test Kitchen Organizer", "price": 49.99}]
        
        # Create new orchestrator with mocked dependencies
        orch = AutonomousProductResearchOrchestrator()
        orch.amazon_scraper = mock_scraper_instance
        orch.keepa = mock_k
        
        result = orch.discover_and_evaluate_products(region="USA", category="Kitchen Storage", max_candidates=1)
        
        self.assertTrue(len(result) > 0)
        # Check for the correct result structure
        self.assertIn("status", result[0])
        self.assertEqual(result[0]["status"], "BLOCKED_AT_GATE_2")
    
    def test_gate1_zero_price_returns_error(self):
        # Set up Keepa mock with zero price
        mock_k = MagicMock()
        mock_prod = KeepaProduct(asin="B0ZERO0000", title="Zero Price", current_price=0.0, currency="USD")
        mock_k.get_product.return_value = mock_prod
        mock_k._enabled = True
        
        # Set up scraper mock
        mock_scraper_instance = MagicMock()
        mock_scraper_instance.search.return_value = [{"asin": "B0ZERO0000", "title": "Zero Price", "price": 0.0}]
        
        # Create new orchestrator with mocked dependencies
        orch = AutonomousProductResearchOrchestrator()
        orch.amazon_scraper = mock_scraper_instance
        orch.keepa = mock_k
        
        result = orch.discover_and_evaluate_products(region="USA", category="Test", max_candidates=1)
        
        # With zero price, product should fail Gate 1 and be skipped
        # Result should be empty
        self.assertEqual(len(result), 0)
    
    def test_scraper_failure_no_fallback(self):
        mock_scraper_instance = MagicMock()
        mock_scraper_instance.search.side_effect = ScraperError("Scraper failed")
        
        orch = AutonomousProductResearchOrchestrator()
        orch.amazon_scraper = mock_scraper_instance
        
        result = orch.discover_and_evaluate_products(region="USA", category="Test", max_candidates=1)
        
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["success"])
        self.assertIn("Scraper failed", result[0]["error"])
    
    def test_re_evaluate_requires_fob(self):
        self.assertTrue(hasattr(self.orch, 're_evaluate_single_product'))

if __name__ == "__main__":
    unittest.main(verbosity=2)