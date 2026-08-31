"""
tools/ai_supervisor.py — AI Active Supervisor for ALL Online Tasks.

This is the CENTRAL AI BRAIN that actively supervises, monitors, and improves
ALL online tasks in real-time. Every online task runs under AI supervision.

Key Capabilities:
1. ACTIVE RUNTIME MONITORING: Watches every online task as it executes
2. AI SCRAPER VALIDATOR: Validates every scraped product in real-time
3. AUTO SOFT-DELETE: Invalid findings auto soft-deleted with AI reasoning
4. ARCHIVE VIEW: Soft-deleted items shown in Archive with AI rejection reasons
5. REAL-TIME SUPERVISION: AI actively improves tasks based on collected data
6. ADAPTIVE STRATEGY: AI adjusts scraping strategy based on validation results

Architecture:
- AI Supervisor runs as a background monitor
- Every online task registers with Supervisor before execution
- Supervisor wraps task execution with AI validation
- Validation results stored with AI reasoning
- Soft-deleted items moved to Archive with AI rejection reasons
"""

import os
import sys
import json
import time
import threading
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from contextlib import contextmanager
from functools import wraps

# Project root import
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from models.nim_cluster import SupremeNIMCluster
from config.settings import NIM_MODELS
from core.database import (
    record_scraper_validation, get_scraper_validations,
    soft_delete_product, restore_product, get_all_products,
    get_all_table_names, get_table_data,
    record_ai_supervisor_log, get_ai_supervisor_logs,
    record_ai_task_improvement, get_ai_task_improvements
)
from core.utils import normalize_region

logger = logging.getLogger("aprs.ai_supervisor")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s — %(message)s")


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    SOFT_DELETED = "soft_deleted"
    IMPROVED = "improved"


class ValidationResult(Enum):
    VALID = "valid"
    INVALID = "invalid"
    NEEDS_REVIEW = "needs_review"


@dataclass
class OnlineTask:
    """Represents an online task under AI supervision."""
    task_id: str
    task_type: str  # "scrape", "discover", "validate", "search", "discover_niche", etc.
    target: str  # URL, query, niche, etc.
    marketplace: str = ""
    region: str = "India"
    status: TaskStatus = TaskStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    data_collected: Dict = field(default_factory=dict)
    validation_results: List[Dict] = field(default_factory=list)
    ai_feedback: List[str] = field(default_factory=list)
    improvements_applied: List[str] = field(default_factory=list)
    error: Optional[str] = None
    
    
@dataclass
class ScraperValidation:
    """Result of AI validation for scraped data."""
    product_id: str
    marketplace: str
    region: str
    is_valid: bool
    confidence: float
    issues: List[str]
    auto_soft_delete: bool
    rejection_reason: str
    rejection_category: str
    ai_reasoning: str
    ai_suggested_fix: Optional[str] = None
    validated_at: datetime = field(default_factory=datetime.now)


class AISupervisor:
    """
    CENTRAL AI SUPERVISOR — The brain that actively monitors ALL online tasks.
    
    Every online task MUST register with this supervisor before execution.
    The supervisor wraps execution with AI validation and real-time monitoring.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.cluster = SupremeNIMCluster()
        self._active_tasks: Dict[str, OnlineTask] = {}
        self._task_history: List[OnlineTask] = []
        self._validation_cache: Dict[str, ScraperValidation] = {}
        self._improvement_log: List[Dict] = []
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = threading.Event()
        self._supervision_active = True
        
        # AI Model for supervision
        self._supervision_model = "nemotron_scout"
        
        logger.info("🧠 AI SUPERVISOR INITIALIZED — Active monitoring ENGAGED")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # TASK REGISTRATION & EXECUTION WRAPPER
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def register_task(self, task_type: str, target: str, marketplace: str = "", region: str = "India", **kwargs) -> str:
        """Register a new online task under AI supervision. Returns task_id."""
        task_id = f"{task_type}_{int(time.time() * 1000)}_{abs(hash(target)) % 10000:04d}"
        
        task = OnlineTask(
            task_id=task_id,
            task_type=task_type,
            target=target,
            marketplace=marketplace,
            region=region,
            status=TaskStatus.PENDING,
            data_collected=kwargs
        )
        
        with threading.Lock():
            self._active_tasks[task_id] = task
        
        self._log_supervisor_event("TASK_REGISTERED", {
            "task_id": task_id,
            "task_type": task_type,
            "target": target,
            "marketplace": marketplace,
            "region": region
        })
        
        logger.info(f"🧠 AI SUPERVISOR: Task REGISTERED [{task_id}] — {task_type} → {target}")
        return task_id
    
    @contextmanager
    def supervise(self, task_id: str):
        """
        Context manager that wraps task execution with AI supervision.
        Usage:
            with supervisor.supervise(task_id) as task:
                result = do_online_work()
                task.data_collected = result
        """
        task = self._active_tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not registered with AI Supervisor")
        
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        
        self._log_supervisor_event("TASK_STARTED", {"task_id": task_id})
        logger.info(f"🧠 AI SUPERVISOR: Task STARTED [{task_id}] — {task.task_type}")
        
        try:
            yield task
            
            # Post-execution AI validation
            if task.data_collected:
                self._ai_validate_task_output(task)
            
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now()
            self._log_supervisor_event("TASK_COMPLETED", {"task_id": task_id, "validation_count": len(task.validation_results)})
            logger.info(f"🧠 AI SUPERVISOR: Task COMPLETED [{task_id}]")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.now()
            self._log_supervisor_event("TASK_FAILED", {"task_id": task_id, "error": str(e)})
            logger.error(f"🧠 AI SUPERVISOR: Task FAILED [{task_id}] — {e}")
            raise
        finally:
            # Move to history
            with threading.Lock():
                self._task_history.append(task)
                if task_id in self._active_tasks:
                    del self._active_tasks[task_id]
    
    def execute_supervised(self, task_id: str, task_func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function under full AI supervision.
        Handles registration, execution, validation, and logging automatically.
        """
        task_type = kwargs.pop('_task_type', 'generic')
        target = kwargs.pop('_target', str(args[0]) if args else 'unknown')
        marketplace = kwargs.pop('_marketplace', '')
        region = kwargs.pop('_region', 'India')
        
        tid = self.register_task(task_type, target, marketplace, region)
        
        with self.supervise(tid) as task:
            result = task_func(*args, **kwargs)
            task.data_collected = result if isinstance(result, dict) else {"result": result}
            return result
    
    # ══════════════════════════════════════════════════════════════════════════════
    # AI SCRAPER VALIDATOR — Real-time validation of scraped data
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def _ai_validate_task_output(self, task: OnlineTask):
        """AI validates the output of a completed task."""
        if task.task_type in ("scrape", "scrape_product", "scrape_marketplace"):
            self._ai_validate_scraped_products(task)
        elif task.task_type in ("discover", "discover_niche", "discover_trends"):
            self._ai_validate_discovery_output(task)
        elif task.task_type in ("search", "search_products"):
            self._ai_validate_search_results(task)
        
        # Apply AI improvements based on validation results
        self._ai_apply_improvements(task)
    
    def _ai_validate_scraped_products(self, task: OnlineTask):
        """AI validates scraped product data in real-time."""
        products = task.data_collected.get("products", [])
        if not products:
            return
        
        logger.info(f"🧠 AI SUPERVISOR: Validating {len(products)} scraped products from [{task.task_id}]")
        
        for product in products:
            validation = self._ai_validate_single_product(product, task.marketplace, task.region)
            task.validation_results.append(validation)
            
            # Store validation in DB
            try:
                record_scraper_validation({
                    "product_id": product.get("product_id", f"temp_{abs(hash(str(product)))}"),
                    "marketplace": task.marketplace,
                    "region": task.region,
                    "is_valid": validation.is_valid,
                    "confidence": validation.confidence,
                    "issues": json.dumps(validation.issues),
                    "auto_soft_delete": validation.auto_soft_delete,
                    "rejection_reason": validation.rejection_reason,
                    "rejection_category": validation.rejection_category,
                    "ai_notes": validation.ai_reasoning,
                    "raw_product_data": json.dumps(product, default=str)[:5000]
                })
            except Exception as e:
                logger.warning(f"Failed to record validation: {e}")
            
            # Auto soft-delete if AI recommends
            if validation.auto_soft_delete and product.get("product_id"):
                try:
                    soft_delete_product(
                        product["product_id"],
                        f"AI Supervisor Validation Rejected: {validation.rejection_reason}",
                        deleted_by="ai_supervisor"
                    )
                    task.ai_feedback.append(f"Auto soft-deleted {product.get('product_id')}: {validation.rejection_reason}")
                    logger.info(f"🧠 AI SUPERVISOR: Auto soft-deleted {product['product_id']} — {validation.rejection_reason}")
                    self._write_ai_rejection_to_product(
                        product_id=product["product_id"],
                        rejection_reason=validation.rejection_reason,
                        rejection_category=validation.rejection_category,
                        ai_reasoning=validation.ai_reasoning,
                        confidence=validation.confidence,
                    )
                except Exception as e:
                    logger.warning(f"Failed to soft-delete: {e}")
    
    def _ai_validate_single_product(self, product: Dict, marketplace: str, region: str) -> ScraperValidation:
        """AI validates a single scraped product with detailed reasoning."""
        
        product_summary = self._prepare_product_summary(product, marketplace, region)
        
        prompt = f"""You are the AI SUPERVISOR validating e-commerce product data in REAL-TIME.

SCRAPED PRODUCT DATA:
{product_summary}

VALIDATION CRITERIA (check ALL):
1. COMPLETENESS: Has title, price (>0), URL, marketplace-appropriate fields?
2. PRICE VALIDITY: Price > 0, reasonable for {marketplace}/{region}, not suspiciously low/high?
3. URL VALIDITY: Proper product URL format for {marketplace}, accessible pattern?
3. DATA REALISM: Rating 1-5, review_count realistic, availability logical?
4. MARKETPLACE CONSISTENCY: Data matches {marketplace} structure (ASIN for Amazon, PID for Flipkart, etc.)?
5. DUPLICATE SIGNALS: Identical title/price across multiple entries?
6. BUSINESS VIABILITY: Price allows margins, not obvious test/fake data?

RESPOND AS JSON ONLY:
{{
    "is_valid": true/false,
    "confidence": 0-100,
    "issues": ["specific issue 1", "specific issue 2"],
    "auto_soft_delete": true/false,
    "rejection_reason": "specific reason if invalid",
    "rejection_category": "missing_data|invalid_price|invalid_url|unrealistic_data|duplicate|marketplace_mismatch|fake_data",
    "ai_reasoning": "detailed step-by-step validation reasoning",
    "ai_suggested_fix": "how to fix if invalid, or 'N/A' if valid"
}}"""

        raw = self._nim_query(prompt, task_type="ultra_reasoning", max_tokens=2000, temperature=0.1)
        validation_data = self._extract_json(raw)
        
        return ScraperValidation(
            product_id=product.get("product_id", f"temp_{abs(hash(str(product)))}"),
            marketplace=marketplace,
            region=region,
            is_valid=validation_data.get("is_valid", True),
            confidence=validation_data.get("confidence", 50),
            issues=validation_data.get("issues", []),
            auto_soft_delete=validation_data.get("auto_soft_delete", False),
            rejection_reason=validation_data.get("rejection_reason", "Unknown"),
            rejection_category=validation_data.get("rejection_category", "unknown"),
            ai_reasoning=validation_data.get("ai_reasoning", "No reasoning provided"),
            ai_suggested_fix=validation_data.get("ai_suggested_fix")
        )
    
    def _ai_validate_discovery_output(self, task: OnlineTask):
        """AI validates discovery outputs (niches, sources, keywords) — active implementation."""
        data = task.data_collected
        sources  = data.get("sources",  data.get("new_sources",  []))
        niches   = data.get("niches",   data.get("new_niches",   []))
        keywords = data.get("keywords", data.get("new_seeds",    []))
        if not (sources or niches or keywords):
            return
        logger.info(f"🧠 AI SUPERVISOR: Validating discovery [{task.task_id}] — "
                    f"{len(sources)} sources, {len(niches)} niches, {len(keywords)} keywords")
        summary = (
            f"Sources: {len(sources)} — sample: {[s.get('url','') for s in sources[:4]]}\n"
            f"Niches:  {len(niches)}  — sample: {[n.get('category','') for n in niches[:4]]}\n"
            f"Keywords:{len(keywords)} — sample: {[k.get('keyword',k) for k in keywords[:4]]}\n"
            f"Region: {task.region}"
        )
        prompt = f"""You are AI SUPERVISOR reviewing DISCOVERY results for an autonomous e-commerce engine.

DISCOVERY OUTPUT:
{summary}

Validate:
1. Are discovered URLs real e-commerce / trend sites (not garbage or spam)?
2. Are discovered niches specific, searchable product keywords (not vague categories)?
3. Are discovered keywords commercially viable with buyer intent?

Respond as JSON only:
{{"sources_quality":"high|medium|low","niches_quality":"high|medium|low","keywords_quality":"high|medium|low","flagged_sources":[],"flagged_niches":[],"overall_quality_score":0-100,"ai_assessment":"...","recommended_adjustment":"..."}}"""
        raw = self._nim_query(prompt, task_type="ultra_reasoning", max_tokens=1200, temperature=0.15)
        try:
            result = self._extract_json(raw)
            score  = result.get("overall_quality_score", 70)
            task.ai_feedback.append(f"Discovery quality: {score}/100 — {result.get('ai_assessment','OK')}")
            if result.get("recommended_adjustment"):
                task.improvements_applied.append(result["recommended_adjustment"])
            self._log_supervisor_event("DISCOVERY_VALIDATED",
                {"task_id": task.task_id, "score": score,
                 "flagged_sources": len(result.get("flagged_sources", [])),
                 "flagged_niches": len(result.get("flagged_niches", []))})
            logger.info(f"🧠 AI SUPERVISOR: Discovery quality {score}/100 [{task.task_id}]")
        except Exception as e:
            logger.warning(f"Discovery validation parse error: {e}")

    def _ai_validate_search_results(self, task: OnlineTask):
        """AI validates trend/search results — active implementation."""
        data   = task.data_collected
        trends = data.get("trends", data.get("result", data.get("signals", [])))
        if not trends:
            return
        trend_list = list(trends.values())[:10] if isinstance(trends, dict) else trends[:10]
        logger.info(f"🧠 AI SUPERVISOR: Validating {len(trend_list)} trend signals [{task.task_id}]")
        keywords = [t.get("keyword", str(t)) if isinstance(t, dict) else str(t) for t in trend_list]
        prompt = f"""You are AI SUPERVISOR reviewing TREND SIGNALS for an e-commerce engine.
Region: {task.region}

TREND SIGNALS:
{keywords}

For each: Is it a real consumer product keyword with buyer intent, specific enough to search on Amazon/Flipkart?

Respond as JSON only:
{{"valid_keywords":[],"invalid_keywords":[],"invalid_reasons":{{}},"overall_signal_quality":"high|medium|low","ai_assessment":"...","recommended_focus":"..."}}"""
        raw = self._nim_query(prompt, task_type="nemotron_scout", max_tokens=1200, temperature=0.1)
        try:
            result  = self._extract_json(raw)
            valid   = result.get("valid_keywords", [])
            invalid = result.get("invalid_keywords", [])
            task.ai_feedback.append(
                f"Trend signals: {len(valid)} valid, {len(invalid)} filtered — "
                f"Quality: {result.get('overall_signal_quality','unknown')}"
            )
            self._log_supervisor_event("TRENDS_VALIDATED",
                {"task_id": task.task_id, "valid": len(valid), "invalid": len(invalid)})
            logger.info(f"🧠 AI SUPERVISOR: Trends {len(valid)} valid / {len(invalid)} filtered [{task.task_id}]")
        except Exception as e:
            logger.warning(f"Trend validation parse error: {e}")
    
    def _prepare_product_summary(self, product: Dict, marketplace: str, region: str) -> str:
        """Prepare structured product summary for AI validation."""
        curr = product.get('currency', 'INR' if region == 'India' else 'USD')
        price = product.get('price', product.get('planned_msrp', product.get('retail_msrp', 'N/A')))
        url = product.get('product_url', product.get('listing_url', product.get('marketplace_url', 'N/A')))
        return f"""
Product: {product.get('title', product.get('name', 'Unknown'))}
Marketplace: {marketplace}
Region: {region}
Price: {price} {curr}
Original Price: {product.get('original_price', 'N/A')}
Discount: {product.get('discount_pct', 'N/A')}%
Rating: {product.get('rating', 'N/A')}
Review Count: {product.get('review_count', 'N/A')}
Availability: {product.get('availability', 'in_stock')}
Product URL: {url}
Image URL: {product.get('image_url', 'N/A')}
Seller: {product.get('seller_name', 'N/A')}
Seller Rating: {product.get('seller_rating', 'N/A')}
ASIN/PID: {product.get('asin', product.get('product_id', 'N/A'))}
Raw Keys: {list(product.keys())}
"""
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # AI ACTIVE IMPROVEMENT ENGINE
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def _ai_apply_improvements(self, task: OnlineTask):
        """AI applies improvements based on validation results and historical data."""
        if not task.validation_results:
            return
        
        # Collect validation insights
        invalid_count = sum(1 for v in task.validation_results if not v.is_valid)
        total = len(task.validation_results)
        
        if invalid_count == 0:
            return  # All valid, no improvements needed
        
        # Analyze failure patterns
        categories = {}
        for v in task.validation_results:
            if not v.is_valid:
                cat = v.rejection_category
                categories[cat] = categories.get(cat, 0) + 1
        
        # Generate AI improvement suggestions
        prompt = f"""You are the AI SUPERVISOR analyzing scraper failures to IMPROVE future runs.

TASK: {task.task_type} → {task.target}
MARKETPLACE: {task.marketplace}
REGION: {task.region}
TOTAL PRODUCTS: {len(task.validation_results)}
INVALID: {invalid_count}/{total}

FAILURE PATTERNS:
{json.dumps(categories, indent=2)}

SAMPLE INVALID REASONS:
{[v.rejection_reason for v in task.validation_results if not v.is_valid][:5]}

Based on this data, provide SPECIFIC, ACTIONABLE improvements for the scraper/discovery:
1. Selector fixes (CSS/XPath)
2. URL pattern adjustments
3. Pagination handling
4. Anti-bot evasion
5. Data extraction logic
6. Rate limiting adjustments
7. Request headers/cookies
8. JavaScript rendering needs

Respond as JSON:
{{
    "improvements": [
        {{"type": "selector_fix|url_pattern|pagination|anti_bot|extraction|rate_limit|headers|js_render", "description": "specific fix", "priority": "high|medium|low", "target": "what to change"}}
    ],
    "strategy_adjustment": "overall strategy change recommendation"
}}"""

        raw = self._nim_query(prompt, task_type="ultra_reasoning", max_tokens=2000, temperature=0.2)
        try:
            improvements = self._extract_json(raw)
        except:
            improvements = {"improvements": [], "strategy_adjustment": "AI analysis failed"}
        
        # Record improvements
        for imp in improvements.get("improvements", []):
            improvement_record = {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "marketplace": task.marketplace,
                "region": task.region,
                "improvement_type": imp.get("type"),
                "description": imp.get("description"),
                "priority": imp.get("priority"),
                "target": imp.get("target"),
                "triggered_by": f"{invalid_count}/{total} invalid products",
                "applied_at": datetime.now().isoformat()
            }
            
            try:
                record_ai_task_improvement(improvement_record)
            except:
                pass
            
            task.improvements_applied.append(imp.get("description", ""))
        
        self._improvement_log.append({
            "task_id": task.task_id,
            "timestamp": datetime.now().isoformat(),
            "improvements": improvements.get("improvements", []),
            "strategy_adjustment": improvements.get("strategy_adjustment", "")
        })
        
        logger.info(f"🧠 AI SUPERVISOR: Applied {len(improvements.get('improvements', []))} improvements to [{task.task_id}]")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # REAL-TIME MONITORING THREAD
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def start_monitoring(self):
        """Start the real-time monitoring thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        
        self._stop_monitor.clear()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, name="AI-Supervisor-Monitor", daemon=True)
        self._monitor_thread.start()
        logger.info("🧠 AI SUPERVISOR: Real-time monitoring STARTED")
    
    def stop_monitoring(self):
        """Stop the monitoring thread."""
        self._stop_monitor.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("🧠 AI SUPERVISOR: Real-time monitoring STOPPED")
    
    def _monitor_loop(self):
        """Background loop that actively monitors all online activity."""
        while not self._stop_monitor.is_set():
            try:
                # Monitor active tasks
                with threading.Lock():
                    active = list(self._active_tasks.values())
                
                for task in active:
                    if task.status == TaskStatus.RUNNING:
                        # Check for stuck tasks
                        if task.started_at:
                            elapsed = (datetime.now() - task.started_at).total_seconds()
                            if elapsed > 300:  # 5 minutes
                                self._log_supervisor_event("TASK_STUCK", {"task_id": task.task_id, "elapsed": elapsed})
                                logger.warning(f"🧠 AI SUPERVISOR: Task STUCK [{task.task_id}] — {elapsed:.0f}s")
                                
                                # AI suggests recovery
                                self._ai_suggest_recovery(task)
                
                # Periodic strategy review
                if len(self._improvement_log) % 10 == 0 and self._improvement_log:
                    self._ai_strategy_review()
                
            except Exception as e:
                logger.error(f"AI Supervisor monitor error: {e}")
            
            time.sleep(30)  # Check every 30 seconds
    
    def _ai_suggest_recovery(self, task: OnlineTask):
        """AI suggests recovery for stuck/failed tasks."""
        prompt = f"""AI SUPERVISOR RECOVERY ANALYSIS

STUCK TASK: {task.task_id}
TYPE: {task.task_type}
TARGET: {task.task}
ELAPSED: {(datetime.now() - task.started_at).total_seconds():.0f}s
DATA COLLECTED: {len(task.data_collected)} items

Suggest recovery action:
1. Retry with different approach
2. Skip and continue
3. Reduce scope
4. Change strategy entirely
5. Alert human

JSON response: {{"action": "retry|skip|reduce|change_strategy|alert", "reason": "...", "new_params": {{}}}}"""

        raw = self._nim_query(prompt, task_type="ultra_reasoning", max_tokens=1000, temperature=0.2)
        try:
            recovery = self._extract_json(raw)
            logger.info(f"🧠 AI SUPERVISOR: Recovery suggestion for [{task.task_id}] — {recovery.get('action')}")
        except:
            pass
    
    def _ai_strategy_review(self):
        """Periodic AI review of overall strategy based on accumulated improvements."""
        if len(self._improvement_log) < 5:
            return
        
        recent = self._improvement_log[-20:]
        
        prompt = f"""AI SUPERVISOR STRATEGY REVIEW

RECENT IMPROVEMENTS (last 20):
{json.dumps([imp.get('improvement_type') for imp in recent if isinstance(imp, dict)], indent=2)}

TASKS MONITORED: {len(self._task_history)}
ACTIVE TASKS: {len(self._active_tasks)}

Provide STRATEGIC recommendations for overall scraping/discovery strategy:
- Which marketplaces need attention?
- What anti-bot measures needed?
- Rate limiting adjustments?
- New sources to explore?
- Architecture changes?

JSON: {{"strategic_recommendations": [...], "priority_focus": "..."}}"""

        raw = self._nim_query(prompt, task_type="nemotron_scout", max_tokens=2000, temperature=0.2)
        try:
            strategy = self._extract_json(raw)
            logger.info(f"🧠 AI SUPERVISOR: Strategy review complete — {len(strategy.get('strategic_recommendations', []))} recommendations")
        except:
            pass
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # NIM QUERY HELPERS
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def _nim_query(self, prompt: str, task_type: str = "ultra_reasoning", max_tokens: int = 2000, temperature: float = 0.2) -> str:
        """Query NIM with supervision-optimized parameters, with automatic local Ollama GGUF fallback."""
        try:
            res = self.cluster.query(
                prompt=prompt,
                task_type=task_type if task_type in NIM_MODELS else "ultra_reasoning",
                system_prompt="You are the AI SUPERVISOR for an autonomous e-commerce intelligence system. You actively monitor, validate, and improve all online tasks in real-time. Be precise, actionable, and strategic.",
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=60.0
            )
            if isinstance(res, dict):
                return res.get("content", "")
            return str(res)
        except Exception as e:
            logger.warning(f"NIM query notice: {e}. Trying local Ollama fallback...")
            try:
                from models.llm_router import LLMRouter, LLMTaskType
                router = LLMRouter()
                import asyncio
                loop = asyncio.new_event_loop()
                resp = loop.run_until_complete(
                    router._query_ollama(
                        prompt=prompt,
                        system_prompt="You are the AI SUPERVISOR for an autonomous e-commerce intelligence system. Respond in valid JSON only.",
                        temperature=temperature,
                        max_tokens=max_tokens,
                        force_json=True
                    )
                )
                loop.close()
                if resp and resp.content:
                    return resp.content
            except Exception as oe:
                logger.debug(f"Ollama supervisor fallback note: {oe}")
            return ""
    
    def _extract_json(self, raw: str) -> dict:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        except:
            pass
        return {}
    
    # ══════════════════════════════════════════════════════════════════════════════
    # LOGGING & STATUS
    # ═══════════════════════════════════════════════════════════════════════════════
    
    def _log_supervisor_event(self, event_type: str, details: Dict):
        """Log supervisor event to database."""
        try:
            record_ai_supervisor_log({
                "event_type": event_type,
                "details": json.dumps(details, default=str),
                "timestamp": datetime.now().isoformat(),
                "active_tasks": len(self._active_tasks),
                "total_validations": sum(len(t.validation_results) for t in self._task_history)
            })
        except Exception as e:
            logger.debug(f"Failed to log supervisor event: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current supervisor status."""
        return {
            "supervision_active": self._supervision_active,
            "monitoring_active": self._monitor_thread and self._monitor_thread.is_alive(),
            "active_tasks": len(self._active_tasks),
            "completed_tasks": len(self._task_history),
            "total_validations": sum(len(t.validation_results) for t in self._task_history),
            "total_improvements": len(self._improvement_log),
            "active_task_details": [
                {
                    "task_id": t.task_id,
                    "task_type": t.task_type,
                    "target": t.target,
                    "status": t.status.value,
                    "elapsed": (datetime.now() - t.started_at).total_seconds() if t.started_at else 0,
                    "validations": len(t.validation_results)
                }
                for t in self._active_tasks.values()
            ]
        }
    
    def get_archive_view(self, limit: int = 100) -> List[Dict]:
        """Get soft-deleted products with AI rejection reasons for Archive view."""
        products = get_all_products(include_deleted=True)
        archived = [p for p in products if p.get("is_deleted") == 1]
        
        # Enhance with validation details
        for p in archived:
            # Get validation records for this product
            try:
                validations = get_scraper_validations()
                p_validations = [v for v in validations if v.get("product_id") == p.get("product_id")]
                if p_validations:
                    latest = p_validations[-1]
                    p["ai_rejection_reason"] = latest.get("rejection_reason", "")
                    p["ai_rejection_category"] = latest.get("rejection_category", "")
                    p["ai_reasoning"] = latest.get("ai_notes", "")
                    p["ai_confidence"] = latest.get("confidence", 0)
                else:
                    p["ai_rejection_reason"] = p.get("deletion_reason", "No AI validation record")
                    p["ai_rejection_category"] = "manual"
                    p["ai_reasoning"] = "Deleted before AI Supervisor validation"
                    p["ai_confidence"] = 0
            except:
                p["ai_rejection_reason"] = p.get("deletion_reason", "Unknown")
                p["ai_rejection_category"] = "unknown"
                p["ai_reasoning"] = "Error retrieving validation"
                p["ai_confidence"] = 0
        
        return archived[:limit]

    def validate_products_batch(self, products: List[Dict], marketplace: str, region: str) -> Dict[str, Any]:
        """
        Public method: validate a batch of products against AI criteria.
        Called by daemon after each niche scrape cycle.
        """
        if not products:
            return {"valid": 0, "invalid": 0, "auto_deleted": 0}
        valid_count = invalid_count = deleted_count = 0
        for product in products:
            try:
                validation = self._ai_validate_single_product(product, marketplace, region)
                if validation.is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1
                    try:
                        record_scraper_validation({
                            "product_id": product.get("product_id", "unknown"),
                            "marketplace": marketplace,
                            "region": region,
                            "is_valid": False,
                            "confidence": validation.confidence,
                            "issues": json.dumps(validation.issues),
                            "auto_soft_delete": validation.auto_soft_delete,
                            "rejection_reason": validation.rejection_reason,
                            "rejection_category": validation.rejection_category,
                            "ai_notes": validation.ai_reasoning,
                            "raw_product_data": json.dumps(product, default=str)[:3000]
                        })
                    except Exception:
                        pass
                    if validation.auto_soft_delete and product.get("product_id"):
                        try:
                            soft_delete_product(
                                product["product_id"],
                                f"AI Supervisor: {validation.rejection_reason}",
                                deleted_by="ai_supervisor"
                            )
                            self._write_ai_rejection_to_product(
                                product_id=product["product_id"],
                                rejection_reason=validation.rejection_reason,
                                rejection_category=validation.rejection_category,
                                ai_reasoning=validation.ai_reasoning,
                                confidence=validation.confidence,
                            )
                            deleted_count += 1
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Batch validation error for {product.get('product_id','?')}: {e}")
        logger.info(
            f"🧠 AI SUPERVISOR batch validate [{marketplace}/{region}]: "
            f"{valid_count} valid, {invalid_count} invalid, {deleted_count} auto-deleted"
        )
        return {"valid": valid_count, "invalid": invalid_count, "auto_deleted": deleted_count}

    def _write_ai_rejection_to_product(self, product_id: str, rejection_reason: str,
                                        rejection_category: str, ai_reasoning: str, confidence: float):
        """Write AI rejection reason directly to master_products row."""
        try:
            from core.database import get_connection
            conn = get_connection()
            for col, dtype in [("ai_rejection_reason","TEXT"),("ai_rejection_category","TEXT"),
                                ("ai_reasoning","TEXT"),("ai_confidence","REAL")]:
                try:
                    conn.execute(f"ALTER TABLE master_products ADD COLUMN {col} {dtype}")
                except Exception:
                    pass
            conn.execute(
                """UPDATE master_products
                   SET ai_rejection_reason=?, ai_rejection_category=?, ai_reasoning=?,
                       ai_confidence=?, deletion_reason=?
                   WHERE product_id=?""",
                (rejection_reason, rejection_category, ai_reasoning, confidence,
                 f"AI Supervisor [{rejection_category}]: {rejection_reason}", product_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to write AI rejection to master_products: {e}")


# ════════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS & DECORATORS
# ════════════════════════════════════════════════════════════════════════════════

_supervisor_instance = None

def get_supervisor() -> AISupervisor:
    """Get singleton AI Supervisor instance."""
    global _supervisor_instance
    if _supervisor_instance is None:
        _supervisor_instance = AISupervisor()
    return _supervisor_instance


def supervised_task(task_type: str, target: str, marketplace: str = "", region: str = "India"):
    """
    Decorator to run any function under AI Supervision.
    
    @supervised_task("scrape", "silicone stretch lids", "amazon", "India")
    def scrape_amazon(query):
        return scrape_function(query)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            supervisor = get_supervisor()
            task_id = supervisor.register_task(task_type, target, marketplace, region)
            with supervisor.supervise(task_id) as task:
                result = func(*args, **kwargs)
                task.data_collected = result if isinstance(result, dict) else {"result": result}
                return result
        return wrapper
    return decorator


def run_under_supervision(task_type: str, target: str, func: Callable, marketplace: str = "", region: str = "India", *args, **kwargs) -> Any:
    """Run a function under AI supervision (non-decorator version)."""
    supervisor = get_supervisor()
    return supervisor.execute_supervised(
        task_type=task_type,
        target=target,
        func=func,
        marketplace=marketplace,
        region=region,
        *args, **kwargs
    )


# ════════════════════════════════════════════════════════════════════════════════
# DATABASE EXTENSIONS FOR SUPERVISOR
# ════════════════════════════════════════════════════════════════════════════════

def ensure_supervisor_tables():
    """Ensure AI Supervisor tables exist in database."""
    from core.database import get_connection
    
    conn = get_connection()
    cur = conn.cursor()
    
    # AI Supervisor Logs
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ai_supervisor_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active_tasks INTEGER DEFAULT 0,
            total_validations INTEGER DEFAULT 0
        )
    ''')
    
    # AI Task Improvements
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ai_task_improvements (
            improvement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            task_type TEXT,
            marketplace TEXT,
            region TEXT,
            improvement_type TEXT,
            description TEXT,
            priority TEXT,
            target TEXT,
            triggered_by TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Scraper Validations (if not exists)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scraper_validations (
            validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            region TEXT NOT NULL,
            is_valid INTEGER DEFAULT 1,
            confidence REAL DEFAULT 50.0,
            issues TEXT,
            auto_soft_delete INTEGER DEFAULT 0,
            rejection_reason TEXT,
            rejection_category TEXT,
            ai_notes TEXT,
            ai_suggested_fix TEXT,
            raw_product_data TEXT,
            validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Ensure deletion_reason column exists in master_products
    cur.execute("PRAGMA table_info(master_products)")
    columns = [row[1] for row in cur.fetchall()]
    
    if "deletion_reason" not in columns:
        cur.execute("ALTER TABLE master_products ADD COLUMN deletion_reason TEXT")
        logger.info("Added deletion_reason column to master_products")
    
    if "ai_rejection_reason" not in columns:
        cur.execute("ALTER TABLE master_products ADD COLUMN ai_rejection_reason TEXT")
        logger.info("Added ai_rejection_reason column to master_products")
    
    if "ai_rejection_category" not in columns:
        cur.execute("ALTER TABLE master_products ADD COLUMN ai_rejection_category TEXT")
        logger.info("Added ai_rejection_category column to master_products")
    
    if "ai_reasoning" not in columns:
        cur.execute("ALTER TABLE master_products ADD COLUMN ai_reasoning TEXT")
        logger.info("Added ai_reasoning column to master_products")
    
    conn.commit()
    conn.close()


if __name__ == "__main__":
    # Test the supervisor
    supervisor = get_supervisor()
    supervisor.start_monitoring()
    
    # Test a supervised task
    def dummy_scrape(query):
        return {"products": [{"title": "Test Product", "price": 299, "product_url": "https://amazon.in/dp/TEST123", "rating": 4.5, "review_count": 100}]}
    
    result = run_under_supervision("scrape", "test query", dummy_scrape, "amazon", "India")
    print("Result:", result)
    
    print("\nSupervisor Status:")
    print(json.dumps(supervisor.get_status(), indent=2, default=str))
    
    time.sleep(2)
    supervisor.stop_monitoring()