"""
tools/discovery_engine.py — Discovery Orchestrator for APRS V7.

Coordinates multi-marketplace product discovery using WebAgent (NIM 550B driven).
NO LLM CALLS in orchestration - purely deterministic orchestration.
LLM is used inside WebAgent for page extraction only.

Pipeline:
1. Load active niches from DB (dynamic_niches table)
2. Load seed keywords from DB (dynamic_seed_keywords table)  
3. For each niche/keyword: scrape Amazon + Flipkart + Meesho via WebAgent
4. Validate & deduplicate via Pydantic + ProductMatcher
5. Store RawProduct[] -> SQLite

Usage:
    engine = DiscoveryEngine()
    results = await engine.run_discovery_batch(region="India", max_niches=5)
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from core.database import (
    get_dynamic_niches, get_seed_keywords, update_niche_scan,
    record_dynamic_niche, record_seed_keyword,
)
from core.validation import (
    RawProduct, CanonicalProduct, ProductMatcher, ValidationPipeline,
)
from tools.web_agent import WebAgent

logger = logging.getLogger("aprs.discovery")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s — %(message)s")


class DiscoveryEngine:
    """
    Deterministic multi-marketplace discovery orchestrator.
    
    Replaces NIM-powered discovery with database-driven niche/keyword expansion.
    """
    
    def __init__(
        self,
        max_concurrent_scrapers: int = 2,
        max_pages_per_search: int = 2,
    ):
        self.max_concurrent = max_concurrent_scrapers
        self.max_pages = max_pages_per_search
        self.matcher = ProductMatcher()
        self.validator = ValidationPipeline()
    
    async def run_discovery_batch(
        self,
        region: str = "India",
        max_niches: int = None,
        max_candidates_per_niche: int = None,
        use_seed_keywords: bool = True,
    ) -> Dict[str, Any]:
        """
        Run a complete discovery batch across niches and marketplaces.
        
        Args:
            region: Target region (India, USA, etc.)
            max_niches: Maximum niches to process (default from settings)
            max_candidates_per_niche: Max products per niche (default from settings)
            use_seed_keywords: Whether to also use seed keywords for search
        
        Returns:
            Dict with discovery statistics and canonical products
        """
        max_niches = max_niches or settings.batch_niche_limit
        max_candidates = max_candidates_per_niche or settings.batch_max_candidates
        
        logger.info(f"Starting discovery batch for {region}: max_niches={max_niches}, max_candidates={max_candidates}")
        
        # Load niches from DB
        niches = get_dynamic_niches(region=region, active_only=True, limit=max_niches)
        if not niches:
            logger.warning(f"No active niches found for {region}, seeding defaults")
            await self._seed_default_niches(region)
            niches = get_dynamic_niches(region=region, active_only=True, limit=max_niches)
        
        logger.info(f"Loaded {len(niches)} niches from DB")
        
        # Load seed keywords
        seed_keywords = []
        if use_seed_keywords:
            seed_keywords = get_seed_keywords(region=region, active_only=True, limit=20)
            logger.info(f"Loaded {len(seed_keywords)} seed keywords from DB")

        # Single universal agent — replaces AmazonScraper + FlipkartScraper
        web_agent = WebAgent(headless=settings.web_agent_headless)
        all_raw_products = []
        niche_results = {}

        # Process each niche
        for niche in niches:
            category = niche["category"]
            niche_id = niche.get("niche_id")
            search_limit = niche.get("search_limit", max_candidates)

            logger.info(f"Processing niche: {category} (limit: {search_limit})")

            # Search queries: niche category + seed keywords
            search_queries = [category]
            if use_seed_keywords and seed_keywords:
                for sk in seed_keywords[:3]:
                    search_queries.append(f"{category} {sk['keyword']}")

            niche_products = []

            for query in search_queries:
                if len(niche_products) >= search_limit:
                    break

                try:
                    # WebAgent searches Amazon.in + Flipkart + Meesho in one call
                    results = await web_agent.search_all_marketplaces(
                        query=query,
                        max_per_site=search_limit,
                        region=region,
                    )
                    for p in results:
                        if isinstance(p, RawProduct):
                            niche_products.append(p)

                    logger.info(f"  Query '{query}': {len(results)} products across all marketplaces")

                except Exception as e:
                    logger.error(f"Error searching '{query}': {e}")
                    continue

                # Rate limiting between queries
                await asyncio.sleep(settings.scraper_delay_ms / 1000)

            # Validate + deduplicate within niche
            if niche_products:
                valid_products, errors = self.validator.validate_batch(
                    [p.model_dump() for p in niche_products]
                )
                if errors:
                    logger.warning(f"  Validation errors: {len(errors)}")
                
                # Deduplicate
                canonicals = self.validator.deduplicate(valid_products)
                logger.info(f"  Niche '{category}': {len(niche_products)} raw -> {len(valid_products)} valid -> {len(canonicals)} canonical")
                
                # Limit to max_candidates
                canonicals = canonicals[:max_candidates]
                
                # Update niche scan stats
                if niche_id:
                    update_niche_scan(niche_id, products_found=len(canonicals))
                
                niche_results[category] = {
                    "raw_count": len(niche_products),
                    "valid_count": len(valid_products),
                    "canonical_count": len(canonicals),
                    "products": [c.model_dump() for c in canonicals],
                }
                
                all_raw_products.extend(niche_products)
            else:
                niche_results[category] = {
                    "raw_count": 0,
                    "valid_count": 0,
                    "canonical_count": 0,
                    "products": [],
                }
        
        # Final deduplication across all niches
        if all_raw_products:
            valid_all, _ = self.validator.validate_batch([p.model_dump() for p in all_raw_products])
            final_canonicals = self.validator.deduplicate(valid_all)
        else:
            final_canonicals = []
        
        logger.info(f"Discovery batch complete: {len(all_raw_products)} raw -> {len(final_canonicals)} final canonical products")
        
        return {
            "region": region,
            "niches_processed": len(niches),
            "total_raw_products": len(all_raw_products),
            "total_canonical_products": len(final_canonicals),
            "canonical_products": [c.model_dump() for c in final_canonicals],
            "niche_details": niche_results,
        }
    
    async def _seed_default_niches(self, region: str = "India"):
        """Seed default niches if DB is empty."""
        default_niches = [
            {"category": "Stainless Steel Insulated Water Bottle", "region": region, "search_limit": 3, "priority_score": 85},
            {"category": "Wireless Earbuds Noise Cancellation", "region": region, "search_limit": 3, "priority_score": 80},
            {"category": "Portable Blender USB Rechargeable", "region": region, "search_limit": 3, "priority_score": 75},
            {"category": "Electric Lunch Box Food Warmer", "region": region, "search_limit": 3, "priority_score": 70},
            {"category": "Magnetic Wireless Car Charger", "region": region, "search_limit": 3, "priority_score": 75},
            {"category": "Silicone Air Fryer Liners", "region": region, "search_limit": 3, "priority_score": 65},
            {"category": "Cordless Handheld Vacuum Cleaner", "region": region, "search_limit": 3, "priority_score": 70},
            {"category": "Smart LED Desk Lamp Wireless Charging", "region": region, "search_limit": 3, "priority_score": 65},
            {"category": "Portable Neck Fan USB Rechargeable", "region": region, "search_limit": 3, "priority_score": 60},
            {"category": "Collapsible Silicone Food Storage", "region": region, "search_limit": 3, "priority_score": 55},
        ]
        
        for niche in default_niches:
            try:
                record_dynamic_niche(
                    category=niche["category"],
                    region=niche["region"],
                    search_limit=niche["search_limit"],
                    priority_score=niche["priority_score"],
                    discovered_by="bootstrap",
                    source_signal="default_seed",
                )
            except Exception as e:
                logger.debug(f"Niche seed skipped: {e}")
        
        # Seed default keywords
        default_keywords = [
            "best under 1000", "viral 2024", "must have gadgets",
            "kitchen gadgets", "home organization", "car accessories",
            "fitness equipment", "beauty tools", "pet products",
            "office accessories", "travel essentials", "smart home",
        ]
        
        for kw in default_keywords:
            try:
                record_seed_keyword(
                    keyword=kw,
                    region=region,
                    source_platform="bootstrap",
                    velocity_score=50.0,
                )
            except Exception as e:
                logger.debug(f"Keyword seed skipped: {e}")
        
        logger.info(f"Seeded {len(default_niches)} default niches and {len(default_keywords)} seed keywords for {region}")
    
    async def run_single_niche_discovery(
        self,
        category: str,
        region: str = "India",
        max_candidates: int = None,
    ) -> List[CanonicalProduct]:
        """
        Run discovery for a single niche/category.
        Useful for targeted research.
        """
        max_candidates = max_candidates or settings.batch_max_candidates
        
        logger.info(f"Single niche discovery: {category} in {region}")
        
        agent = WebAgent()
        # Search all marketplaces using WebAgent (NIM 550B driven)
        all_products = await agent.search_all_marketplaces(
            query=category,
            max_per_site=max_candidates,
            region=region,
        )
        
        if not all_products:
            return []
        
        # Validate and deduplicate
        valid_products, errors = self.validator.validate_batch(
            [p.model_dump() for p in all_products]
        )
        
        canonicals = self.validator.deduplicate(valid_products)
        return canonicals[:max_candidates]


async def run_discovery_cli(
    region: str = "India",
    category: str = None,
    max_niches: int = 5,
    max_candidates: int = 3,
) -> Dict[str, Any]:
    """CLI entry point for discovery."""
    engine = DiscoveryEngine()
    
    if category:
        # Single niche mode
        canonicals = await engine.run_single_niche_discovery(category, region, max_candidates)
        return {
            "region": region,
            "category": category,
            "canonical_products": [c.model_dump() for c in canonicals],
        }
    else:
        # Batch mode
        return await engine.run_discovery_batch(
            region=region,
            max_niches=max_niches,
            max_candidates_per_niche=max_candidates,
        )


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="APRS V6 Pro Discovery Engine")
    parser.add_argument("--region", type=str, default="India", help="Target region")
    parser.add_argument("--category", type=str, help="Single category to research")
    parser.add_argument("--max-niches", type=int, default=5, help="Max niches in batch mode")
    parser.add_argument("--max-candidates", type=int, default=3, help="Max candidates per niche")
    
    args = parser.parse_args()
    
    result = asyncio.run(run_discovery_cli(
        region=args.region,
        category=args.category,
        max_niches=args.max_niches,
        max_candidates=args.max_candidates,
    ))
    
    import json
    print(json.dumps(result, indent=2, default=str))