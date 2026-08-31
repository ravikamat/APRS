"""
tools/adapters/base_adapter.py — Universal Source Adapter Framework for APRS V6 Pro.

Defines the pluggable contract for all data ingestion sources:
- Search Trends (Google Trends, Autocomplete, YouTube)
- Social Trends (TikTok, Instagram, Reddit, Meta Ads)
- Marketplaces (Amazon, Flipkart, Meesho, Myntra, Shopify)
- Complaint Sources (Review harvesters, forum discussions)
"""
from typing import Protocol, List, Dict, Any, Optional
from pydantic import BaseModel, Field
import datetime
import time


class SourceHealth(BaseModel):
    source_name: str
    is_healthy: bool = True
    last_successful_run: Optional[str] = None
    records_collected_total: int = 0
    consecutive_errors: int = 0
    average_latency_ms: float = 0.0
    status_message: str = "ONLINE"


class SourceAdapter(Protocol):
    source_name: str

    def discover_topics(self, query: str, region: str = "India") -> List[Dict[str, Any]]:
        """Discovers breakout keywords, trend signals, or viral topics."""
        ...

    def search_products(self, query: str, region: str = "India", limit: int = 5) -> List[Dict[str, Any]]:
        """Searches cross-marketplace product listings."""
        ...

    def collect_reviews(self, listing_url_or_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Collects 3-star reviews and defect comments for analysis."""
        ...

    def health_check(self) -> SourceHealth:
        """Returns the operational status and latency telemetry of the source adapter."""
        ...


class BaseSourceAdapter:
    """Base class providing telemetry, error tracking, and fallback handling for adapters."""

    def __init__(self, source_name: str):
        self.source_name = source_name
        self.records_collected_total = 0
        self.consecutive_errors = 0
        self.total_latency_ms = 0.0
        self.total_calls = 0
        self.last_successful_run = None

    def record_success(self, count: int, latency_ms: float):
        self.records_collected_total += count
        self.consecutive_errors = 0
        self.total_latency_ms += latency_ms
        self.total_calls += 1
        self.last_successful_run = datetime.datetime.now().isoformat()

    def record_error(self):
        self.consecutive_errors += 1
        self.total_calls += 1

    def health_check(self) -> SourceHealth:
        avg_lat = (self.total_latency_ms / max(1, self.total_calls))
        is_healthy = self.consecutive_errors < 5
        status_msg = "ONLINE" if is_healthy else f"DEGRADED ({self.consecutive_errors} errors)"
        return SourceHealth(
            source_name=self.source_name,
            is_healthy=is_healthy,
            last_successful_run=self.last_successful_run,
            records_collected_total=self.records_collected_total,
            consecutive_errors=self.consecutive_errors,
            average_latency_ms=round(avg_lat, 1),
            status_message=status_msg
        )
