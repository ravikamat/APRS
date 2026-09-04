"""
integrations/agent_reach.py — Agent-Reach MCP Client for APRS V7.

Wrapper for the Agent-Reach MCP server (localhost:3000).
Provides tools for Reddit, Twitter, YouTube, RSS, and web extraction.
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

logger = logging.getLogger("aprs.agent_reach")


@dataclass
class AgentReachResponse:
    """Response from Agent-Reach MCP server."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    tool_used: str = ""


class AgentReachClient:
    """
    Client for Agent-Reach MCP Server (localhost:3000).
    
    Provides access to:
    - reddit_scraper: Get top posts from any subreddit
    - twitter_search: Search Twitter for keywords
    - youtube_transcript: Get transcript from any YouTube video URL
    - rss_subscribe: Subscribe to RSS feed, get new items
    - web_extract: Get readable text from any URL (bypasses paywalls)
    - duckduckgo_search: Web search with result snippets
    """
    
    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        import aiohttp
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=60),
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
                timeout=aiohttp.ClientTimeout(total=60),
                headers={"Content-Type": "application/json"},
            )
        return self._session
    
    async def _call_tool(self, tool_name: str, params: Dict) -> AgentReachResponse:
        """Call an Agent-Reach tool via MCP."""
        if not hasattr(self, '_session') or self._session is None or self._session.closed:
            import aiohttp
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=60),
                headers={"Content-Type": "application/json"},
            )
        
        try:
            async with self._session.post(
                f"{self.base_url}/mcp/tools/{tool_name}",
                json=params,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return AgentReachResponse(
                        success=True,
                        data=data.get("result", data),
                        tool_used=tool_name,
                    )
                else:
                    text = await resp.text()
                    return AgentReachResponse(
                        success=False,
                        error=f"HTTP {resp.status}: {text}",
                        tool_used=tool_name,
                    )
        except asyncio.TimeoutError:
            return AgentReachResponse(
                success=False,
                error="Request timeout",
                tool_used=tool_name,
            )
        except Exception as e:
            logger.error(f"Agent-Reach {tool_name} error: {e}")
            return AgentReachResponse(
                success=False,
                error=str(e),
                tool_used=tool_name,
            )
    
    # ── Reddit Scraper ──────────────────────────────────────────────────────
    
    async def reddit_scraper(
        self,
        subreddit: str,
        sort: str = "hot",
        time_filter: str = "week",
        limit: int = 25,
    ) -> AgentReachResponse:
        """Get top posts from a subreddit."""
        return await self._call_tool("reddit_scraper", {
            "subreddit": subreddit,
            "sort": sort,
            "time_filter": time_filter,
            "limit": limit,
        })
    
    async def reddit_search(
        self,
        query: str,
        subreddit: Optional[str] = None,
        sort: str = "relevance",
        time_filter: str = "week",
        limit: int = 25,
    ) -> AgentReachResponse:
        """Search Reddit for posts matching query."""
        params = {
            "query": query,
            "sort": sort,
            "time_filter": time_filter,
            "limit": limit,
        }
        if subreddit:
            params["subreddit"] = subreddit
        return await self._call_tool("reddit_search", params)
    
    async def reddit_post_comments(
        self,
        post_url: str,
        limit: int = 50,
    ) -> AgentReachResponse:
        """Get comments from a Reddit post."""
        return await self._call_tool("reddit_post_comments", {
            "post_url": post_url,
            "limit": limit,
        })
    
    # ── Twitter Search ──────────────────────────────────────────────────────
    
    async def twitter_search(
        self,
        query: str,
        max_results: int = 50,
        lang: str = "en",
    ) -> AgentReachResponse:
        """Search Twitter for tweets matching query."""
        return await self._call_tool("twitter_search", {
            "query": query,
            "max_results": max_results,
            "lang": lang,
        })
    
    async def twitter_user_timeline(
        self,
        username: str,
        max_results: int = 20,
    ) -> AgentReachResponse:
        """Get recent tweets from a user."""
        return await self._call_tool("twitter_user_timeline", {
            "username": username,
            "max_results": max_results,
        })
    
    # ── YouTube Transcript ──────────────────────────────────────────────────
    
    async def youtube_transcript(
        self,
        video_url: str,
        language: str = "en",
    ) -> AgentReachResponse:
        """Get transcript from any YouTube video URL."""
        return await self._call_tool("youtube_transcript", {
            "video_url": video_url,
            "language": language,
        })
    
    async def youtube_search(
        self,
        query: str,
        max_results: int = 20,
    ) -> AgentReachResponse:
        """Search YouTube for videos."""
        return await self._call_tool("youtube_search", {
            "query": query,
            "max_results": max_results,
        })
    
    # ── RSS Subscribe ───────────────────────────────────────────────────────
    
    async def rss_subscribe(
        self,
        feed_url: str,
        max_items: int = 50,
    ) -> AgentReachResponse:
        """Subscribe to RSS feed and get latest items."""
        return await self._call_tool("rss_subscribe", {
            "feed_url": feed_url,
            "max_items": max_items,
        })
    
    async def rss_get_new_items(
        self,
        feed_url: str,
        since: Optional[datetime] = None,
    ) -> AgentReachResponse:
        """Get new items from RSS feed since last check."""
        params = {"feed_url": feed_url}
        if since:
            params["since"] = since.isoformat()
        return await self._call_tool("rss_get_new_items", params)
    
    # ── Web Extract ─────────────────────────────────────────────────────────
    
    async def web_extract(
        self,
        url: str,
        extract_schema: Optional[Dict] = None,
    ) -> AgentReachResponse:
        """Extract structured data from any URL (bypasses paywalls)."""
        params = {"url": url}
        if extract_schema:
            params["extract_schema"] = extract_schema
        return await self._call_tool("web_extract", params)
    
    # ── DuckDuckGo Search ──────────────────────────────────────────────────
    
    async def duckduckgo_search(
        self,
        query: str,
        max_results: int = 10,
    ) -> AgentReachResponse:
        """Search DuckDuckGo for web results."""
        return await self._call_tool("duckduckgo_search", {
            "query": query,
            "max_results": max_results,
        })
    
    # ── Health Check ────────────────────────────────────────────────────────
    
    async def health_check(self) -> AgentReachResponse:
        """Check if Agent-Reach server is healthy."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health", timeout=5) as resp:
                    if resp.status == 200:
                        return AgentReachResponse(success=True, data={"status": "healthy"})
                    return AgentReachResponse(success=False, error=f"HTTP {resp.status}")
        except Exception as e:
            return AgentReachResponse(success=False, error=str(e))
    
    async def list_tools(self) -> AgentReachResponse:
        """List all available tools."""
        return await self._call_tool("list_tools", {})


# Convenience functions for common operations

async def search_reddit_for_products(
    query: str,
    subreddits: List[str] = None,
    limit_per_sub: int = 10,
) -> List[Dict]:
    """Search multiple subreddits for product discussions."""
    if subreddits is None:
        subreddits = [
            "IndiaBuy", "amazonfinds", "tiktokmademebuyit",
            "IndianBeautyDeals", "frugalmalefashion", "BuyItForLife",
            "DIY", "HomeImprovement", "malelifestyle",
        ]
    
    async with AgentReachClient() as client:
        all_posts = []
        for sub in subreddits:
            result = await client.reddit_search(query, subreddit=sub, limit=limit_per_sub)
            if result.success and result.data:
                for post in result.data.get("posts", []):
                    post["subreddit"] = sub
                    all_posts.append(post)
            await asyncio.sleep(0.5)  # Rate limiting
        return all_posts


async def get_youtube_transcript_for_product(product_name: str) -> Optional[str]:
    """Get YouTube transcript for product review."""
    async with AgentReachClient() as client:
        # Search for review videos
        search_result = await client.youtube_search(f"{product_name} review", max_results=5)
        if not search_result.success:
            return None
        
        videos = search_result.data.get("videos", [])
        for video in videos[:3]:
            video_url = video.get("url")
            if video_url:
                transcript_result = await client.youtube_transcript(video_url)
                if transcript_result.success:
                    return transcript_result.data.get("transcript", "")
    return None


async def monitor_reddit_keywords(
    keywords: List[str],
    subreddits: List[str],
    callback: callable,
    interval_minutes: int = 30,
):
    """Monitor Reddit for keyword mentions in real-time."""
    # This would be run as a background task
    pass


if __name__ == "__main__":
    async def test():
        async with AgentReachClient() as client:
            # Test health check
            health = await client.health_check()
            print(f"Health check: {health.success}")
            
            if health.success:
                # Test Reddit search
                result = await client.reddit_search("wireless headphones", subreddit="IndiaBuy", limit=5)
                print(f"Reddit search: {result.success}, {len(result.data.get('posts', []))} posts")
                
                # Test YouTube transcript
                # transcript = await client.youtube_transcript("https://youtube.com/watch?v=...")
                # print(f"Transcript: {transcript.data.get('transcript', '')[:100]}")
    
    asyncio.run(test())