#!/usr/bin/env python3
"""
APRS V7 — 18+ Hour Continuous Autonomous Daemon Runner

Runs the full autonomous research pipeline continuously for extended periods.
Handles errors gracefully, logs everything to database, and provides monitoring.

Usage:
    python run_18hr_daemon.py [--hours 18] [--interval 3600] [--config config.yaml]

Features:
- Continuous cycles with configurable interval
- Automatic error recovery and retry
- Database health monitoring
- Progress tracking and statistics
- Graceful shutdown on Ctrl+C
- Real-time status logging
"""

import asyncio
import signal
import sys
import time
import logging
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.agent_orchestrator import AgentOrchestrator, OrchestratorMode, AgentState
from core.daemon_service import DaemonService
from core.database import init_db, get_connection, get_live_table_counts
from config.settings import settings

# ── Logging Setup ──────────────────────────────────────────────────────────────
LOG_DIR = _ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

log_file = LOG_DIR / f"daemon_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s — %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Set specific loggers
logging.getLogger("aprs.orchestrator").setLevel(logging.INFO)
logging.getLogger("aprs.daemon").setLevel(logging.INFO)
logging.getLogger("aprs.contracts").setLevel(logging.WARNING)  # Reduce noise
logging.getLogger("core.llm_router").setLevel(logging.INFO)
logging.getLogger("core.database").setLevel(logging.WARNING)

logger = logging.getLogger("aprs.runner")


class ContinuousRunner:
    """Manages continuous daemon execution with monitoring and recovery."""
    
    def __init__(
        self,
        target_hours: float = 18.0,
        cycle_interval: int = 3600,
        max_cycles: Optional[int] = None,
    ):
        self.target_hours = target_hours
        self.cycle_interval = cycle_interval
        self.max_cycles = max_cycles
        
        self.orchestrator = AgentOrchestrator(mode=OrchestratorMode.CONTINUOUS)
        self.daemon = DaemonService(interval_seconds=cycle_interval)
        
        self.start_time: Optional[float] = None
        self.cycles_completed = 0
        self.total_agents_run = 0
        self.total_agents_failed = 0
        self.total_items_created = 0
        self.last_cycle_time = 0
        self.running = False
        self.shutdown_requested = False
        
        # Statistics
        self.cycle_stats = []
        self.agent_failure_counts = {}
        
    async def initialize(self):
        """Initialize database and components."""
        logger.info("=" * 70)
        logger.info(f"APRS V7 Continuous Runner — Target: {self.target_hours}h")
        logger.info("=" * 70)
        
        # Initialize database
        init_db()
        logger.info("✅ Database initialized")
        
        # Check Ollama
        try:
            from core.ollama_manager import ensure_ollama_running
            if ensure_ollama_running():
                logger.info("✅ Ollama server ready")
            else:
                logger.warning("⚠️ Ollama server not available - will auto-start on demand")
        except Exception as e:
            logger.warning(f"⚠️ Ollama check failed: {e}")
        
        # Initial table counts
        counts = get_live_table_counts()
        logger.info(f"📊 Initial DB state: {sum(counts.values()):,} rows across {len(counts)} tables")
        for table, count in sorted(counts.items()):
            if count > 0:
                logger.info(f"   {table}: {count:,}")
        
        logger.info(f"⏱️ Cycle interval: {self.cycle_interval}s ({self.cycle_interval/60:.0f} min)")
        logger.info(f"🎯 Target duration: {self.target_hours}h")
        if self.max_cycles:
            logger.info(f"🔄 Max cycles: {self.max_cycles}")
        
    async def run_cycle_with_monitoring(self, cycle_num: int) -> dict:
        """Run a single cycle with full monitoring and error handling."""
        cycle_start = time.time()
        logger.info(f"\n{'='*70}")
        logger.info(f"🔄 CYCLE #{cycle_num} STARTED at {datetime.now().strftime('%H:%M:%S')}")
        logger.info(f"{'='*70}")
        
        cycle_data = {
            "cycle_num": cycle_num,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "agents": [],
            "success": False,
            "error": None,
        }
        
        try:
            # Run the cycle
            results = await self.orchestrator.run_cycle()
            
            cycle_duration = time.time() - cycle_start
            cycle_data["duration_sec"] = round(cycle_duration, 1)
            cycle_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            
            # Analyze results
            agents_run = 0
            agents_succeeded = 0
            agents_failed = 0
            agents_blocked = 0
            items_created = 0
            
            for r in results:
                agents_run += 1
                if r.state == AgentState.COMPLETED:
                    agents_succeeded += 1
                    items_created += r.items_created
                elif r.state == AgentState.FAILED:
                    agents_failed += 1
                    self.agent_failure_counts[r.agent_name] = self.agent_failure_counts.get(r.agent_name, 0) + 1
                    logger.error(f"   ❌ {r.agent_name}: {r.error}")
                elif r.state == AgentState.BLOCKED:
                    agents_blocked += 1
                else:
                    agents_blocked += 1
                
                cycle_data["agents"].append({
                    "name": r.agent_name,
                    "state": r.state.value,
                    "duration_ms": r.duration_ms,
                    "items_processed": r.items_processed,
                    "items_created": r.items_created,
                    "error": r.error,
                })
            
            self.total_agents_run += agents_run
            self.total_agents_failed += agents_failed
            self.total_items_created += items_created
            
            cycle_data["success"] = True
            cycle_data["summary"] = {
                "agents_run": agents_run,
                "succeeded": agents_succeeded,
                "failed": agents_failed,
                "blocked": agents_blocked,
                "items_created": items_created,
            }
            
            # Log summary
            logger.info(f"\n📋 CYCLE #{cycle_num} COMPLETE in {cycle_duration:.1f}s")
            logger.info(f"   Agents run: {agents_run} | ✅ {agents_succeeded} | ❌ {agents_failed} | ⏭️ {agents_blocked}")
            logger.info(f"   Items created this cycle: {items_created}")
            logger.info(f"   Total items created: {self.total_items_created}")
            
            # Log table counts every 5 cycles
            if cycle_num % 5 == 0:
                counts = get_live_table_counts()
                total_rows = sum(counts.values())
                logger.info(f"📊 DB Growth: {total_rows:,} total rows")
                for table, count in sorted(counts.items()):
                    if count > 0:
                        logger.info(f"   {table}: {count:,}")
            
            # Check for repeated failures
            for agent, fail_count in self.agent_failure_counts.items():
                if fail_count >= 3:
                    logger.warning(f"⚠️ Agent '{agent}' has failed {fail_count} times consecutively")
            
        except Exception as e:
            cycle_duration = time.time() - cycle_start
            cycle_data["duration_sec"] = round(cycle_duration, 1)
            cycle_data["success"] = False
            cycle_data["error"] = str(e)
            logger.error(f"❌ CYCLE #{cycle_num} FAILED after {cycle_duration:.1f}s: {e}")
            logger.exception(e)
            self.total_agents_failed += 1
        
        self.cycle_stats.append(cycle_data)
        self.cycles_completed = cycle_num
        self.last_cycle_time = time.time()
        
        return cycle_data
    
    async def run(self):
        """Main continuous run loop."""
        self.running = True
        self.start_time = time.time()
        cycle_num = 0
        
        logger.info(f"\n🚀 STARTING CONTINUOUS RUN — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Set up signal handlers
        def signal_handler(sig, frame):
            logger.info(f"\n🛑 Shutdown signal received (Ctrl+C)")
            self.shutdown_requested = True
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        while not self.shutdown_requested:
            # Check time limit
            elapsed_hours = (time.time() - self.start_time) / 3600
            if elapsed_hours >= self.target_hours:
                logger.info(f"\n⏰ Target duration ({self.target_hours}h) reached!")
                break
            
            # Check cycle limit
            if self.max_cycles and cycle_num >= self.max_cycles:
                logger.info(f"\n🔄 Max cycles ({self.max_cycles}) reached!")
                break
            
            cycle_num += 1
            
            try:
                await self.run_cycle_with_monitoring(cycle_num)
            except Exception as e:
                logger.error(f"❌ Unexpected error in cycle {cycle_num}: {e}")
                logger.exception(e)
            
            # Wait for next cycle (with shutdown check)
            if not self.shutdown_requested:
                wait_time = self.cycle_interval
                logger.info(f"⏳ Waiting {wait_time}s until next cycle... (elapsed: {elapsed_hours:.2f}h)")
                
                # Wait in chunks to check shutdown
                chunk = 30
                waited = 0
                while waited < wait_time and not self.shutdown_requested:
                    await asyncio.sleep(min(chunk, wait_time - waited))
                    waited += chunk
        
        await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown with final report."""
        self.running = False
        elapsed = time.time() - self.start_time if self.start_time else 0
        
        logger.info(f"\n{'='*70}")
        logger.info(f"🏁 RUNNER SHUTDOWN — Final Report")
        logger.info(f"{'='*70}")
        logger.info(f"⏱️ Total runtime: {elapsed/3600:.2f} hours ({elapsed/60:.0f} minutes)")
        logger.info(f"🔄 Cycles completed: {self.cycles_completed}")
        logger.info(f"🤖 Total agents run: {self.total_agents_run}")
        logger.info(f"✅ Total succeeded: {self.total_agents_run - self.total_agents_failed}")
        logger.info(f"❌ Total failed: {self.total_agents_failed}")
        logger.info(f"📦 Total items created: {self.total_items_created}")
        
        if self.cycle_stats:
            avg_cycle_time = sum(c.get("duration_sec", 0) for c in self.cycle_stats) / len(self.cycle_stats)
            logger.info(f"⏱️ Avg cycle time: {avg_cycle_time:.1f}s")
        
        # Agent failure summary
        if self.agent_failure_counts:
            logger.info(f"\n⚠️ Agent Failure Counts:")
            for agent, count in sorted(self.agent_failure_counts.items(), key=lambda x: -x[1]):
                logger.info(f"   {agent}: {count} failures")
        
        # Final DB stats
        counts = get_live_table_counts()
        total_rows = sum(counts.values())
        logger.info(f"\n📊 Final Database State: {total_rows:,} rows")
        for table, count in sorted(counts.items()):
            if count > 0:
                logger.info(f"   {table}: {count:,}")
        
        logger.info(f"\n📝 Full log saved to: {log_file}")
        logger.info(f"🏁 APRS V7 Continuous Runner stopped.")


async def main():
    parser = argparse.ArgumentParser(description="APRS V7 Continuous Daemon Runner")
    parser.add_argument("--hours", type=float, default=18.0, help="Target runtime in hours")
    parser.add_argument("--interval", type=int, default=3600, help="Cycle interval in seconds")
    parser.add_argument("--max-cycles", type=int, default=None, help="Maximum cycles to run")
    parser.add_argument("--single", action="store_true", help="Run single cycle and exit")
    args = parser.parse_args()
    
    runner = ContinuousRunner(
        target_hours=args.hours,
        cycle_interval=args.interval,
        max_cycles=args.max_cycles,
    )
    
    await runner.initialize()
    
    if args.single:
        logger.info("Running single test cycle...")
        await runner.run_cycle_with_monitoring(1)
    else:
        await runner.run()


if __name__ == "__main__":
    asyncio.run(main())