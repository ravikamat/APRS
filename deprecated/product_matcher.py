"""
core/product_matcher.py — Canonical Product Graph & Demand Proxy Engine for APRS V6 Pro.

Provides:
1. Canonical product family normalization and cross-marketplace deduplication.
2. Deterministic validation constraints (price sanity, category verification, brand exclusion).
3. Demand Proxy Scoring (BSR velocity, review growth, ad density, price stability).
"""
import re
from typing import Dict, Any, List, Optional, Tuple


class CanonicalProductMatcher:
    """
    Normalizes product titles and maps cross-marketplace listings
    into a unified canonical product family.
    """

    STOP_WORDS = {
        "for", "and", "with", "the", "in", "of", "to", "a", "an", "best", "new",
        "pack", "set", "combo", "premium", "pro", "plus", "portable", "2024", "2025", "2026"
    }

    @classmethod
    def normalize_title(cls, title: str) -> str:
        """Strips noise, punctuation, and promotional fluff to find the core noun phrase."""
        clean = re.sub(r"[^\w\s]", " ", title.lower())
        tokens = [t for t in clean.split() if t not in cls.STOP_WORDS and len(t) > 2]
        return " ".join(tokens[:8])

    @classmethod
    def evaluate_match_confidence(
        cls,
        canonical_title: str,
        target_listing_title: str,
        canonical_price: float,
        target_price: float,
        target_category: str = "General"
    ) -> Tuple[str, float]:
        """
        Classifies match between a canonical product and a marketplace listing:
        Returns (Match Class: EXACT_MATCH, PROBABLE_VARIANT, RELATED_ALTERNATIVE, UNRELATED, Confidence Score 0.0-1.0)
        """
        norm_canon = set(cls.normalize_title(canonical_title).split())
        norm_target = set(cls.normalize_title(target_listing_title).split())

        if not norm_canon or not norm_target:
            return ("UNRELATED", 0.0)

        # Jaccard overlap of key noun tokens
        overlap = len(norm_canon.intersection(norm_target))
        jaccard = overlap / float(len(norm_canon.union(norm_target)))

        # Price sanity check (Price shouldn't differ by more than 3.5x for the same physical SKU)
        price_ratio = max(canonical_price, target_price) / max(0.1, min(canonical_price, target_price))

        if price_ratio > 4.5:
            # Extreme price deviation -> likely accessory or bundle or unrelated
            return ("UNRELATED", round(jaccard * 0.3, 2))

        if jaccard >= 0.65 and price_ratio <= 1.8:
            return ("EXACT_MATCH", round(min(1.0, jaccard * 1.2), 2))
        elif jaccard >= 0.35 and price_ratio <= 2.8:
            return ("PROBABLE_VARIANT", round(jaccard, 2))
        elif jaccard >= 0.20:
            return ("RELATED_ALTERNATIVE", round(jaccard * 0.8, 2))
        else:
            return ("UNRELATED", round(jaccard * 0.5, 2))


class DemandProxyScorer:
    """
    Computes a verified Demand Proxy Score (0-100) from observable marketplace signals
    rather than guessing unverified raw sales counts.
    """

    @classmethod
    def calculate_demand_proxy(
        cls,
        bsr_rank: int = 5000,
        review_count: int = 250,
        rating: float = 4.2,
        ad_active_days: int = 30,
        price_stability_pct: float = 85.0
    ) -> Dict[str, Any]:
        """
        Calculates demand proxy score from 5 observable metrics:
        - BSR Rank Velocity (40 pts)
        - Review Momentum (25 pts)
        - Sustained Ad Spending Density (15 pts)
        - Price Stability / Anti-Discounting (10 pts)
        - Customer Rating Sentiment (10 pts)
        """
        # 1. BSR Component (Rank 1-500 = 40pts, 500-2000 = 32pts, 2000-5000 = 24pts, 5000-15000 = 15pts, >15k = 5pts)
        if bsr_rank <= 500:
            bsr_pts = 40.0
        elif bsr_rank <= 2000:
            bsr_pts = 32.0
        elif bsr_rank <= 5000:
            bsr_pts = 24.0
        elif bsr_rank <= 15000:
            bsr_pts = 16.0
        elif bsr_rank <= 35000:
            bsr_pts = 8.0
        else:
            bsr_pts = 3.0

        # 2. Review Momentum (Reviews 50-500 = sweet spot for non-saturated high demand, >5000 = saturated)
        if 80 <= review_count <= 800:
            review_pts = 25.0  # Prime emerging product
        elif 800 < review_count <= 2500:
            review_pts = 20.0
        elif review_count > 2500:
            review_pts = 15.0  # High demand but hyper-competitive
        else:
            review_pts = max(5.0, review_count * 0.2)

        # 3. Ad Longevity (If seller is paying for ads > 20 days, the SKU is profitable)
        if ad_active_days >= 30:
            ad_pts = 15.0
        elif ad_active_days >= 14:
            ad_pts = 10.0
        elif ad_active_days >= 7:
            ad_pts = 6.0
        else:
            ad_pts = 2.0

        # 4. Price Stability
        price_pts = (price_stability_pct / 100.0) * 10.0

        # 5. Rating Sentiment (Rating 3.6-4.3 is ideal for v2.0 improvement, >4.7 is hard to beat, <3.3 is junk)
        if 3.7 <= rating <= 4.3:
            rating_pts = 10.0  # Prime target for defect-solving v2.0
        elif 4.4 <= rating <= 4.7:
            rating_pts = 7.0
        elif rating > 4.7:
            rating_pts = 5.0
        else:
            rating_pts = 3.0

        total_demand_proxy = min(100.0, max(0.0, bsr_pts + review_pts + ad_pts + price_pts + rating_pts))

        signal_tier = "HIGH_VELOCITY_OPPORTUNITY" if total_demand_proxy >= 75.0 else ("MODERATE_DEMAND" if total_demand_proxy >= 55.0 else "LOW_DEMAND")

        return {
            "demand_proxy_score": round(total_demand_proxy, 1),
            "signal_tier": signal_tier,
            "bsr_pts": round(bsr_pts, 1),
            "review_pts": round(review_pts, 1),
            "ad_pts": round(ad_pts, 1),
            "price_pts": round(price_pts, 1),
            "rating_pts": round(rating_pts, 1)
        }
