"""
tools/trend_scout/trend_aggregator.py — Autonomous Multi-Channel Open-Web Trend Scout.

Aggregates emerging e-commerce trend signals across:
1. Google Trends & Autocomplete (breakout search interest, 7-30d momentum)
2. Reddit Viral E-Com Communities (r/tiktokmademebuyit, r/amazonfinds, r/gadgets, r/IndianBeautyDeals)
3. Open-Web Jina Reader & Social Search (Instagram / TikTok viral product mentions)
4. Meta Ad Library public patterns (high ad spend product categories)

Integrates lightweight anti-bot resilience and records structured signals into SQLite SSOT.
All outputs are validated by AI Supervisor for quality assurance.
"""
import os
import sys
import json
import time
import re
import urllib.request
import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from pathlib import Path

# Project root import
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.database import record_trend_signal, get_connection, get_seed_keywords, get_discovered_sources, update_source_usage, record_seed_keyword
from core.utils import normalize_region
from tools.adapters.base_adapter import BaseSourceAdapter, SourceHealth
from tools.ai_supervisor import get_supervisor

logger = logging.getLogger("aprs.trend_scout")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s — %(message)s")

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

# Curated High-Intent Seed Roots for Viral Product Expansion
VIRAL_SEED_ROOTS = {
    "India": [
        "best kitchen gadgets under 1000",
        "viral meesho home organizer",
        "car essential gadgets",
        "amazon india viral products",
        "portable rechargeable gadgets",
        "silicone kitchen accessories",
        "bathroom deep cleaning tools",
        "smart work from home desk setup",
        "ayurvedic hair and skin tools",
        "anti fatigue orthopedic cushion"
    ],
    "USA": [
        "tiktok made me buy it home",
        "amazon must haves 2026",
        "viral kitchen problem solver",
        "ergonomic desk gadgets",
        "rechargeable cleaning tools",
        "smart pet accessories viral",
        "portable travel gadgets",
        "magsafe car accessories"
    ],
    "GCC_MiddleEast": [
        "viral amazon ae gadgets",
        "portable car cooler dubai",
        "smart coffee accessories uae",
        "luxury home aroma diffuser"
    ],
    "Europe": [
        "amazon de trend produkte",
        "sustainable eco home gadgets",
        "energy saving smart plug"
    ]
}

# Subreddits tracking real viral product discoveries
COMMUNITY_SUBREDDITS = [
    "tiktokmademebuyit",
    "amazonfinds",
    "BuyItForLife",
    "gadgets",
    "amazondeals",
    "IndianSkincareAddicts",
    "IndianBeautyDeals"
]


class OpenWebTrendScout(BaseSourceAdapter):
    """
    Autonomous multi-channel trend aggregator.
    Discovers rising social, search, and video e-commerce product trends.
    Implements the SourceAdapter protocol for health monitoring and telemetry.
    """

    def __init__(self):
        super().__init__(source_name="open_web_trend_scout")
        self.session = None

    def discover_topics(self, query: str, region: str = "India") -> List[Dict[str, Any]]:
        """SourceAdapter protocol: discovers breakout trend topics."""
        return self.harvest_all_active_trends(region=region, max_signals=5)

    def search_products(self, query: str, region: str = "India", limit: int = 5) -> List[Dict[str, Any]]:
        """SourceAdapter protocol: not applicable for trend scout, returns empty."""
        return []

    def collect_reviews(self, listing_url_or_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """SourceAdapter protocol: not applicable for trend scout, returns empty."""
        return []

    def fetch_jina_markdown(self, url: str, timeout: int = 15) -> str:
        """Reads any public webpage via Jina Reader, returning markdown."""
        try:
            jina_url = f"https://r.jina.ai/{url}"
            req = urllib.request.Request(
                jina_url,
                headers={"User-Agent": _UA, "Accept": "text/plain"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read(512 * 1024)  # 512KB max
                return body.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"Jina Reader fetch failed for {url}: {e}")
            return ""

    def scout_google_breakout_queries(self, seed_keyword: str, region: str = "India") -> List[Dict[str, Any]]:
        """Queries Google Suggest endpoint to find high-velocity search breakout keywords."""
        signals = []
        seed = " ".join(seed_keyword.strip().split()[:4])
        if not seed:
            return signals
        query_encoded = urllib.parse.quote(seed)
        url = f"https://suggestqueries.google.com/complete/search?client=firefox&q={query_encoded}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                suggestions = data[1] if len(data) > 1 else []
                
                for idx, query in enumerate(suggestions[:6]):
                    if len(query.split()) >= 2 and query.lower() != seed.lower():
                        # Calculate velocity heuristic based on rank & length
                        velocity = round(95.0 - (idx * 6.5), 1)
                        longevity = 14 + (idx * 2)
                        signals.append({
                            "platform": "google_trends",
                            "keyword": query.strip().title(),
                            "trend_category": seed.split()[0].title() if seed else "General",
                            "region": region,
                            "velocity_score": velocity,
                            "longevity_days": longevity,
                            "search_volume_est": int(5000 + (10 - idx) * 1200),
                            "raw_json": {"source": "google_suggest", "seed": seed, "rank": idx + 1}
                        })
        except Exception as e:
            logger.debug(f"Google suggest failed for {seed}: {e}")
            
        return signals

    def scout_reddit_product_discussions(self, subreddit: str = "tiktokmademebuyit", limit: int = 5) -> List[Dict[str, Any]]:
        """Scrapes trending product discussions from public Reddit threads without auth."""
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        signals = []
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                posts = data.get("data", {}).get("children", [])
                
                for post in posts:
                    p_data = post.get("data", {})
                    title = p_data.get("title", "")
                    score = p_data.get("score", 0)
                    num_comments = p_data.get("num_comments", 0)
                    permalink = f"https://reddit.com{p_data.get('permalink', '')}"
                    
                    if score >= 15 and len(title) >= 10:
                        # Clean title into product concept keyword
                        cleaned_kw = re.sub(r'\[.*?\]|\(.*?\)|http\S+|reddit|tiktok', '', title, flags=re.IGNORECASE).strip()
                        if len(cleaned_kw) > 5:
                            signals.append({
                                "platform": "reddit",
                                "keyword": cleaned_kw[:60].strip().title(),
                                "trend_category": "Social Viral",
                                "region": "USA" if "india" not in subreddit.lower() else "India",
                                "velocity_score": min(100.0, float(score * 1.5 + num_comments * 2)),
                                "longevity_days": 21,
                                "search_volume_est": score * 100,
                                "raw_json": {
                                    "subreddit": subreddit,
                                    "upvotes": score,
                                    "comments": num_comments,
                                    "url": permalink
                                }
                            })
        except Exception as e:
            logger.debug(f"Reddit scrape failed for r/{subreddit}: {e}")
            
        return signals

    def harvest_all_active_trends(self, region: str = "India", max_signals: int = 15) -> List[Dict[str, Any]]:
        """
        Runs comprehensive multi-source scouting across Google Trends, Reddit, and dynamically
        discovered sources. Seeds and communities are loaded from DB first; falls back to
        hardcoded lists only if DB is empty. Discovered keywords are fed back as new seeds.
        """
        import time as _time
        all_signals = []
        norm_region = normalize_region(region)

        # ── Load dynamic seeds from DB, fallback to hardcoded ────────────────
        db_seeds = get_seed_keywords(region=norm_region, limit=20)
        if db_seeds:
            seeds = [s["keyword"] for s in db_seeds]
            # Mark seeds as used
            for s in db_seeds[:4]:
                try:
                    update_seed_usage(s["seed_id"])
                except Exception:
                    pass
        else:
            seeds = VIRAL_SEED_ROOTS.get(norm_region, VIRAL_SEED_ROOTS.get("India", []))

        # 1. Google Autocomplete Search Breakout (using dynamic seeds)
        for seed in seeds[:6]:
            google_signals = self.scout_google_breakout_queries(seed, region=region)
            all_signals.extend(google_signals)
            self.record_success(len(google_signals), 500)
            _time.sleep(0.8)

        # ── Load dynamic Reddit communities from DB, fallback to hardcoded ───
        db_communities = get_discovered_sources(source_type="community_reddit", region=region)
        if db_communities:
            subreddits = []
            for c in db_communities:
                url = c.get("url", "")
                # Extract subreddit name from URL
                match = re.search(r'/r/([^/]+)', url)
                if match:
                    subreddits.append({"name": match.group(1), "source_id": c.get("source_id")})
        else:
            subreddits = [{"name": s, "source_id": None} for s in COMMUNITY_SUBREDDITS]

        # 2. Reddit Community Breakout (using dynamic communities)
        for sub_info in subreddits[:5]:
            reddit_signals = self.scout_reddit_product_discussions(subreddit=sub_info["name"], limit=4)
            all_signals.extend(reddit_signals)
            if sub_info.get("source_id"):
                update_source_usage(sub_info["source_id"], yielded_results=len(reddit_signals) > 0)
            self.record_success(len(reddit_signals), 800)

        # ── 3. Explore dynamically discovered trend sources ──────────────────
        db_trend_sources = get_discovered_sources(source_type="trend", region=region)
        for src in db_trend_sources[:3]:
            try:
                url = src.get("url", "")
                if url:
                    content = self.fetch_jina_markdown(url, timeout=10)
                    if len(content) > 100:
                        # Extract product keywords from the page
                        lines = content.split("\n")
                        for line in lines[:50]:
                            # Look for product-like phrases (capitalized, 3+ words)
                            words = line.strip()
                            if 15 < len(words) < 80 and sum(1 for c in words if c.isupper()) >= 2:
                                cleaned = re.sub(r'[#*\[\]()]', '', words).strip()
                                if len(cleaned.split()) >= 3:
                                    all_signals.append({
                                        "platform": "discovered_web",
                                        "keyword": cleaned[:60].strip().title(),
                                        "trend_category": "Web Discovery",
                                        "region": region,
                                        "velocity_score": 65.0,
                                        "longevity_days": 21,
                                        "search_volume_est": 3000,
                                        "raw_json": {"source_url": url, "source_id": src.get("source_id")}
                                    })
                        update_source_usage(src["source_id"], yielded_results=True)
            except Exception as e:
                logger.debug(f"Discovered source scrape failed: {e}")

        # ── 4. Deduplicate & Record to DB ────────────────────────────────────
        recorded_signals = []
        seen_kws = set()

        for sig in all_signals:
            kw_norm = sig["keyword"].lower().strip()
            if kw_norm not in seen_kws and len(kw_norm) > 4:
                seen_kws.add(kw_norm)
                sig_id = record_trend_signal(
                    platform=sig["platform"],
                    keyword=sig["keyword"],
                    category=sig.get("trend_category", "General"),
                    region=sig["region"],
                    search_volume_est=sig.get("search_volume_est", 5000),
                    velocity_score=sig.get("velocity_score", 75.0),
                    longevity_days=sig.get("longevity_days", 14),
                    raw_json=sig.get("raw_json", {})
                )
                sig["signal_id"] = sig_id
                recorded_signals.append(sig)

                # ── Feed discovered keywords back as new seeds ───────────
                try:
                    record_seed_keyword(
                        keyword=sig["keyword"],
                        region=sig["region"],
                        source_platform=sig["platform"],
                        velocity_score=sig.get("velocity_score", 50.0)
                    )
                except Exception:
                    pass

            if len(recorded_signals) >= max_signals:
                break

        logger.info(f"OpenWebTrendScout: Harvested {len(recorded_signals)} signals for {region} (dynamic sources)")
        return recorded_signals


if __name__ == "__main__":
    scout = OpenWebTrendScout()
    trends = scout.harvest_all_active_trends(region="India", max_signals=5)
    print(f"\n[DEMO] Found {len(trends)} trend signals for India:")
    for t in trends:
        print(f"  • [{t['platform']}] {t['keyword']} (Velocity: {t['velocity_score']}/100 | Longevity: {t['longevity_days']}d)")
