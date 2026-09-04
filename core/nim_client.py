"""
core/nim_client.py — NIM 550B Client for APRS V7.

High-level client for NVIDIA Nemotron-3-Ultra-550B via OpenAI-compatible API.
Handles connection pooling, retries, caching, and health monitoring.
"""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

from config.settings import settings

logger = logging.getLogger("aprs.nim_client")


@dataclass
class NIMResponse:
    """NIM API response wrapper."""
    content: str
    model: str
    latency_ms: int
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None
    cached: bool = False


class NIMClient:
    """
    NIM 550B Client with connection pooling, LRU caching, and health monitoring.
    
    Features:
    - Connection pooling via aiohttp
    - LRU cache for repeated prompts
    - Automatic retries with exponential backoff
    - Health monitoring
    - Token usage tracking
    """
    
    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        max_concurrent: int = 10,
        cache_size: int = 1000,
        cache_ttl: int = 3600,
    ):
        self.api_key = api_key or settings.nim_api_key
        self.base_url = base_url or settings.nim_base_url
        self.model = model or settings.nim_model
        self.max_concurrent = max_concurrent
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl
        
        self._cache: Dict[str, tuple] = {}  # key -> (response, timestamp)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Health tracking
        self.health = True
        self.error_count = 0
        self.last_error: Optional[str] = None
        self.call_count = 0
        self.cache_hits = 0
        self.cache_misses = 0
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=settings.web_agent_timeout_s),
            connector=aiohttp.TCPConnector(limit=settings.web_agent_max_steps),
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=settings.web_agent_timeout_s),
                connector=aiohttp.TCPConnector(limit=settings.web_agent_max_steps),
            )
        return self._session
    
    def _cache_key(self, prompt: str, temperature: float, max_tokens: int, json_mode: bool) -> str:
        """Generate cache key from request parameters."""
        content = f"{prompt}|{temperature}|{max_tokens}|{json_mode}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    def _get_cached(self, key: str) -> Optional[NIMResponse]:
        """Get cached response if still valid."""
        if key in self._cache:
            response, timestamp = self._cache[key]
            if time.time() - timestamp < self.cache_ttl:
                self.cache_hits += 1
                response.cached = True
                return response
            else:
                # Expired
                del self._cache[key]
        self.cache_misses += 1
        return None
    
    def _cache_response(self, key: str, response: NIMResponse):
        """Cache response with timestamp."""
        # LRU eviction if cache full
        if len(self._cache) >= self.cache_size:
            # Remove oldest entry
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        
        self._cache[key] = (response, time.time())
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        json_mode: bool = False,
        use_cache: bool = True,
    ) -> NIMResponse:
        """
        Send chat completion request to NIM 550B.
        
        Args:
            messages: OpenAI-style messages list
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            json_mode: Force JSON output format
            use_cache: Whether to use LRU cache
            
        Returns:
            NIMResponse with content and metadata
        """
        if not self.api_key:
            return NIMResponse(
                content="",
                model=self.model,
                latency_ms=0,
                success=False,
                error="NIM_API_KEY not configured",
            )
        
        # Check cache
        cache_key = self._cache_key(
            str(messages), temperature, max_tokens, json_mode
        )
        
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached:
                return cached
        
        async with self._semaphore:
            return await self._do_request(
                messages, temperature, max_tokens, json_mode, cache_key
            )
    
    async def _do_request(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        cache_key: str,
    ) -> NIMResponse:
        """Execute the actual HTTP request with retries."""
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=settings.web_agent_timeout_s),
                connector=aiohttp.TCPConnector(limit=20),
            )
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        start = time.time()
        last_error = None
        
        for attempt in range(3):  # 3 retries
            try:
                async with self._session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                ) as resp:
                    latency_ms = int((time.time() - start) * 1000)
                    
                    if resp.status == 429:
                        # Rate limited - wait and retry
                        wait_time = 2 ** attempt
                        logger.warning(f"NIM rate limited, waiting {wait_time}s (attempt {attempt + 1}/3)")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    if resp.status >= 500:
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status,
                            message=f"NIM HTTP {resp.status}"
                        )
                    
                    if resp.status != 200:
                        text = await resp.text()
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status,
                            message=f"NIM HTTP {resp.status}: {text}"
                        )
                    
                    data = await resp.json()
                    choice = data.get("choices", [{}])[0]
                    content = choice.get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    
                    response = NIMResponse(
                        content=content,
                        model=self.model,
                        latency_ms=latency_ms,
                        tokens_used=usage.get("total_tokens", 0),
                        success=True,
                    )
                    
                    # Cache successful response
                    if cache_key:
                        self._cache_response(cache_key, response)
                    
                    self.health = True
                    self.error_count = 0
                    self.call_count += 1
                    
                    return response
                    
            except asyncio.TimeoutError:
                last_error = "Request timeout"
                logger.warning(f"NIM request timeout (attempt {attempt + 1}/3)")
            except aiohttp.ClientResponseError as e:
                last_error = f"HTTP {e.status}: {e.message}"
                if e.status >= 500:
                    # Server error - retry
                    pass
                elif e.status == 429:
                    # Rate limit - wait longer
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                else:
                    # Client error - don't retry
                    break
            except aiohttp.ClientError as e:
                last_error = f"Client error: {e}"
                logger.warning(f"NIM client error (attempt {attempt + 1}/3): {e}")
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.error(f"NIM unexpected error: {e}")
            
            # Exponential backoff before retry
            await asyncio.sleep(2 ** attempt)
        
        # All retries failed
        self.error_count += 1
        self.last_error = last_error or "All retries failed"
        self.health = False
        
        return NIMResponse(
            content="",
            model=self.model,
            latency_ms=0,
            success=False,
            error=last_error or "All retries failed",
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics for monitoring."""
        total_requests = self.cache_hits + self.cache_misses
        cache_hit_rate = self.cache_hits / total_requests if total_requests > 0 else 0
        
        return {
            "health": self.health,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "call_count": self.call_count,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_hit_rate": round(cache_hit_rate, 3),
            "cache_size": len(self._cache),
            "max_concurrent": self.max_concurrent,
        }
    
    def clear_cache(self):
        """Clear the response cache."""
        self._cache.clear()
        self.cache_hits = 0
        self.cache_misses = 0
    
    async def health_check(self) -> bool:
        """Quick health check - try a minimal request."""
        try:
            response = await self.chat(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0.0,
                use_cache=False,
            )
            return response.success
        except Exception:
            return False


# Global singleton instance
_nim_client: Optional[NIMClient] = None


def get_nim_client() -> NIMClient:
    """Get or create the global NIM client singleton."""
    global _nim_client
    if _nim_client is None:
        _nim_client = NIMClient()
    return _nim_client


# Convenience function for quick calls
async def nim_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> NIMResponse:
    """Quick NIM chat call using global client."""
    client = get_nim_client()
    return await client.chat(messages, temperature, max_tokens, json_mode)


if __name__ == "__main__":
    async def test():
        async with NIMClient() as client:
            print("NIM Client Stats:", client.get_stats())
            
            # Test health check
            healthy = await client.health_check()
            print(f"Health check: {'OK' if healthy else 'FAILED'}")
            
            if client.api_key:
                # Test a simple call
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Say 'hello world' in JSON: {\"msg\": \"...\"}"}
                ]
                response = await client.chat(messages, temperature=0.1, max_tokens=50, json_mode=True)
                print(f"Response: {response.content}")
                print(f"Latency: {response.latency_ms}ms, Tokens: {response.tokens_used}")
                print(f"Cached: {response.cached}")
            else:
                print("No NIM_API_KEY configured, skipping chat test")
            
            print("\nFinal Stats:", client.get_stats())
    
    asyncio.run(test())