# APRS V7 — Complete End-to-End Build Plan
## Ultimate Autonomous Multi-Agent Product Research System

> **Version:** 4.1 — Master Implementation Specification (Gap-Audited)  
> **Last Updated:** 2026-09-03T19:40 IST  
> **Goal:** 100% autonomous, self-improving system with 5-tier LLM fallback, manual override at every layer, and internet-wide data collection from 50+ sources.

---

## ⚠️ SECTION 0: GAP AUDIT — BUGS & ISSUES FOUND IN CODEBASE

**Audit date:** 2026-09-03 19:38 IST  
**Method:** Automated file-by-file scan, grep search, pytest collection, schema diff

### 🔴 CRITICAL — Will crash at runtime

| # | File | Line | Issue | Fix Required |
|---|------|------|-------|-------------|
| C1 | `tools/discovery_engine.py` | 260 | **Second scraping block still uses OLD `AmazonScraper`/`FlipkartScraper` context manager.** Lines 37-38 were fixed to import `WebAgent`, but the `discover_single_niche()` method at line 260 still does `async with AmazonScraper() as amazon, FlipkartScraper() as flipkart:` — these classes are no longer imported. **Will crash when `discover_single_niche()` is called.** | Replace lines 260-275 with WebAgent calls |
| C2 | `tools/trend_scout/trend_aggregator.py` | 32 | `from tools.ai_supervisor import get_supervisor` — **ai_supervisor was moved to `deprecated/`.** This import will crash on any trend scan. | Remove import; replace `get_supervisor()` calls with direct logic or stub |
| C3 | `core/team_meeting.py` | 123-124 | `from models.nim_cluster import SupremeNIMCluster` — **models/nim_cluster.py no longer exists.** Team meeting feature is 100% broken. | Delete team_meeting.py (unused in V7 pipeline) or replace with LLMRouter call |
| C4 | `tests/test_phase6_e2e.py` | 61 | `from tools.ai_supervisor import get_supervisor` — deprecated import. Test will fail at runtime. | Rewrite test or delete |

### 🟡 MAJOR — Roadmap claims that don't match code

| # | Issue | Reality |
|---|-------|---------|
| M1 | Roadmap says Gate 4 uses "NIM 550B Arbiter via LLMRouter" | Gate 4 is purely deterministic — `ScoringEngine.score()` with weighted rubric (BSR 25pts, Reviews 20pts, Margin 40pts, Defect 10pts, Competition 5pts). **No LLM call.** Upgrade plan: add optional NIM arbiter as Gate 5. |
| M2 | Roadmap Section 5 says "23 existing tables" | Actually **26 tables** — `learned_rules`, `gate_logs`, and `review_snapshots` already exist in `init_db()`. |
| M3 | Roadmap proposes different `learned_rules` schema | The init_db() version (columns: `rule_id_str`, `name`, `condition`, `action`, `severity`, `params_json`, `enabled`, `tags_json`) is the CORRECT one — rule_engine.py uses it. |
| M4 | Roadmap proposes different `gate_logs` schema | The init_db() version has `gate_name`, `status` CHECK, `details_json`, FK to master_products. Keep it. |
| M5 | `discovery_engine.py` docstring says "Playwright scrapers" | Line 37 imports WebAgent (browser-use). But `discover_single_niche()` at L260 still uses old Playwright scrapers. **Dual personality bug.** |
| M6 | Roadmap says settings.py has Groq/Kimi fields | `groq_api_key`, `kimi_model_path`, `kimi_preset`, `kimi_enabled`, all `LLM_TIER_*`, all `AGENT_*_MODE` fields **do not exist** in settings.py. |
| M7 | Roadmap Section 8 shows full .env template | `.env.example` has NONE of: `GROQ_*`, `KIMI_*`, `LLM_TIER_*`, `AGENT_*_MODE`, `EVOLUTION_GO_*`, `CRM_*`, `WORLDMONITOR_*`, `OPENBB_*`, `AGENT_REACH_*`. |
| M8 | `economics_engine.py` claims "WIRE: OpenBB for live USD/INR" | All rates hardcoded (L41-60). No hook to receive live data. Must add `set_live_rate()` method. |

### 🟠 MODERATE — Dead code

| # | File | Issue |
|---|------|-------|
| D1 | `core/database.py` L586-614 | `ai_supervisor_logs` + `ai_task_improvements` tables — ai_supervisor is deprecated, tables + 3 helper functions are dead code |
| D2 | `core/database.py` L981 | `record_product_evaluation()` hardcodes `"ai_supervisor"` as source |
| D3 | `core/team_meeting.py` | 100% broken (SupremeNIMCluster). Not called by V7 pipeline. |
| D4 | `pipeline.py` L6 docstring | Says "Playwright scrapers" — should say WebAgent/browser-use |

### 🔵 STRUCTURAL — 20 Files missing, 6 DB tables missing

**Files to build:** `core/llm_router.py`, `core/nim_client.py`, `core/groq_client.py`, `core/kimi_wrapper.py`, `core/supplier_models.py`, `core/outreach_engine.py`, `core/agent_orchestrator.py`, `core/scheduler.py`, `core/learning_engine.py`, `tools/internet_crawler.py`, `tools/niche_expander.py`, `tools/supplier_agent.py`, `tools/gst_verifier.py`, `tools/problem_miner.py`, `integrations/agent_reach.py`, `integrations/openbb_client.py`, `integrations/worldmonitor.py`, `integrations/evolution_go.py`, `integrations/crm_client.py`, `integrations/opencompany.py`

**DB tables to add (6 not 8):** `supplier_profiles`, `outreach_drafts`, `supplier_conversations`, `problem_opportunities`, `llm_tier_log`, `pending_human_decisions`  
(`learned_rules`, `gate_logs` already exist — see M2)

### 🟢 CORRECTED DB TABLE COUNT

**26 existing tables:** master_products, product_suppliers, daily_snapshots, meeting_audit_log, product_gate_progress, arbiter_decision_log, trend_signals, multi_platform_listings, swarm_audit_log, negative_findings, launchpad_items, defect_clusters, economics_assessments, discovered_sources, dynamic_niches, dynamic_seed_keywords, marketplace_config, scraped_listings, scraper_validations, ai_supervisor_logs, ai_task_improvements, website_capture_stats, url_validation_log, learned_rules, gate_logs, review_snapshots

### 📊 TEST SUITE: 100 tests collected, 0 collection errors

Runtime failures expected in: `test_phase6_e2e.py` (ai_supervisor import), possibly `test_aprs_v6_swarm.py`

### 🎯 PRIORITY FIX ORDER (before any new build)

```
FIX 1: discovery_engine.py L260 — replace old AmazonScraper block     — 10 min
FIX 2: trend_aggregator.py L32 — remove ai_supervisor import          — 5 min  
FIX 3: team_meeting.py L123 — delete or stub SupremeNIMCluster         — 5 min
FIX 4: test_phase6_e2e.py L61 — rewrite test                          — 10 min
FIX 5: settings.py — add Groq/Kimi/Tier/AgentMode fields              — 15 min
FIX 6: database.py — add 6 new tables                                 — 15 min
FIX 7: economics_engine.py — add set_live_rate() hook                  — 10 min
```

---

## SECTION 1: LLM TIER STACK (5 Levels, Fully Automatic Fallback)

Every AI call in APRS goes through a single `LLMRouter` that tries each tier in sequence. No agent ever calls a model directly — they all call `LLMRouter.chat()`.

```
TIER 1: NIM 550B (nvidia/nemotron-3-ultra-550b-a55b)
        ├─ Endpoint: https://integrate.api.nvidia.com/v1
        ├─ Use for: Gate 4 arbiter, outreach drafting, problem synthesis,
        │           browser agent driving, weekly niche rebalancing
        ├─ Trigger fallback on: HTTP 429, HTTP 503, timeout >30s, 3 consecutive errors
        └─ Cost: ₹0 (unlimited key)

TIER 2: Ollama — qwen27b_iq1 (local, always-on)
        ├─ Endpoint: http://127.0.0.1:11434
        ├─ Model: F:\Yuki_1.0\data\models\Qwen3.8-27B-UD-IQ1_S.gguf (mapped as qwen27b_iq1)
        ├─ Use for: Gate 2 defect extraction, bulk Reddit/forum mining,
        │           review reading (50+ products/day), cheap classification
        ├─ Trigger fallback on: Ollama not running, CUDA OOM, timeout >120s
        └─ Cost: ₹0 (local)

TIER 3: Groq Free API (Llama-3.3-70B or Mixtral-8x7B)
        ├─ Endpoint: https://api.groq.com/openai/v1 (OpenAI-compatible)
        ├─ Limits: 14,400 req/day free, 6,000 tokens/min
        ├─ Use for: Fast classification, entity extraction, short summaries
        │           when Ollama is offline (laptop mode)
        ├─ Trigger fallback on: Groq 429 or daily quota hit
        └─ Cost: ₹0 (free tier, from awesome-freellm-apis directory)

TIER 4: kimi-k3-in-c (local C99 engine, 2.78T params)
        ├─ Binary: H:\trade\kimi-k3-in-c\bin\k3 (must be compiled)
        ├─ Model: 1.56 TB checkpoint (streams from NVMe, 8 GB RAM minimum)
        ├─ Speed: 26.5 s/token @ 8GB | 19.8 s/token @ 64GB | 5.6 s/token @ 128GB
        ├─ Use for: Deep reasoning tasks when NIM + Ollama + Groq all unavailable
        │           OVERNIGHT BATCH ONLY — too slow for interactive use
        ├─ Trigger fallback on: All 3 above tiers failed AND task_priority == BATCH
        ├─ NOT used for: Real-time scraping decisions, time-sensitive tasks
        └─ Cost: ₹0 (local, needs 1.56TB disk space + NVMe recommended)

TIER 5: MANUAL OVERRIDE (Human-in-the-loop fallback)
        ├─ Trigger: All 4 AI tiers unavailable OR manual_override flag set
        ├─ Behavior: Task pauses → dashboard shows pending task with context
        │            Human reads context, types verdict/answer in dashboard
        │            APRS resumes from that point with human-provided decision
        └─ Use for: Any agent when explicitly set to MANUAL in settings
```

### LLMRouter Implementation (`core/llm_router.py`)

```python
class LLMRouter:
    """
    Single entry point for ALL LLM calls in APRS.
    5-tier automatic fallback. Manual override at any tier.
    
    Settings (all configurable in .env or dashboard Settings tab):
      LLM_TIER_1_ENABLED=true          # NIM 550B
      LLM_TIER_2_ENABLED=true          # Ollama
      LLM_TIER_3_ENABLED=true          # Groq free
      LLM_TIER_4_ENABLED=false         # kimi-k3 (disabled by default — slow)
      LLM_TIER_5_MANUAL_FALLBACK=true  # Human override
      
      # Per-agent override (bypasses tier ladder for specific agents):
      AGENT_GATE4_LLM=nim              # Force Gate4 to always use NIM
      AGENT_DEFECT_LLM=ollama          # Force defect mining to always use Ollama
      AGENT_SUPPLIER_LLM=nim           # Force supplier agent to use NIM
      # Set to "auto" to use normal tier ladder (default)
    """
    
    TIERS = {
        1: "nim_550b",
        2: "ollama_local", 
        3: "groq_free",
        4: "kimi_k3_local",
        5: "manual_human",
    }
    
    def __init__(self):
        self.health = {t: True for t in self.TIERS}  # tier health state
        self.error_counts = {t: 0 for t in self.TIERS}
        self.kimi_wrapper = KimiK3Wrapper()  # wraps the C binary via subprocess
    
    def chat(
        self,
        messages: List[dict],
        agent_name: str = "default",
        task_priority: str = "realtime",  # realtime | batch
        json_mode: bool = False,
        max_tokens: int = 2048,
        force_tier: Optional[int] = None,  # manual override
    ) -> LLMResponse:
        """
        Call LLM with automatic 5-tier fallback.
        Returns LLMResponse with: text, tier_used, latency_ms, tokens_used
        """
        # Check per-agent override from settings
        agent_override = self._get_agent_override(agent_name)
        
        # Determine starting tier
        start_tier = force_tier or agent_override or 1
        
        for tier_num in range(start_tier, 6):
            if not self._is_tier_enabled(tier_num):
                continue
            if not self.health[tier_num]:
                continue
            # Tier 4 (kimi-k3) only for batch tasks — skip if realtime
            if tier_num == 4 and task_priority == "realtime":
                continue
                
            try:
                result = self._call_tier(tier_num, messages, json_mode, max_tokens)
                # Success — reset error count for this tier
                self.error_counts[tier_num] = 0
                self.health[tier_num] = True
                # Log which tier was used (for monitoring dashboard)
                self._log_tier_usage(agent_name, tier_num, result)
                return result
                
            except (RateLimitError, TimeoutError, ServiceUnavailable) as e:
                self.error_counts[tier_num] += 1
                if self.error_counts[tier_num] >= 3:
                    self.health[tier_num] = False  # mark tier unhealthy
                    logger.warning(f"Tier {tier_num} marked unhealthy after 3 errors: {e}")
                continue  # try next tier
                
        # All tiers failed → Tier 5: human override
        return self._human_override(messages, agent_name)
    
    def _call_tier(self, tier, messages, json_mode, max_tokens) -> LLMResponse:
        if tier == 1:   return self._call_nim(messages, json_mode, max_tokens)
        if tier == 2:   return self._call_ollama(messages, json_mode, max_tokens)
        if tier == 3:   return self._call_groq(messages, json_mode, max_tokens)
        if tier == 4:   return self.kimi_wrapper.chat(messages, max_tokens)
        
    def _human_override(self, messages, agent_name) -> LLMResponse:
        # Write task to `pending_human_decisions` DB table
        # Dashboard shows it with full context
        # Block until human provides decision (or timeout 24h → skip task)
        task_id = record_pending_decision(agent_name, messages)
        logger.critical(f"ALL LLM TIERS FAILED for {agent_name}. Human override required. Task ID: {task_id}")
        return LLMResponse(text="AWAITING_HUMAN", tier_used=5, task_id=task_id)
```

### KimiK3Wrapper — C Binary Integration

```python
class KimiK3Wrapper:
    """
    Wraps the kimi-k3-in-c C99 binary via subprocess.
    
    IMPORTANT constraints:
    - Requires 1.56 TB model checkpoint on disk (not included — must download)
    - Linux x86-64 only (binary won't run on Windows natively)
    - 26.5 s/token on 8GB RAM — use ONLY for batch overnight tasks
    - Windows workaround: run inside WSL2 or Docker Linux container
    
    Setup (one-time):
      1. WSL2: wsl --install
      2. Inside WSL: cd /mnt/h/trade/kimi-k3-in-c && make
      3. Download 1.56 TB checkpoint (Hugging Face: moonshotai/Kimi-K3)
      4. Set KIMI_MODEL_PATH in .env
    
    Practical reality:
    - At 26.5 s/token, a 200-token response = ~88 minutes
    - ONLY suitable for: weekly synthesis report, overnight deep analysis,
      one-time product category deep dive (schedule Sunday 00:00, done by 06:00)
    - NOT suitable for: any real-time decision, scraping, gate validation
    """
    
    BINARY_PATH = "wsl /mnt/h/trade/kimi-k3-in-c/bin/k3"  # via WSL on Windows
    
    def is_available(self) -> bool:
        # Check: WSL installed + binary compiled + model checkpoint exists
        try:
            result = subprocess.run(["wsl", "--status"], capture_output=True, timeout=5)
            model_path = settings.kimi_model_path
            return result.returncode == 0 and Path(model_path).exists()
        except Exception:
            return False
    
    def chat(self, messages: List[dict], max_tokens: int = 100) -> LLMResponse:
        # Convert messages to a single prompt (kimi-k3 is a base model, no chat template)
        prompt = self._messages_to_prompt(messages)
        
        cmd = [
            "wsl", "/mnt/h/trade/kimi-k3-in-c/bin/k3",
            settings.kimi_model_path,
            "--trunk", settings.kimi_trunk_path,
            "--preset", settings.kimi_preset,  # "laptop" | "server"
            "--tok", settings.kimi_model_path,
            "--prompt", prompt,
            "--gen", str(max_tokens),
            "--incremental"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=max_tokens * 35)  # 35s/token safety buffer
        
        # Parse output between "--- generated text ---" markers
        output = self._extract_generated_text(result.stdout)
        return LLMResponse(text=output, tier_used=4, model="kimi-k3-2.78T")
```

---

## SECTION 2: AGENT MANUAL OVERRIDE SYSTEM

Every agent has a `mode` that can be set per-agent in the dashboard Settings tab or `.env`:

```
# .env — per-agent LLM override
AGENT_INTERNET_CRAWLER_MODE=auto        # auto | manual | disabled | force_tier:2
AGENT_TREND_SIGNAL_MODE=auto
AGENT_NICHE_EXPANDER_MODE=auto
AGENT_DISCOVERY_MODE=auto
AGENT_PROBLEM_MINER_MODE=auto
AGENT_GATE_ENGINE_MODE=auto
AGENT_SUPPLIER_MODE=auto
AGENT_OUTREACH_MODE=manual              # outreach always requires human approval
AGENT_LEARNING_MODE=auto
AGENT_ORCHESTRATOR_MODE=auto

# Emergency stops (disable agent entirely, e.g. if misbehaving)
AGENT_SUPPLIER_ENABLED=true
AGENT_LEARNING_ENABLED=true
```

### Agent Mode Behavior

```
MODE: auto          → Use LLMRouter normal tier ladder (NIM→Ollama→Groq→Kimi→Human)
MODE: manual        → Every LLM call goes to Tier 5 (human decides). Agent still runs
                      but pauses at every AI decision for human input.
MODE: disabled      → Agent does not run. Tasks for this agent skip silently or queue.
MODE: force_tier:N  → Skip to tier N in the fallback ladder for this agent.
                      Example: force_tier:2 → always use Ollama, skip NIM.
                      Useful if: NIM is flaky, or you want to save NIM quota for important tasks.
```

### Dashboard Override Panel (Settings Tab → Agent Control)

```
┌─────────────────────────────────────────────────────────────────────┐
│  AGENT CONTROL PANEL                              [Save All Changes] │
├───────────────────┬──────────┬────────────────┬────────────────────┤
│ Agent             │ Enabled  │ LLM Mode       │ Force Tier         │
├───────────────────┼──────────┼────────────────┼────────────────────┤
│ InternetCrawler   │ ✅ ON   │ [auto      ▾]  │ [NIM 550B    ▾]    │
│ TrendSignal       │ ✅ ON   │ [auto      ▾]  │ [No LLM      ▾]    │
│ NicheExpander     │ ✅ ON   │ [auto      ▾]  │ [NIM 550B    ▾]    │
│ Discovery         │ ✅ ON   │ [auto      ▾]  │ [NIM 550B    ▾]    │
│ ProblemMiner      │ ✅ ON   │ [auto      ▾]  │ [Ollama      ▾]    │
│ GateEngine        │ ✅ ON   │ [auto      ▾]  │ [NIM 550B    ▾]    │
│ SupplierAgent     │ ✅ ON   │ [auto      ▾]  │ [NIM 550B    ▾]    │
│ OutreachEngine    │ ✅ ON   │ [MANUAL    ▾]  │ [Human       ▾]    │
│ LearningAgent     │ ✅ ON   │ [auto      ▾]  │ [NIM 550B    ▾]    │
│ Orchestrator      │ ✅ ON   │ [auto      ▾]  │ [None/Logic  ▾]    │
├───────────────────┴──────────┴────────────────┴────────────────────┤
│ LLM TIER HEALTH                                                      │
│  Tier 1 NIM 550B:    🟢 Healthy  (12 calls today, 0 errors)         │
│  Tier 2 Ollama:      🔴 OFFLINE  (not running — start with: ollama) │
│  Tier 3 Groq Free:   🟢 Healthy  (4,231/14,400 req used today)      │
│  Tier 4 kimi-k3:     ⚪ Disabled (enable in .env: KIMI_ENABLED=true)│
│  Tier 5 Human:       🟡 Standby  (0 pending decisions)              │
│                                                                      │
│ [Run Agent Manually]  [Test LLM Connection]  [View Agent Logs]      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## SECTION 3: DATA COLLECTION — 50+ SOURCES

### 3A. Trend Signal Sources (What is becoming popular?)

```python
TREND_SOURCES = {
    # Google signals (no API key, public endpoints)
    "google_trends_realtime": {
        "url": "https://trends.google.com/trending?geo=IN",
        "method": "browser_use",  # NIM 550B drives Chrome via browser-use
        "schedule": "every_2h",
        "output": "trending_keywords → trend_signals table",
    },
    "google_autocomplete": {
        "url": "https://suggestqueries.google.com/complete/search?client=firefox&hl=en-IN&q={keyword}",
        "method": "curl_cffi",   # No browser needed, JSON response
        "schedule": "every_4h",
        "output": "autocomplete_suggestions → trend_signals table",
    },
    "google_shopping_trending": {
        "url": "https://shopping.google.com/",
        "method": "browser_use",
        "schedule": "every_6h",
        "output": "trending_products → scraped_listings table",
    },
    
    # YouTube signals
    "youtube_trending_india": {
        "url": "https://www.youtube.com/feed/trending?gl=IN",
        "method": "Agent-Reach (youtube_transcript tool)",
        "schedule": "every_6h",
        "output": "viral_product_mentions → trend_signals table",
    },
    "youtube_product_reviews": {
        "url": "https://www.youtube.com/results?search_query={keyword}+review+2026",
        "method": "Agent-Reach (youtube_transcript)",
        "schedule": "on_demand per product",
        "output": "review_transcript → defect_clusters table",
    },
    
    # Reddit signals (Agent-Reach)
    "reddit_indiabuy": {
        "url": "https://www.reddit.com/r/IndiaBuy/top/?t=week",
        "method": "Agent-Reach (reddit_scraper tool)",
        "schedule": "every_6h",
        "output": "viral_products → trend_signals table",
    },
    "reddit_amazonfinds": {
        "url": "https://www.reddit.com/r/amazonfinds/top/?t=week",
        "method": "Agent-Reach (reddit_scraper tool)",
        "schedule": "every_6h",
    },
    "reddit_tiktokmademebuyit": {
        "url": "https://www.reddit.com/r/tiktokmademebuyit/top/?t=week",
        "method": "Agent-Reach (reddit_scraper tool)",
        "schedule": "every_6h",
    },
    "reddit_indiabeautydeals": {
        "url": "https://www.reddit.com/r/IndianBeautyDeals/top/?t=week",
        "method": "Agent-Reach (reddit_scraper tool)",
        "schedule": "every_6h",
    },
    "reddit_frugalmalefashion": {
        "url": "https://www.reddit.com/r/frugalmalefashion/top/?t=week",
        "method": "Agent-Reach (reddit_scraper tool)",
        "schedule": "every_8h",
    },
    "reddit_buyitforlife": {
        "url": "https://www.reddit.com/r/BuyItForLife/new/",
        "method": "Agent-Reach (reddit_scraper tool)",
        "schedule": "every_12h",
        "output": "quality_product_demand → trend_signals + problem_opportunities",
    },
    "reddit_malelifestyle": {
        "url": "https://www.reddit.com/r/malelifestyle/top/?t=week",
        "method": "Agent-Reach",
        "schedule": "every_12h",
    },
    "reddit_diy": {
        "url": "https://www.reddit.com/r/DIY/top/?t=week",
        "method": "Agent-Reach",
        "schedule": "every_12h",
    },
    "reddit_homeimprovement": {
        "url": "https://www.reddit.com/r/HomeImprovement/new/",
        "method": "Agent-Reach",
        "schedule": "every_12h",
    },
    
    # Social Commerce signals
    "twitter_viral_india": {
        "url": "https://twitter.com/search?q=viral+product+india&f=live",
        "method": "Agent-Reach (twitter_scraper tool)",
        "schedule": "every_4h",
    },
    "twitter_amazon_deals": {
        "url": "https://twitter.com/search?q=amazon+india+deal+OR+flipkart+viral&f=live",
        "method": "Agent-Reach",
        "schedule": "every_4h",
    },
    
    # Macro / Commodity signals (worldmonitor MCP)
    "worldmonitor_commodities": {
        "endpoint": "wm-mcp://commodity.worldmonitor.app",
        "method": "MCP query via worldmonitor",
        "schedule": "every_12h",
        "output": "raw_material_prices → updates economics_engine cost assumptions",
    },
    "worldmonitor_macro_india": {
        "endpoint": "wm-mcp://india.worldmonitor.app",
        "method": "MCP query",
        "schedule": "every_12h",
        "output": "consumer_sentiment, import_export → trend_signals table",
    },
    
    # OpenBB financial data
    "openbb_usd_inr": {
        "call": "obb.currency.price.historical(symbol='USDINR=X')",
        "method": "OpenBB MCP",
        "schedule": "daily_06:00",
        "output": "updates settings.usd_inr_rate → economics engine uses live rate",
    },
    "openbb_cpi_india": {
        "call": "obb.economy.price.cpi(country='india')",
        "method": "OpenBB MCP",
        "schedule": "weekly",
        "output": "consumer_price_index → demand projection context",
    },
}
```

### 3B. Product Discovery Sources (What is selling?)

```python
PRODUCT_SOURCES = {
    # Primary Indian marketplaces
    "amazon_in_search": {
        "method": "WebAgent (browser-use + NIM 550B)",
        "url": "https://www.amazon.in/s?k={query}",
        "output": "RawProduct[] → master_products",
        "schedule": "on_demand per niche",
    },
    "amazon_in_movers_shakers": {
        "url": "https://www.amazon.in/gp/movers-and-shakers/",
        "method": "Agent-Reach (RSS) OR WebAgent",
        "schedule": "every_6h",
        "output": "BSR_rising_products → trend_signals + dynamic_niches",
    },
    "amazon_in_bestsellers": {
        "url": "https://www.amazon.in/gp/bestsellers/",
        "method": "WebAgent",
        "schedule": "daily",
        "output": "top_bsr_products → scraped_listings",
    },
    "flipkart_search": {
        "method": "WebAgent",
        "url": "https://www.flipkart.com/search?q={query}",
        "output": "RawProduct[] → master_products",
    },
    "flipkart_trending": {
        "url": "https://www.flipkart.com/store/trending-now",
        "method": "WebAgent",
        "schedule": "every_6h",
        "output": "trend_signals table",
    },
    "meesho_trending": {
        "url": "https://www.meesho.com/collections/trending",
        "method": "WebAgent",
        "schedule": "every_6h",
        "output": "trend_signals (India tier-2/3 demand)",
    },
    "meesho_search": {
        "method": "WebAgent",
        "url": "https://www.meesho.com/search?q={query}",
        "output": "RawProduct[] → master_products",
    },
    
    # Regional / niche Indian platforms
    "jiomart_trending": {
        "url": "https://www.jiomart.com/",
        "method": "WebAgent",
        "schedule": "daily",
        "output": "tier-2/3 India demand signals",
    },
    "tatacliq": {
        "url": "https://www.tatacliq.com/",
        "method": "WebAgent",
        "schedule": "weekly",
    },
    "myntra": {
        "url": "https://www.myntra.com/",
        "method": "WebAgent",
        "schedule": "weekly (fashion/apparel only)",
    },
    "nykaa": {
        "url": "https://www.nykaa.com/",
        "method": "WebAgent",
        "schedule": "weekly (beauty/personal care only)",
    },
    
    # D2C brands (track launches + viral products)
    "mamaearth_new": {
        "url": "https://mamaearth.in/pages/new-launches",
        "method": "WebAgent",
        "schedule": "weekly",
        "output": "competitor_launches → trend_signals",
    },
    "wow_skin_new": {
        "url": "https://www.wowskin.com/collections/new-launches",
        "method": "WebAgent",
        "schedule": "weekly",
    },
    "bombay_shaving_new": {
        "url": "https://www.bombayshavingcompany.com/collections/new-arrivals",
        "method": "WebAgent",
        "schedule": "weekly",
    },
    
    # International (price benchmarking + trend lead indicator)
    "alibaba_bestsellers": {
        "url": "https://www.alibaba.com/trade/search?SearchText={query}",
        "method": "WebAgent (for supplier discovery)",
        "schedule": "on_demand per product",
    },
    "aliexpress_trending": {
        "url": "https://www.aliexpress.com/wholesale?SearchText={query}",
        "method": "WebAgent",
        "schedule": "weekly (trend lead 3-6 months ahead of India)",
    },
    "temu_trending": {
        "url": "https://www.temu.com/",
        "method": "WebAgent",
        "schedule": "weekly",
        "output": "emerging_products (India lags Temu by ~4 months)",
    },
    "amazon_us_movers_shakers": {
        "url": "https://www.amazon.com/gp/movers-and-shakers/",
        "method": "WebAgent",
        "schedule": "weekly (US trends → India in 6-12 months)",
        "output": "future_trend_prediction → trend_signals (low priority score)",
    },
    
    # Wholesale / Supplier platforms
    "indiamart_search": {
        "url": "https://dir.indiamart.com/search.mp?ss={query}",
        "method": "curl_cffi JSON API (no browser needed)",
        "schedule": "on_demand per product",
        "output": "supplier_profiles table",
    },
    "tradeindia": {
        "url": "https://www.tradeindia.com/search.html?search_str={query}",
        "method": "WebAgent fallback",
        "schedule": "on_demand",
        "output": "supplier_profiles table",
    },
    "exportersindia": {
        "url": "https://www.exportersindia.com/search/?search={query}",
        "method": "WebAgent",
        "schedule": "on_demand",
    },
    
    # Niche platforms
    "etsy_trending": {
        "url": "https://www.etsy.com/",
        "method": "WebAgent",
        "schedule": "weekly (artisan/handmade product ideas)",
    },
    "shopee_trending": {
        "url": "https://shopee.in/ OR shopee.com",
        "method": "WebAgent",
        "schedule": "weekly (SE Asia trend signal)",
    },
    "daraz": {
        "url": "https://www.daraz.com/",
        "method": "WebAgent",
        "schedule": "weekly (South Asia — Bangladesh/Pakistan demand)",
    },
}
```

### 3C. Problem Discovery Sources (What are people struggling with?)

```python
PROBLEM_SOURCES = {
    "amazon_qa_sections": {
        "url": "https://www.amazon.in/ask/questions/asin/{asin}/",
        "method": "WebAgent reads Q&A → Ollama extracts unmet needs",
        "schedule": "on_demand per discovered product",
        "output": "problem_opportunities table",
    },
    "amazon_3star_reviews": {
        "url": "https://www.amazon.in/product-reviews/{asin}/?filterByStar=three_star",
        "method": "WebAgent reads reviews → Ollama defect extraction",
        "schedule": "on_demand per product (Gate 2)",
        "output": "defect_clusters table",
    },
    "quora_product_questions": {
        "url": "https://www.quora.com/search?q={keyword}+product",
        "method": "Agent-Reach (web extraction)",
        "schedule": "weekly per niche",
        "output": "problem_opportunities table",
    },
    "youtube_product_fail_comments": {
        "url": "YouTube search: '{product} problem OR bad OR disappointed'",
        "method": "Agent-Reach (youtube_transcript — reads comments)",
        "schedule": "on_demand per product",
        "output": "defect_clusters table",
    },
    "reddit_complaints_per_niche": {
        "url": "Reddit search for complaints in niche communities",
        "method": "Agent-Reach (reddit_scraper)",
        "schedule": "weekly per niche",
        "output": "problem_opportunities table",
    },
    "flipkart_reviews": {
        "url": "https://www.flipkart.com/product-reviews/{product_id}",
        "method": "WebAgent (India-specific complaint patterns)",
        "schedule": "on_demand per product",
        "output": "defect_clusters table",
    },
    "trustpilot_brand": {
        "url": "https://www.trustpilot.com/review/{brand_domain}",
        "method": "Agent-Reach (web extraction)",
        "schedule": "on_demand per competitor brand",
        "output": "problem_opportunities (brand-level failures = your entry point)",
    },
    "indiamart_product_queries": {
        "url": "IndiaMART 'Buy Leads' — what buyers are asking suppliers for",
        "method": "WebAgent",
        "schedule": "weekly",
        "output": "problem_opportunities + dynamic_niches (demand from buyers)",
    },
}
```

### 3D. Auto-Discovery: Self-Expanding Source List

The system discovers NEW sources automatically:

```python
class SourceDiscoveryEngine:
    """
    NIM 550B reads content from existing sources and identifies NEW sources
    not in our current list. New sources auto-added to discovered_sources table.
    Low-yield sources auto-deactivated.
    """
    
    async def discover_new_sources_from_content(self, page_content: str, parent_url: str):
        prompt = f"""
        You are analyzing a web page for an e-commerce product research tool.
        Parent URL: {parent_url}
        
        From this content, identify any NEW web pages, communities, forums, marketplaces,
        or data sources that would be useful for:
        1. Finding viral/trending products in India
        2. Understanding what problems consumers face with products
        3. Finding product suppliers in India or China
        
        Return JSON array of new sources:
        [{{"url": "...", "source_type": "trend|problem|product|supplier",
           "reason": "why useful", "schedule": "every_6h|daily|weekly"}}]
        
        Page content:
        {page_content[:3000]}
        """
        new_sources = nim_client.chat(prompt, json_mode=True)
        for source in new_sources:
            record_discovered_source(
                url=source["url"],
                source_type=source["source_type"],
                discovered_by=parent_url,
            )
    
    async def deactivate_low_yield_sources(self):
        # Sources with 0 useful signals in last 3 scan cycles → deactivate
        sources = get_sources_with_low_yield(consecutive_empty_runs=3)
        for s in sources:
            update_source_status(s["id"], active=False,
                               reason="3 consecutive empty runs")
```

---

## SECTION 4: COMPLETE AGENT WIRING DIAGRAM

### 4A. The 10 Agents and Their Connections

```
╔══════════════════════════════════════════════════════════════════════════╗
║                    AGENT ORCHESTRATOR (core/agent_orchestrator.py)       ║
║         Schedules all agents. No LLM. Deterministic routing rules.       ║
║  Backed by: event-driven-autonomous-loop (H:\trade) as task queue        ║
╚════════════════════════════════════════════════════════════════════════════╝
    │
    ├──[every 6h]──► INTERNET CRAWLER AGENT
    │                tools/internet_crawler.py
    │                ├─ Reads: 50+ sources (see Section 3)
    │                ├─ Uses: Agent-Reach (Reddit/Twitter/RSS)
    │                │        WebAgent (browser-use + NIM 550B)
    │                │        worldmonitor MCP (macro signals)
    │                │        OpenBB MCP (commodity prices)
    │                ├─ LLM: NIM 550B → extracts signals from pages
    │                │       Ollama → bulk text classification
    │                └─ Writes: trend_signals, problem_opportunities,
    │                           discovered_sources tables
    │
    ├──[after crawler]─► TREND SIGNAL AGENT  
    │                    tools/trend_scout/trend_aggregator.py
    │                    ├─ Reads: Google Autocomplete API (no key)
    │                    │        Google Trends Explore API (no key)
    │                    │        trend_signals table (from crawler)
    │                    ├─ LLM: NONE — pure API calls + math
    │                    └─ Writes: trend_signals table (with momentum scores)
    │
    ├──[after trend signal]─► NICHE EXPANDER AGENT
    │                         tools/niche_expander.py
    │                         ├─ Reads: trend_signals (last 24h)
    │                         │        dynamic_niches (current active)
    │                         │        gate outcomes (which niches succeeded)
    │                         ├─ Logic: if category appears in ≥3 signals
    │                         │         with interest_score > 60 → add niche
    │                         │         if niche has 0 products in 3 scans → deactivate
    │                         ├─ LLM: NIM 550B (weekly rebalance only)
    │                         └─ Writes: dynamic_niches table
    │
    ├──[09:00 daily]─► DISCOVERY AGENT
    │                  tools/discovery_engine.py
    │                  ├─ Reads: dynamic_niches (active only)
    │                  │         dynamic_seed_keywords (weighted)
    │                  │         agentmemory (past successful queries)
    │                  ├─ Uses: WebAgent.search_all_marketplaces()
    │                  │        (Amazon.in + Flipkart + Meesho in parallel)
    │                  │        Agent-Reach for RSS/structured sources
    │                  ├─ LLM: NIM 550B (drives browser-use Chrome agent)
    │                  ├─ Validates: ValidationPipeline (Pydantic, no LLM)
    │                  ├─ Deduplicates: ProductMatcher (fuzzy, no LLM)
    │                  └─ Writes: master_products, scraped_listings,
    │                             multi_platform_listings tables
    │
    ├──[after discovery]─► PROBLEM MINER AGENT
    │                      tools/problem_miner.py
    │                      ├─ Reads: master_products (newly discovered)
    │                      │         problem_opportunities table
    │                      ├─ For each product:
    │                      │   ├─ Amazon Q&A → WebAgent reads → Ollama extracts
    │                      │   ├─ Reddit complaints → Agent-Reach → Ollama classifies
    │                      │   ├─ YouTube comments → Agent-Reach transcript → Ollama
    │                      │   └─ Flipkart reviews → WebAgent → Ollama
    │                      ├─ LLM: Ollama (bulk extraction on all products)
    │                      │       NIM 550B (synthesis: "what product solves this?")
    │                      └─ Writes: defect_clusters, problem_opportunities tables
    │
    ├──[15:00 daily]─► GATE ENGINE AGENT
    │                  core/gate_engine.py
    │                  ├─ Reads: master_products (validation_status='pending')
    │                  │         product_gate_progress (resume incomplete)
    │                  │         learned_rules (from rule_engine.py)
    │                  │         agentmemory (gate history per category)
    │                  │
    │                  ├─ GATE 1: BSR Check (Deterministic — Keepa API)
    │                  │   ├─ Input: ASIN + marketplace
    │                  │   ├─ Logic: BSR < 50,000 AND CoeffVariation < 0.30
    │                  │   ├─ LLM: NONE
    │                  │   └─ Output: PASS/FAIL → product_gate_progress
    │                  │
    │                  ├─ GATE 2: Defect Mining (Ollama — local, bulk)
    │                  │   ├─ Input: defect_clusters (from ProblemMiner)
    │                  │   ├─ Logic: ≥1 fixable defect found in 3-star reviews
    │                  │   ├─ LLM: Ollama (already mined by ProblemMiner)
    │                  │   └─ Output: PASS/FAIL + defect_list → defect_clusters
    │                  │
    │                  ├─ GATE 3: Economics (Deterministic — 15-factor math)
    │                  │   ├─ Input: price, category, weight, BSR
    │                  │   │         Live: USD/INR from OpenBB, commodity from worldmonitor
    │                  │   ├─ Logic: 15-factor P&L → net_margin ≥ 20%
    │                  │   ├─ LLM: NONE
    │                  │   └─ Output: PASS/FAIL + full P&L → economics_assessments
    │                  │
    │                  ├─ GATE 4: Deterministic Scoring (ScoringEngine, NO LLM)
    │                  │   ├─ Input: full dossier (G1+G2+G3 outputs combined)
    │                  │   ├─ LLM: NONE — deterministic weighted rubric
    │                  │   │       BSR signal: 25 pts
    │                  │   │       Review quality: 20 pts
    │                  │   │       Margin safety: 40 pts
    │                  │   │       Defect fixability: 10 pts
    │                  │   │       Competition density: 5 pts
    │                  │   ├─ Thresholds: ≥75 PROCEED | ≥60 MARGINAL | <60 REJECT
    │                  │   └─ Output: verdict + score breakdown → launchpad_items (if PROCEED)
    │                  │
    │                  ├─ GATE 5 [PLANNED]: NIM 550B Arbiter (upgrade, not yet built)
    │                  │   ├─ Input: G1-G4 full dossier + market context
    │                  │   ├─ LLM: LLMRouter.chat(agent="gate5_arbiter")
    │                  │   │       → NIM 550B (tier 1, preferred)
    │                  │   │       → Ollama (tier 2 fallback)
    │                  │   │       → Groq 70B (tier 3 fallback)
    │                  │   │       → kimi-k3 (tier 4, batch only)
    │                  │   │       → Human override (tier 5)
    │                  │   ├─ Prompt: "Review this scored product. Override?"
    │                  │   │          CONFIRM|OVERRIDE_REJECT|OVERRIDE_PROCEED + risk_flags
    │                  │   ├─ Can override Gate 4 score if strong reasoning provided
    │                  │   └─ Output: final_verdict → launchpad_items
    │                  │
    │                  ├─ Rule Engine (applied at every gate):
    │                  │   ├─ Reads: learned_rules table
    │                  │   └─ Auto-rejects/approves based on learned patterns
    │                  │
    │                  └─ Writes: product_gate_progress, gate_logs, arbiter_decision_log,
    │                             launchpad_items (PROCEED products)
    │
    ├──[on PROCEED]─► SUPPLIER AGENT
    │                 tools/supplier_agent.py
    │                 ├─ Reads: launchpad_items (new PROCEED products)
    │                 │         defect_clusters (v2.0 improvement spec)
    │                 │         agentmemory (past supplier interactions)
    │                 ├─ Discovery:
    │                 │   ├─ IndiaMART JSON API (curl_cffi, fast, no browser)
    │                 │   │   URL: dir.indiamart.com/search.mp?ss={query}&biz=1
    │                 │   ├─ Alibaba → WebAgent (browser-use)
    │                 │   ├─ ExportersIndia → WebAgent
    │                 │   └─ TradeIndia → WebAgent
    │                 ├─ Verification:
    │                 │   ├─ GST Verifier → mastergst.com API (free)
    │                 │   └─ Scores: badge + gst_valid + contact + relevance
    │                 ├─ LLM: NIM 550B (via LLMRouter)
    │                 │       → scores relevance, extracts contact info
    │                 └─ Writes: supplier_profiles table (status=PENDING)
    │
    ├──[after supplier]─► OUTREACH ENGINE (MANUAL MODE BY DEFAULT)
    │                     core/outreach_engine.py
    │                     ├─ Reads: supplier_profiles (status=PENDING)
    │                     │         defect_clusters (v2.0 improvements)
    │                     │         economics_assessments (target price)
    │                     ├─ LLM: NIM 550B → drafts personalized email
    │                     │       Email content includes:
    │                     │         - Product spec with specific v2.0 improvements
    │                     │         - Quantity: "initial order 500 units"
    │                     │         - Asks for: catalog, MOQ pricing, sample cost
    │                     │         - NEVER: price target, payment, commitment
    │                     │
    │                     │   ─── HUMAN APPROVAL GATE ───
    │                     │
    │                     ├─ Dashboard Suppliers tab shows:
    │                     │   supplier card + GST status + draft email
    │                     ├─ Human clicks: APPROVE → SMTP sends
    │                     │               EDIT → modify draft → APPROVE
    │                     │               REJECT → mark closed
    │                     │               HOLD → revisit later
    │                     │
    │                     ├─ Outreach channels (in priority order):
    │                     │   1. Email (SMTP via OpenCompany Gmail node)
    │                     │   2. WhatsApp (evolution-go REST API)
    │                     │   3. IndiaMART chat (WebAgent clicks "Contact Supplier")
    │                     │
    │                     └─ Writes: outreach_drafts, supplier_conversations tables
    │
    └──[Sunday 23:00]─► LEARNING AGENT
                        core/learning_engine.py
                        ├─ Reads: gate_logs (last 30 days)
                        │         master_products (with gate outcomes)
                        │         supplier_conversations (reply rates)
                        │         dynamic_niches (scan history)
                        │         dynamic_seed_keywords (performance)
                        │         agentmemory (cross-session learnings)
                        ├─ Analyses:
                        │   ├─ Category gate failure patterns → learned_rules
                        │   ├─ Niche performance → priority_score updates
                        │   ├─ Keyword yield → weight updates
                        │   ├─ Supplier response rates → ranking updates
                        │   └─ Source yield → source priority updates
                        ├─ LLM: NIM 550B (via LLMRouter)
                        │       Prompt: "Analyze 30-day research outcomes.
                        │               What rules should we add?
                        │               Which niches to add/remove?
                        │               Which sources are working?"
                        └─ Writes: learned_rules, updated niche priorities,
                                   keyword weights, source priorities,
                                   weekly_summary (shown in dashboard)
```

### 4B. External Tools Wiring

```python
# OpenCompany — Visual Orchestration Layer
# Runs at localhost:5678
# Wires agents via HTTP webhook nodes
# Each APRS Python module exposes a simple HTTP endpoint (FastAPI)
# OpenCompany calls the endpoint on schedule, handles retry + alerting

APRS_ENDPOINTS = {
    "POST /run/crawler":    "InternetCrawlerAgent.crawl_cycle()",
    "POST /run/trend":      "TrendSignalAgent.scan()",
    "POST /run/expand":     "NicheExpander.expand_from_signals()",
    "POST /run/discover":   "DiscoveryAgent.run_batch()",
    "POST /run/mine":       "ProblemMiner.mine_batch()",
    "POST /run/gates":      "GateEngine.run_pending_batch()",
    "POST /run/suppliers":  "SupplierAgent.run_pending()",
    "POST /run/learn":      "LearningAgent.weekly_synthesis()",
    "GET  /health":         "All agent status + LLM tier health",
    "POST /override/agent": "Set agent mode (auto/manual/disabled/force_tier)",
}

# agentmemory — Persistent Memory (MCP server at localhost:3333)
MEMORY_USAGE = {
    "InternetCrawler": "remember successful source URLs and their yield",
    "Discovery":        "remember which queries found high-scoring products",
    "GateEngine":       "remember category gate pass rates",
    "SupplierAgent":    "remember supplier quality patterns by cluster/city",
    "LearningAgent":    "write and read weekly learning summaries",
}
# All agents call: memory.store(key, value, confidence=0.9)
#                  memory.recall(query, top_k=5)

# Agent-Reach — Internet Access (MCP server)
AGENT_REACH_TOOLS = {
    "reddit_scraper":       "Get top posts from any subreddit",
    "twitter_search":       "Search Twitter for keywords",
    "youtube_transcript":   "Get transcript from any YouTube video URL",
    "rss_subscribe":        "Subscribe to RSS feed, get new items",
    "web_extract":          "Get readable text from any URL (bypasses paywalls)",
    "duckduckgo_search":    "Web search with result snippets",
}

# worldmonitor MCP — Macro Intelligence
WORLDMONITOR_QUERIES = {
    "commodity":    "Get current price of cotton, steel, ABS plastic, bamboo",
    "macro_india":  "Consumer sentiment index, PMI, import/export volumes",
    "instability":  "Country instability score for China (supplier risk)",
}

# OpenBB MCP — Financial Data
OPENBB_CALLS = {
    "usd_inr":      "obb.currency.price.historical('USDINR=X') → latest rate",
    "commodity":    "obb.commodity.price.historical('COTTON') → raw material cost",
    "india_cpi":    "obb.economy.price.cpi(country='india') → inflation context",
}

# evolution-go — WhatsApp API (HTTP server at localhost:8080)
WHATSAPP_USAGE = {
    "send_opportunity_alert": "When product passes Gate 4 → WhatsApp you with summary",
    "send_supplier_message":  "After human approves → WhatsApp supplier",
    "receive_supplier_reply": "Supplier replies → webhook → OutreachEngine.parse()",
    "send_weekly_report":     "Sunday evening → WhatsApp you the week's findings",
}

# crm — Supplier CRM (localhost:3000 or embedded in dashboard)
CRM_INTEGRATION = {
    "create_contact":     "When supplier found → create CRM contact",
    "enrich_company":     "CRM agent auto-researches: GST, founding year, products",
    "record_fact":        "Every email sent/received → logged to contact timeline",
    "schedule_recheck":   "No reply in 7 days → auto-schedule follow-up",
    "get_contact_history":"Before drafting email → pull all past interactions",
}

# event-driven-autonomous-loop — Task Queue
QUEUE_TASKS = [
    "scan_internet_sources",    # InternetCrawler
    "extract_trend_signals",    # TrendSignal
    "expand_niches",            # NicheExpander
    "discover_products",        # Discovery
    "mine_problems",            # ProblemMiner
    "run_gate_pipeline",        # GateEngine (Gate 1→2→3→4)
    "find_suppliers",           # SupplierAgent
    "draft_outreach",           # OutreachEngine
    "weekly_synthesis",         # LearningAgent
]
# Each task on completion → auto-enqueues next task in sequence
# If task fails → retry x3 → alert human → continue with next task
```

---

## SECTION 5: DATABASE — COMPLETE TABLE MAP

### Existing (26 tables — verified in database.py init_db())
`master_products`, `product_suppliers`, `daily_snapshots`, `meeting_audit_log`, `product_gate_progress`, `arbiter_decision_log`, `trend_signals`, `multi_platform_listings`, `swarm_audit_log`, `negative_findings`, `launchpad_items`, `defect_clusters`, `economics_assessments`, `discovered_sources`, `dynamic_niches`, `dynamic_seed_keywords`, `marketplace_config`, `scraped_listings`, `scraper_validations`, `ai_supervisor_logs` _(deprecated)_, `ai_task_improvements` _(deprecated)_, `website_capture_stats`, `url_validation_log`, **`learned_rules`** _(already in init_db)_, **`gate_logs`** _(already in init_db)_, **`review_snapshots`** _(already in init_db)_

### New Tables to Add (6 tables — NOT 8, learned_rules + gate_logs already exist)

```sql
-- 1. Supplier profiles from IndiaMART/Alibaba
supplier_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    platform TEXT NOT NULL,             -- indiamart|alibaba|exportersindia
    profile_url TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    gst_number TEXT,
    gst_verified INTEGER DEFAULT 0,
    gst_business_name TEXT,
    gst_status TEXT,                    -- Active|Cancelled|Suspended
    moq_estimate INTEGER,
    unit_price_range TEXT,
    verification_badge INTEGER DEFAULT 0,
    location_city TEXT,
    location_state TEXT,
    relevance_score REAL DEFAULT 0.0,
    outreach_status TEXT DEFAULT 'PENDING',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 2. Outreach drafts pending human approval
outreach_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id INTEGER REFERENCES supplier_profiles(id),
    product_id TEXT NOT NULL,
    channel TEXT DEFAULT 'email',       -- email|whatsapp|indiamart_chat
    draft_subject TEXT,
    draft_body TEXT NOT NULL,
    approval_status TEXT DEFAULT 'PENDING',
    approved_by TEXT,
    approved_at TEXT,
    sent_at TEXT,
    sent_via TEXT,                      -- smtp|evolution_go|webagent
    created_at TEXT DEFAULT (datetime('now'))
);

-- 3. Full supplier conversation threads
supplier_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    thread_id TEXT NOT NULL,
    supplier_id INTEGER REFERENCES supplier_profiles(id),
    product_id TEXT NOT NULL,
    turn_number INTEGER NOT NULL,
    direction TEXT NOT NULL,            -- OUTBOUND|INBOUND
    channel TEXT DEFAULT 'email',
    content TEXT NOT NULL,
    ai_classification TEXT,             -- catalog_received|question|negotiating|payment_request|escalate
    escalation_triggers_json TEXT,      -- list of triggered escalation codes
    draft_reply TEXT,
    reply_status TEXT DEFAULT 'PENDING',
    created_at TEXT DEFAULT (datetime('now'))
);

-- 4. Unmet needs and problem opportunities
problem_opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,          -- reddit|amazon_qa|quora|youtube|flipkart_review|forum
    source_url TEXT,
    problem_statement TEXT NOT NULL,
    product_category TEXT,
    severity_score REAL DEFAULT 0.0,    -- 0-1: how painful is this problem?
    frequency_count INTEGER DEFAULT 1,  -- how many people mention it?
    nim_synthesis TEXT,                 -- NIM 550B's synthesis of the problem
    v2_product_spec TEXT,               -- NIM-generated improvement spec
    related_product_id TEXT,            -- if tied to a specific discovered product
    status TEXT DEFAULT 'NEW',          -- NEW|NICHE_CREATED|PRODUCT_FOUND|CLOSED
    created_at TEXT DEFAULT (datetime('now'))
);

-- 5. LLM tier usage monitoring
llm_tier_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    tier_used INTEGER NOT NULL,         -- 1=NIM|2=Ollama|3=Groq|4=Kimi|5=Human
    model_name TEXT,
    task_type TEXT,
    tokens_used INTEGER,
    latency_ms INTEGER,
    success INTEGER DEFAULT 1,
    fallback_reason TEXT,               -- why did it fall back from previous tier?
    created_at TEXT DEFAULT (datetime('now'))
);

-- 6. Human override pending queue
pending_human_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    task_description TEXT NOT NULL,
    context_json TEXT NOT NULL,         -- full context for human to decide
    decision_options TEXT,              -- suggested options (PROCEED|REJECT|CUSTOM)
    human_decision TEXT,
    human_notes TEXT,
    status TEXT DEFAULT 'AWAITING',     -- AWAITING|DECIDED|EXPIRED
    expires_at TEXT,                    -- auto-expire after 24h → skip task
    created_at TEXT DEFAULT (datetime('now')),
    decided_at TEXT
);
```

---

## SECTION 6: COMPLETE FILE STRUCTURE

```
D:\ecomm-strategy\
│
├── config/
│   ├── settings.py          ✅ DONE — STILL MISSING: groq_api_key, kimi_model_path,
│   │                                       kimi_preset, kimi_enabled, LLM_TIER_*,
│   │                                       AGENT_*_MODE (all Tier 3/4/5 fields)
│   ├── fees.py              ✅ DONE
│   └── .env                 ✅ DONE — add new keys
│
├── core/
│   ├── database.py          ✅ DONE (26 tables) — ADD 6 new tables (NOT 8, learned_rules+gate_logs already exist)
│   ├── validation.py        ✅ DONE
│   ├── economics_engine.py  ✅ DONE — WIRE: OpenBB for live USD/INR + commodity
│   ├── scoring_engine.py    ✅ DONE
│   ├── rule_engine.py       ✅ DONE
│   ├── gate_engine.py       ✅ DONE — WIRE: LLMRouter for Gate 4
│   ├── pipeline.py          ✅ DONE
│   ├── backup.py            ✅ DONE
│   ├── logging_config.py    ✅ DONE
│   ├── utils.py             ✅ DONE
│   ├── models.py            ✅ DONE
│   ├── excel_manager.py     ✅ DONE
│   ├── team_meeting.py      ✅ DONE (keep)
│   ├── meeting_doc_manager.py ✅ DONE
│   │
│   ├── llm_router.py        ❌ BUILD — 5-tier fallback + manual override
│   ├── nim_client.py        ❌ BUILD — NIM 550B wrapper (calls LLMRouter)
│   ├── kimi_wrapper.py      ❌ BUILD — C binary subprocess wrapper (WSL)
│   ├── groq_client.py       ❌ BUILD — Groq free API client
│   ├── supplier_models.py   ❌ BUILD — Pydantic models for supplier pipeline
│   ├── outreach_engine.py   ❌ BUILD — NIM drafting + human approval gate
│   ├── agent_orchestrator.py ❌ BUILD — OR replace with OpenCompany
│   ├── scheduler.py         ❌ BUILD — OR replace with OpenCompany
│   └── learning_engine.py   ❌ BUILD
│
├── tools/
│   ├── web_agent.py         ✅ DONE — browser-use + NIM 550B
│   ├── amazon_scraper.py    ✅ DONE (kept as fallback)
│   ├── flipkart_scraper.py  ✅ DONE (kept as fallback)
│   ├── discovery_engine.py  ✅ DONE — WIRE: WebAgent + AgentReach
│   ├── review_miner.py      ✅ DONE
│   ├── keepa_api_client.py  ✅ DONE
│   ├── google_trends_engine.py ✅ DONE
│   ├── import_gguf_to_ollama.py ✅ DONE
│   ├── bulk_discovery_engine.py ✅ DONE (wire to orchestrator)
│   ├── print_fresh_discovery.py ✅ DONE (utility)
│   ├── run_live_realtime_scan.py ✅ DONE (wire to orchestrator)
│   │
│   ├── trend_scout/
│   │   ├── trend_aggregator.py ✅ DONE — WIRE to orchestrator
│   │   └── __init__.py      ✅ DONE
│   │
│   ├── adapters/
│   │   ├── base_adapter.py  ✅ DONE
│   │   └── __init__.py      ✅ DONE
│   │
│   ├── internet_crawler.py  ❌ BUILD — reads 50+ sources
│   ├── niche_expander.py    ❌ BUILD — trends → niches auto
│   ├── supplier_agent.py    ❌ BUILD — IndiaMART + Alibaba + GST verify
│   ├── gst_verifier.py      ❌ BUILD — mastergst.com API
│   └── problem_miner.py     ❌ BUILD — unmet needs mining
│
├── integrations/            ❌ NEW DIRECTORY
│   ├── agent_reach.py       ❌ BUILD — Agent-Reach MCP client wrapper
│   ├── openbb_client.py     ❌ BUILD — OpenBB MCP wrapper for economics
│   ├── worldmonitor.py      ❌ BUILD — worldmonitor MCP client
│   ├── evolution_go.py      ❌ BUILD — WhatsApp REST API client
│   ├── crm_client.py        ❌ BUILD — CRM API client
│   └── opencompany.py       ❌ BUILD — OpenCompany webhook endpoints
│
├── web/
│   └── app.py               ✅ DONE (4 tabs) — ADD:
│                              Tab 5: Suppliers (crm embed + outreach)
│                              Tab 6: Agent Control (LLM tier health + overrides)
│                              Tab 7: Data Sources (source list + yield stats)
│
├── tests/                   ✅ DONE — add tests for new modules
├── main.py                  ✅ DONE — add --daemon flag for orchestrator
├── roadmap.md               ✅ THIS FILE
└── deprecated/              ✅ (old V5 files moved here)
```

---

## SECTION 7: LLM FALLBACK WIRING — EVERY AI CALL

```python
# core/llm_router.py routes ALL of these:

AI_CALLS_IN_SYSTEM = {
    
    # InternetCrawlerAgent
    "extract_trend_signals":         {"default": "nim", "task_type": "realtime"},
    "classify_page_content":         {"default": "ollama", "task_type": "batch"},
    "discover_new_sources":          {"default": "nim", "task_type": "realtime"},
    
    # NicheExpander
    "weekly_niche_rebalance":        {"default": "nim", "task_type": "batch"},
    "niche_quality_check":           {"default": "ollama", "task_type": "batch"},
    
    # DiscoveryAgent (WebAgent drives Chrome)
    "browser_navigate_amazon":       {"default": "nim", "task_type": "realtime"},
    "browser_navigate_flipkart":     {"default": "nim", "task_type": "realtime"},
    "browser_navigate_meesho":       {"default": "nim", "task_type": "realtime"},
    "browser_navigate_supplier":     {"default": "nim", "task_type": "realtime"},
    
    # ProblemMiner
    "extract_amazon_qa_problems":    {"default": "ollama", "task_type": "batch"},
    "extract_reddit_complaints":     {"default": "ollama", "task_type": "batch"},
    "extract_youtube_pain_points":   {"default": "ollama", "task_type": "batch"},
    "synthesize_product_opportunity":{"default": "nim", "task_type": "batch"},
    
    # GateEngine
    # Gate 1: NO LLM (Keepa API + math)
    # Gate 2: review_miner.py uses Ollama already
    # Gate 3: NO LLM (15-factor math)
    # Gate 4: NO LLM (deterministic ScoringEngine — 5-factor weighted rubric)
    "gate5_arbiter_override":         {"default": "nim", "task_type": "realtime",
                                      "status": "PLANNED — not yet built",
                                      "fallback_ok": True},  # accepts Ollama/Groq verdict
    
    # SupplierAgent
    "extract_supplier_contacts":     {"default": "nim", "task_type": "realtime"},
    "score_supplier_relevance":      {"default": "ollama", "task_type": "batch"},
    
    # OutreachEngine
    "draft_initial_email":           {"default": "nim", "task_type": "realtime"},
    "classify_supplier_reply":       {"default": "nim", "task_type": "realtime"},
    "check_escalation_triggers":     {"default": "none",  # regex first, LLM only if regex unclear
                                      "fallback": "ollama"},
    "draft_follow_up_email":         {"default": "nim", "task_type": "realtime"},
    "parse_catalog_from_reply":      {"default": "ollama", "task_type": "batch"},
    
    # LearningAgent
    "analyze_gate_patterns":         {"default": "nim", "task_type": "batch",
                                      "kimi_ok": True},  # kimi-k3 OK for overnight
    "generate_weekly_report":        {"default": "nim", "task_type": "batch",
                                      "kimi_ok": True},
    "reweight_niches":               {"default": "ollama", "task_type": "batch"},
}
```

---

## SECTION 8: SETTINGS — COMPLETE .ENV TEMPLATE

```bash
# ═══════════════════════════════════════════════════════
# APRS V7 — Complete Environment Configuration
# ═══════════════════════════════════════════════════════

# ── NIM 550B (Tier 1) ──────────────────────────────────
NIM_API_KEY=your_nim_key_here
NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NIM_MODEL=nvidia/nemotron-3-ultra-550b-a55b
NIM_ARBITER_ENABLED=true
NIM_TEMPERATURE=0.1
NIM_MAX_TOKENS=4096
LLM_TIER_1_ENABLED=true

# ── Ollama Local (Tier 2) ──────────────────────────────
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen27b_iq1
OLLAMA_FALLBACK_MODEL=llama3.1:8b
OLLAMA_CONTEXT_WINDOW=8192
OLLAMA_TEMPERATURE=0.2
LLM_TIER_2_ENABLED=true

# ── Groq Free (Tier 3) ─────────────────────────────────
GROQ_API_KEY=your_groq_key_from_console.groq.com
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_BASE_URL=https://api.groq.com/openai/v1
LLM_TIER_3_ENABLED=true

# ── kimi-k3-in-c (Tier 4) — BATCH ONLY ────────────────
KIMI_ENABLED=false                    # Enable only if you have 1.56TB model
KIMI_MODEL_PATH=/mnt/h/kimi/k3model   # WSL path to model checkpoint
KIMI_TRUNK_PATH=/mnt/h/kimi/k3trunk
KIMI_PRESET=server                    # laptop|server (based on RAM)
LLM_TIER_4_ENABLED=false

# ── Human Override (Tier 5) ────────────────────────────
LLM_TIER_5_MANUAL_FALLBACK=true
HUMAN_DECISION_TIMEOUT_HOURS=24       # Auto-expire pending decisions after 24h

# ── Per-Agent LLM Override ─────────────────────────────
AGENT_GATE4_LLM=auto                  # nim|ollama|groq|kimi|manual|auto
AGENT_OUTREACH_LLM=manual             # outreach always human-reviewed
AGENT_DEFECT_LLM=ollama               # bulk, always use local
AGENT_LEARNING_LLM=auto
AGENT_SUPPLIER_LLM=auto
AGENT_DISCOVERY_LLM=auto

# ── Per-Agent Enable/Disable ───────────────────────────
AGENT_INTERNET_CRAWLER_ENABLED=true
AGENT_TREND_SIGNAL_ENABLED=true
AGENT_NICHE_EXPANDER_ENABLED=true
AGENT_DISCOVERY_ENABLED=true
AGENT_PROBLEM_MINER_ENABLED=true
AGENT_GATE_ENGINE_ENABLED=true
AGENT_SUPPLIER_ENABLED=true
AGENT_OUTREACH_ENABLED=true
AGENT_LEARNING_ENABLED=true

# ── Data APIs ──────────────────────────────────────────
KEEPA_API_KEY=your_keepa_key

# ── External Tools ─────────────────────────────────────
OPENCOMPANY_URL=http://localhost:5678
OPENCOMPANY_WEBHOOK_SECRET=your_secret
AGENT_REACH_MCP_URL=http://localhost:3001
AGENTMEMORY_MCP_URL=http://localhost:3333
WORLDMONITOR_MCP_URL=http://localhost:3002
OPENBB_MCP_URL=http://localhost:3003
EVOLUTION_GO_URL=http://localhost:8080
EVOLUTION_GO_INSTANCE=aprs-whatsapp
CRM_URL=http://localhost:3000
CRM_API_KEY=your_crm_key

# ── Email (SMTP) ────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_app_password
OUTREACH_FROM_NAME=Your Business Name

# ── WhatsApp ────────────────────────────────────────────
WHATSAPP_YOUR_NUMBER=+91XXXXXXXXXX
WHATSAPP_NOTIFY_ON_PROCEED=true
WHATSAPP_WEEKLY_REPORT=true

# ── WebAgent (browser-use) ─────────────────────────────
WEB_AGENT_HEADLESS=true
WEB_AGENT_TIMEOUT_S=180
WEB_AGENT_MAX_STEPS=20

# ── Scraping ────────────────────────────────────────────
SCRAPER_DELAY_MS=2000
SCRAPER_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36
SUPPLIER_PLATFORMS=indiamart,alibaba,exportersindia
SUPPLIER_MAX_RESULTS=8

# ── Gate Thresholds ─────────────────────────────────────
BSR_MAX_THRESHOLD=50000
BSR_CV_MAX=0.30
MIN_NET_MARGIN_PCT=20.0
SCORE_PROCEED_THRESHOLD=75
SCORE_MARGINAL_THRESHOLD=60

# ── Economics ───────────────────────────────────────────
TARGET_AOV_MIN_INR=500
TARGET_AOV_MAX_INR=2500
SWEET_SPOT_MSRP_INR=999
DEFAULT_COD_PCT=0.65
DEFAULT_RTO_PCT=0.18
PLATFORM_FEE_PCT=0.15
```

---

## SECTION 9: 4-WEEK BUILD SEQUENCE

### WEEK 1 — LLM Foundation + Supplier Pipeline

**Day 0 (PREREQUISITE — fix critical bugs from Gap Audit):**
- FIX C1: `tools/discovery_engine.py` L260 — replace `AmazonScraper`/`FlipkartScraper` block with WebAgent
- FIX C2: `tools/trend_scout/trend_aggregator.py` L32 — remove `ai_supervisor` import
- FIX C3: `core/team_meeting.py` L123 — stub out or delete `SupremeNIMCluster`
- FIX C4: `tests/test_phase6_e2e.py` L61 — rewrite test, remove `ai_supervisor` import
- FIX M5: `tools/discovery_engine.py` docstring — update "Playwright" → "browser-use WebAgent"
- FIX D4: `core/pipeline.py` L6 docstring — update "Playwright scrapers" → "WebAgent"
- Verify: `C:\Python314\python.exe -m pytest tests/ -v --tb=short` — all 100 tests pass

**Day 1:** `core/llm_router.py` — 5-tier fallback + manual override
- `core/nim_client.py` — NIM 550B wrapper
- `core/groq_client.py` — Groq free API wrapper
- `core/kimi_wrapper.py` — C binary subprocess via WSL

**Day 2:** `core/supplier_models.py` — Pydantic models
- `tools/gst_verifier.py` — mastergst.com API
- `tools/supplier_agent.py` — IndiaMART + Alibaba + GST verify

**Day 3:** `core/outreach_engine.py` — NIM drafting + human gate
- `integrations/evolution_go.py` — WhatsApp API client
- SMTP wiring via OpenCompany Gmail node

**Day 4:** `core/database.py` — add 6 new tables (learned_rules + gate_logs already exist)
- Test: product PROCEED → supplier found → draft email shown → human approves → email sends

**Day 5:** `web/app.py` — Tab 5: Suppliers tab
- `web/app.py` — Tab 6: Agent Control panel (LLM tier health + overrides)

**Day 6-7:** Integration test — full PROCEED product → supplier → email flow

---

### WEEK 2 — Intelligence + Data Collection

**Day 1-2:** `tools/problem_miner.py`
- Mine Amazon Q&A + Reddit + YouTube via Agent-Reach + WebAgent
- Ollama bulk extraction + NIM 550B synthesis

**Day 3:** `tools/internet_crawler.py` — seed 50+ sources
- `integrations/agent_reach.py` — Agent-Reach MCP client
- Wire all 3C problem sources + 3A trend sources

**Day 4:** `tools/niche_expander.py` — auto-expand from signals
- Wire `trend_scout/trend_aggregator.py` → `dynamic_niches` auto

**Day 5:** `integrations/worldmonitor.py` — commodity prices
- `integrations/openbb_client.py` — USD/INR + macro
- Wire economics_engine to live rates

**Day 6-7:** Start OpenCompany setup + wire first 3 agents as workflows

---

### WEEK 3 — Full Autonomy

**Day 1-2:** `core/agent_orchestrator.py` — deterministic routing
- OR: finish OpenCompany workflow wiring (replaces orchestrator)
- `core/scheduler.py` — APScheduler cron

**Day 3:** `integrations/agentmemory.py` — persistent memory client
- Wire agentmemory to all 10 agents

**Day 4-5:** `core/learning_engine.py` — weekly self-improvement

**Day 6:** `web/app.py` — Tab 7: Data Sources (source list + yield stats)

**Day 7:** 24-hour autonomous test run — no human input, verify:
- [ ] Crawler runs every 6h
- [ ] New niches added automatically
- [ ] Products discovered and gated
- [ ] Suppliers found for PROCEED products
- [ ] Outreach drafts waiting in dashboard

---

### WEEK 4 — Production Hardening

**Day 1-2:** Full test suite — all new modules
- LLMRouter fallback tests (mock NIM timeout → verify Ollama used)
- Supplier pipeline E2E test (mock IndiaMART response)
- Escalation trigger tests (mock payment request → verify alert)

**Day 3:** Kimi-k3-in-c setup (if proceeding):
- Install WSL2 if not present
- Compile kimi-k3 binary in WSL
- Verify WSL subprocess call works from Windows Python
- Set `KIMI_ENABLED=true` in .env

**Day 4:** First real production run:
- [ ] 5 active niches
- [ ] Live internet crawl
- [ ] Gate pipeline on real products
- [ ] Real supplier found and approved

**Day 5-7:** 35-minute Monday workflow validated. Iterate.

---

## SECTION 10: KIMI-K3-IN-C — PRACTICAL REALITY

```
CAN IT RUN? Yes, but with major constraints.

Constraint 1: Linux x86-64 only
  → Windows workaround: WSL2 (Windows Subsystem for Linux)
  → Binary runs inside WSL, Python calls it via subprocess
  → kimi_wrapper.py uses: subprocess.run(["wsl", "./bin/k3", ...])

Constraint 2: 1.56 TB model checkpoint
  → Must download from Hugging Face: moonshotai/Kimi-K3
  → Requires 1.56 TB free disk space on fast NVMe
  → Download: huggingface-cli download moonshotai/Kimi-K3 --local-dir /mnt/h/kimi/

Constraint 3: Speed (26.5 s/token at 8GB RAM)
  → 200-token response = 88 MINUTES
  → Completely impractical for real-time decisions
  → ONLY suitable for: overnight batch runs, weekly analysis, deep research
  → Tasks that CAN use kimi-k3:
    ✓ Weekly niche rebalance report (scheduled Sunday 23:00, done by 06:00)
    ✓ Deep product category analysis (one-shot, overnight)
    ✓ Annual trend synthesis report
  → Tasks that CANNOT use kimi-k3:
    ✗ Gate 4 arbiter (needs response in <60s)
    ✗ Browser agent driving (needs real-time)
    ✗ Any interactive or real-time task

Recommended setting: KIMI_ENABLED=false initially
  Enable only after: WSL2 confirmed working + 1.56TB model downloaded
  LLMRouter handles it transparently — enable in .env, no code changes
```

---

## SECTION 11: ESCALATION HARD STOPS

These patterns IMMEDIATELY stop all AI action and alert you:

```python
ESCALATION_PATTERNS = {
    # Payment demands — STOP IMMEDIATELY
    "advance_payment":    r"advance|upfront|token money|booking amount",
    "bank_transfer":      r"NEFT|RTGS|IMPS|bank transfer|bank account",
    "upi_payment":        r"UPI|PhonePe|Paytm|GPay payment|transfer ₹",
    
    # Commitment traps
    "quantity_commit":    r"minimum order.*commitment|purchase order.*advance",
    "contract_sign":      r"sign.*agreement|MOU|memorandum|contract",
    "agent_fee":          r"agent fee|middleman|commission.*advance",
    
    # Suspicious patterns
    "video_call_urgent":  r"video call|whatsapp video|verify.*call",
    "factory_visit":      r"visit.*factory|come to.*office|meet.*personally",
    "price_too_low":      r"₹[0-9]+.*per.*piece",  # cross-check vs market floor
    "very_high_moq":      r"MOQ.*[1-9][0-9]{4,}",  # MOQ > 9,999 units
}

# On ANY escalation trigger:
# 1. Stop ALL outreach for this supplier immediately
# 2. Mark supplier_conversation.direction = ESCALATED
# 3. WhatsApp alert to your number (via evolution-go)
# 4. Dashboard shows red banner with full conversation context
# 5. No further AI action until you dismiss the alert
```

---

## MONITORING DASHBOARD (Tab 6: Agent Control)

```
┌──────────────────────────────────────────────────────────────────────┐
│ SYSTEM STATUS                               Last updated: 5 min ago   │
├──────────────────────────────────────────────────────────────────────┤
│ LLM TIER HEALTH                                                        │
│  🟢 Tier 1 NIM 550B    Healthy   47 calls today  0 errors            │
│  🔴 Tier 2 Ollama      OFFLINE   Start: ollama serve                 │
│  🟢 Tier 3 Groq Free   Healthy   1,203/14,400 req  ████░░░░░░ 8%    │
│  ⚪ Tier 4 kimi-k3     Disabled  Enable: KIMI_ENABLED=true in .env   │
│  🟡 Tier 5 Human       Standby   2 pending decisions                 │
│                                                    [View Pending]     │
├──────────────────────────────────────────────────────────────────────┤
│ AGENT STATUS (last 24h)                                                │
│  InternetCrawler   ✅ 4 runs    38 signals collected                  │
│  TrendSignal       ✅ 4 runs    12 breakout keywords                  │
│  NicheExpander     ✅ 1 run     2 new niches added                    │
│  Discovery         ✅ 1 run     47 products found                     │
│  ProblemMiner      ✅ 1 run     23 products mined                     │
│  GateEngine        ✅ 1 run     47 evaluated → 3 PROCEED              │
│  SupplierAgent     ✅ 1 run     3 products → 19 suppliers found       │
│  OutreachEngine    ⏸ MANUAL    6 drafts awaiting approval            │
│  LearningAgent     💤 SCHEDULED Sunday 23:00                         │
├──────────────────────────────────────────────────────────────────────┤
│ DATA SOURCES (top performing)                                          │
│  reddit_indiabuy        34 signals this week  ████████░░             │
│  amazon_movers_shakers  28 signals this week  ███████░░░             │
│  meesho_trending        19 signals this week  █████░░░░░             │
│  google_trends          14 signals this week  ████░░░░░░             │
│  twitter_viral          8 signals this week   ██░░░░░░░░             │
│                                      [View All 50+ Sources]           │
└──────────────────────────────────────────────────────────────────────┘
```

---

## SUCCESS DEFINITION

```
WEEK 1 DONE WHEN:
  ✓ LLMRouter tested: NIM → Ollama → Groq → Human override all work
  ✓ Supplier found for 1 test product, GST verified
  ✓ Draft email shown in dashboard, human approves, email sends

WEEK 2 DONE WHEN:
  ✓ Internet crawler runs 6h cycle, finds 10+ trend signals
  ✓ New niche auto-added from trend signal
  ✓ Problem miner finds 1+ unmet need from Reddit/Amazon

WEEK 3 DONE WHEN:
  ✓ System runs 24h without human input
  ✓ Dashboard shows: signals → niches → products → gates → suppliers → drafts
  ✓ agentmemory persists data across restarts

WEEK 4 DONE WHEN:
  ✓ First real email sent to real IndiaMART supplier
  ✓ System finds product on Monday, supplier contacted by Wednesday
  ✓ 35-minute Monday review workflow validated
```
