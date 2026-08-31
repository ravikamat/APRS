"""
web/app.py — APRS V6 Pro — Autonomous E-Commerce Intelligence Platform
Full Streamlit Dashboard with 8 tabs + Archive.
"""
import os
import sys
import time
import json
import datetime
import logging
import pandas as pd
import streamlit as st
from pathlib import Path
from typing import Optional

# ── Project root on sys.path ─────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Core imports ──────────────────────────────────────────────────────────────
from core.database import (
    init_db, get_connection, get_all_products, get_all_table_names, get_table_data,
    toggle_shortlist, get_shortlisted_products, soft_delete_product, restore_product,
    set_human_override, log_meeting_turn, get_meeting_history,
    get_gate_status, update_gate_status, get_current_gate, get_products_stuck_at_gate,
    add_to_launchpad, get_launchpad_items, update_launchpad_status,
    get_defect_clusters, get_economics_assessments,
    get_active_trend_signals, get_swarm_audit_logs,
    get_dynamic_niches, get_seed_keywords, get_discovered_sources,
    get_scraped_listings,
)
from core.economics_engine import Comprehensive15FactorEconomics
from core.background_daemon import daemon_controller
from models.nim_cluster import SupremeNIMCluster
from tools.ai_supervisor import get_supervisor

logger = logging.getLogger("aprs.webapp")

# ── Init DB ───────────────────────────────────────────────────────────────────
init_db()

# ── Helper: safe multi-platform listings fetch ────────────────────────────────
def _get_mpl(product_id: str) -> list:
    """Fetch multi-platform listings for a product from multi_platform_listings table."""
    try:
        conn = get_connection()
        cur = conn.execute(
            "SELECT * FROM multi_platform_listings WHERE product_id=? ORDER BY platform",
            (product_id,)
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []

# ── Helper: currency formatter ────────────────────────────────────────────────
def format_currency(val: float, region: str = "India") -> str:
    if region in ("India", "IN"):
        return f"₹{val:,.0f}"
    elif region in ("USA", "US"):
        return f"${val:,.2f}"
    elif region in ("UK", "GB"):
        return f"£{val:,.2f}"
    else:
        return f"{val:,.2f}"

# ── Helper: Word doc generator ────────────────────────────────────────────────
DOCX_FILE_PATH = str(_ROOT / "data" / "aprs_war_room.docx")

def generate_meeting_word_doc():
    try:
        from docx import Document
        history = get_meeting_history(limit=200)
        doc = Document()
        doc.add_heading("APRS V6 War Room — Meeting Minutes", level=1)
        doc.add_paragraph(f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        doc.add_paragraph("")
        for entry in history:
            doc.add_heading(f"{entry.get('speaker_name','?')} [{entry.get('timestamp','')}]", level=2)
            doc.add_paragraph(f"User: {entry.get('user_prompt','')}")
            doc.add_paragraph(f"Response: {entry.get('response_text','')}")
            doc.add_paragraph("")
        Path(DOCX_FILE_PATH).parent.mkdir(parents=True, exist_ok=True)
        doc.save(DOCX_FILE_PATH)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Word doc generation failed: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="APRS V6 — Autonomous E-Commerce Swarm",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background: #F8FAFC; }
    .block-container { padding-top: 0.7rem !important; }
    .metric-card { background:#FFFFFF; border-radius:10px; padding:14px 18px; border:1px solid #E2E8F0; margin-bottom:8px; }
    .gate-badge { display:inline-block; padding:2px 10px; border-radius:12px; font-size:0.78rem; font-weight:700; margin:2px; }
    .badge-pass { background:#D1FAE5; color:#065F46; }
    .badge-fail { background:#FEE2E2; color:#991B1B; }
    .badge-pending { background:#E2E8F0; color:#475569; }
    .badge-blocked { background:#FEF3C7; color:#92400E; }
    .badge-progress { background:#DBEAFE; color:#1E40AF; }
    .agent-sales { border-left: 4px solid #0284C7; background:#EFF6FF; padding:10px 14px; border-radius:0 8px 8px 0; margin:6px 0; }
    .agent-quality { border-left: 4px solid #DC2626; background:#FFF1F2; padding:10px 14px; border-radius:0 8px 8px 0; margin:6px 0; }
    .agent-supplier { border-left: 4px solid #D97706; background:#FFFBEB; padding:10px 14px; border-radius:0 8px 8px 0; margin:6px 0; }
    .agent-finance { border-left: 4px solid #4F46E5; background:#EEF2FF; padding:10px 14px; border-radius:0 8px 8px 0; margin:6px 0; }
    .agent-tech { border-left: 4px solid #0D9488; background:#F0FDFA; padding:10px 14px; border-radius:0 8px 8px 0; margin:6px 0; }
    .agent-secretary { border-left: 4px solid #059669; background:#ECFDF5; padding:10px 14px; border-radius:0 8px 8px 0; margin:6px 0; }
    .member-pill { display:inline-block; padding:3px 10px; border-radius:12px; font-size:0.82rem; font-weight:600; margin-right:6px; }
    .aprs-navbar {
        background:#0F172A; border-bottom:2px solid #1E3A8A; padding:10px 20px;
        margin-bottom:12px; border-radius:8px; display:flex; align-items:center;
        justify-content:space-between; flex-wrap:wrap; gap:10px;
    }
    .aprs-nav-brand { font-size:1.15rem; font-weight:800; color:#F8FAFC; letter-spacing:0.03em; }
    .aprs-blinker {
        display:inline-flex; align-items:center; gap:6px; font-size:0.82rem;
        font-weight:600; padding:3px 10px; border-radius:20px;
        background:#1E293B; border:1px solid #334155; color:#E2E8F0;
    }
    .aprs-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
    .dot-pulse { box-shadow:0 0 0 0 rgba(34,197,94,0.7); animation:aprs-pulse 2s infinite; }
    @keyframes aprs-pulse {
        0%   { box-shadow: 0 0 0 0 rgba(34,197,94,0.7); }
        70%  { box-shadow: 0 0 0 6px rgba(34,197,94,0); }
        100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
    }
    .aprs-nim-keys { font-size:0.75rem; color:#94A3B8; font-family:monospace; }
</style>
""", unsafe_allow_html=True)

# ── Background Daemon Setup ───────────────────────────────────────────────────
if "daemon_started" not in st.session_state:
    daemon_controller.start()
    st.session_state["daemon_started"] = True
daemon_status = daemon_controller.get_status()

# ── AI Supervisor: Start monitoring at app boot ───────────────────────────────
try:
    from tools.ai_supervisor import get_supervisor, ensure_supervisor_tables
    ensure_supervisor_tables()
    _supervisor = get_supervisor()
    _supervisor.start_monitoring()
    _sup_status = _supervisor.get_status()
except Exception as _se:
    _supervisor = None
    _sup_status = {"supervision_active": False, "active_tasks": 0, "completed_tasks": 0,
                   "total_validations": 0, "total_improvements": 0, "monitoring_active": False}

# ── NIM Cluster Status ────────────────────────────────────────────────────────
nim_cluster = SupremeNIMCluster()
cluster_status = nim_cluster.get_cluster_status()
nim_ok = len(cluster_status) > 0 and any(s.get("key_preview", "").startswith("nvapi") or len(s.get("key_preview","")) > 5 for s in cluster_status)
# Better online check: key exists in env
_k1 = os.getenv("NIM_API_KEY_1", "")
nim_ok = bool(_k1 and _k1.startswith("nvapi-"))
nim_calls_total = sum(s.get("calls", 0) for s in cluster_status)

daemon_ok       = not daemon_status["is_paused"]
_nim_dot_color  = "#22C55E" if nim_ok else "#EF4444"
_nim_label      = "AI Swarm Online" if nim_ok else "AI Swarm Offline"
_daemon_dot     = "#22C55E" if daemon_ok else "#F59E0B"
_daemon_running = "ACTIVE" if daemon_ok else "PAUSED"
_daemon_skus    = daemon_status["total_discovered_session"]
_daemon_niches  = f"{daemon_status['niche_index']}/{daemon_status['total_niches']}"
_sup_dot        = "#22C55E" if _sup_status.get("monitoring_active") else "#94A3B8"
_sup_label      = f"Supervisor Active • {_sup_status.get('total_validations', 0)} validated"
_key_preview    = "&nbsp;|&nbsp;".join(
    f"K{i+1}:{s['key_preview'][:8]}&#8230; ({s['calls']})"
    for i, s in enumerate(cluster_status)
) if cluster_status else "No keys configured"

st.markdown(f"""
<div class="aprs-navbar">
    <div class="aprs-nav-brand">&#9889; APRS V6 — Autonomous E-Commerce Swarm</div>
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
        <span class="aprs-blinker">
            <span class="aprs-dot dot-pulse" style="background:{_nim_dot_color};"></span>
            {_nim_label} &nbsp;&middot;&nbsp; {nim_calls_total} calls
        </span>
        <span class="aprs-blinker">
            <span class="aprs-dot dot-pulse" style="background:{_daemon_dot};"></span>
            Scraper {_daemon_running} &nbsp;&middot;&nbsp; {_daemon_skus} SKUs &nbsp;&middot;&nbsp; {_daemon_niches} niches
        </span>
        <span class="aprs-blinker">
            <span class="aprs-dot dot-pulse" style="background:{_sup_dot};"></span>
            🧠 {_sup_label}
        </span>
        <span class="aprs-nim-keys">{_key_preview}</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar: AI Key Manager ───────────────────────────────────────────────────
with st.sidebar:
    st.header("⚡ System Controls")

    with st.expander("🔑 NVIDIA NIM API Configuration", expanded=(not nim_ok)):
        st.caption("Enter your NVIDIA NIM API keys (`nvapi-...`). Supports automatic multi-key failover.")
        k1_input = st.text_input("NIM Key #1", value=os.getenv("NIM_API_KEY_1", ""), type="password", help="Primary key for Nemotron 120B / 30B")
        k2_input = st.text_input("NIM Key #2 (Optional)", value=os.getenv("NIM_API_KEY_2", ""), type="password", help="Secondary failover key")
        k3_input = st.text_input("NIM Key #3 (Optional)", value=os.getenv("NIM_API_KEY_3", ""), type="password", help="Tertiary failover key")

        if st.button("💾 Save & Connect AI Swarm", type="primary", use_container_width=True, key="btn_save_nim_keys"):
            env_file = _ROOT / ".env"
            if k1_input.strip():
                os.environ["NIM_API_KEY_1"] = k1_input.strip()
            if k2_input.strip():
                os.environ["NIM_API_KEY_2"] = k2_input.strip()
            if k3_input.strip():
                os.environ["NIM_API_KEY_3"] = k3_input.strip()
            if env_file.exists():
                lines = env_file.read_text(encoding="utf-8").splitlines()
                new_lines = []
                key_set = set()
                for line in lines:
                    if line.startswith("NIM_API_KEY_1="):
                        new_lines.append(f"NIM_API_KEY_1={k1_input.strip()}")
                        key_set.add("NIM_API_KEY_1")
                    elif line.startswith("NIM_API_KEY_2="):
                        new_lines.append(f"NIM_API_KEY_2={k2_input.strip()}")
                        key_set.add("NIM_API_KEY_2")
                    elif line.startswith("NIM_API_KEY_3="):
                        new_lines.append(f"NIM_API_KEY_3={k3_input.strip()}")
                        key_set.add("NIM_API_KEY_3")
                    else:
                        new_lines.append(line)
                if "NIM_API_KEY_1" not in key_set and k1_input.strip():
                    new_lines.append(f"NIM_API_KEY_1={k1_input.strip()}")
                env_file.write_text("\n".join(new_lines), encoding="utf-8")
            else:
                lines_to_write = [f"NIM_API_KEY_1={k1_input.strip()}"]
                if k2_input.strip():
                    lines_to_write.append(f"NIM_API_KEY_2={k2_input.strip()}")
                if k3_input.strip():
                    lines_to_write.append(f"NIM_API_KEY_3={k3_input.strip()}")
                env_file.write_text("\n".join(lines_to_write), encoding="utf-8")
            st.success("Keys saved! Reconnecting swarm...")
            time.sleep(0.4)
            st.rerun()

    st.divider()
    st.markdown("### 🤖 Active Swarm Models")
    st.markdown("- **Lead Arbiter (120B)**: `nvidia/nemotron-3-super-120b-a12b`")
    st.markdown("- **Fast Scout (30B)**: `nvidia/nemotron-3-nano-30b-a3b`")
    st.markdown("- **Vision Agent**: `meta/llama-3.2-90b-vision-instruct`")

    st.divider()
    st.markdown("### 🧠 AI Supervisor Status")
    _col1, _col2 = st.columns(2)
    with _col1:
        st.metric("✅ Validated", _sup_status.get("total_validations", 0))
        st.metric("🔄 Active Tasks", _sup_status.get("active_tasks", 0))
    with _col2:
        st.metric("📋 Completed", _sup_status.get("completed_tasks", 0))
        st.metric("🔧 Improvements", _sup_status.get("total_improvements", 0))
    _mon_color = "🟢" if _sup_status.get("monitoring_active") else "🔴"
    st.caption(f"{_mon_color} Monitoring: {'Active' if _sup_status.get('monitoring_active') else 'Offline'}")

    st.divider()
    st.markdown("### 📊 Live DB Stats")
    try:
        conn = get_connection()
        for tbl in ["master_products", "trend_signals", "product_gate_progress"]:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
            st.metric(tbl.replace("_", " ").title(), cnt)
        # AI supervisor tables
        for tbl in ["scraper_validations", "ai_supervisor_logs"]:
            try:
                cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                st.metric(tbl.replace("_", " ").title(), cnt)
            except Exception:
                pass
        conn.close()
    except Exception:
        st.caption("DB unavailable")

# ── Session State ─────────────────────────────────────────────────────────────
if "active_tab" not in st.session_state:
    st.session_state["active_tab"] = "opps"
if "last_seen_skus" not in st.session_state:
    st.session_state["last_seen_skus"] = daemon_status["total_discovered_session"]

# ── New SKU Notification Banner ───────────────────────────────────────────────
new_skus = max(0, daemon_status["total_discovered_session"] - st.session_state["last_seen_skus"])
if new_skus > 0:
    nc1, nc2 = st.columns([4, 1])
    with nc1:
        st.info(f"🔔 **Swarm Discovery:** **{new_skus}** new high-velocity opportunities found in background!")
    with nc2:
        if st.button("🔄 Update List", key="btn_update_notif", type="primary", use_container_width=True):
            st.session_state["last_seen_skus"] = daemon_status["total_discovered_session"]
            st.cache_data.clear()
            st.rerun()

# ── Tab Navigation ────────────────────────────────────────────────────────────
NAV_TABS = [
    ("opps",        "📋 Opportunities"),
    ("launchpad",   "🚀 Launchpad"),
    ("meeting",     "🎙️ War Room"),
    ("keepa",       "📈 Keepa / BSR"),
    ("supplier",    "🏭 Suppliers"),
    ("econ",        "📊 Economics"),
    ("date",        "📅 Date Logic"),
    ("db_explorer", "🗄️ SSOT DB"),
    ("archive",     "🗃️ Archive"),
]

tab_cols = st.columns(len(NAV_TABS))
for col, (tab_key, tab_label) in zip(tab_cols, NAV_TABS):
    with col:
        is_active = st.session_state["active_tab"] == tab_key
        if st.button(tab_label, key=f"nav_{tab_key}",
                     type="primary" if is_active else "secondary",
                     use_container_width=True):
            st.session_state["active_tab"] = tab_key
            st.rerun()

st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] button[kind="primary"] {
    background:#2563EB !important; color:white !important;
    border-bottom:3px solid #60A5FA !important; border-radius:6px 6px 0 0 !important;
}
div[data-testid="stHorizontalBlock"] button[kind="secondary"] {
    background:#F1F5F9 !important; color:#475569 !important;
    border-bottom:3px solid transparent !important; border-radius:6px 6px 0 0 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Daemon Controls ───────────────────────────────────────────────────────────
d_col1, d_col2, d_col3 = st.columns([2, 1, 1])
with d_col1:
    st.caption(f"🔄 Scanning: `{daemon_status['current_niche']}` — {daemon_status['total_discovered_session']} SKUs evaluated")
with d_col2:
    if daemon_status["is_paused"]:
        if st.button("▶️ Resume Daemon", key="btn_resume_daemon", use_container_width=True):
            daemon_controller.resume(); st.rerun()
    else:
        if st.button("⏸️ Pause Daemon", key="btn_pause_daemon", use_container_width=True):
            daemon_controller.pause(); st.rerun()
with d_col3:
    with st.popover("📜 Scraper Log"):
        for entry in daemon_status["recent_logs"]:
            st.caption(entry)

st.markdown("---")

# ── Cached Product Fetch ──────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def fetch_cached_products(include_deleted=True):
    return get_all_products(include_deleted=include_deleted)

products = fetch_cached_products(include_deleted=True)

# ── Tab routing ───────────────────────────────────────────────────────────────
_active = st.session_state["active_tab"]
tab_opps        = _active == "opps"
tab_launchpad   = _active == "launchpad"
tab_meeting     = _active == "meeting"
tab_h10_keepa   = _active == "keepa"
tab_sup_dir     = _active == "supplier"
tab_econ        = _active == "econ"
tab_date        = _active == "date"
tab_db_explorer = _active == "db_explorer"
tab_archive     = _active == "archive"


# =============================================================================
# TAB 1: OPPORTUNITIES — Master Product List & Gate Tracker
# =============================================================================
if tab_opps:
    st.subheader("📋 Discovered Opportunities — Gate Pipeline")
    st.caption("All products discovered by the autonomous swarm, with 6-gate status, gate filtering, and manual review.")

    live_products = [p for p in products if p.get("is_deleted", 0) == 0]

    # ── Filters ──────────────────────────────────────────────────────────────
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        regions = ["All"] + sorted({p["region"] for p in live_products if p.get("region")})
        sel_region = st.selectbox("🌍 Region", regions)
    with f2:
        cats = ["All"] + sorted({p["category"] for p in live_products if p.get("category")})
        sel_cat = st.selectbox("📦 Category", cats)
    with f3:
        statuses = ["All", "PENDING", "PASS", "FAIL", "CONSENSUS_PASS", "CONSENSUS_FAIL"]
        sel_status = st.selectbox("🔵 Status", statuses)
    with f4:
        shortlisted_only = st.checkbox("⭐ Shortlisted Only")

    filtered = live_products
    if sel_region != "All":
        filtered = [p for p in filtered if p.get("region") == sel_region]
    if sel_cat != "All":
        filtered = [p for p in filtered if p.get("category") == sel_cat]
    if sel_status != "All":
        filtered = [p for p in filtered if p.get("status") == sel_status or p.get("consensus_status") == sel_status]
    if shortlisted_only:
        filtered = [p for p in filtered if p.get("is_shortlisted", 0) == 1]

    st.caption(f"Showing **{len(filtered)}** of **{len(live_products)}** active products")
    st.markdown("---")

    if not filtered:
        st.info("No products match the current filters. The background daemon is continuously discovering new products.")
    else:
        for p in filtered:
            pid = p["product_id"]
            gate_statuses = get_gate_status(pid)
            current_gate = get_current_gate(pid)

            with st.expander(f"{'⭐ ' if p.get('is_shortlisted') else ''}**{p['name'][:65]}** — {p['region']} | Score: {p.get('overall_score',0):.0f}/100 | Net: {p.get('net_profit_pct',0):.1f}%", expanded=False):
                c1, c2, c3 = st.columns([2, 2, 1])

                with c1:
                    st.markdown(f"**Category:** {p.get('category', 'N/A')}")
                    st.markdown(f"**MSRP:** {format_currency(p.get('planned_msrp', 0), p['region'])}")
                    st.markdown(f"**Landed COGS:** {format_currency(p.get('landed_cogs', 0), p['region'])}")
                    st.markdown(f"**Gross %:** {p.get('gross_margin_pct', 0):.1f}%  &nbsp; **Net %:** {p.get('net_profit_pct', 0):.1f}%  &nbsp; **Stress %:** {p.get('worst_case_stress_margin_pct', 0):.1f}%")
                    st.markdown(f"**Sourcing:** {p.get('sourcing_cluster', 'N/A')}")

                with c2:
                    st.markdown("**Gate Progress:**")
                    gate_row = ""
                    for g in range(1, 7):
                        gs = gate_statuses.get(g, {})
                        g_status = gs.get("status", "PENDING")
                        badge_cls = {"PASS": "badge-pass", "FAIL": "badge-fail", "PENDING": "badge-pending",
                                     "BLOCKED": "badge-blocked", "IN_PROGRESS": "badge-progress"}.get(g_status, "badge-pending")
                        gate_row += f'<span class="gate-badge {badge_cls}">G{g}:{g_status[:4]}</span>'
                    st.markdown(gate_row, unsafe_allow_html=True)
                    st.caption(f"Current Gate: **{current_gate}** | Swarm: {p.get('consensus_status', 'N/A')}")

                    if p.get("competitor_3star_flaws"):
                        with st.popover("🛡️ 3-Star Flaws"):
                            st.markdown(p["competitor_3star_flaws"])
                    if p.get("upgrade_v2_engineering"):
                        with st.popover("🔧 V2 Fix"):
                            st.markdown(p["upgrade_v2_engineering"])

                with c3:
                    is_sl = bool(p.get("is_shortlisted", 0))
                    sl_label = "★ Shortlisted" if is_sl else "☆ Shortlist"
                    if st.button(sl_label, key=f"sl_{pid}", use_container_width=True):
                        toggle_shortlist(pid)
                        st.cache_data.clear()
                        st.rerun()

                    override = p.get("human_override_status") or ""
                    new_override = st.selectbox(
                        "Override Status",
                        ["", "MANUALLY_APPROVED", "MANUALLY_REJECTED", "ON_HOLD"],
                        index=["", "MANUALLY_APPROVED", "MANUALLY_REJECTED", "ON_HOLD"].index(override) if override in ["", "MANUALLY_APPROVED", "MANUALLY_REJECTED", "ON_HOLD"] else 0,
                        key=f"ov_{pid}"
                    )
                    if new_override != override:
                        set_human_override(pid, new_override or None)
                        st.cache_data.clear()
                        st.rerun()

                    # NOTE: Manual soft-delete removed — AI Supervisor auto-validates and
                    # rejects products with written reasoning. View rejected products in
                    # the 🗄️ SSOT DB Explorer tab → master_products → Show AI-Rejected toggle.

                    if st.button("🚀 Add to Launchpad", key=f"lp_{pid}", use_container_width=True, type="primary"):
                        add_to_launchpad(pid, p["name"])
                        st.toast(f"Added {p['name'][:30]}... to Launchpad!", icon="🚀")

                # Action plan
                if p.get("action_plan"):
                    st.info(f"📋 **Action Plan:** {p['action_plan']}")

            st.markdown("<hr style='margin:4px 0; border:0.5px solid #F1F5F9;'>", unsafe_allow_html=True)


# =============================================================================
# TAB 2: LAUNCHPAD
# =============================================================================
if tab_launchpad:
    st.subheader("🚀 Sourcing Launchpad — Live RFQ Workspace")
    st.caption("Products approved for sourcing pilot. Manage factory confirmation, samples, QC, and purchase orders.")

    lp_items = get_launchpad_items()
    sl_items = get_shortlisted_products()

    col_lp, col_sl = st.columns(2)
    with col_lp:
        st.metric("Active Launchpad Items", len(lp_items))
    with col_sl:
        st.metric("Shortlisted Products", len(sl_items))

    st.divider()

    if not lp_items:
        st.info("No launchpad items yet. Click **🚀 Add to Launchpad** on any approved product in Opportunities.")
    else:
        for item in lp_items:
            with st.expander(f"🚀 {item.get('product_name', 'Unknown')} — Status: {item.get('launch_status', 'N/A')}", expanded=False):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Target Launch Date:** {item.get('target_launch_date', 'TBD')}")
                    st.markdown(f"**Target MOQ:** {item.get('target_moq', 300):,} units")
                    st.markdown(f"**Target FOB:** ${item.get('target_fob', 0):.2f}")
                    st.markdown(f"**Factory:** {item.get('confirmed_factory_name', 'Not confirmed yet')}")
                    st.markdown(f"**QC Standard:** {item.get('qc_aql_standard', 'N/A')}")
                with c2:
                    st.markdown("**Checklist:**")
                    st.markdown(f"- Sample Ordered: {'✅' if item.get('sample_ordered') else '⬜'}")
                    st.markdown(f"- Sample Approved: {'✅' if item.get('sample_approved') else '⬜'}")
                    st.markdown(f"- Compliance Passed: {'✅' if item.get('compliance_checklist_passed') else '⬜'}")
                    st.markdown(f"- PO Generated: {'✅' if item.get('purchase_order_generated') else '⬜'}")

                    new_status = st.selectbox(
                        "Update Launch Status",
                        ["SOURCING_NEGOTIATION", "SAMPLE_ORDERED", "SAMPLE_APPROVED", "QC_IN_PROGRESS", "PO_ISSUED", "SHIPPED", "LIVE"],
                        index=["SOURCING_NEGOTIATION", "SAMPLE_ORDERED", "SAMPLE_APPROVED", "QC_IN_PROGRESS", "PO_ISSUED", "SHIPPED", "LIVE"].index(item.get("launch_status", "SOURCING_NEGOTIATION")) if item.get("launch_status") in ["SOURCING_NEGOTIATION", "SAMPLE_ORDERED", "SAMPLE_APPROVED", "QC_IN_PROGRESS", "PO_ISSUED", "SHIPPED", "LIVE"] else 0,
                        key=f"lp_status_{item.get('item_id', 0)}"
                    )
                    if st.button("💾 Save Status", key=f"lp_save_{item.get('item_id', 0)}", use_container_width=True):
                        update_launchpad_status(item["item_id"], new_status)
                        st.toast("Launchpad status updated!", icon="✅")
                        st.rerun()


# =============================================================================
# TAB 3: WAR ROOM — AI SPECIALIST CHAT
# =============================================================================
if tab_meeting:
    st.subheader("🎙️ Direct Specialist Chat & Team Meeting Room")
    st.caption("Talk directly to a specific specialist, or call `@all` for a full group debate. Every response is logged to Word by the Secretary.")

    r_cols = st.columns(6)
    r_members = [
        ("📈 Sales",      "Demand, Velocity & Ads",       "#0284C7"),
        ("🛡️ Quality",    "3-Star Flaws & v2.0 Fix",       "#DC2626"),
        ("🏭 Supplier",   "Factories, MOQ & FOB",          "#D97706"),
        ("💰 Finance",    "Margins & Stress Test",         "#4F46E5"),
        ("💻 Tech (You)", "Codebase & Scrapers",           "#0D9488"),
        ("📝 Secretary",  "Minutes & Word Doc",            "#059669"),
    ]
    for idx, (m_name, m_desc, m_col) in enumerate(r_members):
        with r_cols[idx]:
            st.markdown(f'<div class="member-pill" style="border-left:4px solid {m_col};"><strong>{m_name}</strong></div>', unsafe_allow_html=True)
            st.caption(m_desc)

    st.write("")

    ctrl_col1, ctrl_col2 = st.columns([3, 2])
    with ctrl_col1:
        target_speaker = st.selectbox(
            "🎯 Talk To / Target Speaker:",
            options=[
                ("auto",      "🤖 Auto-Detect (mention who you want)"),
                ("sales",     "📈 Sales (Demand, BSR, TikTok & Meta Ads)"),
                ("quality",   "🛡️ Quality (3-Star Review Defects & Engineering Fixes)"),
                ("supplier",  "🏭 Supplier (Factories, Ningbo/Moradabad, FOB & MOQs)"),
                ("finance",   "💰 Finance (Profit Margins, CAC Stress & Pricing)"),
                ("tech",      "💻 Tech / Antigravity (Codebase, Scraping Pipelines & DB)"),
                ("secretary", "📝 Secretary (Summaries, Action Items & Word Doc)"),
                ("all",       "👥 Everyone (Full Team Meeting / Roundtable)"),
            ],
            format_func=lambda x: x[1],
            index=0
        )[0]

    with ctrl_col2:
        st.write("")
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button("📝 Compile Word Doc", use_container_width=True):
                generate_meeting_word_doc()
                st.toast("Word Document compiled from meeting audit log!", icon="📄")
        with c_btn2:
            if Path(DOCX_FILE_PATH).exists():
                with open(DOCX_FILE_PATH, "rb") as f_doc:
                    st.download_button(
                        "⬇️ Download .docx",
                        data=f_doc.read(),
                        file_name="aprs_war_room.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )

    st.markdown("---")

    # ── Chat history ──────────────────────────────────────────────────────────
    history = get_meeting_history(limit=60)
    ROLE_CSS = {
        "Sales Agent": "agent-sales",
        "Quality Engineer": "agent-quality",
        "Supplier Coordinator": "agent-supplier",
        "Finance Analyst": "agent-finance",
        "Tech Lead": "agent-tech",
        "Secretary": "agent-secretary",
    }

    if "war_room_session" not in st.session_state:
        import uuid
        st.session_state["war_room_session"] = str(uuid.uuid4())[:8]

    for turn in history:
        css_cls = ROLE_CSS.get(turn.get("speaker_name", ""), "agent-tech")
        st.markdown(
            f'<div class="{css_cls}"><strong>{turn.get("avatar","🤖")} {turn.get("speaker_name","?")}:</strong> {turn.get("response_text","")}</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── Chat input ────────────────────────────────────────────────────────────
    user_msg = st.chat_input("Ask the team... (e.g. 'What's the best niche for India?', '@quality find flaws in bamboo toothbrush')")
    if user_msg:
        SPEAKER_MAP = {
            "sales":     ("📈 Sales Agent",          "📈", "agent-sales"),
            "quality":   ("🛡️ Quality Engineer",     "🛡️", "agent-quality"),
            "supplier":  ("🏭 Supplier Coordinator", "🏭", "agent-supplier"),
            "finance":   ("💰 Finance Analyst",       "💰", "agent-finance"),
            "tech":      ("💻 Tech Lead",             "💻", "agent-tech"),
            "secretary": ("📝 Secretary",             "📝", "agent-secretary"),
        }

        speakers_to_respond = list(SPEAKER_MAP.items()) if target_speaker == "all" else (
            [(target_speaker, SPEAKER_MAP[target_speaker])] if target_speaker in SPEAKER_MAP else list(SPEAKER_MAP.items())
        )

        for sp_key, (sp_name, sp_avatar, sp_css) in speakers_to_respond:
            with st.spinner(f"{sp_avatar} {sp_name} is thinking..."):
                try:
                    resp = nim_cluster.query(
                        prompt=f"You are {sp_name} in an e-commerce product research war room. User asked: {user_msg}\n\nProvide a concise, expert response in 2-4 sentences relevant to your specialty.",
                        task_type="fast_triage",
                        timeout=8.0
                    )
                    response_text = resp.get("content", "Analysis complete — no further findings.")
                except Exception as e:
                    response_text = f"⚠️ AI offline ({type(e).__name__}) — Using heuristic analysis: The requested analysis requires reviewing margin and supply chain data in the SSOT database."

            log_meeting_turn(
                session_id=st.session_state["war_room_session"],
                speaker_name=sp_name,
                speaker_role=sp_key,
                avatar=sp_avatar,
                user_prompt=user_msg,
                response_text=response_text
            )
            st.markdown(
                f'<div class="{sp_css}"><strong>{sp_avatar} {sp_name}:</strong> {response_text}</div>',
                unsafe_allow_html=True
            )


# =============================================================================
# TAB 4: KEEPA / BSR — Price & Rank Intelligence
# =============================================================================
if tab_h10_keepa:
    st.subheader("📈 Keepa / BSR — Price Intelligence & Rank Tracker")
    st.caption("Best Seller Rank, price history, and platform-level listing comparisons.")

    live_products = [p for p in products if p.get("is_deleted", 0) == 0]
    if not live_products:
        st.info("No products in the database yet.")
    else:
        sel_pid_k = st.selectbox(
            "Select Product",
            [p["product_id"] for p in live_products],
            format_func=lambda x: next((p["name"][:60] for p in live_products if p["product_id"] == x), x)
        )
        sel_prod_k = next((p for p in live_products if p["product_id"] == sel_pid_k), None)

        if sel_prod_k:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("BSR Rank", f"#{sel_prod_k.get('bsr_rank', 0):,}")
            k2.metric("Est. Daily Units", sel_prod_k.get("estimated_daily_units", 0))
            k3.metric("Price Stability", f"{sel_prod_k.get('keepa_price_stability', 85):.1f}%")
            k4.metric("Ad Active Days", sel_prod_k.get("ad_active_days", 30))

            st.divider()
            st.markdown("#### 🛒 Multi-Platform Listings")
            listings = _get_mpl(sel_pid_k)
            if listings:
                df_l = pd.DataFrame(listings)
                display_cols = [c for c in ["platform", "title", "price", "currency", "rating", "review_count", "in_stock", "listing_url"] if c in df_l.columns]
                st.dataframe(df_l[display_cols], use_container_width=True)
            else:
                st.info("No cross-platform listings scraped yet for this product. The daemon will populate them on the next scan cycle.")


# =============================================================================
# TAB 5: SUPPLIERS
# =============================================================================
if tab_sup_dir:
    st.subheader("🏭 Supplier Directory — Sourcing Intelligence")
    st.caption("Factory partners, FOB pricing, MOQs, and sourcing cluster data.")

    live_products = [p for p in products if p.get("is_deleted", 0) == 0]
    if not live_products:
        st.info("No products to show supplier data for.")
    else:
        sel_pid_s = st.selectbox(
            "Select Product",
            [p["product_id"] for p in live_products],
            format_func=lambda x: next((p["name"][:60] for p in live_products if p["product_id"] == x), x),
            key="sup_pid"
        )
        sel_prod_s = next((p for p in live_products if p["product_id"] == sel_pid_s), None)

        if sel_prod_s:
            s1, s2 = st.columns(2)
            with s1:
                st.markdown(f"**Sourcing Hub:** {sel_prod_s.get('sourcing_cluster', 'N/A')}")
                st.markdown(f"**Region:** {sel_prod_s.get('region', 'N/A')}")
                st.markdown(f"**Factory COGS:** {format_currency(sel_prod_s.get('factory_cogs') or 0, sel_prod_s.get('region','India'))}")
            with s2:
                st.markdown(f"**Landed COGS:** {format_currency(sel_prod_s.get('landed_cogs', 0), sel_prod_s.get('region','India'))}")
                st.markdown(f"**MSRP:** {format_currency(sel_prod_s.get('planned_msrp', 0), sel_prod_s.get('region','India'))}")
                if sel_prod_s.get("marketplace_url"):
                    st.markdown(f"**Product URL:** [{sel_prod_s['marketplace_url'][:50]}...]({sel_prod_s['marketplace_url']})")

            # Suppliers from DB
            st.divider()
            st.markdown("#### 🏭 Registered Factory Partners")
            try:
                conn = get_connection()
                cur = conn.execute("SELECT * FROM product_suppliers WHERE product_id=?", (sel_pid_s,))
                sup_rows = [dict(r) for r in cur.fetchall()]
                conn.close()
                if sup_rows:
                    df_sup = pd.DataFrame(sup_rows)
                    cols = [c for c in ["factory_name", "supplier_type", "industrial_address", "fob_unit_price", "moq_units", "certifications", "platform_profile_url"] if c in df_sup.columns]
                    st.dataframe(df_sup[cols], use_container_width=True)
                else:
                    st.info("No factory partners registered yet for this product. Swarm Gate 4 will populate supplier data.")
            except Exception as e:
                st.warning(f"Could not load suppliers: {e}")


# =============================================================================
# TAB 6: ECONOMICS — 15-Factor 3-Scenario Engine
# =============================================================================
if tab_econ:
    st.subheader("📊 15-Factor 3-Scenario Unit Economics Engine")
    st.caption("Conservative / Expected / Upside net margin analysis with break-even price and stress testing.")

    live_products = [p for p in products if p.get("is_deleted", 0) == 0]
    if not live_products:
        st.info("No products to analyse.")
    else:
        sel_econ_pid = st.selectbox(
            "Select Product",
            [p["product_id"] for p in live_products],
            format_func=lambda x: next((p["name"][:60] for p in live_products if p["product_id"] == x), x),
            key="econ_pid"
        )
        sel_prod_econ = next((p for p in live_products if p["product_id"] == sel_econ_pid), None)

        # Stored assessments
        stored_assessments = get_economics_assessments(sel_econ_pid)
        if stored_assessments:
            st.markdown("#### 📂 Stored AI-Generated Assessments")
            for sa in stored_assessments:
                with st.expander(f"Assessment — {sa.get('created_at', 'N/A')[:16]}", expanded=False):
                    cols_a = {
                        "Conservative Net%": sa.get("conservative_net_pct", 0),
                        "Expected Net%": sa.get("expected_net_pct", 0),
                        "Upside Net%": sa.get("upside_net_pct", 0),
                    }
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("Conservative", f"{sa.get('conservative_net_pct', 0):.1f}%")
                    mc2.metric("Expected", f"{sa.get('expected_net_pct', 0):.1f}%")
                    mc3.metric("Upside", f"{sa.get('upside_net_pct', 0):.1f}%")
                    st.caption(f"Composite Score: {sa.get('composite_score', 'N/A')} | Recommendation: {sa.get('recommendation', 'N/A')}")
        else:
            st.info("No 15-factor assessment stored yet. Run the calculator below to generate one.")

        # Live Calculator
        st.divider()
        st.markdown("#### ⚡ 15-Factor Economics Calculator")
        if sel_prod_econ:
            with st.form("quick_15factor"):
                qc1, qc2 = st.columns(2)
                with qc1:
                    q_fob = st.number_input("FOB Price (USD)", value=float(sel_prod_econ.get("factory_cogs") or sel_prod_econ.get("landed_cogs", 0) * 0.5 or 5.0), step=0.5, min_value=0.5)
                    q_msrp = st.number_input("MSRP", value=float(sel_prod_econ.get("planned_msrp") or 29.99), step=1.0)
                with qc2:
                    q_lead = st.number_input("Lead Time (days)", value=30, step=5, min_value=1)
                    q_trend = st.number_input("Trend Half-Life (days)", value=90, step=10, min_value=7)

                if st.form_submit_button("⚡ Calculate 15-Factor Economics", type="primary"):
                    try:
                        assessment = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
                            product_id=sel_econ_pid,
                            fob_price=q_fob,
                            planned_msrp=q_msrp,
                            region=sel_prod_econ.get("region", "India"),
                            category=sel_prod_econ.get("category", "General"),
                            lead_time_days=q_lead,
                            trend_half_life_days=q_trend
                        )
                        rc1, rc2, rc3 = st.columns(3)
                        rc1.metric("Conservative Net%", f"{assessment.conservative.net_profit_pct:.1f}%")
                        rc2.metric("Expected Net%", f"{assessment.expected.net_profit_pct:.1f}%")
                        rc3.metric("Upside Net%", f"{assessment.upside.net_profit_pct:.1f}%")
                        st.info(f"**Verdict:** {assessment.recommendation}  |  **Composite Score:** {assessment.composite_score}")
                    except Exception as eq:
                        st.error(f"Calculation error: {eq}")

        # Summary table
        st.divider()
        st.markdown("#### 📋 All Products — Economics Summary")
        econ_rows = []
        for p in live_products:
            cogs = p.get("landed_cogs", 0) or 0
            msrp = p.get("planned_msrp", 0) or 0
            markup = round(msrp / cogs, 2) if cogs > 0 else 0.0
            econ_rows.append({
                "Product ID": p["product_id"], "Name": p["name"][:45], "Region": p["region"],
                "MSRP": format_currency(msrp, p["region"]),
                "Landed COGS": format_currency(cogs, p["region"]),
                "Markup": f"{markup}x",
                "Gross %": f"{p.get('gross_margin_pct', 0):.1f}%",
                "Net %": f"{p.get('net_profit_pct', 0):.1f}%",
                "Stress %": f"{p.get('worst_case_stress_margin_pct', 0):.1f}%",
                "Sourcing Hub": p.get("sourcing_cluster", ""),
                "Status": p.get("human_override_status") or p.get("status", "PENDING"),
            })
        st.dataframe(pd.DataFrame(econ_rows), use_container_width=True)


# =============================================================================
# TAB 7: DATE LOGIC
# =============================================================================
if tab_date:
    st.subheader("📅 Date Logic Ledger & Daily Rolling Snapshots")
    conn = get_connection()
    try:
        df_snap = pd.read_sql_query("""
            SELECT s.snapshot_id as "ID", s.date as "Date", s.product_id as "Product ID",
                   p.name as "Product Name", p.region as "Region",
                   s.current_price as "Price", s.bsr_rank as "BSR",
                   s.estimated_daily_units as "Daily Units", s.status as "Status"
            FROM daily_snapshots s
            LEFT JOIN master_products p ON s.product_id = p.product_id
            ORDER BY s.date DESC
            LIMIT 200
        """, conn)
        if df_snap.empty:
            st.info("No daily snapshots recorded yet. The daemon will populate these as products are re-evaluated over time.")
        else:
            st.dataframe(df_snap, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load snapshots: {e}")
    finally:
        conn.close()


# =============================================================================
# TAB 8: SSOT DATABASE EXPLORER
# =============================================================================
if tab_db_explorer:
    st.subheader("🗄️ Unified SSOT Database Explorer & Multi-Table Inspector")
    st.caption("Direct read access to all SQLite SSOT tables. Inspect raw data, run text queries, and export tables to CSV.")

    table_names = get_all_table_names()
    if not table_names:
        st.warning("No user tables found in database.")
    else:
        db_c1, db_c2, db_c3 = st.columns([2, 2, 1])
        with db_c1:
            default_idx = table_names.index("master_products") if "master_products" in table_names else 0
            sel_table = st.selectbox("📂 Select Database Table", options=table_names, index=default_idx)
        with db_c2:
            search_query = st.text_input("🔍 Search within table (text query)", placeholder="e.g. Kitchen, PASS, India...")
        with db_c3:
            row_limit = st.selectbox("Row Limit", [50, 100, 200, 500, 1000], index=2)

        # ── AI-Rejected Products View (only for master_products) ──────────────
        if sel_table == "master_products":
            _rej_col1, _rej_col2 = st.columns([3, 1])
            with _rej_col1:
                show_rejected = st.toggle(
                    "🔴 Show AI-Rejected Products (soft-deleted)",
                    value=False,
                    help="Show only products auto soft-deleted by AI Supervisor with written rejection reasons"
                )
            with _rej_col2:
                try:
                    conn = get_connection()
                    _rej_count = conn.execute(
                        "SELECT COUNT(*) FROM master_products WHERE is_deleted=1"
                    ).fetchone()[0]
                    _total_count = conn.execute(
                        "SELECT COUNT(*) FROM master_products"
                    ).fetchone()[0]
                    conn.close()
                    st.metric("AI Rejected", f"{_rej_count} / {_total_count}")
                except Exception:
                    show_rejected = False

            if show_rejected:
                st.markdown("### 🔴 AI-Rejected Products — Written Rejection Reasons")
                st.caption(
                    "Products auto soft-deleted by AI Supervisor. "
                    "Rejection reason and AI reasoning are written directly to the product record."
                )
                try:
                    conn = get_connection()
                    rows = conn.execute("""
                        SELECT product_id, name, category, region,
                               ai_rejection_reason, ai_rejection_category,
                               ai_reasoning, ai_confidence,
                               deletion_reason, status, planned_msrp,
                               created_at
                        FROM master_products
                        WHERE is_deleted = 1
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (int(row_limit),)).fetchall()
                    conn.close()
                    if rows:
                        _rej_df = pd.DataFrame([dict(r) for r in rows])
                        # Highlight AI rejection columns
                        def _highlight_rejected(col):
                            if col.name in ("ai_rejection_reason", "ai_rejection_category", "ai_reasoning"):
                                return ["background-color: #FEE2E2; color: #991B1B; font-weight:600"] * len(col)
                            if col.name == "ai_confidence":
                                return ["background-color: #FEF3C7; color: #92400E"] * len(col)
                            return [""] * len(col)

                        st.dataframe(
                            _rej_df.style.apply(_highlight_rejected, axis=0),
                            use_container_width=True
                        )
                        _csv_rej = _rej_df.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "📥 Download AI-Rejected Products CSV",
                            data=_csv_rej,
                            file_name=f"ai_rejected_{datetime.date.today().isoformat()}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.info("No AI-rejected products yet. The AI Supervisor will auto-delete invalid findings and write reasons here.")
                except Exception as _re:
                    st.error(f"Error loading rejected products: {_re}")
                st.divider()

        # ── Standard table view ──────────────────────────────────────────────
        raw_records = get_table_data(sel_table, limit=int(row_limit), search_query=search_query)

        if not raw_records:
            st.info(f"No records found in table `{sel_table}` matching query.")
        else:
            df_table = pd.DataFrame(raw_records)
            st.markdown(f"**Table: `{sel_table}` — {len(df_table)} records shown (active only):**")
            st.dataframe(df_table, use_container_width=True)

            csv_data = df_table.to_csv(index=False).encode("utf-8")
            st.download_button(
                label=f"📥 Download `{sel_table}` as CSV",
                data=csv_data,
                file_name=f"{sel_table}_{datetime.date.today().isoformat()}.csv",
                mime="text/csv",
                use_container_width=False
            )

        # Row count overview for all tables
        st.divider()
        st.markdown("#### 📊 All Tables — Row Count Overview")
        conn = get_connection()
        try:
            overview = []
            for tbl in table_names:
                try:
                    cnt = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                    # For master_products, show rejected count separately
                    if tbl == "master_products":
                        try:
                            rej = conn.execute("SELECT COUNT(*) FROM master_products WHERE is_deleted=1").fetchone()[0]
                            active = cnt - rej
                            overview.append({"Table": tbl, "Row Count": cnt, "Active": active, "AI Rejected": rej})
                        except Exception:
                            overview.append({"Table": tbl, "Row Count": cnt, "Active": cnt, "AI Rejected": 0})
                    else:
                        overview.append({"Table": tbl, "Row Count": cnt})
                except Exception:
                    overview.append({"Table": tbl, "Row Count": "—"})
            st.dataframe(pd.DataFrame(overview), use_container_width=True)
        finally:
            conn.close()



# =============================================================================
# TAB 9: ARCHIVE — AI Rejected Products
# =============================================================================
if tab_archive:
    st.subheader("🗃️ Archive — AI Rejected Products with Rejection Reasons")
    st.caption("Products auto soft-deleted by AI Supervisor validation. Each entry shows the AI rejection reason and reasoning.")

    supervisor = get_supervisor()
    archived_products = supervisor.get_archive_view(limit=200)

    if not archived_products:
        st.info("No archived products yet. AI Supervisor will auto soft-delete invalid scraped findings with AI rejection reasons.")
    else:
        total_archived = len(archived_products)
        high_confidence = len([p for p in archived_products if p.get("ai_confidence", 0) >= 80])
        categories = {}
        for p in archived_products:
            cat = p.get("ai_rejection_category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Archived", total_archived)
        with col2:
            st.metric("High Confidence Rejections", high_confidence)
        with col3:
            st.metric("Rejection Categories", len(categories))
        with col4:
            restored_count = len([p for p in archived_products if p.get("is_deleted") == 0])
            st.metric("Restored This Session", restored_count)

        with st.expander("📊 Rejection Category Breakdown", expanded=False):
            for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                st.write(f"• **{cat}**: {count} products")

        st.markdown("---")

        for p in archived_products:
            pid = p["product_id"]
            with st.container():
                col1, col2, col4, col5, col6 = st.columns([0.4, 2.0, 1.2, 1.0, 1.0])
                with col1:
                    st.caption(f"#{pid}")
                with col2:
                    st.markdown(f"**{p['name'][:40]}**")
                    st.caption(f"Category: {p.get('category', 'N/A')} | Region: {p['region']}")
                with col4:
                    cat = p.get("ai_rejection_category", "unknown")
                    cat_colors = {
                        "missing_data": "#EF4444", "invalid_price": "#F97316",
                        "invalid_url": "#F59E0B", "unrealistic_data": "#8B5CF6",
                        "duplicate": "#EC4899", "marketplace_mismatch": "#06B6D4",
                        "fake_data": "#DC2626", "validation_error": "#64748B",
                        "manual": "#6B7280"
                    }
                    color = cat_colors.get(cat, "#64748B")
                    st.markdown(f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.7rem;font-weight:600;">{cat.upper()}</span>', unsafe_allow_html=True)
                with col5:
                    reason = p.get("ai_rejection_reason", "No reason recorded")
                    conf = p.get("ai_confidence", 0)
                    st.caption(f"Confidence: {conf}%")
                    with st.popover("📝 AI Rejection Reason", use_container_width=False):
                        st.markdown(f"**Product:** {p['name']}")
                        st.markdown(f"**Category:** {p.get('ai_rejection_category', 'unknown')}")
                        st.markdown(f"**Confidence:** {p.get('ai_confidence', 0)}%")
                        st.markdown("**AI Reasoning:**")
                        st.info(p.get("ai_reasoning", "No AI reasoning recorded"))
                        st.markdown("**Rejection Reason:**")
                        st.error(reason)
                        if st.button("♻️ Restore Product", key=f"restore_archive_{pid}", type="primary", use_container_width=True):
                            restore_product(pid)
                            st.toast(f"Product {pid} restored!", icon="♻️")
                            st.rerun()
                with col6:
                    if st.button("🔍 View Details", key=f"view_archive_{pid}", use_container_width=True):
                        st.session_state["active_tab"] = "opps"
                        st.rerun()

            st.markdown("<hr style='margin:4px 0; border:0.5px solid #F1F5F9;'>", unsafe_allow_html=True)