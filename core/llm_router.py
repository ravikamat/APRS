"""
core/llm_router.py — 5-Tier LLM Router for APRS V7.

Single entry point for ALL LLM calls in APRS.
5-tier automatic fallback with per-agent override.
No agent ever calls a model directly — they all call LLMRouter.chat().
"""

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict, Any, Optional
from pathlib import Path

import aiohttp

from config.settings import settings

logger = logging.getLogger("aprs.llm_router")


class LLMTier(Enum):
    """LLM tiers in priority order (1 = highest)."""
    NIM_550B = 1           # NIM 550B Nemotron-3-Ultra (primary, unlimited)
    OLLAMA_LOCAL = 2       # Local Ollama (qwen27b_iq1, always-on)
    GROQ_FREE = 3          # Groq Free API (Llama-3.3-70B, 14k req/day)
    KIMI_K3_LOCAL = 4      # Kimi-K3 C99 binary (2.78T params, overnight batch only)
    HUMAN_OVERRIDE = 5     # Human-in-the-loop fallback


class LLMTaskType(Enum):
    """Task types for routing and tier selection."""
    GATE4_ARBITER = "gate4_arbiter"
    GATE2_DEFECT_MINING = "gate2_defect_mining"
    GATE5_ARBITER = "gate5_arbiter"
    BROWSER_AGENT = "browser_agent"
    BULK_CLASSIFICATION = "bulk_classification"
    OUTREACH_DRAFTING = "outreach_drafting"
    WEEKLY_SYNTHESIS = "weekly_synthesis"
    SUPPLIER_ANALYSIS = "supplier_analysis"
    PROBLEM_SYNTHESIS = "problem_synthesis"
    BROWSER_USE_DRIVING = "browser_use_driving"
    WEEKLY_NICHE_REBALANCE = "weekly_niche_rebalance"
    FAST_CLASSIFICATION = "fast_classification"
    ENTITY_EXTRACTION = "entity_extraction"
    SHORT_SUMMARIES = "short_summaries"
    DEEP_REASONING = "deep_reasoning"
    OVERNIGHT_BATCH = "overnight_batch"
    GENERIC = "generic"


class LLMTaskPriority(Enum):
    """Task priority affects tier selection (e.g., Kimi-K3 only for batch)."""
    REALTIME = "realtime"
    BATCH = "batch"


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    text: str
    tier_used: int
    tier_name: str
    model: str
    latency_ms: int
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None
    task_id: Optional[str] = None


class LLMError(Exception):
    """Base exception for LLM errors."""
    pass


class RateLimitError(LLMError):
    """Rate limit exceeded."""
    pass


class ServiceUnavailable(LLMError):
    """Service temporarily unavailable."""
    pass


class TimeoutError(LLMError):
    """Request timed out."""
    pass


class LLMRouter:
    """
    Single entry point for ALL LLM calls in APRS.
    5-tier automatic fallback with per-agent override.
    
    Settings (all configurable in .env or dashboard Settings tab):
      LLM_TIER_1_ENABLED=true          # NIM 550B
      LLM_TIER_2_ENABLED=true          # Ollama
      LLM_TIER_3_ENABLED=true          # Groq free
      LLM_TIER_4_ENABLED=false         # kimi-k3 (disabled by default — slow)
      LLM_TIER_5_MANUAL_FALLBACK=true  # Human override
      
      # Per-agent override (bypasses tier ladder for specific agents):
      AGENT_GATE4_LLM=nim              # Force Gate4 to always use NIM
      AGENT_DEFECT_LLM=ollama          # Force defect mining to always use Ollama
      AGENT_SUPPLIER_LLM=nim           # Force supplier agent to use NIM
      # Set to "auto" to use normal tier ladder (default)
    """
    
    TIERS = {
        1: "nim_550b",
        2: "ollama_local", 
        3: "groq_free",
        4: "kimi_k3_local",
        5: "manual_human",
    }
    
    # Per-task default tier mapping (can be overridden by agent mode)
    TASK_DEFAULT_TIER = {
        LLMTaskType.GATE4_ARBITER: 1,
        LLMTaskType.GATE5_ARBITER: 1,
        LLMTaskType.GATE2_DEFECT_MINING: 1,  # NIM first → Groq → Ollama fallback
        LLMTaskType.BROWSER_AGENT: 1,
        LLMTaskType.BROWSER_USE_DRIVING: 1,
        LLMTaskType.BULK_CLASSIFICATION: 2,
        LLMTaskType.OUTREACH_DRAFTING: 1,
        LLMTaskType.WEEKLY_SYNTHESIS: 1,
        LLMTaskType.SUPPLIER_ANALYSIS: 1,
        LLMTaskType.PROBLEM_SYNTHESIS: 1,
        LLMTaskType.WEEKLY_NICHE_REBALANCE: 1,
        LLMTaskType.FAST_CLASSIFICATION: 3,
        LLMTaskType.ENTITY_EXTRACTION: 2,
        LLMTaskType.SHORT_SUMMARIES: 3,
        LLMTaskType.DEEP_REASONING: 1,
        LLMTaskType.OVERNIGHT_BATCH: 4,
        LLMTaskType.GENERIC: 1,
    }
    
    def __init__(self):
        self.health = {t: True for t in self.TIERS}
        self.error_counts = {t: 0 for t in self.TIERS}
        self.kimi_wrapper = None  # Lazy init
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._session:
            await self._session.close()
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=settings.web_agent_timeout_s)
            )
        return self._session
    
    def _get_agent_override(self, agent_name: str) -> Optional[int]:
        """Get per-agent tier override from settings."""
        override_map = {
            "internet_crawler": settings.agent_internet_crawler_mode,
            "trend_signal": settings.agent_trend_signal_mode,
            "niche_expander": settings.agent_niche_expander_mode,
            "discovery": settings.agent_discovery_mode,
            "problem_miner": settings.agent_problem_miner_mode,
            "gate_engine": settings.agent_gate_engine_mode,
            "supplier": settings.agent_supplier_mode,
            "outreach": settings.agent_outreach_mode,
            "learning": settings.agent_learning_mode,
            "orchestrator": settings.agent_orchestrator_mode,
        }
        
        mode = override_map.get(agent_name, "auto")
        
        if mode == "auto":
            return None
        if mode == "disabled":
            return 0
        if mode == "manual":
            return 5
        if mode.startswith("force_tier:"):
            try:
                return int(mode.split(":")[1])
            except (IndexError, ValueError):
                return None
        
        # Named tier
        tier_map = {v: k for k, v in self.TIERS.items()}
        return tier_map.get(mode.lower())
    
    def _is_tier_enabled(self, tier_num: int) -> bool:
        """Check if a tier is enabled in settings."""
        enabled_map = {
            1: settings.llm_tier_1_enabled,
            2: settings.llm_tier_2_enabled,
            3: settings.llm_tier_3_enabled,
            4: settings.llm_tier_4_enabled,
            5: settings.llm_tier_5_manual_fallback,
        }
        return enabled_map.get(tier_num, True)
    
    def _get_kimi_wrapper(self):
        """Lazy init Kimi wrapper."""
        if self.kimi_wrapper is None:
            self.kimi_wrapper = KimiK3Wrapper()
        return self.kimi_wrapper
    
    async def chat(
        self,
        messages: List[Dict],
        agent_name: str = "default",
        task_type: LLMTaskType = LLMTaskType.GENERIC,
        task_priority: LLMTaskPriority = LLMTaskPriority.REALTIME,
        json_mode: bool = False,
        max_tokens: int = 2048,
        force_tier: Optional[int] = None,
    ) -> LLMResponse:
        """
        Call LLM with automatic 5-tier fallback.
        
        Returns LLMResponse with: text, tier_used, tier_name, model, latency_ms, tokens_used
        """
        start_time = time.time()
        
        # Check per-agent override from settings
        agent_override = self._get_agent_override(agent_name)
        
        # Determine starting tier
        start_tier = force_tier or agent_override or self.TASK_DEFAULT_TIER.get(task_type, 1)
        
        for tier_num in range(start_tier, 6):
            if not self._is_tier_enabled(tier_num):
                continue
            if not self.health[tier_num]:
                continue
            
            # Tier 4 (kimi-k3) only for batch tasks — skip if realtime
            if tier_num == 4 and task_priority == LLMTaskPriority.REALTIME:
                continue
            
            try:
                result = await self._call_tier(tier_num, messages, json_mode, max_tokens)
                result.latency_ms = int((time.time() - start_time) * 1000)
                result.tier_used = tier_num
                result.tier_name = self.TIERS[tier_num]
                
                # Success — reset error count for this tier
                self.error_counts[tier_num] = 0
                self.health[tier_num] = True
                
                # Log which tier was used (for monitoring dashboard)
                logger.info(f"LLM call for '{agent_name}' ({task_type.value}) used Tier {tier_num} ({self.TIERS[tier_num]})")
                
                return result
                
            except (RateLimitError, TimeoutError, ServiceUnavailable) as e:
                self.error_counts[tier_num] += 1
                if self.error_counts[tier_num] >= 3:
                    self.health[tier_num] = False  # mark tier unhealthy
                    logger.warning(f"Tier {tier_num} ({self.TIERS[tier_num]}) marked unhealthy after 3 errors: {e}")
                continue  # try next tier
            
            except Exception as e:
                logger.error(f"Tier {tier_num} ({self.TIERS[tier_num]}) unexpected error: {e}")
                self.error_counts[tier_num] += 1
                continue
        
        # All tiers failed → Tier 5: human override
        return await self._human_override(messages, agent_name, task_type, start_time)
    
    async def _call_tier(self, tier: int, messages: List[Dict], json_mode: bool, max_tokens: int) -> LLMResponse:
        """Dispatch to appropriate tier implementation."""
        if tier == 1:
            return await self._call_nim(messages, json_mode, max_tokens)
        if tier == 2:
            return await self._call_ollama(messages, json_mode, max_tokens)
        if tier == 3:
            return await self._call_groq(messages, json_mode, max_tokens)
        if tier == 4:
            return await self._get_kimi_wrapper().chat(messages, max_tokens)
        
        raise ValueError(f"Invalid tier: {tier}")
    
    async def _call_nim(self, messages: List[Dict], json_mode: bool, max_tokens: int) -> LLMResponse:
        """Call NIM 550B via OpenAI-compatible API."""
        if not settings.nim_api_key:
            raise ServiceUnavailable("NIM_API_KEY not configured")
        
        session = self._get_session()
        payload = {
            "model": settings.nim_model,
            "messages": messages,
            "temperature": settings.nim_temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        headers = {
            "Authorization": f"Bearer {settings.nim_api_key}",
            "Content-Type": "application/json",
        }
        
        start = time.time()
        async with session.post(
            f"{settings.nim_base_url}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            latency_ms = int((time.time() - start) * 1000)
            
            if resp.status == 429:
                raise RateLimitError("NIM rate limit exceeded")
            if resp.status >= 500:
                raise ServiceUnavailable(f"NIM HTTP {resp.status}")
            if resp.status != 200:
                text = await resp.text()
                raise ServiceUnavailable(f"NIM HTTP {resp.status}: {text}")
            
            data = await resp.json()
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            
            return LLMResponse(
                text=content,
                tier_used=1,
                tier_name="nim_550b",
                model=settings.nim_model,
                latency_ms=latency_ms,
                tokens_used=usage.get("total_tokens", 0),
            )
    
    async def _call_ollama(self, messages: List[Dict], json_mode: bool, max_tokens: int) -> LLMResponse:
        """Call local Ollama via HTTP API."""
        if not settings.ollama_url:
            raise ServiceUnavailable("OLLAMA_URL not configured")
        
        # Convert messages to Ollama format
        prompt = self._messages_to_prompt(messages)
        
        payload = {
            "model": settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": settings.ollama_temperature,
                "num_predict": max_tokens,
            },
        }
        if json_mode:
            payload["format"] = "json"
        
        session = self._get_session()
        start = time.time()
        async with session.post(
            f"{settings.ollama_url}/api/generate",
            json=payload,
        ) as resp:
            latency_ms = int((time.time() - start) * 1000)
            
            if resp.status != 200:
                text = await resp.text()
                raise ServiceUnavailable(f"Ollama HTTP {resp.status}: {text}")
            
            data = await resp.json()
            content = data.get("response", "")
            
            return LLMResponse(
                text=content,
                tier_used=2,
                tier_name="ollama_local",
                model=settings.ollama_model,
                latency_ms=latency_ms,
            )
    
    async def _call_groq(self, messages: List[Dict], json_mode: bool, max_tokens: int) -> LLMResponse:
        """Call Groq Free API (OpenAI-compatible)."""
        if not settings.groq_api_key:
            raise ServiceUnavailable("GROQ_API_KEY not configured")
        
        session = self._get_session()
        payload = {
            "model": settings.groq_model,
            "messages": messages,
            "temperature": settings.groq_temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        headers = {
            "Authorization": f"Bearer {settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        
        start = time.time()
        async with session.post(
            f"{settings.groq_base_url}/chat/completions",
            json=payload,
            headers=headers,
        ) as resp:
            latency_ms = int((time.time() - start) * 1000)
            
            if resp.status == 429:
                raise RateLimitError("Groq rate limit exceeded")
            if resp.status >= 500:
                raise ServiceUnavailable(f"Groq HTTP {resp.status}")
            if resp.status != 200:
                text = await resp.text()
                raise ServiceUnavailable(f"Groq HTTP {resp.status}: {text}")
            
            data = await resp.json()
            choice = data.get("choices", [{}])[0]
            content = choice.get("message", {}).get("content", "")
            usage = data.get("usage", {})
            
            return LLMResponse(
                text=content,
                tier_used=3,
                tier_name="groq_free",
                model=settings.groq_model,
                latency_ms=latency_ms,
                tokens_used=usage.get("total_tokens", 0),
            )
    
    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        """Convert OpenAI-style messages to a single prompt for Ollama."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        return "\n\n".join(parts)
    
    async def _human_override(
        self, 
        messages: List[Dict], 
        agent_name: str, 
        task_type: LLMTaskType,
        start_time: float,
    ) -> LLMResponse:
        """Tier 5: Human override via pending_human_decisions table."""
        from core.database import record_pending_decision
        
        # Write task to pending_human_decisions DB table
        task_id = await record_pending_decision(
            agent_name=agent_name,
            task_type=task_type.value,
            context=messages,
            options=[
                {"label": "Approve", "action": "approve"},
                {"label": "Reject", "action": "reject"},
                {"label": "Modify", "action": "modify"},
            ],
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        logger.critical(
            f"ALL LLM TIERS FAILED for {agent_name}. "
            f"Human override required. Task ID: {task_id}"
        )
        
        return LLMResponse(
            text="AWAITING_HUMAN",
            tier_used=5,
            tier_name="manual_human",
            model="human",
            latency_ms=latency_ms,
            task_id=task_id,
        )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status of all tiers for dashboard."""
        return {
            "tiers": {
                self.TIERS[t]: {
                    "enabled": self._is_tier_enabled(t),
                    "healthy": self.health[t],
                    "errors": self.error_counts[t],
                }
                for t in range(1, 6)
            },
            "agent_overrides": {
                agent: self._get_agent_override(agent)
                for agent in [
                    "internet_crawler", "trend_signal", "niche_expander", "discovery",
                    "problem_miner", "gate_engine", "supplier", "outreach",
                    "learning", "orchestrator",
                ]
            }
        }


class KimiK3Wrapper:
    """
    Wraps the kimi-k3-in-c C99 binary via subprocess.
    
    IMPORTANT constraints:
    - Requires 1.56 TB model checkpoint on disk (not included — must download)
    - Linux x86-64 only (binary won't run on Windows natively)
    - 26.5 s/token on 8GB RAM — use ONLY for batch overnight tasks
    - Windows workaround: run inside WSL2 or Docker Linux container
    
    Setup (one-time):
      1. WSL2: wsl --install
      2. Inside WSL: cd /mnt/h/trade/kimi-k3-in-c && make
      3. Download 1.56 TB checkpoint (Hugging Face: moonshotai/Kimi-K3)
      4. Set KIMI_MODEL_PATH in .env
    
    Practical reality:
    - At 26.5 s/token, a 200-token response = ~88 minutes
    - ONLY suitable for: weekly synthesis report, overnight deep analysis,
      one-time product category deep dive (schedule Sunday 00:00, done by 06:00)
    - NOT suitable for: any real-time decision, scraping, gate validation
    """
    
    def __init__(self):
        self.binary_path = "wsl /mnt/h/trade/kimi-k3-in-c/bin/k3"
    
    def is_available(self) -> bool:
        """Check: WSL installed + binary compiled + model checkpoint exists."""
        try:
            result = subprocess.run(["wsl", "--status"], capture_output=True, timeout=5)
            model_path = settings.kimi_model_path
            return result.returncode == 0 and Path(model_path).exists()
        except Exception:
            return False
    
    async def chat(self, messages: List[Dict], max_tokens: int = 100) -> LLMResponse:
        """Call kimi-k3 binary via WSL subprocess."""
        if not self.is_available():
            raise ServiceUnavailable("kimi-k3 not available (WSL/binary/model missing)")
        
        # Convert messages to a single prompt (kimi-k3 is a base model, no chat template)
        prompt = self._messages_to_prompt(messages)
        
        cmd = [
            "wsl", "/mnt/h/trade/kimi-k3-in-c/bin/k3",
            settings.kimi_model_path,
            "--trunk", settings.kimi_trunk_path,
            "--preset", settings.kimi_preset,  # "laptop" | "server"
            "--tok", settings.kimi_model_path,
            "--prompt", prompt,
            "--gen", str(max_tokens),
            "--incremental"
        ]
        
        start = time.time()
        try:
            # Use asyncio subprocess for non-blocking
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=max_tokens * 35  # 35s/token safety buffer
            )
            
            latency_ms = int((time.time() - start) * 1000)
            
            if proc.returncode != 0:
                raise ServiceUnavailable(f"kimi-k3 exited with code {proc.returncode}: {stderr.decode()}")
            
            # Parse output between "--- generated text ---" markers
            output = self._extract_generated_text(stdout.decode())
            
            return LLMResponse(
                text=output,
                tier_used=4,
                tier_name="kimi_k3_local",
                model="kimi-k3-2.78T",
                latency_ms=latency_ms,
            )
            
        except asyncio.TimeoutError:
            raise TimeoutError(f"kimi-k3 timed out after {max_tokens * 35}s")
        except Exception as e:
            raise ServiceUnavailable(f"kimi-k3 error: {e}")
    
    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        """Convert messages to prompt for kimi-k3 base model."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        return "\n\n".join(parts)
    
    def _extract_generated_text(self, stdout: str) -> str:
        """Extract generated text from kimi-k3 output."""
        # kimi-k3 outputs generated text between markers
        import re
        match = re.search(r"--- generated text ---\s*(.*?)\s*---", stdout, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Fallback: return last N lines
        lines = stdout.strip().split('\n')
        return '\n'.join(lines[-5:]) if lines else ""


if __name__ == "__main__":
    # Quick test
    async def test():
        async with LLMRouter() as router:
            # Test health status
            print("Health status:", router.get_health_status())
            
            # Test a simple call (will use NIM if available, otherwise fallback)
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'hello world' in JSON: {\"msg\": \"...\"}"}
            ]
            response = await router.chat(
                messages=messages,
                agent_name="test",
                task_type=LLMTaskType.GENERIC,
                json_mode=True,
                max_tokens=50,
            )
            print(f"Response: {response.text}")
            print(f"Tier used: {response.tier_name} (tier {response.tier_used})")
            print(f"Latency: {response.latency_ms}ms")
    
    asyncio.run(test())