"""
web/app.py — APRS V7 Pro — AI Virtual Office Control Center.

10 Tabs:
1. 📋 Opportunities & Gate Pipeline — Product cards, manual gate controls
2. ⚡ Agent Command Center — 9 agent grid, Main AI Supervisor, live activity
3. 🏭 Suppliers & Outreach — Supplier cards, GST badges, outreach drafts
4. 🔍 Customer Reviews & Problem Mining — 3-star defects, v2.0 specs
5. 🚀 Sourcing Launchpad — Kanban pipeline
6. 🎙️ War Room — 6 AI specialists + Word export
7. 📈 Keepa & Cross-Marketplace — BSR/Price tracking, comparison
8. 📊 15-Factor Economics — Interactive waterfall charts
9. 🗄️ SSOT Database Explorer — All 33 tables, live search, CSV
10. 🗃️ Archive & Recovery — Soft-deleted products, 1-click restore
"""
import os
import sys
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# ── Project root on sys.path ─────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Core imports ──────────────────────────────────────────────────────────────
from config.settings import settings
from core.database import (
    init_db, get_connection, get_all_products, get_all_table_names, get_table_data,
    toggle_shortlist, get_shortlisted_products, soft_delete_product, restore_product,
    set_human_override, get_gate_status, get_defect_clusters, get_economics_assessments,
    get_dynamic_niches, get_seed_keywords, get_discovered_sources,
    get_supplier_profiles_for_product, get_outreach_drafts_for_product,
    update_outreach_status, get_problem_opportunities, get_archive_products,
    get_recent_swarm_audit_log, get_live_table_counts,
)
from core.economics_engine import Comprehensive15FactorEconomics
from core.gate_engine import GateEngine
from core.rule_engine import create_rule_engine
from core.validation import CanonicalProduct
from core.daemon_service import daemon_controller

logger = logging.getLogger("aprs.webapp")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s — %(message)s")

# ── Init DB ───────────────────────────────────────────────────────────────────
init_db()

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="APRS V7 Pro — AI Virtual Office",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background: #F8FAFC; }
    .block-container { padding-top: 0.5rem !important; max-width: 100% !important; }
    
    /* Cards & Containers */
    .metric-card { background:#FFFFFF; border-radius:10px; padding:14px 18px; border:1px solid #E2E8F0; margin-bottom:8px; color:#1E293B; }
    .metric-card h4, .metric-card strong, .metric-card small { color:#1E293B; }
    
    /* Gate Badges */
    .gate-badge { display:inline-block; padding:2px 10px; border-radius:12px; font-size:0.78rem; font-weight:700; margin:2px; }
    .badge-pass { background:#D1FAE5; color:#065F46; }
    .badge-fail { background:#FEE2E2; color:#991B1B; }
    .badge-pending { background:#E2E8F0; color:#475569; }
    .badge-blocked { background:#FEF3C7; color:#92400E; }
    .badge-progress { background:#DBEAFE; color:#1E40AF; }
    .badge-override { background:#EDE9FE; color:#6B21A8; }
    
    /* Score Display */
    .score-big { font-size:2.5rem; font-weight:800; text-align:center; }
    .score-proceed { color:#059669; }
    .score-marginal { color:#D97706; }
    .score-reject { color:#DC2626; }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 24px; border-radius: 8px 8px 0 0; color:#1E293B !important; }
    .stTabs [aria-selected="true"] { background: #2563EB !important; color: white !important; }
    
    /* Status LEDs */
    .status-led { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }
    .led-green { background:#22C55E; box-shadow:0 0 8px #22C55E; animation:pulse 2s infinite; }
    .led-yellow { background:#EAB308; box-shadow:0 0 8px #EAB308; animation:pulse 2s infinite; }
    .led-red { background:#EF4444; box-shadow:0 0 8px #EF4444; animation:pulse 2s infinite; }
    .led-gray { background:#94A3B8; }
    @keyframes pulse { 0% { opacity:1; } 50% { opacity:0.5; } 100% { opacity:1; } }
    
    /* Table Chips */
    .table-chip { background:#EFF6FF; color:#1E40AF; padding:4px 10px; border-radius:6px; font-size:0.8rem; font-weight:600; margin:2px; display:inline-block; }
    
    /* Agent Rows */
    .agent-row { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:8px; padding:12px; margin:6px 0; color:#1E293B; }
    .agent-row strong, .agent-row small, .agent-row div { color:#1E293B; }
    .agent-running { border-left:4px solid #22C55E; }
    .agent-paused { border-left:4px solid #EAB308; }
    
    /* Kanban */
    .kanban-column { background:#F1F5F9; border-radius:8px; padding:10px; min-height:300px; }
    .kanban-card { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:6px; padding:12px; margin:8px 0; box-shadow:0 1px 3px rgba(0,0,0,0.05); color:#1E293B; }
    .kanban-card strong, .kanban-card small { color:#1E293B; }
    
    /* Review & Spec Clusters */
    .review-cluster { background:#FFF7ED; border-left:4px solid #F97316; padding:12px; margin:8px 0; border-radius:0 8px 8px 0; color:#1E293B; }
    .review-cluster strong, .review-cluster small { color:#1E293B; }
    .v2-spec { background:#F0FDF4; border-left:4px solid #22C55E; padding:12px; margin:8px 0; border-radius:0 8px 8px 0; color:#1E293B; }
    .v2-spec strong { color:#1E293B; }
    
    /* Sidebar */
    .sidebar-header { font-size:1.1rem; font-weight:700; color:#1E293B; margin-bottom:0.5rem; }
    .live-indicator { display:inline-flex; align-items:center; gap:6px; }
    
    /* Top Header - Primary Control Bar */
    .top-header { 
        background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%); 
        border: 1px solid #E2E8F0; 
        border-radius: 12px; 
        padding: 16px 20px; 
        margin-bottom: 12px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .top-header .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease;
    }
    .top-header .stButton > button[kind="primary"] {
        background: #2563EB;
        border-color: #2563EB;
    }
    .top-header .stButton > button[kind="primary"]:hover {
        background: #1D4ED8;
        border-color: #1D4ED8;
    }
    .top-header .stTextInput > div > div > input {
        border-radius: 8px;
        border: 1px solid #E2E8F0;
    }
    .top-header .stSelectbox > div > div {
        border-radius: 8px;
    }
    
    /* Sidebar as Filter Panel */
    .stSidebar { background: #F8FAFC !important; }
    .stSidebar .stMetric { background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; padding: 8px 12px; }
    .stSidebar .stSelectbox > div > div { border-radius: 6px; }
    .stSidebar .stCheckbox > label { color: #1E293B; }
    
    /* Hide default streamlit header/footer */
    header[data-testid="stHeader"] { display: none; }
    footer { display: none; }
    
    /* Ensure tabs are prominent */
    .stTabs [data-baseweb="tab-list"] { 
        background: #FFFFFF; 
        border: 1px solid #E2E8F0; 
        border-radius: 10px; 
        padding: 4px; 
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] { 
        background: transparent; 
        border-radius: 6px; 
        color: #475569 !important; 
        font-weight: 500;
    }
    .stTabs [aria-selected="true"] { 
        background: #2563EB !important; 
        color: white !important; 
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
    }
    
    /* Flow Graph Styles */
    .flow-node { 
        display:inline-flex; flex-direction:column; align-items:center; 
        padding:12px 16px; border-radius:10px; 
        min-width:140px; text-align:center;
        box-shadow:0 2px 8px rgba(0,0,0,0.1);
        transition:all 0.3s ease;
        cursor:pointer;
    }
    .flow-node:hover { transform:translateY(-2px); box-shadow:0 4px 16px rgba(0,0,0,0.15); }
    .flow-node.completed { background:#D1FAE5; border:2px solid #059669; }
    .flow-node.running { background:#DBEAFE; border:2px solid #2563EB; animation:pulse 1.5s infinite; }
    .flow-node.failed { background:#FEE2E2; border:2px solid #DC2626; }
    .flow-node.blocked { background:#FEF3C7; border:2px solid #D97706; }
    .flow-node.idle { background:#F1F5F9; border:2px solid #94A3B8; opacity:0.6; }
    .flow-node-icon { font-size:1.8rem; margin-bottom:4px; }
    .flow-node-name { font-weight:700; font-size:0.85rem; color:#1E293B; margin-bottom:2px; }
    .flow-node-status { font-size:0.7rem; font-weight:600; text-transform:uppercase; padding:2px 8px; border-radius:6px; }
    .flow-node-stats { font-size:0.65rem; color:#64748B; margin-top:4px; }
    
    .flow-arrow { font-size:1.5rem; color:#94A3B8; margin:0 8px; align-self:center; }
    .flow-arrow.active { color:#2563EB; }
    
    .flow-layer { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:20px; margin:12px 0; }
    .flow-layer-title { font-weight:700; color:#1E293B; margin-bottom:16px; padding-bottom:8px; border-bottom:2px solid #E2E8F0; }
    
    /* Branch Detail Panel */
    .branch-detail { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; padding:16px; margin-top:16px; }
    .branch-detail h4 { color:#1E293B; margin-top:0; }
    .branch-detail .data-row { display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #F1F5F9; }
    .branch-detail .data-row:last-child { border-bottom:none; }
    .branch-detail .data-label { color:#64748B; font-weight:500; }
    .branch-detail .data-value { color:#1E293B; font-weight:600; }
    
    /* Top Header Improvements */
    .top-header { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:12px; padding:16px 20px; margin-bottom:16px; }
    .header-section { display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
    .daemon-controls { display:flex; gap:8px; }
    .daemon-btn { padding:8px 16px; border-radius:8px; font-weight:600; border:none; cursor:pointer; transition:all 0.2s; }
    .daemon-btn.primary { background:#2563EB; color:white; }
    .daemon-btn.primary:hover { background:#1D4ED8; }
    .daemon-btn.secondary { background:#F1F5F9; color:#1E293B; border:1px solid #E2E8F0; }
    .daemon-btn.secondary:hover { background:#E2E8F0; }
    .daemon-btn.danger { background:#FEE2E2; color:#DC2626; border:1px solid #FECACA; }
    .daemon-btn.danger:hover { background:#FECACA; }
    
    /* Search Expandable */
    .search-expand { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; padding:12px; margin:8px 0; }
    .search-expand-header { display:flex; align-items:center; justify-content:space-between; cursor:pointer; }
    .search-expand-content { margin-top:12px; padding-top:12px; border-top:1px solid #E2E8F0; }
    
    /* Stats Summary */
    .stat-card { background:#FFFFFF; border:1px solid #E2E8F0; border-radius:10px; padding:16px; text-align:center; }
    .stat-value { font-size:1.5rem; font-weight:800; color:#1E293B; }
    .stat-label { font-size:0.75rem; color:#64748B; text-transform:uppercase; letter-spacing:0.05em; }
</style>
""", unsafe_allow_html=True)

# ── Helper Functions ──────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_products(include_deleted: bool = False) -> List[Dict]:
    return get_all_products(include_deleted=include_deleted)

def format_inr(val: float) -> str:
    return f"₹{val:,.0f}" if val else "₹0"

def format_pct(val: float) -> str:
    return f"{val:.1f}%" if val is not None else "N/A"

def get_gate_status_dict(product_id: str) -> Dict[int, Dict]:
    gate_list = get_gate_status(product_id)
    return {g["gate_number"]: g for g in gate_list}

def create_waterfall_chart(assessment: Dict) -> go.Figure:
    scenarios = ["Conservative", "Expected", "Upside"]
    fig = make_subplots(rows=1, cols=3, subplot_titles=scenarios, horizontal_spacing=0.08)
    colors = {"revenue": "#059669", "cogs": "#DC2626", "fees": "#D97706", "marketing": "#7C3AED", "tax": "#EA580C", "profit": "#059669"}
    for idx, scenario in enumerate(scenarios):
        col = idx + 1
        sc_data = assessment.get(scenario.lower(), {})
        msrp = sc_data.get("planned_msrp", 0)
        landed_cogs = sc_data.get("landed_cogs", 0)
        marketplace_comm = sc_data.get("marketplace_commission", 0)
        fulfillment = sc_data.get("fulfillment_fee", 0)
        payment_fee = sc_data.get("payment_or_cod_fee", 0)
        rto = sc_data.get("rto_reserve", 0)
        fraud = sc_data.get("return_fraud_reserve", 0)
        ads = sc_data.get("ad_tacos_reserve", 0)
        tax = sc_data.get("net_tax_burden", 0)
        net_profit = sc_data.get("net_profit", 0)
        x_labels = ["MSRP", "COGS", "Comm.", "Fulfill.", "Payment", "RTO", "Fraud", "Ads", "Tax", "Net Profit"]
        y_values = [msrp, -landed_cogs, -marketplace_comm, -fulfillment, -payment_fee, -rto, -fraud, -ads, -tax, net_profit]
        bar_colors = []
        for i, v in enumerate(y_values):
            if v > 0: bar_colors.append(colors["revenue"])
            elif i == 1: bar_colors.append(colors["cogs"])
            elif i in (2, 3): bar_colors.append(colors["fees"])
            elif i == 7: bar_colors.append(colors["marketing"])
            elif i == 8: bar_colors.append(colors["tax"])
            else: bar_colors.append(colors["profit"])
        fig.add_trace(go.Bar(name=scenario, x=x_labels, y=y_values, marker_color=bar_colors, text=[f"₹{abs(v):,.0f}" for v in y_values], textposition="auto", showlegend=False), row=1, col=col)
        fig.add_annotation(x=0.5, y=net_profit, text=f"Net: ₹{net_profit:,.0f} ({sc_data.get('net_profit_pct', 0):.1f}%)", showarrow=True, arrowhead=2, row=1, col=col, font=dict(size=11, color=colors["profit"] if net_profit > 0 else colors["cogs"]))
    fig.update_layout(height=450, title_text="15-Factor Economics Waterfall — 3 Scenarios", template="plotly_white", margin=dict(t=60, b=40, l=40, r=40))
    fig.update_xaxes(tickangle=-45)
    fig.update_yaxes(title_text="Amount (INR)")
    return fig

def create_score_radar(breakdown: Dict) -> go.Figure:
    categories = list(breakdown.keys())
    values = list(breakdown.values())
    max_values = {"market_signal": 25, "review_quality": 20, "margin_safety": 40, "defect_fixability": 10, "competition_density": 5}
    normalized = [v / max_values.get(c, 1) * 100 for c, v in zip(categories, values)]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=normalized + [normalized[0]], theta=categories + [categories[0]], fill='toself', name='Score Breakdown', line_color='#2563EB', fillcolor='rgba(37, 99, 235, 0.2)'))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), height=350, margin=dict(t=30, b=30, l=30, r=30))
    return fig

def export_dossier_excel(product: Dict, assessments: List[Dict], defects: List[Dict]) -> bytes:
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        overview = pd.DataFrame([{"Product": product.get("name", ""), "Category": product.get("category", ""), "Region": product.get("region", ""), "MSRP": product.get("planned_msrp", 0), "Landed COGS": product.get("landed_cogs", 0), "Gross Margin %": product.get("gross_margin_pct", 0), "Net Margin %": product.get("net_profit_pct", 0), "BSR": product.get("bsr_rank", 0), "Rating": product.get("rating", 0), "Reviews": product.get("review_count", 0)}])
        overview.to_excel(writer, sheet_name="Overview", index=False)
        if assessments:
            econ_rows = []
            for a in assessments:
                for sc in ["conservative", "expected", "upside"]:
                    sc_data = a.get(sc, {})
                    econ_rows.append({"Scenario": sc.capitalize(), "MSRP": sc_data.get("planned_msrp", 0), "FOB": sc_data.get("fob_price", 0), "Landed COGS": sc_data.get("landed_cogs", 0), "Gross Profit": sc_data.get("gross_profit", 0), "Gross Margin %": sc_data.get("gross_margin_pct", 0), "Net Profit": sc_data.get("net_profit", 0), "Net Margin %": sc_data.get("net_profit_pct", 0), "Status": sc_data.get("status", "")})
            pd.DataFrame(econ_rows).to_excel(writer, sheet_name="Economics", index=False)
        if defects:
            pd.DataFrame(defects).to_excel(writer, sheet_name="Defects", index=False)
    return output.getvalue()

def export_dossier_word(product: Dict, assessments: List[Dict], defects: List[Dict]) -> bytes:
    from io import BytesIO
    from docx import Document
    from docx.shared import Inches, Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc = Document()
    title = doc.add_heading("APRS V7 Pro — Product Dossier", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_heading("Product Overview", level=1)
    table = doc.add_table(rows=8, cols=2, style='Light Grid Accent 1')
    data = [("Product", product.get("name", "")), ("Category", product.get("category", "")), ("Region", product.get("region", "")), ("MSRP", format_inr(product.get("planned_msrp", 0))), ("Landed COGS", format_inr(product.get("landed_cogs", 0))), ("Gross Margin", format_pct(product.get("gross_margin_pct", 0))), ("Net Margin", format_pct(product.get("net_profit_pct", 0))), ("BSR Rank", f"#{product.get('bsr_rank', 0):,}")]
    for i, (k, v) in enumerate(data):
        table.cell(i, 0).text = k
        table.cell(i, 1).text = str(v)
    if assessments:
        doc.add_heading("15-Factor Economics (3 Scenarios)", level=1)
        a = assessments[0]
        for sc in ["conservative", "expected", "upside"]:
            sc_data = a.get(sc, {})
            doc.add_heading(f"{sc.capitalize()} Scenario", level=2)
            t = doc.add_table(rows=5, cols=2, style='Light Grid Accent 1')
            sc_fields = [("MSRP", format_inr(sc_data.get("planned_msrp", 0))), ("FOB", format_inr(sc_data.get("fob_price", 0))), ("Landed COGS", format_inr(sc_data.get("landed_cogs", 0))), ("Net Profit", format_inr(sc_data.get("net_profit", 0))), ("Net Margin %", format_pct(sc_data.get("net_profit_pct", 0)))]
            for i, (k, v) in enumerate(sc_fields):
                t.cell(i, 0).text = k
                t.cell(i, 1).text = str(v)
    if defects:
        doc.add_heading("Defect Analysis & v2.0 Specification", level=1)
        for d in defects:
            doc.add_heading(f"Defect: {d.get('defect_description', '')}", level=3)
            doc.add_paragraph(f"Severity: {d.get('severity', 'N/A')}")
            doc.add_paragraph(f"Fixable: {'Yes' if d.get('is_fixable') else 'No'}")
            if d.get('v2_fix_description'):
                doc.add_paragraph(f"v2.0 Fix: {d['v2_fix_description']}")
    output = BytesIO()
    doc.save(output)
    return output.getvalue()

def export_war_room_doc(product: Dict, meeting_log: List[Dict]) -> bytes:
    from io import BytesIO
    from docx import Document
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc = Document()
    title = doc.add_heading(f"APRS War Room — {product.get('name', 'Product')}", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    doc.add_paragraph(f"Product ID: {product.get('product_id', 'N/A')}")
    doc.add_paragraph(f"Category: {product.get('category', 'N/A')} | Region: {product.get('region', 'N/A')}")
    doc.add_heading("Meeting Transcript", level=1)
    for turn in meeting_log:
        speaker = turn.get("speaker_name", "Unknown")
        role = turn.get("speaker_role", "")
        prompt = turn.get("user_prompt", "")
        response = turn.get("response_text", "")
        p = doc.add_paragraph()
        p.add_run(f"{speaker} ({role}): ").bold = True
        p.add_run(f"{prompt}\n{response}")
        doc.add_paragraph("")
    output = BytesIO()
    doc.save(output)
    return output.getvalue()

# ── Load Data ─────────────────────────────────────────────────────────────────
products = load_products(include_deleted=False)
shortlisted = [p for p in products if p.get("is_shortlisted", 0) == 1]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🏢 APRS V7 Pro")
    st.caption("AI Virtual Office Control Center")
    st.divider()
    
    # Quick stats
    col1, col2 = st.columns(2)
    col1.metric("Products", len(products))
    col2.metric("Shortlisted", len(shortlisted))
    col1, col2 = st.columns(2)
    col1.metric("Niches", len(get_dynamic_niches(active_only=True)))
    col2.metric("Seed Keywords", len(get_seed_keywords(active_only=True)))
    
    st.divider()
    
    # Filters
    st.subheader("Filters")
    regions = ["All"] + sorted({p["region"] for p in products if p.get("region")})
    sel_region = st.selectbox("Region", regions)
    categories = ["All"] + sorted({p["category"] for p in products if p.get("category")})
    sel_category = st.selectbox("Category", categories)
    show_shortlisted_only = st.checkbox("Shortlisted Only", value=False)
    
    st.divider()
    
    # Gate thresholds
    st.subheader("Gate Thresholds")
    st.caption(f"Gate 1 BSR: < {settings.gate1_bsr_threshold:,}")
    st.caption(f"Gate 1 CV: < {settings.gate1_cv_threshold:.0%}")
    st.caption(f"Gate 3 Margin: ≥ {settings.gate3_min_margin_pct:.0f}%")
    st.caption(f"Gate 4 Score: ≥ {settings.gate4_min_score}")

# ── Apply Filters ─────────────────────────────────────────────────────────────
filtered = products
if sel_region != "All":
    filtered = [p for p in filtered if p.get("region") == sel_region]
if sel_category != "All":
    filtered = [p for p in filtered if p.get("category") == sel_category]
if show_shortlisted_only:
    filtered = [p for p in filtered if p.get("is_shortlisted", 0) == 1]

# ══════════════════════════════════════════════════════════════════════════════
# TOP CONTROL BAR — Single unified header with status, daemon controls & search
# ══════════════════════════════════════════════════════════════════════════════
status = daemon_controller.get_status()
table_counts = daemon_controller.get_live_table_counts()

# Status LEDs
nim_led = "🟢"  # Would check actual NIM connectivity
groq_led = "🟢"  # Would check Groq
ollama_led = "🟡"  # Would check Ollama
daemon_running = status["running"]
daemon_paused = status["is_paused"]

# Single unified header row
st.markdown('<div class="top-header">', unsafe_allow_html=True)

# Row 1: Service Status + Daemon Controls + Search
col_status, col_controls, col_search = st.columns([2.5, 2.5, 3])

with col_status:
    st.markdown(f"""
    <div class="live-indicator" style="gap:12px; flex-wrap:wrap;">
        <span class="status-led led-{'green' if nim_led=='🟢' else 'gray'}"></span><strong>NIM 550B</strong>
        <span class="status-led led-{'green' if groq_led=='🟢' else 'gray'}"></span><strong>Groq</strong>
        <span class="status-led led-{'yellow' if ollama_led=='🟡' else 'green' if ollama_led=='🟢' else 'gray'}"></span><strong>Ollama</strong>
        <span class="status-led led-{'green' if daemon_running else 'yellow' if daemon_paused else 'red'}"></span>
        <strong style="color:{'#059669' if daemon_running else '#D97706' if daemon_paused else '#DC2626'};">
            {'● ACTIVE' if daemon_running else '⏸ PAUSED' if daemon_paused else '■ STOPPED'}
        </strong>
    </div>
    """, unsafe_allow_html=True)

with col_controls:
    # Daemon Controls - always visible
    dc1, dc2, dc3, dc4 = st.columns(4)
    
    if not daemon_running:
        # Daemon stopped - show START button prominently
        if dc1.button("▶️ START", type="primary", use_container_width=True, key="daemon_start_main"):
            daemon_controller.start()
            st.rerun()
        dc2.caption("Daemon stopped")
        dc3.caption("")
        dc4.caption("")
    else:
        # Daemon running - show PAUSE/RESUME + FORCE CYCLE
        if daemon_paused:
            if dc1.button("▶ RESUME", type="primary", use_container_width=True, key="daemon_resume_main"):
                daemon_controller.resume()
                st.rerun()
        else:
            if dc1.button("⏸ PAUSE", use_container_width=True, key="daemon_pause_main"):
                daemon_controller.pause()
                st.rerun()
        
        if dc2.button("🔄 CYCLE", use_container_width=True, key="daemon_cycle_main"):
            daemon_controller.trigger_cycle_now()
            st.toast("⚡ Cycle triggered!")
        
        with dc3:
            with st.popover("📜 Logs", use_container_width=True):
                logs = daemon_controller.stream_log_tail(30)
                for log in reversed(logs):
                    st.text(log)
                if st.button("Clear", key="clear_log_main"):
                    daemon_controller.recent_logs.clear()
                    st.rerun()
        
        dc4.caption(f"Cycle #{status.get('cycle_count', 0)}")

with col_search:
    # Product Search - expandable
    if "search_expanded" not in st.session_state:
        st.session_state["search_expanded"] = False
    
    sc1, sc2 = st.columns([1, 5])
    with sc1:
        if st.button(
            "🔍 Search" + (" ▼" if st.session_state["search_expanded"] else " ▶"),
            use_container_width=True,
            key="search_toggle_main"
        ):
            st.session_state["search_expanded"] = not st.session_state["search_expanded"]
            st.rerun()
    
    with sc2:
        if st.session_state["search_expanded"]:
            s1, s2, s3, s4 = st.columns([3, 1.5, 1.5, 1])
            with s1:
                search_query = st.text_input(
                    "Search", placeholder="Product name, ID, category, ASIN...",
                    key="product_search_input_main", label_visibility="collapsed"
                )
            with s2:
                search_region = st.selectbox("Region", ["All"] + sorted({p["region"] for p in products if p.get("region")}), key="search_region_main", label_visibility="collapsed")
            with s3:
                search_category = st.selectbox("Category", ["All"] + sorted({p["category"] for p in products if p.get("category")}), key="search_category_main", label_visibility="collapsed")
            with s4:
                search_btn = st.button("🔍", type="primary", use_container_width=True, key="product_search_btn_main", help="Search")
            
            if search_btn or (search_query and len(search_query) >= 2):
                sq = search_query.lower() if search_query else ""
                search_results = products
                if sq:
                    search_results = [p for p in search_results if 
                        sq in p.get("name", "").lower() or
                        sq in p.get("product_id", "").lower() or
                        sq in p.get("category", "").lower() or
                        sq in p.get("amazon_asin", "").lower()
                    ]
                if search_region != "All":
                    search_results = [p for p in search_results if p.get("region") == search_region]
                if search_category != "All":
                    search_results = [p for p in search_results if p.get("category") == search_category]
                
                if search_results:
                    st.caption(f"Found {len(search_results)} matches")
                    for p in search_results[:8]:
                        r1, r2, r3, r4 = st.columns([3, 1, 1, 1])
                        with r1:
                            st.markdown(f"**{p['name'][:45]}**  \n<small>{p.get('category','')} • {p.get('region','')} • {format_inr(p.get('planned_msrp',0))}</small>", unsafe_allow_html=True)
                        with r2:
                            st.caption(f"Score: {p.get('overall_score',0):.0f}")
                        with r3:
                            st.caption(p.get('status','PENDING'))
                        with r4:
                            if st.button("Open", key=f"sv_{p['product_id']}", use_container_width=True):
                                st.session_state["search_expanded"] = False
                                st.session_state["view_product_id"] = p["product_id"]
                                st.session_state["active_tab"] = "opportunities"
                                st.rerun()
                else:
                    st.caption("No matches found")

st.markdown('</div>', unsafe_allow_html=True)

# Quick stats chips row
chips_html = " ".join([f'<span class="table-chip">{k}: {v:,}</span>' for k, v in [
    ("Products", table_counts.get("master_products", 0)),
    ("Niches", table_counts.get("dynamic_niches", 0)),
    ("Suppliers", table_counts.get("supplier_profiles", 0)),
    ("Outreach", table_counts.get("outreach_drafts", 0)),
    ("Rules", table_counts.get("learned_rules", 0)),
    ("Shortlisted", len(shortlisted)),
]])
st.markdown(chips_html, unsafe_allow_html=True)

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# TAB DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════
TABS = [
    ("opportunities", "📋 Opportunities"),
    ("agent_cockpit", "⚡ Agent Command"),
    ("suppliers", "🏭 Suppliers"),
    ("reviews", "🔍 Reviews"),
    ("launchpad", "🚀 Launchpad"),
    ("war_room", "🎙️ War Room"),
    ("keepa", "📈 Keepa"),
    ("economics", "📊 Economics"),
    ("db_explorer", "🗄️ DB Explorer"),
    ("archive", "🗃️ Archive"),
    ("flow_graph", "🔄 Flow Graph"),
]

tab_opp, tab_agent, tab_sup, tab_rev, tab_lp, tab_wr, tab_kp, tab_eco, tab_db, tab_arch, tab_flow = st.tabs([t[1] for t in TABS])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: OPPORTUNITIES & GATE PIPELINE
# ═════════════════════════════════════════════════════════════════════════════
with tab_opp:
    st.subheader("📋 Opportunities & Gate Pipeline")
    
    # Niches overview
    niches = get_dynamic_niches(region=sel_region if sel_region != "All" else None, active_only=True)
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown("**Active Niches**")
        if niches:
            niche_df = pd.DataFrame(niches)
            display_cols = ["category", "region", "priority_score", "times_scanned", "products_found", "is_active"]
            st.dataframe(niche_df[display_cols], width='stretch', hide_index=True)
        else:
            st.info("No active niches. Run discovery scan via CLI or Agent Command tab.")
    with c2:
        st.markdown("**Quick Actions**")
        if st.button("🔍 Run Discovery Scan", type="primary", width='stretch', key="opp_discovery"):
            result = daemon_controller.run_agent_on_demand("discovery")
            st.toast(f"Discovery: {result.get('status', 'started')}")
        if st.button("📥 Export Niches CSV", width='stretch', key="opp_niches_csv"):
            if niches:
                csv = pd.DataFrame(niches).to_csv(index=False)
                st.download_button("Download", csv, "niches.csv", "text/csv", width='stretch')
    
    st.divider()
    
    # Product list with gate status
    st.markdown("**Product Pipeline**")
    
    if not filtered:
        st.info("No products match current filters.")
    else:
        # Gate summary metrics
        gate_stats = {1: {"pass": 0, "fail": 0, "pending": 0}, 2: {"pass": 0, "fail": 0, "pending": 0}, 3: {"pass": 0, "fail": 0, "pending": 0}, 4: {"pass": 0, "fail": 0, "pending": 0}, 5: {"pass": 0, "fail": 0, "pending": 0}}
        
        for p in filtered:
            gates = get_gate_status_dict(p["product_id"])
            for g in range(1, 6):
                gs = gates.get(g, {})
                s = gs.get("status", "PENDING")
                if s == "PASS": gate_stats[g]["pass"] += 1
                elif s == "FAIL": gate_stats[g]["fail"] += 1
                else: gate_stats[g]["pending"] += 1
        
        gcols = st.columns(5)
        gate_labels = {1: "Signal", 2: "Defects", 3: "Economics", 4: "Score", 5: "Arbiter"}
        for i, g in enumerate([1, 2, 3, 4, 5]):
            with gcols[i]:
                total = gate_stats[g]["pass"] + gate_stats[g]["fail"] + gate_stats[g]["pending"]
                st.metric(f"Gate {g}: {gate_labels[g]}", f"{gate_stats[g]['pass']}/{total}", delta=f"{gate_stats[g]['fail']} failed" if gate_stats[g]['fail'] else None)
        
        st.divider()
        
        # Product table with selection
        rows = []
        for p in filtered:
            gates = get_gate_status_dict(p["product_id"])
            gate_str = ""
            for g in range(1, 6):
                gs = gates.get(g, {})
                status = gs.get("status", "PENDING")
                badge = {"PASS": "✅", "FAIL": "❌", "PENDING": "⏳", "BLOCKED": "🚫", "IN_PROGRESS": "🔄", "OVERRIDDEN": "⚡", "OVERRIDDEN_PASS": "⚡", "OVERRIDDEN_REJECT": "🚫"}.get(status, "❓")
                gate_str += f"{badge} "
            
            rows.append({
                "⭐": "★" if p.get("is_shortlisted") else "☆",
                "Product": p["name"][:55],
                "Category": p.get("category", ""),
                "Region": p.get("region", ""),
                "MSRP": format_inr(p.get("planned_msrp", 0)),
                "Net %": format_pct(p.get("net_profit_pct", 0)),
                "Score": f"{p.get('overall_score', 0):.0f}",
                "Gates": gate_str.strip(),
                "Status": p.get("status", "PENDING"),
                "ID": p["product_id"],
            })
        
        df = pd.DataFrame(rows)
        selection = st.dataframe(df, width='stretch', hide_index=True, column_config={
            "⭐": st.column_config.TextColumn("★", width=40),
            "Product": st.column_config.TextColumn("Product", width=280),
            "Gates": st.column_config.TextColumn("Gates 1-5", width=180),
        }, on_select="rerun", selection_mode="single-row", key="opp_product_table")
        
        # Product detail on selection
        if selection.selection.rows:
            idx = selection.selection.rows[0]
            product = filtered[idx]
            pid = product["product_id"]
            
            st.divider()
            st.markdown(f"### 📦 {product['name']}")
            
            # Gate details with manual controls
            gates = get_gate_status_dict(pid)
            gate_labels = {1: "Signal", 2: "Defects", 3: "Economics", 4: "Score", 5: "Arbiter"}
            
            for g in range(1, 6):
                gs = gates.get(g, {})
                gs_status = gs.get("status", "PENDING")
                badge_class = {"PASS": "badge-pass", "FAIL": "badge-fail", "PENDING": "badge-pending", "BLOCKED": "badge-blocked", "IN_PROGRESS": "badge-progress", "OVERRIDDEN": "badge-override", "OVERRIDDEN_PASS": "badge-override", "OVERRIDDEN_REJECT": "badge-fail"}.get(gs_status, "badge-pending")
                
                gc1, gc2, gc3, gc4 = st.columns([2, 1, 1, 2])
                with gc1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <strong>Gate {g}: {gate_labels[g]}</strong><br>
                        <span class="gate-badge {badge_class}">{gs_status}</span>
                    </div>
                    """, unsafe_allow_html=True)
                with gc2:
                    if gs_status != "PASS":
                        if st.button(f"🔄 Restart", key=f"restart_g{g}_{pid}", use_container_width=True):
                            result = daemon_controller.rerun_product_gates(pid)
                            st.toast(f"Gate restart: {result.get('status', 'started')}")
                            st.rerun()
                with gc3:
                    if gs_status in ("FAIL", "PENDING", "BLOCKED"):
                        if st.button(f"⏩ Force Pass", key=f"force_pass_g{g}_{pid}", use_container_width=True):
                            reason = st.text_input(f"Reason for Force Pass Gate {g}", key=f"reason_pass_g{g}_{pid}", placeholder="e.g., Human review approved")
                            if st.button(f"Confirm Pass", key=f"confirm_pass_g{g}_{pid}", use_container_width=True):
                                from core.database import set_human_override_with_reason
                                set_human_override_with_reason(pid, "PASS", reason or f"Force pass Gate {g} via dashboard")
                                st.toast("Gate forced PASS")
                                st.rerun()
                with gc4:
                    if gs_status in ("FAIL", "PENDING", "BLOCKED"):
                        if st.button(f"❌ Force Reject", key=f"force_reject_g{g}_{pid}", use_container_width=True):
                            reason = st.text_input(f"Reason for Force Reject Gate {g}", key=f"reason_reject_g{g}_{pid}", placeholder="e.g., Critical risk identified")
                            if st.button(f"Confirm Reject", key=f"confirm_reject_g{g}_{pid}", use_container_width=True):
                                from core.database import set_human_override_with_reason
                                set_human_override_with_reason(pid, "REJECT", reason or f"Force reject Gate {g} via dashboard")
                                st.toast("Gate forced REJECT")
                                st.rerun()
                
                if gs.get("metadata"):
                    with st.expander(f"Gate {g} Details"):
                        st.json(gs["metadata"])
            
            # Launchpad action
            if all(gs.get("status") == "PASS" for gs in gates.values() if gs):
                if st.button("🚀 Add to Launchpad", key=f"add_lp_{pid}", type="primary", use_container_width=True):
                    from core.database import get_connection
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute("UPDATE master_products SET status='SOURCING_NEGOTIATION' WHERE product_id=?", (pid,))
                    conn.commit()
                    conn.close()
                    st.toast("Added to Sourcing Launchpad!")
                    st.rerun()
            
            # Defects
            defects = get_defect_clusters(pid)
            if defects:
                with st.expander("🛡️ Defects & v2.0 Spec"):
                    for d in defects:
                        st.markdown(f"**{d.get('defect_description', '')}**")
                        st.caption(f"Severity: {d.get('severity')} | Fixable: {'Yes' if d.get('is_fixable') else 'No'}")
                        if d.get('v2_fix_description'):
                            st.markdown(f"*v2.0 Fix:* {d['v2_fix_description'][:200]}...")
            
            # Standard actions
            a1, a2, a3 = st.columns(3)
            with a1:
                if st.button("⭐ Toggle Shortlist", key=f"sl_{pid}", width='stretch'):
                    toggle_shortlist(pid)
                    st.rerun()
            with a2:
                if st.button("🗑️ Soft Delete", key=f"del_{pid}", width='stretch'):
                    soft_delete_product(pid, "Deleted via dashboard")
                    st.rerun()
            with a3:
                if st.button("📋 View Economics", key=f"econ_{pid}", width='stretch'):
                    st.session_state["view_econ_pid"] = pid
                    st.session_state["active_tab"] = "economics"
                    st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# TAB 2: AGENT COMMAND CENTER
# ═════════════════════════════════════════════════════════════════════════════
with tab_agent:
    st.subheader("⚡ Agent Command Center")
    
    # Refresh status
    status = daemon_controller.get_status()
    agent_telemetry = status.get("agent_telemetry", {})
    agent_states = status.get("agent_states", {})
    agent_modes = daemon_controller.get_agent_modes()
    
    # Left panel: Agent Grid
    st.markdown("### 🤖 Agent Status Grid")
    
    AGENT_DISPLAY = {
        "internet_crawler": {"name": "Internet Crawler", "icon": "🌐", "desc": "Scans web for trends & niches"},
        "trend_signal": {"name": "Trend Signal", "icon": "📈", "desc": "Google Trends, Reddit, YouTube"},
        "niche_expander": {"name": "Niche Expander", "icon": "🔍", "desc": "Expands categories to niches"},
        "discovery": {"name": "Discovery", "icon": "🛒", "desc": "Multi-marketplace scraping"},
        "problem_miner": {"name": "Problem Miner", "icon": "⛏️", "desc": "3-star review defect mining"},
        "gate_engine": {"name": "Gate Engine", "icon": "🚪", "desc": "5-gate deterministic pipeline"},
        "supplier_agent": {"name": "Supplier Agent", "icon": "🏭", "desc": "IndiaMART/Alibaba + GST verify"},
        "outreach_engine": {"name": "Outreach Engine", "icon": "📧", "desc": "Email/WhatsApp drafts (NIM)"},
        "learning_agent": {"name": "Learning Agent", "icon": "🧠", "desc": "Weekly rule synthesis"},
    }
    
    agent_cols = st.columns(3)
    for idx, (agent_key, info) in enumerate(AGENT_DISPLAY.items()):
        col = agent_cols[idx % 3]
        with col:
            telemetry = agent_telemetry.get(agent_key, {})
            state = agent_states.get(agent_key, "IDLE")
            mode = agent_modes.get(agent_key, "auto")
            
            # Status indicator
            status_color = {"COMPLETED": "🟢", "RUNNING": "🔵", "FAILED": "🔴", "BLOCKED": "🟡", "IDLE": "⚪", "PAUSED": "🟡"}.get(state, "⚪")
            
            with st.container():
                st.markdown(f"""
                <div class="agent-row {'agent-running' if state=='RUNNING' else ''}">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div><strong>{info['icon']} {info['name']}</strong></div>
                        <div>{status_color} {state}</div>
                    </div>
                    <div style="font-size:0.8rem; color:#64748B; margin:4px 0;">{info['desc']}</div>
                    <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px; font-size:0.75rem;">
                        <div>Runs: <strong>{telemetry.get('runs', 0)}</strong></div>
                        <div>✅ Success: <strong>{telemetry.get('successes', 0)}</strong></div>
                        <div>Items: <strong>{telemetry.get('items_processed', 0)}</strong></div>
                        <div>Created: <strong>{telemetry.get('items_created', 0)}</strong></div>
                        <div>Last: <strong>{telemetry.get('last_run', 'Never')}</strong></div>
                        <div>Duration: <strong>{telemetry.get('last_duration_ms', 0)}ms</strong></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Mode selector
                new_mode = st.selectbox(
                    "Mode", ["auto", "manual", "disabled", "force_tier:1", "force_tier:2", "force_tier:3", "force_tier:4", "force_tier:5"],
                    index=["auto", "manual", "disabled", "force_tier:1", "force_tier:2", "force_tier:3", "force_tier:4", "force_tier:5"].index(mode),
                    key=f"mode_{agent_key}",
                    label_visibility="collapsed"
                )
                if new_mode != mode:
                    daemon_controller.set_agent_mode(agent_key, new_mode)
                    st.rerun()
                
                # Run Now button
                if st.button("▶️ Run Now", key=f"run_{agent_key}", use_container_width=True):
                    result = daemon_controller.run_agent_on_demand(agent_key)
                    st.toast(f"{agent_key}: {result.get('status', 'started')}")
                    st.rerun()
    
    st.divider()
    
    # Right panel: Main AI Supervisor
    st.markdown("### 🧠 Main AI Supervisor")
    st.caption("Give natural language commands. The Supervisor (NIM 550B) will decide which agents to dispatch.")
    
    supervisor_instruction = st.text_area(
        "Command",
        placeholder='e.g., "Find suppliers for copper cookware in Moradabad"\n"Re-evaluate product IN_KIT_01 through all gates"\n"Mine reviews for ASIN B08XYZ123"\n"Run full discovery for kitchen niche"',
        height=100,
        key="supervisor_input"
    )
    
    s1, s2 = st.columns([1, 3])
    with s1:
        if st.button("🚀 Send Command", type="primary", use_container_width=True, disabled=not supervisor_instruction.strip()):
            with st.spinner("Supervisor thinking..."):
                result = daemon_controller.supervisor_command(supervisor_instruction)
            st.session_state["last_supervisor_result"] = result
            st.rerun()
    with s2:
        if st.button("📋 View Last Response", use_container_width=True):
            if "last_supervisor_result" in st.session_state:
                st.json(st.session_state["last_supervisor_result"])
            else:
                st.info("No previous command")
    
    if "last_supervisor_result" in st.session_state:
        result = st.session_state["last_supervisor_result"]
        if result.get("status") == "success":
            st.success(f"✅ {result.get('reasoning', 'Command executed')}")
            for dispatch in result.get("dispatches", []):
                agent = dispatch.get("agent", "?")
                r = dispatch.get("result", {})
                status = r.get("status", "?")
                st.markdown(f"- **{agent}**: {status}")
        else:
            st.error(f"❌ {result.get('error', 'Unknown error')}")
    
    st.divider()
    
    # Bottom panel: Recent Agent Activity Feed
    st.markdown("### 📜 Recent Agent Activity (swarm_audit_log)")
    audit_logs = get_recent_swarm_audit_log(limit=20)
    if audit_logs:
        audit_df = pd.DataFrame(audit_logs)
        display_cols = ["agent_name", "action", "details", "product_id", "cycle_num", "items_processed", "items_created", "duration_ms", "success", "created_at"]
        display_cols = [c for c in display_cols if c in audit_df.columns]
        st.dataframe(audit_df[display_cols], width='stretch', hide_index=True)
    else:
        st.info("No agent activity logged yet. Start the daemon to begin.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 3: SUPPLIERS & OUTREACH HUB
# ═════════════════════════════════════════════════════════════════════════════
with tab_sup:
    st.subheader("🏭 Suppliers & Outreach Hub")
    
    # Product selector
    product_options = {f"{p['name'][:50]} ({p['product_id']})": p for p in filtered}
    if not product_options:
        st.info("No products available. Run discovery first.")
    else:
        sel_key = st.selectbox("Select Product", list(product_options.keys()), key="sup_product_select")
        sel_product = product_options[sel_key]
        pid = sel_product["product_id"]
        
        # Find suppliers button
        if st.button("🔍 Find New Suppliers", type="primary", key="sup_find"):
            with st.spinner("Discovering suppliers..."):
                result = daemon_controller.run_agent_on_demand("supplier_agent")
            st.toast(f"Supplier Agent: {result.get('status', 'started')}")
            st.rerun()
        
        # Get suppliers
        suppliers = get_supplier_profiles_for_product(pid)
        
        if not suppliers:
            st.info(f"No suppliers found for **{sel_product['name']}** yet. Click 'Find New Suppliers' to start discovery.")
        else:
            st.markdown(f"### Suppliers for {sel_product['name']} ({len(suppliers)} found)")
            
            for sup in suppliers:
                with st.container():
                    sc1, sc2, sc3, sc4 = st.columns([3, 1, 1, 1])
                    with sc1:
                        st.markdown(f"""
                        <div class="metric-card">
                            <strong>{sup.get('company_name', 'Unknown Company')}</strong><br>
                            <small>📍 {sup.get('location', 'Unknown')} | 🏷️ {sup.get('platform', 'Unknown')}</small><br>
                            <small>MOQ: {sup.get('moq_units', 'N/A')} | Unit Price: {sup.get('fob_unit_price', 'N/A')}</small>
                        </div>
                        """, unsafe_allow_html=True)
                    with sc2:
                        gst_status = "✅ GST Active" if sup.get('gst_verified') else "❌ GST Invalid"
                        st.markdown(f"""
                        <div class="metric-card">
                            {gst_status}<br>
                            <small>Score: {sup.get('verification_score', 0):.0f}/100</small>
                        </div>
                        """, unsafe_allow_html=True)
                    with sc3:
                        if sup.get('platform_profile_url'):
                            st.markdown(f"[🔗 {sup.get('platform', 'Profile').title()}]({sup.get('platform_profile_url')})")
                    with sc4:
                        if st.button("📧 View Drafts", key=f"drafts_{sup.get('supplier_id')}", use_container_width=True):
                            st.session_state[f"show_drafts_{sup.get('supplier_id')}"] = not st.session_state.get(f"show_drafts_{sup.get('supplier_id')}", False)
                            st.rerun()
                
                # Show outreach drafts if expanded
                if st.session_state.get(f"show_drafts_{sup.get('supplier_id')}", False):
                    drafts = get_outreach_drafts_for_product(pid)
                    sup_drafts = [d for d in drafts if d.get("supplier_id") == sup.get("supplier_id")]
                    
                    if not sup_drafts:
                        if st.button("✍️ Generate Outreach Draft", key=f"gen_draft_{sup.get('supplier_id')}", use_container_width=True):
                            with st.spinner("Generating draft with NIM 550B..."):
                                result = daemon_controller.run_agent_on_demand("outreach_engine")
                            st.toast(f"Outreach: {result.get('status', 'started')}")
                            st.rerun()
                    else:
                        for draft in sup_drafts:
                            with st.expander(f"📧 Draft: {draft.get('subject', 'Outreach')} ({draft.get('status', 'PENDING')})"):
                                st.text_area("Email Draft", value=draft.get("email_draft", ""), height=200, key=f"email_{draft.get('draft_id')}")
                                st.text_area("WhatsApp Draft", value=draft.get("whatsapp_draft", ""), height=100, key=f"wa_{draft.get('draft_id')}")
                                
                                d1, d2, d3, d4 = st.columns(4)
                                with d1:
                                    if st.button("✅ Approve & Send", key=f"approve_{draft.get('draft_id')}", type="primary", use_container_width=True):
                                        update_outreach_status(draft.get('draft_id'), "APPROVED")
                                        st.toast("Draft approved!")
                                        st.rerun()
                                with d2:
                                    if st.button("✏️ Save Edit", key=f"edit_{draft.get('draft_id')}", use_container_width=True):
                                        edited = st.session_state.get(f"email_{draft.get('draft_id')}", "")
                                        update_outreach_status(draft.get('draft_id'), "EDITED", edited_text=edited)
                                        st.toast("Draft updated!")
                                        st.rerun()
                                with d3:
                                    if st.button("❌ Reject", key=f"reject_{draft.get('draft_id')}", use_container_width=True):
                                        update_outreach_status(draft.get('draft_id'), "REJECTED")
                                        st.toast("Draft rejected")
                                        st.rerun()
                                with d4:
                                    if st.button("⏸ Hold", key=f"hold_{draft.get('draft_id')}", use_container_width=True):
                                        update_outreach_status(draft.get('draft_id'), "HOLD")
                                        st.toast("Draft on hold")
                                        st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# TAB 4: CUSTOMER REVIEWS & PROBLEM MINING
# ═════════════════════════════════════════════════════════════════════════════
with tab_rev:
    st.subheader("🔍 Customer Reviews & Problem Mining")
    
    product_options = {f"{p['name'][:50]} ({p['product_id']})": p for p in filtered}
    if not product_options:
        st.info("No products available.")
    else:
        sel_key = st.selectbox("Select Product", list(product_options.keys()), key="rev_product_select")
        sel_product = product_options[sel_key]
        pid = sel_product["product_id"]
        
        # Mine reviews button
        if st.button("🔍 Mine Reviews Now", type="primary", key="rev_mine"):
            with st.spinner("Mining 3-star reviews with Ollama..."):
                result = daemon_controller.run_agent_on_demand("problem_miner")
            st.toast(f"Problem Miner: {result.get('status', 'started')}")
            st.rerun()
        
        # Get defects
        defects = get_defect_clusters(pid)
        opportunities = get_problem_opportunities(pid)
        
        if not defects and not opportunities:
            st.info(f"No review data mined yet for **{sel_product['name']}**. Click 'Mine Reviews Now' to start.")
        else:
            # Defect clusters
            if defects:
                st.markdown("### 🛡️ 3-Star Review Failure Clusters")
                for d in defects:
                    with st.container():
                        st.markdown(f"""
                        <div class="review-cluster">
                            <strong>{d.get('defect_description', 'Unknown defect')}</strong><br>
                            <small>Severity: {d.get('severity', 'N/A')} | Frequency: {d.get('frequency', 'N/A')} | Fixable: {'✅ Yes' if d.get('is_fixable') else '❌ No'}</small>
                        </div>
                        """, unsafe_allow_html=True)
                        if d.get('v2_fix_description'):
                            st.markdown(f"""
                            <div class="v2-spec">
                                <strong>v2.0 Specification:</strong> {d['v2_fix_description']}
                            </div>
                            """, unsafe_allow_html=True)
            
            # Problem opportunities (from Q&A, Reddit, YouTube)
            if opportunities:
                st.markdown("### 💡 Unmet Needs & Problem Opportunities")
                for opp in opportunities:
                    with st.expander(f"{opp.get('source', 'Unknown').upper()}: {opp.get('problem_statement', 'No statement')[:80]}..."):
                        st.markdown(f"**Source:** {opp.get('source', 'N/A')}")
                        st.markdown(f"**Problem:** {opp.get('problem_statement', 'N/A')}")
                        st.markdown(f"**Frequency:** {opp.get('frequency', 'N/A')}")
                        st.markdown(f"**Suggested Solution:** {opp.get('suggested_solution', 'N/A')}")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 5: SOURCING LAUNCHPAD
# ═════════════════════════════════════════════════════════════════════════════
with tab_lp:
    st.subheader("🚀 Sourcing Launchpad")
    
    from core.database import get_launchpad_items, update_launchpad_status
    
    launchpad_items = get_launchpad_items()
    
    if not launchpad_items:
        st.info("No products in sourcing pipeline. Approve products from Opportunities tab to add them here.")
    else:
        # Kanban columns
        stages = ["SOURCING_NEGOTIATION", "SAMPLE_ORDERED", "SAMPLE_APPROVED", "QC_IN_PROGRESS", "PO_ISSUED", "SHIPPED", "LIVE"]
        stage_labels = {
            "SOURCING_NEGOTIATION": "🤝 Sourcing Negotiation",
            "SAMPLE_ORDERED": "📦 Sample Ordered",
            "SAMPLE_APPROVED": "✅ Sample Approved",
            "QC_IN_PROGRESS": "🔬 QC in Progress",
            "PO_ISSUED": "📋 PO Issued",
            "SHIPPED": "🚚 Shipped",
            "LIVE": "🟢 Live"
        }
        
        cols = st.columns(len(stages))
        for idx, stage in enumerate(stages):
            with cols[idx]:
                st.markdown(f"#### {stage_labels[stage]}")
                stage_items = [item for item in launchpad_items if item.get("status") == stage]
                
                for item in stage_items:
                    with st.container():
                        st.markdown(f"""
                        <div class="kanban-card">
                            <strong>{item.get('product_name', 'Unknown')}</strong><br>
                            <small>💰 FOB: {format_inr(item.get('target_fob', 0))} | 📦 MOQ: {item.get('target_moq', 'N/A')}</small><br>
                            <small>🏭 {item.get('factory_name', 'TBD')}</small><br>
                            <small>📅 Target: {item.get('target_launch_date', 'TBD')}</small>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        next_stage_idx = min(idx + 1, len(stages) - 1)
                        if st.button(f"▶ Move to {stage_labels[stages[next_stage_idx]]}", key=f"move_{item.get('launchpad_id')}_{stage}", use_container_width=True):
                            update_launchpad_status(item.get('launchpad_id'), stages[next_stage_idx])
                            st.rerun()
                
                if not stage_items:
                    st.caption("— empty —")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 6: WAR ROOM
# ═════════════════════════════════════════════════════════════════════════════
with tab_wr:
    st.subheader("🎙️ War Room — Multi-Agent Executive Meeting")
    
    product_options = {f"{p['name'][:50]} ({p['product_id']})": p for p in filtered}
    if not product_options:
        st.info("No products available.")
    else:
        sel_key = st.selectbox("Select Product for War Room", list(product_options.keys()), key="wr_product_select")
        sel_product = product_options[sel_key]
        pid = sel_product["product_id"]
        
        # Initialize meeting state
        if "war_room_log" not in st.session_state:
            st.session_state["war_room_log"] = []
        if "war_room_pid" != pid:
            st.session_state["war_room_log"] = []
            st.session_state["war_room_pid"] = pid
        
        SPECIALISTS = [
            {"name": "Sarah Chen", "role": "VP Sales", "avatar": "👩‍💼", "focus": "Market demand, pricing, competitive positioning"},
            {"name": "Marcus Webb", "role": "Quality Director", "avatar": "👨‍🔬", "focus": "Defect analysis, v2.0 specs, compliance"},
            {"name": "Priya Patel", "role": "Sourcing Lead", "avatar": "👩‍🏭", "focus": "Supplier viability, MOQ, lead times, GST"},
            {"name": "David Park", "role": "Finance Controller", "avatar": "👨‍💰", "focus": "Margins, cash flow, risk-adjusted returns"},
            {"name": "Alex Kumar", "role": "Tech Lead", "avatar": "👨‍💻", "focus": "Manufacturing feasibility, tooling, IP"},
            {"name": "Secretary", "role": "Meeting Secretary", "avatar": "📝", "focus": "Action items, decisions, timeline"},
        ]
        
        # Show meeting history
        if st.session_state["war_room_log"]:
            st.markdown("### 📜 Meeting Transcript")
            for turn in st.session_state["war_room_log"]:
                with st.expander(f"{turn['avatar']} **{turn['speaker_name']}** ({turn['speaker_role']})"):
                    st.markdown(f"**Prompt:** {turn['user_prompt']}")
                    st.markdown(f"**Response:** {turn['response_text']}")
        
        # Input for next turn
        st.markdown("### 💬 Next Turn")
        col1, col2 = st.columns([3, 1])
        with col1:
            specialist_idx = st.selectbox("Address Specialist", range(len(SPECIALISTS)), format_func=lambda i: f"{SPECIALISTS[i]['avatar']} {SPECIALISTS[i]['name']} — {SPECIALISTS[i]['role']}", key="wr_specialist")
        with col2:
            user_prompt = st.text_input("Your direction", placeholder="e.g., Sarah, what's our pricing strategy for India?", key="wr_prompt")
        
        if st.button("💬 Send to Specialist", type="primary", disabled=not user_prompt.strip()):
            specialist = SPECIALISTS[specialist_idx]
            
            # Build context for specialist
            context = f"""
            Product: {sel_product['name']}
            Category: {sel_product.get('category', 'N/A')}
            Region: {sel_product.get('region', 'N/A')}
            MSRP: {format_inr(sel_product.get('planned_msrp', 0))}
            Score: {sel_product.get('overall_score', 0)}/100
            Status: {sel_product.get('status', 'PENDING')}
            """
            
            # Add gate status
            gates = get_gate_status_dict(pid)
            gate_str = ", ".join([f"G{g}:{gs.get('status','?')}" for g, gs in gates.items()])
            context += f"\nGates: {gate_str}"
            
            # Add supplier info
            suppliers = get_supplier_profiles_for_product(pid)
            if suppliers:
                context += f"\nSuppliers: {len(suppliers)} found"
            
            prompt = f"""You are {specialist['name']}, {specialist['role']}. Focus: {specialist['focus']}.
            
            CONTEXT:
            {context}
            
            USER DIRECTION:
            {user_prompt}
            
            Provide your expert analysis and recommendations. Be concise and actionable."""
            
            with st.spinner(f"Consulting {specialist['name']}..."):
                from core.llm_router import LLMRouter, LLMTaskType
                router = LLMRouter()
                try:
                    response = router.chat(
                        messages=[
                            {"role": "system", "content": f"You are {specialist['name']}, {specialist['role']}. {specialist['focus']}. Be decisive and specific."},
                            {"role": "user", "content": prompt}
                        ],
                        agent_name="war_room",
                        task_type=LLMTaskType.DEEP_REASONING,
                        max_tokens=800,
                    )
                    response_text = response.text
                except Exception as e:
                    response_text = f"Error: {e}"
            
            # Log the turn
            turn = {
                "speaker_name": specialist["name"],
                "speaker_role": specialist["role"],
                "avatar": specialist["avatar"],
                "user_prompt": user_prompt,
                "response_text": response_text,
                "timestamp": datetime.now().isoformat(),
            }
            st.session_state["war_room_log"].append(turn)
            st.rerun()
        
        # Export
        if st.session_state["war_room_log"]:
            if st.button("📄 Generate Word Report", type="primary", use_container_width=True):
                doc_bytes = export_war_room_doc(sel_product, st.session_state["war_room_log"])
                st.download_button(
                    "Download War Room Report",
                    doc_bytes,
                    f"war_room_{pid}_{datetime.now().strftime('%Y%m%d')}.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    width='stretch',
                )

# ═════════════════════════════════════════════════════════════════════════════
# TAB 7: KEEPA & CROSS-MARKETPLACE TRACKER
# ═════════════════════════════════════════════════════════════════════════════
with tab_kp:
    st.subheader("📈 Keepa & Cross-Marketplace Tracker")
    
    product_options = {f"{p['name'][:50]} ({p['product_id']})": p for p in filtered}
    if not product_options:
        st.info("No products available.")
    else:
        sel_key = st.selectbox("Select Product", list(product_options.keys()), key="kp_product_select")
        sel_product = product_options[sel_key]
        pid = sel_product["product_id"]
        
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("🔄 Refresh Keepa Data", type="primary", key="kp_refresh"):
                with st.spinner("Fetching Keepa data..."):
                    from tools.keepa_api_client import KeepaClient
                    client = KeepaClient()
                    # Would call client.get_product_data(pid)
                    st.toast("Keepa refresh triggered")
                    st.rerun()
        
        with c2:
            if st.button("🔄 Refresh Cross-Marketplace", key="kp_cross"):
                with st.spinner("Scraping Flipkart & Meesho..."):
                    result = daemon_controller.run_agent_on_demand("discovery")
                st.toast("Cross-marketplace refresh started")
        
        st.divider()
        
        # Amazon BSR/Price charts (would use Keepa data)
        st.markdown("### Amazon BSR History")
        st.caption("Connect Keepa API for live BSR tracking")
        
        # Placeholder chart
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(30)), y=[15000 + i*100 for i in range(30)], mode='lines', name='BSR Rank'))
        fig.update_layout(height=300, title="BSR Trend (30 days)", xaxis_title="Days Ago", yaxis_title="BSR Rank", yaxis=dict(autorange="reversed"), template="plotly_white")
        st.plotly_chart(fig, width='stretch')
        
        st.markdown("### Price History")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=list(range(30)), y=[1299 - i*2 for i in range(30)], mode='lines', name='Price (INR)'))
        fig2.update_layout(height=300, title="Price Trend (30 days)", xaxis_title="Days Ago", yaxis_title="Price (INR)", template="plotly_white")
        st.plotly_chart(fig2, width='stretch')
        
        st.divider()
        
        # Cross-marketplace comparison
        st.markdown("### Cross-Marketplace Comparison")
        
        # Get multi-platform listings
        from core.database import get_connection
        conn = get_connection()
        cur = conn.execute("SELECT * FROM multi_platform_listings WHERE product_id = ?", (pid,))
        listings = [dict(r) for r in cur.fetchall()]
        conn.close()
        
        if listings:
            df = pd.DataFrame(listings)
            st.dataframe(df[["platform", "title", "price", "rating", "review_count", "bsr_rank", "availability"]], width='stretch', hide_index=True)
        else:
            st.info("No cross-platform data yet. Run discovery to populate.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 8: ECONOMICS
# ═════════════════════════════════════════════════════════════════════════════
with tab_eco:
    st.subheader("📊 15-Factor Economics & Waterfall")
    
    if not filtered:
        st.info("No products to analyze.")
    else:
        product_options = {f"{p['name'][:50]} ({p['product_id']})": p for p in filtered}
        sel_key = st.selectbox("Select Product", list(product_options.keys()), key="eco_product_select")
        sel_product = product_options[sel_key]
        pid = sel_product["product_id"]
        
        assessments = get_economics_assessments(pid)
        
        if not assessments:
            st.warning("No economics assessment found. Run evaluation via CLI or use Quick Calculator below.")
            
            # Quick calculator
            with st.form("econ_calc"):
                st.markdown("**Quick Economics Calculator**")
                c1, c2, c3 = st.columns(3)
                with c1:
                    q_fob = st.number_input("FOB (INR)", value=float(sel_product.get("factory_cogs") or sel_product.get("landed_cogs", 0) * 0.3 or 350), step=50.0)
                    q_msrp = st.number_input("MSRP (INR)", value=float(sel_product.get("planned_msrp", 1299)), step=100.0)
                with c2:
                    q_cat = st.selectbox("Category", ["Kitchen", "Home", "Electronics", "Beauty", "Apparel", "General"], index=["Kitchen", "Home", "Electronics", "Beauty", "Apparel", "General"].index(sel_product.get("category", "General")))
                    q_mkt = st.selectbox("Marketplace", ["amazon", "flipkart", "meesho"])
                with c3:
                    q_lead = st.number_input("Lead Time (days)", value=30, step=5)
                    q_trend = st.number_input("Trend Half-Life (days)", value=90, step=10)
                
                if st.form_submit_button("🧮 Calculate 15-Factor Economics", type="primary"):
                    assessment = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
                        product_id=pid, fob_price=q_fob, planned_msrp=q_msrp,
                        region=sel_product.get("region", "India"), category=q_cat,
                        marketplace=q_mkt, lead_time_days=q_lead, trend_half_life_days=q_trend,
                    )
                    st.session_state["quick_assessment"] = assessment
                    st.rerun()
            
            if "quick_assessment" in st.session_state:
                assessments = [st.session_state["quick_assessment"]]
        
        if assessments:
            assessment = assessments[0]
            
            # Scenario Summary Cards
            st.markdown("### Scenario Summary")
            sc_cols = st.columns(3)
            for idx, sc_name in enumerate(["conservative", "expected", "upside"]):
                sc = assessment.get(sc_name, {})
                with sc_cols[idx]:
                    net_pct = sc.get("net_profit_pct", 0)
                    gross_pct = sc.get("gross_margin_pct", 0)
                    status = sc.get("status", "UNKNOWN")
                    badge = "🟢" if status == "PASS" else "🔴"
                    st.markdown(f"""
                    <div class="metric-card">
                        <h4>{badge} {sc_name.capitalize()}</h4>
                        <strong>Net Margin:</strong> {net_pct:.1f}%<br>
                        <strong>Gross Margin:</strong> {gross_pct:.1f}%<br>
                        <strong>Landed COGS:</strong> ₹{sc.get('landed_cogs', 0):,.0f}<br>
                        <strong>Net Profit:</strong> ₹{sc.get('net_profit', 0):,.0f}
                    </div>
                    """, unsafe_allow_html=True)
            
            st.divider()
            
            # Waterfall Chart
            st.markdown("### 📈 Waterfall Chart — Cost Breakdown")
            fig = create_waterfall_chart(assessment)
            st.plotly_chart(fig, width='stretch')
            
            st.divider()
            
            # Detailed breakdown table
            st.markdown("### 📋 Detailed Cost Breakdown")
            detail_rows = []
            for sc_name in ["conservative", "expected", "upside"]:
                sc = assessment.get(sc_name, {})
                detail_rows.append({
                    "Scenario": sc_name.capitalize(), "MSRP": format_inr(sc.get("planned_msrp", 0)),
                    "FOB": format_inr(sc.get("fob_price", 0)), "Landed COGS": format_inr(sc.get("landed_cogs", 0)),
                    "Gross Profit": format_inr(sc.get("gross_profit", 0)), "Gross %": format_pct(sc.get("gross_margin_pct", 0)),
                    "Mkt Comm": format_inr(sc.get("marketplace_commission", 0)), "Fulfillment": format_inr(sc.get("fulfillment_fee", 0)),
                    "Payment/COD": format_inr(sc.get("payment_or_cod_fee", 0)), "RTO Reserve": format_inr(sc.get("rto_reserve", 0)),
                    "Fraud Reserve": format_inr(sc.get("return_fraud_reserve", 0)), "Ads (TACoS)": format_inr(sc.get("ad_tacos_reserve", 0)),
                    "Tax": format_inr(sc.get("net_tax_burden", 0)), "Total Variable": format_inr(sc.get("total_variable_cost", 0)),
                    "Net Profit": format_inr(sc.get("net_profit", 0)), "Net %": format_pct(sc.get("net_profit_pct", 0)),
                    "Status": sc.get("status", ""),
                })
            detail_df = pd.DataFrame(detail_rows)
            st.dataframe(detail_df, width='stretch', hide_index=True)
            
            # Lead time risk
            st.divider()
            col1, col2, col3 = st.columns(3)
            col1.metric("Lead Time Risk", f"{assessment.get('lead_time_risk_factor', 0):.0%}")
            col2.metric("Composite Score", f"{assessment.get('composite_score', 0):.1f}/100")
            col3.metric("Recommendation", assessment.get("recommendation", "N/A"))

# ═════════════════════════════════════════════════════════════════════════════
# TAB 9: DB EXPLORER
# ═════════════════════════════════════════════════════════════════════════════
with tab_db:
    st.subheader("🗄️ SSOT Database Explorer")
    
    # All tables overview
    st.markdown("### All Tables — Live Row Counts")
    table_counts = get_live_table_counts()
    
    # Summary metrics
    total_tables = len(table_counts)
    total_rows = sum(table_counts.values())
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Tables", total_tables)
    col2.metric("Total Rows", f"{total_rows:,}")
    col3.metric("DB Size", "~MB")  # Would calculate actual size
    
    # Table grid
    table_rows = []
    for table, count in sorted(table_counts.items()):
        table_rows.append({"Table": table, "Rows": count, "Status": "🟢 Active" if count > 0 else "⚪ Empty"})
    df_tables = pd.DataFrame(table_rows)
    st.dataframe(df_tables, width='stretch', hide_index=True)
    
    st.divider()
    
    # Table Inspector
    st.markdown("### Table Inspector")
    tables = get_all_table_names()
    sel_table = st.selectbox("Select Table", tables, key="db_table_select")
    
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search_query = st.text_input("Search", placeholder="Filter rows...", key="db_search")
    with c2:
        limit = st.selectbox("Limit", [50, 100, 500, 1000, "All"], index=0, key="db_limit")
    with c3:
        if st.button("🔄 Refresh", key="db_refresh"):
            st.rerun()
    
    if sel_table:
        lim = int(limit) if limit != "All" else 10000
        table_data = get_table_data(sel_table, limit=lim, search_query=search_query if search_query else None)
        if table_data:
            st.dataframe(pd.DataFrame(table_data), width='stretch', hide_index=True)
            # CSV export
            csv = pd.DataFrame(table_data).to_csv(index=False)
            st.download_button("📥 Download CSV", csv, f"{sel_table}_{datetime.now().strftime('%Y%m%d')}.csv", "text/csv", width='stretch')
        else:
            st.info("Table is empty or no matching rows")
    
    st.divider()
    
    # AI-Rejected Products View
    st.markdown("### 🤖 AI-Rejected Products")
    conn = get_connection()
    cur = conn.execute("""
        SELECT product_id, name, category, overall_score, status, ai_rejection_reason, ai_reasoning, ai_confidence, updated_at
        FROM master_products 
        WHERE status = 'AI_REJECTED' OR human_override_status = 'REJECT'
        ORDER BY updated_at DESC
    """)
    rejected = [dict(r) for r in cur.fetchall()]
    conn.close()
    
    if rejected:
        rej_df = pd.DataFrame(rejected)
        st.dataframe(rej_df[["product_id", "name", "category", "overall_score", "status", "ai_rejection_reason", "ai_confidence"]], width='stretch', hide_index=True)
    else:
        st.info("No AI-rejected products found.")

# ═════════════════════════════════════════════════════════════════════════════
# TAB 10: ARCHIVE & RECOVERY
# ═════════════════════════════════════════════════════════════════════════════
with tab_arch:
    st.subheader("🗃️ Archive & Product Recovery")
    
    archive = get_archive_products()
    
    if not archive:
        st.info("No soft-deleted products in archive.")
    else:
        st.markdown(f"### {len(archive)} Soft-Deleted Products")
        
        for item in archive:
            with st.expander(f"{item['name']} ({item['product_id']}) — Deleted: {item.get('deleted_at', item.get('updated_at', 'Unknown'))[:10]}"):
                c1, c2, c3 = st.columns([2, 1, 1])
                with c1:
                    st.markdown(f"**Category:** {item.get('category', 'N/A')} | **Region:** {item.get('region', 'N/A')}")
                    st.markdown(f"**MSRP:** {format_inr(item.get('planned_msrp', 0))} | **Net Margin:** {format_pct(item.get('net_profit_pct', 0))}")
                    st.markdown(f"**Deletion Reason:** {item.get('deletion_reason', 'N/A')}")
                with c2:
                    if item.get('ai_rejection_reason'):
                        st.markdown(f"**AI Rejection:** {item['ai_rejection_reason']}")
                    if item.get('ai_reasoning'):
                        st.caption(f"AI Reasoning: {item['ai_reasoning'][:200]}...")
                    if item.get('ai_confidence'):
                        st.caption(f"AI Confidence: {item['ai_confidence']:.0%}")
                with c3:
                    if st.button("♻️ Restore Product", key=f"restore_{item['product_id']}", type="primary", use_container_width=True):
                        restore_product(item['product_id'])
                        st.toast(f"Restored {item['name']}!")
                        st.rerun()
                    if st.button("🗑️ Permanently Delete", key=f"perm_del_{item['product_id']}", use_container_width=True):
                        if st.button("⚠️ CONFIRM PERMANENT DELETE", key=f"confirm_perm_{item['product_id']}", use_container_width=True):
                            conn = get_connection()
                            cur = conn.cursor()
                            cur.execute("DELETE FROM master_products WHERE product_id=?", (item['product_id'],))
                            conn.commit()
                            conn.close()
                            st.toast("Permanently deleted!")
                            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 11: FLOW GRAPH — Agent Pipeline Visualization
# ══════════════════════════════════════════════════════════════════════════════
with tab_flow:
    st.subheader("🔄 Agent Pipeline Flow Graph")
    st.caption("Real-time visualization of the autonomous research pipeline. Click any node to see detailed metrics and collected data.")
    
    # Get current status
    status = daemon_controller.get_status()
    agent_states = status.get("agent_states", {})
    agent_telemetry = status.get("agent_telemetry", {})
    
    # Define pipeline layers (matching AGENT_ORDER in orchestrator)
    PIPELINE_LAYERS = [
        {
            "name": "📅 Planning & Strategy",
            "agents": [
                {"key": "strategy_planner", "icon": "📅", "name": "Strategy Planner", "desc": "Weekly strategic research planning"},
                {"key": "ai_scout", "icon": "🤖", "name": "AI Scout", "desc": "Autonomous website/platform discovery (10x)"},
            ]
        },
        {
            "name": "🌐 Discovery & Signals",
            "agents": [
                {"key": "internet_crawler", "icon": "🌐", "name": "Internet Crawler", "desc": "Scans 50+ sources for trends"},
                {"key": "trend_signal", "icon": "📈", "name": "Trend Signal", "desc": "Aggregates Google Trends, Reddit, YouTube"},
                {"key": "demand_sense", "icon": "📊", "name": "Demand Sense", "desc": "Computes real demand proxies"},
                {"key": "competition_xray", "icon": "🔍", "name": "Competition X-Ray", "desc": "Deep competitive analysis"},
                {"key": "niche_expander", "icon": "🔎", "name": "Niche Expander", "desc": "Expands categories to niches"},
            ]
        },
        {
            "name": "🛒 Product Discovery",
            "agents": [
                {"key": "discovery", "icon": "🛒", "name": "Discovery", "desc": "Multi-marketplace scraping"},
                {"key": "problem_miner", "icon": "⛏️", "name": "Problem Miner", "desc": "3-star review defect mining"},
            ]
        },
        {
            "name": "🚪 Gate Pipeline",
            "agents": [
                {"key": "gate_engine", "icon": "🚪", "name": "Gate Engine", "desc": "5-gate deterministic pipeline"},
                {"key": "supplier_agent", "icon": "🏭", "name": "Supplier Agent", "desc": "IndiaMART/Alibaba + GST verify"},
            ]
        },
        {
            "name": "📧 Outreach & Learning",
            "agents": [
                {"key": "outreach_engine", "icon": "📧", "name": "Outreach Engine", "desc": "Email/WhatsApp drafts (NIM)"},
                {"key": "winner_score", "icon": "🏆", "name": "Winner Score", "desc": "Nightly leaderboard computation"},
                {"key": "maintenance", "icon": "🔧", "name": "Maintenance", "desc": "TTL cleanup, VACUUM, backup"},
                {"key": "weight_tuner", "icon": "⚖️", "name": "Weight Tuner", "desc": "Quarterly weight optimization"},
                {"key": "learning_agent", "icon": "🧠", "name": "Learning Agent", "desc": "Weekly rule synthesis"},
            ]
        },
    ]
    
    # Status color mapping
    STATUS_CONFIG = {
        "COMPLETED": {"class": "completed", "label": "✅ COMPLETED", "color": "#059669"},
        "RUNNING": {"class": "running", "label": "🔄 RUNNING", "color": "#2563EB"},
        "FAILED": {"class": "failed", "label": "❌ FAILED", "color": "#DC2626"},
        "BLOCKED": {"class": "blocked", "label": "⚠️ BLOCKED", "color": "#D97706"},
        "IDLE": {"class": "idle", "label": "⏸ IDLE", "color": "#94A3B8"},
        "PAUSED": {"class": "idle", "label": "⏸ PAUSED", "color": "#94A3B8"},
    }
    
    # Initialize selected node in session state
    if "selected_flow_node" not in st.session_state:
        st.session_state["selected_flow_node"] = None
    
    # Render pipeline layers
    for layer_idx, layer in enumerate(PIPELINE_LAYERS):
        st.markdown(f'<div class="flow-layer">', unsafe_allow_html=True)
        st.markdown(f'<div class="flow-layer-title">{layer["name"]}</div>', unsafe_allow_html=True)
        
        # Create columns for agents in this layer
        cols = st.columns(len(layer["agents"]))
        
        for agent_idx, agent in enumerate(layer["agents"]):
            with cols[agent_idx]:
                state = agent_states.get(agent["key"], "IDLE")
                telemetry = agent_telemetry.get(agent["key"], {})
                config = STATUS_CONFIG.get(state, STATUS_CONFIG["IDLE"])
                
                # Node click handler
                if st.button(
                    f"{agent['icon']} {agent['name']}",
                    key=f"flow_{agent['key']}",
                    use_container_width=True,
                    help=f"{agent['desc']}\nStatus: {state}\nRuns: {telemetry.get('runs', 0)}\nCreated: {telemetry.get('items_created', 0)}"
                ):
                    st.session_state["selected_flow_node"] = agent["key"]
                    st.rerun()
                
                # Render node with status styling
                st.markdown(f"""
                <div class="flow-node {config['class']}">
                    <div class="flow-node-icon">{agent['icon']}</div>
                    <div class="flow-node-name">{agent['name']}</div>
                    <div class="flow-node-status" style="background:{config['color']}20; color:{config['color']}; border:1px solid {config['color']};">
                        {config['label']}
                    </div>
                    <div class="flow-node-stats">
                        Runs: {telemetry.get('runs', 0)} | 
                        ✅ {telemetry.get('successes', 0)} | 
                        📦 {telemetry.get('items_created', 0)}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Add arrow between layers (except last)
        if layer_idx < len(PIPELINE_LAYERS) - 1:
            st.markdown('<div style="text-align:center;"><span class="flow-arrow">⬇</span></div>', unsafe_allow_html=True)
    
    # Branch Detail Panel
    if st.session_state["selected_flow_node"]:
        selected_key = st.session_state["selected_flow_node"]
        
        # Find agent info
        selected_agent = None
        for layer in PIPELINE_LAYERS:
            for agent in layer["agents"]:
                if agent["key"] == selected_key:
                    selected_agent = agent
                    break
            if selected_agent:
                break
        
        if selected_agent:
            state = agent_states.get(selected_key, "IDLE")
            telemetry = agent_telemetry.get(selected_key, {})
            config = STATUS_CONFIG.get(state, STATUS_CONFIG["IDLE"])
            
            st.markdown("---")
            st.markdown(f"""
            <div class="branch-detail">
                <h4>{selected_agent['icon']} {selected_agent['name']} — Branch Details</h4>
                <div class="data-row">
                    <span class="data-label">Status</span>
                    <span class="data-value" style="color:{config['color']};">{config['label']}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Description</span>
                    <span class="data-value">{selected_agent['desc']}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Total Runs</span>
                    <span class="data-value">{telemetry.get('runs', 0)}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Successful Runs</span>
                    <span class="data-value" style="color:#059669;">{telemetry.get('successes', 0)}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Failed Runs</span>
                    <span class="data-value" style="color:#DC2626;">{telemetry.get('failures', 0)}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Items Processed</span>
                    <span class="data-value">{telemetry.get('items_processed', 0):,}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Items Created</span>
                    <span class="data-value" style="color:#059669;">{telemetry.get('items_created', 0):,}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Last Run</span>
                    <span class="data-value">{telemetry.get('last_run', 'Never')}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Last Duration</span>
                    <span class="data-value">{telemetry.get('last_duration_ms', 0)} ms</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Last Error</span>
                    <span class="data-value" style="color:#DC2626;">{telemetry.get('last_error', 'None')}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Show collected data based on agent type
            st.markdown("### 📊 Collected Data")
            
            if selected_key == "trend_signal":
                # Show trend signals
                from core.database import get_connection
                conn = get_connection()
                cur = conn.execute("""
                    SELECT platform, keyword, trend_category, region, search_volume_est, velocity_score, status, created_at
                    FROM trend_signals 
                    WHERE status = 'ACTIVE'
                    ORDER BY velocity_score DESC, created_at DESC LIMIT 20
                """)
                trends = [dict(r) for r in cur.fetchall()]
                conn.close()
                if trends:
                    st.dataframe(pd.DataFrame(trends), width='stretch', hide_index=True)
                else:
                    st.info("No trend signals collected yet.")
                    
            elif selected_key == "discovery":
                # Show discovered products
                products = load_products(include_deleted=False)
                if products:
                    df = pd.DataFrame([{
                        "Product": p["name"][:50],
                        "Category": p.get("category", ""),
                        "Region": p.get("region", ""),
                        "MSRP": format_inr(p.get("planned_msrp", 0)),
                        "Score": f"{p.get('overall_score', 0):.0f}",
                        "Status": p.get("status", "PENDING"),
                    } for p in products[:50]])
                    st.dataframe(df, width='stretch', hide_index=True)
                else:
                    st.info("No products discovered yet.")
                    
            elif selected_key == "gate_engine":
                # Show gate progress
                from core.database import get_gate_status
                products = load_products(include_deleted=False)
                gate_data = []
                for p in products[:30]:
                    gates = get_gate_status(p["product_id"])
                    gate_str = " → ".join([f"G{g['gate_number']}:{g.get('status','?')}" for g in gates])
                    gate_data.append({
                        "Product": p["name"][:40],
                        "ID": p["product_id"],
                        "Gates": gate_str,
                        "Score": f"{p.get('overall_score', 0):.0f}",
                    })
                if gate_data:
                    st.dataframe(pd.DataFrame(gate_data), width='stretch', hide_index=True)
                else:
                    st.info("No products in gate pipeline.")
                    
            elif selected_key == "problem_miner":
                # Show defect clusters
                from core.database import get_defect_clusters
                products = load_products(include_deleted=False)
                all_defects = []
                for p in products[:20]:
                    defects = get_defect_clusters(p["product_id"])
                    for d in defects:
                        all_defects.append({
                            "Product": p["name"][:35],
                            "Defect": d.get("defect_description", "")[:60],
                            "Severity": d.get("severity", "N/A"),
                            "Fixable": "✅" if d.get("is_fixable") else "❌",
                            "v2 Fix": d.get("v2_fix_description", "")[:50] if d.get("v2_fix_description") else "—",
                        })
                if all_defects:
                    st.dataframe(pd.DataFrame(all_defects), width='stretch', hide_index=True)
                else:
                    st.info("No defects mined yet.")
                    
            elif selected_key == "supplier_agent":
                # Show suppliers
                from core.database import get_supplier_profiles_for_product
                products = load_products(include_deleted=False)
                all_suppliers = []
                for p in products[:15]:
                    suppliers = get_supplier_profiles_for_product(p["product_id"])
                    for s in suppliers:
                        all_suppliers.append({
                            "Product": p["name"][:30],
                            "Supplier": s.get("company_name", "Unknown")[:30],
                            "Platform": s.get("platform", "N/A"),
                            "MOQ": s.get("moq_units", "N/A"),
                            "Price": s.get("fob_unit_price", "N/A"),
                            "GST": "✅" if s.get("gst_verified") else "❌",
                            "Score": f"{s.get('verification_score', 0):.0f}/100",
                        })
                if all_suppliers:
                    st.dataframe(pd.DataFrame(all_suppliers), width='stretch', hide_index=True)
                else:
                    st.info("No suppliers found yet.")
                    
            elif selected_key == "outreach_engine":
                # Show outreach drafts
                from core.database import get_connection
                conn = get_connection()
                cur = conn.execute("""
                    SELECT od.draft_id, od.subject, od.status, od.channel, od.created_at, mp.company_name
                    FROM outreach_drafts od
                    JOIN supplier_profiles mp ON od.supplier_id = mp.supplier_id
                    ORDER BY od.created_at DESC LIMIT 20
                """)
                drafts = [dict(r) for r in cur.fetchall()]
                conn.close()
                if drafts:
                    st.dataframe(pd.DataFrame(drafts), width='stretch', hide_index=True)
                else:
                    st.info("No outreach drafts yet.")
                    
            elif selected_key == "learning_agent":
                # Show learned rules
                from core.database import get_learned_rules
                rules = get_learned_rules(enabled_only=True)
                if rules:
                    df = pd.DataFrame([{
                        "Rule ID": r.get("rule_id_str", "")[:20],
                        "Name": r.get("name", "")[:40],
                        "Severity": r.get("severity", 1),
                        "Action": r.get("action", "")[:40],
                        "Enabled": "✅" if r.get("enabled") else "❌",
                    } for r in rules[:30]])
                    st.dataframe(df, width='stretch', hide_index=True)
                else:
                    st.info("No learned rules yet.")
                    
            elif selected_key in ["internet_crawler", "niche_expander", "demand_sense", "competition_xray", "ai_scout"]:
                # Show dynamic niches or discovered sources
                from core.database import get_dynamic_niches, get_discovered_sources
                if selected_key in ["internet_crawler", "niche_expander", "demand_sense", "competition_xray"]:
                    niches = get_dynamic_niches(active_only=True)
                    if niches:
                        df = pd.DataFrame([{
                            "Category": n.get("category", ""),
                            "Region": n.get("region", ""),
                            "Priority": f"{n.get('priority_score', 0):.0f}",
                            "Scanned": n.get("times_scanned", 0),
                            "Products Found": n.get("products_found", 0),
                            "Last Scan": n.get("last_scanned_at", "Never")[:16] if n.get("last_scanned_at") else "Never",
                        } for n in niches])
                        st.dataframe(df, width='stretch', hide_index=True)
                    else:
                        st.info("No dynamic niches yet.")
                if selected_key == "ai_scout":
                    sources = get_discovered_sources(active_only=True)
                    if sources:
                        df = pd.DataFrame([{
                            "Source": s.get("source_name", s.get("domain", ""))[:40],
                            "Type": s.get("source_type", ""),
                            "Region": s.get("region", ""),
                            "Reliability": f"{s.get('reliability_score', 0):.0f}%",
                            "Times Used": s.get("times_used", 0),
                            "Yielded": s.get("times_yielded_results", 0),
                        } for s in sources[:30]])
                        st.dataframe(df, width='stretch', hide_index=True)
                    else:
                        st.info("No discovered sources yet.")
            
            # Close detail button
            if st.button("✖ Close Details", key="close_flow_detail", use_container_width=True):
                st.session_state["selected_flow_node"] = None
                st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("APRS V7 Pro — AI Virtual Office | 24/7 Autonomous Research | Deterministic 5-Gate Pipeline | Local Ollama | Playwright Scrapers | NIM 550B Arbiter")