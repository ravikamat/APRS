import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root before any key reads
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")

BASE_DIR = _BASE_DIR

# ── NVIDIA NIM Cluster (3 keys loaded from .env) ───────────────────────────
NIM_API_KEYS = [
    k for k in [
        os.getenv("NIM_API_KEY_1", ""),
        os.getenv("NIM_API_KEY_2", ""),
        os.getenv("NIM_API_KEY_3", ""),
    ] if k.strip()
]
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1/chat/completions"

# ── NIM Model Matrix (verified active endpoints on NVIDIA NIM catalog) ─────
NIM_MODELS = {
    "deep_reasoning":        "nvidia/nemotron-3-super-120b-a12b",
    "ultra_reasoning":       "nvidia/nemotron-3-super-120b-a12b",
    "long_context_synthesis": "nvidia/nemotron-3-super-120b-a12b",
    "fast_triage":           "nvidia/nemotron-3-nano-30b-a3b",
    "vision_multimodal":     "meta/llama-3.2-90b-vision-instruct",
    "adversarial_critic":    "nvidia/nemotron-3-super-120b-a12b",
    # Nemotron specialized swarm roles
    "nemotron_scout":        "nvidia/nemotron-3-super-120b-a12b",
    "nemotron_arbiter":      "nvidia/nemotron-3-ultra-550b-a55b",  # Nemotron 3 Ultra 550B for final verdict
    "nemotron_ultra":        "nvidia/nemotron-3-ultra-550b-a55b",
}

# ── Swarm Agent Role Matrix ───────────────────────────────────────────────
SWARM_ROLES = {
    "trend_scout": {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "task_type": "nemotron_scout",
        "system_prompt": "You are the Lead Open-Web Trend Scout. Identify emerging high-velocity viral products and evaluate 7-30 day search momentum."
    },
    "marketplace_harvester": {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "task_type": "ultra_reasoning",
        "system_prompt": "You are the Multi-Marketplace Catalog Harvester. Match trend signals to active high-velocity listings on Amazon, Flipkart, Meesho, and Shopify."
    },
    "defect_analyst": {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "task_type": "deep_reasoning",
        "system_prompt": "You are the Chief Quality Engineer & Defect Miner. Synthesize multi-source 3-star reviews into structural BOM upgrades."
    },
    "economics_auditor": {
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "task_type": "long_context_synthesis",
        "system_prompt": "You are the 15-Factor Unit Economics Lead. Validate landed COGS, RTO reserves, FBA fees, and stress resilience."
    },
    "chief_arbiter": {
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "task_type": "adversarial_critic",
        "system_prompt": "You are the Supreme Investment Arbiter. Issue final consensus verdicts and flag false-positive backtrack alerts."
    }
}

# ── Local GGUF Model Paths (loaded from .env; None if not configured) ──────
LOCAL_HEAVY_MODELS = {
    "qwen_27b_gguf":   os.getenv("LOCAL_QWEN_27B_PATH", r"F:\Yuki_1.0\data\models\Qwen3.8-27B-UD-IQ1_S.gguf"),
    "qwen_0_5b_gguf":  os.getenv("LOCAL_QWEN_05B_PATH", r"F:\Yuki_1.0\data\models\qwen2.5-0.5b-instruct-q4_k_m.gguf"),
    "kimi_k3_gguf":    os.getenv("LOCAL_KIMI_K3_PATH", r"H:\trade\kimi-k3-in-c"),
}

# ── Local Offline GGUF Configuration (Ollama / llama.cpp / LM Studio) ─────
LOCAL_GGUF_CONFIG = {
    "ollama_url":     os.getenv("OLLAMA_URL", "http://localhost:11434"),
    "default_model":  os.getenv("LOCAL_QWEN_27B_MODEL", "qwen2.5:27b-instruct-q4_K_M"),
    "fallback_model": os.getenv("LOCAL_FALLBACK_MODEL", "phi3:3.8b"),
    "context_window": 8192,
    "temperature":    0.2,
}

# ── LLM Routing Configuration (NIM primary → Local fallback) ───────────────
# Format: "task_type:provider1,provider2;task_type:provider1"
# Providers: nim, ollama, llamacpp
# Arbiter stage uses NIM only (no fallback for final verdict)
LLM_ROUTING = {
    "scout":        ["nim", "ollama"],
    "harvester":    ["nim", "ollama"],
    "defect_miner": ["nim", "ollama"],
    "economics":    ["nim", "ollama"],
    "arbiter":      ["nim"],  # Never fallback - final verdict must use NIM
    "general":      ["nim", "ollama"],
}

# ── Data Storage Paths ──────────────────────────────────────────────────────
DATABASE_PATH      = BASE_DIR / "data" / "research_engine.db"
EXCEL_MASTER_PATH  = BASE_DIR / "APRS_Master_Product_Intelligence.xlsx"
RAW_DATA_DIR       = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
LOGS_DIR           = BASE_DIR / "logs"

# ── Supported Geographic Regions & Market Rules ────────────────────────────
REGIONAL_PROFILES = {
    "India": {
        "currency":           "INR",
        "symbol":             "₹",
        "target_aov_min":     799,
        "target_aov_max":     2499,
        "sweet_spot_msrp":    1299,
        "default_cod_pct":    0.35,
        "default_rto_pct":    0.18,
        "platform_fee_pct":   0.05,
        "sourcing_hubs":      ["Tirupur (Textiles)", "Surat (Apparel/Jewelry)", "Moradabad (Brass/Home)", "Jaipur (Handicrafts)", "Shenzhen (Electronics)", "Yiwu (Small Goods)"],
        "marketplaces":       ["Meesho", "Amazon IN", "Flipkart", "Myntra", "Blinkit Trends"],
    },
    "USA": {
        "currency":           "USD",
        "symbol":             "$",
        "target_aov_min":     35.00,
        "target_aov_max":     150.00,
        "sweet_spot_msrp":    59.99,
        "default_cod_pct":    0.0,
        "default_rto_pct":    0.04,
        "platform_fee_pct":   0.05,
        "sourcing_hubs":      ["Yiwu (Small Goods)", "Shenzhen (Electronics)", "Dongguan (Hardware)", "Ningbo (Appliances)", "Mexico (Nearshoring)"],
        "marketplaces":       ["Amazon US", "TikTok Shop", "Meta Ad Library", "Shopify DTC"],
    },
    "GCC_MiddleEast": {
        "currency":           "USD",
        "symbol":             "$",
        "target_aov_min":     65.00,
        "target_aov_max":     250.00,
        "sweet_spot_msrp":    95.00,
        "default_cod_pct":    0.25,
        "default_rto_pct":    0.12,
        "platform_fee_pct":   0.06,
        "sourcing_hubs":      ["Shenzhen (Electronics)", "Guangzhou (Beauty/Fragrance)", "Yiwu (Accessories)"],
        "marketplaces":       ["Amazon AE/SA", "Noon", "TikTok Shop GCC", "Snapchat Direct"],
    },
    "Europe": {
        "currency":           "EUR",
        "symbol":             "€",
        "target_aov_min":     40.00,
        "target_aov_max":     120.00,
        "sweet_spot_msrp":    65.00,
        "default_cod_pct":    0.0,
        "default_rto_pct":    0.08,
        "platform_fee_pct":   0.05,
        "sourcing_hubs":      ["Turkey (Textiles/Ceramics)", "Poland (Packaging)", "Ningbo (Appliances)", "Shenzhen (Electronics)"],
        "marketplaces":       ["Amazon DE/UK", "Otto", "Shopify EU", "Klarna Trends"],
    },
    "UK": {
        "currency":           "GBP",
        "symbol":             "£",
        "target_aov_min":     25.00,
        "target_aov_max":     100.00,
        "sweet_spot_msrp":    45.00,
        "default_cod_pct":    0.0,
        "default_rto_pct":    0.06,
        "platform_fee_pct":   0.05,
        "sourcing_hubs":      ["Shenzhen (Electronics)", "Ningbo (Appliances)", "Turkey (Textiles)"],
        "marketplaces":       ["Amazon UK", "eBay UK", "Shopify UK"],
    },
}
