"""
core/gate_engine.py — Unified 4-Gate State Machine for APRS V6 Pro.

Replaces the scattered 6-gate system with a deterministic 4-gate pipeline:

Gate 1: Keepa BSR Signal Validation (<50k BSR, CV <0.30)
Gate 2: Defect Mining (Ollama - 3-star review analysis)  
Gate 3: 15-Factor Economics (>=20% net margin)
Gate 4: Deterministic Scoring (>=75/100)

Each gate is a pure function with explicit pass/fail criteria.
No LLM calls in gates 1, 3, 4. Only Gate 2 uses local Ollama.
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum

from config.settings import settings
from core.validation import (
    RawProduct, CanonicalProduct, ValidationPipeline, ProductMatcher, DemandProxyScorer,
)
from core.economics_engine import Comprehensive15FactorEconomics
from core.scoring_engine import ScoringEngine, ScoreBreakdown
from tools.review_miner import ReviewMiner

logger = logging.getLogger("aprs.gate_engine")


class GateStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass
class GateResult:
    """Result of a single gate evaluation."""
    gate_number: int
    gate_name: str
    status: GateStatus
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASS


@dataclass
class PipelineResult:
    """Complete pipeline result for a product."""
    product: CanonicalProduct
    gate_results: List[GateResult]
    final_verdict: str  # PROCEED, MARGINAL, REJECT
    score_breakdown: Optional[ScoreBreakdown] = None
    economics_assessment: Optional[Any] = None
    defects: List[Dict] = field(default_factory=list)
    v2_spec: Dict = field(default_factory=dict)
    
    @property
    def all_gates_passed(self) -> bool:
        return all(g.passed for g in self.gate_results)
    
    @property
    def current_gate(self) -> int:
        for i, g in enumerate(self.gate_results):
            if g.status != GateStatus.PASS:
                return g.gate_number
        return 5  # All gates passed


class GateEngine:
    """
    Unified 4-Gate State Machine.
    
    Executes gates sequentially. Each gate must pass before the next runs.
    Deterministic - no LLM in gates 1, 3, 4.
    """
    
    GATE_DEFINITIONS = {
        1: ("Signal Validation", "Keepa BSR < 50k, Price CV < 0.30"),
        2: ("Defect Mining", "Ollama extracts actionable defects from 3-star reviews"),
        3: ("Economics Validation", "15-Factor 3-Scenario >= 20% net margin"),
        4: ("Deterministic Scoring", "0-100 Rubric >= 75"),
    }
    
    def __init__(
        self,
        min_bsr: int = None,
        max_cv: float = None,
        min_margin_pct: float = None,
        min_score: int = None,
    ):
        self.min_bsr = min_bsr or settings.gate1_bsr_threshold
        self.max_cv = max_cv or settings.gate1_cv_threshold
        self.min_margin_pct = min_margin_pct or settings.gate3_min_margin_pct
        self.min_score = min_score or settings.gate4_min_score
        
        self.scoring_engine = ScoringEngine()
        self.economics_engine = Comprehensive15FactorEconomics()
        self.review_miner = ReviewMiner()
    
    def run_gate_1_signal(
        self,
        product: CanonicalProduct,
        bsr_current: int,
        bsr_30d_ago: Optional[int] = None,
        price_current: float = None,
        price_30d_ago: Optional[float] = None,
    ) -> GateResult:
        """
        Gate 1: Signal Validation
        
        Criteria:
        - BSR < 50,000 (configurable)
        - Price Coefficient of Variation < 0.30 (configurable)
        - Price stability check
        """
        logger.info(f"Gate 1: Validating signal for {product.canonical_title[:50]}")
        
        # BSR check
        bsr_pass = bsr_current is not None and bsr_current < self.min_bsr
        
        # Price CV check (if historical data available)
        cv_pass = True
        cv = None
        if price_current and price_30d_ago and price_30d_ago > 0:
            cv = abs(price_current - price_30d_ago) / price_30d_ago
            cv_pass = cv < self.max_cv
        
        passed = bsr_pass and cv_pass
        
        details = {
            "bsr_current": bsr_current,
            "bsr_threshold": self.min_bsr,
            "bsr_pass": bsr_pass,
            "price_cv": cv,
            "cv_threshold": self.max_cv,
            "cv_pass": cv_pass,
        }
        
        return GateResult(
            gate_number=1,
            gate_name=self.GATE_DEFINITIONS[1][0],
            status=GateStatus.PASS if passed else GateStatus.FAIL,
            details=details,
        )
    
    async def run_gate_2_defects(
        self,
        product: CanonicalProduct,
        reviews: List[str],
    ) -> GateResult:
        """
        Gate 2: Defect Mining (uses local Ollama)
        
        Criteria:
        - At least 1 actionable defect extracted from 3-star reviews
        - Defects have specific suggested fixes
        - v2.0 specification generated
        
        This is the ONLY gate that uses an LLM (local Ollama).
        """
        logger.info(f"Gate 2: Mining defects for {product.canonical_title[:50]}")
        
        if not reviews:
            return GateResult(
                gate_number=2,
                gate_name=self.GATE_DEFINITIONS[2][0],
                status=GateStatus.FAIL,
                details={"error": "No 3-star reviews provided"},
                error="No reviews available for defect mining",
            )
        
        try:
            result = await self.review_miner.extract_defects(
                product_title=product.canonical_title,
                reviews=reviews,
            )
            
            defects = result.get("defects", [])
            v2_spec = result.get("v2_spec", {})
            
            # Pass if we got at least 1 valid defect with a fix
            valid_defects = [
                d for d in defects 
                if d.get("defect") and d.get("suggested_fix")
            ]
            
            passed = len(valid_defects) > 0
            
            details = {
                "total_defects": len(defects),
                "actionable_defects": len(valid_defects),
                "defects": valid_defects,
                "v2_spec": v2_spec,
                "has_v2_improvements": bool(v2_spec),
            }
            
            return GateResult(
                gate_number=2,
                gate_name=self.GATE_DEFINITIONS[2][0],
                status=GateStatus.PASS if passed else GateStatus.FAIL,
                details=details,
            )
            
        except Exception as e:
            logger.error(f"Gate 2 error for {product.canonical_title}: {e}")
            return GateResult(
                gate_number=2,
                gate_name=self.GATE_DEFINITIONS[2][0],
                status=GateStatus.FAIL,
                details={"error": str(e)},
                error=f"Defect mining failed: {e}",
            )
    
    def run_gate_3_economics(
        self,
        product: CanonicalProduct,
        fob_price: float,
        planned_msrp: float,
        region: str = "India",
        category: str = "General",
        marketplace: str = "amazon",
        **kwargs
    ) -> GateResult:
        """
        Gate 3: Economics Validation
        
        Criteria:
        - Expected scenario: Net margin >= 20% AND Gross margin >= 50%
        - OR Conservative scenario: Net margin >= 15% AND Gross margin >= 45%
        - Lead time <= 70% of trend half-life
        
        Uses Comprehensive15FactorEconomics.passes_gate()
        """
        logger.info(f"Gate 3: Validating economics for {product.canonical_title[:50]}")
        
        try:
            passes, details = self.economics_engine.passes_gate(
                fob_price=fob_price,
                planned_msrp=planned_msrp,
                region=region,
                category=category,
                marketplace=marketplace,
                min_margin_pct=self.min_margin_pct,
                **kwargs
            )
            
            # Also get full assessment for downstream use
            assessment = self.economics_engine.evaluate_15_factor_economics(
                product_id=f"CANONICAL_{hash(product.canonical_title) % 1000000:06d}",
                fob_price=fob_price,
                planned_msrp=planned_msrp,
                region=region,
                category=category,
                marketplace=marketplace,
                **kwargs
            )
            
            details["full_assessment"] = assessment
            
            return GateResult(
                gate_number=3,
                gate_name=self.GATE_DEFINITIONS[3][0],
                status=GateStatus.PASS if passes else GateStatus.FAIL,
                details=details,
            )
            
        except Exception as e:
            logger.error(f"Gate 3 error for {product.canonical_title}: {e}")
            return GateResult(
                gate_number=3,
                gate_name=self.GATE_DEFINITIONS[3][0],
                status=GateStatus.FAIL,
                details={"error": str(e)},
                error=f"Economics validation failed: {e}",
            )
    
    def run_gate_4_scoring(
        self,
        product: CanonicalProduct,
        bsr: Optional[int] = None,
        rating: float = 0.0,
        review_count: int = 0,
        net_margin_pct: float = 0.0,
        has_defects: bool = False,
        competitor_count: int = 10,
    ) -> GateResult:
        """
        Gate 4: Deterministic Scoring
        
        Criteria:
        - Total score >= 75 (PROCEED)
        - Total score >= 60 (MARGINAL)
        - Total score < 60 (REJECT)
        
        Scoring rubric (from roadmap):
        - Market Signal (BSR): 25 pts
        - Review Quality: 20 pts
        - Margin Safety: 40 pts
        - Defect Fixability: 10 pts
        - Competition Density: 5 pts
        """
        logger.info(f"Gate 4: Scoring {product.canonical_title[:50]}")
        
        try:
            score_breakdown = self.scoring_engine.score(
                bsr=bsr or product.amazon_bsr,
                rating=rating or product.rating,
                review_count=review_count or product.review_count,
                net_margin_pct=net_margin_pct,
                has_defects=has_defects,
                competitor_count=competitor_count,
            )
            
            passed = score_breakdown.total >= self.min_score
            
            details = {
                "total_score": score_breakdown.total,
                "threshold": self.min_score,
                "verdict": score_breakdown.verdict,
                "breakdown": {
                    "market_signal": score_breakdown.market_signal,
                    "review_quality": score_breakdown.review_quality,
                    "margin_safety": score_breakdown.margin_safety,
                    "defect_fixability": score_breakdown.defect_fixability,
                    "competition_density": score_breakdown.competition_density,
                },
            }
            
            return GateResult(
                gate_number=4,
                gate_name=self.GATE_DEFINITIONS[4][0],
                status=GateStatus.PASS if passed else GateStatus.FAIL,
                details=details,
            )
            
        except Exception as e:
            logger.error(f"Gate 4 error for {product.canonical_title}: {e}")
            return GateResult(
                gate_number=4,
                gate_name=self.GATE_DEFINITIONS[4][0],
                status=GateStatus.FAIL,
                details={"error": str(e)},
                error=f"Scoring failed: {e}",
            )
    
    async def run_full_pipeline(
        self,
        product: CanonicalProduct,
        # Gate 1 inputs
        bsr_current: int,
        bsr_30d_ago: Optional[int] = None,
        price_current: float = None,
        price_30d_ago: Optional[float] = None,
        # Gate 2 inputs
        reviews_3star: List[str] = None,
        # Gate 3 inputs
        fob_price: float = 0.0,
        planned_msrp: float = 0.0,
        region: str = "India",
        category: str = "General",
        marketplace: str = "amazon",
        # Gate 4 inputs
        rating: float = None,
        review_count: int = None,
        competitor_count: int = 10,
        **econ_kwargs
    ) -> PipelineResult:
        """
        Run the complete 4-gate pipeline for a product.
        
        Gates execute sequentially. If any gate fails, pipeline stops.
        """
        logger.info(f"Starting 4-gate pipeline for: {product.canonical_title}")
        
        gate_results = []
        
        # Gate 1: Signal Validation
        g1 = self.run_gate_1_signal(
            product=product,
            bsr_current=bsr_current,
            bsr_30d_ago=bsr_30d_ago,
            price_current=price_current,
            price_30d_ago=price_30d_ago,
        )
        gate_results.append(g1)
        
        if not g1.passed:
            logger.warning(f"Gate 1 FAILED for {product.canonical_title}: {g1.details}")
            return PipelineResult(
                product=product,
                gate_results=gate_results,
                final_verdict="REJECT",
            )
        
        # Gate 2: Defect Mining
        g2 = await self.run_gate_2_defects(
            product=product,
            reviews=reviews_3star or [],
        )
        gate_results.append(g2)
        
        if not g2.passed:
            logger.warning(f"Gate 2 FAILED for {product.canonical_title}")
            return PipelineResult(
                product=product,
                gate_results=gate_results,
                final_verdict="REJECT",
                defects=g2.details.get("defects", []),
                v2_spec=g2.details.get("v2_spec", {}),
            )
        
        # Gate 3: Economics Validation
        g3 = self.run_gate_3_economics(
            product=product,
            fob_price=fob_price,
            planned_msrp=planned_msrp,
            region=region,
            category=category,
            marketplace=marketplace,
            **econ_kwargs
        )
        gate_results.append(g3)
        
        if not g3.passed:
            logger.warning(f"Gate 3 FAILED for {product.canonical_title}")
            return PipelineResult(
                product=product,
                gate_results=gate_results,
                final_verdict="REJECT",
                defects=g2.details.get("defects", []),
                v2_spec=g2.details.get("v2_spec", {}),
                economics_assessment=g3.details.get("full_assessment"),
            )
        
        # Gate 4: Deterministic Scoring
        g4 = self.run_gate_4_scoring(
            product=product,
            bsr=bsr_current,
            rating=rating or product.rating,
            review_count=review_count or product.review_count,
            net_margin_pct=g3.details.get("expected", {}).get("net_margin_pct", 0.0),
            has_defects=g2.details.get("actionable_defects", 0) > 0,
            competitor_count=competitor_count,
        )
        gate_results.append(g4)
        
        # Determine final verdict
        if g4.passed:
            final_verdict = "PROCEED"
        elif g4.details.get("total_score", 0) >= 60:
            final_verdict = "MARGINAL"
        else:
            final_verdict = "REJECT"
        
        logger.info(f"Pipeline complete for {product.canonical_title}: {final_verdict} (Score: {g4.details.get('total_score', 0)})")
        
        return PipelineResult(
            product=product,
            gate_results=gate_results,
            final_verdict=final_verdict,
            score_breakdown=g4.details.get("breakdown"),
            economics_assessment=g3.details.get("full_assessment"),
            defects=g2.details.get("defects", []),
            v2_spec=g2.details.get("v2_spec", {}),
        )


async def run_gate_pipeline_batch(
    products: List[CanonicalProduct],
    gate_inputs: Dict[str, Dict[str, Any]],
) -> List[PipelineResult]:
    """
    Run gate pipeline for multiple products in batch.
    
    Args:
        products: List of CanonicalProduct objects
        gate_inputs: Dict mapping product_id to gate input parameters
        
    Returns:
        List of PipelineResult objects
    """
    engine = GateEngine()
    results = []
    
    for product in products:
        inputs = gate_inputs.get(product.canonical_title, {})
        result = await engine.run_full_pipeline(product, **inputs)
        results.append(result)
    
    return results


if __name__ == "__main__":
    import asyncio
    
    # Quick test
    async def test():
        from core.validation import CanonicalProduct
        
        product = CanonicalProduct(
            canonical_title="Stainless Steel Water Bottle 1L",
            category="Kitchen",
            retail_price_inr=1299.0,
            amazon_asin="B001",
            rating=4.5,
            review_count=200,
            amazon_bsr=15000,
        )
        
        engine = GateEngine()
        
        # Test Gate 1
        g1 = engine.run_gate_1_signal(product, bsr_current=15000, price_current=1299, price_30d_ago=1250)
        print(f"Gate 1: {g1.status.value} - {g1.details}")
        
        # Test Gate 3
        g3 = engine.run_gate_3_economics(
            product, fob_price=350, planned_msrp=1299, region="India", category="Kitchen"
        )
        print(f"Gate 3: {g3.status.value} - Net Margin: {g3.details.get('expected', {}).get('net_margin_pct')}%")
        
        # Test Gate 4
        g4 = engine.run_gate_4_scoring(
            product, bsr=15000, rating=4.5, review_count=200, 
            net_margin_pct=25.37, has_defects=True, competitor_count=5
        )
        print(f"Gate 4: {g4.status.value} - Score: {g4.details.get('total_score')}")
        
        # Full pipeline (mock reviews for Gate 2)
        mock_reviews = [
            "Great bottle but lid leaks after a week",
            "Insulation good but paint chips easily",
            "Dent arrived on bottom, otherwise fine",
        ]
        
        result = await engine.run_full_pipeline(
            product=product,
            bsr_current=15000,
            price_current=1299,
            reviews_3star=mock_reviews,
            fob_price=350,
            planned_msrp=1299,
            region="India",
            category="Kitchen",
            competitor_count=5,
        )
        print(f"\nFull Pipeline: {result.final_verdict}")
        print(f"Gates passed: {sum(1 for g in result.gate_results if g.passed)}/4")
    
    asyncio.run(test())