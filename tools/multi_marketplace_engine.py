"""
tools/multi_marketplace_engine.py — Universal Multi-Marketplace Engine.

UNIVERSAL: Uses ONE data-driven scraper (UniversalBrowserScraper) that works for
ANY marketplace via browser-use + database configuration.

No hardcoded scrapers. No CSS selectors in code. 100% dynamic from marketplace_config table.
"""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import sys

# Project root import
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.database import record_multi_platform_listing, get_marketplace_configs
from core.utils import normalize_region
from tools.adapters.base_adapter import BaseSourceAdapter
from core.product_matcher import CanonicalProductMatcher

logger = logging.getLogger("aprs.multi_mkt")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s — %(message)s")


class MultiMarketplaceEngine(BaseSourceAdapter):
    """
    Universal cross-platform e-commerce crawler.
    Uses UniversalBrowserScraper (browser-use + DB config) for ALL marketplaces.
    """

    def __init__(self, use_cloud: bool = None, proxy_country: str = None):
        import os
        super().__init__(source_name="universal_marketplace_engine")
        self.matcher = CanonicalProductMatcher()
        self._scraper = None
        self._use_cloud = use_cloud if use_cloud is not None else bool(os.getenv("BROWSER_USE_API_KEY"))
        self._proxy_country = proxy_country or os.getenv("BROWSER_USE_PROXY_COUNTRY")

    def _get_scraper(self):
        """Lazy init universal scraper."""
        if self._scraper is None:
            from tools.universal_browser_scraper import UniversalBrowserScraper
            self._scraper = UniversalBrowserScraper(
                use_cloud=self._use_cloud,
                proxy_country=self._proxy_country
            )
        return self._scraper

    def discover_topics(self, query: str, region: str = "India") -> List[Dict[str, Any]]:
        """SourceAdapter protocol: not applicable for marketplace engine."""
        return []

    def collect_reviews(self, listing_url_or_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """SourceAdapter protocol: not applicable here, use review harvester."""
        return []

    def search_all_marketplaces(self, query: str, region: str = "India", max_per_platform: int = 2) -> List[Dict[str, Any]]:
        """
        Queries ALL active marketplaces for a product query using universal scraper.
        Runs in parallel across all configured marketplaces for the region.
        """
        canon_region = normalize_region(region)
        scraper = self._get_scraper()
        
        try:
            # Run async scrape in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(
                    scraper.scrape_all_marketplaces(canon_region, query, max_pages=2)
                )
            finally:
                loop.close()
        except Exception as e:
            logger.warning(f"Universal scrape failed for '{query}' in {canon_region}: {e}")
            return []

        # Normalize results to expected format
        all_results = []
        for marketplace, products in results.items():
            for p in products:
                all_results.append({
                    "platform": marketplace.lower().replace(" ", "_"),
                    "title": p.title,
                    "price": p.price or 0.0,
                    "currency": p.currency,
                    "rating": p.rating,
                    "review_count": p.review_count,
                    "listing_url": p.product_url,
                    "in_stock": 1 if p.availability.lower() not in ("out of stock", "unavailable") else 0,
                    "source": f"{marketplace.lower()}_universal"
                })
        
        return all_results

    def attach_listings_to_product(self, product_id: str, query: str, region: str = "India"):
        """Crawls and attaches multi-marketplace listings to a product in the SSOT database."""
        listings = self.search_all_marketplaces(query=query, region=region, max_per_platform=2)
        count = 0
        for item in listings:
            ok = record_multi_platform_listing(
                product_id=product_id,
                platform=item["platform"],
                title=item["title"],
                price=float(item.get("price", 0.0)),
                listing_url=item.get("listing_url", ""),
                rating=item.get("rating"),
                review_count=item.get("review_count", 0),
                currency=item.get("currency", "INR")
            )
            if ok:
                count += 1
        logger.info(f"Attached {count} multi-platform listings to product {product_id}")
        return listings

    def get_available_marketplaces(self, region: str = "India") -> List[Dict]:
        """Get list of available marketplace configurations for a region."""
        configs = get_marketplace_configs(region=region, active_only=True)
        return [{
            "marketplace": c["marketplace_name"],
            "region": c["region"],
            "priority": c["priority"],
            "success_rate": c["success_rate"]
        } for c in configs]


# Backward compatibility aliases
class AmazonLiveScraper:
    """Deprecated: Use UniversalBrowserScraper instead."""
    def __init__(self, *args, **kwargs):
        logger.warning("AmazonLiveScraper is deprecated. Use MultiMarketplaceEngine (universal).")

    def search(self, *args, **kwargs):
        return []


class ScraperError(Exception):
    pass


if __name__ == "__main__":
    async def demo():
        engine = MultiMarketplaceEngine()
        results = await engine._get_scraper().scrape_all_marketplaces("India", "Silicone Oil Bottle Brush Dispenser", max_pages=1)
        print(f"\n[DEMO] Found products from {len(results)} marketplaces:")
        for marketplace, products in results.items():
            print(f"  [{marketplace.upper()}] {len(products)} products")
            for p in products[:3]:
                print(f"    • {p.title[:50]} — {p.currency}{p.price} | {p.rating}★ ({p.review_count})")

    asyncio.run(demo())