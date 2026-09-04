"""
integrations/openbb_client.py — OpenBB MCP Client for APRS V7.

Wrapper for OpenBB MCP Server (localhost:3002).
Provides financial data: USD/INR rates, commodity prices, CPI, etc.
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

logger = logging.getLogger("aprs.openbb_client")


@dataclass
class OpenBBResponse:
    """Response from OpenBB MCP server."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    call: str = ""


class OpenBBClient:
    """
    Client for OpenBB MCP Server (localhost:3002).
    
    Provides access to financial data:
    - Currency exchange rates (USD/INR, etc.)
    - Commodity prices (cotton, steel, copper, etc.)
    - Economic indicators (CPI, PMI, GDP)
    - Equity data (stock prices, fundamentals)
    """
    
    def __init__(self, base_url: str = "http://localhost:3002"):
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
        """Call OpenBB MCP endpoint."""
        if not hasattr(self, '_session') or self._session is None or self._session.closed:
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
                    raise Exception(f"OpenBB HTTP {resp.status}: {text}")
        except asyncio.TimeoutError:
            raise Exception("OpenBB request timeout")
        except Exception as e:
            raise Exception(f"OpenBB request failed: {e}")
    
    # ── Currency ─────────────────────────────────────────────────────────────
    
    async def get_usd_inr_rate(self) -> float:
        """Get latest USD/INR exchange rate."""
        data = await self._call("/currency/price", {"symbol": "USDINR=X"})
        # OpenBB returns: {"price": 83.12, "timestamp": "..."}
        return float(data.get("price", 0))
    
    async def get_currency_pair(self, base: str, quote: str) -> float:
        """Get exchange rate for any currency pair."""
        symbol = f"{base}{quote}=X"
        data = await self._call("/currency/price", {"symbol": symbol})
        return float(data.get("price", 0))
    
    async def get_historical_rate(self, base: str, quote: str, days: int = 30) -> List[Dict]:
        """Get historical exchange rate data."""
        symbol = f"{base}{quote}=X"
        return await self._call("/currency/history", {
            "symbol": symbol,
            "days": days,
        })
    
    # ── Commodities ──────────────────────────────────────────────────────────
    
    async def get_commodity_price(self, commodity: str) -> float:
        """Get current commodity price.
        
        Supported: cotton, copper, steel, aluminum, crude_oil, brent, natural_gas, gold, silver
        """
        data = await self._call("/commodity/price", {"symbol": commodity.upper()})
        return float(data.get("price", 0))
    
    async def get_commodity_history(self, commodity: str, days: int = 30) -> List[Dict]:
        """Get historical commodity prices."""
        return await self._call("/commodity/history", {
            "symbol": commodity.upper(),
            "days": days,
        })
    
    # ── Economic Indicators ──────────────────────────────────────────────────
    
    async def get_india_cpi(self) -> float:
        """Get India CPI (Consumer Price Index)."""
        data = await self._call("/economy/cpi", {"country": "india"})
        return float(data.get("value", 0))
    
    async def get_india_pmi(self) -> float:
        """Get India PMI (Purchasing Managers' Index)."""
        data = await self._call("/economy/pmi", {"country": "india"})
        return float(data.get("value", 0))
    
    async def get_gdp_growth(self, country: str = "india") -> float:
        """Get GDP growth rate for a country."""
        data = await self._call("/economy/gdp", {"country": country.lower()})
        return float(data.get("growth_rate", 0))
    
    # ── Equity Data ──────────────────────────────────────────────────────────
    
    async def get_stock_price(self, symbol: str) -> float:
        """Get current stock price."""
        data = await self._call("/equity/price", {"symbol": symbol})
        return float(data.get("price", 0))
    
    async def get_stock_fundamentals(self, symbol: str) -> Dict:
        """Get stock fundamentals (P/E, P/B, ROE, etc.)."""
        return await self._call("/equity/fundamentals", {"symbol": symbol})
    
    # ── Health Check ─────────────────────────────────────────────────────────
    
    async def health_check(self) -> bool:
        """Check if OpenBB MCP server is healthy."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://localhost:3002/health", timeout=5) as resp:
                    return resp.status == 200
        except Exception:
            return False


# Convenience functions

async def get_usd_inr_rate() -> float:
    """Quick function to get USD/INR rate."""
    async with OpenBBClient() as client:
        return await client.get_usd_inr_rate()


async def get_commodity_price(commodity: str) -> float:
    """Quick function to get commodity price."""
    async with OpenBBClient() as client:
        return await client.get_commodity_price(commodity)


if __name__ == "__main__":
    async def test():
        async with OpenBBClient() as client:
            print("Testing OpenBB Client...")
            
            # Health check
            healthy = await client.health_check()
            print(f"OpenBB Health: {'OK' if healthy else 'FAILED'}")
            
            if client._session and not client._session.closed:
                # Test USD/INR
                try:
                    rate = await client.get_usd_inr_rate()
                    print(f"USD/INR Rate: {rate}")
                except Exception as e:
                    print(f"USD/INR error: {e}")
                
                # Test commodity
                try:
                    cotton_price = await client.get_commodity_price("cotton")
                    print(f"Cotton Price: {cotton_price}")
                except Exception as e:
                    print(f"Cotton price error: {e}")
    
    asyncio.run(test())