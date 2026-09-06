"""
tools/demand_sense.py — Demand Sensing Layer.

Beyond trends: Real demand proxies from marketplace data.
- Keepa BSR velocity (BSR rank change over time)
- Review-count growth rate (reviews/month = true demand proxy)
- Review-gap detection (high sales + few reviews = weak competition)
- Price stability tracking
"""
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

from core.database import get_connection

logger = logging.getLogger("aprs.demand_sense")


@dataclass
class DemandSignal:
    """A demand signal for a product/category."""
    product_id: str
    category: str
    region: str
    bsr_current: Optional[int]
    bsr_30d_ago: Optional[int]
    bsr_velocity: float  # % change (negative = improving)
    review_count_current: int
    review_count_30d_ago: int
    review_growth_rate: float  # reviews/month
    review_gap_score: float  # 0-100, high = high sales + few reviews
    price_current: Optional[float]
    price_30d_ago: Optional[float]
    price_cv: float
    demand_score: float  # 0-100 composite
    signal_quality: str  # HIGH, MEDIUM, LOW
    computed_at: str


class DemandSense:
    """
    Demand Sensing Layer — computes real demand proxies from marketplace data.
    
    Sources:
    - Keepa API (BSR history, price history)
    - Multi-platform listings snapshots (review counts over time)
    - Daily snapshots table (historical BSR/price/review data)
    """
    
    def __init__(self):
        self.conn = None
    
    def _get_connection(self):
        if self.conn is None:
            from core.database import get_connection
            self.conn = get_connection()
        return self.conn
    
    def get_bsr_history(self, product_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get BSR history from daily_snapshots or keepa_cache."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT bsr_rank, current_price as price_inr, date as snapshot_date
            FROM daily_snapshots
            WHERE product_id = ? AND date >= date('now', ?)
            ORDER BY date ASC
        ''', (product_id, f'-{days} days'))
        
        rows = [dict(r) for r in cur.fetchall()]
        return rows
    
    def get_listing_snapshots(self, product_id: str, marketplace: str = "amazon", days: int = 30) -> List[Dict[str, Any]]:
        """Get listing snapshots from multi_platform_listings history (if tracked)."""
        # For now, we'll use daily_snapshots as the primary source
        return self.get_bsr_history(product_id, days)
    
    def compute_bsr_velocity(self, history: List[Dict]) -> tuple[Optional[int], Optional[int], float]:
        """Compute BSR velocity from history."""
        if not history:
            return None, None, 0.0
        
        current = history[-1].get("bsr_rank") if history[-1].get("bsr_rank") else None
        oldest = history[0].get("bsr_rank") if history[0].get("bsr_rank") else None
        
        if current and oldest and oldest > 0:
            # BSR: lower is better, so negative velocity = improving
            velocity = ((current - oldest) / oldest) * 100
            return current, oldest, round(velocity, 2)
        
        return current, oldest, 0.0
    
    def compute_review_growth(self, history: List[Dict], product_id: str) -> tuple[int, int, float]:
        """Compute review count growth rate (reviews/month)."""
        if not history:
            return 0, 0, 0.0
        
        # Get current review count from master_products or multi_platform_listings
        conn = self._get_connection()
        cur = conn.cursor()
        
        # Try to get review_count from multi_platform_listings (most recent)
        cur.execute('''
            SELECT review_count FROM multi_platform_listings
            WHERE product_id = ? AND platform = 'amazon_india'
            ORDER BY created_at DESC LIMIT 1
        ''', (product_id,))
        row = cur.fetchone()
        current_reviews = row[0] if row and row[0] else 0
        
        # Estimate review count 30 days ago based on BSR velocity
        # If no history, assume slow growth
        if len(history) < 2:
            return current_reviews, max(0, current_reviews - 5), 5.0  # Assume 5 reviews/month
        
        # Estimate based on BSR changes (rough heuristic)
        # This is a simplified estimation - in production, use Keepa API
        bsr_changes = []
        for i in range(1, len(history)):
            prev_bsr = history[i-1].get("bsr_rank")
            curr_bsr = history[i].get("bsr_rank")
            if prev_bsr and curr_bsr and prev_bsr > 0:
                bsr_changes.append((curr_bsr - prev_bsr) / prev_bsr)
        
        avg_bsr_change = sum(bsr_changes) / len(bsr_changes) if bsr_changes else 0
        
        # Estimate monthly review growth based on BSR velocity
        # Higher sales (improving BSR) -> more reviews
        estimated_monthly_growth = max(1, 50 * (1 - avg_bsr_change))
        
        return current_reviews, max(0, int(current_reviews - estimated_monthly_growth)), estimated_monthly_growth
    
    def compute_price_cv(self, history: List[Dict]) -> tuple[Optional[float], Optional[float], float]:
        """Compute price coefficient of variation."""
        prices = [h.get("price_inr") for h in history if h.get("price_inr")]
        
        if len(prices) < 2:
            return prices[-1] if prices else None, prices[0] if prices else None, 0.0
        
        current = prices[-1]
        oldest = prices[0]
        
        import statistics
        mean_price = statistics.mean(prices)
        stdev = statistics.stdev(prices) if len(prices) > 1 else 0
        cv = stdev / mean_price if mean_price > 0 else 0
        
        return current, oldest, round(cv, 4)
    
    def compute_review_gap_score(self, bsr: Optional[int], review_count: int) -> float:
        """
        Review gap detection: High sales (low BSR) + few reviews = weak competition.
        Score 0-100: higher = better opportunity.
        """
        if not bsr or bsr <= 0:
            return 0.0
        
        # Normalize BSR (lower is better, so invert)
        # BSR 1000 -> high sales, BSR 50000 -> low sales
        if bsr < 1000:
            sales_proxy = 100
        elif bsr < 5000:
            sales_proxy = 80
        elif bsr < 15000:
            sales_proxy = 60
        elif bsr < 50000:
            sales_proxy = 40
        else:
            sales_proxy = 10
        
        # Review density: few reviews for high sales = opportunity
        if review_count < 10:
            review_proxy = 100
        elif review_count < 50:
            review_proxy = 80
        elif review_count < 200:
            review_proxy = 50
        elif review_count < 500:
            review_proxy = 30
        else:
            review_proxy = 10
        
        # Gap = high sales proxy + high review proxy (few reviews)
        gap = (sales_proxy * 0.6) + (review_proxy * 0.4)
        return round(min(100, gap), 1)
    
    def compute_demand_score(self, bsr_velocity: float, review_growth: float, 
                            review_gap: float, price_cv: float) -> float:
        """Composite demand score 0-100."""
        # BSR velocity: negative = improving (good), positive = declining (bad)
        bsr_score = max(0, 50 - bsr_velocity)  # improving BSR gets >50
        bsr_score = min(100, bsr_score)
        
        # Review growth: positive = growing demand
        review_score = min(100, max(0, 50 + review_growth * 2))
        
        # Review gap: high = opportunity
        gap_score = review_gap
        
        # Price stability: low CV = stable pricing (good)
        price_score = max(0, 100 - price_cv * 200)
        
        # Weighted composite
        demand = (
            bsr_score * 0.30 +
            review_score * 0.25 +
            gap_score * 0.30 +
            price_score * 0.15
        )
        
        return round(min(100, max(0, demand)), 1)
    
    def assess_signal_quality(self, history: List[Dict]) -> str:
        """Assess quality of demand signal based on data completeness."""
        if len(history) >= 10:
            return "HIGH"
        elif len(history) >= 5:
            return "MEDIUM"
        elif len(history) >= 2:
            return "LOW"
        return "INSUFFICIENT"
    
    def analyze_product(self, product_id: str) -> Optional[DemandSignal]:
        """Analyze demand for a single product."""
        history = self.get_bsr_history(product_id, 30)
        
        if not history:
            return None
        
        bsr_current, bsr_30d, bsr_velocity = self.compute_bsr_velocity(history)
        review_current, review_30d, review_growth = self.compute_review_growth(history, product_id)
        price_current, price_30d, price_cv = self.compute_price_cv(history)
        
        review_gap = self.compute_review_gap_score(bsr_current, review_current)
        demand_score = self.compute_demand_score(bsr_velocity, review_growth, review_gap, price_cv)
        quality = self.assess_signal_quality(history)
        
        # Get category/region from master_products
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("SELECT category, region FROM master_products WHERE product_id = ?", (product_id,))
        row = cur.fetchone()
        category = row[0] if row else "Unknown"
        region = row[1] if row else "India"
        
        return DemandSignal(
            product_id=product_id,
            category=category,
            region=region,
            bsr_current=bsr_current,
            bsr_30d_ago=bsr_30d,
            bsr_velocity=bsr_velocity,
            review_count_current=review_current,
            review_count_30d_ago=review_30d,
            review_growth_rate=review_growth,
            review_gap_score=review_gap,
            price_current=price_current,
            price_30d_ago=price_30d,
            price_cv=price_cv,
            demand_score=demand_score,
            signal_quality=quality,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )
    
    def analyze_category(self, category: str, region: str = "India", limit: int = 50) -> List[DemandSignal]:
        """Analyze demand for all products in a category."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT product_id FROM master_products
            WHERE category = ? AND region = ? AND is_deleted = 0
            ORDER BY overall_score DESC LIMIT ?
        ''', (category, region, limit))
        
        product_ids = [row[0] for row in cur.fetchall()]
        
        signals = []
        for pid in product_ids:
            signal = self.analyze_product(pid)
            if signal:
                signals.append(signal)
        
        return sorted(signals, key=lambda s: s.demand_score, reverse=True)
    
    def get_top_opportunities(self, region: str = "India", min_score: float = 60, limit: int = 20) -> List[DemandSignal]:
        """Get top demand opportunities across all categories."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        cur.execute('''
            SELECT product_id, category FROM master_products
            WHERE region = ? AND is_deleted = 0 AND overall_score > 0
            ORDER BY overall_score DESC LIMIT 200
        ''', (region,))
        
        products = cur.fetchall()
        
        signals = []
        for pid, cat in products:
            signal = self.analyze_product(pid)
            if signal and signal.demand_score >= min_score:
                signals.append(signal)
        
        return sorted(signals, key=lambda s: s.demand_score, reverse=True)[:limit]


async def run_demand_sense(category: str = None, region: str = "India") -> Dict[str, Any]:
    """Run demand sensing for a category or region."""
    sense = DemandSense()
    
    if category:
        signals = sense.analyze_category(category, region)
    else:
        signals = sense.get_top_opportunities(region)
    
    return {
        "signals_found": len(signals),
        "top_signals": [
            {
                "product_id": s.product_id,
                "category": s.category,
                "demand_score": s.demand_score,
                "bsr_velocity": s.bsr_velocity,
                "review_growth_rate": s.review_growth_rate,
                "review_gap_score": s.review_gap_score,
                "signal_quality": s.signal_quality,
            }
            for s in signals[:10]
        ],
    }


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_demand_sense())
    print(f"Found {result['signals_found']} demand signals")
    for s in result["top_signals"][:5]:
        print(f"  {s['product_id']}: demand={s['demand_score']}, bsr_vel={s['bsr_velocity']}, review_growth={s['review_growth_rate']}, gap={s['review_gap_score']}")