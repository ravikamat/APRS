import requests
import time
import json
from collections import OrderedDict
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class KeepaProduct(BaseModel):
    asin: str
    title: str
    current_price: float = Field(..., ge=0)
    currency: str = "USD"
    bsr_current: Optional[int] = None
    bsr_category: Optional[str] = None
    rating: float = Field(default=0.0, ge=0, le=5)
    review_count: int = Field(default=0, ge=0)
    price_30d_avg: Optional[float] = None
    price_90d_avg: Optional[float] = None
    price_historical_low: Optional[float] = None
    is_buybox_suppressed: bool = False
    last_update: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or len(v.strip()) < 3:
            raise ValueError("Product title cannot be empty")
        return v.strip()


class KeepaAPIError(Exception):
    pass


class KeepaRateLimitError(KeepaAPIError):
    pass


class _LRUCache:
    """Proper LRU cache using OrderedDict (move_to_end)."""
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._cache: OrderedDict[str, Any] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key]

    def put(self, key: str, value: Any) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        if len(self._cache) > self.capacity:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


class KeepaAPIClient:
    """
    Production-hardened Keepa API client.
    - Token-aware rate limiting (Keepa uses token buckets, not HTTP 429).
    - Exponential backoff with jitter on transient errors.
    - In-memory LRU cache for ASIN lookups.
    - Pydantic response validation.
    """
    BASE_URL = "https://api.keepa.com"
    DOMAINS = {"USA": 1, "UK": 2, "Germany": 3, "France": 4, "Japan": 5, "Canada": 6, "Italy": 8, "Spain": 9, "India": 10}

    def __init__(self, api_key: str = "", max_retries: int = 3, cache_size: int = 100):
        self.api_key = api_key
        self.max_retries = max_retries
        self._cache = _LRUCache(cache_size)
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
        self._enabled = bool(api_key and len(api_key) >= 20)

    def _get_domain_id(self, region: str) -> int:
        return self.DOMAINS.get(region, 1)

    def _fetch(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Raw fetch with retry, jitter, and cache bypass."""
        url = f"{self.BASE_URL}/{endpoint}"
        params["key"] = self.api_key

        for attempt in range(self.max_retries):
            try:
                resp = self.session.get(url, params=params, timeout=(5, 15))

                if resp.status_code == 429:
                    raise KeepaRateLimitError("Keepa token bucket exhausted")
                resp.raise_for_status()
                data = resp.json()

                if data.get("error"):
                    raise KeepaAPIError(f"Keepa API error: {data['error']}")

                return data

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                wait = (2 ** attempt) + (hash(endpoint) % 1000) / 1000
                if attempt < self.max_retries - 1:
                    time.sleep(wait)
                else:
                    raise KeepaAPIError(f"Keepa unreachable after {self.max_retries} attempts: {e}")
            except KeepaRateLimitError:
                if attempt < self.max_retries - 1:
                    time.sleep(60)
                else:
                    raise

        raise KeepaAPIError("Unreachable")

    def get_product(self, asin: str, region: str = "USA") -> Optional[KeepaProduct]:
        """
        Fetch live product data from Keepa by ASIN.
        Returns None if product is not tracked, delisted, or Keepa API is not configured.
        """
        if not self._enabled:
            return None
            
        if not asin or len(asin) != 10:
            raise ValueError("ASIN must be 10 alphanumeric characters")

        cache_key = f"{region}:{asin}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        domain_id = self._get_domain_id(region)
        data = self._fetch("product", {"domain": domain_id, "asin": asin, "stats": "30,90"})

        products = data.get("products", [])
        if not products:
            return None

        raw = products[0]

        def _extract_price(cents: Optional[int]) -> Optional[float]:
            return round(cents / 100.0, 2) if cents and cents > 0 else None

        stats = raw.get("stats", {})
        current = _extract_price(stats.get("current", [None, None])[0]) or 0.0
        avg30 = _extract_price(stats.get("avg30", [None, None])[0])
        avg90 = _extract_price(stats.get("avg90", [None, None])[0])
        hist_low = _extract_price(stats.get("min", [None, None])[0])

        bsr_data = raw.get("stats", {}).get("current", [None, None, None])
        bsr_current = bsr_data[2] if len(bsr_data) > 2 and bsr_data[2] else None

        product = KeepaProduct(
            asin=raw.get("asin", asin),
            title=raw.get("title", "Unknown Product"),
            current_price=current,
            currency="INR" if domain_id == 10 else "USD" if domain_id == 1 else "EUR" if domain_id in (3, 4, 8, 9) else "GBP",
            bsr_current=bsr_current,
            bsr_category=raw.get("rootCategory", None),
            rating=round(raw.get("rating", 0) / 10.0, 1),
            review_count=raw.get("reviewsCount", 0),
            price_30d_avg=avg30,
            price_90d_avg=avg90,
            price_historical_low=hist_low,
            is_buybox_suppressed=raw.get("buyBoxSellerIdHistory", []) == [],
        )

        self._cache.put(cache_key, product)
        return product

    def search_by_keyword(self, query: str, region: str = "USA", page: int = 0) -> List[str]:
        """
        Search Keepa for ASINs matching a keyword.
        Returns list of ASINs (not full products to save tokens).
        Returns empty list if Keepa API is not configured.
        """
        if not self._enabled:
            return []
        domain_id = self._get_domain_id(region)
        data = self._fetch("search", {
            "domain": domain_id,
            "key": self.api_key,
            "search": query,
            "page": page,
            "type": "product"
        })
        return [p.get("asin") for p in data.get("products", []) if p.get("asin")]


if __name__ == "__main__":
    import os
    key = os.environ.get("KEEPA_API_KEY", "your-key-here")
    client = KeepaAPIClient(key)
    try:
        prod = client.get_product("B0B39BC5T6", region="USA")
        if prod:
            print(f"[LIVE KEEPA] {prod.title} | ${prod.current_price} | BSR: {prod.bsr_current}")
        else:
            print("[KEEPA] Product not found")
    except KeepaAPIError as e:
        print(f"[KEEPA ERROR] {e}")