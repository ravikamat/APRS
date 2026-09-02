# APRS — Autonomous Product Research System
## Master Roadmap & Architecture Blueprint v3.0

> **Last Updated:** 2026-09-02  
> **Vision:** 100% autonomous multi-agent system that continuously scrapes the internet, identifies emerging trends, finds problems people face, discovers products, validates economics, finds suppliers, drafts outreach — no human involvement until the final investment decision.  
> **Philosophy:** Multi-agent NIM 550B reasoning + deterministic math + local Ollama at scale. Humans decide on money only.

---

## PHASE COMPLETION STATUS

### COMPLETED — V6 Foundation

| Module | File | Lines | Status |
|--------|------|--------|--------|
| Pydantic settings | `config/settings.py` | 197 | DONE + NIM/WebAgent fields added |
| Marketplace fees | `config/fees.py` | 82 | DONE |
| Pydantic validation | `core/validation.py` | 224 | DONE |
| 15-factor economics | `core/economics_engine.py` | 435 | DONE |
| Deterministic scoring | `core/scoring_engine.py` | 85 | DONE |
| Rule accumulator + 8 seed rules | `core/rule_engine.py` | 541 | DONE |
| 4-gate engine | `core/gate_engine.py` | 539 | DONE |
| E2E pipeline | `core/pipeline.py` | 281 | DONE |
| 23-table SQLite SSOT | `core/database.py` | 2140 | DONE |
| Ollama defect miner | `tools/review_miner.py` | 195 | DONE |
| Keepa BSR client | `tools/keepa_api_client.py` | 171 | DONE |
| Discovery engine | `tools/discovery_engine.py` | 301 | DONE — refactored to WebAgent |
| Universal WebAgent | `tools/web_agent.py` | 381 | NEW — browser-use + NIM 550B |
| Google Trends engine | `tools/google_trends_engine.py` | 209 | DONE |
| Trend scout (Reddit/Google) | `tools/trend_scout/trend_aggregator.py` | 307 | DONE (needs wiring) |
| Source adapter base | `tools/adapters/base_adapter.py` | 65 | DONE |
| 4-tab Streamlit dashboard | `web/app.py` | 807 | DONE (needs Suppliers tab) |
| CLI entrypoint | `main.py` | 311 | DONE |

### EXISTS BUT NOT WIRED

| Module | File | Issue |
|--------|------|-------|
| Trend scout | `tools/trend_scout/trend_aggregator.py` | NOT auto-feeding `dynamic_niches` table |
| Bulk discovery | `tools/bulk_discovery_engine.py` | Standalone script, not in pipeline |
| Live scan | `tools/run_live_realtime_scan.py` | Standalone, not scheduled |
| Orchestrator | `core/orchestrator.py` | V5 artifact — kept for `ComprehensiveUnitEconomics` only |

### NOT YET BUILT (V7 Targets)

| Module | Target File | Priority |
|--------|-------------|----------|
| NIM 550B client | `core/nim_client.py` | CRITICAL |
| Supplier models | `core/supplier_models.py` | CRITICAL |
| Supplier agent | `tools/supplier_agent.py` | CRITICAL |
| Outreach engine | `core/outreach_engine.py` | CRITICAL |
| Problem miner | `tools/problem_miner.py` | CRITICAL |
| Internet crawler | `tools/internet_crawler.py` | HIGH |
| Niche auto-expander | `tools/niche_expander.py` | HIGH |
| GST verifier | `tools/gst_verifier.py` | HIGH |
| Agent orchestrator | `core/agent_orchestrator.py` | HIGH |
| Suppliers tab UI | `web/app.py` 5th tab | HIGH |
| 6 missing DB tables | `core/database.py` | HIGH |
| Self-improvement loop | `core/learning_engine.py` | MEDIUM |
| Scheduler/cron | `core/scheduler.py` | MEDIUM |

---

## COMPLETE VISION: 5-Layer Autonomous Architecture

```
LAYER 0: INTERNET INTELLIGENCE (24/7 autonomous)
  InternetCrawlerAgent reads:
  - Google Trends breakout keywords (India, real-time)
  - Reddit: r/IndiaBuy, r/amazonfinds, r/tiktokmademebuyit,
            r/IndianBeautyDeals, r/frugalmalefashion, r/malelifestyle
  - YouTube trending product demos and reviews
  - Twitter/X viral commerce keywords
  - Meesho/Flipkart viral and trending sections
  - Amazon Q&A unanswered questions (unmet needs)
  - Quora product complaint questions
  - Forum complaints (DIY, HomeImprovement, BuyItForLife)
  - Small D2C sites: Mamaearth, WOW, Bombay Shaving (new launches)
  - International: Temu trending, AliExpress bestsellers
  Output: trend_signals, problem_opportunities → feeds dynamic_niches

LAYER 1: PRODUCT DISCOVERY (fully autonomous)
  DiscoveryAgent reads dynamic_niches
  WebAgent (NIM 550B + browser-use) searches:
  - Amazon.in, Flipkart, Meesho in parallel
  - Any site found by InternetCrawler
  ValidationPipeline + Deduplication
  Output: CanonicalProduct[] → master_products table

LAYER 2: PROBLEM-PRODUCT MATCHING (fully autonomous)
  ProblemMinerAgent:
  - ReviewMiner: mines 3-star reviews via Ollama (bulk)
  - ProblemMiner: reads Reddit/Quora/YouTube comments via Ollama
  - NIM 550B synthesizes: "People want X but products fail at Y"
  - Generates v2.0 BOM spec: same product + fix Y
  Output: DefectCluster + v2.0 improvement spec → defect_clusters table

LAYER 3: GATE VALIDATION (fully autonomous)
  Gate 1: Keepa BSR < 50,000, CV < 0.30 (deterministic)
  Gate 2: >=1 fixable defect found (Ollama)
  Gate 3: >=20% net margin, 15-factor economics (deterministic math)
  Gate 4: NIM 550B arbiter "would you invest?" consensus
  RuleEngine: learned rules applied at every gate
  Output: PROCEED/MARGINAL/REJECT → product_gate_progress, launchpad_items

LAYER 4: SUPPLIER INTELLIGENCE (semi-autonomous, human approves emails)
  SupplierAgent:
  - IndiaMART JSON API (curl_cffi, fast, no browser)
  - Alibaba via WebAgent (browser-use fallback)
  - GST verification via govt API (filters fake companies)
  - Scores suppliers: badge + gst_verified + contact + relevance
  
  OutreachEngine (NIM 550B):
  - Drafts personalized 150-word email per supplier
  - References specific v2.0 improvements
  - Asks for: catalog, MOQ pricing, sample cost
  - NEVER mentions: price target, payment, commitments
  
  ---- HUMAN APPROVAL GATE ----
  Dashboard Suppliers tab shows draft → you click APPROVE
  Reply parsing: paste supplier reply → AI classifies + drafts response
  Escalation auto-detected: payment, advance, broker fee → ALERT + STOP

LAYER 5: SELF-IMPROVEMENT (weekly autonomous)
  LearningEngine reads last 30 days:
  - Which niches produced PROCEED? → increase priority
  - Which categories always fail Gate 3? → add learned_rule
  - Which keywords found nothing 3 weeks? → deactivate
  - Which suppliers replied fastest? → boost ranking
  NIM 550B weekly synthesis: recommend 5 new niches, prune 3 dead ones
  All improvements stored in DB — no code changes needed
```

---

## AGENT ROSTER (10 Agents)

| Agent | File | LLM | Role |
|-------|------|-----|------|
| InternetCrawlerAgent | `tools/internet_crawler.py` | WebAgent + NIM 550B | Reads internet 24/7 |
| TrendSignalAgent | `tools/trend_scout/trend_aggregator.py` | Google APIs (no LLM) | Breakout keywords |
| NicheExpanderAgent | `tools/niche_expander.py` | NIM 550B | Trends → new niches in DB |
| DiscoveryAgent | `tools/discovery_engine.py` | WebAgent + NIM 550B | Scrapes marketplaces |
| ProblemMinerAgent | `tools/problem_miner.py` | Ollama (bulk) + NIM 550B | Unmet needs mining |
| GateAgent | `core/gate_engine.py` | Keepa + Ollama + NIM 550B | 4-gate validation |
| SupplierAgent | `tools/supplier_agent.py` | WebAgent + NIM 550B | Supplier discovery + vetting |
| OutreachAgent | `core/outreach_engine.py` | NIM 550B | Personalized email drafting |
| LearningAgent | `core/learning_engine.py` | NIM 550B | Weekly self-improvement |
| AgentOrchestrator | `core/agent_orchestrator.py` | None (routing only) | Schedules all agents |

### LLM Assignment

```
NIM 550B (unlimited) — reasoning, quality tasks:
  Gate 4 arbiter, outreach drafting, problem synthesis,
  weekly rebalance, reply parsing, browser agent driving

Ollama qwen27b_iq1 (local) — volume, bulk tasks:
  Gate 2 defect extraction (runs on every product)
  Reddit/forum mining (thousands of posts per session)
  Bulk review reading (50+ products per day)

Deterministic math (no LLM) — speed critical:
  Gate 1 BSR, Gate 3 economics, Scoring 0-100,
  Deduplication, Pydantic validation, GST format check
```

---

## MODULES TO BUILD — DETAILED SPECS

### A1. `core/nim_client.py` (~150 lines) — CRITICAL

NIM 550B wrapper with retry + Ollama fallback.

```python
class NIMClient:
    def chat(self, messages, json_mode=False) -> str
        # 1. POST to integrate.api.nvidia.com/v1/chat/completions
        # 2. Retry 3x on rate limit (exponential backoff)
        # 3. Fallback to Ollama on persistent failure

    def arbiter_verdict(self, product_dossier: dict) -> ArbiterVerdict
        # Structured prompt → verdict: PROCEED|MARGINAL|REJECT
        # confidence: 0-100, reasoning: str, risk_flags: List[str]

    def synthesize_problem(self, reviews, forum_posts) -> str
        # "What problem do these people have a product could solve?"

    def expand_niches(self, trend_signals, current_niches) -> List[str]
        # Weekly: "Suggest 5 new product niches from these signals"

    def draft_outreach(self, supplier, product_spec) -> str
        # "Draft 150-word email to this supplier about this product"

    def parse_supplier_reply(self, reply, context) -> ReplyAnalysis
        # "Classify this reply + check escalation triggers + draft response"
```

Wire to: gate_engine Gate 4, outreach_engine, learning_engine, niche_expander

---

### A2. `core/supplier_models.py` (~120 lines) — CRITICAL

```python
class SupplierProfile(BaseModel):
    company_name, platform, profile_url, contact_phone, contact_email
    gst_number, gst_verified: bool, gst_business_name
    moq_estimate, unit_price_range, verification_badge: bool
    location_city, location_state, relevance_score: float
    outreach_status: PENDING|DRAFTED|SENT|REPLIED|ESCALATED|CLOSED

class OutreachDraft(BaseModel):
    supplier_id, product_id, draft_subject, draft_email
    approval_status: PENDING|APPROVED|REJECTED|SENT

class SupplierConversation(BaseModel):
    thread_id, supplier_id, product_id, turn_number
    direction: OUTBOUND|INBOUND
    content, ai_classification, escalation_triggers: List[str]
    draft_reply, reply_status: PENDING|APPROVED|SENT|SKIPPED

class GSTVerification(BaseModel):
    gst_number, is_valid: bool, legal_name, trade_name
    state, registration_date, taxpayer_type, status
```

---

### A3. `tools/supplier_agent.py` (~300 lines) — CRITICAL

```python
class SupplierAgent:
    # IndiaMART direct JSON (no browser, fast):
    INDIAMART_API = "https://dir.indiamart.com/search.mp?ss={query}&biz=1"

    async def discover_suppliers(product_spec, cluster, max_results=8)
        # 1. Try IndiaMART JSON API (curl_cffi)
        # 2. Fallback: WebAgent browser on IndiaMART
        # 3. Alibaba via WebAgent
        # 4. GST verify all found suppliers
        # 5. Score: badge + gst_verified + contact + relevance
        # Returns: List[SupplierProfile] sorted by score

    async def verify_gst(gst_number: str) -> GSTVerification
        # API: https://api.mastergst.com/returns/masterapi/gstn/{gst}
        # Validates: format + active status + legal name

    def check_escalation_triggers(reply_text: str) -> List[str]
        # Regex patterns for: advance payment, bank transfer,
        # agent fee, video call, factory visit, high MOQ
```

---

### A4. `core/outreach_engine.py` (~200 lines) — CRITICAL

```python
class OutreachEngine:
    async def draft_initial_outreach(supplier, product_spec, v2_improvements)
        # NIM 550B → 150-word email
        # References specific v2.0 improvements
        # Asks for: catalog, MOQ for 500 units, sample cost
        # NEVER mentions: price target, payment, commitment
        # Stores in outreach_drafts table as PENDING

    async def parse_supplier_reply(inbound_message, context, supplier)
        # 1. Regex escalation check (instant)
        # 2. If escalation → status=ESCALATED, dashboard alert
        # 3. Else → NIM 550B classifies + drafts reply
        # 4. Stores as PENDING (human approves before sending)

    def classify_reply(text: str) -> str
        # catalog_received|question|negotiating|payment_request|escalate
```

---

### B1. `tools/problem_miner.py` (~350 lines) — HIGH

The intelligence that finds UNMET NEEDS — not just existing products.

```python
class ProblemMiner:
    """
    Sources:
    1. Amazon Q&A unanswered questions (unmet need signal)
    2. Reddit complaints in niche communities
    3. Quora "why does X always break?" questions
    4. YouTube product video comments
    5. 3-star review patterns from review_miner.py
    """
    async def mine_amazon_qa(self, asin: str) -> List[ProblemOpportunity]
        # WebAgent reads Amazon Q&A section
        # NIM 550B: "What problem does this unanswered question reveal?"

    async def mine_reddit_complaints(self, keyword: str) -> List[ProblemOpportunity]
        # WebAgent searches Reddit for product complaints
        # Ollama (bulk): extracts problem statements
        # NIM 550B (synthesis): "Summarize the core unmet need"

    async def mine_youtube_comments(self, video_url: str) -> List[ProblemOpportunity]
        # WebAgent reads YouTube comments
        # Ollama: extracts pain points

    async def synthesize_opportunity(self, problems) -> ProductOpportunity
        # NIM 550B: "What product would solve these problems?
        # Describe the v2.0 spec."
        # Returns ProductOpportunity → feeds NicheExpander
```

---

### B2. `tools/internet_crawler.py` (~400 lines) — HIGH

```python
class InternetCrawlerAgent:
    """
    Knows WHERE to look and WHAT to search. Self-expanding source list.
    Schedule: every 6 hours via scheduler.py
    """
    SEED_SOURCES = {
        "trends": [
            "https://trends.google.com/trending?geo=IN",
            "https://www.youtube.com/feed/trending",
        ],
        "reddit": [
            "https://reddit.com/r/IndiaBuy/top/?t=week",
            "https://reddit.com/r/amazonfinds/top/?t=week",
            "https://reddit.com/r/tiktokmademebuyit/top/?t=week",
            "https://reddit.com/r/IndianBeautyDeals/top/?t=week",
            "https://reddit.com/r/frugalmalefashion/top/?t=week",
        ],
        "ecom_viral": [
            "https://www.meesho.com/collections/trending",
            "https://www.flipkart.com/store/trending-now",
        ],
        "problems": [
            "https://reddit.com/r/BuyItForLife/new/",
            "https://quora.com/search?q=product+that+would+solve",
        ],
    }

    async def crawl_cycle(self):
        # For each active source in discovered_sources table:
        #   WebAgent reads page
        #   NIM 550B extracts: trend signals, problems, product mentions
        #   Records to trend_signals, problem_opportunities
        # NIM 550B discovers NEW sources from page content
        # New sources added to discovered_sources table
        # Low-yield sources (3 empty runs) → deactivated

    async def extract_signals_from_page(self, url, source_type) -> List[dict]
        # trend → {keyword, category, interest_score}
        # problem → {problem_statement, category, severity}
        # product → {title, price, marketplace, viral_indicator}
```

---

### B3. `tools/niche_expander.py` (~200 lines) — HIGH

```python
class NicheExpander:
    async def expand_from_signals(self):
        # Reads last 24h trend_signals
        # Category appears in >=3 signals with interest > 60 → add niche

    async def prune_dead_niches(self):
        # 0 products found in last 3 scans → deactivate niche

    async def nim_weekly_rebalance(self):
        # NIM 550B reads: active niches + 30d signals + gate outcomes
        # Outputs: add_niches, remove_niches, priority_adjustments
```

---

### B4. `tools/gst_verifier.py` (~100 lines) — HIGH

```python
class GSTVerifier:
    # Free public GST lookup — filters fake suppliers instantly
    API = "https://api.mastergst.com/returns/masterapi/gstn/{gst}"

    def verify(self, gst_number: str) -> GSTVerification:
        # Validate format (15 alphanumeric)
        # API call → legal_name, status, registration_date
        # Check: status == "Active"
```

---

### B5. `core/agent_orchestrator.py` (~300 lines) — HIGH

```python
class AgentOrchestrator:
    """Coordinates all agents. No LLM. Deterministic routing."""

    # Daily schedule:
    # 00:00 / 06:00 / 12:00 / 18:00 → InternetCrawlerAgent.crawl_cycle()
    # 09:00 → NicheExpander.expand_from_signals()
    #          if new niches → DiscoveryAgent.run_batch()
    # 15:00 → GateAgent.run_full_pipeline() for pending products
    # 21:00 → NicheExpander.prune_dead_niches()
    # Sunday 23:00 → LearningAgent.weekly_synthesis()
    #                NicheExpander.nim_weekly_rebalance()

    # Event triggers:
    # New PROCEED product → SupplierAgent.discover_suppliers()
    # >=5 new trend signals in same category → immediate DiscoveryAgent scan

    async def run_forever(self):
        # APScheduler with above schedule
        # Health monitoring: alert if any agent fails 3x in a row
```

---

### C1. `core/learning_engine.py` (~250 lines) — MEDIUM

```python
class LearningEngine:
    """Runs weekly. Makes the system smarter over time without code changes."""

    async def analyze_gate_outcomes(self):
        # Which categories always fail Gate 3?
        # Add learned_rule: REJECT if category in [...] AND margin < X%

    async def reweight_niches(self):
        # PROCEED verdicts → increase niche priority_score
        # 0 PROCEED in 4 weeks → decrease priority

    async def improve_seed_keywords(self):
        # Best-performing keywords → increase weight
        # No results in 3 weeks → deactivate

    async def nim_weekly_report(self) -> str:
        # NIM 550B reads 30-day summary
        # Returns actionable "Week in Review" report
        # Saved to DB, shown on dashboard
```

---

## DATABASE — 6 TABLES TO ADD

```sql
learned_rules (
    id, rule_name, condition_expr, verdict,
    confidence, times_triggered, times_correct,
    created_at, last_triggered_at
);

gate_logs (
    id, product_id, gate_number, from_status, to_status,
    triggered_by, metadata_json, created_at
);

supplier_profiles (
    id, product_id, company_name, platform, profile_url,
    contact_phone, contact_email, gst_number, gst_verified,
    gst_business_name, moq_estimate, unit_price_range,
    verification_badge, location_city, location_state,
    relevance_score, outreach_status, created_at
);

outreach_drafts (
    id, supplier_id, product_id, draft_subject, draft_email,
    approval_status, approved_by, approved_at, sent_at, created_at
);

supplier_conversations (
    id, thread_id, supplier_id, product_id, turn_number,
    direction, content, ai_classification,
    escalation_triggers_json, draft_reply, reply_status, created_at
);

problem_opportunities (
    id, source_type, source_url, problem_statement,
    product_category, severity_score, frequency_count,
    nim_synthesis, v2_product_spec, status, created_at
);
```

---

## COMPLETE WIRING MAP

```
internet_crawler.py
    writes → trend_signals, problem_opportunities, discovered_sources
    ↓
niche_expander.py reads trend_signals
    writes → dynamic_niches (new categories)
    ↓
discovery_engine.py reads dynamic_niches
    calls → web_agent.search_all_marketplaces()
    calls → ValidationPipeline → CanonicalProduct
    writes → master_products, scraped_listings
    ↓
gate_engine.py reads master_products
    Gate 1 → keepa_api_client.py (BSR check)
    Gate 2 → review_miner.py + problem_miner.py (Ollama)
    Gate 3 → economics_engine.py (deterministic)
    Gate 4 → nim_client.py (NIM 550B arbiter)
    rules → rule_engine.py (applied at every gate)
    writes → product_gate_progress, gate_logs, launchpad_items
    ↓ (PROCEED only)
supplier_agent.py
    calls → IndiaMART JSON API (curl_cffi)
    calls → web_agent.find_suppliers() (Alibaba/ExportersIndia fallback)
    calls → gst_verifier.py (verify each supplier)
    writes → supplier_profiles
    ↓
outreach_engine.py reads supplier_profiles
    calls → nim_client.draft_outreach() (NIM 550B)
    writes → outreach_drafts (status=PENDING)

    ---- HUMAN APPROVAL GATE ----
    web/app.py Suppliers tab shows drafts
    Human clicks APPROVE → SMTP sends email
    writes → outreach_drafts (status=SENT)
    ↓
supplier_conversation loop:
    Human pastes supplier reply into dashboard
    outreach_engine.parse_supplier_reply()
    calls → nim_client.parse_supplier_reply()
    If escalation → dashboard alert, STOP
    Else → draft shown as PENDING for human approval
    writes → supplier_conversations

learning_engine.py (weekly Sunday)
    reads → gate_logs, master_products, supplier_conversations
    writes → learned_rules, updated niche priority_scores, seed weights

web/app.py (reads everything, writes human decisions)
    Tab 1: Research — trigger scans, view discovery results
    Tab 2: Economics — P&L waterfall charts per product
    Tab 3: Dossiers — full product dossiers, Gate outcomes
    Tab 4: Settings — config, learned rules, DB health
    Tab 5: Suppliers — supplier cards, outreach approval, conversations (NEW)
```

---

## BUILD SEQUENCE — 4 WEEKS

```
WEEK 1 — Critical supplier pipeline:
  Day 1: core/nim_client.py + core/supplier_models.py
  Day 2: tools/supplier_agent.py + tools/gst_verifier.py
  Day 3: core/outreach_engine.py + outreach prompts
  Day 4: database.py — add 6 missing tables
  Day 5: web/app.py — add Suppliers tab (5th tab)
  Day 6-7: End-to-end test: product PROCEED → supplier found → draft email shown

WEEK 2 — Intelligence expansion:
  Day 1-2: tools/problem_miner.py
  Day 3-4: tools/internet_crawler.py
  Day 5: tools/niche_expander.py
  Day 6-7: Wire trend_scout → dynamic_niches auto-expansion

WEEK 3 — Full autonomy layer:
  Day 1-2: core/agent_orchestrator.py
  Day 3: core/scheduler.py (APScheduler)
  Day 4-5: core/learning_engine.py
  Day 6-7: 24-hour autonomous run test (no human input)

WEEK 4 — Production hardening:
  Day 1-2: Full test suite, fix gaps
  Day 3: First real autonomous scan (5 live niches)
  Day 4: First supplier outreach (human approves, sends)
  Day 5-7: 35-minute Monday workflow validated in production
```

---

## 35-MINUTE MONDAY WORKFLOW (Target State)

```
09:00  You open dashboard (system has been running overnight)
09:05  Dashboard shows: 3 PROCEED products discovered, 12 suppliers found
09:10  You review product dossiers (economics, defects, v2.0 spec)
09:20  You review 5 supplier outreach drafts (each 150-word email)
09:30  You approve 2 emails → they send automatically via SMTP
09:35  Done. AI handles follow-up for 2-3 turns, escalates when needed.

Thursday:
  "Supplier A quoted 165 INR, Supplier B 142 INR for 500 units.
   Recommend sample from Supplier B (GST verified, 4-day lead time)."
  You decide: "Order samples from both" → manually WhatsApp for payment.
```

---

## SUCCESS CRITERIA

| Milestone | Metric | Target |
|-----------|--------|--------|
| Supplier pipeline | Human can approve+send email from dashboard | Week 1 |
| Problem mining | System finds unmet needs from Reddit/Amazon | Week 2 |
| Internet crawler | Runs 24h with zero human input | Week 3 |
| Self-improvement | Rule engine adds 1+ learned rule per week | Week 4 |
| Full autonomy | 35-min Monday workflow works end-to-end | Week 4 |
| First sample order | Product found by system, sampled via AI-assisted outreach | Week 8 |

---

## HARD LIMITS (System Enforced — Non-Negotiable)

The system WILL NEVER autonomously:
- Mention price commitments to suppliers
- Promise delivery timelines
- Agree to advance payments
- Share bank account details
- Commit to order quantities
- Make any binding agreement

Any supplier message containing these topics triggers immediate escalation.
The AI stops, raises a red alert in the dashboard, and waits for human.
