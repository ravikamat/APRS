# SUPREME PRODUCT FINDER — Master Autonomous Plan

**Version 1.0 | 2026-09-04 | APRS V8 Rebuild Strategy**

---

## 1. THE NORTH STAR

**Mission:** A system that runs 24/7 with zero human input, dynamically researches the internet, and outputs a ranked shortlist of products that pass all 6 constraints — demand, trend, margin, differentiation, supply, risk — refreshed daily, with every claim traceable to evidence.

**The one output that matters:** a single sorted list. If the system cannot answer "what are today's top 10 products to sell?" in one query, it is a scraper, not a finder.

**Operating loop:**

```
SCAN -> SCORE -> DEEP-DIVE -> VALIDATE -> LEARN -> repeat, forever
```

---

## 2. WHAT YOU HAVE TODAY (honest inventory)

| Asset | Status | Verdict |
|---|---|---|
| 9-agent orchestrator + daemon | Working — runs discovery 24/7 | KEEP — only proven-working part (40k listings scraped) |
| 5-Gate pipeline concept | Correct design | KEEP — gates map to the 6 constraints |
| 15-factor economics engine | Deterministic math built | KEEP — ran only once; needs to run 500x more |
| Defect miner (Ollama) | Built, never produced data | FIX — review_snapshots = 0 rows |
| NIM 550B arbiter + LLM router | Built, unverified | FIX — llm_tier_log = 0 rows means zero audit trail |
| Supplier agent + GST verifier | Built, zero output | FIX — supplier_profiles = 0 rows |
| Streamlit 10-tab cockpit | Built | KEEP — good human-in-loop surface |
| SQLite 32-table SSOT | Corrupted | REPAIR — orphans, duplicates, 3 conflicting DB paths |
| Learning engine | 0 rules | REBUILD — nothing has launched so nothing to learn from |
| Architecture docs (3 of them) | Contradict each other | DELETE 2, regenerate 1 from live schema |

**Bottom line:** ~70% of components exist. What is missing is a *flowing funnel*, *clean data*, and *verification that the AI parts actually work*.

---

## 3. WHAT TO ADD (the missing components)

### A. Strategic Research Brain (the biggest gap)

Current system is *reactive* scraping (keywords -> listings). Missing: *strategic* research — deciding **where to look**, not just how.

| New Component | File | Function |
|---|---|---|
| Strategy Planner Agent | `agents/strategy_planner.py` | Weekly: analyzes learned_rules + negative_findings + launchpad outcomes -> decides which categories/regions to research next. Writes a research_directive row. |
| Demand Sensing Layer | `tools/demand_sense.py` | Beyond trends: Keepa BSR velocity, review-count growth rate (reviews/month = true demand proxy), review-gap detection (high sales + few reviews = weak competition). |
| Competition X-Ray | `tools/competition_xray.py` | Per candidate: listing count, brand concentration (Amazon Basics present? flee), price-band crowding, first-page ad density. |
| Research Directive Table | `research_directives` (new table) | Strategy Planner output: {category, region, why, priority, expires_at}. Every downstream agent reads this instead of wandering. |
| Winner Score | computed column on `master_products` | Single composite 0-100 ranking the cockpit sorts by. |

### B. Self-Healing & Verification (flying blind today)

| New Component | File | Function |
|---|---|---|
| Health Monitor Agent | `agents/health_monitor.py` | Every cycle: verifies each agent actually wrote expected output; detects silent failures (the exact disease that killed Gates 2-5). |
| Agent Output Contract | `core/contracts.py` | Every agent MUST write: output rows + swarm_audit_log entry + expected-row-count check. Missing output -> auto retry -> escalate to pending_human_decisions. |
| Pipeline State Machine | `core/pipeline_fsm.py` | Explicit per-product state: DISCOVERED -> GATED -> DEEP_DIVED -> VALIDATED -> SHORTLISTED -> SOURCING. No product silently sits in limbo. |

### C. Dynamic Learning That Actually Works

| New Component | File | Function |
|---|---|---|
| Outcome Tracker | `launchpad_outcomes` (new table) | When a launchpad item reaches LIVE: record actual sales/margin/returns monthly. This is the fuel the Learning Engine never had. |
| Weight Tuner | `core/weight_tuner.py` | Quarterly: backtest winner-score weights against actual outcomes; suggest (not auto-apply) weight changes. |

### D. Data Infrastructure Repair

| Fix | Details |
|---|---|
| One DB, one path | Kill APRS_DB_PATH ambiguity. `data/aprs.db`, enforced at startup with a DB_PATH singleton. |
| Migration tooling | Alembic or versioned schema_migrations table — no more hand-edited schemas drifting from docs. |
| Dedupe hash | scraped_listings.content_hash (title+price+marketplace, normalized) + unique index -> stop re-scraping 40k listings. |
| Retention jobs | TTL deleter daemon: ai_supervisor_logs 14d, scraped_listings 30d post-validation, swarm_audit_log 90d. |

---

## 4. THE WIRING — how everything connects

```
+--------------------------------------------------------------------------+
|                    STRATEGIC LAYER (runs weekly)                         |
|                                                                          |
|  Strategy Planner --reads--> learned_rules, negative_findings,           |
|         |                       launchpad_outcomes, trend_signals        |
|         v                                                                |
|  research_directives  (WHERE to hunt next: category/region/priority)     |
+---------------+----------------------------------------------------------+
                | every agent cycle reads directives first
                v
+--------------------------------------------------------------------------+
|                    EXECUTION LAYER (daemon, every cycle)                 |
|                                                                          |
|  [1] InternetCrawler --> trend_signals, discovered_sources               |
|  [2] TrendScout --> trend_signals (velocity validated)                   |
|  [3] NicheExpander --> dynamic_niches  (guided by directives)            |
|  [4] DiscoveryEngine --> scraped_listings  (dedupe hash enforced)        |
|  [5] ValidationPipeline --> master_products  (funnel: 10k -> 500)        |
|                                                                          |
|  [6] Pipeline FSM -- per product:                                        |
|     Gate1 (deterministic BSR/CV) --> Gate2 (Ollama defect mine)          |
|     --> Gate3 (15-factor economics x3 scenarios)                         |
|     --> Gate4 (scoring) --> Gate5 (NIM arbiter)                          |
|                                                                          |
|  [7] HealthMonitor -- checks [1]-[6] wrote output; retries; escalates    |
|                                                                          |
|  [8] WinnerScore computer -- nightly: ranks ALL validated products       |
|           |                                                              |
|           v  Top N where Gate5 = CONFIRM_PROCEED                         |
|  [9] SupplierAgent --> supplier_profiles --> GSTVerifier                 |
|  [10] OutreachEngine --> outreach_drafts --> HUMAN APPROVAL --> launchpad|
+---------------+----------------------------------------------------------+
                | weekly
                v
+--------------------------------------------------------------------------+
|                    LEARNING LAYER                                        |
|  LearningEngine --> learned_rules (from gate failures)                   |
|  WeightTuner --> weight change proposals (from launchpad_outcomes)       |
|  StrategyPlanner consumes --> loop closes back to directives             |
+--------------------------------------------------------------------------+
```

**Wiring rules (non-negotiable):**

1. **Every agent reads research_directives first.** No directive = no cycle. This makes research *strategic* instead of random.
2. **Every agent writes through core/contracts.py.** Output rows + audit row + health-check entry, in one transaction. This prevents another silent death like Gate 2.
3. **Every gate transition goes through pipeline_fsm.py.** UI buttons and agents both call the FSM — no direct table writes.
4. **The cockpit reads one view:** `v_winner_leaderboard` (product_id, winner_score, gate badges, margin, top defect, supplier count) — Tab 1 becomes a leaderboard, not a table browser.
5. **Human touchpoints stay exactly 3:** shortlist review, outreach approval, sample QC.

---

## 5. WINNER SCORE FORMULA (the ranking heart)

```
WinnerScore = 0.30 x MarginSafety      (net margin after stress, 0-100)
            + 0.20 x DemandVelocity    (review growth rate + BSR trend)
            + 0.20 x Differentiation   (fixable defects found x severity)
            + 0.15 x CompetitionGap    (inverse: brand concentration, review gap)
            + 0.10 x SignalFreshness   (trend velocity, recency)
            + 0.05 x SupplyAccess      (verified suppliers found)
```

Deterministic, tunable, backtestable. Gates filter (PASS/FAIL); WinnerScore *ranks* the survivors. Two different jobs.

---

## 6. PHASED BUILD PLAN (12 weeks)

| Phase | Weeks | Deliverable | Exit criteria |
|---|---|---|---|
| 0: Stabilize | 1-2 | DB repair + one canonical schema doc + health monitor skeleton | Orphan count = 0; docs match sqlite_master; funnel SQL runs |
| 1: Unblock the funnel | 3-4 | Debug Gate 2 chain (review scraper -> Ollama -> defect_clusters); wire contracts + audit logging | One product goes end-to-end Gate 1->5 with gate_logs populated |
| 2: Strategy layer | 5-7 | research_directives + Strategy Planner + DemandSense + Competition X-Ray | Directives drive a cycle; funnel yields 50+ deep-dives |
| 3: Supply chain | 8-9 | Supplier agent debug + GST verifier + outreach + launchpad live | 3+ products reach launchpad with verified suppliers |
| 4: Learning loop | 10-11 | Outcome tracker + weight tuner + strategy feedback | learned_rules has >=5 real rules from actual failures |
| 5: Tune & harden | 12 | Winner score calibration, TTL jobs, backups, load test | Top-10 list stable for 3 consecutive days; 100% audit coverage |

**Rule for the whole build:** after Phase 1, every phase must produce *flowing products*, not just code. A phase is not done when the code merges — it is done when the leaderboard shows new ranked entries.

---

## 7. SUCCESS METRICS

| Metric | Today | 30-day target |
|---|---|---|
| Products through all 5 gates | ~1 | 25+ |
| Deep-dive products/week | 0 | 15+ |
| gate_logs rows per gate run | 0 | 1:1 (100% audit) |
| Orphaned rows | ~9k+ | 0 |
| Time from scraped to shortlisted | never happens | < 48h |
| Top-10 leaderboard churn | n/a | <=30% daily turnover (stability = confidence) |
| Human minutes/day required | unknown | <=30 |

---

## 8. RISKS & GUARDRAILS

| Risk | Guardrail |
|---|---|
| AI agents hallucinate products that do not exist | Deterministic gates own all numbers; LLMs only interpret text (defects, arbiter reasoning) |
| Self-modifying rules go rogue | learned_rules need approved_by human before enabled=1 |
| Scraping ToS / WhatsApp bans | Rotation, rate limits, human sends all outreach |
| Ollama/VRAM contention crashes cycles | Health monitor retries with backoff; Tier 3 fallback verified weekly |
| SQLite chokes at scale | Phase 5 load test; migrate to Postgres only if >50 writes/sec sustained |

---

## 9. THE ONE-PARAGRAPH VERSION

Repair the data, force every agent to prove it worked, un-stick the funnel at Gate 2, add a strategy brain so research is directed instead of random, rank everything with one winner score, and close the learning loop with real launch outcomes. Same codebase, same agents — but wired so nothing can silently die again.

---

## Appendix A: Diagnostic SQL (run before Phase 0 starts)

```sql
-- Orphan detector: gate progress rows pointing at missing products
SELECT COUNT(*) FROM product_gate_progress pgp
LEFT JOIN master_products mp ON pgp.product_id = mp.product_id
WHERE mp.product_id IS NULL;

-- Duplicate listings per platform
SELECT product_id, platform, COUNT(*) c
FROM multi_platform_listings
GROUP BY product_id, platform HAVING c > 1;

-- Orphans in multi_platform_listings
SELECT COUNT(*) FROM multi_platform_listings mpl
LEFT JOIN master_products mp ON mpl.product_id = mp.product_id
WHERE mp.product_id IS NULL;

-- Funnel health: what fraction of scraped listings were validated?
SELECT
  (SELECT COUNT(*) FROM scraped_listings) AS scraped,
  (SELECT COUNT(*) FROM scraper_validations) AS validated,
  (SELECT COUNT(*) FROM master_products) AS canonical,
  (SELECT COUNT(*) FROM defect_clusters) AS defects,
  (SELECT COUNT(*) FROM economics_assessments) AS econ,
  (SELECT COUNT(*) FROM supplier_profiles) AS suppliers;
```

## Appendix B: Phase 0 Checklist

- [ ] Run Appendix A SQL, record baseline numbers
- [ ] Pick one canonical DB path; delete/env-lock the others
- [ ] Dedupe product_gate_progress and multi_platform_listings (keep latest per key)
- [ ] Fix pending_human_decisions FK (point to product_id, not agent_name)
- [ ] Add CHECK constraints: gate status enums, scenario enums, json_valid() on JSON columns
- [ ] Standardize all timestamps to UTC
- [ ] Regenerate ONE schema doc from sqlite_master + PRAGMA; delete the other two docs
- [ ] Backup DB before any mutation
