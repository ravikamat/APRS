import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
from pathlib import Path

from tools.amazon_scraper import AmazonScraper, ScraperError
from tools.keepa_api_client import KeepaAPIClient, KeepaProduct, KeepaAPIError

class TestPhase3Scrapers(unittest.TestCase):

    def setUp(self):
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.test_db = Path(self._tmp_dir.name) / f'test_phase3_{os.getpid()}_{id(self)}.db'
        os.environ["APRS_DB_PATH"] = str(self.test_db)
        from core.database import init_db
        init_db()

    def tearDown(self):
        os.environ.pop("APRS_DB_PATH", None)
        try:
            self._tmp_dir.cleanup()
        except Exception:
            pass

    def test_amazon_scraper_instantiates(self):
        """V6 AmazonScraper (Playwright) can be instantiated."""
        scraper = AmazonScraper()
        self.assertIsNotNone(scraper)
        self.assertEqual(scraper.BASE_URL, "https://www.amazon.in")

    def test_amazon_scraper_selectors_defined(self):
        """Selector fallback lists are defined for all critical fields."""
        scraper = AmazonScraper()
        required_keys = ["product_container", "title", "price_whole"]
        for key in required_keys:
            self.assertIn(key, scraper.SELECTORS)
            self.assertGreater(len(scraper.SELECTORS[key]), 0)

    def test_scraper_error_is_exception(self):
        """ScraperError is a proper Exception subclass."""
        err = ScraperError("test error")
        self.assertIsInstance(err, Exception)
        self.assertIn("test error", str(err))

    def test_keepa_india_domain(self):
        """Test that India domain ID is 10."""
        client = KeepaAPIClient(api_key="test-key-12345")
        self.assertEqual(client._get_domain_id("India"), 10)
        self.assertEqual(client._get_domain_id("USA"), 1)
        self.assertEqual(client._get_domain_id("UK"), 2)
        self.assertEqual(client._get_domain_id("Germany"), 3)

    def test_keepa_currency_detection(self):
        client = KeepaAPIClient(api_key="test-key-12345")
        client._enabled = True
        client._fetch = MagicMock(return_value={
            "products": [{
                "asin": "B0TEST1234",
                "title": "Test Product",
                "stats": {
                    "current": [123456, None, 100],
                    "avg30": [125000, None],
                    "avg90": [124000, None],
                    "min": [120000, None]
                },
                "rating": 45,
                "reviewsCount": 100,
                "rootCategory": "Home & Kitchen"
            }]
        })
        with patch.object(client, '_get_domain_id', return_value=10):
            product = client.get_product("B0TEST1234", region="India")
            self.assertEqual(product.currency, "INR")
        with patch.object(client, '_get_domain_id', return_value=1):
            product = client.get_product("B0TEST1234", region="USA")
            self.assertEqual(product.currency, "USD")

    def test_keepa_caching(self):
        client = KeepaAPIClient(api_key="test-key-12345")
        client._enabled = True
        call_count = [0]
        def mock_fetch(endpoint, params):
            call_count[0] += 1
            return {
                "products": [{
                    "asin": "B0TEST1234",
                    "title": "Test Product",
                    "stats": {
                        "current": [10000, None, 100],
                        "avg30": [10500, None],
                        "avg90": [10400, None],
                        "min": [9500, None]
                    },
                    "rating": 45,
                    "reviewsCount": 100,
                    "rootCategory": "Home & Kitchen"
                }]
            }
        client._fetch = mock_fetch
        p1 = client.get_product("B0TEST1234", region="USA")
        p2 = client.get_product("B0TEST1234", region="USA")
        self.assertEqual(p1.asin, p2.asin)
        self.assertEqual(call_count[0], 1)

if __name__ == "__main__":
    unittest.main(verbosity=2)