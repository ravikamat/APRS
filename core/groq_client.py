"""
core/groq_client.py — Groq Free Tier Client for APRS V7.

Client for Groq Free API (Llama-3.3-70B, Mixtral-8x7B).
OpenAI-compatible API with generous free tier limits.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import aiohttp

from config.settings import settings

logger = logging.getLogger("aprs.groq_client")


@dataclass
class GroqResponse:
    """Groq API response wrapper."""
    content: str
    model: str
    latency_ms: int
    tokens_used: int = 0
    success: bool = True
    error: Optional[str] = None
    cached: bool = False


class GroqClient:
    """
    Groq Free Tier Client for fast classification and extraction tasks.
    
    Free tier limits:
    - 14,400 requests/day
    - 6,000 tokens/minute
    - 30 RPM (requests per minute)
    
    Models available:
    - llama-3.3-70b-versatile (default, best quality)
    - llama-3.1-8b-instant (fastest)
    - mixtral-8x7b-32768 (large context)
    - gemma2-9b-it (fast)
    """
    
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
        base_url: str = None,
        max_concurrent: int = 5,
    ):
        self.api_key = api_key or settings.groq_api_key
        self.model = model or settings.groq_model
        self.base_url = base_url or settings.groq_base_url
        self.max_concurrent = max_concurrent
        
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Health tracking
        self.health = True
        self.error_count = 0
        self.last_error: Optional[str] = None
        self.call_count = 0
    
    async def __aenter__(self):
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10),
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
    
    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=aiohttp.TCPConnector(limit=10),
            )
        return self._session
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> GroqResponse:
        """
        Send chat completion request to Groq API.
        
        Args:
            messages: OpenAI-style messages list
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            json_mode: Force JSON output format
            
        Returns:
            GroqResponse with content and metadata
        """
        if not self.api_key:
            return GroqResponse(
                content="",
                model=self.model,
                latency_ms=0,
                success=False,
                error="GROQ_API_KEY not configured",
            )
        
        async with self._semaphore:
            return await self._do_request(messages, temperature, max_tokens, json_mode)
    
    async def _do_request(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> GroqResponse:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                connector=aiohttp.TCPConnector(limit=10),
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
        
        for attempt in range(3):
            try:
                async with self._session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                ) as resp:
                    latency_ms = int((time.time() - start) * 1000)
                    
                    if resp.status == 429:
                        # Rate limited - wait and retry
                        wait_time = 5 * (attempt + 1)
                        logger.warning(f"Groq rate limited, waiting {wait_time}s (attempt {attempt + 1}/3)")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    if resp.status >= 500:
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status,
                            message=f"Groq HTTP {resp.status}"
                        )
                    
                    if resp.status != 200:
                        text = await resp.text()
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status,
                            message=f"Groq HTTP {resp.status}: {text}"
                        )
                    
                    data = await resp.json()
                    choice = data.get("choices", [{}])[0]
                    content = choice.get("message", {}).get("content", "")
                    usage = data.get("usage", {})
                    
                    response = GroqResponse(
                        content=content,
                        model=self.model,
                        latency_ms=latency_ms,
                        tokens_used=usage.get("total_tokens", 0),
                        success=True,
                    )
                    
                    self.health = True
                    self.error_count = 0
                    self.call_count += 1
                    
                    return response
                    
            except asyncio.TimeoutError:
                last_error = "Request timeout"
                logger.warning(f"Groq request timeout (attempt {attempt + 1}/3)")
            except aiohttp.ClientResponseError as e:
                last_error = f"HTTP {e.status}: {e.message}"
                if e.status >= 500:
                    pass  # retry
                elif e.status == 429:
                    await asyncio.sleep(5 * (attempt + 1))
                    continue
                else:
                    break  # client error, don't retry
            except aiohttp.ClientError as e:
                last_error = f"Client error: {e}"
                logger.warning(f"Groq client error (attempt {attempt + 1}/3): {e}")
            except Exception as e:
                last_error = f"Unexpected error: {e}"
                logger.error(f"Groq unexpected error: {e}")
            
            await asyncio.sleep(2 ** attempt)
        
        # All retries failed
        self.error_count += 1
        self.last_error = last_error or "All retries failed"
        self.health = False
        
        return GroqResponse(
            content="",
            model=self.model,
            latency_ms=0,
            success=False,
            error=last_error or "All retries failed",
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics for monitoring."""
        return {
            "health": self.health,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "call_count": self.call_count,
        }
    
    async def health_check(self) -> bool:
        """Quick health check - try a minimal request."""
        try:
            response = await self.chat(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
                temperature=0.0,
            )
            return response.success
        except Exception:
            return False


# Global singleton instance
_groq_client: Optional[GroqClient] = None


def get_groq_client() -> GroqClient:
    """Get or create the global Groq client singleton."""
    global _groq_client
    if _groq_client is None:
        _groq_client = GroqClient()
    return _groq_client


# Convenience function
async def groq_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.1,
    max_tokens: int = 2048,
    json_mode: bool = False,
) -> GroqResponse:
    """Quick Groq chat call using global client."""
    client = get_groq_client()
    return await client.chat(messages, temperature, max_tokens, json_mode)


if __name__ == "__main__":
    async def test():
        async with GroqClient() as client:
            print("Groq Client Stats:", client.get_stats())
            
            healthy = await client.health_check()
            print(f"Health check: {'OK' if healthy else 'FAILED'}")
            
            if client.api_key:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Say 'hello world' in JSON: {\"msg\": \"...\"}"}
                ]
                response = await client.chat(messages, temperature=0.1, max_tokens=50, json_mode=True)
                print(f"Response: {response.content}")
                print(f"Latency: {response.latency_ms}ms, Tokens: {response.tokens_used}")
            else:
                print("No GROQ_API_KEY configured, skipping chat test")
            
            print("\nFinal Stats:", client.get_stats())
    
    asyncio.run(test())