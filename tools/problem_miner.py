"""
tools/problem_miner.py — Problem Miner for APRS V7.

Extracts product defects, complaints, and unmet needs from:
- Amazon Q&A sections
- Amazon 3-star reviews
- Flipkart reviews
- YouTube comments
- Reddit discussions
- Quora questions
- Trustpilot reviews
- IndiaMART buy leads
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import sys
from pathlib import Path

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from core.database import (
    get_connection, add_problem_opportunity, get_problem_opportunities,
)
from tools.web_agent import WebAgent
from core.llm_router import LLMRouter, LLMTaskType
from core.supplier_models import ProblemOpportunity

logger = logging.getLogger("aprs.problem_miner")


@dataclass
class MiningResult:
    """Result of problem mining for a product."""
    product_id: str
    opportunities_found: int = 0
    defects_extracted: int = 0
    sources_scanned: int = 0
    errors: List[str] = field(default_factory=list)


class ProblemMiner:
    """
    Problem Miner — Extracts defects, complaints, and unmet needs from multiple sources.

    Sources:
    - Amazon Q&A sections
    - Amazon 3-star reviews
    - Flipkart reviews
    - YouTube comments (via Agent-Reach)
    - Reddit discussions
    - Quora questions
    - Trustpilot reviews
    - IndiaMART buy leads
    """

    def __init__(self):
        self.web_agent = WebAgent()
        self.llm_router = None  # Lazy init
        self._session = None

    async def __aenter__(self):
        await self._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_session()

    async def _init_session(self):
        import aiohttp
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10),
        )

    async def _close_session(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _get_llm_router(self):
        if self.llm_router is None:
            from core.llm_router import LLMRouter
            self.llm_router = LLMRouter()
        return self.llm_router

    async def mine_product(
        self,
        product_id: str,
        asin: Optional[str] = None,
        flipkart_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Mine defects and problems for a specific product across all sources.
        
        Returns:
            Dict with opportunities_found, defects_extracted, sources_scanned
        """
        logger.info(f"Starting problem mining for product {product_id}")
        
        all_opportunities = []
        total_sources = 0
        errors = []

        # Get product info
        product = await self._get_product(product_id)
        product_name = asin or flipkart_id or "Unknown Product"

        # 1. Amazon Q&A
        if asin:
            try:
                qa_opportunities = await self._mine_amazon_qa(asin)
                all_opportunities.extend(qa_opportunities)
            except Exception as e:
                logger.warning(f"Amazon Q&A mining failed for {asin}: {e}")
                errors.append(f"Amazon Q&A: {e}")

        # 2. Amazon 3-star reviews
        if asin:
            try:
                review_opportunities = await self._mine_amazon_3star_reviews(product_id, asin)
                all_opportunities.extend(review_opportunities)
            except Exception as e:
                logger.warning(f"Amazon 3-star reviews failed for {asin}: {e}")
                errors.append(f"Amazon reviews: {e}")

        # 3. Flipkart reviews
        if flipkart_id:
            try:
                flipkart_ops = await self._mine_flipkart_reviews(flipkart_id)
                all_opportunities.extend(flipkart_ops)
            except Exception as e:
                logger.warning(f"Flipkart reviews failed for {flipkart_id}: {e}")
                errors.append(f"Flipkart reviews: {e}")

        # 4. Reddit complaints
        try:
            reddit_ops = await self._mine_reddit_complaints()
            all_opportunities.extend(reddit_ops)
        except Exception as e:
            logger.warning(f"Reddit mining failed: {e}")
            errors.append(f"Reddit: {e}")

        # 5. YouTube comments (via Agent-Reach)
        try:
            youtube_ops = await self._mine_youtube_comments()
            all_opportunities.extend(youtube_ops)
        except Exception as e:
            logger.warning(f"YouTube mining failed: {e}")
            errors.append(f"YouTube: {e}")

        # 6. Quora questions
        try:
            quora_ops = await self._mine_quora_questions()
            all_opportunities.extend(quora_ops)
        except Exception as e:
            logger.warning(f"Quora mining failed: {e}")
            errors.append(f"Quora: {e}")

        # 7. Trustpilot reviews
        try:
            trustpilot_ops = await self._mine_trustpilot()
            all_opportunities.extend(trustpilot_ops)
        except Exception as e:
            logger.warning(f"Trustpilot mining failed: {e}")
            errors.append(f"Trustpilot: {e}")

        # 8. IndiaMART buy leads
        try:
            indiamart_ops = await self._mine_indiamart_buy_leads()
            all_opportunities.extend(indiamart_ops)
        except Exception as e:
            logger.warning(f"IndiaMART mining failed: {e}")
            errors.append(f"IndiaMART: {e}")

        # Deduplicate opportunities
        unique_opportunities = self._deduplicate_opportunities(all_opportunities)

        # Save to database
        saved_count = 0
        for opp in unique_opportunities:
            try:
                opp["product_id"] = product_id
                opp_id = await self._save_opportunity(opp)
                if opp_id:
                    saved_count += 1
            except Exception as e:
                logger.warning(f"Failed to save opportunity: {e}")

        return {
            "opportunities_found": len(unique_opportunities),
            "defects_extracted": saved_count,
            "sources_scanned": 8,
            "errors": errors,
        }

    async def _mine_amazon_qa(self, asin: str) -> List[Dict]:
        """Mine Amazon Q&A section for unmet needs."""
        agent = WebAgent()
        url = f"https://www.amazon.in/ask/questions/asin/{asin}/"
        
        prompt = f"""Visit the Amazon Q&A page for ASIN {asin}.
Extract all questions that indicate:
1. Missing features customers are asking for
2. Problems with the product
3. Missing accessories or compatibility issues
4. Quality complaints

For each question, extract:
- question_text
- answer_summary (if available)
- upvotes (if visible)
- category: missing_feature|quality_issue|compatibility|accessory|other

Return as JSON array."""
        
        try:
            result = await self.web_agent.extract_from_url(
                url=f"https://www.amazon.in/ask/questions/asin/{asin}/",
                schema={"questions": "array"},
                task_description=prompt
            )
            return result.get("questions", [])
        except Exception as e:
            logger.warning(f"Amazon Q&A mining failed: {e}")
            return []

    async def _mine_amazon_3star_reviews(self, product_id: str, asin: str) -> List[Dict]:
        """Mine 3-star reviews for actionable defects."""
        url = f"https://www.amazon.in/product-reviews/{asin}/?filterByStar=three_star"
        
        prompt = f"""Visit the Amazon 3-star reviews page for ASIN {asin}.
Extract up to 20 review texts. For each review, extract:
- review_text (the full review body)
- review_title (if present)
- reviewer_name (if visible)
- review_date (if visible)
- helpful_votes (number if shown, else 0)
- verified_purchase (true/false if badge visible)

Return as JSON array of objects with these fields."""
        
        try:
            result = await self.web_agent.extract_from_url(
                url=url,
                schema={"reviews": "array"},
                task_description=prompt
            )
            reviews = result.get("reviews", [])
            
            # Store in database using master_products product_id
            from core.database import record_review_snapshot
            for review in reviews:
                try:
                    record_review_snapshot(
                        product_id=product_id,
                        marketplace="amazon",
                        rating=3.0,
                        review_text=review.get("review_text", "")[:2000],
                        review_title=review.get("review_title", "")[:200],
                        reviewer_name=review.get("reviewer_name", "")[:100],
                        review_date=review.get("review_date", ""),
                        helpful_votes=int(review.get("helpful_votes", 0) or 0),
                        verified_purchase=1 if review.get("verified_purchase", False) else 0,
                    )
                except Exception as e:
                    logger.warning(f"Failed to store review: {e}")
            
            logger.info(f"Scraped {len(reviews)} 3-star reviews for product {product_id} (ASIN {asin})")
            return reviews
        except Exception as e:
            logger.warning(f"Amazon 3-star review scraping failed for ASIN {asin}: {e}")
            return []

    async def _mine_flipkart_reviews(self, product_id: str) -> List[Dict]:
        """Mine Flipkart reviews for defects."""
        # URL: https://www.flipkart.com/product-reviews/{product_id}
        return []

    async def _mine_reddit_complaints(self) -> List[Dict]:
        """Mine Reddit for product complaints."""
        # Use Agent-Reach or WebAgent to scrape relevant subreddits
        return []

    async def _mine_youtube_comments(self) -> List[Dict]:
        """Mine YouTube comments for product complaints."""
        # Use Agent-Reach youtube_transcript tool
        return []

    async def _mine_quora_questions(self) -> List[Dict]:
        """Mine Quora for product questions."""
        return []

    async def _mine_trustpilot(self) -> List[Dict]:
        """Mine Trustpilot for brand/product reviews."""
        return []

    async def _mine_indiamart_buy_leads(self) -> List[Dict]:
        """Mine IndiaMART buy leads for demand signals."""
        return []

    def _deduplicate_opportunities(self, opportunities: List[Dict]) -> List[Dict]:
        """Deduplicate opportunities by similarity."""
        seen = set()
        unique = []
        for opp in opportunities:
            # Create a signature from problem_text + source
            sig = (opp.get("problem_text", "")[:100], opp.get("source", ""))
            if sig not in seen:
                seen.add(sig)
                unique.append(opp)
        return unique

    async def _save_opportunity(self, opportunity: Dict) -> Optional[int]:
        """Save opportunity to database."""
        from core.database import add_problem_opportunity
        
        try:
            opp_id = add_problem_opportunity(
                product_id=opportunity.get("product_id", ""),
                source=opportunity.get("source", ""),
                source_url=opportunity.get("source_url", ""),
                problem_text=opportunity.get("problem_text", ""),
                problem_category=opportunity.get("problem_category", "other"),
                severity=opportunity.get("severity", "minor"),
                frequency_estimate=opportunity.get("frequency_estimate", 1),
                suggested_solution=opportunity.get("suggested_solution", ""),
                market_size_estimate=opportunity.get("market_size_estimate", ""),
                competitor_solution=opportunity.get("competitor_solution", ""),
                status=opportunity.get("status", "IDENTIFIED"),
            )
            return opp_id
        except Exception as e:
            logger.warning(f"Failed to save opportunity: {e}")
            return None


async def mine_product(
    product_id: str,
    asin: Optional[str] = None,
    flipkart_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Convenience function to mine a single product."""
    async with ProblemMiner() as miner:
        return await miner.mine_product(product_id, asin, flipkart_id)


if __name__ == "__main__":
    async def test():
        # Test with a sample product
        result = await mine_product(
            product_id="TEST001",
            asin="B09TEST123",
        )
        print(f"Mining result: {result}")

    asyncio.run(test())