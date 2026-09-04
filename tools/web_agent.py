"""
tools/web_agent.py - Universal Browser Agent for APRS V7.

Replaces all individual scrapers (amazon_scraper.py, flipkart_scraper.py) and
supplier discovery with a single browser-use Agent driven by NIM 550B.

Architecture:
  - ONE agent, any website, zero CSS selector maintenance
  - NIM 550B reads pages like a human and extracts structured data
  - Ollama fallback if NIM is unavailable
  - Structured output: always returns List[RawProduct] or List[SupplierProfile]

Usage:
    agent = WebAgent()

    # Product discovery (any marketplace)
    products = await agent.search_products(
        query="bamboo spice rack",
        site="amazon.in",
        max_results=10
    )

    # Supplier discovery (IndiaMART, Alibaba, ExportersIndia)
    suppliers = await agent.find_suppliers(
        product_spec="bamboo spice rack with 6 compartments",
        cluster="Moradabad",
        max_results=8
    )

    # Generic: read any page and extract structured data
    data = await agent.extract_from_url(
        url="https://dir.indiamart.com/search.mp?ss=bamboo+spice+rack",
        extract_schema={"company": str, "gst": str, "moq": int}
    )
"""
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_BU_PATH = _ROOT / "tools" / "browser-use"
if str(_BU_PATH) not in sys.path:
    sys.path.insert(0, str(_BU_PATH))

from config.settings import settings
from core.validation import RawProduct

logger = logging.getLogger("aprs.web_agent")


# ---------------------------------------------------------------------------
# LLM factory: NIM 550B via OpenAI-compatible API, Ollama fallback
# ---------------------------------------------------------------------------

def _build_nim_llm():
    """Return NIM 550B as a browser-use compatible LLM."""
    from browser_use.llm.openai.like import ChatOpenAILike
    return ChatOpenAILike(
        model=settings.nim_model,
        api_key=settings.nim_api_key,
        base_url=settings.nim_base_url,
        temperature=0.1,
        max_tokens=4096,
    )


def _build_ollama_llm():
    """Return local Ollama as a browser-use compatible LLM (fallback)."""
    from browser_use.llm.ollama.chat import ChatOllama
    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_url,
        temperature=0.1,
    )


def _get_llm():
    """Return NIM if configured, else Ollama."""
    if settings.nim_api_key and settings.nim_arbiter_enabled:
        try:
            return _build_nim_llm()
        except Exception as e:
            logger.warning(f"NIM LLM init failed ({e}), falling back to Ollama")
    return _build_ollama_llm()


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

PRODUCT_SEARCH_PROMPT = """
You are a product data extraction agent for an e-commerce research tool.

Task: Search for "{query}" on {site} and extract product listings.

For each product (up to {max_results}), extract:
- title: exact product title
- price: numeric price in local currency (number only, no symbols)
- rating: star rating (e.g. 4.2)
- review_count: number of ratings/reviews (integer)
- product_id: ASIN (Amazon) or product ID (Flipkart/Meesho)
- url: full product URL
- marketplace: site name (e.g. "amazon_in", "flipkart", "meesho")
- bsr: Best Seller Rank if visible (integer, null if not shown)
- image_url: main product image URL if available

Rules:
- Skip sponsored/ad products
- Skip products with price = 0 or missing
- Extract only organic search results
- Return as a JSON array

Return ONLY valid JSON array, no explanation:
[{{"title": "...", "price": 799.0, "rating": 4.3, ...}}, ...]
"""

SUPPLIER_SEARCH_PROMPT = """
You are a supplier intelligence agent for an Indian e-commerce sourcing platform.

Task: Find verified suppliers for "{product_spec}" {cluster_text}.

Search on: {platform}

For each supplier (up to {max_results}), extract:
- company_name: full company/business name
- platform: which site you found them on
- profile_url: full URL to their profile/listing
- contact_phone: phone number if visible (string)
- contact_email: email if visible (string or null)
- gst_number: GST number if shown (format: 15 alphanumeric chars, or null)
- moq_estimate: minimum order quantity (integer, or null if not shown)
- verification_badge: true if platform shows "verified supplier" / "gold supplier" badge
- product_categories: what they sell (brief description)
- location: city/state

Rules:
- Prioritize verified/certified suppliers
- Skip brokers and trading companies if manufacturer is available
- Skip suppliers with no contact info

Return ONLY valid JSON array, no explanation:
[{{"company_name": "...", "platform": "indiamart", "gst_number": "...", ...}}, ...]
"""

GENERIC_EXTRACT_PROMPT = """
You are a data extraction agent.

Task: Visit this URL and extract the requested data.
URL: {url}

Extract the following fields from the page:
{schema_description}

Return ONLY valid JSON with the extracted data. If a field is not found, use null.
"""


# ---------------------------------------------------------------------------
# WebAgent: universal browser agent
# ---------------------------------------------------------------------------

class WebAgent:
    """
    Universal AI browser agent powered by browser-use + NIM 550B.

    Replaces all site-specific scrapers with a single agent that reads
    any webpage and extracts structured data using NIM's understanding
    of page content.
    """

    # Sites this agent knows how to search
    SITE_URLS = {
        "amazon_in": "https://www.amazon.in/s?k={query}",
        "amazon.in": "https://www.amazon.in/s?k={query}",
        "flipkart": "https://www.flipkart.com/search?q={query}",
        "meesho": "https://www.meesho.com/search?q={query}",
    }

    SUPPLIER_PLATFORMS = {
        "indiamart": "https://dir.indiamart.com/search.mp?ss={query}",
        "alibaba": "https://www.alibaba.com/trade/search?SearchText={query}",
        "exportersindia": "https://www.exportersindia.com/search/?search={query}",
    }

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._llm = None  # lazy init

    def _get_llm(self):
        if self._llm is None:
            self._llm = _get_llm()
        return self._llm

    async def _run_agent_task(self, task: str, start_url: str = None,
                               timeout_seconds: int = 120) -> str:
        """
        Run a browser-use Agent with the given task and return its output text.
        """
        from browser_use import Agent, Browser, BrowserProfile

        browser = Browser(
            BrowserProfile(
                headless=self.headless,
                user_agent=settings.scraper_user_agent,
                viewport={"width": 1280, "height": 900},
            )
        )

        agent = Agent(
            task=task,
            llm=self._get_llm(),
            browser=browser,
            max_steps=20,
        )

        try:
            result = await asyncio.wait_for(agent.run(), timeout=timeout_seconds)
            # browser-use returns AgentHistoryList; get the final output
            if hasattr(result, 'final_result'):
                return result.final_result() or ""
            return str(result)
        except asyncio.TimeoutError:
            logger.warning(f"WebAgent task timed out after {timeout_seconds}s")
            return ""
        except Exception as e:
            logger.error(f"WebAgent task failed: {e}")
            return ""
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    def _parse_json_output(self, raw: str, expected_type: str = "list") -> Any:
        """
        Extract and parse JSON from agent output.
        Handles markdown code blocks and partial JSON.
        """
        if not raw:
            return [] if expected_type == "list" else {}

        # Strip markdown code fences
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip().rstrip("```").strip()

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract just the JSON portion
            import re
            if expected_type == "list":
                match = re.search(r'\[.*\]', raw, re.DOTALL)
            else:
                match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning(f"Could not parse JSON from agent output: {raw[:200]}")
            return [] if expected_type == "list" else {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def search_products(
        self,
        query: str,
        site: str = "amazon_in",
        max_results: int = 10,
        region: str = "India",
    ) -> List[RawProduct]:
        """
        Search for products on any marketplace and return validated RawProduct list.

        Args:
            query: Search query (e.g. "bamboo spice rack")
            site: Marketplace key ("amazon_in", "flipkart", "meesho")
            max_results: Maximum products to extract
            region: Target region for context

        Returns:
            List of validated RawProduct objects
        """
        logger.info(f"[WebAgent] Searching '{query}' on {site} (max={max_results})")

        url_template = self.SITE_URLS.get(site.lower(), self.SITE_URLS["amazon_in"])
        start_url = url_template.format(query=query.replace(" ", "+"))

        task = PRODUCT_SEARCH_PROMPT.format(
            query=query,
            site=site,
            max_results=max_results,
        ) + f"\n\nStart at: {start_url}"

        raw_output = await self._run_agent_task(task, timeout_seconds=180)
        extracted = self._parse_json_output(raw_output, "list")

        # Convert to RawProduct, drop invalid
        products: List[RawProduct] = []
        for item in extracted:
            if not isinstance(item, dict):
                continue
            try:
                # Normalize marketplace key
                if "marketplace" not in item or not item["marketplace"]:
                    item["marketplace"] = site.replace(".", "_").replace("-", "_")
                p = RawProduct(**{k: v for k, v in item.items()
                                  if k in RawProduct.model_fields})
                products.append(p)
            except Exception as e:
                logger.debug(f"Skipping invalid product: {e}")

        logger.info(f"[WebAgent] Extracted {len(products)} valid products from {site}")
        return products

    async def find_suppliers(
        self,
        product_spec: str,
        cluster: str = "",
        platforms: List[str] = None,
        max_results: int = 8,
    ) -> List[Dict]:
        """
        Find and extract supplier information from IndiaMART, Alibaba, ExportersIndia.

        Args:
            product_spec: What you want to source (e.g. "bamboo spice rack 6-compartment")
            cluster: Manufacturing cluster to focus on (e.g. "Moradabad", "Rajkot")
            platforms: Which platforms to search (default: indiamart + alibaba)
            max_results: Max suppliers to return

        Returns:
            List of supplier dicts (raw, before GST verification)
        """
        if platforms is None:
            platforms = ["indiamart", "alibaba"]

        cluster_text = f"in {cluster}" if cluster else "in India"
        query = f"{product_spec} {cluster}".strip()
        all_suppliers: List[Dict] = []

        for platform in platforms:
            if len(all_suppliers) >= max_results:
                break

            url_template = self.SUPPLIER_PLATFORMS.get(platform)
            if not url_template:
                logger.warning(f"Unknown supplier platform: {platform}")
                continue

            start_url = url_template.format(query=query.replace(" ", "+"))
            remaining = max_results - len(all_suppliers)

            task = SUPPLIER_SEARCH_PROMPT.format(
                product_spec=product_spec,
                cluster_text=cluster_text,
                platform=platform,
                max_results=remaining,
            ) + f"\n\nStart at: {start_url}"

            logger.info(f"[WebAgent] Searching suppliers on {platform} for '{query}'")
            raw_output = await self._run_agent_task(task, timeout_seconds=180)
            extracted = self._parse_json_output(raw_output, "list")

            for item in extracted:
                if isinstance(item, dict) and item.get("company_name"):
                    all_suppliers.append(item)

            logger.info(f"[WebAgent] Found {len(extracted)} suppliers on {platform}")
            # Small delay between platforms
            await asyncio.sleep(2)

        logger.info(f"[WebAgent] Total suppliers found: {len(all_suppliers)}")
        return all_suppliers[:max_results]

    async def extract_from_url(
        self,
        url: str,
        schema: Dict[str, Any],
        task_description: str = "",
    ) -> Dict:
        """
        Generic: visit any URL and extract fields described in schema.

        Args:
            url: Target URL
            schema: Dict of {field_name: type_hint_or_description}
            task_description: Optional extra instructions

        Returns:
            Dict of extracted values
        """
        schema_desc = "\n".join(f"- {k}: {v}" for k, v in schema.items())
        task = GENERIC_EXTRACT_PROMPT.format(
            url=url,
            schema_description=schema_desc,
        )
        if task_description:
            task = task_description + "\n\n" + task

        raw_output = await self._run_agent_task(task, timeout_seconds=120)
        return self._parse_json_output(raw_output, "dict")

    async def search_all_marketplaces(
        self,
        query: str,
        max_per_site: int = 5,
        region: str = "India",
    ) -> List[RawProduct]:
        """
        Search Amazon.in + Flipkart + Meesho in parallel for a query.
        Returns combined, deduplicated RawProduct list.
        """
        sites = ["amazon_in", "flipkart", "meesho"]

        tasks = [
            self.search_products(query, site=s, max_results=max_per_site, region=region)
            for s in sites
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_products: List[RawProduct] = []
        for site, result in zip(sites, results):
            if isinstance(result, Exception):
                logger.warning(f"[WebAgent] {site} search failed: {result}")
            else:
                all_products.extend(result)

        logger.info(f"[WebAgent] Total across all marketplaces: {len(all_products)}")
        return all_products


# ---------------------------------------------------------------------------
# CLI quick-test
# ---------------------------------------------------------------------------

async def _demo():
    agent = WebAgent(headless=False)  # visible for demo
    print("[demo] Searching 'bamboo spice rack' on amazon.in...")
    products = await agent.search_products("bamboo spice rack", site="amazon_in", max_results=5)
    for p in products:
        print(f"  {p.title[:60]:60s} ₹{p.price:>8.0f}  ★{p.rating}")

    print("\n[demo] Finding suppliers on IndiaMART...")
    suppliers = await agent.find_suppliers("bamboo spice rack", cluster="Moradabad", max_results=3)
    for s in suppliers:
        print(f"  {s.get('company_name','?')[:50]:50s}  GST:{s.get('gst_number','N/A')}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_demo())
