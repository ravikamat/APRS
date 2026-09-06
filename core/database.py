import sqlite3
import json
import time
import random
import threading
from datetime import datetime, timezone
import os
import sys
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

# Ensure project root is importable when running database.py standalone
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# Global lock for database write operations to prevent locking issues
# Use RLock (reentrant lock) to allow the same thread to acquire the lock multiple times
_db_write_lock = threading.RLock()


def _execute_with_lock(func, *args, **kwargs):
    """Execute a database function with a global write lock."""
    with _db_write_lock:
        return func(*args, **kwargs)


def get_db_path() -> Path:
    """Get database path, respecting environment variable for testing."""
    return Path(os.environ.get("APRS_DB_PATH", _PROJECT_ROOT / "data" / "research_engine.db"))


DB_PATH = get_db_path()
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------
# PYDANTIC DATA SCHEMAS (STRICT VALIDATION LAYER)
# -------------------------------------------------------------
class SupplierModel(BaseModel):
    factory_name: str = Field(..., min_length=2)
    supplier_type: str = "Direct Manufacturer"
    industrial_address: str = "Industrial Zone"
    contact_person: str = "Export Manager"
    contact_details: str = "WhatsApp / Email"
    platform_profile_url: str = "https://alibaba.com"
    fob_unit_price: str = "$0.00"
    moq_units: int = Field(default=100, ge=1)
    sample_cost_leadtime: str = "$30 / 3 days"
    certifications: str = "ISO9001, CE"

class ProductEvaluationModel(BaseModel):
    product_id: str
    name: str = Field(..., min_length=3)
    category: str
    region: str = "USA"
    planned_msrp: float = Field(..., gt=0)
    landed_cogs: float = Field(..., ge=0)
    gross_margin_pct: float = Field(default=0.0)
    estimated_cac: float = Field(default=0.0)
    net_profit_pct: float = Field(default=0.0)
    worst_case_stress_margin_pct: float = Field(default=0.0)
    status: str = Field(default="PENDING")
    overall_score: float = Field(default=0.0, ge=0, le=100)
    consensus_status: str = "CONSENSUS_PASS"
    action_plan: str = ""
    sourcing_cluster: str = ""
    marketplace_url: str = ""
    competitor_3star_flaws: str = ""
    upgrade_v2_engineering: str = ""
    bsr_rank: int = Field(default=100)
    estimated_daily_units: int = Field(default=30)
    ad_active_days: int = Field(default=30)
    suppliers: List[SupplierModel] = []
    human_override_status: Optional[str] = None
    # APRS V6 Swarm Fields
    is_shortlisted: int = 0
    is_deleted: int = 0
    deletion_reason: Optional[str] = None
    trend_source: Optional[str] = None
    trend_confidence_score: float = 0.0
    platform_availability: Optional[str] = None
    # AI Supervision Fields for Archive/Rejection tracking
    ai_rejection_reason: Optional[str] = None
    ai_reasoning: Optional[str] = None
    ai_rejection_category: Optional[str] = None
    ai_confidence: float = 0.0

# -------------------------------------------------------------
# DATABASE CONNECTION (WAL MODE & BUSY TIMEOUT)
# -------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    """Returns connection with WAL mode, busy timeout, and foreign keys ON."""
    conn = sqlite3.connect(str(get_db_path()), timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=60000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def execute_with_retry(conn: sqlite3.Connection, query: str, params: tuple = (), max_retries: int = 5, base_delay: float = 0.1) -> sqlite3.Cursor:
    """Execute a query with retry on database locked errors."""
    import time
    import random
    
    for attempt in range(max_retries + 1):
        try:
            return conn.execute(query, params)
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) or "database is locked" in str(e).lower():
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
                    time.sleep(delay)
                    continue
            raise
    raise sqlite3.OperationalError("Max retries exceeded for database locked error")

def _column_exists(cur, table: str, col: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    return any(row[1] == col for row in cur.fetchall())

def init_db():
    """Initializes tables, meeting audit log, and performs schema migrations."""
    conn = get_connection()
    cur = conn.cursor()
    
    # 1. Master Products Table — ALL COLUMNS EXPLICIT
    cur.execute('''
        CREATE TABLE IF NOT EXISTS master_products (
            product_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            region TEXT NOT NULL,
            planned_msrp REAL NOT NULL,
            landed_cogs REAL NOT NULL DEFAULT 0.0,
            gross_margin_pct REAL NOT NULL DEFAULT 0.0,
            estimated_cac REAL NOT NULL DEFAULT 0.0,
            net_profit_pct REAL NOT NULL DEFAULT 0.0,
            worst_case_stress_margin_pct REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','PASS','FAIL','BLOCKED','SOURCING_NEGOTIATION','SAMPLE_ORDERED','SAMPLE_APPROVED','QC_IN_PROGRESS','PO_ISSUED','SHIPPED','LIVE','AI_REJECTED')),
            overall_score REAL NOT NULL DEFAULT 0.0,
            consensus_status TEXT NOT NULL DEFAULT 'CONSENSUS_PASS' CHECK(consensus_status IN ('CONSENSUS_PASS','CONSENSUS_FAIL','OVERRIDDEN')),
            action_plan TEXT,
            sourcing_cluster TEXT,
            marketplace_url TEXT,
            competitor_3star_flaws TEXT,
            upgrade_v2_engineering TEXT,
            bsr_rank INTEGER DEFAULT 100,
            estimated_daily_units INTEGER DEFAULT 30,
            ad_active_days INTEGER DEFAULT 30,
            human_override_status TEXT,
            first_discovered_date TEXT,
            last_evaluated_date TEXT,
            keepa_price_stability REAL DEFAULT 85.0,
            helium_monthly_revenue REAL,
            factory_cogs REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            -- AI Supervision columns for Archive/Rejection tracking
            ai_rejection_reason TEXT,
            ai_reasoning TEXT,
            ai_rejection_category TEXT,
            ai_confidence REAL DEFAULT 0.0,
            is_deleted INTEGER DEFAULT 0 CHECK(is_deleted IN (0,1)),
            is_shortlisted INTEGER DEFAULT 0 CHECK(is_shortlisted IN (0,1)),
            deletion_reason TEXT,
            deleted_at TIMESTAMP,
            trend_source TEXT,
            trend_confidence_score REAL DEFAULT 0.0,
            platform_availability TEXT,
            custom_tags TEXT
        )
    ''')
    
    # 2. Schema Migrations: Ensure all expected columns exist on legacy tables
    required_cols = [
        ("bsr_rank", "INTEGER DEFAULT 100"),
        ("estimated_daily_units", "INTEGER DEFAULT 30"),
        ("ad_active_days", "INTEGER DEFAULT 30"),
        ("human_override_status", "TEXT"),
        ("created_at", "TIMESTAMP"),
        ("updated_at", "TIMESTAMP"),
        ("first_discovered_date", "TEXT"),
        ("last_evaluated_date", "TEXT"),
        ("keepa_price_stability", "REAL DEFAULT 85.0"),
        ("helium_monthly_revenue", "REAL"),
        ("factory_cogs", "REAL"),
        ("landed_cogs", "REAL NOT NULL DEFAULT 0.0"),
        ("estimated_cac", "REAL NOT NULL DEFAULT 0.0"),
        ("gross_margin_pct", "REAL NOT NULL DEFAULT 0.0"),
        ("net_profit_pct", "REAL NOT NULL DEFAULT 0.0"),
        ("worst_case_stress_margin_pct", "REAL NOT NULL DEFAULT 0.0"),
        ("overall_score", "REAL NOT NULL DEFAULT 0.0"),
        ("consensus_status", "TEXT NOT NULL DEFAULT 'CONSENSUS_PASS'"),
        ("status", "TEXT NOT NULL DEFAULT 'PENDING'"),
        ("action_plan", "TEXT"),
        ("ai_rejection_reason", "TEXT"),
        ("ai_reasoning", "TEXT"),
        ("ai_rejection_category", "TEXT"),
        ("ai_confidence", "REAL DEFAULT 0.0"),
        ("sourcing_cluster", "TEXT"),
        ("marketplace_url", "TEXT"),
        ("competitor_3star_flaws", "TEXT"),
        ("upgrade_v2_engineering", "TEXT"),
        # APRS V6 Swarm & Shortlist Fields
        ("is_shortlisted", "INTEGER DEFAULT 0"),
        ("shortlisted_at", "TIMESTAMP"),
        ("is_deleted", "INTEGER DEFAULT 0"),
        ("deletion_reason", "TEXT"),
        ("deleted_at", "TIMESTAMP"),
        ("trend_source", "TEXT"),
        ("trend_confidence_score", "REAL DEFAULT 0.0"),
        ("platform_availability", "TEXT"),
        ("custom_tags", "TEXT"),
    ]
    for col_name, col_type in required_cols:
        if not _column_exists(cur, "master_products", col_name):
            try:
                cur.execute(f"ALTER TABLE master_products ADD COLUMN {col_name} {col_type};")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    continue
                raise
    
    # 3. Product Suppliers Table
    cur.execute('''
        CREATE TABLE IF NOT EXISTS product_suppliers (
            supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            factory_name TEXT NOT NULL,
            supplier_type TEXT,
            industrial_address TEXT,
            contact_person TEXT,
            contact_details TEXT,
            platform_profile_url TEXT,
            fob_unit_price TEXT,
            moq_units INTEGER,
            sample_cost_leadtime TEXT,
            certifications TEXT,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')
    
    # 4. Daily Rolling Snapshots
    cur.execute('''
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            date DATE NOT NULL,
            current_price REAL,
            bsr_rank INTEGER,
            estimated_daily_units INTEGER,
            velocity_wow_pct REAL,
            status TEXT,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id)
        )
    ''')
    
    # 5. ZERO-LAG WAR ROOM AUDIT LOG TABLE
    cur.execute('''
        CREATE TABLE IF NOT EXISTS meeting_audit_log (
            message_id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            speaker_name TEXT NOT NULL,
            speaker_role TEXT NOT NULL,
            avatar TEXT NOT NULL,
            user_prompt TEXT NOT NULL,
            response_text TEXT NOT NULL
        )
    ''')
    
    # 6. PRODUCT GATE PROGRESS TABLE — WITH UNIQUE CONSTRAINT
    try:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS product_gate_progress (
                progress_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                gate_number INTEGER NOT NULL CHECK(gate_number BETWEEN 1 AND 6),
                status TEXT NOT NULL CHECK(status IN ('PENDING', 'IN_PROGRESS', 'PASS', 'FAIL', 'BLOCKED', 'OVERRIDDEN')),
                blocked_reason TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                completed_by TEXT,
                metadata_json TEXT,
                FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
            )
        ''')
        # Add unique index explicitly after table creation (only if table is empty)
        cur.execute('SELECT COUNT(*) FROM product_gate_progress')
        if cur.fetchone()[0] == 0:
            cur.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS uq_prod_gate 
                ON product_gate_progress (product_id, gate_number)
            ''')
            print("[DEBUG] product_gate_progress table and unique index created successfully")
        else:
            print("[DEBUG] product_gate_progress table exists with data, skipping unique index creation")
    except Exception as e:
        print(f"[ERROR] Failed to create product_gate_progress table: {e}")
        raise
    
    # 7. ARBITER DECISION LOG TABLE
    cur.execute('''
        CREATE TABLE IF NOT EXISTS arbiter_decision_log (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            model_name TEXT,
            stage_name TEXT,
            decision_json TEXT,
            latency_sec REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')

    # 8. OPEN-WEB TREND SIGNALS TABLE (Instagram, TikTok, Meta Ads, Google Trends, Reddit)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS trend_signals (
            signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            keyword TEXT NOT NULL,
            trend_category TEXT,
            region TEXT DEFAULT 'India',
            search_volume_est INTEGER DEFAULT 0,
            velocity_score REAL DEFAULT 0.0,
            longevity_days INTEGER DEFAULT 7,
            raw_signal_json TEXT,
            status TEXT DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','ARCHIVED','EXPIRED')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 9. MULTI-PLATFORM LISTINGS TABLE (Flipkart, Meesho, Myntra, Amazon, Shopify)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS multi_platform_listings (
            listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('amazon','flipkart','meesho','myntra','shopify','other')),
            title TEXT NOT NULL,
            price REAL NOT NULL,
            currency TEXT DEFAULT 'INR' CHECK(currency IN ('INR','USD','EUR','AED')),
            rating REAL,
            review_count INTEGER DEFAULT 0,
            listing_url TEXT NOT NULL,
            seller_name TEXT,
            in_stock INTEGER DEFAULT 1 CHECK(in_stock IN (0,1)),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')

    # 9b. KEEPA CACHE TABLE — Cached Keepa API responses for BSR/Price history
    cur.execute('''
        CREATE TABLE IF NOT EXISTS keepa_cache (
            cache_id INTEGER PRIMARY KEY AUTOINCREMENT,
            asin TEXT NOT NULL,
            domain TEXT NOT NULL DEFAULT 'IN',
            data_type TEXT NOT NULL CHECK(data_type IN ('bsr','price','sales','rating','reviews')),
            raw_json TEXT NOT NULL,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            UNIQUE(asin, domain, data_type)
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_keepa_asin_type ON keepa_cache(asin, data_type);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_keepa_expires ON keepa_cache(expires_at);')

    # 10. SWARM MULTI-AGENT AUDIT & BACKTRACK LOG TABLE
    cur.execute('''
        CREATE TABLE IF NOT EXISTS swarm_audit_log (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            agent_role TEXT NOT NULL,
            action TEXT NOT NULL,
            input_summary TEXT,
            reasoning TEXT NOT NULL,
            backtrack_target_stage TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 11. FORMAL NEGATIVE FINDING BACKTRACKING EVENTS TABLE
    cur.execute('''
        CREATE TABLE IF NOT EXISTS negative_findings (
            finding_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            origin_stage TEXT NOT NULL,
            target_stage TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            human_readable_reason TEXT NOT NULL,
            evidence_summary TEXT,
            severity TEXT DEFAULT 'HIGH',
            recommended_action TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 12. SOURCING LAUNCHPAD & RFQ WORKSPACE TABLE
    cur.execute('''
        CREATE TABLE IF NOT EXISTS launchpad_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            target_launch_date TEXT,
            target_moq INTEGER DEFAULT 300,
            target_fob REAL DEFAULT 0.0,
            confirmed_factory_name TEXT,
            sample_ordered INTEGER DEFAULT 0,
            sample_approved INTEGER DEFAULT 0,
            qc_aql_standard TEXT DEFAULT 'ISO 2859-1 (AQL 2.5 Major / 4.0 Minor)',
            compliance_checklist_passed INTEGER DEFAULT 0,
            purchase_order_generated INTEGER DEFAULT 0,
            launch_status TEXT DEFAULT 'SOURCING_NEGOTIATION',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')
    
    # 13. DEFECT CLUSTERS TABLE — Structured complaint clustering from reviews
    cur.execute('''
        CREATE TABLE IF NOT EXISTS defect_clusters (
            cluster_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            defect_category TEXT NOT NULL,
            defect_description TEXT NOT NULL,
            source_platform TEXT DEFAULT 'amazon',
            source_url TEXT,
            review_rating REAL DEFAULT 3.0,
            frequency_count INTEGER DEFAULT 1,
            severity TEXT DEFAULT 'MEDIUM' CHECK(severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
            is_fixable INTEGER DEFAULT 1,
            v2_fix_description TEXT,
            v2_bom_delta_usd REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')

    # 14. ECONOMICS ASSESSMENTS TABLE — 15-factor 3-scenario unit economics results
    cur.execute('''
        CREATE TABLE IF NOT EXISTS economics_assessments (
            assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            scenario TEXT NOT NULL CHECK(scenario IN ('CONSERVATIVE', 'EXPECTED', 'UPSIDE')),
            msrp REAL DEFAULT 0.0,
            fob_cost REAL DEFAULT 0.0,
            packaging_cost REAL DEFAULT 0.0,
            volumetric_freight REAL DEFAULT 0.0,
            customs_duty REAL DEFAULT 0.0,
            marketplace_commission REAL DEFAULT 0.0,
            fulfillment_fee REAL DEFAULT 0.0,
            payment_gateway_fee REAL DEFAULT 0.0,
            rto_reserve REAL DEFAULT 0.0,
            return_fraud_reserve REAL DEFAULT 0.0,
            ad_spend_reserve REAL DEFAULT 0.0,
            damage_reserve REAL DEFAULT 0.0,
            tooling_amortization REAL DEFAULT 0.0,
            net_gst_burden REAL DEFAULT 0.0,
            contribution_margin REAL DEFAULT 0.0,
            contribution_margin_pct REAL DEFAULT 0.0,
            lead_time_pass INTEGER DEFAULT 1,
            overall_pass INTEGER DEFAULT 0,
            composite_score REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')

    # 15. Discovered Sources — NIM Discovery AI finds websites/platforms dynamically
    cur.execute('''
        CREATE TABLE IF NOT EXISTS discovered_sources (
            source_id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            domain TEXT,
            source_type TEXT NOT NULL DEFAULT 'trend',
            source_name TEXT,
            description TEXT,
            region TEXT DEFAULT 'Global',
            reliability_score REAL DEFAULT 70.0,
            times_used INTEGER DEFAULT 0,
            times_yielded_results INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            last_crawled_at TIMESTAMP,
            discovered_by TEXT DEFAULT 'nim_discovery',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(url, source_type)
        )
    ''')

    # 16. Dynamic Niches — replaces hardcoded DAEMON_NICHES, auto-expanded by NIM
    cur.execute('''
        CREATE TABLE IF NOT EXISTS dynamic_niches (
            niche_id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            region TEXT NOT NULL DEFAULT 'India',
            search_limit INTEGER DEFAULT 3,
            priority_score REAL DEFAULT 50.0,
            discovered_by TEXT DEFAULT 'nim_discovery',
            source_signal TEXT,
            times_scanned INTEGER DEFAULT 0,
            products_found INTEGER DEFAULT 0,
            last_scanned_at TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, region)
        )
    ''')

    # 17. Dynamic Seed Keywords — replaces hardcoded VIRAL_SEED_ROOTS
    cur.execute('''
        CREATE TABLE IF NOT EXISTS dynamic_seed_keywords (
            seed_id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            region TEXT NOT NULL DEFAULT 'India',
            source_platform TEXT DEFAULT 'nim_generated',
            parent_keyword TEXT,
            velocity_score REAL DEFAULT 50.0,
            times_used INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(keyword, region)
        )
    ''')

    # 18. Universal Marketplace Scraper Configuration — data-driven scraper for ANY site
    cur.execute('''
        CREATE TABLE IF NOT EXISTS marketplace_config (
            config_id INTEGER PRIMARY KEY AUTOINCREMENT,
            marketplace_name TEXT NOT NULL,
            region TEXT NOT NULL DEFAULT 'Global',
            base_url TEXT NOT NULL,
            search_url_pattern TEXT NOT NULL,
            search_param_name TEXT DEFAULT 'q',
            pagination_type TEXT DEFAULT 'page_param',
            pagination_param TEXT DEFAULT 'page',
            max_pages INTEGER DEFAULT 5,
            results_per_page INTEGER DEFAULT 20,
            requires_js INTEGER DEFAULT 1,
            anti_bot_level TEXT DEFAULT 'medium',
            login_required INTEGER DEFAULT 0,
            login_url TEXT,
            cookie_domain TEXT,
            product_list_selector TEXT,
            product_title_selector TEXT,
            product_price_selector TEXT,
            product_rating_selector TEXT,
            product_review_count_selector TEXT,
            product_url_selector TEXT,
            product_image_selector TEXT,
            next_page_selector TEXT,
            custom_headers_json TEXT,
            extraction_prompt TEXT,
            is_active INTEGER DEFAULT 1,
            priority INTEGER DEFAULT 50,
            last_scraped_at TIMESTAMP,
            success_rate REAL DEFAULT 100.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(marketplace_name, region)
        )
    ''')

    # 19. Scraped Product Listings — universal storage for all marketplace results
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scraped_listings (
            listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_id INTEGER NOT NULL,
            product_id TEXT,
            marketplace TEXT NOT NULL,
            region TEXT NOT NULL,
            search_query TEXT,
            title TEXT NOT NULL,
            price REAL,
            currency TEXT DEFAULT 'INR',
            original_price REAL,
            discount_pct REAL,
            rating REAL,
            review_count INTEGER DEFAULT 0,
            availability TEXT,
            product_url TEXT NOT NULL,
            image_url TEXT,
            seller_name TEXT,
            seller_rating REAL,
            raw_data_json TEXT,
            extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (config_id) REFERENCES marketplace_config(config_id) ON DELETE CASCADE
        )
    ''')

    # 20. Indexes for marketplace scraper
    cur.execute('CREATE INDEX IF NOT EXISTS idx_mkt_config_region ON marketplace_config(region, is_active);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_scraped_listings_query ON scraped_listings(search_query, marketplace);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_scraped_listings_product ON scraped_listings(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_scraped_listings_marketplace ON scraped_listings(marketplace, region);')

    # 21. Indexes for fast queries & deduplication
    cur.execute('CREATE INDEX IF NOT EXISTS idx_prod_region ON master_products(region);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_prod_url ON master_products(marketplace_url);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_prod_shortlist ON master_products(is_shortlisted);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_prod_deleted ON master_products(is_deleted);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_meeting_session ON meeting_audit_log(session_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_gate_progress ON product_gate_progress(product_id, gate_number);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_arbiter_log ON arbiter_decision_log(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_trend_platform ON trend_signals(platform, status);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_multi_listing_prod ON multi_platform_listings(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_swarm_audit_prod ON swarm_audit_log(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_negative_findings_prod ON negative_findings(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_launchpad_prod ON launchpad_items(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_defect_clusters_prod ON defect_clusters(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_econ_assess_prod ON economics_assessments(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_disc_sources_type ON discovered_sources(source_type, is_active);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_disc_sources_region ON discovered_sources(region, source_type);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_dyn_niches_region ON dynamic_niches(region, is_active);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_dyn_seeds_region ON dynamic_seed_keywords(region, is_active);')

    # ── AI Supervisor tables: scraper_validations, ai_supervisor_logs, ai_task_improvements ──
    cur.execute('''
        CREATE TABLE IF NOT EXISTS scraper_validations (
            validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            region TEXT NOT NULL,
            is_valid INTEGER DEFAULT 1,
            confidence REAL DEFAULT 50.0,
            issues TEXT,
            auto_soft_delete INTEGER DEFAULT 0,
            rejection_reason TEXT,
            rejection_category TEXT,
            ai_notes TEXT,
            ai_suggested_fix TEXT,
            raw_product_data TEXT,
            validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ai_supervisor_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active_tasks INTEGER DEFAULT 0,
            total_validations INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS ai_task_improvements (
            improvement_id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            task_type TEXT,
            marketplace TEXT,
            region TEXT,
            improvement_type TEXT,
            description TEXT,
            priority TEXT,
            target TEXT,
            triggered_by TEXT,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # ── Website Capture Stats — tracks genuine captured data per website ──────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS website_capture_stats (
            stat_id INTEGER PRIMARY KEY AUTOINCREMENT,
            marketplace TEXT NOT NULL,
            region TEXT NOT NULL,
            source_url TEXT NOT NULL,
            total_captured INTEGER DEFAULT 0,
            genuine_captured INTEGER DEFAULT 0,
            failed_validation INTEGER DEFAULT 0,
            last_captured_at TIMESTAMP,
            last_validated_at TIMESTAMP,
            validation_success_rate REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(marketplace, region, source_url)
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_website_capture_stats_marketplace ON website_capture_stats(marketplace, region);')

    # ── URL Validation Log — tracks URL validation results ───────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS url_validation_log (
            validation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            marketplace TEXT NOT NULL,
            region TEXT NOT NULL,
            url TEXT NOT NULL,
            is_accessible INTEGER DEFAULT 0,
            http_status_code INTEGER,
            content_matches_product INTEGER DEFAULT 0,
            title_match_score REAL,
            price_match_score REAL,
            response_time_ms INTEGER,
            error_message TEXT,
            validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_url_validation_log_product ON url_validation_log(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_url_validation_log_url ON url_validation_log(url);')

    # ── Learned Rules — persistent rule storage from rule_engine.py ────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS learned_rules (
            rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_id_str TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            description TEXT,
            condition TEXT NOT NULL,
            action TEXT NOT NULL,
            severity INTEGER DEFAULT 1,
            params_json TEXT,
            enabled INTEGER DEFAULT 1,
            tags_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_learned_rules_enabled ON learned_rules(enabled);')

    # ── Gate Execution Logs — audit trail for 4-gate pipeline ──────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS gate_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            gate_number INTEGER NOT NULL CHECK(gate_number BETWEEN 1 AND 4),
            gate_name TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('PENDING', 'RUNNING', 'PASS', 'FAIL', 'BLOCKED')),
            details_json TEXT,
            error_message TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            duration_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_gate_logs_product ON gate_logs(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_gate_logs_gate ON gate_logs(gate_number);')

    # ── Review Snapshots — 3-star review storage for defect mining ────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS review_snapshots (
            snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            marketplace TEXT NOT NULL DEFAULT 'amazon',
            rating REAL NOT NULL CHECK(rating >= 1.0 AND rating <= 5.0),
            review_text TEXT NOT NULL,
            review_title TEXT,
            reviewer_name TEXT,
            review_date TEXT,
            helpful_votes INTEGER DEFAULT 0,
            verified_purchase INTEGER DEFAULT 0,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_review_snapshots_product ON review_snapshots(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_review_snapshots_rating ON review_snapshots(rating);')

    # Ensure AI rejection columns exist in master_products
    _ai_cols = [
        ("ai_rejection_reason",    "TEXT"),
        ("ai_rejection_category",  "TEXT"),
        ("ai_reasoning",           "TEXT"),
        ("ai_confidence",          "REAL DEFAULT 0.0"),
    ]
    for _col, _dtype in _ai_cols:
        if not _column_exists(cur, "master_products", _col):
            try:
                cur.execute(f"ALTER TABLE master_products ADD COLUMN {_col} {_dtype}")
            except Exception:
                pass

    # ── 1. Supplier Profiles — verified suppliers with GST, verification status ─────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS supplier_profiles (
            supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            company_name TEXT NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('indiamart','alibaba','exportersindia','tradeindia','other')),
            profile_url TEXT,
            contact_phone TEXT,
            contact_email TEXT,
            gst_number TEXT,
            moq_estimate INTEGER,
            verification_badge INTEGER DEFAULT 0 CHECK(verification_badge IN (0,1)),
            product_categories TEXT,
            location TEXT,
            gst_verified INTEGER DEFAULT 0 CHECK(gst_verified IN (0,1)),
            gst_check_date TEXT,
            verification_score REAL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','VERIFIED','REJECTED','CONTACTED')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_supplier_profiles_product ON supplier_profiles(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_supplier_profiles_status ON supplier_profiles(status);')

    # ── 2. Outreach Drafts — email drafts awaiting human approval ──────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS outreach_drafts (
            draft_id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'email' CHECK(channel IN ('email','whatsapp','indiamart_chat')),
            status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','APPROVED','REJECTED','SENT','HOLD')),
            approved_by TEXT,
            approved_at TIMESTAMP,
            sent_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES supplier_profiles(supplier_id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_outreach_drafts_supplier ON outreach_drafts(supplier_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_outreach_drafts_status ON outreach_drafts(status);')

    # ── 3. Supplier Conversations — email/WhatsApp thread history ──────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS supplier_conversations (
            conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER NOT NULL,
            channel TEXT NOT NULL CHECK(channel IN ('email','whatsapp','indiamart_chat')),
            direction TEXT NOT NULL CHECK(direction IN ('inbound','outbound')),
            message_text TEXT,
            message_id TEXT,  -- external message ID (e.g. WhatsApp message ID)
            status TEXT NOT NULL DEFAULT 'RECEIVED' CHECK(status IN ('RECEIVED','READ','REPLIED')),
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES supplier_profiles(supplier_id) ON DELETE CASCADE
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_supplier_conversations_supplier ON supplier_conversations(supplier_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_supplier_conversations_received ON supplier_conversations(received_at);')

    # ── 4. Problem Opportunities — unmet needs from reviews/Q&A/Reddit ──────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS problem_opportunities (
            opportunity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT NOT NULL,
            source TEXT NOT NULL CHECK(source IN ('amazon_qa','amazon_reviews','reddit','youtube','flipkart','quora','trustpilot','other')),
            source_url TEXT,
            problem_text TEXT NOT NULL,
            problem_category TEXT CHECK(problem_category IN ('functional','quality','ux','durability','missing_feature','other')),
            severity TEXT CHECK(severity IN ('critical','major','minor')),
            frequency_estimate INTEGER,  -- estimated users affected (1-10 scale)
            suggested_solution TEXT,
            market_size_estimate TEXT,
            competitor_solution TEXT,
            status TEXT NOT NULL DEFAULT 'IDENTIFIED' CHECK(status IN ('IDENTIFIED','VALIDATED','IN_PROGRESS','LAUNCHED')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE CASCADE
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_problem_opportunities_product ON problem_opportunities(product_id);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_problem_opportunities_source ON problem_opportunities(source);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_problem_opportunities_status ON problem_opportunities(status);')

    # ── 5. LLM Tier Log — track which LLM tier was used for each call ──────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS llm_tier_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            tier_used INTEGER NOT NULL,  -- 1=NIM, 2=Ollama, 3=Groq, 4=Kimi, 5=Human
            tier_name TEXT NOT NULL,
            model_name TEXT,
            task_type TEXT,
            success INTEGER NOT NULL,
            latency_ms INTEGER,
            tokens_used INTEGER,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_llm_tier_log_agent ON llm_tier_log(agent_name);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_llm_tier_log_tier ON llm_tier_log(tier_used);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_llm_tier_log_created ON llm_tier_log(created_at);')

    # ── 6. Pending Human Decisions — tasks waiting for human approval ───────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pending_human_decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            product_id TEXT,
            task_type TEXT NOT NULL,
            context_json TEXT NOT NULL,
            options_json TEXT NOT NULL,  -- [{"label": "Approve", "action": "approve"}, ...]
            decision TEXT,  -- human's choice
            decided_by TEXT,
            decided_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,  -- auto-expire after 24h
            status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','DECIDED','EXPIRED','SKIPPED')),
            priority INTEGER DEFAULT 1,
            FOREIGN KEY (product_id) REFERENCES master_products(product_id) ON DELETE SET NULL
        )
    ''')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_pending_decisions_agent ON pending_human_decisions(agent_name);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_pending_decisions_status ON pending_human_decisions(status);')
    cur.execute('CREATE INDEX IF NOT EXISTS idx_pending_decisions_expires ON pending_human_decisions(expires_at);')

    # Ensure AI rejection columns exist in master_products

    conn.commit()
    conn.close()


def is_duplicate_product(product_id: str, marketplace_url: str) -> bool:
    """Checks if product or ASIN URL already exists in database."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT product_id FROM master_products WHERE product_id = ? OR marketplace_url = ?", (product_id, marketplace_url))
    exists = cur.fetchone() is not None
    conn.close()
    return exists

def record_product_evaluation(prod_dict: dict, eval_dict: dict, model_name: str = "Nemotron-3-Ultra-550B") -> bool:
    """Inserts or updates a validated product dossier into the SSOT database."""
    if not eval_dict:
        raise ValueError("eval_dict cannot be empty. Gate 3 must produce real economics before DB write.")
    
    try:
        merged_data = {
            "product_id": prod_dict["id"],
            "name": prod_dict["name"],
            "category": prod_dict["category"],
            "region": prod_dict.get("region", "USA"),
            "planned_msrp": float(prod_dict.get("retail_msrp", 49.99)),
            "landed_cogs": float(eval_dict.get("landed_cogs", prod_dict.get("factory_cogs", 0.0))),
            "gross_margin_pct": float(eval_dict.get("gross_margin_pct", 0.0)),
            "estimated_cac": float(prod_dict.get("est_cac", 0.0)),
            "net_profit_pct": float(eval_dict.get("net_profit_pct", 0.0)),
            "worst_case_stress_margin_pct": float(eval_dict.get("worst_case_stress_margin_pct", eval_dict.get("stress_margin_pct", 0.0))),
            "status": eval_dict.get("status", "PENDING"),
            "overall_score": float(eval_dict.get("score", 0.0)),
            "consensus_status": eval_dict.get("consensus_status", "CONSENSUS_PASS"),
            "action_plan": eval_dict.get("action_plan", "Awaiting Gate 2 manual defect review"),
            "sourcing_cluster": prod_dict.get("sourcing_hub", ""),
            "marketplace_url": prod_dict.get("marketplace_url", ""),
            "competitor_3star_flaws": prod_dict.get("competitor_flaw", ""),
            "upgrade_v2_engineering": prod_dict.get("upgrade_v2", ""),
            "bsr_rank": int(prod_dict.get("bsr_rank", 100)),
            "estimated_daily_units": int(prod_dict.get("estimated_daily_units", 30)),
            "ad_active_days": int(prod_dict.get("ad_active_days", 0)),
            "suppliers": prod_dict.get("suppliers", [])
        }
        
        validated = ProductEvaluationModel(**merged_data)
        
        conn = get_connection()
        cur = conn.cursor()
        
        today_str = datetime.now(timezone.utc).date().isoformat()
        
        # Upsert into master_products (including V6 trend & shortlist fields + AI Supervision fields)
        cur.execute('''
            INSERT INTO master_products (
                product_id, name, category, region, planned_msrp, landed_cogs,
                gross_margin_pct, estimated_cac, net_profit_pct, worst_case_stress_margin_pct,
                status, overall_score, consensus_status, action_plan, sourcing_cluster,
                marketplace_url, competitor_3star_flaws, upgrade_v2_engineering,
                bsr_rank, estimated_daily_units, ad_active_days,
                is_shortlisted, is_deleted, trend_source, trend_confidence_score, platform_availability,
                first_discovered_date, last_evaluated_date, updated_at,
                -- AI Supervision columns
                ai_rejection_reason, ai_reasoning, ai_rejection_category, ai_confidence
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                name=excluded.name,
                planned_msrp=excluded.planned_msrp,
                landed_cogs=excluded.landed_cogs,
                gross_margin_pct=excluded.gross_margin_pct,
                estimated_cac=excluded.estimated_cac,
                net_profit_pct=excluded.net_profit_pct,
                worst_case_stress_margin_pct=excluded.worst_case_stress_margin_pct,
                status=excluded.status,
                overall_score=excluded.overall_score,
                consensus_status=excluded.consensus_status,
                action_plan=excluded.action_plan,
                marketplace_url=excluded.marketplace_url,
                bsr_rank=excluded.bsr_rank,
                estimated_daily_units=excluded.estimated_daily_units,
                ad_active_days=excluded.ad_active_days,
                trend_source=COALESCE(excluded.trend_source, master_products.trend_source),
                trend_confidence_score=COALESCE(excluded.trend_confidence_score, master_products.trend_confidence_score),
                platform_availability=COALESCE(excluded.platform_availability, master_products.platform_availability),
                last_evaluated_date=excluded.last_evaluated_date,
                updated_at=CURRENT_TIMESTAMP,
                -- AI Supervision columns
                ai_rejection_reason=COALESCE(excluded.ai_rejection_reason, master_products.ai_rejection_reason),
                ai_reasoning=COALESCE(excluded.ai_reasoning, master_products.ai_reasoning),
                ai_rejection_category=COALESCE(excluded.ai_rejection_category, master_products.ai_rejection_category),
                ai_confidence=COALESCE(excluded.ai_confidence, master_products.ai_confidence)
        ''', (
            validated.product_id, validated.name, validated.category, validated.region,
            validated.planned_msrp, validated.landed_cogs, validated.gross_margin_pct,
            validated.estimated_cac, validated.net_profit_pct, validated.worst_case_stress_margin_pct,
            validated.status, validated.overall_score, validated.consensus_status, validated.action_plan,
            validated.sourcing_cluster, validated.marketplace_url, validated.competitor_3star_flaws,
            validated.upgrade_v2_engineering, validated.bsr_rank, validated.estimated_daily_units,
            validated.ad_active_days, validated.is_shortlisted, validated.is_deleted,
            validated.trend_source, validated.trend_confidence_score, validated.platform_availability,
            today_str, today_str,
            # AI Supervision columns
            validated.ai_rejection_reason, validated.ai_reasoning, validated.ai_rejection_category, validated.ai_confidence
        ))
        
        # Initialize gate progress for new products
        cur.execute("SELECT COUNT(*) FROM product_gate_progress WHERE product_id = ?", (validated.product_id,))
        if cur.fetchone()[0] == 0:
            for g in range(1, 7):
                cur.execute('''
                    INSERT INTO product_gate_progress (product_id, gate_number, status, started_at)
                    VALUES (?, ?, 'PENDING', CURRENT_TIMESTAMP)
                ''', (validated.product_id, g))
        
        # Refresh suppliers for this product
        cur.execute("DELETE FROM product_suppliers WHERE product_id = ?", (validated.product_id,))
        for s in validated.suppliers:
            cur.execute('''
                INSERT INTO product_suppliers (
                    product_id, factory_name, supplier_type, industrial_address,
                    contact_person, contact_details, platform_profile_url,
                    fob_unit_price, moq_units, sample_cost_leadtime, certifications
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                validated.product_id, s.factory_name, s.supplier_type, s.industrial_address,
                s.contact_person, s.contact_details, s.platform_profile_url,
                s.fob_unit_price, s.moq_units, s.sample_cost_leadtime, s.certifications
            ))
            
        conn.commit()
        conn.close()
        return True
    except (ValueError, TypeError) as e:
        print(f"[DB VALIDATION ERROR in record_product_evaluation]: {e}")
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"[DB ERROR in record_product_evaluation]: {e}")
        traceback.print_exc()
        raise

def get_all_products(include_deleted: bool = False, shortlisted_only: bool = False) -> List[Dict[str, Any]]:
    """Fetches products with attached suppliers from SQLite SSOT, filtering soft-deleted by default."""
    conn = get_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM master_products"
    clauses = []
    params = []
    
    if not include_deleted:
        clauses.append("COALESCE(is_deleted, 0) = 0")
    if shortlisted_only:
        clauses.append("COALESCE(is_shortlisted, 0) = 1")
        
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
        
    query += " ORDER BY overall_score DESC"
    
    cur.execute(query, params)
    products = [dict(row) for row in cur.fetchall()]
    
    for p in products:
        cur.execute("SELECT * FROM product_suppliers WHERE product_id = ?", (p["product_id"],))
        p["suppliers"] = [dict(s) for s in cur.fetchall()]
        # Attach multi-platform listings if available
        cur.execute("SELECT platform, title, price, currency, rating, review_count, listing_url, in_stock FROM multi_platform_listings WHERE product_id = ?", (p["product_id"],))
        p["multi_platform_listings"] = [dict(l) for l in cur.fetchall()]
        
    conn.close()
    return products

def soft_delete_product(product_id: str, deletion_reason: str, deleted_by: str = "human", 
                         ai_rejection_reason: Optional[str] = None, ai_reasoning: Optional[str] = None,
                         ai_rejection_category: Optional[str] = None, ai_confidence: float = 0.0) -> bool:
    """Soft-deletes a product with mandatory audit rationale, preserving history.
    Optionally accepts AI Supervisor rejection details for Archive tracking."""
    if not deletion_reason or not deletion_reason.strip():
        raise ValueError("A deletion reason is mandatory for auditing purposes.")
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            UPDATE master_products
            SET is_deleted = 1, 
                deletion_reason = ?, 
                deleted_at = CURRENT_TIMESTAMP, 
                updated_at = CURRENT_TIMESTAMP,
                ai_rejection_reason = COALESCE(?, ai_rejection_reason),
                ai_reasoning = COALESCE(?, ai_reasoning),
                ai_rejection_category = COALESCE(?, ai_rejection_category),
                ai_confidence = COALESCE(?, ai_confidence)
            WHERE product_id = ?
        ''', (deletion_reason.strip(), ai_rejection_reason, ai_reasoning, 
              ai_rejection_category, ai_confidence, product_id))
        
        # Log to swarm audit log
        cur.execute('''
            INSERT INTO swarm_audit_log (product_id, agent_role, action, input_summary, reasoning)
            VALUES (?, ?, 'SOFT_DELETE', 'User/AI requested deletion', ?)
        ''', (product_id, deleted_by, deletion_reason.strip()))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Soft Delete Error]: {e}")
        return False

def restore_product(product_id: str) -> bool:
    """Restores a soft-deleted product back to the active catalogue."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            UPDATE master_products
            SET is_deleted = 0, deletion_reason = NULL, deleted_at = NULL, updated_at = CURRENT_TIMESTAMP,
                ai_rejection_reason = NULL, ai_reasoning = NULL, ai_rejection_category = NULL, ai_confidence = 0.0
            WHERE product_id = ?
        ''', (product_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Restore Error]: {e}")
        return False

def write_ai_rejection(product_id: str, ai_rejection_reason: str, ai_reasoning: str, 
                       ai_rejection_category: str, ai_confidence: float = 0.0) -> bool:
    """Write AI Supervisor rejection details to a product for Archive tracking.
    Used when AI Supervisor validates and rejects a scraped product."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            UPDATE master_products
            SET is_deleted = 1,
                deletion_reason = ?,
                deleted_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP,
                ai_rejection_reason = ?,
                ai_reasoning = ?,
                ai_rejection_category = ?,
                ai_confidence = ?
            WHERE product_id = ?
        ''', (f"AI Validation Rejected: {ai_rejection_reason}", ai_rejection_reason, ai_reasoning, 
              ai_rejection_category, ai_confidence, product_id))
        
        # Log to swarm audit log
        cur.execute('''
            INSERT INTO swarm_audit_log (product_id, agent_role, action, input_summary, reasoning)
            VALUES (?, ?, 'AI_VALIDATION_REJECTED', 'AI Supervisor validation failed', ?)
        ''', (product_id, "ai_supervisor", ai_reasoning[:500]))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Write AI Rejection Error]: {e}")
        return False

def toggle_shortlist(product_id: str, is_shortlisted: bool = True) -> bool:
    """Marks or unmarks a product as shortlisted for active selling/sourcing."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        shortlist_val = 1 if is_shortlisted else 0
        cur.execute('''
            UPDATE master_products
            SET is_shortlisted = ?, shortlisted_at = CASE WHEN ? = 1 THEN CURRENT_TIMESTAMP ELSE NULL END, updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
        ''', (shortlist_val, shortlist_val, product_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Shortlist Error]: {e}")
        return False

def get_shortlisted_products() -> List[Dict[str, Any]]:
    """Returns only active products marked as shortlisted for selling."""
    return get_all_products(include_deleted=False, shortlisted_only=True)

# -------------------------------------------------------------
# OPEN-WEB TREND SIGNALS & MULTI-PLATFORM RECORDING
# -------------------------------------------------------------
def record_trend_signal(platform: str, keyword: str, category: str = "General", region: str = "India",
                        search_volume_est: int = 0, velocity_score: float = 0.0,
                        longevity_days: int = 7, raw_json: dict = None) -> int:
    """Records an emerging social/search trend signal from Instagram, TikTok, Meta, Google, or Reddit."""
    max_retries = 5
    base_delay = 0.1
    
    for attempt in range(5):
        try:
            conn = get_connection()
            cur = conn.cursor()
            raw_str = json.dumps(raw_json or {})
            cur.execute('''
                INSERT INTO trend_signals (platform, keyword, trend_category, region, search_volume_est, velocity_score, longevity_days, raw_signal_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (platform, keyword, category, region, search_volume_est, velocity_score, longevity_days, raw_str))
            signal_id = cur.lastrowid
            conn.commit()
            conn.close()
            return signal_id
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower() and attempt < 4:
                import time, random
                delay = 0.1 * (2 ** attempt) + random.uniform(0, 0.1)
                time.sleep(delay)
                continue
            print(f"[DB Record Trend Error]: {e}")
            return 0
        except Exception as e:
            print(f"[DB Record Trend Error]: {e}")
            return 0
    return 0

def get_active_trend_signals(region: str = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetches active trend signals sorted by velocity and longevity."""
    conn = get_connection()
    cur = conn.cursor()
    if region:
        cur.execute("SELECT * FROM trend_signals WHERE status = 'ACTIVE' AND region = ? ORDER BY velocity_score DESC, created_at DESC LIMIT ?", (region, limit))
    else:
        cur.execute("SELECT * FROM trend_signals WHERE status = 'ACTIVE' ORDER BY velocity_score DESC, created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_trend_signals(category: str = "", region: str = "India", limit: int = 50) -> List[Dict[str, Any]]:
    """Fetches trend signals filtered by category and region."""
    conn = get_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM trend_signals WHERE status = 'ACTIVE'"
    params = []
    
    if region:
        query += " AND region = ?"
        params.append(region)
    
    if category:
        query += " AND (trend_category = ? OR keyword LIKE ?)"
        params.extend([category, f"%{category}%"])
    
    query += " ORDER BY velocity_score DESC, created_at DESC LIMIT ?"
    params.append(limit)
    
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def record_multi_platform_listing(product_id: str, platform: str, title: str, price: float,
                                  listing_url: str, rating: float = None, review_count: int = 0,
                                  currency: str = "INR", seller_name: str = None) -> bool:
    """Stores cross-platform listings (Flipkart, Meesho, Myntra, Amazon, Shopify)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO multi_platform_listings (product_id, platform, title, price, currency, rating, review_count, listing_url, seller_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (product_id, platform, title, float(price), currency, rating, int(review_count), listing_url, seller_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Multi-Platform Listing Error]: {e}")
        return False

def record_multi_platform_listing(product_id: str, platform: str, title: str, price: float,
                                  listing_url: str, rating: float = None, review_count: int = 0,
                                  currency: str = "INR", seller_name: str = None) -> bool:
    """Stores cross-platform listings (Flipkart, Meesho, Myntra, Amazon, Shopify)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO multi_platform_listings (product_id, platform, title, price, currency, rating, review_count, listing_url, seller_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (product_id, platform, title, float(price), currency, rating, int(review_count), listing_url, seller_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Multi-Platform Listing Error]: {e}")
        return False


# ── KEEPA CACHE ──────────────────────────────────────────────────────────────────

def set_keepa_cache(asin: str, domain: str, data_type: str, raw_json: str, ttl_hours: int = 24) -> bool:
    """Store Keepa API response in cache with TTL."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        expires_at = datetime.now(timezone.utc).replace(microsecond=0)
        expires_at = expires_at.replace(hour=expires_at.hour + ttl_hours)
        cur.execute('''
            INSERT INTO keepa_cache (asin, domain, data_type, raw_json, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(asin, domain, data_type) DO UPDATE SET
                raw_json = excluded.raw_json,
                expires_at = excluded.expires_at,
                fetched_at = CURRENT_TIMESTAMP
        ''', (asin, domain, data_type, raw_json, expires_at.isoformat()))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Keepa Cache Error]: {e}")
        return False


def get_keepa_cache(asin: str, domain: str, data_type: str) -> Optional[Dict]:
    """Retrieve valid Keepa cache entry."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            SELECT * FROM keepa_cache 
            WHERE asin = ? AND domain = ? AND data_type = ? AND expires_at > CURRENT_TIMESTAMP
        ''', (asin, domain, data_type))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[DB Keepa Cache Error]: {e}")
        return None


def clean_expired_keepa_cache() -> int:
    """Remove expired Keepa cache entries. Returns count of deleted rows."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM keepa_cache WHERE expires_at <= CURRENT_TIMESTAMP')
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        return deleted
    except Exception as e:
        print(f"[DB Keepa Cache Clean Error]: {e}")
        return 0


def record_swarm_audit_log(product_id: str, agent_role: str, action: str, reasoning: str,
                           input_summary: str = "", backtrack_target_stage: str = None) -> bool:
    """Records an AI swarm audit decision, verification step, or false-positive backtrack alarm."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO swarm_audit_log (product_id, agent_role, action, input_summary, reasoning, backtrack_target_stage)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (product_id, agent_role, action, input_summary, reasoning, backtrack_target_stage))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Swarm Audit Log Error]: {e}")
        return False

def get_swarm_audit_logs(product_id: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetches swarm audit decisions and backtrack logs."""
    conn = get_connection()
    cur = conn.cursor()
    if product_id:
        cur.execute("SELECT * FROM swarm_audit_log WHERE product_id = ? ORDER BY audit_id DESC LIMIT ?", (product_id, limit))
    else:
        cur.execute("SELECT * FROM swarm_audit_log ORDER BY audit_id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# -------------------------------------------------------------
# UNIFIED DATABASE EXPLORER INSPECTOR (APRS V6)
# -------------------------------------------------------------
def get_all_table_names() -> List[str]:
    """Returns all user table names present in SQLite database."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name ASC;")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()
    return tables

def get_table_data(table_name: str, limit: int = 200, search_query: str = None) -> List[Dict[str, Any]]:
    """Safely retrieves raw records from any SQLite table for the Unified SSOT Explorer."""
    # Whitelist table names to prevent SQL injection
    valid_tables = get_all_table_names()
    if table_name not in valid_tables:
        return []
    
    conn = get_connection()
    cur = conn.cursor()
    
    if search_query and search_query.strip():
        # Generic text search across table columns
        cur.execute(f"PRAGMA table_info({table_name});")
        text_cols = [r[1] for r in cur.fetchall() if "TEXT" in str(r[2]).upper() or "CHAR" in str(r[2]).upper()]
        if text_cols:
            where_clause = " OR ".join([f"{col} LIKE ?" for col in text_cols])
            params = [f"%{search_query.strip()}%"] * len(text_cols)
            cur.execute(f"SELECT * FROM {table_name} WHERE {where_clause} LIMIT {int(limit)}", params)
        else:
            cur.execute(f"SELECT * FROM {table_name} LIMIT {int(limit)}")
    else:
        cur.execute(f"SELECT * FROM {table_name} LIMIT {int(limit)}")
        
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def set_human_override(product_id: str, new_status: str) -> bool:
    """Allows human user to override algorithmic verdicts AND sync all gates."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            UPDATE master_products
            SET human_override_status = ?, status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
        ''', (new_status, new_status, product_id))
        
        # SYNC: Override all gates
        if new_status in ("PASS", "OVERRIDDEN"):
            for g in range(1, 7):
                cur.execute('''
                    UPDATE product_gate_progress
                    SET status = 'OVERRIDDEN', completed_by = 'human_override', completed_at = CURRENT_TIMESTAMP
                    WHERE product_id = ? AND gate_number = ?
                ''', (product_id, g))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Override Error]: {e}")
        return False

# -------------------------------------------------------------
# ZERO-LAG MEETING AUDIT LOGGING
# -------------------------------------------------------------
def log_meeting_turn(session_id: str, speaker_name: str, speaker_role: str, avatar: str, user_prompt: str, response_text: str):
    """Inserts a single chat message turn into SQLite audit table instantly (O(1))."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO meeting_audit_log (session_id, speaker_name, speaker_role, avatar, user_prompt, response_text)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, speaker_name, speaker_role, avatar, user_prompt, response_text))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Meeting Log Error]: {e}")

def get_meeting_history(session_id: str = None) -> List[Dict[str, Any]]:
    """Fetches all logged meeting dialogue from SQLite."""
    conn = get_connection()
    cur = conn.cursor()
    if session_id:
        cur.execute("SELECT * FROM meeting_audit_log WHERE session_id = ? ORDER BY message_id ASC", (session_id,))
    else:
        cur.execute("SELECT * FROM meeting_audit_log ORDER BY message_id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# -------------------------------------------------------------
# GATE STATE MACHINE (6-Stage Workflow)
# -------------------------------------------------------------
GATE_NAMES = {
    1: "SIGNAL_DISCOVERY",
    2: "DEFECT_MINING",
    3: "ECONOMICS_VALIDATION",
    4: "SOURCING_QUOTE",
    5: "WAR_ROOM_CONSENSUS",
    6: "SIGN_OFF_ARTIFACTS"
}

GATE_ORDER = [1, 2, 3, 4, 5, 6]

def init_product_gates(product_id: str) -> bool:
    """Initialize all 6 gates for a new product as PENDING."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        for gate_num in GATE_ORDER:
            cur.execute('''
                INSERT OR IGNORE INTO product_gate_progress (product_id, gate_number, status, started_at)
                VALUES (?, ?, 'PENDING', CURRENT_TIMESTAMP)
            ''', (product_id, gate_num))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[GATE INIT ERROR]: {e}")
        return False

def reset_product_gates(product_id: str) -> bool:
    """Reset all gates for a product back to PENDING."""
    try:
        conn = get_connection()
        conn.execute("DELETE FROM product_gate_progress WHERE product_id = ?", (product_id,))
        conn.commit()
        conn.close()
        return init_product_gates(product_id)
    except Exception as e:
        print(f"[GATE RESET ERROR]: {e}")
        return False

def get_gate_status(product_id: str, gate_number: int = None) -> List[Dict[str, Any]]:
    """Get gate progress for a product. If gate_number is None, returns all gates."""
    conn = get_connection()
    cur = conn.cursor()
    if gate_number:
        cur.execute("SELECT * FROM product_gate_progress WHERE product_id = ? AND gate_number = ?", (product_id, gate_number))
    else:
        cur.execute("SELECT * FROM product_gate_progress WHERE product_id = ? ORDER BY gate_number", (product_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def update_gate_status(product_id: str, gate_number: int, status: str, blocked_reason: str = None, metadata: Dict = None, completed_by: str = "system") -> bool:
    """Update a gate's status with timestamp and metadata."""
    valid_statuses = ['PENDING', 'IN_PROGRESS', 'PASS', 'FAIL', 'BLOCKED', 'OVERRIDDEN']
    if status not in valid_statuses:
        raise ValueError(f"Invalid status: {status}. Must be one of {valid_statuses}")
    if gate_number not in GATE_ORDER:
        raise ValueError(f"Invalid gate_number: {gate_number}. Must be 1-5")
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        now = datetime.now(timezone.utc).isoformat()
        details_json = json.dumps(metadata or {})
        
        if status == 'IN_PROGRESS':
            cur.execute('''
                UPDATE product_gate_progress
                SET status = ?, started_at = COALESCE(started_at, ?), blocked_reason = ?, details_json = ?, completed_by = ?
                WHERE product_id = ? AND gate_number = ?
            ''', (status, now, blocked_reason, details_json, completed_by, product_id, gate_number))
        elif status in ('PASS', 'FAIL', 'OVERRIDDEN'):
            cur.execute('''
                UPDATE product_gate_progress
                SET status = ?, completed_at = ?, blocked_reason = ?, details_json = ?, completed_by = ?
                WHERE product_id = ? AND gate_number = ?
            ''', (status, now, blocked_reason, details_json, completed_by, product_id, gate_number))
        elif status == 'BLOCKED':
            cur.execute('''
                UPDATE product_gate_progress
                SET status = ?, blocked_reason = ?, details_json = ?, completed_by = ?
                WHERE product_id = ? AND gate_number = ?
            ''', (status, blocked_reason, details_json, completed_by, product_id, gate_number))
        else:  # PENDING
            cur.execute('''
                UPDATE product_gate_progress
                SET status = ?, started_at = NULL, completed_at = NULL, blocked_reason = NULL, details_json = '{}', completed_by = NULL
                WHERE product_id = ? AND gate_number = ?
            ''', (status, product_id, gate_number))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[GATE UPDATE ERROR]: {e}")
        return False

def can_enter_gate(product_id: str, gate_number: int) -> tuple[bool, str]:
    """
    Check if a product can enter a specific gate.
    Returns (can_enter: bool, reason: str)
    """
    if gate_number == 1:
        return True, "Gate 1 always open"
    
    # Gates 3 and 4 both require Gate 2 PASS (not sequential)
    # Gate 3: Economics with estimated FOB
    # Gate 4: Manual FOB entry
    if gate_number in (3, 4):
        prev_gate = 2
        gates = get_gate_status(product_id)
        prev_gate_info = next((g for g in gates if g['gate_number'] == prev_gate), None)
        
        if not prev_gate_info:
            return False, f"Gate 2 not initialized"
        
        if prev_gate_info['status'] == 'PASS':
            return True, f"Gate 2 passed"
        elif prev_gate_info['status'] == 'OVERRIDDEN':
            return True, f"Gate 2 overridden by human"
        elif prev_gate_info['status'] == 'FAIL':
            return False, f"Gate 2 failed: {prev_gate_info.get('blocked_reason', 'No reason recorded')}"
        elif prev_gate_info['status'] == 'BLOCKED':
            return False, f"Gate 2 blocked: {prev_gate_info.get('blocked_reason', 'No reason recorded')}"
        else:
            return False, f"Gate 2 is {prev_gate_info['status']} (must be PASS or OVERRIDDEN)"
    
    # Gates 5 and 6 require previous gate PASS
    prev_gate = gate_number - 1
    gates = get_gate_status(product_id)
    prev_gate_info = next((g for g in gates if g['gate_number'] == prev_gate), None)
    
    if not prev_gate_info:
        return False, f"Previous gate {prev_gate} not initialized"
    
    if prev_gate_info['status'] == 'PASS':
        return True, f"Gate {prev_gate} passed"
    elif prev_gate_info['status'] == 'OVERRIDDEN':
        return True, f"Gate {prev_gate} overridden by human"
    elif prev_gate_info['status'] == 'FAIL':
        return False, f"Gate {prev_gate} failed: {prev_gate_info.get('blocked_reason', 'No reason recorded')}"
    elif prev_gate_info['status'] == 'BLOCKED':
        return False, f"Gate {prev_gate} blocked: {prev_gate_info.get('blocked_reason', 'No reason recorded')}"
    else:
        return False, f"Gate {prev_gate} is {prev_gate_info['status']} (must be PASS or OVERRIDDEN)"

def get_current_gate(product_id: str) -> int:
    """Get the current active gate for a product (first non-PASS gate)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT gate_number, status FROM product_gate_progress WHERE product_id = ? ORDER BY gate_number ASC", (product_id,))
    gates = cur.fetchall()
    conn.close()
    
    if not gates:
        # Auto-initialize if missing
        init_product_gates(product_id)
        return 1
        
    for g in gates:
        if g["status"] not in ("PASS", "OVERRIDDEN"):
            return g["gate_number"]
    return 7  # All passed

def get_products_stuck_at_gate(gate_number: int) -> List[Dict[str, Any]]:
    """Get all products currently stuck at a specific gate."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT mp.product_id, mp.name, mp.category, mp.region, pgp.blocked_reason, pgp.status, pgp.metadata_json
        FROM master_products mp
        JOIN product_gate_progress pgp ON mp.product_id = pgp.product_id
        WHERE pgp.gate_number = ? AND pgp.status IN ('BLOCKED', 'IN_PROGRESS', 'PENDING')
        ORDER BY mp.updated_at DESC
    ''', (gate_number,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def record_negative_finding(
    product_id: str,
    origin_stage: str,
    target_stage: str,
    reason_code: str,
    human_readable_reason: str,
    evidence_summary: str = "",
    severity: str = "HIGH",
    recommended_action: str = "Branch to next candidate"
) -> int:
    """Records a formal backtracking NegativeFinding event."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO negative_findings (
            product_id, origin_stage, target_stage, reason_code,
            human_readable_reason, evidence_summary, severity, recommended_action
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_id, origin_stage, target_stage, reason_code,
        human_readable_reason, evidence_summary, severity, recommended_action
    ))
    fid = cur.lastrowid
    conn.commit()
    conn.close()
    return fid

def get_negative_findings(product_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Fetches negative finding events for auditing and false-positive backtracking."""
    conn = get_connection()
    cur = conn.cursor()
    if product_id:
        cur.execute("SELECT * FROM negative_findings WHERE product_id = ? ORDER BY created_at DESC LIMIT ?", (product_id, limit))
    else:
        cur.execute("SELECT * FROM negative_findings ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def add_to_launchpad(
    product_id: str,
    product_name: str,
    target_moq: int = 300,
    target_fob: float = 0.0,
    target_launch_date: Optional[str] = None,
    confirmed_factory_name: Optional[str] = None
) -> int:
    """Adds a shortlisted product to the Sourcing & Launchpad workspace."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO launchpad_items (
            product_id, product_name, target_moq, target_fob,
            target_launch_date, confirmed_factory_name
        ) VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        product_id, product_name, target_moq, target_fob,
        target_launch_date, confirmed_factory_name
    ))
    lid = cur.lastrowid
    conn.commit()
    conn.close()
    return lid

def get_launchpad_items() -> List[Dict[str, Any]]:
    """Fetches all items in the Sourcing & Launchpad pipeline."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM launchpad_items ORDER BY updated_at DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def update_launchpad_status(
    item_id: int,
    launch_status: str,
    sample_ordered: Optional[bool] = None,
    sample_approved: Optional[bool] = None,
    qc_passed: Optional[bool] = None,
    po_generated: Optional[bool] = None
) -> bool:
    """Updates the status and milestone checkboxes of a launchpad SKU."""
    conn = get_connection()
    cur = conn.cursor()
    updates = ["launch_status = ?", "updated_at = CURRENT_TIMESTAMP"]
    params = [launch_status]
    if sample_ordered is not None:
        updates.append("sample_ordered = ?")
        params.append(1 if sample_ordered else 0)
    if sample_approved is not None:
        updates.append("sample_approved = ?")
        params.append(1 if sample_approved else 0)
    if qc_passed is not None:
        updates.append("compliance_checklist_passed = ?")
        params.append(1 if qc_passed else 0)
    if po_generated is not None:
        updates.append("purchase_order_generated = ?")
        params.append(1 if po_generated else 0)
    params.append(item_id)
    cur.execute(f"UPDATE launchpad_items SET {', '.join(updates)} WHERE item_id = ?", tuple(params))
    conn.commit()
    conn.close()
    return True

# ──────────────────────────────────────────────────────────────────────────────
# DEFECT CLUSTERS CRUD
# ──────────────────────────────────────────────────────────────────────────────

def record_defect_cluster(
    product_id: str,
    defect_category: str,
    defect_description: str,
    source_platform: str = "amazon",
    source_url: str = "",
    review_rating: float = 3.0,
    frequency_count: int = 1,
    severity: str = "MEDIUM",
    is_fixable: bool = True,
    v2_fix_description: str = "",
    v2_bom_delta_usd: float = 0.0
) -> int:
    """Records a clustered defect finding from review mining."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO defect_clusters (
            product_id, defect_category, defect_description, source_platform,
            source_url, review_rating, frequency_count, severity, is_fixable,
            v2_fix_description, v2_bom_delta_usd
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_id, defect_category, defect_description, source_platform,
        source_url, review_rating, frequency_count, severity,
        1 if is_fixable else 0, v2_fix_description, v2_bom_delta_usd
    ))
    cid = cur.lastrowid
    conn.commit()
    conn.close()
    return cid

def get_defect_clusters(product_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetches defect clusters, optionally filtered by product."""
    conn = get_connection()
    cur = conn.cursor()
    if product_id:
        cur.execute('''
            SELECT * FROM defect_clusters WHERE product_id = ?
            ORDER BY frequency_count DESC, severity DESC LIMIT ?
        ''', (product_id, limit))
    else:
        cur.execute('SELECT * FROM defect_clusters ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# ──────────────────────────────────────────────────────────────────────────────
# REVIEW SNAPSHOTS CRUD
# ──────────────────────────────────────────────────────────────────────────────

def record_review_snapshot(
    product_id: str,
    marketplace: str,
    rating: float,
    review_text: str,
    review_title: str = "",
    reviewer_name: str = "",
    review_date: str = "",
    helpful_votes: int = 0,
    verified_purchase: int = 0,
) -> int:
    """Records a single review snapshot for defect mining."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO review_snapshots (
            product_id, marketplace, rating, review_text, review_title,
            reviewer_name, review_date, helpful_votes, verified_purchase
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_id, marketplace, rating, review_text, review_title,
        reviewer_name, review_date, helpful_votes, verified_purchase
    ))
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid

def get_3star_reviews(product_id: str, marketplace: str = "amazon", limit: int = 20) -> List[str]:
    """Fetches 3-star review texts for a product (for Gate 2 defect mining)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT review_text FROM review_snapshots 
        WHERE product_id = ? AND marketplace = ? AND rating = 3.0
        ORDER BY helpful_votes DESC, scraped_at DESC LIMIT ?
    ''', (product_id, marketplace, limit))
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows if row[0]]

def get_review_snapshots(product_id: str, marketplace: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetches all review snapshots for a product."""
    conn = get_connection()
    cur = conn.cursor()
    if marketplace:
        cur.execute('''
            SELECT * FROM review_snapshots 
            WHERE product_id = ? AND marketplace = ?
            ORDER BY rating ASC, helpful_votes DESC LIMIT ?
        ''', (product_id, marketplace, limit))
    else:
        cur.execute('''
            SELECT * FROM review_snapshots 
            WHERE product_id = ?
            ORDER BY rating ASC, helpful_votes DESC LIMIT ?
        ''', (product_id, limit))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

# ──────────────────────────────────────────────────────────────────────────────
# ECONOMICS ASSESSMENTS CRUD
# ──────────────────────────────────────────────────────────────────────────────

def record_economics_assessment(
    product_id: str,
    scenario: str,
    msrp: float = 0.0,
    fob_cost: float = 0.0,
    packaging_cost: float = 0.0,
    volumetric_freight: float = 0.0,
    customs_duty: float = 0.0,
    marketplace_commission: float = 0.0,
    fulfillment_fee: float = 0.0,
    payment_gateway_fee: float = 0.0,
    rto_reserve: float = 0.0,
    return_fraud_reserve: float = 0.0,
    ad_spend_reserve: float = 0.0,
    damage_reserve: float = 0.0,
    tooling_amortization: float = 0.0,
    net_gst_burden: float = 0.0,
    contribution_margin: float = 0.0,
    contribution_margin_pct: float = 0.0,
    lead_time_pass: bool = True,
    overall_pass: bool = False,
    composite_score: float = 0.0
) -> int:
    """Records a single scenario economics assessment (CONSERVATIVE/EXPECTED/UPSIDE)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO economics_assessments (
            product_id, scenario, msrp, fob_cost, packaging_cost,
            volumetric_freight, customs_duty, marketplace_commission,
            fulfillment_fee, payment_gateway_fee, rto_reserve,
            return_fraud_reserve, ad_spend_reserve, damage_reserve,
            tooling_amortization, net_gst_burden, contribution_margin,
            contribution_margin_pct, lead_time_pass, overall_pass, composite_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        product_id, scenario, msrp, fob_cost, packaging_cost,
        volumetric_freight, customs_duty, marketplace_commission,
        fulfillment_fee, payment_gateway_fee, rto_reserve,
        return_fraud_reserve, ad_spend_reserve, damage_reserve,
        tooling_amortization, net_gst_burden, contribution_margin,
        contribution_margin_pct, 1 if lead_time_pass else 0,
        1 if overall_pass else 0, composite_score
    ))
    aid = cur.lastrowid
    conn.commit()
    conn.close()
    return aid

def get_economics_assessments(product_id: str) -> List[Dict[str, Any]]:
    """Fetches all 3-scenario economics assessments for a product."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT * FROM economics_assessments WHERE product_id = ?
        ORDER BY CASE scenario
            WHEN 'CONSERVATIVE' THEN 1
            WHEN 'EXPECTED' THEN 2
            WHEN 'UPSIDE' THEN 3
        END
    ''', (product_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def persist_full_economics_assessment(product_id: str, assessment_result: dict) -> None:
    """Persists a complete EconomicsAssessment (all 3 scenarios) from the 15-factor engine."""
    scenarios = assessment_result.get("scenarios", {})
    for scenario_name, scenario_data in scenarios.items():
        record_economics_assessment(
            product_id=product_id,
            scenario=scenario_name.upper(),
            msrp=scenario_data.get("msrp", 0.0),
            fob_cost=scenario_data.get("fob_cost", 0.0),
            packaging_cost=scenario_data.get("packaging_cost", 0.0),
            volumetric_freight=scenario_data.get("volumetric_freight", 0.0),
            customs_duty=scenario_data.get("customs_duty", 0.0),
            marketplace_commission=scenario_data.get("marketplace_commission", 0.0),
            fulfillment_fee=scenario_data.get("fulfillment_fee", 0.0),
            payment_gateway_fee=scenario_data.get("payment_gateway_fee", 0.0),
            rto_reserve=scenario_data.get("rto_reserve", 0.0),
            return_fraud_reserve=scenario_data.get("return_fraud_reserve", 0.0),
            ad_spend_reserve=scenario_data.get("ad_spend_reserve", 0.0),
            damage_reserve=scenario_data.get("damage_reserve", 0.0),
            tooling_amortization=scenario_data.get("tooling_amortization", 0.0),
            net_gst_burden=scenario_data.get("net_gst_burden", 0.0),
            contribution_margin=scenario_data.get("contribution_margin", 0.0),
            contribution_margin_pct=scenario_data.get("contribution_margin_pct", 0.0),
            lead_time_pass=assessment_result.get("lead_time_pass", True),
            overall_pass=assessment_result.get("financially_viable", False),
            composite_score=assessment_result.get("composite_score", 0.0)
        )


# ── LEARNED RULES CRUD ────────────────────────────────────────────────────────

def add_learned_rule(rule) -> Optional[int]:
    """Insert a learned rule. Returns rule_id."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO learned_rules (
                rule_id_str, name, description, condition, action,
                severity, params_json, enabled, tags_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            rule.rule_id,
            rule.name,
            rule.description,
            rule.condition,
            rule.action,
            rule.severity,
            json.dumps(rule.params) if rule.params else "{}",
            1 if rule.enabled else 0,
            json.dumps(rule.tags) if rule.tags else "[]",
        ))
        conn.commit()
        rule_id = cur.lastrowid
        conn.close()
        return rule_id
    except Exception as e:
        logger.warning(f"add_learned_rule error: {e}")
        conn.close()
        return None


def get_learned_rules(active_only: bool = True, limit: int = 100) -> List[Dict]:
    """Get learned rules, optionally filtered by enabled status."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM learned_rules WHERE 1=1"
    params = []
    if active_only:
        query += " AND enabled = 1"
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    # Parse JSON fields
    for row in rows:
        row['params'] = json.loads(row['params_json']) if row['params_json'] else {}
        row['tags'] = json.loads(row['tags_json']) if row['tags_json'] else []
    conn.close()
    return rows


def update_learned_rule(rule_id: int, **kwargs) -> bool:
    """Update a learned rule."""
    if not kwargs:
        return False
    conn = get_connection()
    cur = conn.cursor()
    try:
        set_clauses = []
        params = []
        for key, value in kwargs.items():
            if key in ('params', 'tags') and isinstance(value, (dict, list)):
                value = json.dumps(value)
            set_clauses.append(f"{key} = ?")
            params.append(value)
        params.append(rule_id)
        query = f"UPDATE learned_rules SET {', '.join(set_clauses)} WHERE rule_id = ?"
        cur.execute(query, params)
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        logger.warning(f"update_learned_rule error: {e}")
        conn.close()
        return False


# ── DISCOVERED SOURCES CRUD ──────────────────────────────────────────────────

def record_discovered_source(url: str, source_type: str = "trend", source_name: str = "",
                              description: str = "", region: str = "Global",
                              reliability_score: float = 70.0, discovered_by: str = "nim_discovery") -> Optional[int]:
    """Insert or update a discovered source URL. Returns source_id or None if duplicate."""
    conn = get_connection()
    cur = conn.cursor()
    domain = url.split("//")[-1].split("/")[0] if "//" in url else url.split("/")[0]
    try:
        cur.execute('''
            INSERT INTO discovered_sources (url, domain, source_type, source_name, description, region, reliability_score, discovered_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url, source_type) DO UPDATE SET
                reliability_score = MAX(discovered_sources.reliability_score, excluded.reliability_score),
                description = CASE WHEN excluded.description != '' THEN excluded.description ELSE discovered_sources.description END,
                is_active = 1
        ''', (url, domain, source_type, source_name, description, region, reliability_score, discovered_by))
        conn.commit()
        sid = cur.lastrowid
        conn.close()
        return sid
    except Exception as e:
        conn.close()
        return None


def get_discovered_sources(source_type: str = None, region: str = None, active_only: bool = True) -> List[Dict]:
    """Get discovered sources, optionally filtered by type and region."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM discovered_sources WHERE 1=1"
    params = []
    if active_only:
        query += " AND is_active = 1"
    if source_type:
        query += " AND source_type = ?"
        params.append(source_type)
    if region:
        query += " AND (region = ? OR region = 'Global')"
        params.append(region)
    query += " ORDER BY reliability_score DESC, times_yielded_results DESC"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_source_usage(source_id: int, yielded_results: bool = False):
    """Increment usage counter and optionally yield counter for a source."""
    conn = get_connection()
    cur = conn.cursor()
    if yielded_results:
        cur.execute("UPDATE discovered_sources SET times_used = times_used + 1, times_yielded_results = times_yielded_results + 1, last_crawled_at = CURRENT_TIMESTAMP WHERE source_id = ?", (source_id,))
    else:
        cur.execute("UPDATE discovered_sources SET times_used = times_used + 1, last_crawled_at = CURRENT_TIMESTAMP WHERE source_id = ?", (source_id,))
    conn.commit()
    conn.close()


# ── DYNAMIC NICHES CRUD ──────────────────────────────────────────────────────

def record_dynamic_niche(category: str, region: str = "India", search_limit: int = 3,
                          priority_score: float = 50.0, discovered_by: str = "nim_discovery",
                          source_signal: str = "") -> Optional[int]:
    """Insert a dynamic niche. Skips duplicates silently."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO dynamic_niches (category, region, search_limit, priority_score, discovered_by, source_signal)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(category, region) DO UPDATE SET
                priority_score = MAX(dynamic_niches.priority_score, excluded.priority_score),
                is_active = 1
        ''', (category, region, search_limit, priority_score, discovered_by, source_signal))
        conn.commit()
        nid = cur.lastrowid
        conn.close()
        return nid
    except Exception as e:
        conn.close()
        return None


def get_dynamic_niches(region: str = None, active_only: bool = True, limit: int = 200) -> List[Dict]:
    """Get dynamic niches, optionally filtered by region."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM dynamic_niches WHERE 1=1"
    params = []
    if active_only:
        query += " AND is_active = 1"
    if region:
        query += " AND region = ?"
        params.append(region)
    query += " ORDER BY priority_score DESC, products_found DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_niche_scan(niche_id: int, products_found: int = 0):
    """Update scan counter and products found for a niche."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""UPDATE dynamic_niches SET times_scanned = times_scanned + 1,
                   products_found = products_found + ?, last_scanned_at = CURRENT_TIMESTAMP
                   WHERE niche_id = ?""", (products_found, niche_id))
    conn.commit()
    conn.close()


# ── DYNAMIC SEED KEYWORDS CRUD ───────────────────────────────────────────────

def record_seed_keyword(keyword: str, region: str = "India", source_platform: str = "nim_generated",
                         parent_keyword: str = "", velocity_score: float = 50.0) -> Optional[int]:
    """Insert a dynamic seed keyword. Skips duplicates silently."""
    for attempt in range(5):
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute('''
                INSERT INTO dynamic_seed_keywords (keyword, region, source_platform, parent_keyword, velocity_score)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(keyword, region) DO UPDATE SET
                    velocity_score = MAX(dynamic_seed_keywords.velocity_score, excluded.velocity_score),
                    is_active = 1
            ''', (keyword, region, source_platform, parent_keyword, velocity_score))
            conn.commit()
            sid = cur.lastrowid
            conn.close()
            return sid
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                import time, random
                delay = 0.1 * (2 ** attempt) + random.uniform(0, 0.1)
                time.sleep(delay)
                continue
            return None
        except Exception:
            return None
    return None


def get_seed_keywords(region: str = "India", active_only: bool = True, limit: int = 50) -> List[Dict]:
    """Get dynamic seed keywords for a region."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM dynamic_seed_keywords WHERE region = ?"
    params = [region]
    if active_only:
        query += " AND is_active = 1"
    query += " ORDER BY velocity_score DESC, times_used ASC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_seed_usage(seed_id: int):
    """Increment usage counter for a seed keyword."""
    for attempt in range(5):
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("UPDATE dynamic_seed_keywords SET times_used = times_used + 1, last_used_at = CURRENT_TIMESTAMP WHERE seed_id = ?", (seed_id,))
            conn.commit()
            conn.close()
            return
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e).lower():
                import time, random
                delay = 0.1 * (2 ** attempt) + random.uniform(0, 0.1)
                time.sleep(delay)
                continue
            return
        except Exception:
            return


# ── UNIVERSAL MARKETPLACE SCRAPER CONFIG CRUD ───────────────────────────────────

def upsert_marketplace_config(config: dict) -> Optional[int]:
    """Insert or update a marketplace scraper configuration."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO marketplace_config (
                marketplace_name, region, base_url, search_url_pattern, search_param_name,
                pagination_type, pagination_param, max_pages, results_per_page,
                requires_js, anti_bot_level, login_required, login_url, cookie_domain,
                product_list_selector, product_title_selector, product_price_selector,
                product_rating_selector, product_review_count_selector, product_url_selector,
                product_image_selector, next_page_selector, custom_headers_json,
                extraction_prompt, is_active, priority
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(marketplace_name, region) DO UPDATE SET
                base_url=excluded.base_url,
                search_url_pattern=excluded.search_url_pattern,
                search_param_name=excluded.search_param_name,
                pagination_type=excluded.pagination_type,
                pagination_param=excluded.pagination_param,
                max_pages=excluded.max_pages,
                results_per_page=excluded.results_per_page,
                requires_js=excluded.requires_js,
                anti_bot_level=excluded.anti_bot_level,
                login_required=excluded.login_required,
                login_url=excluded.login_url,
                cookie_domain=excluded.cookie_domain,
                product_list_selector=excluded.product_list_selector,
                product_title_selector=excluded.product_title_selector,
                product_price_selector=excluded.product_price_selector,
                product_rating_selector=excluded.product_rating_selector,
                product_review_count_selector=excluded.product_review_count_selector,
                product_url_selector=excluded.product_url_selector,
                product_image_selector=excluded.product_image_selector,
                next_page_selector=excluded.next_page_selector,
                custom_headers_json=excluded.custom_headers_json,
                extraction_prompt=excluded.extraction_prompt,
                is_active=excluded.is_active,
                priority=excluded.priority,
                updated_at=CURRENT_TIMESTAMP
        ''', (
            config.get("marketplace_name"),
            config.get("region", "Global"),
            config.get("base_url"),
            config.get("search_url_pattern"),
            config.get("search_param_name", "q"),
            config.get("pagination_type", "page_param"),
            config.get("pagination_param", "page"),
            config.get("max_pages", 5),
            config.get("results_per_page", 20),
            config.get("requires_js", 1),
            config.get("anti_bot_level", "medium"),
            config.get("login_required", 0),
            config.get("login_url"),
            config.get("cookie_domain"),
            config.get("product_list_selector"),
            config.get("product_title_selector"),
            config.get("product_price_selector"),
            config.get("product_rating_selector"),
            config.get("product_review_count_selector"),
            config.get("product_url_selector"),
            config.get("product_image_selector"),
            config.get("next_page_selector"),
            config.get("custom_headers_json"),
            config.get("extraction_prompt"),
            config.get("is_active", 1),
            config.get("priority", 50)
        ))
        conn.commit()
        cid = cur.lastrowid
        conn.close()
        return cid
    except Exception as e:
        logger.warning(f"upsert_marketplace_config error: {e}")
        conn.close()
        return None


def get_marketplace_configs(region: str = None, active_only: bool = True) -> List[Dict]:
    """Get marketplace scraper configurations."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM marketplace_config WHERE 1=1"
    params = []
    if active_only:
        query += " AND is_active = 1"
    if region:
        query += " AND (region = ? OR region = 'Global')"
        params.append(region)
    query += " ORDER BY priority DESC, success_rate DESC"
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_marketplace_config(config_id: int) -> Optional[Dict]:
    """Get a single marketplace config by ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM marketplace_config WHERE config_id = ?", (config_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_marketplace_config_stats(config_id: int, success: bool):
    """Update success rate and last scraped timestamp."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE marketplace_config 
        SET success_rate = (success_rate * 0.9) + (? * 100 * 0.1),
            last_scraped_at = CURRENT_TIMESTAMP
        WHERE config_id = ?
    """, (1.0 if success else 0.0, config_id))
    conn.commit()
    conn.close()


# ── SCRAPED LISTINGS CRUD ──────────────────────────────────────────────────────

def record_scraped_listing(config_id: int, listing: dict) -> Optional[int]:
    """Store a scraped product listing."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO scraped_listings (
                config_id, product_id, marketplace, region, search_query,
                title, price, currency, original_price, discount_pct,
                rating, review_count, availability, product_url, image_url,
                seller_name, seller_rating, raw_data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            config_id,
            listing.get("product_id"),
            listing.get("marketplace"),
            listing.get("region"),
            listing.get("search_query"),
            listing.get("title"),
            listing.get("price"),
            listing.get("currency", "INR"),
            listing.get("original_price"),
            listing.get("discount_pct"),
            listing.get("rating"),
            listing.get("review_count", 0),
            listing.get("availability"),
            listing.get("product_url"),
            listing.get("image_url"),
            listing.get("seller_name"),
            listing.get("seller_rating"),
            json.dumps(listing.get("raw_data", {}), default=str)
        ))
        conn.commit()
        lid = cur.lastrowid
        conn.close()
        return lid
    except Exception as e:
        logger.warning(f"record_scraped_listing error: {e}")
        conn.close()
        return None


def get_scraped_listings(search_query: str = None, marketplace: str = None, region: str = None, limit: int = 100) -> List[Dict]:
    """Get scraped listings with optional filters."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM scraped_listings WHERE 1=1"
    params = []
    if search_query:
        query += " AND search_query = ?"
        params.append(search_query)
    if marketplace:
        query += " AND marketplace = ?"
        params.append(marketplace)
    if region:
        query += " AND region = ?"
        params.append(region)
    query += " ORDER BY extracted_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── SEED INITIAL MARKETPLACE CONFIGS ──────────────────────────────────────────

def seed_initial_marketplace_configs():
    """Bootstrap marketplace configurations for major platforms."""
    configs = [
        {
            "marketplace_name": "Amazon India",
            "region": "India",
            "base_url": "https://www.amazon.in",
            "search_url_pattern": "https://www.amazon.in/s",
            "search_param_name": "k",
            "pagination_type": "page_param",
            "pagination_param": "page",
            "max_pages": 3,
            "results_per_page": 24,
            "requires_js": 1,
            "anti_bot_level": "high",
            "login_required": 0,
            "product_list_selector": "[data-component-type='s-search-result']",
            "product_title_selector": "h2 a.a-link-normal span",
            "product_price_selector": ".a-price-whole",
            "product_rating_selector": "[aria-label*='stars']",
            "product_review_count_selector": "[aria-label*='reviews']",
            "product_url_selector": "h2 a.a-link-normal",
            "product_image_selector": ".s-image",
            "next_page_selector": ".s-pagination-next",
            "extraction_prompt": "Extract product title, price (INR), rating, review count, product URL, image URL, and availability from Amazon India search results.",
            "priority": 100
        },
        {
            "marketplace_name": "Flipkart",
            "region": "India",
            "base_url": "https://www.flipkart.com",
            "search_url_pattern": "https://www.flipkart.com/search",
            "search_param_name": "q",
            "pagination_type": "page_param",
            "pagination_param": "page",
            "max_pages": 3,
            "results_per_page": 24,
            "requires_js": 1,
            "anti_bot_level": "high",
            "login_required": 0,
            "product_list_selector": "[data-id]",
            "product_title_selector": "a[title]",
            "product_price_selector": "._30jeq3",
            "product_rating_selector": "._3LWZlK",
            "product_review_count_selector": "span:contains('reviews')",
            "product_url_selector": "a[title]",
            "product_image_selector": "img[src*='flipkart']",
            "next_page_selector": "a[aria-label='Next']",
            "extraction_prompt": "Extract product title, price (INR), rating, review count, product URL, image URL, and availability from Flipkart search results.",
            "priority": 95
        },
        {
            "marketplace_name": "Meesho",
            "region": "India",
            "base_url": "https://www.meesho.com",
            "search_url_pattern": "https://www.meesho.com/search",
            "search_param_name": "q",
            "pagination_type": "scroll",
            "pagination_param": "",
            "max_pages": 5,
            "results_per_page": 40,
            "requires_js": 1,
            "anti_bot_level": "high",
            "login_required": 0,
            "product_list_selector": "[data-testid='product-card']",
            "product_title_selector": "h3, [data-testid='product-title']",
            "product_price_selector": "[data-testid='price'], .sc-eDvSVe",
            "product_rating_selector": "[data-testid='rating']",
            "product_review_count_selector": "[data-testid='review-count']",
            "product_url_selector": "a[href*='/product/']",
            "product_image_selector": "img[src*='meesho']",
            "next_page_selector": "",
            "extraction_prompt": "Extract product title, price (INR), rating, review count, product URL, image URL, and availability from Meesho search results. Handle infinite scroll.",
            "priority": 90
        },
        {
            "marketplace_name": "Myntra",
            "region": "India",
            "base_url": "https://www.myntra.com",
            "search_url_pattern": "https://www.myntra.com/gateway/v2/search",
            "search_param_name": "q",
            "pagination_type": "api_offset",
            "pagination_param": "offset",
            "max_pages": 3,
            "results_per_page": 50,
            "requires_js": 1,
            "anti_bot_level": "high",
            "login_required": 0,
            "product_list_selector": ".product-base",
            "product_title_selector": ".product-brand, .product-product",
            "product_price_selector": ".product-discountedPrice, .product-strike",
            "product_rating_selector": ".product-ratingsContainer",
            "product_review_count_selector": ".product-ratingsCount",
            "product_url_selector": "a[href*='/buy/']",
            "product_image_selector": "img[src*='myntra']",
            "next_page_selector": "",
            "extraction_prompt": "Extract product title, price (INR), rating, review count, product URL, image URL, and availability from Myntra search results. Note: Myntra uses API-based search.",
            "priority": 85
        },
        {
            "marketplace_name": "Amazon US",
            "region": "USA",
            "base_url": "https://www.amazon.com",
            "search_url_pattern": "https://www.amazon.com/s",
            "search_param_name": "k",
            "pagination_type": "page_param",
            "pagination_param": "page",
            "max_pages": 3,
            "results_per_page": 24,
            "requires_js": 1,
            "anti_bot_level": "high",
            "login_required": 0,
            "product_list_selector": "[data-component-type='s-search-result']",
            "product_title_selector": "h2 a.a-link-normal span",
            "product_price_selector": ".a-price-whole",
            "product_rating_selector": "[aria-label*='stars']",
            "product_review_count_selector": "[aria-label*='reviews']",
            "product_url_selector": "h2 a.a-link-normal",
            "product_image_selector": ".s-image",
            "next_page_selector": ".s-pagination-next",
            "extraction_prompt": "Extract product title, price (USD), rating, review count, product URL, image URL, and availability from Amazon US search results.",
            "priority": 100
        },
        {
            "marketplace_name": "Shopify Generic",
            "region": "Global",
            "base_url": "",
            "search_url_pattern": "{base_url}/search",
            "search_param_name": "q",
            "pagination_type": "page_param",
            "pagination_param": "page",
            "max_pages": 3,
            "results_per_page": 20,
            "requires_js": 1,
            "anti_bot_level": "low",
            "login_required": 0,
            "product_list_selector": ".product-item, .grid-view-item, [data-product-id]",
            "product_title_selector": ".product-title, .grid-view-item__title, h3",
            "product_price_selector": ".price-item--regular, .product-price",
            "product_rating_selector": ".rating, .spr-badge",
            "product_review_count_selector": ".review-count, .spr-summary-count",
            "product_url_selector": "a[href*='/products/']",
            "product_image_selector": "img[src*='product']",
            "next_page_selector": ".pagination__next, a[rel='next']",
            "extraction_prompt": "Extract product title, price, currency, rating, review count, product URL, image URL, and availability from Shopify store search results. Adapt selectors to the specific theme.",
            "priority": 70
        }
    ]
    
    for config in configs:
        upsert_marketplace_config(config)
    
    import logging
    logging.getLogger("aprs.db").info("Marketplace configs seeded/updated")


# ── AI SUPERVISOR: SCRAPER VALIDATIONS ──────────────────────────────────────────

def record_scraper_validation(validation_data: dict) -> Optional[int]:
    """Record AI validation result for scraped product."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO scraper_validations (
                product_id, marketplace, region, is_valid, confidence,
                issues, auto_soft_delete, rejection_reason, rejection_category,
                ai_notes, ai_suggested_fix, raw_product_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            validation_data.get("product_id", ""),
            validation_data.get("marketplace", ""),
            validation_data.get("region", ""),
            1 if validation_data.get("is_valid", True) else 0,
            validation_data.get("confidence", 50.0),
            validation_data.get("issues", "[]"),
            1 if validation_data.get("auto_soft_delete", False) else 0,
            validation_data.get("rejection_reason", ""),
            validation_data.get("rejection_category", ""),
            validation_data.get("ai_notes", ""),
            validation_data.get("ai_suggested_fix", ""),
            validation_data.get("raw_product_data", "")
        ))
        conn.commit()
        vid = cur.lastrowid
        conn.close()
        return vid
    except Exception as e:
        conn.close()
        logger.warning(f"record_scraper_validation error: {e}")
        return None


def get_scraper_validations(product_id: str = None, marketplace: str = None, region: str = None, limit: int = 100) -> List[Dict]:
    """Get scraper validations with optional filters."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM scraper_validations WHERE 1=1"
    params = []
    if product_id:
        query += " AND product_id = ?"
        params.append(product_id)
    if marketplace:
        query += " AND marketplace = ?"
        params.append(marketplace)
    if region:
        query += " AND region = ?"
        params.append(region)
    query += " ORDER BY validated_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── AI SUPERVISOR LOGS ──────────────────────────────────────────────────────────

def record_ai_supervisor_log(log_data: dict) -> Optional[int]:
    """Record AI Supervisor activity log."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO ai_supervisor_logs (event_type, details, active_tasks, total_validations)
            VALUES (?, ?, ?, ?)
        ''', (
            log_data.get("event_type", ""),
            log_data.get("details", ""),
            log_data.get("active_tasks", 0),
            log_data.get("total_validations", 0)
        ))
        conn.commit()
        lid = cur.lastrowid
        conn.close()
        return lid
    except Exception as e:
        conn.close()
        return None


def get_ai_supervisor_logs(limit: int = 100) -> List[Dict]:
    """Get AI Supervisor activity logs."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ai_supervisor_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── AI TASK IMPROVEMENTS ────────────────────────────────────────────────────────

def record_ai_task_improvement(improvement_data: dict) -> Optional[int]:
    """Record AI-suggested task improvement."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO ai_task_improvements (
                task_id, task_type, marketplace, region, improvement_type,
                description, priority, target, triggered_by
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            improvement_data.get("task_id", ""),
            improvement_data.get("task_type", ""),
            improvement_data.get("marketplace", ""),
            improvement_data.get("region", ""),
            improvement_data.get("improvement_type", ""),
            improvement_data.get("description", ""),
            improvement_data.get("priority", "medium"),
            improvement_data.get("target", ""),
            improvement_data.get("triggered_by", "")
        ))
        conn.commit()
        iid = cur.lastrowid
        conn.close()
        return iid
    except Exception as e:
        conn.close()
        return None


def get_ai_task_improvements(limit: int = 100) -> List[Dict]:
    """Get AI task improvements history."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ai_task_improvements ORDER BY applied_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


if __name__ == "__main__":
    init_db()

# ── OUTREACH DRAFTS CRUD ────────────────────────────────────────────────────────

def add_outreach_draft(draft) -> Optional[int]:
    """Insert a new outreach draft. Returns draft_id."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO outreach_drafts (
                supplier_id, product_id, subject, body, channel, status,
                approved_by, approved_at, sent_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            draft.supplier_id,
            draft.product_id,
            draft.subject,
            draft.body,
            draft.channel.value if hasattr(draft.channel, 'value') else draft.channel,
            draft.status.value if hasattr(draft.status, 'value') else draft.status,
            draft.approved_by,
            draft.approved_at,
            draft.sent_at,
        ))
        conn.commit()
        draft_id = cur.lastrowid
        conn.close()
        return draft_id
    except Exception as e:
        logger.warning(f"add_outreach_draft error: {e}")
        conn.close()
        return None


def get_outreach_draft(draft_id: int):
    """Get a single outreach draft by ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM outreach_drafts WHERE draft_id = ?", (draft_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_pending_outreach_drafts(status: str = "APPROVED", limit: int = 50) -> List[Dict]:
    """Get outreach drafts with given status, ordered by creation date."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM outreach_drafts WHERE status = ? ORDER BY created_at ASC LIMIT ?",
        (status, limit)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_outreach_draft(draft_id: int, **kwargs) -> bool:
    """Update outreach draft fields."""
    if not kwargs:
        return False
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Build dynamic update query
        set_clauses = []
        params = []
        for key, value in kwargs.items():
            if hasattr(value, 'value'):  # Handle enums
                value = value.value
            set_clauses.append(f"{key} = ?")
            params.append(value)
        
        params.append(draft_id)
        query = f"UPDATE outreach_drafts SET {', '.join(set_clauses)} WHERE draft_id = ?"
        cur.execute(query, params)
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        logger.warning(f"update_outreach_draft error: {e}")
        conn.close()
        return False


# ── SUPPLIER PROFILES CRUD ────────────────────────────────────────────────────

def add_supplier_profile(profile) -> Optional[int]:
    """Insert a new supplier profile. Returns supplier_id."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO supplier_profiles (
                product_id, company_name, platform, profile_url,
                contact_phone, contact_email, gst_number, moq_estimate,
                verification_badge, product_categories, location,
                gst_verified, gst_check_date, verification_score, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            profile.product_id,
            profile.company_name,
            profile.platform,
            profile.profile_url,
            profile.contact_phone,
            profile.contact_email,
            profile.gst_number,
            profile.moq_estimate,
            1 if profile.verification_badge else 0,
            profile.product_categories,
            profile.location,
            1 if profile.gst_verified else 0,
            profile.gst_check_date,
            profile.verification_score,
            profile.status.value if hasattr(profile.status, 'value') else profile.status,
        ))
        conn.commit()
        supplier_id = cur.lastrowid
        conn.close()
        return supplier_id
    except Exception as e:
        logger.warning(f"add_supplier_profile error: {e}")
        conn.close()
        return None


def get_supplier_profile(supplier_id: int):
    """Get a single supplier profile by ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM supplier_profiles WHERE supplier_id = ?", (supplier_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_supplier_profiles_for_product(product_id: str) -> List[Dict]:
    """Get all supplier profiles for a product."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM supplier_profiles WHERE product_id = ? ORDER BY verification_score DESC", (product_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_supplier_profile(supplier_id: int, **kwargs) -> bool:
    """Update supplier profile fields."""
    if not kwargs:
        return False
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        set_clauses = []
        params = []
        for key, value in kwargs.items():
            if hasattr(value, 'value'):  # Handle enums
                value = value.value
            if key == 'verification_badge' or key == 'gst_verified':
                value = 1 if value else 0
            set_clauses.append(f"{key} = ?")
            params.append(value)
        
        params.append(supplier_id)
        query = f"UPDATE supplier_profiles SET {', '.join(set_clauses)} WHERE supplier_id = ?"
        cur.execute(query, params)
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        logger.warning(f"update_supplier_profile error: {e}")
        conn.close()
        return False


# ── OUTREACH CONVERSATIONS CRUD ──────────────────────────────────────────────

def add_supplier_conversation(
    supplier_id: int,
    channel: str,
    direction: str,
    message_text: str,
    message_id: str = None,
) -> Optional[int]:
    """Log a conversation message with a supplier."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO supplier_conversations (
                supplier_id, channel, direction, message_text, message_id
            ) VALUES (?, ?, ?, ?, ?)
        ''', (supplier_id, channel, direction, message_text, message_id))
        conn.commit()
        cid = cur.lastrowid
        conn.close()
        return cid
    except Exception as e:
        logger.warning(f"add_supplier_conversation error: {e}")
        conn.close()
        return None


def get_supplier_conversations(supplier_id: int, limit: int = 50) -> List[Dict]:
    """Get conversation history for a supplier."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM supplier_conversations WHERE supplier_id = ? ORDER BY received_at DESC LIMIT ?",
        (supplier_id, limit)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── PROBLEM OPPORTUNITIES CRUD ────────────────────────────────────────────────

def add_problem_opportunity(
    product_id: str,
    source: str,
    source_url: str = "",
    problem_text: str = "",
    problem_category: str = "other",
    severity: str = "minor",
    frequency_estimate: int = 1,
    suggested_solution: str = "",
    market_size_estimate: str = "",
    competitor_solution: str = "",
    status: str = "IDENTIFIED",
) -> Optional[int]:
    """Insert a new problem opportunity. Returns opportunity_id."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO problem_opportunities (
                product_id, source, source_url, problem_text,
                problem_category, severity, frequency_estimate,
                suggested_solution, market_size_estimate,
                competitor_solution, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            product_id, source, source_url, problem_text,
            problem_category, severity, frequency_estimate,
            suggested_solution, market_size_estimate,
            competitor_solution, status
        ))
        conn.commit()
        oid = cur.lastrowid
        conn.close()
        return oid
    except Exception as e:
        logger.warning(f"add_problem_opportunity error: {e}")
        conn.close()
        return None


def get_problem_opportunities(product_id: str) -> List[Dict]:
    """Get all problem opportunities for a product."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM problem_opportunities WHERE product_id = ? ORDER BY created_at DESC", (product_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_problem_opportunity(opportunity_id: int, **kwargs) -> bool:
    """Update a problem opportunity."""
    if not kwargs:
        return False
    conn = get_connection()
    cur = conn.cursor()
    try:
        set_clauses = []
        params = []
        for key, value in kwargs.items():
            set_clauses.append(f"{key} = ?")
            params.append(value)
        params.append(opportunity_id)
        query = f"UPDATE problem_opportunities SET {', '.join(set_clauses)} WHERE opportunity_id = ?"
        cur.execute(query, params)
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        logger.warning(f"update_problem_opportunity error: {e}")
        conn.close()
        return False


def get_all_problem_opportunities(limit: int = 100, status: str = None) -> List[Dict]:
    """Get all problem opportunities, optionally filtered by status."""
    conn = get_connection()
    cur = conn.cursor()
    query = "SELECT * FROM problem_opportunities WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── PENDING HUMAN DECISIONS CRUD ──────────────────────────────────────────────

async def record_pending_decision(
    agent_name: str,
    task_type: str,
    context: List[Dict],
    options: List[Dict],
    priority: int = 1,
) -> str:
    """Record a task waiting for human decision. Returns decision_id."""
    import uuid
    import json
    from datetime import timedelta
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        decision_id = str(uuid.uuid4())[:8]
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        
        cur.execute('''
            INSERT INTO pending_human_decisions (
                decision_id, agent_name, task_type, context_json, options_json,
                priority, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            decision_id,
            agent_name,
            task_type,
            json.dumps(context, default=str),
            json.dumps(options, default=str),
            priority,
            expires_at,
        ))
        conn.commit()
        conn.close()
        return decision_id
    except Exception as e:
        logger.warning(f"record_pending_decision error: {e}")
        conn.close()
        return ""


def get_pending_decisions(status: str = "PENDING", limit: int = 50) -> List[Dict]:
    """Get pending human decisions."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM pending_human_decisions WHERE status = ? ORDER BY created_at DESC LIMIT ?",
        (status, limit)
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── LLM TIER LOG ──────────────────────────────────────────────────────────────

def log_llm_tier_usage(log_data: dict) -> Optional[int]:
    """Record which LLM tier was used for an agent call."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO llm_tier_log (
                agent_name, tier_used, tier_name, model_name, task_type,
                success, latency_ms, tokens_used, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            log_data.get("agent_name", ""),
            log_data.get("tier_used", 0),
            log_data.get("tier_name", ""),
            log_data.get("model_name", ""),
            log_data.get("task_type", ""),
            1 if log_data.get("success", True) else 0,
            log_data.get("latency_ms", 0),
            log_data.get("tokens_used", 0),
            log_data.get("error", ""),
        ))
        conn.commit()
        lid = cur.lastrowid
        conn.close()
        return lid
    except Exception as e:
        logger.warning(f"log_llm_tier_usage error: {e}")
        conn.close()
        return None


def get_llm_tier_stats(limit: int = 100) -> List[Dict]:
    """Get LLM tier usage statistics."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM llm_tier_log ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── LIVE TABLE COUNTS FOR DASHBOARD ────────────────────────────────────────────

def get_live_table_counts() -> Dict[str, int]:
    """Returns row counts for all tables — used by live dashboard header."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all table names
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cur.fetchall()]
    
    counts = {}
    for table in tables:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cur.fetchone()[0]
        except Exception:
            counts[table] = 0
    
    conn.close()
    return counts


# ── ENHANCED HUMAN OVERRIDE WITH REASON ────────────────────────────────────────

def set_human_override_with_reason(product_id: str, verdict: str, reason: str, overridden_by: str = "human") -> bool:
    """Allows human user to override algorithmic verdicts with reasoning AND sync all gates."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Update master_products
        cur.execute('''
            UPDATE master_products
            SET human_override_status = ?, status = ?, ai_rejection_reason = ?, updated_at = CURRENT_TIMESTAMP
            WHERE product_id = ?
        ''', (verdict, verdict, reason, product_id))
        
        # Override all gates to PASS or FAIL
        gate_status = "OVERRIDDEN_PASS" if verdict in ("PASS", "OVERRIDDEN_PASS") else "OVERRIDDEN_REJECT"
        for g in range(1, 7):
            cur.execute('''
                UPDATE product_gate_progress
                SET status = ?, blocked_reason = ?, completed_by = ?, completed_at = CURRENT_TIMESTAMP
                WHERE product_id = ? AND gate_number = ?
            ''', (gate_status, reason, overridden_by, product_id, g))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[DB Override Error]: {e}")
        return False


# ── OUTREACH DRAFTS FOR PRODUCT ────────────────────────────────────────────────

def get_outreach_drafts_for_product(product_id: str) -> List[Dict]:
    """Get all outreach drafts for a product (join via supplier)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('''
        SELECT od.*, sp.company_name, sp.supplier_id
        FROM outreach_drafts od
        JOIN supplier_profiles sp ON od.supplier_id = sp.supplier_id
        WHERE sp.product_id = ?
        ORDER BY od.created_at DESC
    ''', (product_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def update_outreach_status(draft_id: int, status: str, edited_text: str = None) -> bool:
    """Update outreach draft status (PENDING, APPROVED, REJECTED, SENT, HOLD)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        if edited_text is not None:
            cur.execute('''
                UPDATE outreach_drafts
                SET status = ?, email_draft = ?, updated_at = CURRENT_TIMESTAMP
                WHERE draft_id = ?
            ''', (status, edited_text, draft_id))
        else:
            cur.execute('''
                UPDATE outreach_drafts
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE draft_id = ?
            ''', (status, draft_id))
        
        conn.commit()
        success = cur.rowcount > 0
        conn.close()
        return success
    except Exception as e:
        logger.warning(f"update_outreach_status error: {e}")
        return False


# ── ARCHIVE / SOFT-DELETED PRODUCTS ────────────────────────────────────────────

def get_archive_products(include_restored: bool = False) -> List[Dict]:
    """Get all soft-deleted products with AI reasoning for recovery review."""
    conn = get_connection()
    cur = conn.cursor()
    
    if include_restored:
        cur.execute('''
            SELECT product_id, name, category, region, planned_msrp, net_profit_pct,
                   is_deleted, deletion_reason, ai_rejection_reason, ai_reasoning,
                   ai_rejection_category, ai_confidence, updated_at, deleted_at
            FROM master_products
            WHERE is_deleted = 1
            ORDER BY deleted_at DESC
        ''')
    else:
        cur.execute('''
            SELECT product_id, name, category, region, planned_msrp, net_profit_pct,
                   is_deleted, deletion_reason, ai_rejection_reason, ai_reasoning,
                   ai_rejection_category, ai_confidence, updated_at, deleted_at
            FROM master_products
            WHERE is_deleted = 1
            ORDER BY deleted_at DESC
        ''')
    
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ── SWARM AUDIT LOG FOR AGENT COCKPIT ──────────────────────────────────────────

def get_recent_swarm_audit_log(limit: int = 50, agent_name: str = None) -> List[Dict]:
    """Get recent swarm audit log entries for live agent activity feed."""
    conn = get_connection()
    cur = conn.cursor()
    
    if agent_name:
        cur.execute(
            "SELECT * FROM swarm_audit_log WHERE agent_role = ? ORDER BY timestamp DESC LIMIT ?",
            (agent_name, limit)
        )
    else:
        cur.execute(
            "SELECT * FROM swarm_audit_log ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
    
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# PENDING HUMAN DECISIONS CRUD
# ──────────────────────────────────────────────────────────────────────────────

def add_pending_human_decision(
    agent_name: str,
    product_id: str,
    task_type: str,
    context_json: str,
    options_json: str,
    priority: str = "NORMAL",
    expires_in_hours: int = 24,
) -> int:
    """Add a decision requiring human input."""
    import json
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO pending_human_decisions (
            agent_name, product_id, task_type, context_json, options_json,
            priority, expires_at, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', ?), 'PENDING', datetime('now'))
    ''', (
        agent_name, product_id, task_type, context_json, options_json,
        priority, f'+{expires_in_hours} hours'
    ))
    
    did = cur.lastrowid
    conn.commit()
    conn.close()
    return did


def get_pending_human_decisions(
    agent_name: str = None,
    status: str = "PENDING",
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get pending human decisions."""
    conn = get_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM pending_human_decisions WHERE status = ?"
    params = [status]
    
    if agent_name:
        query += " AND agent_name = ?"
        params.append(agent_name)
    
    query += " ORDER BY priority DESC, created_at ASC LIMIT ?"
    params.append(limit)
    
    cur.execute(query, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def resolve_pending_human_decision(
    decision_id: int,
    decision: str,
    decided_by: str,
    notes: str = ""
) -> bool:
    """Resolve a pending human decision."""
    import json
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE pending_human_decisions
        SET decision = ?, decided_by = ?, decided_at = datetime('now'),
            status = 'RESOLVED', updated_at = datetime('now')
        WHERE decision_id = ?
    ''', (decision, decided_by, decision_id))
    
    conn.commit()
    conn.close()
    return True


# ──────────────────────────────────────────────────────────────────────────────
# SWARM AUDIT LOG
# ──────────────────────────────────────────────────────────────────────────────

def log_swarm_audit(agent_name: str, action: str, details: str = None, 
                    product_id: str = None, cycle_num: int = None, 
                    items_processed: int = 0, items_created: int = 0,
                    duration_ms: int = 0, success: bool = True) -> Optional[int]:
    """Log an agent execution event to swarm_audit_log for live telemetry."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO swarm_audit_log (
                agent_name, action, details, product_id, cycle_num,
                items_processed, items_created, duration_ms, success
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            agent_name, action, details, product_id, cycle_num,
            items_processed, items_created, duration_ms, 1 if success else 0
        ))
        conn.commit()
        lid = cur.lastrowid
        conn.close()
        return lid
    except Exception as e:
        logger.warning(f"log_swarm_audit error: {e}")
        conn.close()
        return None


if __name__ == "__main__":
    init_db()
    seed_initial_marketplace_configs()
    print("[SUCCESS] SQLite database initialized with schema migrations and meeting audit log!")