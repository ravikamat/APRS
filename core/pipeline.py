"""
core/pipeline.py — V7 End-to-End Pipeline.

Replaces V5 AutonomousProductResearchOrchestrator (6-gate, NIM-dependent, daemon-based)
with deterministic 4-gate batch pipeline:

Stage 1: Discovery (WebAgent via browser-use) → RawProduct[]
Stage 2: Validation (Pydantic v2) → Validated RawProduct[]
Stage 3: Deduplication (ProductMatcher) → CanonicalProduct[]
Stage 4: Gate Execution (4-gate sequential) → PipelineResult[]

No daemons. Batch-only execution.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from datetime import datetime

from config.settings import settings
from core.database import (
    init_db, get_connection, record_product_evaluation, get_all_products,
    update_gate_status, init_product_gates, get_gate_status, get_3star_reviews
)
from core.validation import (
    RawProduct, CanonicalProduct, ValidationPipeline, ProductMatcher,
)
from core.gate_engine import GateEngine, PipelineResult
from core.rule_engine import create_rule_engine
from core.economics_engine import Comprehensive15FactorEconomics
from tools.discovery_engine import DiscoveryEngine
from tools.review_miner import ReviewMiner

logger = logging.getLogger("aprs.pipeline")


@dataclass
class PipelineConfig:
    """Configuration for pipeline execution."""
    region: str = "India"
    category: str = "General"
    max_niches: int = 5
    max_candidates_per_niche: int = 3
    max_pages: int = 2
    use_seed_keywords: bool = True
    competitor_count: int = 10
    min_margin_pct: float = 20.0
    min_score: int = 75


class V6Pipeline:
    """
    V6 Pro Deterministic Batch Pipeline.
    
    Flow:
    1. DiscoveryEngine → RawProduct[] (Amazon + Flipkart)
    2. ValidationPipeline.validate_batch() → Valid RawProduct[]
    3. ProductMatcher → CanonicalProduct[] (deduplicated)
    4. For each CanonicalProduct:
       a. GateEngine.run_gate_1_signal() → BSR/CV check
       b. GateEngine.run_gate_2_defects() → Ollama defect mining
       c. GateEngine.run_gate_3_economics() → 15-factor economics
       d. GateEngine.run_gate_4_scoring() → Deterministic scoring
    5. RuleEngine evaluation → Adjusted score + warnings
    6. Persist to DB + Excel
    """
    
    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        self.gate_engine = GateEngine(
            min_bsr=settings.gate1_bsr_threshold,
            max_cv=settings.gate1_cv_threshold,
            min_margin_pct=self.config.min_margin_pct,
            min_score=self.config.min_score,
        )
        self.rule_engine = create_rule_engine()
        self.discovery_engine = DiscoveryEngine()
        self.review_miner = ReviewMiner()
        self.validator = ValidationPipeline()
        self.matcher = ProductMatcher()
        self.economics_engine = Comprehensive15FactorEconomics()
    
    async def run_discovery(self) -> List[CanonicalProduct]:
        """Run multi-marketplace discovery and return deduplicated canonical products."""
        logger.info(f"Starting discovery: region={self.config.region}, category={self.config.category}")
        
        result = await self.discovery_engine.run_discovery_batch(
            region=self.config.region,
            max_niches=self.config.max_niches,
            max_candidates_per_niche=self.config.max_candidates_per_niche,
            use_seed_keywords=self.config.use_seed_keywords,
        )
        
        canonical_products = [
            CanonicalProduct(**p) for p in result.get("canonical_products", [])
        ]
        
        logger.info(f"Discovery complete: {len(canonical_products)} canonical products")
        return canonical_products
    
    async def run_gates_for_product(
        self,
        product: CanonicalProduct,
        fob_price: float = None,
        planned_msrp: float = None,
        reviews_3star: List[str] = None,
    ) -> PipelineResult:
        """Run all 4 gates for a single product."""
        
        # Use product data or defaults
        fob = fob_price or product.factory_fob_inr or product.retail_price_inr * 0.25
        msrp = planned_msrp or product.retail_price_inr
        
        # Fetch 3-star reviews from database if not provided
        if reviews_3star is None and product.product_id:
            reviews_3star = get_3star_reviews(product.product_id, "amazon", 20)
        reviews = reviews_3star or []
        
        result = await self.gate_engine.run_full_pipeline(
            product=product,
            bsr_current=product.amazon_bsr or 50000,
            price_current=msrp,
            price_30d_ago=msrp * 1.02,
            reviews_3star=reviews,
            fob_price=fob,
            planned_msrp=msrp,
            region=self.config.region,
            category=product.category or "General",
            marketplace="amazon",
            competitor_count=self.config.competitor_count,
        )
        
        # Apply rule engine
        gate_results = {g.gate_number: g.details for g in result.gate_results}
        rule_result = self.rule_engine.evaluate_product({
            "product_id": product.canonical_title,
            "bsr": product.amazon_bsr,
            "price_cv": gate_results.get(1, {}).get("price_cv", 0),
            "category": product.category,
            "net_margin_pct": gate_results.get(3, {}).get("expected", {}).get("net_margin_pct", 0),
            "rating": product.rating,
            "review_count": product.review_count,
            "competitor_count": self.config.competitor_count,
            "lead_time_days": 30,
            "trend_half_life_days": 90,
            "has_defects": gate_results.get(2, {}).get("actionable_defects", 0) > 0,
            "actionable_defects": gate_results.get(2, {}).get("actionable_defects", 0),
            "score": gate_results.get(4, {}).get("total_score", 0),
        }, gate_results)
        
        # Merge rule engine adjustments
        result.final_verdict = rule_result["verdict"] if rule_result["verdict"] != "PENDING" else result.final_verdict
        result.score_breakdown = rule_result.get("context", {})
        
        # Log warnings
        for warning in rule_result.get("warnings", []):
            logger.warning(f"Rule warning for {product.canonical_title}: {warning}")
        
        return result
    
    def persist_results(self, results: List[PipelineResult]):
        """Persist pipeline results to DB and Excel."""
        for result in results:
            product = result.product
            gate_results = {g.gate_number: g.details for g in result.gate_results}
            
            # Prepare evaluation dict for DB
            econ_details = gate_results.get(3, {}).get("expected", {})
            eval_dict = {
                "landed_cogs": econ_details.get("landed_cogs", 0),
                "gross_margin_pct": econ_details.get("gross_margin_pct", 0),
                "net_profit_pct": econ_details.get("net_margin_pct", 0),
                "worst_case_stress_margin_pct": gate_results.get(3, {}).get("conservative", {}).get("net_margin_pct", 0),
                "status": "PASS" if result.final_verdict == "PROCEED" else "FAIL",
                "score": gate_results.get(4, {}).get("total_score", 0),
                "consensus_status": "CONSENSUS_PASS" if result.final_verdict == "PROCEED" else "CONSENSUS_FAIL",
                "action_plan": f"Gate verdict: {result.final_verdict}",
            }
            
            import uuid
            # Generate deterministic UUID from canonical_title + category for reproducibility
            product_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{product.canonical_title}|{product.category or 'General'}"))
            
            prod_dict = {
                "id": product_uuid,
                "name": product.canonical_title,
                "category": product.category or "General",
                "region": self.config.region,
                "retail_msrp": product.retail_price_inr,
                "factory_cogs": product.factory_fob_inr or product.retail_price_inr * 0.25,
                "est_cac": 0,
                "sourcing_hub": product.category or "General",
                "marketplace_url": f"https://amazon.in/dp/{product.amazon_asin}" if product.amazon_asin else "",
                "competitor_flaw": "",
                "upgrade_v2": gate_results.get(2, {}).get("v2_spec", {}).get("improvement_1", ""),
                "bsr_rank": product.amazon_bsr or 0,
                "estimated_daily_units": 30,
                "ad_active_days": 0,
                "suppliers": [],
            }
            
            record_product_evaluation(prod_dict, eval_dict)
            
            # Initialize gate progress
            init_product_gates(product_uuid)
            for g in result.gate_results:
                update_gate_status(
                    product_uuid,
                    g.gate_number,
                    g.status.value,
                    metadata=g.details,
                    completed_by="pipeline"
                )
        
        # Update master Excel
        from core.excel_manager import update_master_excel
        update_master_excel()
        
        logger.info(f"Persisted {len(results)} products to DB and Excel")


async def run_full_pipeline(config: PipelineConfig = None) -> List[PipelineResult]:
    """
    Main entry point for batch pipeline execution.
    
    Returns list of PipelineResult for all processed products.
    """
    pipeline = V6Pipeline(config)
    
    # Phase 1: Discovery
    canonical_products = await pipeline.run_discovery()
    
    if not canonical_products:
        logger.warning("No products discovered")
        return []
    
    # Phase 2: Gate execution
    results = []
    for product in canonical_products:
        logger.info(f"Processing gates for: {product.canonical_title[:50]}")
        
        # Fetch 3-star reviews from database (run_gates_for_product will fetch if not provided)
        result = await pipeline.run_gates_for_product(
            product=product,
            fob_price=product.factory_fob_inr or product.retail_price_inr * 0.25,
            planned_msrp=product.retail_price_inr,
        )
        results.append(result)
    
    # Phase 3: Persistence
    pipeline.persist_results(results)
    
    # Summary
    proceed = sum(1 for r in results if r.final_verdict == "PROCEED")
    marginal = sum(1 for r in results if r.final_verdict == "MARGINAL")
    reject = sum(1 for r in results if r.final_verdict == "REJECT")
    
    logger.info(f"Pipeline complete: {proceed} PROCEED, {marginal} MARGINAL, {reject} REJECT")
    
    return results


def run_pipeline_cli(
    region: str = "India",
    category: str = None,
    max_niches: int = 5,
    max_candidates: int = 3,
) -> List[PipelineResult]:
    """CLI entry point for pipeline."""
    config = PipelineConfig(
        region=region,
        category=category or "General",
        max_niches=max_niches,
        max_candidates_per_niche=max_candidates,
    )
    return asyncio.run(run_full_pipeline(config))


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    
    # Simple CLI
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "scan":
            results = run_pipeline_cli(
                region="India",
                max_niches=5,
                max_candidates=3,
            )
            print(f"\nPipeline complete: {len(results)} products")
            for r in results:
                print(f"  {r.product.canonical_title[:50]}: {r.final_verdict} (Score: {r.score_breakdown.get('total_score', 'N/A')})")
    else:
        print("Usage: python -m core.pipeline scan")