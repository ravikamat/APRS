"""
tools/niche_expander.py — Dynamic Niche Expander for APRS V7.

Expands the niche universe based on trend signals, gate outcomes,
and market feedback. Implements the "niche flywheel" concept.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

import sys

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from core.database import (
    get_connection, get_dynamic_niches, get_dynamic_niches,
    record_dynamic_niche, get_seed_keywords, record_seed_keyword,
    get_active_trend_signals, update_niche_scan,
)
from tools.trend_scout.trend_aggregator import OpenWebTrendScout

logger = logging.getLogger("aprs.niche_expander")


@dataclass
class NicheExpansionResult:
    """Result of niche expansion operation."""
    niches_evaluated: int = 0
    niches_added: int = 0
    niches_updated: int = 0
    niches_deactivated: int = 0
    keywords_generated: int = 0
    signals_processed: int = 0


class NicheExpander:
    """
    Dynamic Niche Expander — manages the niche universe.

    Responsibilities:
    1. Consume trend signals → propose new niches
    2. Evaluate existing niche performance → adjust priorities
    3. Generate seed keywords from successful niches
    4. Deactivate dead niches
    4. Feed back into Discovery Engine
    """

    def __init__(self):
        self.trend_scout = OpenWebTrendScout()

    async def expand_from_signals(self, lookback_days: int = 7) -> NicheExpansionResult:
        """
        Main entry point: expand niche universe based on recent trend signals.
        """
        logger.info("Starting niche expansion from trend signals")
        start_time = datetime.utcnow()

        result = NicheExpansionResult()

        # 1. Fetch recent trend signals
        signals = get_active_trend_signals(limit=100)
        result.signals_processed = len(signals)

        # 2. Cluster signals into candidate niches
        candidate_niches = self._cluster_signals_into_niches(signals)

        # 3. Evaluate and persist new niches
        for niche in candidate_niches:
            if self._should_create_niche(niche):
                niche_id = record_dynamic_niche(
                    category=niche["category"],
                    region=niche.get("region", "India"),
                    search_limit=niche.get("search_limit", 3),
                    priority_score=niche.get("priority_score", 50),
                    discovered_by="signal_clustering",
                    source_signal=niche.get("source_signal", ""),
                )
                if niche_id:
                    logger.info(f"Added new niche: {niche['category']}")
                    result.niches_added += 1

        # 4. Update existing niche priorities based on scan history
        updated = await self._update_niche_priorities()
        result.niches_updated = niches_updated

        # 5. Deactivate dead niches (0 products found in last 3 scans)
        deactivated = await self._deactivate_dead_niches()
        result.niches_deactivated = deactivated

        # 6. Generate seed keywords from successful niches
        keywords_generated = await self._generate_seed_keywords()
        result.keywords_generated = keywords_generated

        result.niches_evaluated = len(get_dynamic_niches(active_only=True))

        duration = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Niche expansion complete in {duration:.1f}s: {result}")
        return result

    def _cluster_signals_into_niches(self, signals: List[Dict]) -> List[Dict]:
        """
        Cluster trend signals into candidate niche categories.
        Uses keyword similarity and category grouping.
        """
        # Group signals by category
        by_category = defaultdict(list)
        for sig in signals:
            cat = sig.get("category", "General")
            by_category[cat].append(sig)

        candidates = []
        for category, signals_in_cat in by_category.items():
            if len(signals_in_cat) < 2:
                continue  # Need at least 2 signals to form a niche

            # Calculate aggregate velocity
            avg_velocity = sum(s.get("velocity_score", 0) for s in signals_in_cat) / len(signals_in_cat)
            max_velocity = max(s.get("velocity_score", 0) for s in signals_in_cat)

            # Generate niche name from top signals
            top_signals = sorted(signals_in_cat, key=lambda s: s.get("velocity_score", 0), reverse=True)[:3]
            keywords = [s["keyword"] for s in top_signals]
            
            # Create a descriptive niche name
            niche_name = self._generate_niche_name(category, keywords)
            
            # Calculate priority score based on velocity and signal count
            priority = min(100, 50 + (avg_velocity * 0.5) + (len(signals_in_cat) * 2))

            candidates.append({
                "category": niche_name,
                "region": "India",
                "priority_score": min(100, priority),
                "search_limit": 3,
                "source_signal": ", ".join(keywords[:3]),
                "discovered_by": "signal_clustering",
                "velocity": avg_velocity,
                "signal_count": len(signals_in_cat),
            })

        return candidates

    def _generate_niche_name(self, category: str, keywords: List[str]) -> str:
        """Generate a descriptive niche name from category and keywords."""
        # Extract key terms from keywords
        all_words = []
        for kw in keywords:
            words = kw.lower().split()
            # Filter out common words
            filtered = [w for w in words if len(w) > 3 and w not in {"best", "viral", "top", "new", "buy", "for", "the", "and", "with", "under", "over"}]
            all_words.extend(filtered)

        # Count word frequency
        from collections import Counter
        word_counts = Counter(all_words)
        top_words = [w for w, _ in word_counts.most_common(3)]

        if top_words:
            return f"{category}: {' '.join(top_words).title()}"
        else:
            return category

    def _should_create_niche(self, niche: Dict) -> bool:
        """Determine if a candidate niche should be created."""
        # Check if niche already exists
        existing = get_dynamic_niches(region=niche.get("region", "India"))
        for existing_niche in existing:
            if existing_niche["category"].lower() == niche["category"].lower():
                return False  # Already exists
        return True

    async def _update_niche_priorities(self) -> int:
        """Update niche priority scores based on scan history."""
        logger.info("Updating niche priorities based on scan history...")
        
        niches = get_dynamic_niches(active_only=True, limit=500)
        updated = 0

        conn = get_connection()
        cur = conn.cursor()

        for niche in niches:
            niche_id = niche.get("niche_id")
            if not niche_id:
                continue

            scans = niche.get("times_scanned", 0)
            found = niche.get("products_found", 0)
            priority = niche.get("priority_score", 50)

            if scans == 0:
                continue

            yield_rate = found / scans

            # Update priority based on yield
            if yield_rate > 0.5:
                new_priority = min(100, priority + 10)
            elif yield_rate > 0.2:
                new_priority = priority
            elif yield_rate > 0:
                new_priority = max(10, priority - 10)
            else:
                new_priority = max(5, priority - 20)

            if abs(new_priority - priority) >= 5:
                try:
                    cur.execute("""
                        UPDATE dynamic_niches 
                        SET priority_score = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE niche_id = ?
                    """, (new_priority, niche_id))
                    conn.commit()
                    updated += 1
                    logger.debug(f"Updated niche priority: {new_priority}")
                except Exception as e:
                    logger.warning(f"Failed to update niche {niche_id}: {e}")

        conn.close()
        logger.info(f"Updated {updated} niche priorities")
        return updated

    async def _deactivate_dead_niches(self) -> int:
        """Deactivate niches with 0 products found in last 3 scans."""
        from core.database import get_dynamic_niches

        niches = get_dynamic_niches(active_only=True, limit=500)
        deactivated = 0

        conn = get_connection()
        cur = conn.cursor()

        for niche in niches:
            scans = niche.get("times_scanned", 0)
            found = niche.get("products_found", 0)
            niche_id = niche.get("niche_id")

            if scans >= 3 and found == 0:
                try:
                    cur.execute("""
                        UPDATE dynamic_niches 
                        SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                        WHERE niche_id = ?
                    """, (niche_id,))
                    conn.commit()
                    deactivated += 1
                    logger.info(f"Deactivated dead niche: {niche.get('category')}")
                except Exception as e:
                    logger.warning(f"Failed to deactivate niche: {e}")

        conn.close()
        return deactivated

    async def _generate_seed_keywords(self) -> int:
        """Generate seed keywords from successful niches and products."""
        from core.database import get_dynamic_niches, get_all_products

        logger.info("Generating seed keywords from successful niches...")

        niches = get_dynamic_niches(active_only=True, limit=50)
        products = get_all_products(include_deleted=False)

        # Extract keywords from high-performing niches
        keyword_candidates = set()

        # From niches with good yield
        for niche in niches:
            if niche.get("products_found", 0) > 5:
                words = niche["category"].lower().split()
                for word in words:
                    if len(word) > 3 and word not in {"best", "viral", "top", "new", "buy"}:
                        keyword_candidates.add(word)

        # From high-scoring products
        for product in products:
            if product.get("overall_score", 0) >= 75:
                words = product["name"].lower().split()
                for word in words:
                    if len(word) > 3 and word not in {"best", "viral", "top", "new", "buy", "for", "the", "and", "with", "under", "over"}:
                        keyword_candidates.add(word)

        # Add as seed keywords
        generated = 0
        for kw in keyword_candidates:
            if len(kw) > 3:
                try:
                    record_seed_keyword(
                        keyword=kw,
                        region="India",
                        source_platform="learning_engine",
                        velocity_score=50.0,
                    )
                    generated += 1
                except Exception:
                    pass

        logger.info(f"Generated {generated} new seed keywords")
        return len(keyword_candidates)


async def run_niche_expansion() -> Dict[str, Any]:
    """Run niche expansion cycle."""
    expander = NicheExpander()
    result = await expander.expand_from_signals()
    return {
        "niches_evaluated": result.niches_evaluated,
        "niches_added": result.niches_added,
        "niches_updated": result.niches_updated,
        "niches_deactivated": result.niches_deactivated,
        "keywords_generated": result.keywords_generated,
        "signals_processed": result.signals_processed,
    }


if __name__ == "__main__":
    async def test():
        result = await run_niche_expansion()
        print(f"Niche expansion result: {result}")

    asyncio.run(test())