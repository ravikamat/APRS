"""
tools/competition_xray.py — Competition X-Ray.

Per candidate product: deep competitive analysis.
- Listing count in category
- Brand concentration (Amazon Basics present? flee)
- Price-band crowding
- First-page ad density
- Review moat analysis
"""
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from collections import Counter

from core.database import get_connection
from tools.web_agent import WebAgent

logger = logging.getLogger("aprs.competition_xray")


@dataclass
class CompetitionSignal:
    """Competitive analysis for a product/category."""
    product_id: str
    category: str
    region: str
    total_listings: int
    unique_brands: int
    brand_concentration_hhi: float  # Herfindahl-Hirschman Index
    amazon_basics_present: bool
    top_brand_share_pct: float
    price_bands: Dict[str, int]  # band -> count
    price_band_crowding: float  # 0-100
    ad_density_first_page: float  # 0-100
    avg_review_count_top10: float
    review_moat_score: float  # 0-100, high = hard to enter
    competitor_asins: List[str]
    competition_score: float  # 0-100 composite (lower = better opportunity)
    computed_at: str


class CompetitionXRay:
    """
    Competition X-Ray — deep competitive analysis per candidate.
    
    Uses WebAgent to scrape category search results and analyze:
    1. Brand landscape (concentration, Amazon Basics)
    2. Price distribution and crowding
    3. Ad density on first page
    4. Review moats (barriers to entry)
    """
    
    def __init__(self):
        self.web_agent = WebAgent()
    
    def _get_connection(self):
        from core.database import get_connection
        return get_connection()
    
    def _parse_price_band(self, price: float) -> str:
        """Categorize price into bands."""
        if price < 300:
            return "under_300"
        elif price < 500:
            return "300_500"
        elif price < 1000:
            return "500_1000"
        elif price < 2000:
            return "1000_2000"
        elif price < 5000:
            return "2000_5000"
        else:
            return "5000_plus"
    
    def compute_hhi(self, brand_shares: List[float]) -> float:
        """Compute Herfindahl-Hirschman Index for brand concentration."""
        # HHI = sum of (market_share_pct)^2
        # 0-10000 scale, but we normalize to 0-100
        hhi = sum(s ** 2 for s in brand_shares)
        return round(min(100, hhi / 100), 1)  # Normalize
    
    def compute_price_crowding(self, price_bands: Dict[str, int]) -> float:
        """Compute price band crowding score (0-100)."""
        if not price_bands:
            return 0.0
        
        total = sum(price_bands.values())
        if total == 0:
            return 0.0
        
        # Find the most crowded band
        max_band_count = max(price_bands.values())
        crowding = (max_band_count / total) * 100
        
        # Also factor in number of bands occupied
        bands_occupied = len([b for b, c in price_bands.items() if c > 0])
        band_penalty = bands_occupied * 5  # More bands = more competition
        
        return round(min(100, crowding + band_penalty), 1)
    
    async def analyze_category(self, category: str, region: str = "India", max_results: int = 50) -> CompetitionSignal:
        """Analyze competition for a category by scraping search results."""
        logger.info(f"Running Competition X-Ray for category: {category}")
        
        # Search for category on Amazon
        query = category.replace(" ", "+")
        url = f"https://www.amazon.in/s?k={query}"
        
        prompt = f"""Search for "{category}" on Amazon India.
Extract up to {max_results} product listings from the first 3 pages.
For each listing, extract:
- asin (from data-asin attribute)
- title
- price (numeric, in INR)
- brand (from brand field or title)
- rating
- review_count
- is_sponsored (boolean - has "Sponsored" badge)
- bsr (if visible on listing)

Return as JSON array of objects."""
        
        try:
            result = await self.web_agent.extract_from_url(
                url=url,
                schema={"products": "array"},
                task_description=prompt
            )
            products = result.get("products", [])
            
            if not products:
                logger.warning(f"No products found for category: {category}")
                return self._empty_signal(category, region)
            
            return self._analyze_products(category, region, products)
            
        except Exception as e:
            logger.error(f"Competition X-Ray failed for {category}: {e}")
            return self._empty_signal(category, region)
    
    def _analyze_products(self, category: str, region: str, products: List[Dict]) -> CompetitionSignal:
        """Analyze scraped product data for competitive signals."""
        total = len(products)
        
        # Brand analysis
        brands = []
        amazon_basics = False
        for p in products:
            brand = p.get("brand", "").strip().lower()
            if not brand and "amazon basics" in p.get("title", "").lower():
                brand = "amazon basics"
                amazon_basics = True
            elif "amazon basics" in brand:
                amazon_basics = True
            if brand:
                brands.append(brand)
        
        brand_counter = Counter(brands)
        unique_brands = len(brand_counter)
        top_brand, top_count = brand_counter.most_common(1)[0] if brand_counter else ("unknown", 0)
        top_brand_share = (top_count / total * 100) if total > 0 else 0
        
        # Brand shares for HHI
        brand_shares = [count / total * 100 for count in brand_counter.values()]
        hhi = self.compute_hhi(brand_shares)
        
        # Price band analysis
        price_bands = {}
        for p in products:
            price = p.get("price")
            if price and isinstance(price, (int, float)) and price > 0:
                band = self._parse_price_band(price)
                price_bands[band] = price_bands.get(band, 0) + 1
        
        price_crowding = self.compute_price_crowding(price_bands)
        
        # Ad density
        sponsored_count = sum(1 for p in products if p.get("is_sponsored", False))
        ad_density = (sponsored_count / total * 100) if total > 0 else 0
        
        # Review moat
        review_counts = [p.get("review_count", 0) for p in products if p.get("review_count")]
        review_counts = [r for r in review_counts if isinstance(r, (int, float)) and r > 0]
        
        if review_counts:
            top10 = sorted(review_counts, reverse=True)[:10]
            avg_review_top10 = sum(top10) / len(top10)
            median_review = sorted(review_counts)[len(review_counts) // 2]
        else:
            avg_review_top10 = 0
            median_review = 0
        
        # Review moat score: high median reviews = hard to enter
        if median_review > 1000:
            moat = 90
        elif median_review > 500:
            moat = 70
        elif median_review > 200:
            moat = 50
        elif median_review > 50:
            moat = 30
        else:
            moat = 10
        
        # Competitor ASINs
        competitor_asins = [p.get("asin", "") for p in products if p.get("asin")]
        
        # Competition score (lower = better opportunity)
        # Factors: brand concentration, ad density, review moat, price crowding
        comp_score = (
            hhi * 0.30 +              # Brand concentration
            ad_density * 0.25 +       # Ad density
            moat * 0.25 +             # Review moat
            price_crowding * 0.20     # Price crowding
        )
        comp_score = round(min(100, max(0, comp_score)), 1)
        
        return CompetitionSignal(
            product_id="",  # Category-level, not product-specific
            category=category,
            region=region,
            total_listings=total,
            unique_brands=unique_brands,
            brand_concentration_hhi=hhi,
            amazon_basics_present=amazon_basics,
            top_brand_share_pct=round(top_brand_share, 1),
            price_bands=price_bands,
            price_band_crowding=price_crowding,
            ad_density_first_page=round(ad_density, 1),
            avg_review_count_top10=round(avg_review_top10, 1),
            review_moat_score=moat,
            competitor_asins=competitor_asins[:20],
            competition_score=comp_score,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )
    
    def _empty_signal(self, category: str, region: str) -> CompetitionSignal:
        return CompetitionSignal(
            product_id="",
            category=category,
            region=region,
            total_listings=0,
            unique_brands=0,
            brand_concentration_hhi=0,
            amazon_basics_present=False,
            top_brand_share_pct=0,
            price_bands={},
            price_band_crowding=0,
            ad_density_first_page=0,
            avg_review_count_top10=0,
            review_moat_score=0,
            competitor_asins=[],
            competition_score=0,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )
    
    def analyze_product_competitors(self, product_id: str, asin: str = None) -> CompetitionSignal:
        """Analyze direct competitors for a specific product."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        # Get product category
        cur.execute("SELECT category, region FROM master_products WHERE product_id = ?", (product_id,))
        row = cur.fetchone()
        if not row:
            return self._empty_signal("Unknown", "India")
        
        category, region = row
        
        # Get competitor ASINs from multi_platform_listings
        cur.execute('''
            SELECT DISTINCT product_id, platform, title, price, rating, review_count
            FROM multi_platform_listings
            WHERE product_id != ? AND platform = 'amazon_india'
            LIMIT 50
        ''', (product_id,))
        
        competitors = [dict(r) for r in cur.fetchall()]
        
        # Convert to product format
        products = []
        for c in competitors:
            products.append({
                "asin": c.get("product_id", ""),
                "title": c.get("title", ""),
                "price": c.get("price", 0),
                "rating": c.get("rating", 0),
                "review_count": c.get("review_count", 0),
                "is_sponsored": False,
            })
        
        return self._analyze_products(category, region, products)


async def run_competition_xray(category: str, region: str = "India") -> Dict[str, Any]:
    """Run competition analysis for a category."""
    xray = CompetitionXRay()
    signal = await xray.analyze_category(category, region)
    
    return {
        "category": category,
        "competition_score": signal.competition_score,
        "total_listings": signal.total_listings,
        "unique_brands": signal.unique_brands,
        "brand_concentration_hhi": signal.brand_concentration_hhi,
        "amazon_basics_present": signal.amazon_basics_present,
        "top_brand_share_pct": signal.top_brand_share_pct,
        "price_band_crowding": signal.price_band_crowding,
        "ad_density_first_page": signal.ad_density_first_page,
        "review_moat_score": signal.review_moat_score,
        "competitor_asins": signal.competitor_asins[:10],
    }


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_competition_xray("Stainless Steel Insulated Water Bottle"))
    print(json.dumps(result, indent=2, default=str))