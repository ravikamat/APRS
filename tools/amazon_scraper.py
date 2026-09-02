"""
tools/amazon_scraper.py — Amazon India Scraper using Playwright + Stealth.
Replaces curl_cffi with reliable browser automation.

Outputs: List[RawProduct] compatible with core.validation.RawProduct
"""
import asyncio
import logging
import random
import re
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from config.settings import settings
from core.validation import RawProduct

logger = logging.getLogger("aprs.amazon_scraper")


class ScraperError(Exception):
    """Raised when scraping fails unrecoverably."""
    pass




@dataclass
class ScrapedProduct:
    """Internal representation before validation."""
    marketplace: str
    product_id: str
    title: str
    price: float
    rating: Optional[float]
    review_count: int
    bsr: Optional[int]
    url: str
    image_url: Optional[str]


class AmazonScraper:
    """
    Amazon India scraper using Playwright with stealth configuration.
    
    Features:
    - Headless Chromium with stealth evasion
    - Human-like behavior (random delays, mouse movements)
    - Robust selector fallbacks
    - Rate limiting compliance
    """
    
    BASE_URL = "https://www.amazon.in"
    SEARCH_URL = "https://www.amazon.in/s"
    
    # CSS Selectors (multiple fallbacks for resilience)
    SELECTORS = {
        "product_container": [
            "[data-component-type='s-search-result']",
            ".sg-col-20of24.sg-col-28of32.sg-col-16of20.sg-col.sg-col-32of36.sg-col-8of12.sg-col-12of18.sg-col-24of28.sg-col-4of6",
            ".s-result-item[data-asin]",
        ],
        "title": [
            "h2 a span",
            ".a-text-normal",
            "#productTitle",
        ],
        "price_whole": [
            ".a-price-whole",
            ".a-offscreen",
        ],
        "price_fraction": [
            ".a-price-fraction",
        ],
        "rating": [
            "[aria-label*='stars']",
            ".a-icon-alt",
        ],
        "review_count": [
            "[aria-label*='ratings']",
            "#acrCustomerReviewText",
        ],
        "product_link": [
            "h2 a.a-link-normal",
            ".a-link-normal.s-no-outline",
        ],
        "image": [
            ".s-image",
            "#landingImage",
        ],
        "bsr": [
            "#SalesRank",
            "#detailBullets_feature_div li:has-text('Best Sellers Rank')",
        ],
        "next_page": [
            ".s-pagination-next:not(.s-pagination-disabled)",
            "a[aria-label='Go to next page']",
        ],
    }
    
    def __init__(
        self,
        headless: bool = None,
        timeout_ms: int = None,
        delay_ms: int = None,
    ):
        self.headless = headless if headless is not None else settings.playwright_headless
        self.timeout_ms = timeout_ms if timeout_ms is not None else settings.playwright_timeout_ms
        self.delay_ms = delay_ms if delay_ms is not None else settings.scraper_delay_ms
        self.user_agent = settings.scraper_user_agent
        self._browser = None
        self._context = None
        self._page = None
    
    async def __aenter__(self):
        await self._launch_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def _launch_browser(self):
        """Launch Playwright browser with stealth configuration."""
        from playwright.async_api import async_playwright
        
        self._playwright = await async_playwright().start()
        
        # Launch with stealth arguments
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1920,1080",
            ],
        )
        
        # Create context with realistic viewport and headers
        self._context = await self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1920, "height": 1080},
            locale="en-IN",
            timezone_id="Asia/Kolkata",
            extra_http_headers={
                "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        
        # Add stealth scripts
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-IN', 'en', 'hi']});
            window.chrome = {runtime: {}};
        """)
        
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.timeout_ms)
    
    async def close(self):
        """Clean up browser resources."""
        if self._page:
            await self._page.close()
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, '_playwright'):
            await self._playwright.stop()
    
    async def _human_delay(self, min_ms: int = None, max_ms: int = None):
        """Random human-like delay."""
        min_d = min_ms or self.delay_ms
        max_d = max_ms or (self.delay_ms * 2)
        await asyncio.sleep(random.uniform(min_d / 1000, max_d / 1000))
    
    async def _human_scroll(self):
        """Simulate human scrolling behavior."""
        await self._page.mouse.wheel(0, random.randint(300, 800))
        await self._human_delay(500, 1500)
    
    async def _try_selectors(self, page, selectors: List[str], attribute: str = None):
        """Try multiple selectors until one works."""
        for selector in selectors:
            try:
                elements = await page.query_selector_all(selector)
                if elements:
                    if attribute:
                        return [await el.get_attribute(attribute) for el in elements]
                    return elements
            except Exception:
                continue
        return []
    
    async def _extract_text(self, page, selectors: List[str]) -> Optional[str]:
        """Extract text content using fallback selectors."""
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    text = await element.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        return None
    
    async def _extract_attribute(self, page, selectors: List[str], attribute: str) -> Optional[str]:
        """Extract attribute using fallback selectors."""
        for selector in selectors:
            try:
                element = await page.query_selector(selector)
                if element:
                    value = await element.get_attribute(attribute)
                    if value:
                        return value
            except Exception:
                continue
        return None
    
    def _parse_price(self, whole: str, fraction: str = None) -> Optional[float]:
        """Parse price from whole and fraction parts."""
        try:
            # Clean the whole part (remove commas, currency symbols)
            clean_whole = re.sub(r"[^\d]", "", whole)
            if not clean_whole:
                return None
            price = float(clean_whole)
            if fraction:
                clean_fraction = re.sub(r"[^\d]", "", fraction)
                if clean_fraction:
                    price += float(clean_fraction) / 100
            return price
        except (ValueError, AttributeError):
            return None
    
    def _parse_rating(self, text: str) -> Optional[float]:
        """Extract rating from text like '4.5 out of 5 stars'."""
        try:
            match = re.search(r"(\d+\.?\d*)\s*(?:out of|\/)\s*5", text, re.IGNORECASE)
            if match:
                return float(match.group(1))
            # Try just a number
            match = re.search(r"(\d+\.?\d*)", text)
            if match:
                val = float(match.group(1))
                if 1.0 <= val <= 5.0:
                    return val
        except (ValueError, AttributeError):
            pass
        return None
    
    def _parse_review_count(self, text: str) -> int:
        """Extract review count from text like '1,234 ratings'."""
        try:
            # Remove non-digit characters except commas
            clean = re.sub(r"[^\d,]", "", text)
            clean = clean.replace(",", "")
            return int(clean) if clean else 0
        except (ValueError, AttributeError):
            return 0
    
    def _parse_bsr(self, text: str) -> Optional[int]:
        """Extract BSR from text like '#1,234 in Home & Kitchen'."""
        try:
            match = re.search(r"#?([\d,]+)\s*(?:in|$)", text)
            if match:
                return int(match.group(1).replace(",", ""))
        except (ValueError, AttributeError):
            pass
        return None
    
    async def search(
        self,
        keyword: str,
        max_results: int = 20,
        max_pages: int = 2,
        region: str = "India",
    ) -> List[RawProduct]:
        """
        Search Amazon for products matching keyword.
        
        Args:
            keyword: Search query
            max_results: Maximum products to return
            max_pages: Maximum pages to scrape
            region: Target region (currently only India supported)
        
        Returns:
            List of validated RawProduct objects
        """
        if not self._page:
            await self._launch_browser()
        
        products = []
        page_num = 1
        
        while len(products) < max_results and page_num <= max_pages:
            search_url = f"{self.SEARCH_URL}?k={keyword.replace(' ', '+')}&page={page_num}"
            logger.info(f"Scraping page {page_num}: {search_url}")
            
            try:
                await self._page.goto(search_url, wait_until="networkidle")
                await self._human_delay()
                await self._human_scroll()
                
                # Wait for product containers
                containers = await self._try_selectors(
                    self._page, self.SELECTORS["product_container"]
                )
                
                if not containers:
                    logger.warning(f"No product containers found on page {page_num}")
                    break
                
                logger.info(f"Found {len(containers)} product containers on page {page_num}")
                
                for container in containers:
                    if len(products) >= max_results:
                        break
                    
                    try:
                        product = await self._extract_product_from_container(container)
                        if product and self._is_valid_product(product):
                            products.append(product)
                    except Exception as e:
                        logger.debug(f"Error extracting product: {e}")
                        continue
                
                # Check for next page
                next_btn = await self._try_selectors(self._page, self.SELECTORS["next_page"])
                if not next_btn:
                    logger.info("No next page button found, stopping")
                    break
                
                page_num += 1
                await self._human_delay(2000, 4000)
                
            except Exception as e:
                logger.error(f"Error scraping page {page_num}: {e}")
                break
        
        logger.info(f"Successfully scraped {len(products)} products for '{keyword}'")
        return products
    
    async def _extract_product_from_container(self, container) -> Optional[RawProduct]:
        """Extract product data from a search result container."""
        # Extract ASIN from container
        asin = await container.get_attribute("data-asin")
        if not asin:
            # Try to get from link
            link = await container.query_selector("a.a-link-normal")
            if link:
                href = await link.get_attribute("href")
                if href:
                    match = re.search(r"/dp/([A-Z0-9]{10})", href)
                    if match:
                        asin = match.group(1)
        
        if not asin:
            return None
        
        # Extract title
        title = await self._extract_text(container, self.SELECTORS["title"])
        if not title or len(title) < 5:
            return None
        
        # Extract price
        price_whole = await self._extract_text(container, self.SELECTORS["price_whole"])
        price_fraction = await self._extract_text(container, self.SELECTORS["price_fraction"])
        price = self._parse_price(price_whole, price_fraction)
        if not price or price <= 0:
            return None
        
        # Extract rating
        rating_text = await self._extract_text(container, self.SELECTORS["rating"])
        rating = self._parse_rating(rating_text) if rating_text else None
        
        # Extract review count
        review_text = await self._extract_text(container, self.SELECTORS["review_count"])
        review_count = self._parse_review_count(review_text) if review_text else 0
        
        # Extract product URL
        product_url = await self._extract_attribute(container, self.SELECTORS["product_link"], "href")
        if product_url and not product_url.startswith("http"):
            product_url = f"{self.BASE_URL}{product_url}"
        
        # Extract image
        image_url = await self._extract_attribute(container, self.SELECTORS["image"], "src")
        
        # BSR is not typically on search results, would need detail page
        bsr = None
        
        return RawProduct(
            marketplace="amazon",
            product_id=asin,
            title=title,
            price=price,
            rating=rating or 0.0,  # Will be validated; 0 fails validation
            review_count=review_count,
            bsr=bsr,
            url=product_url or f"{self.BASE_URL}/dp/{asin}",
            image_url=image_url,
        )
    
    def _is_valid_product(self, product: RawProduct) -> bool:
        """Basic validation before returning."""
        return (
            product.price > 0
            and product.rating >= 1.0
            and product.rating <= 5.0
            and len(product.title) >= 5
            and product.url.startswith("http")
        )
    
    async def get_product_details(self, asin: str) -> Optional[RawProduct]:
        """
        Get detailed product information from product detail page.
        Includes BSR, more accurate rating/review count.
        """
        if not self._page:
            await self._launch_browser()
        
        url = f"{self.BASE_URL}/dp/{asin}"
        logger.info(f"Fetching product details: {url}")
        
        try:
            await self._page.goto(url, wait_until="networkidle")
            await self._human_delay()
            
            # Extract title
            title = await self._extract_text(self._page, ["#productTitle"])
            if not title:
                return None
            
            # Extract price
            price_whole = await self._extract_text(self._page, [".a-price .a-offscreen", "#priceblock_ourprice", "#priceblock_dealprice"])
            price = self._parse_price(price_whole) if price_whole else None
            
            # Extract rating
            rating_text = await self._extract_text(self._page, ["#averageCustomerReviews .a-icon-alt", "#acrPopover"])
            rating = self._parse_rating(rating_text) if rating_text else None
            
            # Extract review count
            review_text = await self._extract_text(self._page, ["#acrCustomerReviewText"])
            review_count = self._parse_review_count(review_text) if review_text else 0
            
            # Extract BSR
            bsr_text = await self._extract_text(self._page, ["#SalesRank", "#detailBullets_feature_div"])
            bsr = self._parse_bsr(bsr_text) if bsr_text else None
            
            # Extract image
            image_url = await self._extract_attribute(self._page, ["#landingImage", "#imgBlkFront"], "src")
            
            return RawProduct(
                marketplace="amazon",
                product_id=asin,
                title=title.strip(),
                price=price or 0.0,
                rating=rating or 0.0,
                review_count=review_count,
                bsr=bsr,
                url=url,
                image_url=image_url,
            )
        except Exception as e:
            logger.error(f"Error fetching product details for {asin}: {e}")
            return None

    def search_sync(
        self,
        keyword: str,
        max_results: int = 20,
        max_pages: int = 2,
        region: str = "India",
    ) -> List[RawProduct]:
        """Sync wrapper for search() - runs async search in event loop."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(self.search(keyword, max_results, max_pages, region))


async def search_amazon(
    keyword: str,
    max_results: int = 20,
    max_pages: int = 2,
) -> List[RawProduct]:
    """Convenience function for simple searches."""
    async with AmazonScraper() as scraper:
        return await scraper.search(keyword, max_results, max_pages)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        async with AmazonScraper(headless=True) as scraper:
            results = await scraper.search("stainless steel water bottle", max_results=5, max_pages=1)
            for r in results:
                print(f"  {r.title[:60]} | ₹{r.price} | ⭐{r.rating} | {r.review_count} reviews | {r.product_id}")
    
    asyncio.run(test())