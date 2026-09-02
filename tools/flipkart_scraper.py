"""
tools/flipkart_scraper.py — Flipkart Scraper using Playwright + Stealth.
India's largest e-commerce marketplace scraper.

Outputs: List[RawProduct] compatible with core.validation.RawProduct
"""
import asyncio
import logging
import random
import re
from typing import List, Optional

from config.settings import settings
from core.validation import RawProduct

logger = logging.getLogger("aprs.flipkart_scraper")


class FlipkartScraper:
    """
    Flipkart scraper using Playwright with stealth configuration.
    
    Features:
    - Headless Chromium with stealth evasion
    - Handles Flipkart's dynamic content loading
    - Robust selector fallbacks for Flipkart's changing DOM
    - Rate limiting compliance
    """
    
    BASE_URL = "https://www.flipkart.com"
    SEARCH_URL = "https://www.flipkart.com/search"
    
    # CSS Selectors for Flipkart (multiple fallbacks)
    SELECTORS = {
        "product_container": [
            "[data-id]",
            "._1AtVbE",
            "._2kHMtA",
            ".col-12-12",  # Grid items
        ],
        "title": [
            "._4rR01T",
            ".s1Q9rs",
            "._2WkVRV",
            ".IRpwTa",
            "a[title]",
        ],
        "price": [
            "._30jeq3",
            "._1_WHN1",
            "._25b18c",
        ],
        "rating": [
            "._3LWZlK",
            "._2_R_DZ",
        ],
        "review_count": [
            "._2_R_DZ span",
            "._38sUEc",
        ],
        "product_link": [
            "._1fQZEK",
            "._2rpwqI",
            "a[href*='/p/']",
        ],
        "image": [
            "._396cs4",
            "._2r_T1I",
            "img[src*='flipkart']",
        ],
        "next_page": [
            "._1LKTO3:not(._3F8Vm_)",
            "a[aria-label='Next']",
            ".nav-next:not(.disabled)",
        ],
        "pid": [
            "[data-id]",
            "a[href*='/p/']",
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
    
    def _parse_price(self, text: str) -> Optional[float]:
        """Parse price from text like '₹1,299' or '₹1,299.00'."""
        try:
            # Remove currency symbol and commas
            clean = re.sub(r"[₹,\s]", "", text)
            # Handle decimal
            if "." in clean:
                return float(clean)
            return float(clean)
        except (ValueError, AttributeError):
            return None
    
    def _parse_rating(self, text: str) -> Optional[float]:
        """Extract rating from text like '4.5' or '4.5 ★'."""
        try:
            match = re.search(r"(\d+\.?\d*)", text)
            if match:
                val = float(match.group(1))
                if 1.0 <= val <= 5.0:
                    return val
        except (ValueError, AttributeError):
            pass
        return None
    
    def _parse_review_count(self, text: str) -> int:
        """Extract review count from text like '1,234 Reviews' or '1.2K Ratings'."""
        try:
            # Handle K notation
            text = text.upper().strip()
            if 'K' in text:
                num = float(re.sub(r"[^\d.]", "", text))
                return int(num * 1000)
            # Regular number with commas
            clean = re.sub(r"[^\d,]", "", text)
            clean = clean.replace(",", "")
            return int(clean) if clean else 0
        except (ValueError, AttributeError):
            return 0
    
    def _extract_pid(self, href: str) -> Optional[str]:
        """Extract Product ID (PID) from Flipkart URL."""
        # Flipkart URLs: /p/item/p/itm123456 or /product-name/p/itm123456
        match = re.search(r"/p/([a-zA-Z0-9]+)", href)
        if match:
            return match.group(1)
        # Also check data-id attribute
        return None
    
    async def search(
        self,
        keyword: str,
        max_results: int = 20,
        max_pages: int = 2,
        region: str = "India",
    ) -> List[RawProduct]:
        """
        Search Flipkart for products matching keyword.
        
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
            search_url = f"{self.SEARCH_URL}?q={keyword.replace(' ', '%20')}&page={page_num}"
            logger.info(f"Scraping Flipkart page {page_num}: {search_url}")
            
            try:
                await self._page.goto(search_url, wait_until="networkidle")
                await self._human_delay()
                await self._human_scroll()
                
                # Handle login popup if present
                await self._handle_popups()
                
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
                logger.error(f"Error scraping Flipkart page {page_num}: {e}")
                break
        
        logger.info(f"Successfully scraped {len(products)} products for '{keyword}' from Flipkart")
        return products
    
    async def _handle_popups(self):
        """Handle common Flipkart popups (login, notifications)."""
        popup_selectors = [
            "button._2KpZ6l._2doB4z",  # Close login popup
            "._3dsJAO ._2KpZ6l",  # Close notification
            "[aria-label='Close']",
        ]
        for selector in popup_selectors:
            try:
                btn = await self._page.query_selector(selector)
                if btn:
                    await btn.click()
                    await self._human_delay(500, 1000)
            except Exception:
                pass
    
    async def _extract_product_from_container(self, container) -> Optional[RawProduct]:
        """Extract product data from a search result container."""
        # Extract PID from container or link
        pid = await container.get_attribute("data-id")
        if not pid:
            link = await container.query_selector("a[href*='/p/']")
            if link:
                href = await link.get_attribute("href")
                if href:
                    pid = self._extract_pid(href)
        
        if not pid:
            return None
        
        # Extract title
        title = await self._extract_text(container, self.SELECTORS["title"])
        if not title or len(title) < 5:
            return None
        
        # Extract price
        price_text = await self._extract_text(container, self.SELECTORS["price"])
        price = self._parse_price(price_text) if price_text else None
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
        
        # Flipkart doesn't expose BSR on search results
        bsr = None
        
        return RawProduct(
            marketplace="flipkart",
            product_id=pid,
            title=title.strip(),
            price=price,
            rating=rating or 0.0,
            review_count=review_count,
            bsr=bsr,
            url=product_url or f"{self.BASE_URL}/p/{pid}",
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
    
    async def get_product_details(self, pid: str) -> Optional[RawProduct]:
        """
        Get detailed product information from product detail page.
        """
        if not self._page:
            await self._launch_browser()
        
        url = f"{self.BASE_URL}/p/{pid}"
        logger.info(f"Fetching Flipkart product details: {url}")
        
        try:
            await self._page.goto(url, wait_until="networkidle")
            await self._human_delay()
            await self._handle_popups()
            
            # Extract title
            title = await self._extract_text(self._page, ["span.B_NuCI", "h1._3eWWd-", "._35KyD6"])
            if not title:
                return None
            
            # Extract price
            price_text = await self._extract_text(self._page, ["div._30jeq3._16Jk6d", "._3qQ9m1", "._1_WHN1"])
            price = self._parse_price(price_text) if price_text else None
            
            # Extract rating
            rating_text = await self._extract_text(self._page, ["div._3LWZlK", "._2_R_DZ"])
            rating = self._parse_rating(rating_text) if rating_text else None
            
            # Extract review count
            review_text = await self._extract_text(self._page, ["span._2_R_DZ", "._38sUEc"])
            review_count = self._parse_review_count(review_text) if review_text else 0
            
            # Extract image
            image_url = await self._extract_attribute(self._page, ["img._396cs4", "._2r_T1I"], "src")
            
            return RawProduct(
                marketplace="flipkart",
                product_id=pid,
                title=title.strip(),
                price=price or 0.0,
                rating=rating or 0.0,
                review_count=review_count,
                bsr=None,
                url=url,
                image_url=image_url,
            )
        except Exception as e:
            logger.error(f"Error fetching Flipkart product details for {pid}: {e}")
            return None


async def search_flipkart(
    keyword: str,
    max_results: int = 20,
    max_pages: int = 2,
) -> List[RawProduct]:
    """Convenience function for simple searches."""
    async with FlipkartScraper() as scraper:
        return await scraper.search(keyword, max_results, max_pages)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    async def test():
        async with FlipkartScraper(headless=True) as scraper:
            results = await scraper.search("stainless steel water bottle", max_results=5, max_pages=1)
            for r in results:
                print(f"  {r.title[:60]} | ₹{r.price} | ⭐{r.rating} | {r.review_count} reviews | {r.product_id}")
    
    asyncio.run(test())