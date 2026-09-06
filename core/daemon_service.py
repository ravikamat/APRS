"""
core/daemon_service.py — 24/7 Autonomous Background Daemon & Agent Controller for APRS V7.

Provides a thread-safe singleton background service that:
1. Runs continuous multi-agent research cycles (crawling, discovery, mining, gates, suppliers, learning)
2. Exposes live status, real-time counters, and recent log streams to Streamlit / Web UI
3. Allows interactive controls: Start, Pause, Resume, Force Single Cycle, and On-Demand Agent Dispatch
4. Allows manual gate restart and re-evaluation for specific products
"""
import os
import sys
import time
import logging
import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.database import (
    init_db, get_connection, get_all_products, get_gate_status,
    reset_product_gates, update_gate_status, get_dynamic_niches,
    get_live_table_counts, log_swarm_audit, get_3star_reviews
)
from core.agent_orchestrator import AgentOrchestrator, OrchestratorMode, AgentState, AgentRunResult, AgentConfig

logger = logging.getLogger("aprs.daemon")


class DaemonService:
    """
    Singleton 24/7 Background Daemon Service.
    Wraps AgentOrchestrator with thread-safe controls and live telemetry for Web UI.
    """
    _instance: Optional["DaemonService"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DaemonService, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, interval_seconds: int = 3600):
        if self._initialized:
            return
        
        self.interval_seconds = interval_seconds
        self.orchestrator = AgentOrchestrator(mode=OrchestratorMode.CONTINUOUS)
        self.thread: Optional[threading.Thread] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        
        self.is_running = False
        self.is_paused = False
        self.current_agent = "idle"
        self.current_niche = "all niches"
        self.cycle_count = 0
        self.total_discovered_session = 0
        self.total_evaluated_session = 0
        self.total_passed_session = 0
        self.start_time: Optional[float] = None
        
        # Telemetry for each agent
        self.agent_telemetry: Dict[str, Dict[str, Any]] = {
            agent: {
                "runs": 0,
                "successes": 0,
                "failures": 0,
                "items_processed": 0,
                "items_created": 0,
                "last_run": None,
                "last_duration_ms": 0,
                "last_error": None,
            }
            for agent in self.orchestrator.AGENT_ORDER
        }
        
        self.recent_logs: List[str] = []
        self._max_logs = 100
        
        self._stop_requested = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Unpaused by default
        
        self._initialized = True
        self.log("DaemonService initialized. Ready for 24/7 autonomous operation.")

    def log(self, message: str, level: str = "INFO"):
        """Append log message with timestamp."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        entry = f"[{timestamp}] [{level}] {message}"
        self.recent_logs.append(entry)
        if len(self.recent_logs) > self._max_logs:
            self.recent_logs.pop(0)
        
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

    def start(self):
        """Start the background daemon thread."""
        with self._lock:
            if self.is_running and self.thread and self.thread.is_alive():
                self.log("Daemon already running.", "DEBUG")
                return
            
            self._stop_requested.clear()
            self._pause_event.set()
            self.is_running = True
            self.is_paused = False
            self.start_time = time.time()
            
            self.thread = threading.Thread(
                target=self._run_thread_entry,
                name="APRS-24x7-Daemon",
                daemon=True
            )
            self.thread.start()
            self.log("🚀 24/7 Background Autonomous Daemon started.")

    def pause(self):
        """Pause continuous execution."""
        self.is_paused = True
        self._pause_event.clear()
        self.log("⏸️ Background daemon paused.")

    def resume(self):
        """Resume continuous execution."""
        self.is_paused = False
        self._pause_event.set()
        self.log("▶️ Background daemon resumed.")

    def stop(self):
        """Stop the background daemon thread cleanly."""
        self.is_running = False
        self.is_paused = False
        self._stop_requested.set()
        self._pause_event.set()
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.log("⏹️ Background daemon stopped.")

    def _run_thread_entry(self):
        """Thread worker loop."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main_orchestration_loop())
        except Exception as e:
            self.log(f"Daemon fatal thread error: {e}", "ERROR")
        finally:
            self.loop.close()
            self.is_running = False

    async def _main_orchestration_loop(self):
        """Continuous background execution loop."""
        while not self._stop_requested.is_set():
            # Respect pause state
            while self.is_paused and not self._stop_requested.is_set():
                await asyncio.sleep(1.0)
            
            if self._stop_requested.is_set():
                break
            
            try:
                await self._execute_full_cycle()
            except Exception as e:
                self.log(f"Cycle execution error: {e}", "ERROR")
            
            # Wait for next cycle interval with periodic check for stop/pause
            elapsed_wait = 0
            while elapsed_wait < self.interval_seconds and not self._stop_requested.is_set():
                await asyncio.sleep(2.0)
                elapsed_wait += 2.0

    async def _execute_full_cycle(self):
        """Execute one complete cycle through all agents in order."""
        self.cycle_count += 1
        self.log(f"--- Starting Autonomous Research Cycle #{self.cycle_count} ---")
        
        for agent_name in self.orchestrator.AGENT_ORDER:
            if self._stop_requested.is_set():
                break
            
            # Wait if paused mid-cycle
            while self.is_paused and not self._stop_requested.is_set():
                await asyncio.sleep(1.0)
            
            config = self.orchestrator._agent_configs.get(agent_name)
            if not config or not config.enabled:
                continue
            
            self.current_agent = agent_name
            self.log(f"⚡ Running Agent: {agent_name.replace('_', ' ').title()}...")
            
            t0 = time.time()
            try:
                result = await self.orchestrator.run_agent(agent_name)
                duration_ms = int((time.time() - t0) * 1000)
                
                # Update telemetry
                stats = self.agent_telemetry[agent_name]
                stats["runs"] += 1
                stats["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                stats["last_duration_ms"] = duration_ms
                
                if result.state == AgentState.COMPLETED:
                    stats["successes"] += 1
                    stats["items_processed"] += result.items_processed
                    stats["items_created"] += result.items_created
                    stats["last_error"] = None
                    self.log(f"✅ {agent_name} completed in {duration_ms}ms (processed: {result.items_processed}, created: {result.items_created})")
                else:
                    stats["failures"] += 1
                    stats["last_error"] = result.error
                    self.log(f"⚠️ {agent_name} status: {result.state.value} — {result.error}", "WARNING")
            
            except Exception as e:
                duration_ms = int((time.time() - t0) * 1000)
                stats = self.agent_telemetry[agent_name]
                stats["runs"] += 1
                stats["failures"] += 1
                stats["last_error"] = str(e)
                self.log(f"❌ {agent_name} failed: {e}", "ERROR")

        self.current_agent = "idle"
        self.log(f"🏁 Cycle #{self.cycle_count} completed.")

    def trigger_cycle_now(self):
        """Trigger an immediate single cycle run."""
        def _run_single():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._execute_full_cycle())
            finally:
                loop.close()

        t = threading.Thread(target=_run_single, daemon=True)
        t.start()
        self.log("⚡ Immediate cycle triggered by user.")

    def run_agent_on_demand(self, agent_name: str) -> Dict[str, Any]:
        """Dispatch a single agent on-demand from the Web UI / Supervisor."""
        if agent_name not in self.orchestrator.AGENT_ORDER:
            return {"error": f"Unknown agent: {agent_name}"}

        self.log(f"🎯 On-Demand dispatch requested for: {agent_name}")
        
        async def _run():
            return await self.orchestrator.run_agent(agent_name)

        # Run synchronously or in temporary loop
        temp_loop = asyncio.new_event_loop()
        try:
            res: AgentRunResult = temp_loop.run_until_complete(_run())
            stats = self.agent_telemetry[agent_name]
            stats["runs"] += 1
            stats["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            stats["last_duration_ms"] = res.duration_ms
            if res.state == AgentState.COMPLETED:
                stats["successes"] += 1
                stats["items_processed"] += res.items_processed
                stats["items_created"] += res.items_created
                self.log(f"✅ On-demand {agent_name} succeeded: {res.items_created} items created.")
                return {"status": "success", "result": res.__dict__}
            else:
                stats["failures"] += 1
                stats["last_error"] = res.error
                self.log(f"⚠️ On-demand {agent_name} did not complete: {res.error}", "WARNING")
                return {"status": "failed", "error": res.error}
        except Exception as e:
            self.log(f"❌ On-demand {agent_name} execution error: {e}", "ERROR")
            return {"status": "error", "error": str(e)}
        finally:
            temp_loop.close()

    def rerun_product_gates(self, product_id: str) -> Dict[str, Any]:
        """Reset gates and re-evaluate a product through GateEngine."""
        self.log(f"🔄 Manual gate re-evaluation requested for product: {product_id}")
        
        # 1. Reset gates in DB
        reset_product_gates(product_id)
        
        # 2. Fetch product details
        conn = get_connection()
        cur = conn.execute("SELECT * FROM master_products WHERE product_id = ?", (product_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return {"status": "error", "error": f"Product {product_id} not found in database."}
        
        p = dict(row)
        
        # 3. Build CanonicalProduct
        from core.validation import CanonicalProduct
        from core.gate_engine import GateEngine
        
        canonical = CanonicalProduct(
            canonical_title=p.get("name", "Unknown Product"),
            category=p.get("category", "General"),
            retail_price_inr=float(p.get("planned_msrp") or 999.0),
            amazon_asin=p.get("amazon_asin"),
            rating=float(p.get("rating") or 4.0),
            review_count=int(p.get("review_count") or 100),
            amazon_bsr=int(p.get("bsr_rank") or 15000),
            factory_fob_inr=float(p.get("factory_cogs") or (float(p.get("planned_msrp") or 999.0) * 0.25)),
        )
        canonical.product_id = product_id
        canonical.region = p.get("region", "India")
        
        # 4. Run through GateEngine
        engine = GateEngine()
        
        # Fetch 3-star reviews from database
        reviews_3star = get_3star_reviews(product_id, "amazon", 20)
        
        async def _eval():
            return await engine.run_full_pipeline(
                product=canonical,
                bsr_current=canonical.amazon_bsr or 15000,
                price_current=canonical.retail_price_inr,
                reviews_3star=reviews_3star,
                fob_price=canonical.factory_fob_inr or (canonical.retail_price_inr * 0.25),
                planned_msrp=canonical.retail_price_inr,
                region=canonical.region,
                category=canonical.category,
                marketplace="amazon",
                competitor_count=8,
            )
        
        temp_loop = asyncio.new_event_loop()
        try:
            result = temp_loop.run_until_complete(_eval())
            self.log(f"✅ Re-evaluated {product_id}: Verdict = {result.final_verdict} (Gates passed: {len(result.gate_results)})")
            return {
                "status": "success",
                "verdict": result.final_verdict,
                "gate_results": [g.__dict__ for g in result.gate_results],
            }
        except Exception as e:
            self.log(f"❌ Gate re-evaluation failed for {product_id}: {e}", "ERROR")
            return {"status": "error", "error": str(e)}
        finally:
            temp_loop.close()

    def get_status(self) -> Dict[str, Any]:
        """Return comprehensive status dictionary for web dashboard."""
        uptime = int(time.time() - self.start_time) if (self.start_time and self.is_running) else 0
        return {
            "running": self.is_running,
            "is_paused": self.is_paused,
            "current_agent": self.current_agent,
            "current_niche": self.current_niche,
            "cycle_count": self.cycle_count,
            "total_discovered_session": self.total_discovered_session,
            "total_passed_session": self.total_passed_session,
            "uptime_seconds": uptime,
            "agent_states": {k: v.value for k, v in self.orchestrator._agent_states.items()},
            "agent_telemetry": self.agent_telemetry,
            "recent_logs": list(self.recent_logs),
        }

    def get_live_table_counts(self) -> Dict[str, int]:
        """Get live row counts for all tables — used by dashboard header."""
        return get_live_table_counts()

    def stream_log_tail(self, n: int = 50) -> List[str]:
        """Return last N log lines for live log popover."""
        return list(self.recent_logs[-n:])

    def set_agent_mode(self, agent_name: str, mode: str) -> Dict[str, Any]:
        """Set agent execution mode (AUTO, MANUAL, DISABLED, FORCE_TIER:1-5)."""
        if agent_name not in self.orchestrator._agent_configs:
            return {"error": f"Unknown agent: {agent_name}"}
        
        valid_modes = ["auto", "manual", "disabled", "force_tier:1", "force_tier:2", "force_tier:3", "force_tier:4", "force_tier:5"]
        if mode not in valid_modes:
            return {"error": f"Invalid mode: {mode}. Valid: {valid_modes}"}
        
        config = self.orchestrator._agent_configs[agent_name]
        config.mode = mode
        self.log(f"🔧 Agent {agent_name} mode changed to {mode}")
        return {"status": "success", "agent": agent_name, "mode": mode}

    def get_agent_modes(self) -> Dict[str, str]:
        """Get current mode for all agents."""
        return {name: config.mode for name, config in self.orchestrator._agent_configs.items()}

    def supervisor_command(self, instruction: str) -> Dict[str, Any]:
        """Send natural language command to Main AI Supervisor (NIM 550B).
        
        The supervisor parses the instruction and returns a dispatch plan:
        {
            "reasoning": "User wants to find suppliers for copper cookware",
            "dispatch": [
                {"agent": "supplier_agent", "params": {"product_id": "abc123"}},
                {"agent": "discovery", "params": {"keywords": ["copper cookware"], "region": "India"}}
            ]
        }
        Then executes each dispatch.
        """
        self.log(f"🧠 Supervisor command received: {instruction}")
        
        try:
            from core.supervisor_ai import SupervisorAI
            import asyncio
            
            supervisor = SupervisorAI()
            
            # Run with timeout - if it takes too long, use fallback
            async def _run_with_timeout():
                return await asyncio.wait_for(supervisor.parse_command_async(instruction), timeout=10.0)
            
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            plan = loop.run_until_complete(_run_with_timeout())
            
            if not plan or "dispatch" not in plan:
                return {"status": "error", "error": "Supervisor returned invalid plan"}
            
            results = []
            for dispatch in plan.get("dispatch", []):
                agent = dispatch.get("agent")
                params = dispatch.get("params", {})
                if agent:
                    self.log(f"🎯 Supervisor dispatching: {agent} with {params}")
                    result = self.run_agent_on_demand(agent)
                    results.append({"agent": agent, "params": params, "result": result})
            
            return {
                "status": "success",
                "reasoning": plan.get("reasoning", ""),
                "dispatches": results
            }
        except asyncio.TimeoutError:
            self.log("⚠️ Supervisor timed out, using fallback", "WARNING")
            return self._supervisor_fallback(instruction)
        except Exception as e:
            self.log(f"❌ Supervisor command failed: {e}", "ERROR")
            return self._supervisor_fallback(instruction)

    def _supervisor_fallback(self, instruction: str) -> Dict[str, Any]:
        """Keyword-based fallback when Supervisor AI is unavailable."""
        from core.supervisor_ai import SupervisorAI
        supervisor = SupervisorAI()
        plan = supervisor._fallback_plan(instruction)
        
        results = []
        for dispatch in plan.get("dispatch", []):
            agent = dispatch.get("agent")
            params = dispatch.get("params", {})
            if agent:
                self.log(f"🎯 Fallback dispatching: {agent} with {params}")
                result = self.run_agent_on_demand(agent)
                results.append({"agent": agent, "params": params, "result": result})
        
        return {
            "status": "success",
            "reasoning": plan.get("reasoning", "") + " (fallback mode)",
            "dispatches": results
        }


# Global singleton instance for Web UI and scripts
daemon_controller = DaemonService()
