"""
core/agent_orchestrator.py — Deterministic Agent Orchestrator for APRS V7.

Schedules all agents in the correct order, manages dependencies,
and coordinates the autonomous pipeline. No LLM calls — purely deterministic.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Awaitable

import sys

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from core.database import (
    init_db, get_all_products, get_dynamic_niches, get_seed_keywords,
    get_dynamic_niches, get_seed_keywords, update_niche_scan,
    record_dynamic_niche, record_seed_keyword,
    get_active_trend_signals, get_supplier_profiles_for_product,
    get_launchpad_items, add_to_launchpad,
    _db_write_lock,
)
from core.validation import RawProduct, CanonicalProduct, ProductMatcher, ValidationPipeline
from core.gate_engine import GateEngine, PipelineResult
from core.rule_engine import create_rule_engine
from core.economics_engine import Comprehensive15FactorEconomics
from core.pipeline import V6Pipeline, PipelineConfig, run_full_pipeline
from core.llm_router import LLMRouter, LLMTaskType
from core.nim_client import get_nim_client
from core.rule_engine import create_rule_engine
from core.contracts import REGISTRY, verify_agent_output, record_agent_health, run_with_contract
from tools.discovery_engine import DiscoveryEngine
from tools.trend_scout.trend_aggregator import OpenWebTrendScout
from tools.web_agent import WebAgent
from core.outreach_engine import OutreachEngine, create_initial_outreach
from core.maintenance import MaintenanceManager
from core.winner_score import WinnerScoreComputer
from agents.ai_scout import AIScoutAgent, run_ai_scout

logger = logging.getLogger("aprs.orchestrator")


class AgentState(str, Enum):
    """Agent execution state."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    PAUSED = "PAUSED"


class OrchestratorMode(str, Enum):
    """Orchestrator execution mode."""
    CONTINUOUS = "continuous"      # Run forever, cycling through agents
    SINGLE_CYCLE = "single_cycle"  # Run one full cycle then stop
    MANUAL = "manual"              # Wait for explicit triggers


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    name: str
    enabled: bool = True
    mode: str = "auto"  # auto | manual | disabled | force_tier:1..5
    interval_seconds: int = 3600  # Default 1 hour
    max_concurrent: int = 1
    timeout_seconds: int = 300
    retry_count: int = 3
    dependencies: List[str] = field(default_factory=list)  # Agent names that must complete first


@dataclass
class AgentRunResult:
    """Result of a single agent run."""
    agent_name: str
    state: AgentState
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: int = 0
    items_processed: int = 0
    items_created: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentOrchestrator:
    """
    Deterministic Agent Orchestrator for APRS V7.
    
    Coordinates 10 agents in the correct dependency order:
    1. Internet Crawler → Trend Signal → Niche Expander → Discovery
    2. Problem Miner → Gate Engine → Supplier Agent → Outreach Engine
    3. Learning Agent (weekly)
    
    No LLM calls in orchestration logic — purely deterministic scheduling.
    """
    
    # Agent execution order (respecting dependencies)
    AGENT_ORDER = [
        "strategy_planner",      # Weekly: decides WHERE to hunt
        "ai_scout",              # Weekly: discovers new sources, marketplaces, communities
        "internet_crawler",      # Continuous: discovers new sources
        "trend_signal",          # Continuous: aggregates trend signals
        "demand_sense",          # Daily: computes real demand proxies
        "competition_xray",      # Daily: competitive analysis per category
        "niche_expander",        # Daily: expands niches from directives
        "discovery",             # 12h: scrapes marketplaces for products
        "problem_miner",         # Daily: mines defects from reviews
        "gate_engine",           # Daily: runs 5-gate validation
        "supplier_agent",        # Daily: finds/verifies suppliers
        "outreach_engine",       # 12h: sends approved outreach
        "winner_score",          # Daily: computes leaderboard rankings
        "maintenance",           # Daily: TTL cleanup, VACUUM, backup
        "weight_tuner",          # Quarterly: optimizes winner score weights
        "learning_agent",        # Weekly: learns from outcomes
    ]
    
    def __init__(
        self,
        mode: OrchestratorMode = OrchestratorMode.SINGLE_CYCLE,
        max_cycles: Optional[int] = None,
    ):
        self.mode = mode
        self.max_cycles = max_cycles
        self.cycle_count = 0
        self.running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self._agent_states: Dict[str, AgentState] = {name: AgentState.IDLE for name in self.AGENT_ORDER}
        self._agent_configs: Dict[str, AgentConfig] = self._default_configs()
        self._run_history: List[AgentRunResult] = []
        self._cycle_callbacks: List[Callable[[int], Awaitable[None]]] = []
        self._shutdown_event = asyncio.Event()
        
        # Initialize database
        init_db()
        
        # Core components (lazy init)
        self._gate_engine: Optional[GateEngine] = None
        self._pipeline: Optional[V6Pipeline] = None
        self._llm_router: Optional[LLMRouter] = None
        self._outreach_engine: Optional[OutreachEngine] = None
        
    def _default_configs(self) -> Dict[str, AgentConfig]:
        """Default agent configurations."""
        return {
            "strategy_planner": AgentConfig(
                name="strategy_planner",
                enabled=True,
                interval_seconds=604800,  # Weekly
                max_concurrent=1,
                timeout_seconds=600,
            ),
            "internet_crawler": AgentConfig(
                name="internet_crawler",
                enabled=True,
                interval_seconds=7200,  # Every 2 hours
                max_concurrent=2,
                timeout_seconds=600,
                dependencies=["strategy_planner"],
            ),
            "trend_signal": AgentConfig(
                name="trend_signal",
                enabled=True,
                interval_seconds=7200,
                max_concurrent=1,
                timeout_seconds=300,
                dependencies=["internet_crawler"],
            ),
            "demand_sense": AgentConfig(
                name="demand_sense",
                enabled=True,
                interval_seconds=86400,  # Daily
                max_concurrent=1,
                timeout_seconds=300,
                dependencies=["trend_signal"],
            ),
            "competition_xray": AgentConfig(
                name="competition_xray",
                enabled=True,
                interval_seconds=86400,  # Daily
                max_concurrent=1,
                timeout_seconds=300,
                dependencies=["demand_sense"],
            ),
            "niche_expander": AgentConfig(
                name="niche_expander",
                enabled=True,
                interval_seconds=86400,  # Daily
                max_concurrent=1,
                timeout_seconds=120,
                dependencies=["competition_xray"],
            ),
            "discovery": AgentConfig(
                name="discovery",
                enabled=True,
                interval_seconds=43200,  # Every 12 hours
                max_concurrent=1,
                timeout_seconds=600,
                dependencies=["niche_expander"],
            ),
            "problem_miner": AgentConfig(
                name="problem_miner",
                enabled=True,
                interval_seconds=86400,  # Daily
                max_concurrent=2,
                timeout_seconds=600,
                dependencies=["discovery"],
            ),
            "gate_engine": AgentConfig(
                name="gate_engine",
                enabled=True,
                interval_seconds=86400,  # Daily
                max_concurrent=5,
                timeout_seconds=300,
                dependencies=["problem_miner"],
            ),
            "supplier_agent": AgentConfig(
                name="supplier_agent",
                enabled=True,
                interval_seconds=86400,  # Daily
                max_concurrent=2,
                timeout_seconds=600,
                dependencies=["gate_engine"],
            ),
            "outreach_engine": AgentConfig(
                name="outreach_engine",
                enabled=True,
                interval_seconds=43200,  # Every 12 hours
                max_concurrent=1,
                timeout_seconds=180,
                dependencies=["supplier_agent"],
            ),
            "winner_score": AgentConfig(
                name="winner_score",
                enabled=True,
                interval_seconds=86400,  # Daily
                max_concurrent=1,
                timeout_seconds=180,
                dependencies=["outreach_engine"],
            ),
            "maintenance": AgentConfig(
                name="maintenance",
                enabled=True,
                interval_seconds=86400,  # Daily
                max_concurrent=1,
                timeout_seconds=600,
                dependencies=["winner_score"],
            ),
            "weight_tuner": AgentConfig(
                name="weight_tuner",
                enabled=True,
                interval_seconds=2592000,  # Quarterly (30 days)
                max_concurrent=1,
                timeout_seconds=600,
                dependencies=["maintenance"],
            ),
            "learning_agent": AgentConfig(
                name="learning_agent",
                enabled=True,
                interval_seconds=604800,  # Weekly
                max_concurrent=1,
                timeout_seconds=600,
                dependencies=["weight_tuner"],
            ),
            "ai_scout": AgentConfig(
                name="ai_scout",
                enabled=True,
                interval_seconds=86400,  # Daily (24 hours)
                max_concurrent=1,
                timeout_seconds=3600,  # 60 min for 10x discovery
                dependencies=["strategy_planner"],
            ),
        }
    
    @property
    def gate_engine(self) -> GateEngine:
        if self._gate_engine is None:
            self._gate_engine = GateEngine()
        return self._gate_engine
    
    @property
    def pipeline(self) -> V6Pipeline:
        if self._pipeline is None:
            self._pipeline = V6Pipeline()
        return self._pipeline
    
    @property
    def llm_router(self) -> LLMRouter:
        if self._llm_router is None:
            self._llm_router = LLMRouter()
        return self._llm_router
    
    @property
    def outreach_engine(self) -> OutreachEngine:
        if self._outreach_engine is None:
            self._outreach_engine = OutreachEngine()
        return self._outreach_engine
    
    def get_agent_state(self, agent_name: str) -> AgentState:
        """Get current state of an agent."""
        return self._agent_states.get(agent_name, AgentState.IDLE)
    
    def is_agent_ready(self, agent_name: str) -> bool:
        """Check if agent's dependencies are satisfied."""
        config = self._agent_configs.get(agent_name)
        if not config:
            return False
        
        for dep in config.dependencies:
            dep_state = self._agent_states.get(dep)
            if dep_state != AgentState.COMPLETED and dep_state != AgentState.IDLE:
                return False
        return True

    def set_agent_mode(self, agent_name: str, mode: str):
        """Set agent operation mode (auto, manual, disabled, force_tier:X)."""
        if agent_name in self._agent_configs:
            self._agent_configs[agent_name].mode = mode
            if mode == "disabled":
                self._agent_configs[agent_name].enabled = False
            else:
                self._agent_configs[agent_name].enabled = True
            logger.info(f"Agent '{agent_name}' mode updated to: {mode}")

    def set_agent_enabled(self, agent_name: str, enabled: bool):
        """Enable or disable an agent."""
        if agent_name in self._agent_configs:
            self._agent_configs[agent_name].enabled = enabled
            logger.info(f"Agent '{agent_name}' enabled set to: {enabled}")
    
    async def run_agent(self, agent_name: str) -> AgentRunResult:
        """Run a single agent and return result."""
        config = self._agent_configs.get(agent_name)
        if not config or not config.enabled:
            return AgentRunResult(
                agent_name=agent_name,
                state=AgentState.BLOCKED,
                started_at=datetime.now(timezone.utc),
                error=f"Agent not configured or disabled",
            )
        
        # Check dependencies
        for dep in config.dependencies:
            dep_state = self._agent_states.get(dep)
            if dep_state not in (AgentState.COMPLETED, AgentState.IDLE):
                return AgentRunResult(
                    agent_name=agent_name,
                    state=AgentState.BLOCKED,
                    started_at=datetime.now(timezone.utc),
                    error=f"Dependency '{dep}' not ready (state: {self._agent_states.get(dep)})",
                )
        
        started_at = datetime.now(timezone.utc)
        self._agent_states[agent_name] = AgentState.RUNNING
        logger.info(f"Starting agent: {agent_name}")
        
        # Generate cycle ID for contract tracking
        import uuid
        cycle_id = f"{agent_name}_{started_at.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
        
        # Retry configuration for database locked errors
        max_retries = 3
        base_delay = 0.5  # seconds
        
        for attempt in range(max_retries + 1):
            # Acquire database write lock for the entire agent run to prevent locking issues
            import threading
            db_lock_acquired = False
            try:
                # Acquire database write lock for the entire agent run
                _db_write_lock.acquire()
                db_lock_acquired = True
                
                # Run with timeout AND contract enforcement
                async def _wrapped_execute():
                    return await run_with_contract(agent_name, self._execute_agent, cycle_id, cycle_id)
                
                result = await asyncio.wait_for(
                    _wrapped_execute(),
                    timeout=config.timeout_seconds,
                )
                
                completed_at = datetime.now(timezone.utc)
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)
                
                result = AgentRunResult(
                    agent_name=agent_name,
                    state=AgentState.COMPLETED,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    **result,
                )
                
                self._agent_states[agent_name] = AgentState.COMPLETED
                logger.info(f"Agent {agent_name} completed in {duration_ms}ms (contract verified)")
                return result
                
            except asyncio.TimeoutError:
                completed_at = datetime.now(timezone.utc)
                duration_ms = int((completed_at - started_at).total_seconds() * 1000)
                self._agent_states[agent_name] = AgentState.FAILED
                logger.error(f"Agent {agent_name} timed out after {config.timeout_seconds}s")
                return AgentRunResult(
                    agent_name=agent_name,
                    state=AgentState.FAILED,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    error=f"Timeout after {config.timeout_seconds}s",
                )
            except Exception as e:
                error_str = str(e)
                # Check if it's a database locked error and we should retry
                if "database is locked" in error_str.lower() and attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(f"Agent {agent_name} database locked, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(delay)
                    continue
                # Re-raise for other errors or if max retries exceeded
                raise
            finally:
                # Release database write lock
                if db_lock_acquired:
                    _db_write_lock.release()
        
        # If we exhausted retries for database locked
        completed_at = datetime.now(timezone.utc)
        duration_ms = int((completed_at - started_at).total_seconds() * 1000)
        self._agent_states[agent_name] = AgentState.FAILED
        logger.error(f"Agent {agent_name} failed after {max_retries} retries: database locked")
        return AgentRunResult(
            agent_name=agent_name,
            state=AgentState.FAILED,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            error=f"Database locked after {max_retries} retries",
        )
    
    async def _execute_agent(self, agent_name: str, cycle_id: str = None) -> Dict[str, Any]:
        """Execute the actual agent logic. Returns metadata dict."""
        
        if agent_name == "strategy_planner":
            return await self._run_strategy_planner()
        elif agent_name == "ai_scout":
            return await self._run_ai_scout()
        elif agent_name == "internet_crawler":
            return await self._run_internet_crawler()
        elif agent_name == "trend_signal":
            return await self._run_trend_signal()
        elif agent_name == "demand_sense":
            return await self._run_demand_sense()
        elif agent_name == "competition_xray":
            return await self._run_competition_xray()
        elif agent_name == "niche_expander":
            return await self._run_niche_expander()
        elif agent_name == "discovery":
            return await self._run_discovery()
        elif agent_name == "problem_miner":
            return await self._run_problem_miner()
        elif agent_name == "gate_engine":
            return await self._run_gate_engine()
        elif agent_name == "supplier_agent":
            return await self._run_supplier_agent()
        elif agent_name == "outreach_engine":
            return await self._run_outreach_engine()
        elif agent_name == "winner_score":
            return await self._run_winner_score()
        elif agent_name == "maintenance":
            return await self._run_maintenance()
        elif agent_name == "weight_tuner":
            return await self._run_weight_tuner()
        elif agent_name == "learning_agent":
            return await self._run_learning_agent()
        
        return {"items_processed": 0, "items_created": 0}
    
    # Individual agent implementations
    
    async def _run_internet_crawler(self) -> Dict[str, Any]:
        """Run Internet Crawler Agent — scans 50+ sources for trends."""
        from tools.internet_crawler import InternetCrawler
        
        crawler = InternetCrawler()
        result = await crawler.crawl_cycle()
        
        return {
            "items_processed": result.get("sources_scanned", 0),
            "items_created": result.get("signals_found", 0),
        }
    
    async def _run_trend_signal(self) -> Dict[str, Any]:
        """Run Trend Signal Agent — aggregates Google Trends, Reddit, YouTube."""
        scout = OpenWebTrendScout()
        
        all_signals = []
        for region in ["India", "USA", "GCC_MiddleEast", "Europe", "UK"]:
            signals = scout.harvest_all_active_trends(region=region, max_signals=10)
            all_signals.extend(signals)
        
        return {
            "items_processed": len(all_signals),
            "items_created": len(all_signals),
        }
    
    async def _run_strategy_planner(self) -> Dict[str, Any]:
        """Run Strategy Planner Agent — weekly strategic research planning."""
        from agents.strategy_planner import StrategyPlanner
        
        planner = StrategyPlanner()
        result = planner.run_weekly_planning()
        
        return {
            "items_processed": result.get("directives_generated", 0),
            "items_created": result.get("directives_written", 0),
        }
    
    async def _run_demand_sense(self) -> Dict[str, Any]:
        """Run Demand Sense Agent — computes real demand proxies from marketplace data."""
        from tools.demand_sense import DemandSense
        
        sense = DemandSense()
        
        # Get active niches to analyze
        from core.database import get_dynamic_niches
        niches = get_dynamic_niches(region="India", active_only=True, limit=20)
        
        total_signals = 0
        for niche in niches:
            category = niche.get("category", "")
            if category:
                signals = sense.analyze_category(category, "India", limit=10)
                total_signals += len(signals)
        
        # Also get top opportunities across all categories
        opportunities = sense.get_top_opportunities("India", min_score=60, limit=20)
        
        return {
            "items_processed": len(niches),
            "items_created": total_signals + len(opportunities),
        }
    
    async def _run_competition_xray(self) -> Dict[str, Any]:
        """Run Competition X-Ray Agent — deep competitive analysis per category."""
        from tools.competition_xray import CompetitionXRay
        
        xray = CompetitionXRay()
        
        # Get active niches to analyze
        from core.database import get_dynamic_niches
        niches = get_dynamic_niches(region="India", active_only=True, limit=10)
        
        analyzed = 0
        for niche in niches:
            category = niche.get("category", "")
            if category:
                await xray.analyze_category(category, "India")
                analyzed += 1
        
        return {
            "items_processed": analyzed,
            "items_created": analyzed,
        }
    
    async def _run_niche_expander(self) -> Dict[str, Any]:
        """Run Niche Expander Agent — expands dynamic niches from trend signals."""
        from tools.niche_expander import NicheExpander
        
        expander = NicheExpander()
        result = await expander.expand_from_signals()
        
        return {
            "items_processed": result.get("niches_evaluated", 0),
            "items_created": result.get("niches_added", 0),
        }
    
    async def _run_discovery(self) -> Dict[str, Any]:
        """Run Discovery Agent — multi-marketplace product discovery."""
        config = PipelineConfig(
            region="India",
            max_niches=settings.batch_niche_limit,
            max_candidates_per_niche=settings.batch_max_candidates,
            max_pages=settings.batch_max_pages,
        )
        result = await run_full_pipeline(config)
        
        return {
            "items_processed": len(result.get("canonical_products", [])),
            "items_created": result.get("total_canonical_products", 0),
        }
    
    async def _run_problem_miner(self) -> Dict[str, Any]:
        """Run Problem Miner Agent — extracts defects from reviews/Q&A."""
        from tools.problem_miner import ProblemMiner
        
        miner = ProblemMiner()
        result = await miner.mine_batch()
        
        return {
            "items_processed": result.get("products_analyzed", 0),
            "items_created": result.get("opportunities_found", 0),
        }
    
    async def _run_gate_engine(self) -> Dict[str, Any]:
        """Run Gate Engine Agent — executes 4-gate pipeline on pending products."""
        from core.gate_engine import GateEngine
        from core.database import get_3star_reviews, get_connection
        
        engine = GateEngine()
        pending = await self._get_pending_products_for_gates()
        
        processed = 0
        passed = 0
        
        for product in pending[:20]:  # Limit per run
            product_id = product.get("product_id", "")
            if not product_id:
                logger.warning("Skipping product with empty product_id")
                continue
            
            # Verify product still exists in master_products to avoid FK constraint errors
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM master_products WHERE product_id = ? AND COALESCE(is_deleted, 0) = 0", (product_id,))
                exists = cur.fetchone() is not None
                conn.close()
                if not exists:
                    logger.warning(f"Product {product_id} no longer exists in master_products, skipping")
                    continue
            except Exception as e:
                logger.warning(f"Failed to verify product {product_id} existence: {e}")
            
            reviews_3star = get_3star_reviews(product_id, "amazon", 20) if product_id else []
            
            try:
                result = await engine.run_full_pipeline(
                    product=product,
                    bsr_current=product.get("amazon_bsr", 50000),
                    price_current=product.get("planned_msrp", 0),
                    reviews_3star=reviews_3star,
                    fob_price=product.get("factory_fob_inr") or product.get("planned_msrp", 0) * 0.25,
                    planned_msrp=product.get("planned_msrp", 0),
                    region=product.get("region", "India"),
                    category=product.get("category", "General"),
                    marketplace="amazon",
                    competitor_count=10,
                )
                
                if result.final_verdict == "PROCEED":
                    passed += 1
                processed += 1
                
            except Exception as e:
                logger.error(f"Gate engine failed for product {product_id}: {e}")
                # Continue with other products instead of failing entire agent
                continue
        
        return {"items_processed": processed, "items_created": passed}
    
    async def _get_pending_products_for_gates(self) -> List[CanonicalProduct]:
        """Get products ready for gate processing."""
        from core.database import get_all_products, get_gate_status
        
        products = get_all_products(include_deleted=False)
        pending = []
        
        for p in products:
            gates = get_gate_status(p["product_id"])
            # Check if product is at a gate that needs processing
            current_gate = 1
            for g in sorted(gates, key=lambda x: x.get("gate_number", 0)):
                if g.get("status") not in ("PASS", "OVERRIDDEN"):
                    current_gate = g.get("gate_number", 1)
                    break
            
            # Only process if at gate 1-4 (not completed)
            if current_gate <= 4:
                # Convert to CanonicalProduct
                product = CanonicalProduct(
                    canonical_title=p["name"],
                    category=p.get("category", "General"),
                    retail_price_inr=p.get("planned_msrp", 0),
                    amazon_asin=p.get("amazon_asin"),
                    rating=p.get("rating", 0),
                    review_count=p.get("review_count", 0),
                    amazon_bsr=p.get("bsr_rank"),
                    factory_fob_inr=p.get("factory_cogs"),
                )
                product.product_id = p["product_id"]
                product.region = p.get("region", "India")
                pending.append(product)
        
        return pending
    
    async def _run_supplier_agent(self) -> Dict[str, Any]:
        """Run Supplier Agent — finds and verifies suppliers for PROCEED products."""
        from tools.supplier_agent import SupplierAgent
        
        agent = SupplierAgent()
        result = await agent.run_batch()
        
        return {
            "items_processed": result.get("suppliers_found", 0),
            "items_created": result.get("suppliers_verified", 0),
        }
    
    async def _run_outreach_engine(self) -> Dict[str, Any]:
        """Run Outreach Engine — sends approved drafts."""
        engine = OutreachEngine()
        results = await engine.send_approved_drafts(limit=50)
        
        sent = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        
        return {
            "items_processed": len(results),
            "items_created": sent,
        }
    
    async def _run_winner_score(self) -> Dict[str, Any]:
        """Run Winner Score Agent — nightly leaderboard computation."""
        from core.winner_score import WinnerScoreComputer
        
        computer = WinnerScoreComputer()
        result = computer.update_all_scores()
        
        return {
            "items_processed": result.get("updated", 0),
            "items_created": result.get("updated", 0),
        }
    
    async def _run_maintenance(self) -> Dict[str, Any]:
        """Run Maintenance Agent — TTL cleanup, VACUUM, backup."""
        from core.maintenance import MaintenanceManager
        
        manager = MaintenanceManager()
        result = manager.run_full_maintenance()
        
        total_cleaned = sum(result.get("ttl_cleanup", {}).values())
        
        return {
            "items_processed": total_cleaned,
            "items_created": 1 if result.get("backup") else 0,
        }
    
    async def _run_weight_tuner(self) -> Dict[str, Any]:
        """Run Weight Tuner Agent — quarterly winner score weight optimization."""
        from core.weight_tuner import WeightTuner
        
        tuner = WeightTuner()
        proposal = tuner.propose_weight_changes()
        
        if proposal:
            rule_id = tuner.record_proposal(proposal)
            return {
                "items_processed": 1,
                "items_created": 1,
                "proposal": {
                    "rule_id": rule_id,
                    "improvement_pct": proposal.improvement_pct,
                    "proposed_weights": proposal.proposed_weights,
                },
            }
        
        return {
            "items_processed": 0,
            "items_created": 0,
        }
    
    async def _run_learning_agent(self) -> Dict[str, Any]:
        """Run Learning Agent — weekly synthesis and rule generation."""
        from core.learning_engine import LearningEngine
        
        engine = LearningEngine()
        result = await engine.weekly_synthesis()
        
        return {
            "items_processed": result.get("rules_generated", 0),
            "items_created": result.get("rules_added", 0),
        }
    
    async def _run_ai_scout(self) -> Dict[str, Any]:
        """Run AI Scout Agent — daily autonomous website/platform discovery (10x volume)."""
        from agents.ai_scout import run_ai_scout
        
        result = await run_ai_scout(region="India")
        
        return {
            "items_processed": result.get("total_new", 0),
            "items_created": result.get("total_new", 0),
        }
    
    # Orchestration loop
    
    async def run_cycle(self) -> List[AgentRunResult]:
        """Run one complete orchestration cycle."""
        logger.info(f"Starting orchestration cycle #{self.cycle_count + 1}")
        
        self.cycle_count += 1
        cycle_results = []
        
        for agent_name in self.AGENT_ORDER:
            if not self._agent_configs[agent_name].enabled:
                logger.info(f"Skipping disabled agent: {agent_name}")
                continue
            
            if not self.is_agent_ready(agent_name):
                logger.info(f"Skipping {agent_name} — dependencies not met")
                continue
            
            result = await self.run_agent(agent_name)
            cycle_results.append(result)
            
            # Call cycle callbacks
            for callback in self._cycle_callbacks:
                try:
                    await callback(self.cycle_count)
                except Exception as e:
                    logger.warning(f"Cycle callback failed: {e}")
        
        # Reset agent states for next cycle (in continuous mode)
        if self.mode == OrchestratorMode.CONTINUOUS:
            for name in self.AGENT_ORDER:
                if self._agent_states[name] == AgentState.COMPLETED:
                    self._agent_states[name] = AgentState.IDLE
        
        logger.info(f"Cycle #{self.cycle_count} complete: {len(cycle_results)} agents ran")
        return cycle_results
    
    async def run_continuous(self, interval_seconds: int = 3600):
        """Run orchestrator continuously with specified interval."""
        self.mode = OrchestratorMode.CONTINUOUS
        self.running = True
        
        logger.info("Starting continuous orchestration")
        
        while self.running and not self._shutdown_event.is_set():
            try:
                await self.run_cycle()
                
                if self.max_cycles and self.cycle_count >= self.max_cycles:
                    logger.info(f"Reached max cycles ({self.max_cycles}), stopping")
                    break
                
                # Wait for next cycle
                try:
                    await asyncio.wait_for(self._shutdown_event.wait(), timeout=3600)
                except asyncio.TimeoutError:
                    pass  # Normal - continue to next cycle
                    
            except Exception as e:
                logger.error(f"Orchestrator cycle error: {e}")
                await asyncio.sleep(60)  # Wait before retry
        
        logger.info("Orchestrator stopped")
    
    def add_cycle_callback(self, callback: Callable[[int], Awaitable[None]]):
        """Add callback to run after each cycle."""
        self._cycle_callbacks.append(callback)
    
    def stop(self):
        """Signal orchestrator to stop."""
        self.running = False
        self._shutdown_event.set()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "mode": self.mode.value,
            "cycle_count": self.cycle_count,
            "running": self.running,
            "agent_states": {k: v.value for k, v in self._agent_states.items()},
            "cycle_history_count": len(self._run_history),
        }
    
    def get_agent_history(self, agent_name: str = None, limit: int = 50) -> List[AgentRunResult]:
        """Get run history for agent(s)."""
        if agent_name:
            return [r for r in self._run_history if r.agent_name == agent_name][-limit:]
        return self._run_history[-limit:]


# Global singleton
_orchestrator: Optional[AgentOrchestrator] = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator


# Convenience function for CLI
async def run_orchestrator_cycle():
    """Run a single orchestration cycle."""
    orchestrator = get_orchestrator()
    return await orchestrator.run_cycle()


if __name__ == "__main__":
    async def test():
        orchestrator = AgentOrchestrator(mode=OrchestratorMode.SINGLE_CYCLE)
        results = await orchestrator.run_cycle()
        
        print(f"\nOrchestration Cycle Complete:")
        for r in results:
            status_icon = "✅" if r.state == AgentState.COMPLETED else "❌" if r.state == AgentState.FAILED else "⏭️"
            print(f"  {status_icon} {r.agent_name}: {r.state.value} ({r.duration_ms}ms, {r.items_created} created)")
        
        print(f"\nOrchestrator Status: {orchestrator.get_status()}")
    
    asyncio.run(test())