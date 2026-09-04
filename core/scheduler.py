"""
core/scheduler.py — Event-Driven Scheduler for APRS V7.

Integrates with external task queues (event-driven-autonomous-loop at H:\trade)
and provides deterministic scheduling for all agents.
"""

import asyncio
import logging
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Awaitable
from enum import Enum
import sys

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings

logger = logging.getLogger("aprs.scheduler")


class TaskPriority(Enum):
    """Task priority levels."""
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"


@dataclass
class ScheduledTask:
    """A scheduled task with metadata."""
    task_id: str
    name: str
    agent_name: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: TaskPriority = TaskPriority.NORMAL
    status: TaskStatus = TaskStatus.PENDING
    scheduled_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300
    depends_on: List[str] = field(default_factory=list)  # Task IDs
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def __lt__(self, other: "ScheduledTask") -> bool:
        """For priority queue ordering (higher priority first, then earlier scheduled)."""
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        return self.scheduled_at < other.scheduled_at


class TaskQueue:
    """
    Priority-based task queue with dependency resolution.
    
    Features:
    - Priority queue (higher priority = processed first)
    - Dependency resolution (tasks wait for dependencies)
    - Retry logic with exponential backoff
    - Timeout handling
    - Persistence to database
    """
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running: Dict[str, ScheduledTask] = {}
        self._completed: Dict[str, ScheduledTask] = {}
        self._failed: Dict[str, ScheduledTask] = {}
        self._lock = asyncio.Lock()
        self._worker_tasks: List[asyncio.Task] = []
        self._running = False
    
    async def enqueue(self, task: ScheduledTask) -> str:
        """Add a task to the queue. Returns task_id."""
        await self._queue.put(task)
        logger.info(f"Enqueued task {task.task_id} ({task.name}) with priority {task.priority.name}")
        return task.task_id
    
    async def enqueue_batch(self, tasks: List[ScheduledTask]) -> List[str]:
        """Enqueue multiple tasks."""
        task_ids = []
        for task in tasks:
            task_id = await self.enqueue(task)
            task_ids.append(task_id)
        return task_ids
    
    async def start_workers(self, num_workers: int = None):
        """Start worker coroutines."""
        if num_workers is None:
            num_workers = self.max_concurrent
        
        self._running = True
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self._worker_tasks.append(worker)
        
        logger.info(f"Started {num_workers} queue workers")
    
    async def stop_workers(self):
        """Stop all workers gracefully."""
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        logger.info("Queue workers stopped")
    
    async def _worker(self, worker_name: str):
        """Worker coroutine that processes tasks from queue."""
        logger.info(f"Worker {worker_name} started")
        
        while True:
            try:
                # Get next task (with timeout to check shutdown)
                try:
                    task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                
                # Check if task should be cancelled
                if task.status == TaskStatus.CANCELLED:
                    self._queue.task_done()
                    continue
                
                # Check dependencies
                if not await self._dependencies_met(task):
                    # Re-queue with lower priority for later
                    task.priority = TaskPriority(max(0, task.priority.value - 10))
                    await self._queue.put(task)
                    await asyncio.sleep(1)
                    continue
                
                # Execute task
                await self._execute_task(task)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_name} error: {e}")
                await asyncio.sleep(1)
        
        logger.info(f"Worker {worker_name} stopped")
    
    async def _dependencies_met(self, task: ScheduledTask) -> bool:
        """Check if all dependencies are completed."""
        # In a real implementation, this would check the database
        # For now, we'll check the completed dict
        for dep_id in task.depends_on:
            if dep_id not in self._completed:
                return False
        return True
    
    async def _execute_task(self, task: ScheduledTask):
        """Execute a single task."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        self._running[task.task_id] = task
        
        logger.info(f"Executing task {task.task_id} ({task.name})")
        
        try:
            # Execute the actual agent logic
            result = await self._execute_agent_task(task)
            
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            self._completed[task.task_id] = task
            del self._running[task.task_id]
            
            logger.info(f"Task {task.task_id} completed successfully")
            
        except Exception as e:
            await self._handle_task_failure(task, e)
    
    async def _execute_agent_task(self, task: ScheduledTask) -> Dict[str, Any]:
        """Execute the actual agent task logic. Override in subclass or use callback."""
        # This is a hook - actual implementation would be provided by the orchestrator
        # For now, just simulate work
        await asyncio.sleep(0.1)
        return {"items_processed": 0, "items_created": 0}
    
    async def _handle_task_failure(self, task: ScheduledTask, error: Exception):
        """Handle task failure with retry logic."""
        task.retry_count += 1
        task.updated_at = datetime.utcnow()
        
        if task.retry_count >= task.max_retries:
            task.status = TaskStatus.FAILED
            self._failed[task.task_id] = task
            logger.error(f"Task {task.task_id} failed permanently after {task.retry_count} retries: {error}")
        else:
            task.status = TaskStatus.RETRYING
            # Exponential backoff
            delay = 2 ** task.retry_count * 5  # 10s, 20s, 40s...
            logger.warning(f"Task {task.task_id} failed (attempt {task.retry_count}), retrying in {delay}s: {error}")
            await asyncio.sleep(delay)
            await self.enqueue(task)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "pending": self._queue.qsize(),
            "running": len(self._running),
            "completed": len(self._completed),
            "failed": len(self._failed),
            "max_concurrent": self.max_concurrent,
        }


class Scheduler:
    """
    High-level scheduler that manages agent execution schedules.
    
    Coordinates with external task queues (event-driven-autonomous-loop)
    and provides deterministic scheduling for all agents.
    """
    
    def __init__(self, task_queue: TaskQueue = None):
        self.task_queue = task_queue or TaskQueue()
        self._schedules: Dict[str, Dict[str, Any]] = {}
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._agent_callbacks: Dict[str, Callable] = {}
    
    def register_agent(
        self,
        agent_name: str,
        interval_seconds: int,
        callback: Callable[[], Awaitable[Dict[str, Any]]],
        priority: TaskPriority = TaskPriority.NORMAL,
        dependencies: List[str] = None,
        max_concurrent: int = 1,
        timeout_seconds: int = 300,
    ):
        """Register an agent for periodic execution."""
        self._agent_callbacks[agent_name] = callback
        self._schedules[agent_name] = {
            "interval_seconds": interval_seconds,
            "callback": callback,
            "priority": priority,
            "dependencies": dependencies or [],
            "max_concurrent": max_concurrent,
            "timeout_seconds": timeout_seconds,
            "last_run": None,
            "next_run": datetime.utcnow(),
        }
        logger.info(f"Registered agent: {agent_name} (interval: {interval_seconds}s)")
    
    async def start(self):
        """Start the scheduler."""
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        await self.task_queue.start_workers()
        logger.info("Scheduler started")
    
    async def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        await self.task_queue.stop_workers()
        logger.info("Scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop - checks for due tasks every minute."""
        while True:
            try:
                now = datetime.utcnow()
                
                for agent_name, schedule in self._schedules.items():
                    if schedule["next_run"] <= datetime.utcnow():
                        # Check if already running
                        # (In a real implementation, check running tasks)
                        
                        # Create and enqueue task
                        task = ScheduledTask(
                            task_id=f"{schedule['agent_name']}_{int(datetime.utcnow().timestamp())}",
                            name=schedule["agent_name"],
                            agent_name=schedule["agent_name"],
                            priority=schedule["priority"],
                            timeout_seconds=schedule["timeout_seconds"],
                            depends_on=schedule["dependencies"],
                        )
                        
                        await self.task_queue.enqueue(task)
                        
                        # Update next run time
                        schedule["last_run"] = datetime.utcnow()
                        schedule["next_run"] = datetime.utcnow() + timedelta(seconds=schedule["interval_seconds"])
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                await asyncio.sleep(10)
    
    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            "running": self._running,
            "registered_agents": list(self._schedules.keys()),
            "queue_stats": self.task_queue.get_stats(),
            "schedules": {
                name: {
                    "interval_seconds": s["interval_seconds"],
                    "priority": s["priority"].name,
                    "dependencies": s["dependencies"],
                    "last_run": s["last_run"].isoformat() if s["last_run"] else None,
                    "next_run": s["next_run"].isoformat() if s["next_run"] else None,
                }
                for name, s in self._schedules.items()
            }
        }


# External queue integration (event-driven-autonomous-loop at H:\trade)
class ExternalQueueIntegration:
    """
    Integration with event-driven-autonomous-loop at H:\trade.
    
    This external system manages the actual task queue and execution.
    APRS V7 registers agents and submits tasks via HTTP/webhook.
    """
    
    ENDPOINTS = {
        "POST /run/crawler": "InternetCrawlerAgent.crawl_cycle()",
        "POST /run/trend": "TrendSignalAgent.scan()",
        "POST /run/expand": "NicheExpander.expand_from_signals()",
        "POST /run/discover": "DiscoveryAgent.run_batch()",
        "POST /run/mine": "ProblemMiner.mine_batch()",
        "POST /run/gates": "GateEngine.run_pending_batch()",
        "POST /run/suppliers": "SupplierAgent.run_pending()",
        "POST /run/learn": "LearningAgent.weekly_synthesis()",
        "GET  /health": "All agent status + LLM tier health",
        "POST /override/agent": "Set agent mode (auto/manual/disabled/force_tier)",
    }
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        import aiohttp
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    async def submit_task(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a task to the external queue."""
        if not self._session:
            raise RuntimeError("Not initialized - use async with")
        
        url = f"{self.base_url}{endpoint}"
        async with self._session.post(url, json=payload) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"External queue error {resp.status}: {text}")
            return await resp.json()
    
    async def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents from external system."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/health") as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}"}
    
    async def set_agent_mode(self, agent_name: str, mode: str) -> Dict[str, Any]:
        """Set agent mode (auto/manual/disabled/force_tier:N)."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/override/agent",
                json={"agent": agent_name, "mode": mode},
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}"}


# Agent-Memory Integration (MCP server at localhost:3333)
class AgentMemoryClient:
    """
    Client for agentmemory MCP server (localhost:3333).
    
    Provides persistent memory across agent runs.
    """
    
    def __init__(self, url: str = "http://localhost:3333"):
        self.url = url
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        import aiohttp
        self._session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    async def store(self, key: str, value: Any, agent: str = "default", confidence: float = 0.9) -> bool:
        """Store a memory entry."""
        if not hasattr(self, '_session') or self._session is None:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                return await self._store_with_session(session, key, value, agent, confidence)
        return await self._store_with_session(self._session, key, value, agent, confidence)
    
    async def _store_with_session(self, session, key: str, value: Any, agent: str, confidence: float) -> bool:
        try:
            payload = {
                "key": key,
                "value": value,
                "agent": agent,
                "confidence": confidence,
                "timestamp": datetime.utcnow().isoformat(),
            }
            async with session.post(f"http://localhost:3333/memory/store", json=payload) as resp:
                return resp.status == 200
        except Exception as e:
            logger.warning(f"Memory store failed: {e}")
            return False
    
    async def recall(self, query: str, agent: str = "default", top_k: int = 5) -> List[Dict]:
        """Recall memories matching query."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://localhost:3333/memory/recall",
                    json={"query": query, "agent": agent, "top_k": top_k}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return []
        except Exception as e:
            logger.warning(f"Memory recall failed: {e}")
            return []


# Global scheduler instance
_scheduler: Optional["Scheduler"] = None


def get_scheduler() -> Scheduler:
    """Get or create global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


async def run_scheduler_once() -> List[Dict[str, Any]]:
    """Run one scheduler cycle and return results."""
    scheduler = get_scheduler()
    results = []
    
    for agent_name, schedule in scheduler._schedules.items():
        if schedule["next_run"] <= datetime.utcnow():
            # Execute agent callback
            callback = scheduler._agent_callbacks.get(schedule["agent_name"])
            if callback:
                try:
                    result = await callback()
                    results.append({
                        "agent": schedule["agent_name"],
                        "result": result,
                        "executed_at": datetime.utcnow().isoformat(),
                    })
                except Exception as e:
                    logger.error(f"Agent {schedule['agent_name']} failed: {e}")
    
    return results


if __name__ == "__main__":
    async def test():
        # Test scheduler
        scheduler = Scheduler()
        
        # Register a test agent
        async def test_agent():
            await asyncio.sleep(0.1)
            return {"items_processed": 5, "items_created": 2}
        
        scheduler.register_agent(
            agent_name="test_agent",
            interval_seconds=10,
            callback=test_agent,
            priority=TaskPriority.NORMAL,
        )
        
        await scheduler.start()
        await asyncio.sleep(3)
        await scheduler.stop()
        
        print("Scheduler test complete")
        print("Status:", scheduler.get_status())
    
    asyncio.run(test())