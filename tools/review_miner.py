"""
tools/review_miner.py — LLM-powered defect extraction for APRS V7.

Extracts actionable product defects from 3-star customer reviews using
a SINGLE LLM call per product via the 5-tier LLMRouter.

Fallback chain: NIM 550B → Groq → Ollama (qwen3:latest) → Kimi-K3 → Human
If all fail, returns empty defect list (graceful degradation).

Design constraints:
- One LLM call per product (not per review)
- Routed through LLMRouter for automatic fallback
- Structured JSON output via prompt engineering
- Input: Aggregated 3-star review texts (top 20 by helpfulness)
- Output: List of defects with severity and suggested fixes
"""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120

# Load prompt template from external file
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_DEFECT_PROMPT_PATH = _PROMPTS_DIR / "defect_extraction.txt"


def _load_prompt_template() -> str:
    """Load the defect extraction prompt template from disk."""
    if _DEFECT_PROMPT_PATH.exists():
        raw = _DEFECT_PROMPT_PATH.read_text(encoding="utf-8")
        lines = raw.split("\n")
        start = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith('"""') and not stripped.startswith("Version") and not stripped.startswith("Updated") and not stripped.startswith("Used by") and not stripped.startswith("System prompt"):
                start = i
                break
        return "\n".join(lines[start:])
    # Fallback inline prompt if file is missing
    return (
        'You are a product quality analyst. Analyze the following 3-star reviews '
        'for the product: "{product_title}".\n\n'
        'Reviews:\n{reviews_text}\n\n'
        'Identify 3-5 specific defects. For each: defect, frequency (common/occasional/rare), '
        'severity (critical/major/minor), suggested_fix.\n'
        'Also propose 3 v2.0 improvements.\n'
        'Respond ONLY in valid JSON:\n'
        '{{"defects": [{{"defect":"...", "frequency":"...", "severity":"...", "suggested_fix":"..."}}], '
        '"v2_spec": {{"improvement_1":"...", "improvement_2":"...", "improvement_3":"..."}}}}'
    )


_PROMPT_TEMPLATE = _load_prompt_template()


class ReviewMiner:
    """
    Extracts actionable product defects from 3-star reviews.

    V7: Routes through LLMRouter (NIM → Groq → Ollama fallback).
    Falls back to direct Ollama if LLMRouter is unavailable.

    Usage:
        miner = ReviewMiner()
        result = await miner.extract_defects("Bamboo Spice Rack", reviews_list)
        # result = {"defects": [...], "v2_spec": {...}}
    """

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self._router = None

    def _get_router(self):
        """Lazy-load LLMRouter to avoid circular imports."""
        if self._router is None:
            from core.llm_router import LLMRouter
            self._router = LLMRouter()
        return self._router

    async def extract_defects(
        self,
        product_title: str,
        reviews: List[str],
        max_reviews: int = 20,
    ) -> Dict[str, Any]:
        """
        Extract actionable defects from 3-star reviews.

        Uses LLMRouter with task_type=GATE2_DEFECT_MINING for 5-tier fallback.
        """
        if not reviews:
            logger.info("No reviews provided for '%s', skipping defect mining", product_title)
            return {"defects": [], "v2_spec": {}}

        # Aggregate reviews into prompt (cap at max_reviews)
        truncated = reviews[:max_reviews]
        reviews_text = "\n---\n".join(
            [f"Review {i + 1}: {r}" for i, r in enumerate(truncated)]
        )

        # Format prompt from template
        prompt = _PROMPT_TEMPLATE.format(
            product_title=product_title,
            reviews_text=reviews_text,
        )

        # Try LLMRouter first (NIM → Groq → Ollama → Kimi → Human)
        try:
            from core.llm_router import LLMTaskType
            router = self._get_router()
            messages = [
                {"role": "system", "content": "You are a product quality analyst. Respond ONLY in valid JSON."},
                {"role": "user", "content": prompt},
            ]
            response = await router.chat(
                messages=messages,
                agent_name="review_miner",
                task_type=LLMTaskType.GATE2_DEFECT_MINING,
                json_mode=True,
                max_tokens=800,
            )
            result = self._parse_json_response(response.text)
            logger.info(
                "Defect mining for '%s': %d defects via %s (Tier %d, %dms)",
                product_title,
                len(result.get("defects", [])),
                response.tier_name,
                response.tier_used,
                response.latency_ms,
            )
            return result

        except Exception as e:
            logger.warning("LLMRouter failed for '%s': %s — trying direct Ollama", product_title, e)

        # Fallback: direct Ollama call (if LLMRouter completely fails)
        try:
            response_text = await self._query_ollama_direct(prompt)
            result = self._parse_json_response(response_text)
            logger.info(
                "Defect mining for '%s': %d defects via direct Ollama fallback",
                product_title,
                len(result.get("defects", [])),
            )
            return result
        except Exception as e:
            logger.error("All LLM attempts failed for '%s': %s", product_title, e)
            return {"defects": [], "v2_spec": {}, "error": str(e)}

    async def _query_ollama_direct(self, prompt: str) -> str:
        """Direct Ollama call — last-resort fallback if LLMRouter is broken."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 800,
                    },
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")

    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Parse the LLM JSON response with fallback handling."""
        if not text or not text.strip():
            return {"defects": [], "v2_spec": {}, "parse_error": "empty_response"}

        # Try direct JSON parse
        try:
            result = json.loads(text)
            if "defects" not in result:
                result["defects"] = []
            if "v2_spec" not in result:
                result["v2_spec"] = {}
            # Validate defect entries
            validated_defects = []
            for d in result["defects"]:
                if isinstance(d, dict) and "defect" in d:
                    validated_defects.append({
                        "defect": str(d.get("defect", ""))[:100],
                        "frequency": str(d.get("frequency", "occasional")),
                        "severity": str(d.get("severity", "minor")),
                        "suggested_fix": str(d.get("suggested_fix", ""))[:150],
                    })
            result["defects"] = validated_defects
            return result
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        import re
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return {"defects": [], "v2_spec": {}, "parse_error": "invalid_json"}

    async def health_check(self) -> bool:
        """Check if Ollama is reachable and the model is available."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{settings.ollama_url}/api/tags",
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                available = any(settings.ollama_model in m for m in models)
                if not available:
                    logger.warning(
                        "Model '%s' not found in Ollama. Available: %s",
                        settings.ollama_model,
                        models,
                    )
                return available
        except Exception as e:
            logger.error("Ollama health check failed: %s", e)
            return False
