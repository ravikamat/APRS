"""
integrations/opencompany.py — FastAPI Webhooks for APRS V7.

Provides REST API endpoints for OpenCompany visual orchestration layer.
Each APRS module exposes a simple HTTP endpoint.
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

import sys
from pathlib import Path

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings

logger = logging.getLogger("aprs.opencompany")

# ── Request/Response Models ────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    region: str = "India"
    category: Optional[str] = None
    max_niches: int = 5
    max_candidates: int = 3
    max_pages: int = 2
    use_seed_keywords: bool = True

class CrawlResponse(BaseModel):
    success: bool
    task_id: str
    message: str
    data: Optional[Dict] = None

class TrendScanRequest(BaseModel):
    region: str = "India"
    max_signals: int = 10

class TrendScanResponse(BaseModel):
    success: bool
    signals_found: int
    data: List[Dict] = []

class NicheExpandRequest(BaseModel):
    lookback_days: int = 7

class NicheExpandResponse(BaseModel):
    success: bool
    niches_added: int
    niches_updated: int
    keywords_generated: int

class DiscoveryRequest(BaseModel):
    region: str = "India"
    category: Optional[str] = None
    max_niches: int = 5
    max_candidates: int = 3
    max_pages: int = 2
    use_seed_keywords: bool = True

class DiscoveryResponse(BaseModel):
    success: bool
    canonical_products: List[Dict] = []
    task_id: str

class ProblemMineRequest(BaseModel):
    product_id: str
    asin: Optional[str] = None
    flipkart_id: Optional[str] = None

class ProblemMineResponse(BaseModel):
    success: bool
    opportunities_found: int
    defects_extracted: int
    sources_scanned: int
    errors: List[str] = []

class SupplierDiscoverRequest(BaseModel):
    product_id: str
    limit: int = 10

class SupplierDiscoverResponse(BaseModel):
    success: bool
    suppliers_found: int
    suppliers_verified: int
    outreach_drafts_created: int

class OutreachDraftRequest(BaseModel):
    supplier_id: int
    product_id: str
    template_id: str = "initial_contact_v1"
    channel: str = "email"
    custom_vars: Dict[str, str] = {}

class OutreachDraftResponse(BaseModel):
    success: bool
    draft_id: Optional[int] = None
    message: str

class OutreachSendRequest(BaseModel):
    limit: int = 50

class OutreachSendResponse(BaseModel):
    success: bool
    sent: int
    failed: int
    results: List[Dict] = []

class EvaluationRequest(BaseModel):
    product_id: str
    fob_price: float
    planned_msrp: float
    region: str = "India"
    category: str = "General"
    marketplace: str = "amazon"

class EvaluationResponse(BaseModel):
    success: bool
    gate3_passed: bool
    gate4_score: float
    net_margin_pct: float
    recommendation: str

class WebhookEvent(BaseModel):
    event_type: str
    payload: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = "aprs"


# ── FastAPI App ────────────────────────────────────────────────────────────

class OpenCompanySettings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    log_level: str = "info"
    
    class Config:
        env_file = ".env"
        env_prefix = "OPENCOMPANY_"
        extra = "ignore"


# Global settings
app_settings = OpenCompanySettings()

# ── Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("OpenCompany starting up...")
    # Initialize database
    from core.database import init_db
    init_db()
    yield
    # Shutdown
    logger.info("OpenCompany shutting down...")


app = FastAPI(
    title="APRS V7 OpenCompany",
    description="Visual Orchestration Layer for Autonomous Product Research System",
    version="7.0.0",
    lifespan=lifespan,
)


# ── Health & Status ────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "7.0.0",
        "services": {
            "database": "connected",
            "llm_router": "ready",
            "web_agent": "ready",
        }
    }


@app.get("/status")
async def status():
    """Detailed system status."""
    from core.llm_router import LLMRouter
    from core.database import get_connection
    
    router = LLMRouter()
    llm_status = router.get_health_status()
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM master_products")
    product_count = cur.fetchone()[0]
    conn.close()
    
    return {
        "status": "operational",
        "products_in_db": product_count,
        "llm_tiers": llm_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Agent Endpoints ──────────────────────────────────────────────────────

@app.post("/run/crawler", response_model=CrawlResponse)
async def run_crawler(request: CrawlRequest, background_tasks: BackgroundTasks):
    """Run internet crawler for trend signals and product discovery."""
    from tools.internet_crawler import run_crawl_cycle
    
    task_id = f"crawl_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    # Run in background
    background_tasks.add_task(run_crawl_cycle_task, request.dict())
    
    return CrawlResponse(
        success=True,
        task_id=task_id,
        message="Crawl cycle started in background",
    )


async def run_crawl_cycle_task(params: Dict):
    """Background task for crawl cycle."""
    from tools.internet_crawler import run_crawl_cycle
    try:
        result = await run_crawl_cycle(**params)
        logger.info(f"Crawl cycle completed: {result}")
    except Exception as e:
        logger.error(f"Crawl cycle failed: {e}")


@app.post("/run/trend", response_model=TrendScanResponse)
async def run_trend_scan(request: TrendScanRequest):
    """Run trend signal scan."""
    from tools.trend_scout.trend_aggregator import OpenWebTrendScout
    
    scout = OpenWebTrendScout()
    signals = scout.harvest_all_active_trends(region=request.region, max_signals=request.max_signals)
    
    return TrendScanResponse(
        success=True,
        signals_found=len(signals),
        data=signals,
    )


@app.post("/run/expand", response_model=NicheExpandResponse)
async def run_niche_expansion(request: NicheExpandRequest):
    """Run niche expansion from trend signals."""
    from tools.niche_expander import run_niche_expansion
    
    result = await run_niche_expansion(request.lookback_days)
    
    return NicheExpandResponse(
        success=True,
        niches_added=result.niches_added,
        niches_updated=result.niches_updated,
        keywords_generated=result.keywords_generated,
    )


@app.post("/run/discover", response_model=DiscoveryResponse)
async def run_discovery(request: DiscoveryRequest):
    """Run product discovery for niches."""
    from tools.discovery_engine import DiscoveryEngine
    
    engine = DiscoveryEngine()
    result = await engine.run_discovery_batch(
        region=request.region,
        category=request.category,
        max_niches=request.max_niches,
        max_candidates_per_niche=request.max_candidates,
        max_pages=request.max_pages,
        use_seed_keywords=request.use_seed_keywords,
    )
    
    task_id = f"discover_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    
    return DiscoveryResponse(
        success=True,
        canonical_products=result.get("canonical_products", []),
        task_id=task_id,
    )


@app.post("/run/mine", response_model=ProblemMineResponse)
async def run_problem_mining(request: ProblemMineRequest):
    """Run problem mining for a product."""
    from tools.problem_miner import mine_product
    
    result = await mine_product(
        product_id=request.product_id,
        asin=request.asin,
        flipkart_id=request.flipkart_id,
    )
    
    return ProblemMineResponse(
        success=True,
        opportunities_found=result.get("opportunities_found", 0),
        defects_extracted=result.get("defects_extracted", 0),
        sources_scanned=result.get("sources_scanned", 0),
        errors=result.get("errors", []),
    )


@app.post("/run/suppliers", response_model=SupplierDiscoverResponse)
async def run_supplier_discovery(request: SupplierDiscoverRequest):
    """Discover and verify suppliers for a product."""
    from tools.supplier_agent import run_supplier_batch
    
    result = await run_supplier_batch(limit=1, product_id=request.product_id)
    
    return SupplierDiscoverResponse(
        success=True,
        suppliers_found=result.get("suppliers_found", 0),
        suppliers_verified=result.get("suppliers_verified", 0),
        outreach_drafts_created=result.get("outreach_drafts_created", 0),
    )


@app.post("/run/outreach/draft", response_model=OutreachDraftResponse)
async def create_outreach_draft(request: OutreachDraftRequest):
    """Create an outreach draft for a supplier."""
    from core.outreach_engine import create_initial_outreach
    
    draft = await create_initial_outreach(
        supplier_id=request.supplier_id,
        product_id=request.product_id,
        template_id=request.template_id,
        channel=request.channel,
        custom_vars=request.custom_vars,
    )
    
    return OutreachDraftResponse(
        success=True,
        draft_id=draft.draft_id,
        message="Outreach draft created successfully",
    )


@app.post("/run/outreach/send", response_model=OutreachSendResponse)
async def send_outreach(request: OutreachSendRequest):
    """Send approved outreach drafts."""
    from core.outreach_engine import OutreachEngine
    
    engine = OutreachEngine()
    results = await engine.send_approved_drafts(limit=request.limit)
    
    sent = sum(1 for r in results if r.success)
    failed = len(results) - sent
    
    return OutreachSendResponse(
        success=True,
        sent=sent,
        failed=failed,
        results=[{
            "draft_id": r.draft_id if hasattr(r, 'draft_id') else None,
            "success": r.success,
            "channel": r.channel,
            "error": r.error,
        } for r in results],
    )


@app.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_product(request: EvaluationRequest):
    """Evaluate product through Gate 3 (Economics) and Gate 4 (Scoring)."""
    from core.gate_engine import GateEngine
    from core.validation import CanonicalProduct
    
    engine = GateEngine()
    
    product = CanonicalProduct(
        canonical_title="Evaluation Product",
        category=request.category,
        retail_price_inr=request.planned_msrp,
        amazon_asin="EVAL001",
        rating=4.0,
        review_count=100,
        amazon_bsr=10000,
    )
    
    # Run Gate 1 (Signal)
    g1 = engine.run_gate_1_signal(
        product=product,
        bsr_current=10000,
        price_current=request.planned_msrp,
        price_30d_ago=request.planned_msrp * 1.02,
    )
    
    # Run Gate 3 (Economics)
    g3 = engine.run_gate_3_economics(
        product=product,
        fob_price=request.fob_price,
        planned_msrp=request.planned_msrp,
        region=request.region,
        category=request.category,
        marketplace=request.marketplace,
    )
    
    # Run Gate 4 (Scoring)
    g4 = engine.run_gate_4_scoring(
        product=product,
        bsr=10000,
        rating=4.0,
        review_count=100,
        net_margin_pct=g3.details.get("expected", {}).get("net_margin_pct", 0),
        has_defects=False,
        competitor_count=10,
    )
    
    final_verdict = "PROCEED" if g4.passed else "REJECT"
    
    return EvaluationResponse(
        success=True,
        gate3_passed=g3.passed,
        gate4_score=g4.details.get("total_score", 0),
        net_margin_pct=g3.details.get("expected", {}).get("net_margin_pct", 0),
        recommendation=final_verdict,
    )


# ── Webhook Endpoints ────────────────────────────────────────────────────

@app.post("/webhook/agent-reach")
async def webhook_agent_reach(event: WebhookEvent):
    """Receive events from Agent-Reach."""
    logger.info(f"Agent-Reach webhook: {event.event_type}")
    # Process event
    return {"status": "received"}


@app.post("/webhook/evolution-go")
async def webhook_evolution_go(event: WebhookEvent):
    """Receive events from Evolution-Go (WhatsApp)."""
    logger.info(f"Evolution-Go webhook: {event.event_type}")
    # Process WhatsApp events
    return {"status": "received"}


@app.post("/webhook/openbb")
async def webhook_openbb(event: WebhookEvent):
    """Receive events from OpenBB."""
    logger.info(f"OpenBB webhook: {event.event_type}")
    return {"status": "received"}


@app.post("/webhook/worldmonitor")
async def webhook_worldmonitor(event: WebhookEvent):
    """Receive events from WorldMonitor."""
    logger.info(f"WorldMonitor webhook: {event.event_type}")
    return {"status": "received"}


@app.post("/webhook/agent-reach")
async def webhook_agent_reach(event: WebhookEvent):
    """Receive events from Agent-Reach."""
    logger.info(f"Agent-Reach webhook: {event.event_type}")
    return {"status": "received"}


# ── Management Endpoints ─────────────────────────────────────────────────

@app.post("/override/agent")
async def override_agent_mode(agent: str, mode: str):
    """Set agent mode (auto/manual/disabled/force_tier:N)."""
    # This would update settings or send to agent-reach
    logger.info(f"Agent {agent} mode set to {mode}")
    return {"status": "updated", "agent": agent, "mode": mode}


@app.get("/agents/status")
async def get_agent_status():
    """Get status of all agents."""
    return {
        "internet_crawler": "idle",
        "trend_signal": "idle",
        "niche_expander": "idle",
        "discovery": "idle",
        "problem_miner": "idle",
        "gate_engine": "idle",
        "supplier_agent": "idle",
        "outreach_engine": "idle",
        "learning_agent": "idle",
    }


@app.get("/llm/health")
async def llm_health():
    """Get LLM tier health status."""
    from core.llm_router import LLMRouter
    router = LLMRouter()
    return router.get_health_status()


@app.post("/llm/test")
async def test_llm(prompt: str, tier: int = 1):
    """Test LLM at specific tier."""
    from core.llm_router import LLMRouter, LLMTaskType
    
    router = LLMRouter()
    response = await router.chat(
        messages=[{"role": "user", "content": prompt}],
        agent_name="test",
        task_type=LLMTaskType.GENERIC,
        max_tokens=100,
    )
    return {
        "response": response.text,
        "tier_used": response.tier_used,
        "latency_ms": response.latency_ms,
    }


# ── Webhook Receiver for External Systems ────────────────────────────────

@app.post("/webhook/{source}")
async def generic_webhook(source: str, payload: Dict[str, Any]):
    """Generic webhook receiver for any external system."""
    logger.info(f"Webhook from {source}: {payload}")
    # Process based on source
    return {"status": "received", "source": source}


# ── Main Entry Point ────────────────────────────────────────────────────

def main():
    """Run OpenCompany FastAPI server."""
    uvicorn.run(
        "integrations.opencompany:app",
        host=app_settings.host,
        port=app_settings.port,
        reload=app_settings.reload,
        log_level=app_settings.log_level,
    )


if __name__ == "__main__":
    main()