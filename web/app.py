"""
web/app.py — APRS V6 Pro — 4-Tab Streamlit Dashboard.

Tabs:
1. Research — Discovery, niches, products, gate status
2. Economics — 15-Factor 3-Scenario waterfall charts, P&L
3. Dossiers — Ranked product dossiers with export (Word, Excel)
4. Settings — Configuration, API keys, thresholds
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
    set_human_override, get_gate_status, get_current_gate,
    get_defect_clusters, get_economics_assessments,
    get_dynamic_niches, get_seed_keywords, get_discovered_sources,
)
from core.economics_engine import Comprehensive15FactorEconomics
from core.gate_engine import GateEngine
from core.rule_engine import create_rule_engine
from core.validation import CanonicalProduct

logger = logging.getLogger("aprs.webapp")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s — %(message)s")

# ── Init DB ───────────────────────────────────────────────────────────────────
init_db()

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="APRS V6 Pro — E-Commerce Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background: #F8FAFC; }
    .block-container { padding-top: 1rem !important; max-width: 100% !important; }
    .metric-card { background:#FFFFFF; border-radius:10px; padding:14px 18px; border:1px solid #E2E8F0; margin-bottom:8px; }
    .gate-badge { display:inline-block; padding:2px 10px; border-radius:12px; font-size:0.78rem; font-weight:700; margin:2px; }
    .badge-pass { background:#D1FAE5; color:#065F46; }
    .badge-fail { background:#FEE2E2; color:#991B1B; }
    .badge-pending { background:#E2E8F0; color:#475569; }
    .badge-blocked { background:#FEF3C7; color:#92400E; }
    .badge-progress { background:#DBEAFE; color:#1E40AF; }
    .score-big { font-size:2.5rem; font-weight:800; text-align:center; }
    .score-proceed { color:#059669; }
    .score-marginal { color:#D97706; }
    .score-reject { color:#DC2626; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { padding: 10px 24px; border-radius: 8px 8px 0 0; }
    .stTabs [aria-selected="true"] { background: #2563EB !important; color: white !important; }
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
    """Get gate status as dict keyed by gate number."""
    gate_list = get_gate_status(product_id)
    return {g["gate_number"]: g for g in gate_list}

def create_waterfall_chart(assessment: Dict) -> go.Figure:
    """Create Plotly waterfall chart for 3-scenario economics."""
    scenarios = ["Conservative", "Expected", "Upside"]
    
    fig = make_subplots(
        rows=1, cols=3,
        subplot_titles=scenarios,
        horizontal_spacing=0.08,
    )
    
    colors = {
        "revenue": "#059669",
        "cogs": "#DC2626",
        "fees": "#D97706",
        "marketing": "#7C3AED",
        "tax": "#EA580C",
        "profit": "#059669",
    }
    
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
        
        # Waterfall values
        x_labels = ["MSRP", "COGS", "Comm.", "Fulfill.", "Payment", "RTO", "Fraud", "Ads", "Tax", "Net Profit"]
        y_values = [msrp, -landed_cogs, -marketplace_comm, -fulfillment, -payment_fee, -rto, -fraud, -ads, -tax, net_profit]
        
        bar_colors = []
        for i, v in enumerate(y_values):
            if v > 0:
                bar_colors.append(colors["revenue"])
            elif i == 1:
                bar_colors.append(colors["cogs"])
            elif i in (2, 3):
                bar_colors.append(colors["fees"])
            elif i == 7:
                bar_colors.append(colors["marketing"])
            elif i == 8:
                bar_colors.append(colors["tax"])
            else:
                bar_colors.append(colors["profit"])
        
        fig.add_trace(
            go.Bar(
                name=scenario,
                x=x_labels,
                y=y_values,
                marker_color=bar_colors,
                text=[f"₹{abs(v):,.0f}" for v in y_values],
                textposition="auto",
                showlegend=False,
            ),
            row=1, col=col
        )
        
        # Add net profit annotation
        fig.add_annotation(
            x=0.5, y=net_profit,
            text=f"Net: ₹{net_profit:,.0f} ({sc_data.get('net_profit_pct', 0):.1f}%)",
            showarrow=True,
            arrowhead=2,
            row=1, col=col,
            font=dict(size=11, color=colors["profit"] if net_profit > 0 else colors["cogs"]),
        )
    
    fig.update_layout(
        height=450,
        title_text="15-Factor Economics Waterfall — 3 Scenarios",
        template="plotly_white",
        margin=dict(t=60, b=40, l=40, r=40),
    )
    
    fig.update_xaxes(tickangle=-45)
    fig.update_yaxes(title_text="Amount (INR)")
    
    return fig

def create_score_radar(breakdown: Dict) -> go.Figure:
    """Create radar chart for score breakdown."""
    categories = list(breakdown.keys())
    values = list(breakdown.values())
    
    # Max values per category
    max_values = {
        "market_signal": 25,
        "review_quality": 20,
        "margin_safety": 40,
        "defect_fixability": 10,
        "competition_density": 5,
    }
    
    normalized = [v / max_values.get(c, 1) * 100 for c, v in zip(categories, values)]
    
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=normalized + [normalized[0]],
        theta=categories + [categories[0]],
        fill='toself',
        name='Score Breakdown',
        line_color='#2563EB',
        fillcolor='rgba(37, 99, 235, 0.2)',
    ))
    
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        height=350,
        margin=dict(t=30, b=30, l=30, r=30),
    )
    return fig

def export_dossier_excel(product: Dict, assessments: List[Dict], defects: List[Dict]) -> bytes:
    """Export product dossier to Excel."""
    from io import BytesIO
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Product Overview
        overview = pd.DataFrame([{
            "Product": product.get("name", ""),
            "Category": product.get("category", ""),
            "Region": product.get("region", ""),
            "MSRP": product.get("planned_msrp", 0),
            "Landed COGS": product.get("landed_cogs", 0),
            "Gross Margin %": product.get("gross_margin_pct", 0),
            "Net Margin %": product.get("net_profit_pct", 0),
            "BSR": product.get("bsr_rank", 0),
            "Rating": product.get("rating", 0),
            "Reviews": product.get("review_count", 0),
        }])
        overview.to_excel(writer, sheet_name="Overview", index=False)
        
        # Economics Scenarios
        if assessments:
            econ_rows = []
            for a in assessments:
                for sc in ["conservative", "expected", "upside"]:
                    sc_data = a.get(sc, {})
                    econ_rows.append({
                        "Scenario": sc.capitalize(),
                        "MSRP": sc_data.get("planned_msrp", 0),
                        "FOB": sc_data.get("fob_price", 0),
                        "Landed COGS": sc_data.get("landed_cogs", 0),
                        "Gross Profit": sc_data.get("gross_profit", 0),
                        "Gross Margin %": sc_data.get("gross_margin_pct", 0),
                        "Net Profit": sc_data.get("net_profit", 0),
                        "Net Margin %": sc_data.get("net_profit_pct", 0),
                        "Status": sc_data.get("status", ""),
                    })
            pd.DataFrame(econ_rows).to_excel(writer, sheet_name="Economics", index=False)
        
        # Defects
        if defects:
            pd.DataFrame(defects).to_excel(writer, sheet_name="Defects", index=False)
    
    return output.getvalue()

def export_dossier_word(product: Dict, assessments: List[Dict], defects: List[Dict]) -> bytes:
    """Export product dossier to Word document."""
    from io import BytesIO
    from docx import Document
    from docx.shared import Inches, Pt, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    
    doc = Document()
    
    # Title
    title = doc.add_heading(f"APRS V6 Pro — Product Dossier", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Product Info
    doc.add_heading("Product Overview", level=1)
    table = doc.add_table(rows=8, cols=2, style='Light Grid Accent 1')
    data = [
        ("Product", product.get("name", "")),
        ("Category", product.get("category", "")),
        ("Region", product.get("region", "")),
        ("MSRP", format_inr(product.get("planned_msrp", 0))),
        ("Landed COGS", format_inr(product.get("landed_cogs", 0))),
        ("Gross Margin", format_pct(product.get("gross_margin_pct", 0))),
        ("Net Margin", format_pct(product.get("net_profit_pct", 0))),
        ("BSR Rank", f"#{product.get('bsr_rank', 0):,}"),
    ]
    for i, (k, v) in enumerate(data):
        table.cell(i, 0).text = k
        table.cell(i, 1).text = str(v)
    
    # Economics
    if assessments:
        doc.add_heading("15-Factor Economics (3 Scenarios)", level=1)
        a = assessments[0]  # Latest
        for sc in ["conservative", "expected", "upside"]:
            sc_data = a.get(sc, {})
            doc.add_heading(f"{sc.capitalize()} Scenario", level=2)
            t = doc.add_table(rows=5, cols=2, style='Light Grid Accent 1')
            sc_fields = [
                ("MSRP", format_inr(sc_data.get("planned_msrp", 0))),
                ("FOB", format_inr(sc_data.get("fob_price", 0))),
                ("Landed COGS", format_inr(sc_data.get("landed_cogs", 0))),
                ("Net Profit", format_inr(sc_data.get("net_profit", 0))),
                ("Net Margin %", format_pct(sc_data.get("net_profit_pct", 0))),
            ]
            for i, (k, v) in enumerate(sc_fields):
                t.cell(i, 0).text = k
                t.cell(i, 1).text = str(v)
    
    # Defects & v2.0 Spec
    if defects:
        doc.add_heading("Defect Analysis & v2.0 Specification", level=1)
        for d in defects:
            doc.add_heading(f"Defect: {d.get('defect_description', '')}", level=3)
            doc.add_paragraph(f"Severity: {d.get('severity', 'N/A')}")
            doc.add_paragraph(f"Fixable: {'Yes' if d.get('is_fixable') else 'No'}")
            if d.get('v2_fix_description'):
                doc.add_paragraph(f"v2.0 Fix: {d['v2_fix_description']}")
    
    # Save
    output = BytesIO()
    doc.save(output)
    return output.getvalue()


# ── Load Data ─────────────────────────────────────────────────────────────────
products = load_products(include_deleted=False)
shortlisted = [p for p in products if p.get("is_shortlisted", 0) == 1]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚡ APRS V6 Pro")
    st.caption("Autonomous E-Commerce Intelligence")
    st.divider()
    
    # Stats
    col1, col2 = st.columns(2)
    col1.metric("Products", len(products))
    col2.metric("Shortlisted", len(shortlisted))
    
    col1, col2 = st.columns(2)
    col1.metric("Niches", len(get_dynamic_niches(active_only=True)))
    col2.metric("Seed Keywords", len(get_seed_keywords(active_only=True)))
    
    st.divider()
    
    # Quick filters
    st.subheader("Filters")
    regions = ["All"] + sorted({p["region"] for p in products if p.get("region")})
    sel_region = st.selectbox("Region", regions)
    
    categories = ["All"] + sorted({p["category"] for p in products if p.get("category")})
    sel_category = st.selectbox("Category", categories)
    
    show_shortlisted_only = st.checkbox("Shortlisted Only", value=False)
    
    st.divider()
    
    # Gate threshold settings
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

# ── Header ────────────────────────────────────────────────────────────────────
st.title("⚡ APRS V6 Pro — Autonomous E-Commerce Intelligence")
st.caption(f"Showing {len(filtered)} of {len(products)} products | {datetime.now().strftime('%Y-%m-%d %H:%M')}")

# ── Tab Navigation ────────────────────────────────────────────────────────────
TABS = [
    ("research", "🔬 Research"),
    ("economics", "📊 Economics"),
    ("dossiers", "📋 Dossiers"),
    ("settings", "⚙️ Settings"),
]

tab_research, tab_economics, tab_dossiers, tab_settings = st.tabs([t[1] for t in TABS])

# ═════════════════════════════════════════════════════════════════════════════
# TAB 1: RESEARCH
# ════════════════════════════════════════════════════════════════════════════
with tab_research:
    st.subheader("🔬 Research — Discovery, Niches & Gate Pipeline")
    
    # Niches overview
    niches = get_dynamic_niches(region=sel_region if sel_region != "All" else None, active_only=True)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.markdown("**Active Niches**")
        if niches:
            niche_df = pd.DataFrame(niches)
            display_cols = ["category", "region", "priority_score", "times_scanned", "products_found", "is_active"]
            st.dataframe(niche_df[display_cols], width='stretch', hide_index=True)
        else:
            st.info("No active niches. Run discovery scan via CLI: `python main.py scan`")
    
    with col2:
        st.markdown("**Quick Actions**")
        if st.button("🔍 Run Discovery Scan", type="primary", width='stretch'):
            st.info("Run `python main.py scan` from CLI to execute batch discovery.")
        if st.button("📥 Export Niches CSV", width='stretch'):
            if niches:
                csv = pd.DataFrame(niches).to_csv(index=False)
                st.download_button("Download", csv, "niches.csv", "text/csv")
    
    st.divider()
    
    # Product list with gate status
    st.markdown("**Product Pipeline**")
    
    if not filtered:
        st.info("No products match current filters.")
    else:
        # Summary metrics
        gate_stats = {1: {"pass": 0, "fail": 0}, 2: {"pass": 0, "fail": 0}, 3: {"pass": 0, "fail": 0}, 4: {"pass": 0, "fail": 0}}
        
        for p in filtered:
            gates = get_gate_status_dict(p["product_id"])
            for g in range(1, 5):
                gs = gates.get(g, {})
                status = gs.get("status", "PENDING")
                if status == "PASS":
                    gate_stats[g]["pass"] += 1
                elif status == "FAIL":
                    gate_stats[g]["fail"] += 1
        
        gcols = st.columns(4)
        gate_labels = {1: "Signal", 2: "Defects", 3: "Economics", 4: "Scoring"}
        for i, g in enumerate([1, 2, 3, 4]):
            with gcols[i]:
                total = gate_stats[g]["pass"] + gate_stats[g]["fail"]
                st.metric(
                    f"Gate {g}: {gate_labels[g]}",
                    f"{gate_stats[g]['pass']}/{total}",
                    delta=f"{gate_stats[g]['fail']} failed" if gate_stats[g]['fail'] else None,
                )
        
        st.divider()
        
        # Product table
        rows = []
        for p in filtered:
            gates = get_gate_status_dict(p["product_id"])
            gate_str = ""
            for g in range(1, 5):
                gs = gates.get(g, {})
                status = gs.get("status", "PENDING")
                badge = {"PASS": "✅", "FAIL": "❌", "PENDING": "⏳", "BLOCKED": "🚫", "IN_PROGRESS": "🔄"}.get(status, "❓")
                gate_str += f"{badge} "
            
            rows.append({
                "⭐": "★" if p.get("is_shortlisted") else "☆",
                "Product": p["name"][:50],
                "Category": p.get("category", ""),
                "Region": p.get("region", ""),
                "MSRP": format_inr(p.get("planned_msrp", 0)),
                "Net %": format_pct(p.get("net_profit_pct", 0)),
                "Score": f"{p.get('overall_score', 0):.0f}",
                "Gates": gate_str,
                "Status": p.get("status", "PENDING"),
                "ID": p["product_id"],
            })
        
        df = pd.DataFrame(rows)
        
        # Add selection
        selection = st.dataframe(
            df,
            width='stretch',
            hide_index=True,
            column_config={
                "⭐": st.column_config.TextColumn("★", width=40),
                "Product": st.column_config.TextColumn("Product", width=250),
                "Gates": st.column_config.TextColumn("Gates 1-4", width=150),
            },
            on_select="rerun",
            selection_mode="single-row",
        )
        
        # Product detail on selection
        if selection.selection.rows:
            idx = selection.selection.rows[0]
            product = filtered[idx]
            pid = product["product_id"]
            
            st.divider()
            st.markdown(f"### 📦 {product['name']}")
            
            # Gate details
            gates = get_gate_status_dict(pid)
            gate_cols = st.columns(4)
            for i, g in enumerate([1, 2, 3, 4]):
                with gate_cols[i]:
                    gs = gates.get(g, {})
                    status = gs.get("status", "PENDING")
                    badge_class = {"PASS": "badge-pass", "FAIL": "badge-fail", "PENDING": "badge-pending", "BLOCKED": "badge-blocked"}.get(status, "badge-pending")
                    st.markdown(f"""
                    <div class="metric-card">
                        <strong>Gate {g}: {gate_labels[g]}</strong><br>
                        <span class="gate-badge {badge_class}">{status}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    if gs.get("metadata"):
                        with st.expander("Details"):
                            st.json(gs["metadata"])
            
            # Defects
            defects = get_defect_clusters(pid)
            if defects:
                with st.expander("🛡️ Defects & v2.0 Spec"):
                    for d in defects:
                        st.markdown(f"**{d.get('defect_description', '')}**")
                        st.caption(f"Severity: {d.get('severity')} | Fixable: {'Yes' if d.get('is_fixable') else 'No'}")
                        if d.get('v2_fix_description'):
                            st.markdown(f"*v2.0 Fix:* {d['v2_fix_description'][:80]}...")
            
            # Action buttons
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
                    st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 2: ECONOMICS
# ════════════════════════════════════════════════════════════════════════════
with tab_economics:
    st.subheader("📊 Economics — 15-Factor 3-Scenario Analysis")
    
    if not filtered:
        st.info("No products to analyze.")
    else:
        # Product selector
        product_options = {f"{p['name'][:50]} ({p['product_id']})": p for p in filtered}
        sel_key = st.selectbox("Select Product", list(product_options.keys()))
        sel_product = product_options[sel_key]
        pid = sel_product["product_id"]
        
        # Load assessments
        assessments = get_economics_assessments(pid)
        
        if not assessments:
            st.warning("No economics assessment found. Run evaluation via CLI or click below.")
            
            # Quick calculator
            with st.form("econ_calc"):
                st.markdown("**Quick Economics Calculator**")
                c1, c2, c3 = st.columns(3)
                with c1:
                    q_fob = st.number_input("FOB (INR)", value=float(sel_product.get("factory_cogs") or sel_product.get("landed_cogs", 0) * 0.3 or 350), step=50)
                    q_msrp = st.number_input("MSRP (INR)", value=float(sel_product.get("planned_msrp", 1299)), step=100)
                with c2:
                    q_cat = st.selectbox("Category", ["Kitchen", "Home", "Electronics", "Beauty", "Apparel", "General"], 
                                        index=["Kitchen", "Home", "Electronics", "Beauty", "Apparel", "General"].index(sel_product.get("category", "General")))
                    q_mkt = st.selectbox("Marketplace", ["amazon", "flipkart", "meesho"])
                with c3:
                    q_lead = st.number_input("Lead Time (days)", value=30, step=5)
                    q_trend = st.number_input("Trend Half-Life (days)", value=90, step=10)
                
                if st.form_submit_button("🧮 Calculate 15-Factor Economics", type="primary"):
                    assessment = Comprehensive15FactorEconomics.evaluate_15_factor_economics(
                        product_id=pid,
                        fob_price=q_fob,
                        planned_msrp=q_msrp,
                        region=sel_product.get("region", "India"),
                        category=q_cat,
                        marketplace=q_mkt,
                        lead_time_days=q_lead,
                        trend_half_life_days=q_trend,
                    )
                    st.session_state["quick_assessment"] = assessment
                    st.rerun()
            
            if "quick_assessment" in st.session_state:
                assessments = [st.session_state["quick_assessment"]]
        
        if assessments:
            assessment = assessments[0]  # Latest
            
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
                    "Scenario": sc_name.capitalize(),
                    "MSRP": format_inr(sc.get("planned_msrp", 0)),
                    "FOB": format_inr(sc.get("fob_price", 0)),
                    "Landed COGS": format_inr(sc.get("landed_cogs", 0)),
                    "Gross Profit": format_inr(sc.get("gross_profit", 0)),
                    "Gross %": format_pct(sc.get("gross_margin_pct", 0)),
                    "Mkt Comm": format_inr(sc.get("marketplace_commission", 0)),
                    "Fulfillment": format_inr(sc.get("fulfillment_fee", 0)),
                    "Payment/COD": format_inr(sc.get("payment_or_cod_fee", 0)),
                    "RTO Reserve": format_inr(sc.get("rto_reserve", 0)),
                    "Fraud Reserve": format_inr(sc.get("return_fraud_reserve", 0)),
                    "Ads (TACoS)": format_inr(sc.get("ad_tacos_reserve", 0)),
                    "Tax": format_inr(sc.get("net_tax_burden", 0)),
                    "Total Variable": format_inr(sc.get("total_variable_cost", 0)),
                    "Net Profit": format_inr(sc.get("net_profit", 0)),
                    "Net %": format_pct(sc.get("net_profit_pct", 0)),
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

# ════════════════════════════════════════════════════════════════════════════
# TAB 3: DOSSIERS
# ════════════════════════════════════════════════════════════════════════════
with tab_dossiers:
    st.subheader("📋 Dossiers — Ranked Product Reports")
    
    # Sort products by score
    ranked = sorted(filtered, key=lambda p: p.get("overall_score", 0), reverse=True)
    
    if not ranked:
        st.info("No products to show.")
    else:
        # Export all button
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            st.markdown(f"**{len(ranked)} products** ranked by composite score")
        with col2:
            if st.button("📥 Export All (CSV)", type="primary", width='stretch'):
                all_rows = []
                for p in ranked:
                    all_rows.append({
                        "Rank": ranked.index(p) + 1,
                        "Product": p["name"],
                        "Category": p.get("category", ""),
                        "Region": p.get("region", ""),
                        "MSRP": p.get("planned_msrp", 0),
                        "Net Margin %": p.get("net_profit_pct", 0),
                        "Score": p.get("overall_score", 0),
                        "Status": p.get("status", ""),
                    })
                csv = pd.DataFrame(all_rows).to_csv(index=False)
                st.download_button("Download CSV", csv, "aprs_dossiers.csv", "text/csv", width='stretch')
        
        st.divider()
        
        # Individual product dossiers
        for idx, product in enumerate(ranked):
            pid = product["product_id"]
            score = product.get("overall_score", 0)
            verdict = "PROCEED" if score >= 75 else ("MARGINAL" if score >= 60 else "REJECT")
            score_class = "score-proceed" if score >= 75 else ("score-marginal" if score >= 60 else "score-reject")
            
            with st.expander(f"#{idx+1}  {product['name'][:60]}  |  Score: {score:.0f}  |  {verdict}", expanded=(idx < 3)):
                # Header row
                h1, h2, h3, h4 = st.columns([2, 1, 1, 1])
                h1.markdown(f"**Category:** {product.get('category', 'N/A')}  |  **Region:** {product.get('region', 'N/A')}")
                h2.metric("MSRP", format_inr(product.get("planned_msrp", 0)))
                h3.metric("Net Margin", format_pct(product.get("net_profit_pct", 0)))
                h4.metric("BSR", f"#{product.get('bsr_rank', 0):,}")
                
                # Score badge
                st.markdown(f'<div class="score-big {score_class}">{score:.0f} / 100</div>', unsafe_allow_html=True)
                
                # Assessments & Defects
                assessments = get_economics_assessments(pid)
                defects = get_defect_clusters(pid)
                
                d1, d2 = st.columns(2)
                with d1:
                    if assessments:
                        a = assessments[0]
                        sc = a.get("expected", {})
                        st.markdown("**Expected Scenario**")
                        st.markdown(f"- MSRP: {format_inr(sc.get('planned_msrp', 0))}")
                        st.markdown(f"- FOB: {format_inr(sc.get('fob_price', 0))}")
                        st.markdown(f"- Landed COGS: {format_inr(sc.get('landed_cogs', 0))}")
                        st.markdown(f"- Gross Margin: {format_pct(sc.get('gross_margin_pct', 0))}")
                        st.markdown(f"- Net Margin: {format_pct(sc.get('net_profit_pct', 0))}")
                        st.markdown(f"- Status: {sc.get('status', 'N/A')}")
                    else:
                        st.info("No economics assessment")
                
                with d2:
                    if defects:
                        st.markdown("**Defects Found**")
                        for d in defects[:3]:
                            st.markdown(f"- {d.get('defect_description', '')} ({d.get('severity', '')})")
                            if d.get('v2_fix_description'):
                                st.caption(f"  → Fix: {d['v2_fix_description'][:80]}...")
                    else:
                        st.info("No defect data")
                
                # Export buttons
                e1, e2, e3 = st.columns(3)
                with e1:
                    if st.button("📄 Word", key=f"word_{pid}", width='stretch'):
                        word_bytes = export_dossier_word(product, assessments, defects)
                        st.download_button(
                            "Download .docx",
                            word_bytes,
                            f"dossier_{pid}.docx",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"dl_word_{pid}",
                            width='stretch',
                        )
                with e2:
                    if st.button("📊 Excel", key=f"excel_{pid}", width='stretch'):
                        excel_bytes = export_dossier_excel(product, assessments, defects)
                        st.download_button(
                            "Download .xlsx",
                            excel_bytes,
                            f"dossier_{pid}.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_excel_{pid}",
                            width='stretch',
                        )
                with e3:
                    if st.button("⭐ Shortlist", key=f"sl_{pid}", width='stretch'):
                        toggle_shortlist(pid)
                        st.rerun()

# ════════════════════════════════════════════════════════════════════════════
# TAB 4: SETTINGS
# ════════════════════════════════════════════════════════════════════════════
with tab_settings:
    st.subheader("⚙️ Settings & Configuration")
    
    st.markdown("### 🔑 API Credentials")
    st.caption("Configure in `.env` file. See `.env.example` for template.")
    
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Keepa API Key", value=os.getenv("KEEPA_API_KEY", ""), type="password", disabled=True)
        st.text_input("Ollama URL", value=settings.ollama_url, disabled=True)
    with col2:
        st.text_input("Ollama Model", value=settings.ollama_model, disabled=True)
        st.text_input("Database Path", value=str(settings.database_path), disabled=True)
    
    st.divider()
    
    st.markdown("### 🎯 Gate Thresholds")
    st.caption("Modify in `.env` or `config/settings.py`")
    
    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Gate 1: BSR Threshold", f"{settings.gate1_bsr_threshold:,}")
    t2.metric("Gate 1: CV Threshold", f"{settings.gate1_cv_threshold:.0%}")
    t3.metric("Gate 3: Min Margin", f"{settings.gate3_min_margin_pct:.0f}%")
    t4.metric("Gate 4: Min Score", f"{settings.gate4_min_score}")
    
    st.divider()
    
    st.markdown("### 🛠️ Scoring Weights")
    w1, w2, w3, w4, w5 = st.columns(5)
    w1.metric("Market Signal", f"{settings.score_market_signal_weight} pts")
    w2.metric("Review Quality", f"{settings.score_review_quality_weight} pts")
    w3.metric("Margin Safety", f"{settings.score_margin_safety_weight} pts")
    w4.metric("Defect Fixability", f"{settings.score_defect_fixability_weight} pts")
    w5.metric("Competition", f"{settings.score_competition_density_weight} pts")
    
    st.divider()
    
    st.markdown("### 🗄️ Database Explorer")
    tables = get_all_table_names()
    sel_table = st.selectbox("Select Table", tables)
    
    if sel_table:
        table_data = get_table_data(sel_table, limit=100)
        if table_data:
            st.dataframe(pd.DataFrame(table_data), width='stretch', hide_index=True)
        else:
            st.info("Table is empty")
    
    st.divider()
    
    st.markdown("### 📝 Environment Template")
    st.code((_ROOT / ".env.example").read_text(), language="bash")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption("APRS V6 Pro — Deterministic 4-Gate Pipeline | Local Ollama | Playwright Scrapers | Zero LLM in Hot Path")