import re
import difflib
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field, field_validator


class RawProduct(BaseModel):
    marketplace: str = Field(pattern=r'^(amazon|flipkart|meesho)$')
    product_id: str = Field(min_length=3)
    title: str = Field(min_length=5, max_length=300)
    price: float = Field(gt=0)
    rating: float = Field(ge=1.0, le=5.0)
    review_count: int = Field(ge=0)
    bsr: Optional[int] = None
    url: str = Field(pattern=r'^https?://')
    image_url: Optional[str] = None

    @field_validator('title')
    @classmethod
    def title_not_placeholder(cls, v: str) -> str:
        """Block titles that are generic placeholders < 20 chars"""
        blocked = ["click here", "details", "product", "item", "placeholder", "test", "dummy", "generic"]
        v_lower = v.lower()
        if any(b in v_lower for b in blocked) and len(v) < 20:
            raise ValueError('Title appears to be placeholder text')
        return v

    @field_validator('price')
    @classmethod
    def price_realistic(cls, v: float) -> float:
        """Price between 10 and 500000"""
        if not (10 <= v <= 500000):
            raise ValueError('Price must be between 10 and 500000')
        return v


class CanonicalProduct(BaseModel):
    model_config = {"extra": "allow"}
    id: Optional[int] = None
    product_id: Optional[str] = None
    canonical_title: str
    category: Optional[str] = None
    region: Optional[str] = "India"
    retail_price_inr: float
    amazon_asin: Optional[str] = None
    flipkart_id: Optional[str] = None
    meesho_id: Optional[str] = None
    rating: float
    review_count: int
    amazon_bsr: Optional[int] = None
    factory_fob_inr: Optional[float] = None
    packaging_cost_inr: float = 15.0
    freight_per_unit_inr: float = 35.0
    mold_cost_inr: float = 0.0
    mold_amort_units: int = 5000
    current_gate: int = 1
    gate_status: str = 'PENDING'
    final_score: Optional[float] = None



class ProductMatcher:
    STOP_WORDS = {
        "for", "and", "with", "the", "in", "of", "to", "a", "an", "best", "new",
        "pack", "set", "combo", "premium", "pro", "plus", "portable", "2024", "2025", "2026"
    }

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def normalize_title(self, title: str) -> str:
        """Strips noise, punctuation, and promotional fluff to find the core noun phrase."""
        clean = re.sub(r"[^\w\s]", " ", title.lower())
        tokens = [t for t in clean.split() if t not in self.STOP_WORDS and len(t) > 2]
        return " ".join(tokens[:8])

    def similarity(self, title1: str, title2: str) -> float:
        """Using SequenceMatcher to calculate similarity"""
        return difflib.SequenceMatcher(None, title1, title2).ratio()

    def find_canonical(self, products: List[RawProduct]) -> List[CanonicalProduct]:
        """Cluster and merge raw products into canonical products"""
        clusters: List[List[RawProduct]] = []
        for p in products:
            norm_p = self.normalize_title(p.title)
            found = False
            for cluster in clusters:
                norm_c = self.normalize_title(cluster[0].title)
                if self.similarity(norm_p, norm_c) >= self.threshold:
                    cluster.append(p)
                    found = True
                    break
            if not found:
                clusters.append([p])

        canonicals = []
        for cluster in clusters:
            canonical_title = cluster[0].title
            retail_price_inr = sum(p.price for p in cluster) / len(cluster)
            rating = sum(p.rating for p in cluster) / len(cluster)
            review_count = sum(p.review_count for p in cluster)

            amazon_asin = next((p.product_id for p in cluster if p.marketplace == 'amazon'), None)
            flipkart_id = next((p.product_id for p in cluster if p.marketplace == 'flipkart'), None)
            meesho_id = next((p.product_id for p in cluster if p.marketplace == 'meesho'), None)
            amazon_bsr = next((p.bsr for p in cluster if p.marketplace == 'amazon' and p.bsr is not None), None)

            canonicals.append(CanonicalProduct(
                canonical_title=canonical_title,
                retail_price_inr=retail_price_inr,
                rating=round(rating, 1),
                review_count=review_count,
                amazon_asin=amazon_asin,
                flipkart_id=flipkart_id,
                meesho_id=meesho_id,
                amazon_bsr=amazon_bsr
            ))

        return canonicals

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
        # Use class-level STOP_WORDS for normalization
        matcher = cls()
        norm_canon = set(matcher.normalize_title(canonical_title).split())
        norm_target = set(matcher.normalize_title(target_listing_title).split())

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


class ValidationPipeline:
    def validate_batch(self, raw_products: List[dict]) -> tuple[List[RawProduct], List[dict]]:
        """Returns (valid, errors)"""
        valid = []
        errors = []
        for p_dict in raw_products:
            try:
                valid.append(RawProduct(**p_dict))
            except Exception as e:
                errors.append({"data": p_dict, "error": str(e)})
        return valid, errors

    def deduplicate(self, products: List[RawProduct]) -> List[CanonicalProduct]:
        """Runs ProductMatcher"""
        matcher = ProductMatcher()
        return matcher.find_canonical(products)


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