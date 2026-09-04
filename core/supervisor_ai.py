"""
core/supervisor_ai.py — Main AI Supervisor for APRS V7.

Accepts natural language commands from the user via the Web UI,
uses NIM 550B (via LLMRouter) to interpret and generate a structured
dispatch plan, then returns it for execution by DaemonService.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from config.settings import settings
from core.llm_router import LLMRouter, LLMTaskType

logger = logging.getLogger("aprs.supervisor")


@dataclass
class SupervisorPlan:
    """Structured plan returned by the Main AI Supervisor."""
    reasoning: str
    dispatch: List[Dict[str, Any]]
    confidence: float = 0.8


class SupervisorAI:
    """
    Main AI Supervisor — the central intelligence that interprets
    human commands and dispatches agents.
    
    Uses NIM 550B (Tier 1) for reasoning. Falls back through Groq → Ollama.
    """
    
    # Known agents in the system
    KNOWN_AGENTS = [
        "internet_crawler",
        "trend_signal", 
        "niche_expander",
        "discovery",
        "problem_miner",
        "gate_engine",
        "supplier_agent",
        "outreach_engine",
        "learning_agent",
    ]
    
    def __init__(self):
        self.router = LLMRouter()
        self._system_prompt = self._build_system_prompt()
    
    def _build_system_prompt(self) -> str:
        return """You are the Main AI Supervisor for APRS (Autonomous Product Research System).
Your job is to interpret natural language commands from the user and generate a structured dispatch plan.

AVAILABLE AGENTS:
1. internet_crawler — Crawls the web for new niche opportunities, trend signals, seed keywords
2. trend_signal — Analyzes social media, news, Google Trends for emerging product trends
3. niche_expander — Expands broad categories into specific searchable niches
4. discovery — Uses WebAgent (browser-use) to scrape real product data from Amazon.in, Flipkart, Meesho
5. problem_miner — Mines 3-star reviews using local Ollama to extract defects and v2.0 specs
6. gate_engine — Runs the 5-gate deterministic pipeline (Signal → Defects → Economics → Score → NIM Arbiter)
7. supplier_agent — Finds real suppliers on IndiaMART/Alibaba, verifies GST, gets MOQ/pricing
8. outreach_engine — Generates professional email/WhatsApp drafts using NIM 550B
9. learning_agent — Weekly synthesis of outcomes into learned rules

RULES:
- Output ONLY valid JSON, no markdown, no explanation
- The "dispatch" array contains objects with "agent" (string) and "params" (object)
- Only use agents from the KNOWN_AGENTS list
- If a command is ambiguous, ask for clarification in "reasoning" and return empty dispatch
- Typical params:
  * discovery: {"keywords": [...], "region": "India", "max_products": 10}
  * supplier_agent: {"product_id": "abc123"} or {"keywords": [...], "region": "India"}
  * problem_miner: {"product_id": "abc123"} or {"asin": "B08XYZ"}
  * gate_engine: {"product_id": "abc123"}
  * outreach_engine: {"supplier_id": 42} or {"product_id": "abc123"}
  * internet_crawler: {"keywords": [...], "platform": "web"}
  * trend_signal: {"platform": "reddit", "region": "India"}
  * niche_expander: {"category": "Kitchen", "region": "India"}

EXAMPLES:

Command: "Find suppliers for copper cookware in Moradabad"
Response: {
  "reasoning": "User wants to source copper cookware from Moradabad industrial cluster",
  "dispatch": [
    {"agent": "supplier_agent", "params": {"keywords": ["copper cookware", "copper kadai"], "region": "India", "cluster": "Moradabad"}},
    {"agent": "discovery", "params": {"keywords": ["copper cookware"], "region": "India", "max_products": 20}}
  ],
  "confidence": 0.9
}

Command: "Re-evaluate product ABC123 through all gates"
Response: {
  "reasoning": "User wants to re-run the full 5-gate pipeline for a specific product",
  "dispatch": [
    {"agent": "gate_engine", "params": {"product_id": "ABC123"}}
  ],
  "confidence": 0.95
}

Command: "Mine reviews for ASIN B08XYZ123"
Response: {
  "reasoning": "User wants to extract defect clusters from 3-star reviews for a specific ASIN",
  "dispatch": [
    {"agent": "problem_miner", "params": {"asin": "B08XYZ123"}}
  ],
  "confidence": 0.9
}

Command: "Run a full discovery cycle for kitchen niche"
Response: {
  "reasoning": "User wants to discover new products in the Kitchen category",
  "dispatch": [
    {"agent": "internet_crawler", "params": {"keywords": ["kitchen", "cookware", "utensils"], "platform": "web"}},
    {"agent": "trend_signal", "params": {"platform": "reddit", "region": "India"}},
    {"agent": "niche_expander", "params": {"category": "Kitchen", "region": "India"}},
    {"agent": "discovery", "params": {"keywords": ["kitchen", "cookware"], "region": "India", "max_products": 30}}
  ],
  "confidence": 0.85
}"""

    async def parse_command_async(self, instruction: str) -> Optional[Dict[str, Any]]:
        """
        Parse a natural language command and return a structured dispatch plan.
        
        Returns:
            Dict with keys: reasoning, dispatch, confidence
            Or None if parsing failed
        """
        logger.info(f"Supervisor parsing: {instruction}")
        
        prompt = f"""USER COMMAND:
"{instruction}"

Return ONLY valid JSON matching this schema:
{{
  "reasoning": "Brief explanation of what the user wants and which agents to dispatch",
  "dispatch": [
    {{"agent": "agent_name", "params": {{...}}}}
  ],
  "confidence": 0.0-1.0
}}"""
        
        try:
            response = await self.router.chat(
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": prompt}
                ],
                agent_name="supervisor_ai",
                task_type=LLMTaskType.DEEP_REASONING,
                json_mode=True,
                max_tokens=1500,
            )
            
            result = json.loads(response.text)
            
            # Validate structure
            if not isinstance(result, dict):
                logger.warning(f"Supervisor returned non-dict: {type(result)}")
                return None
            
            if "dispatch" not in result:
                logger.warning("Supervisor response missing 'dispatch' key")
                return None
            
            # Validate each dispatch entry
            valid_dispatch = []
            for item in result.get("dispatch", []):
                if isinstance(item, dict) and "agent" in item:
                    agent = item["agent"]
                    if agent in self.KNOWN_AGENTS:
                        valid_dispatch.append(item)
                    else:
                        logger.warning(f"Supervisor returned unknown agent: {agent}")
            
            result["dispatch"] = valid_dispatch
            result["confidence"] = float(result.get("confidence", 0.5))
            
            logger.info(f"Supervisor plan: {result['reasoning']} -> {len(valid_dispatch)} dispatches")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Supervisor JSON parse error: {e}")
            return self._fallback_plan(instruction)
        except Exception as e:
            logger.error(f"Supervisor command error: {e}")
            return self._fallback_plan(instruction)

    def parse_command(self, instruction: str) -> Optional[Dict[str, Any]]:
        """Synchronous wrapper for parse_command_async."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.parse_command_async(instruction))
    
    def _fallback_plan(self, instruction: str) -> Dict[str, Any]:
        """Simple keyword-based fallback when LLM fails."""
        instruction_lower = instruction.lower()
        dispatch = []
        
        # Supplier-related keywords
        if any(kw in instruction_lower for kw in ["supplier", "source", "factory", "manufacturer", "indiamart", "alibaba"]):
            dispatch.append({"agent": "supplier_agent", "params": {}})
        
        # Discovery/scraping keywords
        if any(kw in instruction_lower for kw in ["discover", "scrape", "find product", "search", "amazon", "flipkart", "meesho"]):
            dispatch.append({"agent": "discovery", "params": {"keywords": ["general"], "region": "India", "max_products": 10}})
        
        # Review mining keywords
        if any(kw in instruction_lower for kw in ["review", "defect", "mine", "3-star", "customer feedback"]):
            dispatch.append({"agent": "problem_miner", "params": {}})
        
        # Gate evaluation keywords
        if any(kw in instruction_lower for kw in ["gate", "evaluate", "re-evaluate", "rerun", "restart"]):
            dispatch.append({"agent": "gate_engine", "params": {}})
        
        # Outreach keywords
        if any(kw in instruction_lower for kw in ["outreach", "email", "whatsapp", "contact", "message"]):
            dispatch.append({"agent": "outreach_engine", "params": {}})
        
        # Trend/crawler keywords
        if any(kw in instruction_lower for kw in ["trend", "crawl", "niche", "keyword", "signal"]):
            dispatch.append({"agent": "internet_crawler", "params": {}})
            dispatch.append({"agent": "trend_signal", "params": {}})
            dispatch.append({"agent": "niche_expander", "params": {}})
        
        return {
            "reasoning": f"Fallback keyword matching for: {instruction}",
            "dispatch": dispatch,
            "confidence": 0.4
        }


if __name__ == "__main__":
    import asyncio
    
    async def test():
        supervisor = SupervisorAI()
        
        test_commands = [
            "Find suppliers for copper cookware in Moradabad",
            "Re-evaluate product ABC123 through all gates",
            "Mine reviews for ASIN B08XYZ123",
            "Run a full discovery cycle for kitchen niche",
        ]
        
        for cmd in test_commands:
            print(f"\n>>> {cmd}")
            result = supervisor.parse_command(cmd)
            print(json.dumps(result, indent=2))
    
    asyncio.run(test())