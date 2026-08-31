import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
from pathlib import Path

from tools.amazon_live_scraper import AmazonLiveScraper, ScraperError
from tools.keepa_api_client import KeepaAPIClient, KeepaProduct, KeepaAPIError

class TestPhase3Scrapers(unittest.TestCase):

    def setUp(self):
        # Use system temp dir — never leaks into project data/
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


    def test_amazon_scraper_browser_rotation(self):
        """Test that browser rotation works"""
        scraper = AmazonLiveScraper()
        initial_idx = scraper._profile_idx
        
        # Simulate rotation
        scraper._rotate_session()
        
        # Profile index should increment
        self.assertEqual(scraper._profile_idx, initial_idx + 1)
    
    def test_amazon_scraper_currency_detection(self):
        scraper = AmazonLiveScraper()
        self.assertEqual(scraper._detect_currency("amazon.com"), "USD")
        self.assertEqual(scraper._detect_currency("amazon.in"), "INR")
        self.assertEqual(scraper._detect_currency("amazon.co.uk"), "GBP")
        self.assertEqual(scraper._detect_currency("amazon.de"), "EUR")
    
    def test_amazon_scraper_price_extraction(self):
        """Test price extraction with various formats"""
        scraper = AmazonLiveScraper()
        
        # Create mock item with price
        from bs4 import BeautifulSoup
        html = '<span class="a-price-whole">1,234</span><span class="a-price-fraction">56</span>'
        soup = BeautifulSoup(html, "html.parser")
        item = soup.find("span", class_="a-price-whole").parent
        
        price = scraper._extract_price(item)
        self.assertEqual(price, 1234.56)
    
    def test_keepa_india_domain(self):
        """Test that India domain ID is 10"""
        client = KeepaAPIClient(api_key="test-key-12345")
        self.assertEqual(client._get_domain_id("India"), 10)
        self.assertEqual(client._get_domain_id("USA"), 1)
        self.assertEqual(client._get_domain_id("UK"), 2)
        self.assertEqual(client._get_domain_id("Germany"), 3)
    
    def test_keepa_currency_detection(self):
        client = KeepaAPIClient(api_key="test-key-12345")
        
        # Mock the _fetch method to return product data
        client._enabled = True
        client._fetch = MagicMock(return_value={
            "products": [{
                "asin": "B0TEST1234",
                "title": "Test Product",
                "stats": {
                    "current": [123456, None, 100],  # price in cents, BSR
                    "avg30": [125000, None],
                    "avg90": [124000, None],
                    "min": [120000, None]
                },
                "rating": 45,  # 4.5 * 10
                "reviewsCount": 100,
                "rootCategory": "Home & Kitchen"
            }]
        })
        
        # Test India currency
        with patch.object(client, '_get_domain_id', return_value=10):
            product = client.get_product("B0TEST1234", region="India")
            self.assertEqual(product.currency, "INR")
        
        # Test USA currency
        with patch.object(client, '_get_domain_id', return_value=1):
            product = client.get_product("B0TEST1234", region="USA")
            self.assertEqual(product.currency, "USD")
    
    def test_keepa_caching(self):
        client = KeepaAPIClient(api_key="test-key-12345")
        client._enabled = True
        
        # Mock fetch to return data
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
        
        # First call
        p1 = client.get_product("B0TEST1234", region="USA")
        # Second call should use cache
        p2 = client.get_product("B0TEST1234", region="USA")
        
        self.assertEqual(p1.asin, p2.asin)
        self.assertEqual(call_count[0], 1)  # Only one actual fetch

if __name__ == "__main__":
    unittest.main(verbosity=2)