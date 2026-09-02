"""
tools/ai_discovery_engine.py — AI-Powered Product & Website Discovery Engine with Validation.

Uses NVIDIA NIM to:
1. Discover NEW websites/platforms for trend hunting, marketplace scraping, review mining
2. Discover NEW micro-niche product categories from across the open web
3. Discover NEW seed keywords by expanding existing ones via NIM
4. Discover NEW communities (Reddit, forums) that discuss trending products
5. VALIDATE scraper data quality and auto soft-delete invalid findings
6. Generate AI rejection reasons for archive view

All discoveries and validations stored in DB tables with AI reasoning.
"""
import os
import sys
import json
import re
import logging
import urllib.request
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

# Project root import
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from models.nim_cluster import SupremeNIMCluster
from config.settings import NIM_MODELS, REGIONAL_PROFILES
from core.database import (
    record_discovered_source, get_discovered_sources, update_source_usage,
    record_dynamic_niche, get_dynamic_niches,
    record_seed_keyword, get_seed_keywords, update_seed_usage,
    record_trend_signal, soft_delete_product, get_all_products,
    record_scraper_validation, get_scraper_validations
)
from core.utils import normalize_region

logger = logging.getLogger("aprs.ai_discovery")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s — %(message)s")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


@dataclass
class DiscoveryResult:
    """Result of a discovery operation."""
    sources: List[Dict]
    niches: List[Dict]
    keywords: List[Dict]
    validations: List[Dict]
    total_new: int


class AIDiscoveryEngine:
    """
    Autonomous AI-powered discovery engine that uses NVIDIA NIM to:
    1. Discover new websites/platforms for trends, marketplaces, reviews
    2. Discover new product niches from open web
    3. Discover new seed keywords
    4. VALIDATE scraper data and auto soft-delete invalid findings
    5. Generate AI rejection reasons for archive
    """
    
    def __init__(self):
        self.cluster = SupremeNIMCluster()
        self.regions = list(REGIONAL_PROFILES.keys())
        self._validation_prompt_cache = {}

    def _jina_fetch(self, url: str, timeout: int = 12) -> str:
        """Fetch any URL via Jina Reader, returns markdown content."""
        try:
            jina_url = f"https://r.jina.ai/{url}"
            req = urllib.request.Request(jina_url, headers={"User-Agent": _UA, "Accept": "text/plain"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read(256 * 1024).decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"Jina fetch failed for {url}: {e}")
            return ""

    def _nim_query(self, prompt: str, task_type: str = "nemotron_scout", temperature: float = 0.15, max_tokens: int = 2000) -> str:
        """Query NIM with a prompt, return raw response text."""
        try:
            res = self.cluster.query(
                prompt=prompt,
                task_type=task_type if task_type in NIM_MODELS else "ultra_reasoning",
                system_prompt="You are an autonomous e-commerce intelligence agent. Respond in valid JSON only.",
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=45.0
            )
            if isinstance(res, dict):
                return res.get("content", "")
            return str(res)
        except Exception as e:
            logger.warning(f"NIM query error: {e}", exc_info=True)
            return ""

    def _extract_json(self, raw: str) -> dict:
        """Extract first JSON object from NIM response."""
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

    def _extract_json_array(self, raw: str) -> list:
        """Extract JSON array from NIM response."""
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return []

    # ═══════════════════════════════════════════════════════════════════════════════════════════
    # 1. AI-POWERED WEBSITE/PLATFORM DISCOVERY
    # ═══════════════════════════════════════════════════════════════════════════════════════════════

    def discover_trend_sources(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW trend sources (blogs, social, news, forums)."""
        prompt = f"""You are an AI trend scout. Find 12 REAL websites/platforms where people in {region} 
discover and discuss trending consumer products, viral gadgets, and e-commerce deals in 2026.

Include a mix of:
- Social platforms (TikTok hashtags, Instagram pages, YouTube channels)
- Deal/trend blogs and websites (deal sites, review blogs)
- Reddit communities (specific subreddits)
- News/review sites (tech news, consumer reports)
- Marketplace trend pages (Amazon Movers, Flipkart Trending, Meesho Trends)
- Forums and discussion boards

For each source, provide the EXACT URL that can be scraped for product trends.

Respond as a JSON array:
[
    {{"url": "https://...", "name": "...", "type": "social|blog|reddit|marketplace|forum|news", "description": "...", "reliability": 80, "discovery_reason": "why this source is valuable"}}
]"""
        raw = self._nim_query(prompt, task_type="nemotron_scout", max_tokens=3000)
        sources = self._extract_json_array(raw)
        stored = []

        for src in sources:
            url = src.get("url", "").strip()
            if not url or len(url) < 10 or not url.startswith("http"):
                continue

            # Validate URL exists via Jina Reader (lightweight check)
            content = self._jina_fetch(url, timeout=8)
            is_valid = len(content) > 100

            if is_valid:
                sid = record_discovered_source(
                    url=url,
                    source_type=src.get("type", "trend"),
                    source_name=src.get("name", ""),
                    description=src.get("description", ""),
                    region=region,
                    reliability_score=float(src.get("reliability", 70)),
                    discovered_by="nim_ai_discovery"
                )
                if sid:
                    stored.append({"source_id": sid, "url": url, "name": src.get("name", ""), "discovery_reason": src.get("discovery_reason", "")})
                    logger.info(f"AI Discovery: New trend source [{src.get('type','')}] {url[:60]}")

        logger.info(f"AI Discovery: Found {len(stored)} valid trend sources for {region}")
        return stored

    def discover_marketplace_sources(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW marketplace sources (Amazon, Flipkart, Meesho, Myntra, Shopify, etc.)."""
        reg_cfg = REGIONAL_PROFILES.get(region, {})
        known_mkts = ", ".join(reg_cfg.get("marketplaces", []))

        prompt = f"""You are an AI marketplace scout. Find 10 REAL e-commerce marketplaces, D2C aggregators, 
and product discovery platforms active in the {region} market that sell consumer products.

Already known: {known_mkts}
Find ADDITIONAL ones I might not know about. Include:
- Niche marketplaces (specialty categories)
- Shopify aggregators (themes, marketplaces)
- Local platforms (regional e-commerce)
- Wholesale/B2B sites (IndiaMart, TradeIndia, 1688, etc.)
- Social commerce (Instagram Shops, Facebook Marketplace, TikTok Shop)

For each, provide the search URL pattern where I can search for products by keyword.

Respond as a JSON array:
[
    {{"url": "https://...", "name": "...", "search_pattern": "https://...?q={{keyword}}", "description": "...", "reliability": 75, "discovery_reason": "why this marketplace is valuable"}}
]"""
        raw = self._nim_query(prompt, task_type="ultra_reasoning", max_tokens=3000)
        sources = self._extract_json_array(raw)
        stored = []

        for src in sources:
            url = src.get("url", "").strip()
            if not url or len(url) < 10:
                continue
            sid = record_discovered_source(
                url=url,
                source_type="marketplace",
                source_name=src.get("name", ""),
                description=json.dumps({"search_pattern": src.get("search_pattern", ""), "desc": src.get("description", "")}),
                region=region,
                reliability_score=float(src.get("reliability", 65)),
                discovered_by="nim_ai_discovery"
            )
            if sid:
                stored.append({"source_id": sid, "url": url, "name": src.get("name", ""), "discovery_reason": src.get("discovery_reason", "")})

        logger.info(f"AI Discovery: Found {len(stored)} marketplace sources for {region}")
        return stored

    def discover_communities(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW communities (Reddit, Discord, Facebook, forums)."""
        prompt = f"""You are an AI community scout. Find 10 active Reddit subreddits, Discord servers, 
Facebook groups, or online forums where people in {region} discuss:
- Trending products and gadgets
- E-commerce deals and finds
- Product reviews and recommendations
- Viral TikTok/Instagram products

For Reddit, provide the subreddit name (e.g., "tiktokmademebuyit").
For other platforms, provide the URL.

Respond as a JSON array:
[
    {{"url": "https://reddit.com/r/subreddit_name", "name": "r/subreddit_name", "platform": "reddit|discord|facebook|forum", "description": "...", "activity_level": "high|medium|low", "discovery_reason": "why this community is valuable"}}
]"""
        raw = self._nim_query(prompt, task_type="nemotron_scout", max_tokens=3000)
        sources = self._extract_json_array(raw)
        stored = []

        for src in sources:
            url = src.get("url", "").strip()
            name = src.get("name", "")
            if not url or len(url) < 5:
                continue
            platform = src.get("platform", "reddit")
            reliability = 80.0 if src.get("activity_level") == "high" else 60.0

            sid = record_discovered_source(
                url=url,
                source_type=f"community_{platform}",
                source_name=name,
                description=src.get("description", ""),
                region=region,
                reliability_score=reliability,
                discovered_by="nim_ai_discovery"
            )
            if sid:
                stored.append({"source_id": sid, "url": url, "name": name, "discovery_reason": src.get("discovery_reason", "")})

        logger.info(f"AI Discovery: Found {len(stored)} communities for {region}")
        return stored

    # ══════════════════════════════════════════════════════════════════════════════════════════════════════
    # 2. AI-POWERED PRODUCT NICHE DISCOVERY
    # ═══════════════════════════════════════════════════════════════════════════════════════════════════════

    def discover_new_niches(self, region: str = "India", count: int = 15) -> List[Dict]:
        """AI discovers NEW micro-niche product categories from open web."""
        reg_cfg = REGIONAL_PROFILES.get(region, {})
        currency = reg_cfg.get("currency", "INR")
        aov_min = reg_cfg.get("target_aov_min", 500)
        aov_max = reg_cfg.get("target_aov_max", 3000)

        existing = get_dynamic_niches(region=region, limit=500)
        existing_cats = [n["category"].lower() for n in existing]
        existing_sample = ", ".join(existing_cats[:20])

        prompt = f"""You are an AI product research agent. Discover {count} NEW emerging micro-niche consumer product categories for the {region} market.

Price range: {currency} {aov_min}-{aov_max}
Already known niches (DO NOT repeat these): {existing_sample}

Requirements:
- Each niche must be a SPECIFIC, search-ready product keyword (e.g., "Portable UV-C Sanitizer Wand" not just "sanitizer")
- Focus on PROBLEM-SOLVING products with 30+ day demand (NOT fads)
- Mix categories: Kitchen, Home, Beauty, Fitness, Electronics, Car, Pet, Office, Outdoor
- Include both mainstream and underserved niches
- Each niche must have clear problem it solves

Respond as a JSON array of objects:
[
    {{"category": "Exact Product Niche Name", "priority": 85, "reasoning": "why this niche is promising", "problem_solved": "what problem this solves", "target_audience": "who buys this"}}
]"""
        raw = self._nim_query(prompt, task_type="nemotron_scout", max_tokens=3000)
        niches = self._extract_json_array(raw)
        stored = []

        for n in niches:
            cat = n.get("category", "").strip()
            if not cat or len(cat) < 8 or cat.lower() in existing_cats:
                continue
            nid = record_dynamic_niche(
                category=cat,
                region=region,
                priority_score=float(n.get("priority", 50)),
                discovered_by="nim_ai_discovery",
                source_signal=n.get("reasoning", "")[:200]
            )
            if nid:
                stored.append({"niche_id": nid, "category": cat, "region": region, "reasoning": n.get("reasoning", ""), "problem_solved": n.get("problem_solved", ""), "target_audience": n.get("target_audience", "")})
                logger.info(f"AI Discovery: New niche [{region}] {cat[:50]}")

        logger.info(f"AI Discovery: {len(stored)} new niches discovered for {region}")
        return stored

    def expand_seed_keywords(self, region: str = "India", count: int = 20) -> List[Dict]:
        """AI generates fresh high-intent search seed keywords."""
        existing = get_seed_keywords(region=region, limit=100)
        existing_kws = [s["keyword"].lower() for s in existing]
        existing_sample = ", ".join(existing_kws[:15])

        prompt = f"""Generate {count} HIGH-INTENT product search queries that real shoppers in {region} 
would type into Google, Amazon, or social media to find trending consumer products.

Already known seeds (DO NOT repeat): {existing_sample}

Requirements:
- Must be 3-8 words long
- Must be PRODUCT-FOCUSED (not brand queries)
- Mix of: "best [product] under [price]", "viral [product] 2026", "[product] for [use case]", "[product] problems", "[product] reviews"
- Include trending categories: smart home, kitchen gadgets, car accessories, beauty tools, fitness, pet care, office, outdoor

Respond as a JSON array:
[
    {{"keyword": "viral kitchen gadgets under 1000", "velocity": 85, "intent": "discovery|comparison|problem_solving"}}
]"""
        raw = self._nim_query(prompt, task_type="nemotron_scout", max_tokens=3000)
        seeds = self._extract_json_array(raw)
        stored = []

        for s in seeds:
            kw = s.get("keyword", "").strip()
            if not kw or len(kw) < 8 or kw.lower() in existing_kws:
                continue
            sid = record_seed_keyword(
                keyword=kw,
                region=region,
                source_platform="nim_ai_generated",
                velocity_score=float(s.get("velocity", 50))
            )
            if sid:
                stored.append({"seed_id": sid, "keyword": kw, "intent": s.get("intent", "discovery")})

        logger.info(f"AI Discovery: {len(stored)} new seed keywords for {region}")
        return stored

    def explore_url_for_trends(self, url: str, region: str = "India") -> List[Dict]:
        """AI extracts product trends from ANY webpage."""
        content = self._jina_fetch(url, timeout=15)
        if len(content) < 50:
            logger.warning(f"AI Discovery: URL returned too little content: {url[:60]}")
            return []

        content_trimmed = content[:8000]

        prompt = f"""Analyze this webpage content and extract ANY trending product names, 
product categories, or viral product keywords mentioned.

URL: {url}
Region context: {region}

Content:
{content[:8000]}

Extract all product-related keywords and categories. For each:
- Give the exact product name or category
- Estimate trend velocity (0-100)
- Identify if it's a product, category, or trend

Respond as a JSON array:
[
    {{"keyword": "Portable Electric Coffee Grinder", "type": "product|category|trend", "velocity": 80, "context": "how it was mentioned"}}
]"""
        raw = self._nim_query(prompt, task_type="ultra_reasoning", max_tokens=3000)
        items = self._extract_json_array(raw)
        stored = []

        for item in items:
            kw = item.get("keyword", "").strip()
            if not kw or len(kw) < 5:
                continue
            item_type = item.get("type", "trend")
            velocity = float(item.get("velocity", 50))

            if item_type in ("product", "category"):
                nid = record_dynamic_niche(
                    category=kw, region=region,
                    priority_score=velocity,
                    discovered_by="url_exploration",
                    source_signal=url[:200]
                )
                if nid:
                    stored.append({"type": "niche", "keyword": kw, "niche_id": nid})

            sid = record_seed_keyword(
                keyword=kw, region=region,
                source_platform="url_exploration",
                parent_keyword=url[:100],
                velocity_score=velocity
            )
            if sid:
                stored.append({"type": "seed", "keyword": kw, "seed_id": sid})

        logger.info(f"AI Discovery: Extracted {len(stored)} items from {url[:50]}")
        return stored

    # ═══════════════════════════════════════════════════════════════════════════════════════════════════════
    # 3. AI SCRAPER DATA VALIDATOR (auto soft-delete invalid findings)
    # ═══════════════════════════════════════════════════════════════════════════════════════════════════════

    def validate_scraped_product(self, product_data: Dict, marketplace: str, region: str) -> Dict:
        """
        AI validates scraped product data quality.
        Returns validation result with auto soft-delete recommendation.
        """
        # Prepare product summary for AI
        summary = f"""
Product: {product_data.get('title', 'Unknown')}
Marketplace: {marketplace}
Region: {region}
Price: {product_data.get('price', 'N/A')} {product_data.get('currency', 'INR')}
Rating: {product_data.get('rating', 'N/A')}
Review Count: {product_data.get('review_count', 'N/A')}
Availability: {product_data.get('availability', 'unknown')}
URL: {product_data.get('listing_url', product_data.get('product_url', 'N/A'))}
Seller: {product_data.get('seller_name', 'N/A')}
Raw Data Keys: {list(product_data.keys())}
"""

        prompt = f"""You are an AI data quality validator for e-commerce product scraping.
Analyze this scraped product data and determine if it's VALID and USABLE for business decisions.

Product Data:
{summary}

Validate against these criteria:
1. DATA COMPLETENESS: Has title, price, URL? (required)
2. PRICE VALIDITY: Price > 0, reasonable for marketplace/region
3. URL VALIDITY: Valid product URL format, accessible
4. REALISTIC DATA: Rating 1-5, review count reasonable, availability logical
5. MARKETPLACE CONSISTENCY: Data matches expected format for {marketplace}
6. DUPLICATE CHECK: No obvious duplicate of existing products

Respond as JSON:
{{
    "is_valid": true/false,
    "confidence": 0-100,
    "issues": ["issue1", "issue2"],
    "auto_soft_delete": true/false,
    "rejection_reason": "specific reason if invalid",
    "rejection_category": "missing_data|invalid_price|invalid_url|unrealistic_data|duplicate|marketplace_mismatch",
    "ai_notes": "detailed analysis"
}}"""

        raw = self._nim_query(prompt, task_type="ultra_reasoning", max_tokens=1500)
        try:
            validation = self._extract_json(raw)
        except:
            validation = {"is_valid": True, "confidence": 50, "issues": ["AI validation failed"], "auto_soft_delete": False, "rejection_reason": "Validation error", "rejection_category": "validation_error", "ai_notes": "AI validation failed"}

        # Record validation in DB
        validation_record = {
            "product_id": product_data.get("product_id", ""),
            "marketplace": marketplace,
            "region": region,
            "is_valid": validation.get("is_valid", True),
            "confidence": validation.get("confidence", 50),
            "issues": json.dumps(validation.get("issues", [])),
            "auto_soft_delete": validation.get("auto_soft_delete", False),
            "rejection_reason": validation.get("rejection_reason", ""),
            "rejection_category": validation.get("rejection_category", ""),
            "ai_notes": validation.get("ai_notes", ""),
            "raw_product_data": json.dumps(product_data, default=str)[:5000]
        }

        try:
            record_scraper_validation(validation_record)
        except Exception as e:
            logger.warning(f"Failed to record validation: {e}")

        # Auto soft-delete if AI recommends
        if validation.get("auto_soft_delete", False) and product_data.get("product_id"):
            try:
                soft_delete_product(
                    product_data["product_id"],
                    f"AI Validation Rejected: {validation.get('rejection_reason', 'Invalid data')}",
                    deleted_by="ai_validator"
                )
                logger.info(f"AI Validator: Auto soft-deleted product {product_data['product_id']} - {validation.get('rejection_reason')}")
            except Exception as e:
                logger.warning(f"Failed to soft-delete product: {e}")

        return validation

    def validate_batch_products(self, products: List[Dict], marketplace: str, region: str) -> List[Dict]:
        """Validate a batch of scraped products."""
        results = []
        for product in products:
            validation = self.validate_scraped_product(product, marketplace, region)
            results.append(validation)
        return results

    # ═════════════════════════════════════════════════════════════════════════════════════════════════════════
    # 4. FULL AI DISCOVERY CYCLE
    # ═════════════════════════════════════════════════════════════════════════════════════════════════════════

    def run_full_ai_discovery_cycle(self, region: str = "India") -> Dict[str, Any]:
        """Execute complete AI discovery cycle for a region."""
        logger.info(f"AI Discovery Cycle: Starting full discovery for {region}")
        results = {
            "region": region,
            "new_sources": [],
            "new_marketplaces": [],
            "new_communities": [],
            "new_niches": [],
            "new_seeds": [],
            "validations": [],
            "total_new": 0
        }

        # 1. Discover new trend sources
        try:
            results["new_sources"] = self.discover_trend_sources(region)
        except Exception as e:
            logger.warning(f"AI Discovery: trend sources failed: {e}", exc_info=True)

        # 2. Discover marketplace sources
        try:
            results["new_marketplaces"] = self.discover_marketplace_sources(region)
        except Exception as e:
            logger.warning(f"AI Discovery: marketplace sources failed: {e}", exc_info=True)

        # 3. Discover communities
        try:
            results["new_communities"] = self.discover_communities(region)
        except Exception as e:
            logger.warning(f"AI Discovery: communities failed: {e}", exc_info=True)

        # 4. Discover new niches
        try:
            results["new_niches"] = self.discover_new_niches(region, count=15)
        except Exception as e:
            logger.warning(f"AI Discovery: niches failed: {e}", exc_info=True)

        # 5. Expand seed keywords
        try:
            results["new_seeds"] = self.expand_seed_keywords(region, count=20)
        except Exception as e:
            logger.warning(f"AI Discovery: seeds failed: {e}", exc_info=True)

        results["total_new"] = sum(len(v) for v in results.values() if isinstance(v, list))
        logger.info(f"AI Discovery Cycle: Complete for {region} — {results['total_new']} total discoveries")
        return results

    def seed_initial_data(self):
        """One-time bootstrap: insert baseline static seeds and sources."""
        from tools.trend_scout.trend_aggregator import VIRAL_SEED_ROOTS, COMMUNITY_SUBREDDITS
        from core.background_daemon import STATIC_FALLBACK_NICHES

        # Seed keywords
        existing_seeds = get_seed_keywords(region="India", limit=1)
        if not existing_seeds:
            for region, seeds in VIRAL_SEED_ROOTS.items():
                for kw in seeds:
                    record_seed_keyword(kw, region=region, source_platform="bootstrap", velocity_score=75.0)
            logger.info("AI Discovery: Bootstrapped seed keywords")

        # Community sources
        existing_communities = get_discovered_sources(source_type="community_reddit")
        if not existing_communities:
            for sub in COMMUNITY_SUBREDDITS:
                record_discovered_source(
                    url=f"https://www.reddit.com/r/{sub}/hot.json",
                    source_type="community_reddit",
                    source_name=f"r/{sub}",
                    description=f"Reddit community tracking viral products",
                    region="Global",
                    reliability_score=75.0,
                    discovered_by="bootstrap"
                )
            logger.info("AI Discovery: Bootstrapped community sources")

        # Niches
        existing_niches = get_dynamic_niches(limit=1)
        if not existing_niches:
            for niche in STATIC_FALLBACK_NICHES:
                record_dynamic_niche(
                    category=niche["category"],
                    region=niche["region"],
                    search_limit=niche.get("limit", 3),
                    priority_score=60.0,
                    discovered_by="bootstrap"
                )
            logger.info("AI Discovery: Bootstrapped niches")


# Convenience function for easy integration
async def run_ai_discovery_cycle(region: str = "India") -> Dict[str, Any]:
    """Run one AI discovery cycle for a region."""
    engine = AIDiscoveryEngine()
    return engine.run_full_ai_discovery_cycle(region)


if __name__ == "__main__":
    engine = AIDiscoveryEngine()
    engine.seed_initial_data()
    print("Bootstrapped. Running AI discovery cycle for India...")
    result = engine.run_full_ai_discovery_cycle("India")
    print(f"\nAI Discovery Results:")
    for k, v in result.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} items")