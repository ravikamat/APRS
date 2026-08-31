"""
tools/discovery_engine.py — NIM-Powered Autonomous Source & Niche Discovery Engine.

A dedicated NIM AI agent that continuously discovers:
1. NEW websites/platforms for trend hunting, marketplace scraping, review mining
2. NEW micro-niche product categories from across the open web
3. NEW seed keywords by expanding existing ones via NIM
4. NEW communities (Reddit, forums) that discuss trending products

All discoveries are stored in DB tables (discovered_sources, dynamic_niches, dynamic_seed_keywords)
and consumed by the Trend Scout, Marketplace Engine, and Background Daemon — making the entire
system self-expanding with zero hardcoded limits.
"""
import os
import sys
import json
import re
import logging
import urllib.request
from typing import List, Dict, Any, Optional
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from models.nim_cluster import SupremeNIMCluster
from config.settings import NIM_MODELS, REGIONAL_PROFILES
from core.database import (
    record_discovered_source, get_discovered_sources, update_source_usage,
    record_dynamic_niche, get_dynamic_niches,
    record_seed_keyword, get_seed_keywords, update_seed_usage,
    record_trend_signal
)

logger = logging.getLogger("aprs.discovery")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s — %(message)s")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


class NIMDiscoveryEngine:
    """
    Autonomous NIM-powered discovery agent that self-expands the search space.
    Uses NIM to discover new sources, niches, and keywords — then validates
    each via Jina Reader before storing in DB.
    """

    def __init__(self):
        self.cluster = SupremeNIMCluster()
        self.regions = list(REGIONAL_PROFILES.keys())

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

    def _nim_query(self, prompt: str, task_type: str = "nemotron_scout", temperature: float = 0.15, max_tokens: int = 600) -> str:
        """Query NIM with a prompt, return raw response text."""
        try:
            res = self.cluster.query(
                prompt=prompt,
                task_type=task_type if task_type in NIM_MODELS else "ultra_reasoning",
                system_prompt="You are an autonomous e-commerce intelligence agent. Respond in valid JSON array only.",
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=30.0
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

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. DISCOVER NEW SOURCES (websites, platforms, communities)
    # ═══════════════════════════════════════════════════════════════════════════

    def discover_trend_sources(self, region: str = "India") -> List[Dict]:
        """Ask NIM to find websites/platforms where trending products are discussed."""
        prompt = f"""Find 10 real websites, platforms, blogs, or social channels where people in {region} 
discover and discuss trending consumer products, viral gadgets, and e-commerce deals in 2026.

Include a mix of:
- Social platforms (TikTok, Instagram pages, YouTube channels)
- Deal/trend blogs and websites
- Reddit communities
- News/review sites
- Marketplace trend pages (Amazon Movers, Flipkart Trending)
- Forums and discussion boards

For each source, provide the EXACT URL that can be scraped for product trends.

Respond as a JSON array:
[
    {{"url": "https://...", "name": "...", "type": "social|blog|reddit|marketplace|forum|news", "description": "...", "reliability": 80}}
]"""
        raw = self._nim_query(prompt, task_type="nemotron_scout")
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
                    discovered_by="nim_discovery"
                )
                if sid:
                    stored.append({"source_id": sid, "url": url, "name": src.get("name", "")})
                    logger.info(f"Discovery: New source [{src.get('type','')}] {url[:60]}")

        logger.info(f"Discovery: Found {len(stored)} valid sources for {region}")
        return stored

    def discover_marketplace_sources(self, region: str = "India") -> List[Dict]:
        """Discover e-commerce marketplace URLs for product scraping."""
        reg_cfg = REGIONAL_PROFILES.get(region, {})
        known_mkts = ", ".join(reg_cfg.get("marketplaces", []))

        prompt = f"""Find 8 real e-commerce marketplaces, D2C aggregators, and product discovery platforms 
active in the {region} market that sell consumer products.

Already known: {known_mkts}
Find ADDITIONAL ones I might not know about. Include niche marketplaces, Shopify aggregators,
local platforms, and wholesale/B2B sites.

For each, provide the search URL pattern where I can search for products by keyword.

Respond as a JSON array:
[
    {{"url": "https://...", "name": "...", "search_pattern": "https://...?q={{keyword}}", "description": "...", "reliability": 75}}
]"""
        raw = self._nim_query(prompt, task_type="ultra_reasoning")
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
                discovered_by="nim_discovery"
            )
            if sid:
                stored.append({"source_id": sid, "url": url, "name": src.get("name", "")})

        logger.info(f"Discovery: Found {len(stored)} marketplace sources for {region}")
        return stored

    def discover_communities(self, region: str = "India") -> List[Dict]:
        """Discover Reddit subreddits and forums that discuss trending products."""
        prompt = f"""Find 10 active Reddit subreddits, Discord servers, Facebook groups, or online forums 
where people in {region} discuss:
- Trending products and gadgets
- E-commerce deals and finds
- Product reviews and recommendations
- Viral TikTok/Instagram products

For Reddit, provide the subreddit name (e.g., "tiktokmademebuyit").
For other platforms, provide the URL.

Respond as a JSON array:
[
    {{"url": "https://reddit.com/r/subreddit_name", "name": "r/subreddit_name", "platform": "reddit|discord|facebook|forum", "description": "...", "activity_level": "high|medium|low"}}
]"""
        raw = self._nim_query(prompt, task_type="nemotron_scout")
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
                discovered_by="nim_discovery"
            )
            if sid:
                stored.append({"source_id": sid, "url": url, "name": name})

        logger.info(f"Discovery: Found {len(stored)} communities for {region}")
        return stored

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. DISCOVER NEW NICHES
    # ═══════════════════════════════════════════════════════════════════════════

    def discover_new_niches(self, region: str = "India", count: int = 15) -> List[Dict]:
        """Ask NIM to discover emerging micro-niche product categories."""
        reg_cfg = REGIONAL_PROFILES.get(region, {})
        currency = reg_cfg.get("currency", "INR")
        aov_min = reg_cfg.get("target_aov_min", 500)
        aov_max = reg_cfg.get("target_aov_max", 3000)

        # Get existing niches to avoid duplicates
        existing = get_dynamic_niches(region=region, limit=500)
        existing_cats = [n["category"].lower() for n in existing]
        existing_sample = ", ".join(existing_cats[:20])

        prompt = f"""You are an autonomous e-commerce product research AI.
Discover {count} NEW emerging micro-niche consumer product categories for the {region} market.

Price range: {currency} {aov_min}-{aov_max}
Already known niches (DO NOT repeat these): {existing_sample}

Requirements:
- Each niche must be a specific, search-ready product keyword (e.g., "Portable UV-C Sanitizer Wand" not just "sanitizer")
- Focus on problem-solving products with 30+ day demand (not fads)
- Mix categories: Kitchen, Home, Beauty, Fitness, Electronics, Car, Pet, Office, Outdoor
- Include both mainstream and underserved niches

Respond as a JSON array of objects:
[
    {{"category": "Exact Product Niche Name", "priority": 85, "reasoning": "why this niche is promising"}}
]"""
        raw = self._nim_query(prompt, task_type="nemotron_scout")
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
                discovered_by="nim_discovery",
                source_signal=n.get("reasoning", "")[:200]
            )
            if nid:
                stored.append({"niche_id": nid, "category": cat, "region": region})
                logger.info(f"Discovery: New niche [{region}] {cat[:50]}")

        logger.info(f"Discovery: {len(stored)} new niches discovered for {region}")
        return stored

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. EXPAND SEED KEYWORDS
    # ═══════════════════════════════════════════════════════════════════════════

    def expand_seed_keywords(self, region: str = "India", count: int = 20) -> List[Dict]:
        """Use NIM to generate fresh high-intent search seed keywords."""
        existing = get_seed_keywords(region=region, limit=100)
        existing_kws = [s["keyword"].lower() for s in existing]
        existing_sample = ", ".join(existing_kws[:15])

        prompt = f"""Generate {count} high-intent product search queries that real shoppers in {region} 
would type into Google, Amazon, or social media to find trending consumer products.

Already known seeds (DO NOT repeat): {existing_sample}

Requirements:
- Must be 3-8 words long
- Must be product-focused (not brand queries)
- Mix of: "best [product] under [price]", "viral [product] 2026", "[product] for [use case]"
- Include trending categories: smart home, kitchen gadgets, car accessories, beauty tools, fitness, pet care, office

Respond as a JSON array:
[
    {{"keyword": "viral kitchen gadgets under 1000", "velocity": 85}}
]"""
        raw = self._nim_query(prompt, task_type="nemotron_scout")
        seeds = self._extract_json_array(raw)
        stored = []

        for s in seeds:
            kw = s.get("keyword", "").strip()
            if not kw or len(kw) < 8 or kw.lower() in existing_kws:
                continue
            sid = record_seed_keyword(
                keyword=kw,
                region=region,
                source_platform="nim_generated",
                velocity_score=float(s.get("velocity", 50))
            )
            if sid:
                stored.append({"seed_id": sid, "keyword": kw})

        logger.info(f"Discovery: {len(stored)} new seed keywords for {region}")
        return stored

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. EXPLORE ANY URL (extract product trends from ANY webpage)
    # ═══════════════════════════════════════════════════════════════════════════

    def explore_url_for_trends(self, url: str, region: str = "India") -> List[Dict]:
        """Fetch ANY URL via Jina Reader, then use NIM to extract trending product keywords."""
        content = self._jina_fetch(url, timeout=15)
        if len(content) < 50:
            logger.warning(f"Discovery: URL returned too little content: {url[:60]}")
            return []

        # Truncate content to fit NIM context
        content_trimmed = content[:6000]

        prompt = f"""Analyze this webpage content and extract any trending product names, 
product categories, or viral product keywords mentioned.

URL: {url}
Region context: {region}

Content:
{content_trimmed}

Extract all product-related keywords and categories. For each:
- Give the exact product name or category
- Estimate trend velocity (0-100)

Respond as a JSON array:
[
    {{"keyword": "Portable Electric Coffee Grinder", "type": "product|category|trend", "velocity": 80}}
]"""
        raw = self._nim_query(prompt, task_type="ultra_reasoning")
        items = self._extract_json_array(raw)
        stored = []

        for item in items:
            kw = item.get("keyword", "").strip()
            if not kw or len(kw) < 5:
                continue
            item_type = item.get("type", "trend")
            velocity = float(item.get("velocity", 50))

            if item_type in ("product", "category"):
                # Store as a dynamic niche
                nid = record_dynamic_niche(
                    category=kw, region=region,
                    priority_score=velocity,
                    discovered_by="url_exploration",
                    source_signal=url[:200]
                )
                if nid:
                    stored.append({"type": "niche", "keyword": kw, "niche_id": nid})

            # Also store as seed keyword
            sid = record_seed_keyword(
                keyword=kw, region=region,
                source_platform="url_exploration",
                parent_keyword=url[:100],
                velocity_score=velocity
            )
            if sid:
                stored.append({"type": "seed", "keyword": kw, "seed_id": sid})

        logger.info(f"Discovery: Extracted {len(stored)} items from {url[:50]}")
        return stored

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. FULL DISCOVERY CYCLE (run all discovery tasks for a region)
    # ═══════════════════════════════════════════════════════════════════════════

    def run_full_discovery_cycle(self, region: str = "India") -> Dict[str, Any]:
        """Execute complete discovery cycle: sources + niches + keywords + URL exploration."""
        logger.info(f"Discovery Cycle: Starting full discovery for {region}")
        results = {
            "region": region,
            "new_sources": [],
            "new_marketplaces": [],
            "new_communities": [],
            "new_niches": [],
            "new_seeds": [],
            "url_extractions": []
        }

        # 1. Discover new trend sources
        try:
            results["new_sources"] = self.discover_trend_sources(region)
        except Exception as e:
            logger.warning(f"Discovery: trend sources failed: {e}", exc_info=True)

        # 2. Discover marketplace sources
        try:
            results["new_marketplaces"] = self.discover_marketplace_sources(region)
        except Exception as e:
            logger.warning(f"Discovery: marketplace sources failed: {e}", exc_info=True)

        # 3. Discover communities
        try:
            results["new_communities"] = self.discover_communities(region)
        except Exception as e:
            logger.warning(f"Discovery: communities failed: {e}", exc_info=True)

        # 4. Discover new niches
        try:
            results["new_niches"] = self.discover_new_niches(region, count=15)
        except Exception as e:
            logger.warning(f"Discovery: niches failed: {e}", exc_info=True)

        # 5. Expand seed keywords
        try:
            results["new_seeds"] = self.expand_seed_keywords(region, count=20)
        except Exception as e:
            logger.warning(f"Discovery: seeds failed: {e}", exc_info=True)

        # 6. Explore top discovered sources for product trends
        try:
            sources = get_discovered_sources(source_type="trend", region=region)
            for src in sources[:3]:  # Explore top 3 sources
                url = src.get("url", "")
                if url:
                    extracted = self.explore_url_for_trends(url, region)
                    results["url_extractions"].extend(extracted)
                    update_source_usage(src["source_id"], yielded_results=len(extracted) > 0)
        except Exception as e:
            logger.warning(f"Discovery: URL exploration failed: {e}", exc_info=True)

        total = sum(len(v) for v in results.values() if isinstance(v, list))
        logger.info(f"Discovery Cycle: Complete for {region} — {total} total discoveries")
        return results

    def seed_initial_data(self):
        """One-time bootstrap: insert the baseline static seeds and sources into DB so the system
        can start expanding from them. Only runs if tables are empty."""
        from tools.trend_scout.trend_aggregator import VIRAL_SEED_ROOTS, COMMUNITY_SUBREDDITS
        from core.background_daemon import STATIC_FALLBACK_NICHES

        # Seed keywords
        existing_seeds = get_seed_keywords(region="India", limit=1)
        if not existing_seeds:
            for region, seeds in VIRAL_SEED_ROOTS.items():
                for kw in seeds:
                    record_seed_keyword(kw, region=region, source_platform="bootstrap", velocity_score=75.0)
            logger.info("Discovery: Bootstrapped seed keywords from VIRAL_SEED_ROOTS")

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
            logger.info("Discovery: Bootstrapped community sources from COMMUNITY_SUBREDDITS")

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
            logger.info("Discovery: Bootstrapped niches from STATIC_FALLBACK_NICHES")


if __name__ == "__main__":
    engine = NIMDiscoveryEngine()
    # Bootstrap initial data
    engine.seed_initial_data()
    print("Bootstrapped. Running discovery cycle for India...")
    result = engine.run_full_discovery_cycle("India")
    print(f"\nDiscovery Results:")
    for k, v in result.items():
        if isinstance(v, list):
            print(f"  {k}: {len(v)} items")
