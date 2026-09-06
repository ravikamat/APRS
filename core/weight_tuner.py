"""
core/weight_tuner.py — Winner Score Weight Tuner.

Quarterly: backtest winner-score weights against actual launchpad_outcomes;
suggests (not auto-applies) weight changes for human review.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

try:
    from scipy.optimize import minimize
    HAS_SCIPY = True
except ImportError:
    minimize = None
    HAS_SCIPY = False

from core.database import get_connection, get_launchpad_items, get_learned_rules

logger = logging.getLogger("aprs.weight_tuner")


@dataclass
class WeightProposal:
    """Proposed weight changes for winner score."""
    current_weights: Dict[str, float]
    proposed_weights: Dict[str, float]
    backtest_r2: float
    backtest_mae: float
    improvement_pct: float
    rationale: str
    requires_approval: bool = True


@dataclass
class LaunchOutcome:
    """Actual outcome from launched product."""
    product_id: str
    category: str
    region: str
    actual_monthly_sales: int
    actual_net_margin_pct: float
    actual_return_rate_pct: float
    actual_ad_roas: float
    winner_score_at_launch: float
    margin_safety_score: float
    demand_velocity_score: float
    differentiation_score: float
    competition_gap_score: float
    signal_freshness_score: float
    supply_access_score: float


class WeightTuner:
    """
    Weight Tuner — backtests winner-score weights against real outcomes.
    
    WinnerScore = w1*MarginSafety + w2*DemandVelocity + w3*Differentiation 
                + w4*CompetitionGap + w5*SignalFreshness + w6*SupplyAccess
    
    Runs quarterly (or on demand) to optimize weights using launchpad_outcomes.
    Suggests changes but requires human approval before applying.
    """
    
    DEFAULT_WEIGHTS = {
        "margin_safety": 0.30,
        "demand_velocity": 0.20,
        "differentiation": 0.20,
        "competition_gap": 0.15,
        "signal_freshness": 0.10,
        "supply_access": 0.05,
    }
    
    def __init__(self):
        self.conn = None
    
    def _get_connection(self):
        if self.conn is None:
            from core.database import get_connection
            self.conn = get_connection()
        return self.conn
    
    def get_launch_outcomes(self, min_days: int = 30) -> List[LaunchOutcome]:
        """Fetch launchpad outcomes with their winner score components."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        # Get launchpad items with outcomes
        cur.execute('''
            SELECT 
                lo.product_id,
                lo.actual_monthly_sales,
                lo.actual_revenue_inr,
                lo.actual_net_margin_pct,
                lo.actual_return_rate_pct,
                lo.actual_ad_roas,
                lo.measurement_period_days,
                mp.category,
                mp.region,
                ws.margin_safety_score,
                ws.demand_velocity_score,
                ws.differentiation_score,
                ws.competition_gap_score,
                ws.signal_freshness_score,
                ws.supply_access_score,
                ws.winner_score
            FROM launchpad_outcomes lo
            JOIN master_products mp ON lo.product_id = mp.product_id
            LEFT JOIN winner_scores ws ON lo.product_id = ws.product_id
            WHERE lo.measurement_period_days >= ?
            AND lo.actual_monthly_sales IS NOT NULL
        ''', (min_days,))
        
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        
        outcomes = []
        for r in rows:
            # Compute winner score if missing
            winner_score = r.get("winner_score")
            if winner_score is None:
                ws = self.DEFAULT_WEIGHTS
                winner_score = (
                    ws["margin_safety"] * (r.get("margin_safety_score") or 0) +
                    ws["demand_velocity"] * (r.get("demand_velocity_score") or 0) +
                    ws["differentiation"] * (r.get("differentiation_score") or 0) +
                    ws["competition_gap"] * (r.get("competition_gap_score") or 0) +
                    ws["signal_freshness"] * (r.get("signal_freshness_score") or 0) +
                    ws["supply_access"] * (r.get("supply_access_score") or 0)
                )
            
            outcomes.append(LaunchOutcome(
                product_id=r["product_id"],
                category=r.get("category", ""),
                region=r.get("region", ""),
                actual_monthly_sales=r.get("actual_monthly_sales", 0),
                actual_net_margin_pct=r.get("actual_net_margin_pct", 0),
                actual_return_rate_pct=r.get("actual_return_rate_pct", 0),
                actual_ad_roas=r.get("actual_ad_roas", 0),
                winner_score_at_launch=winner_score,
                margin_safety_score=r.get("margin_safety_score", 0),
                demand_velocity_score=r.get("demand_velocity_score", 0),
                differentiation_score=r.get("differentiation_score", 0),
                competition_gap_score=r.get("competition_gap_score", 0),
                signal_freshness_score=r.get("signal_freshness_score", 0),
                supply_access_score=r.get("supply_access_score", 0),
            ))
        
        return outcomes
    
    def _build_training_data(self, outcomes: List[LaunchOutcome]) -> Tuple[np.ndarray, np.ndarray]:
        """Build X (features) and y (target) for regression."""
        if not outcomes:
            return np.array([]), np.array([])
        
        X = np.array([
            [
                o.margin_safety_score,
                o.demand_velocity_score,
                o.differentiation_score,
                o.competition_gap_score,
                o.signal_freshness_score,
                o.supply_access_score,
            ]
            for o in outcomes
        ])
        
        # Target: composite success metric (normalized)
        # Success = sales * margin * (1 - returns) * ROAS
        y = np.array([
            np.log1p(o.actual_monthly_sales) * 
            max(0.1, o.actual_net_margin_pct / 100) * 
            max(0.1, (100 - o.actual_return_rate_pct) / 100) * 
            min(10, max(0.1, o.actual_ad_roas))
            for o in outcomes
        ])
        
        # Normalize target
        if y.std() > 0:
            y = (y - y.mean()) / y.std()
        
        return X, y
    
    def optimize_weights(self, outcomes: List[LaunchOutcome]) -> Optional[Dict[str, float]]:
        """Optimize weights using constrained regression."""
        X, y = self._build_training_data(outcomes)
        
        if len(X) < 10:
            logger.warning(f"Insufficient data for weight tuning: {len(X)} samples (need >= 10)")
            return None
        
        # Constrained optimization: weights sum to 1, all >= 0
        n_weights = 6
        
        def objective(w):
            pred = X @ w
            return np.mean((pred - y) ** 2)  # MSE
        
        constraints = (
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1.0},  # Sum to 1
        )
        bounds = [(0.01, 0.5) for _ in range(n_weights)]  # Min 1%, max 50%
        
        # Initial guess: current default weights
        x0 = np.array([self.DEFAULT_WEIGHTS[k] for k in 
                      ["margin_safety", "demand_velocity", "differentiation", 
                       "competition_gap", "signal_freshness", "supply_access"]])
        
        if not HAS_SCIPY:
            logger.warning("scipy is not installed — skipping numerical optimization")
            return None
            
        try:
            result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints)
            
            if result.success:
                optimized = {
                    "margin_safety": round(result.x[0], 4),
                    "demand_velocity": round(result.x[1], 4),
                    "differentiation": round(result.x[2], 4),
                    "competition_gap": round(result.x[3], 4),
                    "signal_freshness": round(result.x[4], 4),
                    "supply_access": round(result.x[5], 4),
                }
                logger.info(f"Weight optimization successful: {optimized}")
                return optimized
            else:
                logger.warning(f"Weight optimization failed: {result.message}")
                return None
                
        except Exception as e:
            logger.error(f"Weight optimization error: {e}")
            return None
    
    def backtest(self, outcomes: List[LaunchOutcome], weights: Dict[str, float]) -> Dict[str, float]:
        """Evaluate weights using backtest."""
        X, y = self._build_training_data(outcomes)
        
        if len(X) < 5:
            return {"r2": 0, "mae": 0, "samples": len(X)}
        
        w = np.array([weights[k] for k in 
                     ["margin_safety", "demand_velocity", "differentiation", 
                      "competition_gap", "signal_freshness", "supply_access"]])
        
        pred = X @ w
        
        # R²
        ss_res = np.sum((y - pred) ** 2)
        ss_tot = np.sum((y - y.mean()) ** 2)
        r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        
        # MAE
        mae = np.mean(np.abs(y - pred))
        
        return {"r2": round(r2, 4), "mae": round(mae, 4), "samples": len(X)}
    
    def propose_weight_changes(self) -> Optional[WeightProposal]:
        """Run full weight tuning and propose changes."""
        logger.info("Starting weight tuning analysis...")
        
        outcomes = self.get_launch_outcomes()
        
        if len(outcomes) < 10:
            logger.warning(f"Not enough launch outcomes ({len(outcomes)}) for weight tuning")
            return None
        
        # Backtest current weights
        current_backtest = self.backtest(outcomes, self.DEFAULT_WEIGHTS)
        
        # Optimize
        proposed = self.optimize_weights(outcomes)
        
        if not proposed:
            return None
        
        # Backtest proposed weights
        proposed_backtest = self.backtest(outcomes, proposed)
        
        # Calculate improvement
        improvement = 0
        if current_backtest["mae"] > 0:
            improvement = (current_backtest["mae"] - proposed_backtest["mae"]) / current_backtest["mae"] * 100
        
        # Only propose if meaningful improvement
        if improvement < 5:  # Less than 5% improvement
            logger.info(f"Weight tuning improvement only {improvement:.1f}% - not proposing changes")
            return None
        
        rationale = (
            f"Backtest on {len(outcomes)} launched products. "
            f"Current R²={current_backtest['r2']:.3f}, MAE={current_backtest['mae']:.3f}. "
            f"Proposed R²={proposed_backtest['r2']:.3f}, MAE={proposed_backtest['mae']:.3f}. "
            f"Improvement: {improvement:.1f}% MAE reduction."
        )
        
        return WeightProposal(
            current_weights=self.DEFAULT_WEIGHTS.copy(),
            proposed_weights=proposed,
            backtest_r2=proposed_backtest["r2"],
            backtest_mae=proposed_backtest["mae"],
            improvement_pct=round(improvement, 1),
            rationale=rationale,
        )
    
    def record_proposal(self, proposal: WeightProposal) -> int:
        """Record weight proposal to learned_rules for human review."""
        conn = self._get_connection()
        cur = conn.cursor()
        
        cur.execute('''
            INSERT INTO learned_rules 
            (rule_type, category, region, parameters, weight, source, evidence_json, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            "weight_tuning_proposal",
            "ALL",
            "ALL",
            json.dumps(proposal.proposed_weights),
            1.0,
            "weight_tuner",
            json.dumps({
                "current_weights": proposal.current_weights,
                "proposed_weights": proposal.proposed_weights,
                "backtest_r2": proposal.backtest_r2,
                "backtest_mae": proposal.backtest_mae,
                "improvement_pct": proposal.improvement_pct,
                "rationale": proposal.rationale,
            }),
            0,  # Disabled by default - requires human approval
        ))
        
        rule_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        logger.info(f"Recorded weight tuning proposal as learned_rule #{rule_id}")
        return rule_id


async def run_weight_tuner() -> Dict[str, Any]:
    """Run quarterly weight tuning analysis."""
    tuner = WeightTuner()
    proposal = tuner.propose_weight_changes()
    
    if proposal:
        rule_id = tuner.record_proposal(proposal)
        return {
            "proposal_generated": True,
            "rule_id": rule_id,
            "current_weights": proposal.current_weights,
            "proposed_weights": proposal.proposed_weights,
            "improvement_pct": proposal.improvement_pct,
            "rationale": proposal.rationale,
        }
    else:
        return {
            "proposal_generated": False,
            "reason": "Insufficient data or no meaningful improvement found",
        }


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_weight_tuner())
    print(json.dumps(result, indent=2, default=str))