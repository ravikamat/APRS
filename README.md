# APRS V5 — Autonomous Product Research System

> **6-gate AI pipeline** for discovering, validating, and sourcing winning e-commerce products across India, USA, UK, and GCC markets.

---

## Architecture

```
D:/ecomm-strategy/
├── main.py                        # Entrypoints: --web | --overnight | --scan
├── .env                           # API keys (NIM_API_KEY_1/2/3, KEEPA_API_KEY) — never commit
├── requirements.txt               # All Python dependencies
│
├── config/
│   └── settings.py                # Regional profiles, NIM model IDs, paths (dotenv-loaded)
│
├── core/
│   ├── database.py                # SQLite SSOT (WAL mode, gate state machine, migrations)
│   ├── orchestrator.py            # 12-factor economics engine + 6-gate pipeline runner
│   ├── background_daemon.py       # 24/7 threaded scraping daemon (23 niches)
│   ├── team_meeting.py            # AI War Room: 6 specialist personas, NIM-powered
│   ├── excel_manager.py           # Atomic XLSX 4-sheet export
│   ├── meeting_doc_manager.py     # Word (.docx) meeting minutes generator
│   └── utils.py                   # normalize_region, format_currency, get_product_live_url
│
├── models/
│   └── nim_cluster.py             # 3-key NIM failover cluster + LRU cache + Pydantic arbiter
│
├── tools/
│   ├── amazon_live_scraper.py     # curl_cffi anti-bot Amazon scraper (USA/UK/India/GCC)
│   ├── keepa_api_client.py        # Keepa BSR + price history client (India domain=10)
│   ├── review_reddit_defect_harvester.py  # Reddit public JSON + Amazon 3-star → NIM v2.0 spec
│   ├── google_trends_engine.py    # Google Suggest + Trends interest index
│   ├── bulk_discovery_engine.py   # Parallel multi-niche discovery runner
│   ├── free_spy_suite.py          # Ad intelligence tools
│   └── run_live_realtime_scan.py  # One-shot live scan script
│
├── web/
│   └── app.py                     # Streamlit dashboard (6 tabs + Gate Management + War Room)
│
├── data/
│   └── research_engine.db         # Production SQLite (WAL, 50 India products seeded)
│
└── tests/
    ├── test_phase1_database.py    # DB schema, gates, WAL — temp DB isolated
    ├── test_phase2_orchestrator.py # Gate runner with mocked scraper — temp DB isolated
    ├── test_phase3_scrapers.py    # Amazon + Keepa unit tests — temp DB isolated
    ├── test_phase4_nim.py         # NIM cluster cache + fallback — no live API calls
    ├── test_aprs_platform.py      # Integration: economics, DB WAL, NIM mock — temp DB
    └── test_phase6_e2e.py         # End-to-end mocked pipeline flow
```

---

## The 6-Gate Pipeline

| Gate | Name | Type | Who Enters |
|------|------|------|-----------|
| **1** | Signal Discovery | Automated | Keepa BSR + Amazon scraper |
| **2** | Defect Mining | Manual | Human fills 3-star flaws + v2.0 spec |
| **3** | Economics Validation | Automated | 12-factor landed COGS engine |
| **4** | Sourcing Quote | Manual | Human enters negotiated FOB from factory |
| **5** | War Room Consensus | Automated | NIM `multi_agent_peer_review()` — 3-stage AI debate |
| **6** | Sign-Off & PO | Human | Full Purchase Order / RFQ generation |

---

## Quickstart

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure `.env`
```env
NIM_API_KEY_1=nvapi-...
NIM_API_KEY_2=nvapi-...
NIM_API_KEY_3=nvapi-...
KEEPA_API_KEY=your_keepa_key
```

### 3. Launch
```bash
# Web dashboard + 24/7 background daemon
python main.py --web

# Standalone overnight daemon (no UI)
python main.py --overnight

# One-off CLI scan
python main.py --region India --category "Kitchen Storage" --max 3
```

---

## Regional Economics Models

| Region | Customs | Fulfillment | TACoS | Min Net Margin |
|--------|---------|-------------|-------|----------------|
| **India (domestic mfg)** | 0% | ₹52–95 (Easy Ship tiers) | 14% | 15% |
| **USA** | 7.5% | \$5.50 FBA | 28% | 15% |
| **UK/Europe** | 6.5% | €5.20 | 25% | 18% |
| **GCC (amazon.ae)** | 5% | AED 12 | 22% | 15% |

---

## Running Tests

```bash
# All 26 tests (all isolated — production DB never touched)
python -m pytest tests/ -v

# Specific suites
python -m pytest tests/test_phase1_database.py -v
python -m pytest tests/test_phase4_nim.py -v   # No live NIM calls
```

---

## Key Design Decisions

- **SQLite WAL mode** — concurrent read/write for background daemon + Streamlit UI
- **`APRS_DB_PATH` env var** — all tests use temp DBs; production DB is never touched
- **3-key NIM failover** — `Key #1 → Key #2 → Key #3 → grounded fallback` with LRU cache
- **`normalize_region()`** in `core/utils.py` — exact-match alias lookup prevents `"in" in region` misclassifying Finland/Indonesia as India
- **Supplier data** — Gate 1 creates honest placeholder records requiring Gate 4 manual factory negotiation (no fabricated contacts)
- **Background daemon** — `threading.Thread(daemon=True)` cycling 23 niches; starts automatically on `--web`

---

## Security Notes

- **Never commit** `.env` — API keys must stay in environment variables only
- `shared_meeting_bridge.json` has been **deleted** (contained plaintext NIM key)
- Keys are loaded via `python-dotenv` at module load time in `config/settings.py`

---

## NIM Models Used

| Task | Model |
|------|-------|
| Fast Triage (Gate 1 scoring) | `meta/llama-3.1-70b-instruct` |
| Adversarial Critic (Gate 5) | `meta/llama-3.3-70b-instruct` |
| Deep Reasoning / Arbiter (Gate 5) | `meta/llama-3.3-70b-instruct` |
