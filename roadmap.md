# APRS V6 Pro — Production Implementation Roadmap

> **Version:** 1.0 · **Last Updated:** 2026-09-01  
> **Target:** India-first e-commerce (Amazon.in, Flipkart, Meesho)  
> **Philosophy:** Deterministic math over LLM hallucination. Local inference over API bankruptcy.  
> **Goal:** Identify 1 viable private-label product per week with ≥20% net margin.

---

## Executive Summary

APRS V6 Pro is a **complete architectural pivot** from the current V5 codebase. The existing system
uses a 550B-parameter NIM swarm to validate, score, and arbitrate product decisions. V6 Pro replaces
this with a **deterministic pipeline** where:

- **Zero LLM calls** in the validation, scoring, or economics hot path
- **Local Ollama** used exactly once per product — for 3-star review defect extraction
- **Pydantic v2** replaces the AI Supervisor for data integrity
- **Playwright + stealth** replaces curl_cffi for anti-detection reliability
- **4 sequential gates** replace the scattered 6-gate system
- **4-tab Streamlit UI** replaces the 9-tab dashboard

Monthly cost drops from $15,000-$45,000 to ~$18.

---

## Architecture (V6 Pro)

```
INPUT: Niche Keyword (manual or batch cron)
        |
        v
+-----------------------------------------------+
|  STAGE 1: DISCOVERY                           |
|  tools/discovery_engine.py                    |
|  +-- AmazonScraper (Playwright + stealth)     |
|  +-- FlipkartScraper (Playwright + stealth)   |
|  +-- Output: RawProduct[] -> SQLite           |
+-------------------+---------------------------+
                    |
                    v
+-----------------------------------------------+
|  STAGE 2: VALIDATION                          |
|  core/validation.py                           |
|  +-- Pydantic RawProduct (price>0, rating 1-5)|
|  +-- ProductMatcher (fuzzy dedup)             |
|  +-- Output: CanonicalProduct[] -> SQLite     |
+-------------------+---------------------------+
                    |
                    v
+-----------------------------------------------+
|  STAGE 3: GATE EXECUTION                      |
|  core/gate_engine.py                          |
|  +-- Gate 1: Keepa BSR (<50k, CV <0.30)       |
|  +-- Gate 2: Defect Mining (Ollama, local)     |
|  +-- Gate 3: 15-Factor Economics (>=20% margin)|
|  +-- Gate 4: Deterministic Score (>=75/100)    |
+-------------------+---------------------------+
                    |
                    v
+-----------------------------------------------+
|  STAGE 4: OUTPUT                              |
|  web/app.py                                   |
|  +-- Ranked dossier with full P&L             |
|  +-- v2.0 BOM specification                   |
|  +-- Sourcing cluster recommendation          |
|  +-- Human go/no-go decision                  |
+-----------------------------------------------+
```

---

## Data Flow Rules

1. **No LLM in the hot path.** Only deterministic code validates, scores, and filters.
2. **LLM used exactly once per product:** Defect extraction from reviews (local Ollama, free).
3. **Batch execution only.** No daemons. Cron or manual triggers.
4. **Human in the loop for final investment.** Gate 4 output is a recommendation, not a command.

---

## Gap Analysis: Current V5 vs. V6 Pro Target

| Component | Current (V5) | V6 Pro Target | Gap |
|---|---|---|---|
| Database | Raw sqlite3, 23 tables | Same (keep working layer) | Minor |
| Config | Module-level dicts | pydantic_settings.BaseSettings | Refactor |
| Fee Schedules | Inline in economics_engine.py | Separate config/fees.py | Extract |
| Validation | LLM-based (ai_supervisor.py) | Pydantic v2 schemas | **New module** |
| Scoring | LLM swarm (nim_swarm) | Deterministic 0-100 rubric | **New module** |
| Gate Engine | Scattered across files | Unified GateEngine class | **New module** |
| Rule Engine | Not implemented | learned_rules + safe eval | **New module** |
| Scraping | curl_cffi + TLS impersonation | Playwright + stealth | Rewrite |
| Defect Mining | NIM-heavy via multiple modules | Single review_miner.py, Ollama only | Simplify |
| Product Matcher | Complete, working | Keep as-is | Done |
| Economics Engine | 15-factor, deterministic | Extract fees, add passes_gate() | Minor |
| Keepa Client | Working, production-ready | Keep as-is | Done |
| NIM Swarm | 5-agent, 550B model | **Delete** | Remove |
| AI Supervisor | LLM validation, 1,896 lines | **Delete** (Pydantic replaces) | Remove |
| Background Daemon | 24/7 continuous | **Delete** (batch only) | Remove |
| Streamlit UI | 9 tabs, 1,236 lines | 4 tabs, simplified | Simplify |

---

## 90-Day Build Roadmap

### Phase 1: Foundation (Weeks 1-2)
- [ ] config/settings.py -> Pydantic Settings
- [ ] config/fees.py -> hardcoded marketplace fees
- [ ] core/validation.py -> Pydantic RawProduct + CanonicalProduct
- [ ] .env.example -> environment variable template
- [ ] Unit tests for validation schemas

### Phase 2: Scraping Engine (Weeks 3-4)
- [ ] tools/amazon_scraper.py -> Playwright + stealth
- [ ] tools/flipkart_scraper.py -> Playwright + stealth
- [ ] tools/discovery_engine.py -> orchestrator rewrite
- [ ] Test on 5 real niches

### Phase 3: Core Engine (Weeks 5-6)
- [ ] Refactor core/economics_engine.py -> extract fees, add passes_gate()
- [ ] core/scoring_engine.py -> deterministic 0-100
- [ ] Unit tests for economics and scoring

### Phase 4: Intelligence (Weeks 7-8)
- [ ] Setup Ollama (qwen2.5:14b)
- [ ] tools/review_miner.py -> Ollama defect extraction
- [ ] prompts/defect_extraction.txt -> external prompt
- [ ] Test on 20 real products

### Phase 5: Orchestration (Weeks 9-10)
- [ ] core/gate_engine.py -> unified 4-gate state machine
- [ ] core/rule_engine.py -> rule accumulator + 10 seed rules
- [ ] main.py -> simplified CLI (--scan, --web)
- [ ] End-to-end pipeline test on 3 niches

### Phase 6: Dashboard (Weeks 11-12)
- [ ] web/app.py -> 4-tab Streamlit (Research, Economics, Dossiers, Settings)
- [ ] Plotly waterfall economics chart
- [ ] Dossier export (Word, Excel)

### Phase 7: Hardening (Week 13+)
- [ ] Database backup automation
- [ ] Structured JSON logging
- [ ] Dockerfile
- [ ] Remove deprecated V5 modules
- [ ] First private-label purchase order

---

## Monthly Cost Analysis

| Component | Cost (INR) | Cost (USD) |
|---|---|---|
| Keepa API | Rs.1,500 | $18 |
| Ollama (local) | Rs.0 | $0 |
| SQLite | Rs.0 | $0 |
| Streamlit (local) | Rs.0 | $0 |
| **TOTAL** | **Rs.1,500** | **$18** |

---

## Scoring Rubric (Transparent, Debuggable)

| Factor | Weight | Calculation |
|---|---|---|
| Market Signal (BSR) | 25 pts | max(0, 25 - (BSR / 2000)) |
| Review Quality | 20 pts | Rating >=4.2 & Reviews >=100: 20; >=3.8: 12 |
| Margin Safety | 40 pts | >=30%: 40; >=25%: 32; >=20%: 24; <20%: 0 |
| Defect Fixability | 10 pts | Has 3-star defects: 10 |
| Competition Density | 5 pts | <=5 listings on page 1: 5 |

**Threshold:** >=75 PROCEED | >=60 MARGINAL | <60 REJECT

---

## Success Criteria

1. **Week 2:** Pydantic validates 100 sample products with zero false positives
2. **Week 4:** Scraper captures 50+ listings per niche across 3 marketplaces
3. **Week 6:** Economics engine matches manual P&L within +/-2%
4. **Week 8:** Ollama extracts actionable defects from 80%+ products
5. **Week 10:** Full pipeline produces ranked dossiers for 3 test niches
6. **Week 12:** Dashboard usable for daily workflow
7. **Week 13:** First private-label PO placed from system output
