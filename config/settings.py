"""
config/settings.py — Pydantic Settings for APRS V6 Pro.
Single source of truth for all configuration via environment variables.
"""
import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ─────────────────────────────────────────────────────────────
    database_path: Path = Field(
        default=Path(__file__).resolve().parent.parent / "data" / "research_engine.db",
        validation_alias="APRS_DB_PATH"
    )
    excel_master_path: Path = Field(
        default=Path(__file__).resolve().parent.parent / "APRS_Master_Product_Intelligence.xlsx",
        validation_alias="EXCEL_MASTER_PATH"
    )

    # ── Keepa API ────────────────────────────────────────────────────────────
    keepa_api_key: str = Field(default="", validation_alias="KEEPA_API_KEY")

    # ── Ollama (Local LLM) ───────────────────────────────────────────────────
    ollama_url: str = Field(default="http://localhost:11434", validation_alias="OLLAMA_URL")
    ollama_model: str = Field(default="qwen2.5:14b", validation_alias="OLLAMA_MODEL")
    ollama_fallback_model: str = Field(default="llama3.1:8b", validation_alias="OLLAMA_FALLBACK_MODEL")
    ollama_context_window: int = Field(default=8192, validation_alias="OLLAMA_CONTEXT_WINDOW")
    ollama_temperature: float = Field(default=0.2, validation_alias="OLLAMA_TEMPERATURE")

    # ── Scraping ─────────────────────────────────────────────────────────────
    playwright_headless: bool = Field(default=True, validation_alias="PLAYWRIGHT_HEADLESS")
    playwright_timeout_ms: int = Field(default=30000, validation_alias="PLAYWRIGHT_TIMEOUT_MS")
    scraper_user_agent: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        validation_alias="SCRAPER_USER_AGENT"
    )
    scraper_delay_ms: int = Field(default=2000, validation_alias="SCRAPER_DELAY_MS")

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field(default="json", validation_alias="LOG_FORMAT")  # json or text

    # ── Batch Execution ──────────────────────────────────────────────────────
    batch_niche_limit: int = Field(default=5, validation_alias="BATCH_NICHE_LIMIT")
    batch_max_candidates: int = Field(default=3, validation_alias="BATCH_MAX_CANDIDATES")
    batch_max_pages: int = Field(default=2, validation_alias="BATCH_MAX_PAGES")

    # ── Gate Thresholds ──────────────────────────────────────────────────────
    gate1_bsr_threshold: int = Field(default=50000, validation_alias="GATE1_BSR_THRESHOLD")
    gate1_cv_threshold: float = Field(default=0.30, validation_alias="GATE1_CV_THRESHOLD")
    gate3_min_margin_pct: float = Field(default=20.0, validation_alias="GATE3_MIN_MARGIN_PCT")
    gate4_min_score: int = Field(default=75, validation_alias="GATE4_MIN_SCORE")

    # ── Regional Profiles (India-first) ──────────────────────────────────────
    default_region: str = Field(default="India", validation_alias="DEFAULT_REGION")
    target_aov_min_inr: float = Field(default=799.0, validation_alias="TARGET_AOV_MIN_INR")
    target_aov_max_inr: float = Field(default=2499.0, validation_alias="TARGET_AOV_MAX_INR")
    sweet_spot_msrp_inr: float = Field(default=1299.0, validation_alias="SWEET_SPOT_MSRP_INR")
    default_cod_pct: float = Field(default=0.35, validation_alias="DEFAULT_COD_PCT")
    default_rto_pct: float = Field(default=0.18, validation_alias="DEFAULT_RTO_PCT")
    platform_fee_pct: float = Field(default=0.05, validation_alias="PLATFORM_FEE_PCT")

    # Sourcing hubs for India
    sourcing_hubs: List[str] = Field(
        default_factory=lambda: [
            "Tirupur (Textiles)",
            "Surat (Apparel/Jewelry)",
            "Moradabad (Brass/Home)",
            "Jaipur (Handicrafts)",
            "Shenzhen (Electronics)",
            "Yiwu (Small Goods)",
        ],
        validation_alias="SOURCING_HUBS"
    )

    marketplaces: List[str] = Field(
        default_factory=lambda: ["Amazon IN", "Flipkart", "Meesho", "Myntra"],
        validation_alias="MARKETPLACES"
    )

    # ── Scoring Weights ──────────────────────────────────────────────────────
    score_market_signal_weight: int = Field(default=25, validation_alias="SCORE_MARKET_SIGNAL_WEIGHT")
    score_review_quality_weight: int = Field(default=20, validation_alias="SCORE_REVIEW_QUALITY_WEIGHT")
    score_margin_safety_weight: int = Field(default=40, validation_alias="SCORE_MARGIN_SAFETY_WEIGHT")
    score_defect_fixability_weight: int = Field(default=10, validation_alias="SCORE_DEFECT_FIXABILITY_WEIGHT")
    score_competition_density_weight: int = Field(default=5, validation_alias="SCORE_COMPETITION_DENSITY_WEIGHT")

    score_proceed_threshold: int = Field(default=75, validation_alias="SCORE_PROCEED_THRESHOLD")
    score_marginal_threshold: int = Field(default=60, validation_alias="SCORE_MARGINAL_THRESHOLD")

    # ── NIM 550B (Unlimited — primary LLM for Arbiter + WebAgent) ───────────
    nim_api_key: str = Field(default="", validation_alias="NIM_API_KEY")
    nim_base_url: str = Field(
        default="https://integrate.api.nvidia.com/v1",
        validation_alias="NIM_BASE_URL"
    )
    nim_model: str = Field(
        default="nvidia/nemotron-3-ultra-550b-a55b",
        validation_alias="NIM_MODEL"
    )
    nim_arbiter_enabled: bool = Field(default=True, validation_alias="NIM_ARBITER_ENABLED")
    nim_temperature: float = Field(default=0.1, validation_alias="NIM_TEMPERATURE")
    nim_max_tokens: int = Field(default=4096, validation_alias="NIM_MAX_TOKENS")

    # ── WebAgent (browser-use) ───────────────────────────────────────────────
    web_agent_headless: bool = Field(default=True, validation_alias="WEB_AGENT_HEADLESS")
    web_agent_timeout_s: int = Field(default=180, validation_alias="WEB_AGENT_TIMEOUT_S")
    web_agent_max_steps: int = Field(default=20, validation_alias="WEB_AGENT_MAX_STEPS")
    # Supplier platforms to search (comma-separated)
    supplier_platforms: List[str] = Field(
        default_factory=lambda: ["indiamart", "alibaba"],
        validation_alias="SUPPLIER_PLATFORMS"
    )
    supplier_max_results: int = Field(default=8, validation_alias="SUPPLIER_MAX_RESULTS")



# Singleton instance
settings = Settings()

# ── Backward-compatible constants (for gradual migration) ────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = settings.database_path
EXCEL_MASTER_PATH = settings.excel_master_path
KEEPA_API_KEY = settings.keepa_api_key

# Ollama config (used by review_miner.py)
LOCAL_OLLAMA_CONFIG = {
    "ollama_url": settings.ollama_url,
    "default_model": settings.ollama_model,
    "fallback_model": settings.ollama_fallback_model,
    "context_window": settings.ollama_context_window,
    "temperature": settings.ollama_temperature,
}

# Regional profiles (used by economics_engine.py, orchestrator.py)
REGIONAL_PROFILES = {
    "India": {
        "currency": "INR",
        "symbol": "₹",
        "target_aov_min": settings.target_aov_min_inr,
        "target_aov_max": settings.target_aov_max_inr,
        "sweet_spot_msrp": settings.sweet_spot_msrp_inr,
        "default_cod_pct": settings.default_cod_pct,
        "default_rto_pct": settings.default_rto_pct,
        "platform_fee_pct": settings.platform_fee_pct,
        "gst_vat_rate": 0.18,
        "sourcing_hubs": settings.sourcing_hubs,
        "marketplaces": settings.marketplaces,
    },
    "USA": {
        "currency": "USD",
        "symbol": "$",
        "target_aov_min": 35.0,
        "target_aov_max": 150.0,
        "sweet_spot_msrp": 59.99,
        "default_cod_pct": 0.0,
        "default_rto_pct": 0.04,
        "platform_fee_pct": 0.05,
        "gst_vat_rate": 0.0,
        "sourcing_hubs": ["Yiwu (Small Goods)", "Shenzhen (Electronics)", "Dongguan (Hardware)", "Ningbo (Appliances)", "Mexico (Nearshoring)"],
        "marketplaces": ["Amazon US", "TikTok Shop", "Meta Ad Library", "Shopify DTC"],
    },
    "GCC_MiddleEast": {
        "currency": "USD",
        "symbol": "$",
        "target_aov_min": 65.0,
        "target_aov_max": 250.0,
        "sweet_spot_msrp": 95.0,
        "default_cod_pct": 0.25,
        "default_rto_pct": 0.12,
        "platform_fee_pct": 0.06,
        "gst_vat_rate": 0.05,
        "sourcing_hubs": ["Shenzhen (Electronics)", "Guangzhou (Beauty/Fragrance)", "Yiwu (Accessories)"],
        "marketplaces": ["Amazon AE/SA", "Noon", "TikTok Shop GCC", "Snapchat Direct"],
    },
    "Europe": {
        "currency": "EUR",
        "symbol": "€",
        "target_aov_min": 40.0,
        "target_aov_max": 120.0,
        "sweet_spot_msrp": 65.0,
        "default_cod_pct": 0.0,
        "default_rto_pct": 0.08,
        "platform_fee_pct": 0.05,
        "gst_vat_rate": 0.20,
        "sourcing_hubs": ["Turkey (Textiles/Ceramics)", "Poland (Packaging)", "Ningbo (Appliances)", "Shenzhen (Electronics)"],
        "marketplaces": ["Amazon DE/UK", "Otto", "Shopify EU", "Klarna Trends"],
    },
    "UK": {
        "currency": "GBP",
        "symbol": "£",
        "target_aov_min": 25.0,
        "target_aov_max": 100.0,
        "sweet_spot_msrp": 45.0,
        "default_cod_pct": 0.0,
        "default_rto_pct": 0.06,
        "platform_fee_pct": 0.05,
        "gst_vat_rate": 0.20,
        "sourcing_hubs": ["Shenzhen (Electronics)", "Ningbo (Appliances)", "Turkey (Textiles)"],
        "marketplaces": ["Amazon UK", "eBay UK", "Shopify UK"],
    },
}


if __name__ == "__main__":
    # Print all settings for verification
    import json
    print(json.dumps(settings.model_dump(), indent=2, default=str))