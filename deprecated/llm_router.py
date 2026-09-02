"""
models/llm_router.py — Unified LLM Interface with NIM-Primary + Local-Fallback Routing.

Routes LLM calls to NIM (primary) with automatic fallback to local Ollama/llama.cpp
when NIM keys are exhausted or fail. Arbiter stage uses NIM only (no fallback).
"""
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field

# Project root import
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import (
    NIM_API_KEYS, NIM_BASE_URL, NIM_MODELS, SWARM_ROLES,
    LOCAL_OLLAMA_CONFIG, LOCAL_GGUF_CONFIG
)
from models.nim_cluster import SupremeNIMCluster, NIMClusterExhausted

logger = logging.getLogger("aprs.llm_router")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s — %(message)s")


class LLMProvider(str, Enum):
    NIM = "nim"
    OLLAMA = "ollama"
    LLAMACPP = "llamacpp"


class LLMTaskType(str, Enum):
    SCOUT = "scout"
    HARVESTER = "harvester"
    DEFECT_MINER = "defect_miner"
    ECONOMICS = "economics"
    ARBITER = "arbiter"
    GENERAL = "general"


@dataclass
class LLMResponse:
    content: str
    provider: LLMProvider
    model: str
    latency_ms: int
    success: bool = True
    error: Optional[str] = None
    cached: bool = False
    usage: Optional[Dict[str, Any]] = None


class LLMRouter:
    """
    Unified LLM router with priority failover:
    - NIM (primary): 3-key cluster with LRU cache
    - Ollama (fallback): Local models for high-volume stages
    - Arbiter stage: NIM ONLY (no fallback for final verdict)
    """

    # Task → Provider priority (configurable via settings.py LLM_ROUTING)
    DEFAULT_ROUTING = {
        LLMTaskType.SCOUT:        [LLMProvider.NIM, LLMProvider.OLLAMA],
        LLMTaskType.HARVESTER:    [LLMProvider.NIM, LLMProvider.OLLAMA],
        LLMTaskType.DEFECT_MINER: [LLMProvider.NIM, LLMProvider.OLLAMA],
        LLMTaskType.ECONOMICS:    [LLMProvider.NIM, LLMProvider.OLLAMA],
        LLMTaskType.ARBITER:      [LLMProvider.NIM],  # Never fallback
        LLMTaskType.GENERAL:      [LLMProvider.NIM, LLMProvider.OLLAMA],
    }

    def __init__(self):
        self.nim_cluster = SupremeNIMCluster()
        self.ollama_client = None
        self.ollama_model = None
        self._init_local()
        self._load_routing_config()

        # Metrics
        self.metrics = {
            "nim_calls": 0,
            "nim_failures": 0,
            "ollama_calls": 0,
            "ollama_failures": 0,
            "fallback_triggered": 0,
        }

    def _load_routing_config(self):
        """Load routing from environment or use defaults."""
        import os
        routing_env = os.getenv("LLM_ROUTING")
        if routing_env:
            try:
                # Format: "scout:nim,ollama;harvester:nim,ollama;arbiter:nim"
                custom = {}
                for pair in routing_env.split(";"):
                    if ":" in pair:
                        task, providers = pair.split(":")
                        custom[LLMTaskType(task.strip())] = [
                            LLMProvider(p.strip()) for p in providers.split(",")
                        ]
                self.routing = {**self.DEFAULT_ROUTING, **custom}
            except Exception as e:
                logger.warning(f"Failed to parse LLM_ROUTING env: {e}. Using defaults.")
                self.routing = self.DEFAULT_ROUTING
        else:
            self.routing = self.DEFAULT_ROUTING

    def _init_local(self):
        """Initialize Ollama/llama.cpp clients from env/config."""
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.ollama_model = os.getenv("LOCAL_OLLAMA_MODEL", os.getenv("LOCAL_QWEN_27B_MODEL", "qwen27b_iq1"))

        try:
            import ollama
            self.ollama_client = ollama.AsyncClient(host=ollama_url, timeout=60.0)
            logger.info(f"Ollama client initialized: {ollama_url} | Model: {self.ollama_model}")
        except ImportError:
            logger.warning("ollama package not installed. Local fallback unavailable. Run: pip install ollama")
        except Exception as e:
            logger.warning(f"Ollama client init failed: {e}")

    async def query(
        self,
        prompt: str,
        task_type: LLMTaskType = LLMTaskType.GENERAL,
        system_prompt: str = "You are an expert e-commerce intelligence agent. Respond in valid JSON only.",
        temperature: float = 0.1,
        max_tokens: int = 2048,
        force_json: bool = False,
        **kwargs
    ) -> LLMResponse:
        """
        Try providers in priority order until success.
        """
        providers = self.routing.get(task_type, self.DEFAULT_ROUTING[LLMTaskType.GENERAL])

        for provider in providers:
            try:
                if provider == LLMProvider.NIM:
                    return await self._query_nim(prompt, task_type, system_prompt, temperature, max_tokens, force_json)
                elif provider == LLMProvider.OLLAMA:
                    return await self._query_ollama(prompt, system_prompt, temperature, max_tokens, force_json)
            except Exception as e:
                logger.warning(f"{provider.value} failed for {task_type.value}: {e}")
                if provider == LLMProvider.NIM:
                    self.metrics["nim_failures"] += 1
                elif provider == LLMProvider.OLLAMA:
                    self.metrics["ollama_failures"] += 1
                continue

        # All providers exhausted
        raise RuntimeError(f"All LLM providers exhausted for task_type={task_type.value}")

    async def _query_nim(
        self,
        prompt: str,
        task_type: LLMTaskType,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        force_json: bool
    ) -> LLMResponse:
        """Query NVIDIA NIM cluster with caching."""
        start = time.time()

        # Map task_type to NIM model config
        nim_task_map = {
            LLMTaskType.SCOUT: "nemotron_scout",
            LLMTaskType.HARVESTER: SWARM_ROLES["marketplace_harvester"]["task_type"],
            LLMTaskType.DEFECT_MINER: SWARM_ROLES["defect_analyst"]["task_type"],
            LLMTaskType.ECONOMICS: SWARM_ROLES["economics_auditor"]["task_type"],
            LLMTaskType.ARBITER: "nemotron_arbiter",
            LLMTaskType.GENERAL: "ultra_reasoning",
        }
        nim_task = nim_task_map.get(task_type, "ultra_reasoning")

        # Use NIM cluster's query (sync, run in executor)
        loop = asyncio.get_event_loop()
        raw = await loop.run_in_executor(
            None,
            lambda: self.nim_cluster.query(
                prompt=prompt,
                task_type=nim_task,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                force_json=force_json
            )
        )

        latency_ms = int((time.time() - start) * 1000)
        self.metrics["nim_calls"] += 1

        # Extract content from NIM response
        if isinstance(raw, dict) and raw.get("success"):
            content = raw.get("content", "")
            return LLMResponse(
                content=content,
                provider=LLMProvider.NIM,
                model=raw.get("model", nim_task),
                latency_ms=latency_ms,
                cached=raw.get("cached", False),
                usage=raw
            )
        else:
            # NIMClusterExhausted or error
            error = raw.get("error", "Unknown NIM error") if isinstance(raw, dict) else str(raw)
            raise RuntimeError(f"NIM query failed: {error}")

    async def _query_ollama(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
        force_json: bool
    ) -> LLMResponse:
        """Query local Ollama model (e.g. Qwen 27B / 14B / Llama 8B GGUF fallback)."""
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        model_name = self.ollama_model or os.getenv("LOCAL_OLLAMA_MODEL", "qwen27b_iq1")
        start = time.time()

        # Build messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
        if force_json:
            messages.append({"role": "system", "content": "Respond ONLY with valid JSON. No markdown, no explanations."})

        content = ""
        # 1. Try via AsyncClient if available
        if self.ollama_client:
            try:
                response = await self.ollama_client.chat(
                    model=model_name,
                    messages=messages,
                    options={
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    },
                    format="json" if force_json else None
                )
                content = response.get("message", {}).get("content", "")
            except Exception as e:
                logger.debug(f"Ollama SDK client call failed: {e}. Falling back to direct HTTP...")

        # 2. Fallback to direct HTTP REST endpoint if SDK failed or wasn't loaded
        if not content:
            try:
                import httpx
                payload = {
                    "model": model_name,
                    "messages": messages,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                    "stream": False
                }
                if force_json:
                    payload["format"] = "json"
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(f"{ollama_url.rstrip('/')}/api/chat", json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data.get("message", {}).get("content", "")
                    else:
                        raise RuntimeError(f"Ollama HTTP {resp.status_code}: {resp.text[:200]}")
            except Exception as http_err:
                self.metrics["ollama_failures"] += 1
                raise RuntimeError(f"Ollama query failed on both SDK and HTTP: {http_err}")

        latency_ms = int((time.time() - start) * 1000)
        self.metrics["ollama_calls"] += 1
        self.metrics["fallback_triggered"] = self.metrics.get("fallback_triggered", 0) + 1

        logger.info(f"🔄 FALLBACK ACTIVATED: Switched to Local Ollama GGUF ({model_name}) | Latency: {latency_ms}ms")
        return LLMResponse(
            content=content,
            provider=LLMProvider.OLLAMA,
            model=f"ollama-local:{model_name}",
            latency_ms=latency_ms
        )

    def get_status(self) -> Dict[str, Any]:
        """Get router status and metrics."""
        nim_status = self.nim_cluster.get_cluster_status()
        return {
            "providers": {
                "nim": {
                    "available": len(self.nim_cluster.keys) > 0,
                    "keys": len(self.nim_cluster.keys),
                    "calls": self.metrics["nim_calls"],
                    "failures": self.metrics["nim_failures"],
                    "keys_status": nim_status
                },
                "ollama": {
                    "available": self.ollama_client is not None,
                    "model": self.ollama_model,
                    "calls": self.metrics["ollama_calls"],
                    "failures": self.metrics["ollama_failures"]
                }
            },
            "routing": {k.value: [p.value for p in v] for k, v in self.routing.items()},
            "metrics": {
                **self.metrics,
                "fallback_triggered": self.metrics.get("fallback_triggered", 0),
                "last_fallback_model": f"qwen:{self.ollama_model}" if self.metrics.get("fallback_triggered", 0) > 0 else None
            }
        }

    def health_check(self) -> Dict[str, bool]:
        """Quick health check of all providers."""
        return {
            "nim": len(self.nim_cluster.keys) > 0,
            "ollama": self.ollama_client is not None
        }


# Convenience function for sync usage (e.g., in existing orchestrator)
def query_sync(
    prompt: str,
    task_type: LLMTaskType = LLMTaskType.GENERAL,
    system_prompt: str = "You are an expert e-commerce intelligence agent. Respond in valid JSON only.",
    **kwargs
) -> LLMResponse:
    """Synchronous wrapper for LLMRouter.query()."""
    router = LLMRouter()
    return asyncio.run(router.query(prompt, task_type, system_prompt, **kwargs))


if __name__ == "__main__":
    async def test():
        router = LLMRouter()
        print("LLM Router Status:")
        print(json.dumps(router.get_status(), indent=2, default=str))

        # Test each task type
        for task in LLMTaskType:
            try:
                print(f"\n--- Testing {task.value} ---")
                resp = await router.query(
                    prompt='Say "hello from router" in JSON: {"msg": "..."}',
                    task_type=task,
                    force_json=True
                )
                print(f"Provider: {resp.provider.value} | Model: {resp.model} | Latency: {resp.latency_ms}ms")
                print(f"Content: {resp.content[:100]}")
            except Exception as e:
                print(f"FAILED: {e}")

    asyncio.run(test())