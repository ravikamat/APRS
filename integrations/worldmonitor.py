"""
integrations/worldmonitor.py — WorldMonitor MCP Client for APRS V7.

Wrapper for WorldMonitor MCP Server (localhost:3001).
Provides macro intelligence: commodity prices, country risk, consumer sentiment, trade flows.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp
import sys
from pathlib import Path

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings

logger = logging.getLogger("aprs.worldmonitor")


@dataclass
class WorldMonitorResponse:
    """Response from WorldMonitor MCP server."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    call: str = ""


class WorldMonitorClient:
    """
    Client for WorldMonitor MCP Server (localhost:3001).
    
    Provides macro intelligence:
    - Commodity prices (cotton, steel, copper, aluminum, crude oil, etc.)
    - Country risk scores (China, India, Vietnam, etc.)
    - Consumer sentiment indices
    - Import/export trade flows
    - PMI, CPI, GDP for major economies
    - Shipping/freight rates
    """
    
    def __init__(self, base_url: str = "http://localhost:3001"):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        import aiohttp
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"Content-Type": "application/json"},
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()
    
    def _get_session(self):
        if self._session is None or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Content-Type": "application/json"},
            )
        return self._session
    
    async def _call(self, endpoint: str, params: Dict = None) -> Dict:
        """Call WorldMonitor MCP endpoint."""
        if not self._session or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Content-Type": "application/json"},
            )
        
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        
        try:
            async with self._session.get(f"{self.base_url}{endpoint}", params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    text = await resp.text()
                    raise Exception(f"WorldMonitor HTTP {resp.status}: {text}")
        except asyncio.TimeoutError:
            raise Exception("WorldMonitor request timeout")
        except Exception as e:
            raise Exception(f"WorldMonitor request failed: {e}")
    
    # ── Commodity Prices ────────────────────────────────────────────────────
    
    async def get_commodity_price(self, commodity: str) -> float:
        """Get current commodity price.
        
        Supported: cotton, steel, copper, aluminum, crude_oil, brent, natural_gas, 
                   gold, silver, platinum, palladium, nickel, zinc, lead, tin
        """
        data = await self._call("/commodity/price", {"symbol": commodity.lower()})
        return float(data.get("price", 0))
    
    async def get_commodity_history(self, commodity: str, days: int = 30) -> List[Dict]:
        """Get historical commodity prices."""
        return await self._call("/commodity/history", {
            "symbol": commodity.lower(),
            "days": days,
        })
    
    async def get_multiple_commodities(self, commodities: List[str]) -> Dict[str, float]:
        """Get prices for multiple commodities at once."""
        results = {}
        for commodity in commodities:
            try:
                price = await self.get_commodity_price(commodity)
                results[commodity] = price
            except Exception as e:
                logger.warning(f"Failed to get price for {commodity}: {e}")
                results[commodity] = 0.0
        return results
    
    # ── Country Risk & Macro ─────────────────────────────────────────────────
    
    async def get_country_risk(self, country: str) -> Dict:
        """Get country risk assessment.
        
        Returns: risk_score (0-100), stability_rating, key_risks, outlook
        """
        return await self._call("/country/risk", {"country": country.lower()})
    
    async def get_country_pmi(self, country: str) -> float:
        """Get Purchasing Managers' Index for a country."""
        data = await self._call("/country/pmi", {"country": country.lower()})
        return float(data.get("pmi", 0))
    
    async def get_country_cpi(self, country: str) -> float:
        """Get Consumer Price Index for a country."""
        data = await self._call("/country/cpi", {"country": country.lower()})
        return float(data.get("cpi", 0))
    
    async def get_country_gdp_growth(self, country: str) -> float:
        """Get GDP growth rate for a country."""
        data = await self._call("/country/gdp", {"country": country.lower()})
        return float(data.get("gdp_growth", 0))
    
    async def get_country_instability(self, country: str) -> float:
        """Get country instability score (0-100)."""
        data = await self._call("/country/instability", {"country": country.lower()})
        return float(data.get("instability_score", 0))
    
    # ── Consumer Sentiment ───────────────────────────────────────────────────
    
    async def get_consumer_sentiment(self, country: str = "india") -> Dict:
        """Get consumer sentiment index."""
        return await self._call("/consumer/sentiment", {"country": country.lower()})
    
    async def get_consumer_confidence(self, country: str = "india") -> float:
        """Get consumer confidence index."""
        data = await self._call("/consumer/confidence", {"country": "india"})
        return float(data.get("index", 0))
    
    # ── Trade Flows ──────────────────────────────────────────────────────────
    
    async def get_import_export(self, country: str, partner: str = None) -> Dict:
        """Get import/export data between countries."""
        params = {"country": country.lower()}
        if partner:
            params["partner"] = partner.lower()
        return await self._call("/trade/import_export", params)
    
    async def get_trade_balance(self, country: str) -> Dict:
        """Get trade balance for a country."""
        return await self._call("/trade/balance", {"country": country.lower()})
    
    # ── Shipping & Freight ───────────────────────────────────────────────────
    
    async def get_freight_rate(self, route: str, container_type: str = "40ft") -> float:
        """Get container freight rate for a route.
        
        Example routes: "china-india", "china-usa", "europe-india", "usa-india"
        """
        data = await self._call("/freight/rate", {
            "route": route.lower(),
            "container_type": container_type,
        })
        return float(data.get("rate_usd", 0))
    
    async def get_shipping_time(self, origin: str, destination: str) -> int:
        """Get estimated shipping time in days."""
        data = await self._call("/shipping/time", {
            "origin": origin.lower(),
            "destination": destination.lower(),
        })
        return int(data.get("days", 0))
    
    async def get_port_congestion(self, port: str) -> Dict:
        """Get port congestion status."""
        return await self._call("/port/congestion", {"port": port.lower()})
    
    # ── Health Check ─────────────────────────────────────────────────────────
    
    async def health_check(self) -> bool:
        """Check if WorldMonitor MCP server is healthy."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:3001/health", timeout=5) as resp:
                    return resp.status == 200
        except Exception:
            return False


# Convenience functions

async def get_commodity_prices(commodities: List[str]) -> Dict[str, float]:
    """Get prices for multiple commodities."""
    async with WorldMonitorClient() as client:
        return await client.get_multiple_commodities(commodities)


async def get_country_risk_score(country: str) -> Dict:
    """Get country risk assessment."""
    async with WorldMonitorClient() as client:
        return await client.get_country_risk(country)


async def get_freight_rate(route: str, container_type: str = "40ft") -> float:
    """Get container freight rate for a route."""
    async with WorldMonitorClient() as client:
        return await client.get_freight_rate(route, container_type)


if __name__ == "__main__":
    async def test():
        async with WorldMonitorClient() as client:
            print("Testing WorldMonitor Client...")
            
            # Health check
            healthy = await client.health_check()
            print(f"WorldMonitor Health: {'OK' if healthy else 'FAILED'}")
            
            if healthy:
                # Test commodity prices
                commodities = ["cotton", "steel", "copper", "aluminum"]
                prices = await client.get_multiple_commodities(commodities)
                print(f"Commodity Prices: {prices}")
                
                # Test country risk
                risk = await client.get_country_risk("china")
                print(f"China Risk: {risk}")
                
                # Test freight
                freight = await client.get_freight_rate("china-india")
                print(f"China-India Freight: ${freight}")
    
    asyncio.run(test())