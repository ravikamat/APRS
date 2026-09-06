"""
core/winner_score.py — Nightly Winner Score Computation.

Computes and updates winner_scores for all validated products.
Runs nightly to keep rankings fresh.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from core.database import get_connection, get_all_products, get_defect_clusters, get_economics_assessments, get_supplier_profiles_for_product
from tools.demand_sense import DemandSense
from tools.competition_xray import CompetitionXRay

logger = logging.getLogger("aprs.winner_score")


@dataclass
class ScoreComponents:
    """Individual winner score components."""
    margin_safety: float
    demand_velocity: float
    differentiation: float
    competition_gap: float
    signal_freshness: float
    supply_access: float


class WinnerScoreComputer:
    """
    Winner Score Computer — computes the ranking score for all products.
    
    WinnerScore = 0.30*MarginSafety + 0.20*DemandVelocity + 0.20*Differentiation
                + 0.15*CompetitionGap + 0.10*SignalFreshness + 0.05*SupplyAccess
    
    Runs nightly to keep leaderboard current.
    """
    
    WEIGHTS = {
        "margin_safety": 0.30,
        "demand_velocity": 0.20,
        "differentiation": 0.20,
        "competition_gap": 0.15,
        "signal_freshness": 0.10,
        "supply_access": 0.05,
    }
    
    def __init__(self):
        self.demand_sense = DemandSense()
        self.competition_xray = CompetitionXRay()
        self.conn = None
    
    def _get_connection(self):
        if self.conn is None:
            from core.database import get_connection
            self.conn = get_connection()
        return self.conn
    
    def compute_margin_safety(self, product: Dict) -> float:
        """Margin safety: net margin after stress scenarios (0-100)."""
        # Get economics assessments
        econ = get_economics_assessments(product["product_id"])
        
        if not econ:
            return 0.0
        
        # Use expected scenario margin
        expected = next((e for e in econ if e.get("scenario") == "EXPECTED"), econ[0])
        net_margin = expected.get("contribution_margin_pct", 0)
        
        # Conservative scenario as stress test
        conservative = next((e for e in econ if e.get("scenario") == "CONSERVATIVE"), None)
        stress_margin = conservative.get("contribution_margin_pct", 0) if conservative else net_margin * 0.7
        
        # Score: 0% margin = 0, 30%+ margin = 100
        score = min(100, max(0, (net_margin / 30) * 100))
        
        # Penalty for low stress margin
        if stress_margin < 10:
            score *= 0.5
        elif stress_margin < 15:
            score *= 0.75
        
        return round(score, 1)
    
    def compute_demand_velocity(self, product: Dict) -> float:
        """Demand velocity: review growth rate + BSR trend (0-100)."""
        demand = self.demand_sense.analyze_product(product["product_id"])
        
        if not demand:
            return 0.0
        
        # Combine review growth and BSR velocity
        review_growth = demand.review_growth_rate
        bsr_velocity = demand.bsr_velocity  # Negative = improving
        
        # Review growth score: 0 reviews/mo = 0, 50+/mo = 100
        review_score = min(100, max(0, (review_growth / 50) * 100))
        
        # BSR velocity score: improving BSR (negative) = good
        bsr_score = min(100, max(0, 50 - bsr_velocity))
        
        # Combine
        velocity = (review_score * 0.6) + (bsr_score * 0.4)
        
        return round(min(100, max(0, velocity)), 1)
    
    def compute_differentiation(self, product: Dict) -> float:
        """Differentiation: fixable defects found x severity (0-100)."""
        defects = get_defect_clusters(product["product_id"])
        
        if not defects:
            return 0.0
        
        # Count fixable defects by severity
        fixable = [d for d in defects if d.get("is_fixable")]
        
        severity_scores = {"CRITICAL": 30, "HIGH": 20, "MEDIUM": 10, "LOW": 5}
        total_score = sum(severity_scores.get(d.get("severity", "LOW"), 5) for d in fixable)
        
        # Cap at 100
        return round(min(100, total_score), 1)
    
    def compute_competition_gap(self, product: Dict) -> float:
        """Competition gap: inverse of brand concentration, review gap (0-100)."""
        # This would ideally use CompetitionXRay
        # For now, use proxy from product data
        
        bsr = product.get("bsr_rank", 50000)
        review_count = product.get("review_count", 0)
        
        # Review gap: high BSR (low sales) + low reviews = opportunity
        # But we want HIGH competition gap = LOW competition = GOOD
        if bsr > 50000:
            return 0.0  # No signal
        
        # Low review count relative to BSR = gap
        expected_reviews = max(1, 50000 / bsr * 100)  # Rough heuristic
        gap_ratio = expected_reviews / max(1, review_count)
        
        # Brand concentration penalty (unknown here, assume moderate)
        brand_penalty = 0.7
        
        score = min(100, gap_ratio * 50 * brand_penalty)
        
        return round(score, 1)
    
    def compute_signal_freshness(self, product: Dict) -> float:
        """Signal freshness: trend velocity + recency (0-100)."""
        from core.database import get_trend_signals
        
        # Get trend signals for this category
        signals = get_trend_signals(category=product.get("category", ""), region=product.get("region", "India"), limit=5)
        
        if not signals:
            return 10.0  # Base score
        
        # Average velocity of recent signals
        velocities = [s.get("velocity_score", 0) for s in signals]
        avg_velocity = sum(velocities) / len(velocities) if velocities else 0
        
        # Recency: signals from last 7 days get bonus
        recent_count = 0
        for s in signals:
            try:
                created = datetime.fromisoformat(s.get("created_at", "").replace("Z", "+00:00"))
                if (datetime.now(timezone.utc) - created).days <= 7:
                    recent_count += 1
            except:
                pass
        
        recency_bonus = min(20, recent_count * 5)
        
        return round(min(100, avg_velocity + recency_bonus), 1)
    
    def compute_supply_access(self, product: Dict) -> float:
        """Supply access: verified suppliers found (0-100)."""
        suppliers = get_supplier_profiles_for_product(product["product_id"])
        
        if not suppliers:
            return 0.0
        
        verified = sum(1 for s in suppliers if s.get("gst_verified") or s.get("verification_score", 0) >= 60)
        total = len(suppliers)
        
        # Score based on verified count and total
        if verified >= 3:
            return 100.0
        elif verified >= 2:
            return 75.0
        elif verified >= 1:
            return 50.0
        elif total >= 3:
            return 30.0
        elif total >= 1:
            return 15.0
        else:
            return 0.0
    
    def compute_all_components(self, product: Dict) -> ScoreComponents:
        """Compute all score components for a product."""
        return ScoreComponents(
            margin_safety=self.compute_margin_safety(product),
            demand_velocity=self.compute_demand_velocity(product),
            differentiation=self.compute_differentiation(product),
            competition_gap=self.compute_competition_gap(product),
            signal_freshness=self.compute_signal_freshness(product),
            supply_access=self.compute_supply_access(product),
        )
    
    def compute_winner_score(self, components: ScoreComponents) -> float:
        """Compute final winner score from components."""
        score = (
            self.WEIGHTS["margin_safety"] * components.margin_safety +
            self.WEIGHTS["demand_velocity"] * components.demand_velocity +
            self.WEIGHTS["differentiation"] * components.differentiation +
            self.WEIGHTS["competition_gap"] * components.competition_gap +
            self.WEIGHTS["signal_freshness"] * components.signal_freshness +
            self.WEIGHTS["supply_access"] * components.supply_access
        )
        return round(score, 1)
    
    def update_all_scores(self) -> Dict[str, Any]:
        """Update winner scores for all products."""
        products = get_all_products(include_deleted=False)
        
        updated = 0
        errors = 0
        
        conn = self._get_connection()
        cur = conn.cursor()
        
        for product in products:
            try:
                components = self.compute_all_components(product)
                winner_score = self.compute_winner_score(components)
                
                cur.execute('''
                    INSERT OR REPLACE INTO winner_scores (
                        product_id, margin_safety_score, demand_velocity_score,
                        differentiation_score, competition_gap_score,
                        signal_freshness_score, supply_access_score, computed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ''', (
                    product["product_id"],
                    components.margin_safety,
                    components.demand_velocity,
                    components.differentiation,
                    components.competition_gap,
                    components.signal_freshness,
                    components.supply_access,
                ))
                
                updated += 1
                
            except Exception as e:
                logger.warning(f"Failed to compute winner score for {product.get('product_id')}: {e}")
                errors += 1
        
        conn.commit()
        conn.close()
        
        logger.info(f"Winner score update: {updated} updated, {errors} errors")
        return {"updated": updated, "errors": errors}


async def compute_winner_scores() -> Dict[str, Any]:
    """Nightly winner score computation."""
    computer = WinnerScoreComputer()
    return computer.update_all_scores()


async def get_leaderboard(limit: int = 20, region: str = None, category: str = None) -> List[Dict[str, Any]]:
    """Get current leaderboard from winner_scores."""
    conn = get_connection()
    cur = conn.cursor()
    
    query = '''
        SELECT 
            ws.*, mp.name, mp.category, mp.region, mp.net_profit_pct, 
            mp.overall_score, mp.status, mp.bsr_rank
        FROM winner_scores ws
        JOIN master_products mp ON ws.product_id = mp.product_id
        WHERE mp.is_deleted = 0
    '''
    params = []
    
    if region:
        query += " AND mp.region = ?"
        params.append(region)
    if category:
        query += " AND mp.category = ?"
        params.append(category)
    
    query += " ORDER BY ws.winner_score DESC LIMIT ?"
    params.append(limit)
    
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    
    return rows


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(compute_winner_scores())
    print(f"Winner score computation: {result}")
    
    leaderboard = asyncio.run(get_leaderboard(10))
    print("\nTOP 10 LEADERBOARD:")
    for i, p in enumerate(leaderboard, 1):
        print(f"  {i}. {p['name'][:50]} - Score: {p['winner_score']:.1f} (Margin: {p['margin_safety_score']:.1f}, Demand: {p['demand_velocity_score']:.1f}, Diff: {p['differentiation_score']:.1f})")