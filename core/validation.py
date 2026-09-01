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
    id: Optional[int] = None
    canonical_title: str
    category: Optional[str] = None
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
            best = min(cluster, key=lambda p: p.price)
            canonical_title = cluster[0].title
            retail_price_inr = best.price
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
