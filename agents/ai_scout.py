"""
agents/ai_scout.py — AI Scout Agent for Autonomous Website & Platform Discovery.

Daily (first run of day): Uses NIM 550B to discover NEW sources with 10x volume:
- Trend sources: 120 (blogs, social, news, forums)
- Marketplace sources: 100 (e-commerce, D2C, wholesale, social commerce)
- Community sources: 100 (Reddit, Discord, Facebook, forums)
- Supplier sources: 80 (IndiaMART, Alibaba, 1688, TradeIndia)
- Niches: 150 (micro-niche product categories)
- Keywords: 200 (high-velocity search terms)

All discoveries stored in discovered_sources with reliability scores.
Continues to next category if any category fails.
Sources ranked by reliability score and discovery value.
"""
import json
import logging
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import sys

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings, REGIONAL_PROFILES
from core.database import (
    record_discovered_source, get_discovered_sources, update_source_usage,
    record_dynamic_niche, get_dynamic_niches,
    record_seed_keyword, get_seed_keywords, update_seed_usage,
)
from core.llm_router import LLMRouter, LLMTaskType

logger = logging.getLogger("aprs.ai_scout")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


@dataclass
class ScoutResult:
    """Result of AI Scout discovery run."""
    trend_sources: List[Dict] = field(default_factory=list)
    marketplace_sources: List[Dict] = field(default_factory=list)
    community_sources: List[Dict] = field(default_factory=list)
    supplier_sources: List[Dict] = field(default_factory=list)
    niches: List[Dict] = field(default_factory=list)
    keywords: List[Dict] = field(default_factory=list)
    total_new: int = 0
    errors: List[str] = field(default_factory=list)


class AIScoutAgent:
    """
    AI Scout Agent — Autonomous discovery of new web sources and niches.
    
    Runs daily (first run of day) to find:
    1. NEW trend sources: blogs, social media, news, forums (120 target)
    2. NEW marketplace sources: e-commerce, D2C, wholesale, social commerce (100 target)
    3. NEW community sources: Reddit, Discord, Facebook groups (100 target)
    4. NEW supplier sources: IndiaMART, Alibaba, 1688, TradeIndia (80 target)
    5. NEW niches: micro-niche product categories (150 target)
    6. NEW seed keywords: expanded keywords for search (200 target)
    
    All discoveries stored in discovered_sources with reliability scores.
    Continues to next category if any category fails.
    Sources ranked by reliability score and discovery value.
    """
    
    # 10x multipliers for daily discovery
    TARGET_COUNTS = {
        "trend": 120,
        "marketplace": 100,
        "community": 100,
        "supplier": 80,
        "niche": 150,
        "keyword": 200,
    }
    
    def __init__(self):
        self.llm_router = None
    
    def _get_llm_router(self):
        if self.llm_router is None:
            self.llm_router = LLMRouter()
        return self.llm_router
    
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
    
    def _extract_json_array(self, raw: str) -> list:
        """Extract JSON array from LLM response."""
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return []
    
    def _rank_sources(self, sources: List[Dict], source_type: str) -> List[Dict]:
        """Rank sources by reliability score and discovery value."""
        for src in sources:
            # Calculate composite rank score
            reliability = float(src.get("reliability", 50))
            # Add bonus for specific valuable attributes
            bonus = 0
            if source_type == "marketplace" and src.get("search_pattern"):
                bonus += 10
            if source_type == "trend" and src.get("type") in ["social", "news"]:
                bonus += 5
            if source_type == "community" and src.get("activity_level") == "high":
                bonus += 10
            if source_type == "supplier" and src.get("search_pattern"):
                bonus += 10
            
            src["rank_score"] = reliability + bonus
        
        # Sort by rank_score descending
        sources.sort(key=lambda x: x.get("rank_score", 0), reverse=True)
        return sources
    
    async def _nim_query(self, prompt: str, task_type: LLMTaskType = LLMTaskType.DEEP_REASONING, 
                         temperature: float = 0.15, max_tokens: int = 3000) -> str:
        """Query NIM 550B via LLMRouter."""
        try:
            router = self._get_llm_router()
            response = await router.chat(
                messages=[
                    {"role": "system", "content": "You are an autonomous e-commerce intelligence agent. Respond in valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                agent_name="ai_scout",
                task_type=task_type,
                json_mode=True,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if isinstance(response, dict):
                return response.get("content", response.get("text", ""))
            return str(response)
        except Exception as e:
            logger.warning(f"LLM query error: {e}")
            return ""
    
    def _extract_json_array(self, raw: str) -> list:
        """Extract JSON array from LLM response."""
        try:
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except (json.JSONDecodeError, ValueError):
            pass
        return []
    
    async def _run_discovery_category(self, category: str, prompt: str, 
                                       source_type: str, region: str,
                                       process_func) -> List[Dict]:
        """Run a single discovery category with error handling."""
        target = self.TARGET_COUNTS.get(category, 50)
        logger.info(f"AI Scout: Discovering {target} {category} sources for {region}")
        
        try:
            raw = await self._nim_query(prompt, LLMTaskType.DEEP_REASONING, 0.15, 4000)
            sources = self._extract_json_array(raw)
            
            if not sources:
                logger.warning(f"AI Scout: No {category} sources returned from LLM")
                return []
            
            # Get existing to avoid duplicates
            existing = get_discovered_sources(source_type=source_type, region=region, active_only=True, limit=500)
            existing_urls = {s.get("url", "") for s in existing}
            
            # Process and store
            stored = []
            for src in sources:
                try:
                    result = await process_func(src, region, existing_urls)
                    if result:
                        stored.append(result)
                except Exception as e:
                    logger.debug(f"Failed to process {category} source: {e}")
                    continue
            
            # Rank by reliability and value
            stored = self._rank_sources(stored, category)
            
            logger.info(f"AI Scout: Discovered {len(stored)} {category} sources for {region} (target: {target})")
            return stored
            
        except Exception as e:
            error_msg = f"{category} discovery failed: {e}"
            logger.error(f"AI Scout: {error_msg}")
            return []  # Return empty list, continue to next category
    
    async def discover_trend_sources(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW trend sources (blogs, social, news, forums) - 120 target."""
        
        existing = get_discovered_sources(source_type="trend", region=region, active_only=True, limit=500)
        existing_urls = {s.get("url", "") for s in existing}
        
        prompt = f"""You are an AI trend scout. Find {self.TARGET_COUNTS['trend']} REAL websites/platforms where people in {region} 
discover and discuss trending consumer products, viral gadgets, and e-commerce deals in 2026.

Include a diverse mix of:
- Social platforms (TikTok hashtags, Instagram pages, YouTube channels, Twitter/X lists)
- Deal/trend blogs and websites (deal sites, review blogs, affiliate sites)
- Reddit communities (specific subreddits for deals, products, reviews)
- News/review sites (tech news, consumer reports, product launches)
- Marketplace trend pages (Amazon Movers, Flipkart Trending, Meesho Trends, JioMart Trends)
- Forums and discussion boards (product discussions, deal hunting)
- Video platforms (YouTube trending, Instagram Reels, TikTok discovery)
- Affiliate/cashback sites with trending sections

For each source, provide the EXACT URL that can be scraped for product trends.

Respond as a JSON array:
[
    {{"url": "https://...", "name": "...", "type": "social|blog|reddit|marketplace|forum|news|video|affiliate", "description": "...", "reliability": 80, "discovery_reason": "why this source is valuable"}}
]"""
        
        async def process_trend(src, region, existing_urls):
            url = src.get("url", "").strip()
            if not url or len(url) < 10 or url in existing_urls:
                return None
            sid = record_discovered_source(
                url=url,
                source_type="trend",
                source_name=src.get("name", ""),
                description=src.get("description", ""),
                region=region,
                reliability_score=float(src.get("reliability", 65)),
                discovered_by="ai_scout"
            )
            if sid:
                existing_urls.add(url)
                return {"source_id": sid, "url": url, "name": src.get("name", ""), "type": src.get("type", "trend"), "rank_score": src.get("reliability", 65)}
            return None
        
        return await self._run_discovery_category("trend", prompt, "trend", region, process_trend)
    
    async def discover_marketplace_sources(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW marketplace sources - 100 target."""
        
        reg_cfg = REGIONAL_PROFILES.get(region, {})
        known_mkts = ", ".join(reg_cfg.get("marketplaces", []))
        
        prompt = f"""You are an AI marketplace scout. Find {self.TARGET_COUNTS['marketplace']} REAL e-commerce marketplaces, D2C aggregators, 
and product discovery platforms active in the {region} market that sell consumer products.

Already known: {known_mkts}
Find ADDITIONAL ones I might not know about. Include:
- Niche marketplaces (specialty categories: beauty, electronics, home, fashion, pet, auto)
- Shopify aggregators (themes, marketplaces, app stores)
- Local/regional platforms (state-specific, city-specific e-commerce)
- Wholesale/B2B sites (IndiaMart, TradeIndia, ExportersIndia, 1688, GlobalSources, DHgate, Alibaba)
- Social commerce (Instagram Shops, Facebook Marketplace, TikTok Shop, WhatsApp Catalog)
- Cashback/affiliate aggregators with product feeds
- Subscription box platforms
- Rental/resale marketplaces

For each, provide the EXACT search URL pattern where I can search for products by keyword.

Respond as a JSON array:
[
    {{"url": "https://...", "name": "...", "search_pattern": "https://...?q={{keyword}}", "description": "...", "reliability": 75, "discovery_reason": "why this marketplace is valuable"}}
]"""
        
        async def process_marketplace(src, region, existing_urls):
            url = src.get("url", "").strip()
            if not url or len(url) < 10 or url in existing_urls:
                return None
            sid = record_discovered_source(
                url=url,
                source_type="marketplace",
                source_name=src.get("name", ""),
                description=json.dumps({"search_pattern": src.get("search_pattern", ""), "desc": src.get("description", "")}),
                region=region,
                reliability_score=float(src.get("reliability", 65)),
                discovered_by="ai_scout"
            )
            if sid:
                existing_urls.add(url)
                return {"source_id": sid, "url": url, "name": src.get("name", ""), "discovery_reason": src.get("discovery_reason", ""), "rank_score": src.get("reliability", 65)}
            return None
        
        return await self._run_discovery_category("marketplace", prompt, "marketplace", region, process_marketplace)
    
    async def discover_communities(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW communities (Reddit, Discord, Facebook, forums) - 100 target."""
        
        prompt = f"""You are an AI community scout. Find {self.TARGET_COUNTS['community']} active Reddit subreddits, Discord servers, 
Facebook groups, or online forums where people in {region} discuss:
- Trending products and gadgets
- E-commerce deals and finds
- Product reviews and recommendations
- Viral TikTok/Instagram/YouTube products
- Deal hunting and price drops
- DIY/product modification communities

Include diverse platforms:
- Reddit (specific subreddits)
- Discord (server invites or discovery URLs)
- Facebook Groups (public group URLs)
- Forums (traditional forums, specialized communities)
- Telegram channels (public)
- Quora spaces/topics

For Reddit, provide the subreddit name (e.g., "tiktokmademebuyit").
For other platforms, provide the URL.

Respond as a JSON array:
[
    {{"url": "https://reddit.com/r/subreddit_name", "name": "r/subreddit_name", "platform": "reddit|discord|facebook|forum|telegram|quora", "description": "...", "activity_level": "high|medium|low", "discovery_reason": "why this community is valuable"}}
]"""
        
        async def process_community(src, region, existing_urls):
            url = src.get("url", "").strip()
            name = src.get("name", "")
            if not url or len(url) < 5 or url in existing_urls:
                return None
            platform = src.get("platform", "reddit")
            reliability = 80.0 if src.get("activity_level") == "high" else (60.0 if src.get("activity_level") == "medium" else 40.0)
            
            sid = record_discovered_source(
                url=url,
                source_type=f"community_{platform}",
                source_name=name,
                description=src.get("description", ""),
                region=region,
                reliability_score=reliability,
                discovered_by="ai_scout"
            )
            if sid:
                existing_urls.add(url)
                return {"source_id": sid, "url": url, "name": name, "discovery_reason": src.get("discovery_reason", ""), "rank_score": reliability}
            return None
        
        return await self._run_discovery_category("community", prompt, "community_reddit", region, process_community)
    
    async def discover_supplier_sources(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW supplier sources (wholesale, B2B, manufacturer directories) - 80 target."""
        
        prompt = f"""You are an AI supplier scout. Find {self.TARGET_COUNTS['supplier']} REAL wholesale/B2B platforms, manufacturer directories, 
and supplier marketplaces where e-commerce sellers in {region} can source products.

Include:
- Indian wholesale platforms (IndiaMART, TradeIndia, ExportersIndia, Go4WorldBusiness, etc.)
- International platforms (Alibaba, 1688, GlobalSources, DHgate, Made-in-China, TradeKey)
- Niche supplier directories by category (textiles: Tirupur/Surat, electronics: Shenzhen/Dongguan, home goods: Moradabad, beauty: Gujarat/Mumbai)
- Manufacturer directories by industrial cluster/region
- Private label / contract manufacturing platforms
- Dropshipping supplier platforms
- Packaging/material suppliers

For each, provide the URL and search pattern if available.

Respond as a JSON array:
[
    {{"url": "https://...", "name": "...", "search_pattern": "https://...?q={{keyword}}", "description": "...", "reliability": 75, "discovery_reason": "why this supplier source is valuable"}}
]"""
        
        async def process_supplier(src, region, existing_urls):
            url = src.get("url", "").strip()
            if not url or len(url) < 10 or url in existing_urls:
                return None
            sid = record_discovered_source(
                url=url,
                source_type="supplier",
                source_name=src.get("name", ""),
                description=json.dumps({"search_pattern": src.get("search_pattern", ""), "desc": src.get("description", "")}),
                region=region,
                reliability_score=float(src.get("reliability", 65)),
                discovered_by="ai_scout"
            )
            if sid:
                existing_urls.add(url)
                return {"source_id": sid, "url": url, "name": src.get("name", ""), "discovery_reason": src.get("discovery_reason", ""), "rank_score": src.get("reliability", 65)}
            return None
        
        return await self._run_discovery_category("supplier", prompt, "supplier", region, process_supplier)
    
    async def discover_new_niches(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW micro-niche product categories - 150 target."""
        
        reg_cfg = REGIONAL_PROFILES.get(region, {})
        currency = reg_cfg.get("currency", "INR")
        aov_min = reg_cfg.get("target_aov_min", 500)
        aov_max = reg_cfg.get("target_aov_max", 3000)
        
        existing = get_dynamic_niches(region=region, limit=500)
        existing_cats = [n["category"].lower() for n in existing]
        existing_sample = ", ".join(existing_cats[:30])
        
        prompt = f"""You are an AI product research agent. Discover {self.TARGET_COUNTS['niche']} NEW emerging micro-niche consumer product categories for the {region} market.

Price range: {currency} {aov_min}-{aov_max}
Already known niches (DO NOT repeat these): {existing_sample}

Requirements:
- Each niche must be a SPECIFIC, search-ready product keyword (e.g., "Portable UV-C Sanitizer Wand" not just "sanitizer")
- Focus on PROBLEM-SOLVING products with 30+ day demand (NOT fads)
- Mix categories: Kitchen, Home, Beauty, Fitness, Electronics, Car, Pet, Office, Outdoor, Baby, Automotive, Travel, Sports
- Include both mainstream and underserved niches
- Each niche must have clear problem it solves
- Prioritize niches with high margin potential and low competition

For each niche, provide:
- category: exact search keyword
- problem_solved: what problem this product solves
- target_audience: who buys this
- estimated_price: price range in {currency}
- priority_score: 0-100 based on demand potential
- discovery_reason: why this niche is emerging now

Respond as JSON array:
[
    {{"category": "Portable UV-C Sanitizer Wand", "problem_solved": "sanitizes phone/gadgets without chemicals", "target_audience": "health-conscious parents, office workers", "estimated_price": "₹800-1500", "priority_score": 85, "discovery_reason": "post-pandemic hygiene awareness"}}
]"""
        
        async def process_niche(n, region, existing_cats_set):
            cat = n.get("category", "").strip()
            if not cat or cat.lower() in existing_cats_set:
                return None
            
            sid = record_dynamic_niche(
                category=cat,
                region=region,
                search_limit=3,
                priority_score=float(n.get("priority_score", 50)),
                discovered_by="ai_scout",
                source_signal=f"ai_discovery: {n.get('discovery_reason', '')}"
            )
            if sid:
                existing_cats_set.add(cat.lower())
                return {"niche_id": sid, "category": cat, "problem_solved": n.get("problem_solved", ""), "priority_score": n.get("priority_score", 50), "rank_score": n.get("priority_score", 50)}
            return None
        
        target = self.TARGET_COUNTS['niche']
        logger.info(f"AI Scout: Discovering {target} new niches for {region}")
        
        try:
            raw = await self._nim_query(prompt, LLMTaskType.DEEP_REASONING, 0.15, 5000)
            niches = self._extract_json_array(raw)
            
            if not niches:
                logger.warning("AI Scout: No niches returned from LLM")
                return []
            
            existing_cats_set = set(existing_cats)
            stored = []
            for n in niches:
                try:
                    result = await process_niche(n, region, existing_cats_set)
                    if result:
                        stored.append(result)
                except Exception as e:
                    logger.debug(f"Failed to process niche: {e}")
                    continue
            
            # Rank by priority score
            stored.sort(key=lambda x: x.get("rank_score", 0), reverse=True)
            
            logger.info(f"AI Scout: Discovered {len(stored)} new niches for {region} (target: {target})")
            return stored
            
        except Exception as e:
            logger.error(f"AI Scout: Niche discovery failed: {e}")
            return []
    
    async def discover_seed_keywords(self, region: str = "India") -> List[Dict]:
        """AI discovers NEW seed keywords by expanding existing ones - 200 target."""
        
        existing = get_seed_keywords(region=region, active_only=True, limit=500)
        existing_kws = [k["keyword"].lower() for k in existing]
        existing_sample = ", ".join(existing_kws[:50])
        
        prompt = f"""You are an AI keyword researcher. Find {self.TARGET_COUNTS['keyword']} NEW high-velocity seed keywords for product discovery in {region}.

Already known keywords: {existing_sample}

Find NEW keyword combinations that indicate BUYING INTENT or TREND DISCOVERY:
- "best [category] under [price]"
- "viral [category] 2026"
- "[category] problem solver"
- "must have [category]"
- "gift ideas [category]"
- "[category] for [specific use case]"
- "cheap [category] alternatives"
- "[category] review 2026"
- "top rated [category]"
- "[category] buying guide"

Include long-tail, question-based, and commercial intent keywords.

Respond as JSON array:
[
    {{"keyword": "best kitchen gadgets under 1000", "intent": "buying|trend|problem", "velocity_score": 85, "source": "ai_discovery"}}
]"""
        
        async def process_keyword(kw, region, existing_kws_set):
            keyword = kw.get("keyword", "").strip()
            if not keyword or keyword.lower() in existing_kws_set:
                return None
            
            sid = record_seed_keyword(
                keyword=keyword,
                region=region,
                source_platform="ai_scout",
                velocity_score=float(kw.get("velocity_score", 50))
            )
            if sid:
                existing_kws_set.add(keyword.lower())
                return {"seed_id": sid, "keyword": keyword, "intent": kw.get("intent", "trend"), "rank_score": kw.get("velocity_score", 50)}
            return None
        
        target = self.TARGET_COUNTS['keyword']
        logger.info(f"AI Scout: Discovering {target} new seed keywords for {region}")
        
        try:
            raw = await self._nim_query(prompt, LLMTaskType.DEEP_REASONING, 0.15, 5000)
            keywords = self._extract_json_array(raw)
            
            if not keywords:
                logger.warning("AI Scout: No keywords returned from LLM")
                return []
            
            existing_kws_set = set(existing_kws)
            stored = []
            for kw in keywords:
                try:
                    result = await process_keyword(kw, region, existing_kws_set)
                    if result:
                        stored.append(result)
                except Exception as e:
                    logger.debug(f"Failed to process keyword: {e}")
                    continue
            
            # Rank by velocity score
            stored.sort(key=lambda x: x.get("rank_score", 0), reverse=True)
            
            logger.info(f"AI Scout: Discovered {len(stored)} new seed keywords for {region} (target: {target})")
            return stored
            
        except Exception as e:
            logger.error(f"AI Scout: Keyword discovery failed: {e}")
            return []
    
    async def run_daily_scout(self, region: str = "India") -> ScoutResult:
        """Run complete daily AI Scout discovery (runs on first start of day)."""
        logger.info(f"=" * 60)
        logger.info(f"AI SCOUT: Starting DAILY discovery for {region} (10x volume)")
        logger.info(f"=" * 60)
        logger.info(f"Targets: Trend={self.TARGET_COUNTS['trend']}, Marketplace={self.TARGET_COUNTS['marketplace']}, "
                    f"Community={self.TARGET_COUNTS['community']}, Supplier={self.TARGET_COUNTS['supplier']}, "
                    f"Niche={self.TARGET_COUNTS['niche']}, Keyword={self.TARGET_COUNTS['keyword']}")
        
        result = ScoutResult()
        
        # Run each category SEQUENTIALLY with error handling
        # If one fails, continue to next
        
        logger.info("--- Phase 1: Trend Sources ---")
        try:
            result.trend_sources = await self.discover_trend_sources(region)
        except Exception as e:
            logger.error(f"Trend sources discovery failed: {e}")
            result.errors.append(f"trend: {e}")
        
        logger.info("--- Phase 2: Marketplace Sources ---")
        try:
            result.marketplace_sources = await self.discover_marketplace_sources(region)
        except Exception as e:
            logger.error(f"Marketplace sources discovery failed: {e}")
            result.errors.append(f"marketplace: {e}")
        
        logger.info("--- Phase 3: Community Sources ---")
        try:
            result.community_sources = await self.discover_communities(region)
        except Exception as e:
            logger.error(f"Community sources discovery failed: {e}")
            result.errors.append(f"community: {e}")
        
        logger.info("--- Phase 4: Supplier Sources ---")
        try:
            result.supplier_sources = await self.discover_supplier_sources(region)
        except Exception as e:
            logger.error(f"Supplier sources discovery failed: {e}")
            result.errors.append(f"supplier: {e}")
        
        logger.info("--- Phase 5: New Niches ---")
        try:
            result.niches = await self.discover_new_niches(region)
        except Exception as e:
            logger.error(f"Niche discovery failed: {e}")
            result.errors.append(f"niche: {e}")
        
        logger.info("--- Phase 6: Seed Keywords ---")
        try:
            result.keywords = await self.discover_seed_keywords(region)
        except Exception as e:
            logger.error(f"Keyword discovery failed: {e}")
            result.errors.append(f"keyword: {e}")
        
        # Calculate total new
        result.total_new = (
            len(result.trend_sources) +
            len(result.marketplace_sources) +
            len(result.community_sources) +
            len(result.supplier_sources) +
            len(result.niches) +
            len(result.keywords)
        )
        
        logger.info(f"=" * 60)
        logger.info(f"AI SCOUT DAILY COMPLETE for {region}: {result.total_new} new discoveries")
        logger.info(f"  Trend sources: {len(result.trend_sources)} (target: {self.TARGET_COUNTS['trend']})")
        logger.info(f"  Marketplace sources: {len(result.marketplace_sources)} (target: {self.TARGET_COUNTS['marketplace']})")
        logger.info(f"  Community sources: {len(result.community_sources)} (target: {self.TARGET_COUNTS['community']})")
        logger.info(f"  Supplier sources: {len(result.supplier_sources)} (target: {self.TARGET_COUNTS['supplier']})")
        logger.info(f"  Niches: {len(result.niches)} (target: {self.TARGET_COUNTS['niche']})")
        logger.info(f"  Keywords: {len(result.keywords)} (target: {self.TARGET_COUNTS['keyword']})")
        
        if result.errors:
            logger.warning(f"Errors encountered (continued anyway): {result.errors}")
        
        # Log top ranked sources per category
        for category, sources in [
            ("Trend", result.trend_sources),
            ("Marketplace", result.marketplace_sources),
            ("Community", result.community_sources),
            ("Supplier", result.supplier_sources),
            ("Niche", result.niches),
            ("Keyword", result.keywords)
        ]:
            if sources:
                top = sources[:3]
                for s in top:
                    name = s.get('name', s.get('category', s.get('keyword', s.get('url', 'N/A'))))[:40]
                    rank = s.get('rank_score', 0)
                    logger.info(f"  Top 3 {category}: {name} (rank: {rank:.1f})")
        
        return result


async def run_ai_scout(region: str = "India") -> Dict[str, Any]:
    """Async entry point for orchestrator - runs daily discovery."""
    scout = AIScoutAgent()
    result = await scout.run_daily_scout(region)
    return {
        "trend_sources": len(result.trend_sources),
        "marketplace_sources": len(result.marketplace_sources),
        "community_sources": len(result.community_sources),
        "supplier_sources": len(result.supplier_sources),
        "niches": len(result.niches),
        "keywords": len(result.keywords),
        "total_new": result.total_new,
        "errors": result.errors,
    }


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_ai_scout("India"))
    print(json.dumps(result, indent=2, default=str))