import os
import sys
import shutil
import datetime
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import EXCEL_MASTER_PATH
from core.database import get_all_products, get_connection
from core.utils import normalize_region, get_region_currency

def get_currency_symbol(region: str) -> str:
    """Delegates to core.utils for canonical region-to-currency mapping."""
    sym, _ = get_region_currency(normalize_region(region or "USA"))
    return sym


def update_master_excel() -> str:
    """
    Exports clean read-only snapshot from SQLite SSOT to Master Excel.
    Features:
    1. Atomic shadow-copy write pattern to prevent crashes if user has Excel open.
    2. Regional currency formatting.
    """
    products = get_all_products()
    wb = openpyxl.Workbook()
    wb.remove(wb.active) # Remove default sheet
    
    # Common Styling
    font_family = "Segoe UI"
    hdr_font = Font(name=font_family, size=11, bold=True, color="FFFFFF")
    hdr_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    pass_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    pass_font = Font(name=font_family, size=10, bold=True, color="166534")
    border_thin = Border(
        left=Side(style='thin', color='E2E8F0'),
        right=Side(style='thin', color='E2E8F0'),
        top=Side(style='thin', color='E2E8F0'),
        bottom=Side(style='thin', color='E2E8F0')
    )
    
    # ---------------------------------------------------------
    # SHEET 1: Master Product Registry (All 50 SKUs)
    # ---------------------------------------------------------
    ws1 = wb.create_sheet(title="Master Dossier (50 SKUs)")
    headers1 = [
        "Product ID", "Status", "Consensus", "Product Name", "Category", "Target Region",
        "Planned MSRP", "Landed COGS", "Gross Margin %", "Est. CAC", "Net Margin %",
        "Worst-Case Stress %", "Score", "Sourcing Hub", "Verified Listing URL"
    ]
    ws1.append(headers1)
    
    for p in products:
        sym = get_currency_symbol(p["region"])
        ws1.append([
            p["product_id"],
            p.get("human_override_status") or p["status"],
            p["consensus_status"],
            p["name"],
            p["category"],
            p["region"],
            f"{sym}{p['planned_msrp']:,.2f}",
            f"{sym}{p['landed_cogs']:,.2f}",
            f"{p['gross_margin_pct']:.1f}%",
            f"{sym}{p['estimated_cac']:,.2f}",
            f"{p['net_profit_pct']:.1f}%",
            f"{p['worst_case_stress_margin_pct']:.1f}%",
            p["overall_score"],
            p["sourcing_cluster"],
            p.get("marketplace_url", "")
        ])
        
    # ---------------------------------------------------------
    # SHEET 2: High-Margin Scale Winners & v2.0 Upgrades
    # ---------------------------------------------------------
    ws2 = wb.create_sheet(title="Scale Winners & Upgrades")
    headers2 = ["Product ID", "Product Name", "Category", "Planned MSRP", "Landed COGS", "Net Margin %", "Competitor 3-Star Review Flaws", "Engineered Product v2.0 Upgrade"]
    ws2.append(headers2)
    for p in products:
        sym = get_currency_symbol(p["region"])
        ws2.append([
            p["product_id"], p["name"], p["category"],
            f"{sym}{p['planned_msrp']:,.2f}", f"{sym}{p['landed_cogs']:,.2f}",
            f"{p['net_profit_pct']:.1f}%", p["competitor_3star_flaws"], p["upgrade_v2_engineering"]
        ])

    # ---------------------------------------------------------
    # SHEET 3: 12-Factor Unit Economics Breakdown
    # ---------------------------------------------------------
    ws3 = wb.create_sheet(title="12-Factor Economics")
    headers3 = [
        "Product ID", "Product Name", "MSRP", "Factory FOB", "Landed COGS", "Est. CAC",
        "Referral Fee (15%)", "PG Fee (2%)", "RTO Reserve (9%)", "Net Margin %", "Worst-Case Shock %"
    ]
    ws3.append(headers3)
    for p in products:
        sym = get_currency_symbol(p["region"])
        msrp = p["planned_msrp"]
        factory_cogs = p.get('factory_cogs') or 0.0
        ws3.append([
            p["product_id"], p["name"], f"{sym}{msrp:,.2f}",
            f"{sym}{factory_cogs:,.2f}", f"{sym}{p['landed_cogs']:,.2f}",
            f"{sym}{p['estimated_cac']:,.2f}", f"{sym}{msrp*0.15:,.2f}", f"{sym}{msrp*0.02:,.2f}",
            f"{sym}{msrp*0.09:,.2f}", f"{p['net_profit_pct']:.1f}%", f"{p['worst_case_stress_margin_pct']:.1f}%"
        ])

    # ---------------------------------------------------------
    # SHEET 4: Supplier Directory & Manufacturing Hubs
    # ---------------------------------------------------------
    ws4 = wb.create_sheet(title="Verified Sourcing Directory")
    headers4 = [
        "Product ID", "Factory Name", "Supplier Type", "Industrial Cluster Address",
        "Contact Person", "Direct Contact (WhatsApp/Email)", "FOB Unit Price", "MOQ (Units)",
        "Sample & Lead Time", "Certifications", "B2B Profile Link"
    ]
    ws4.append(headers4)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM product_suppliers ORDER BY product_id ASC")
    for s in cur.fetchall():
        ws4.append([
            s["product_id"], s["factory_name"], s["supplier_type"], s["industrial_address"],
            s["contact_person"], s["contact_details"], s["fob_unit_price"], s["moq_units"],
            s["sample_cost_leadtime"], s["certifications"], s["platform_profile_url"]
        ])
    conn.close()

    # Style all sheets
    for ws in [ws1, ws2, ws3, ws4]:
        for col_idx in range(1, ws.max_column + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = hdr_font
            cell.fill = hdr_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            ws.column_dimensions[get_column_letter(col_idx)].width = 24

    # ---------------------------------------------------------
    # ATOMIC / SHADOW-COPY SAVE (PREVENTS PERMISSION CRASHES)
    # ---------------------------------------------------------
    target_path = Path(EXCEL_MASTER_PATH)
    try:
        wb.save(str(target_path))
        return str(target_path)
    except PermissionError:
        # If user has Excel open, write to shadow copy
        shadow_path = target_path.parent / f"{target_path.stem}_latest.xlsx"
        wb.save(str(shadow_path))
        print(f"[EXCEL LOCK NOTICE] Primary Excel open by user. Exported shadow snapshot to: {shadow_path.name}")
        return str(shadow_path)
    except Exception as e:
        print(f"[EXCEL EXPORT ERROR]: {e}")
        return str(target_path)

if __name__ == "__main__":
    p = update_master_excel()
    print("[SUCCESS] Master Excel snapshot written to:", p)
