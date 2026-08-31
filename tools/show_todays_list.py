import sqlite3
import sys

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("str(Path(__file__).resolve().parent.parent / 'data' / 'research_engine.db')")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT product_id, name, category, region, planned_msrp, landed_cogs, gross_margin_pct, estimated_cac, net_profit_pct, worst_case_stress_margin_pct, status, overall_score, sourcing_cluster, marketplace_url, human_override_status, competitor_3star_flaws, upgrade_v2_engineering FROM master_products ORDER BY overall_score DESC")
rows = cur.fetchall()

print(f"TOTAL ACTIVE OPPORTUNITIES TODAY: {len(rows)}\n")
for i, r in enumerate(rows, 1):
    eff_status = r["human_override_status"] or r["status"]
    reg = r["region"]
    sym = "INR " if "india" in reg.lower() or reg.lower() == "india".lower() else "$"
    
    cur.execute("SELECT factory_name, fob_unit_price, moq_units, contact_details FROM product_suppliers WHERE product_id = ?", (r["product_id"],))
    suppliers = cur.fetchall()
    
    print(f"--------------------------------------------------------------------------------")
    print(f"#{i} [{r['product_id']}] {r['name']}")
    print(f"    Region: {reg} | Category: {r['category']} | Status: {eff_status} | Overall Score: {r['overall_score']:.1f}/100")
    print(f"    MSRP: {sym}{r['planned_msrp']:,.2f} | Landed COGS: {sym}{r['landed_cogs']:,.2f} | Gross Margin: {r['gross_margin_pct']:.1f}%")
    print(f"    Est. CAC: {sym}{r['estimated_cac']:,.2f} | Net Profit Margin: {r['net_profit_pct']:.1f}% | Stress Test Net Margin: {r['worst_case_stress_margin_pct']:.1f}%")
    print(f"    Sourcing Hub: {r['sourcing_cluster']}")
    print(f"    Marketplace Link: {r['marketplace_url']}")
    print(f"    3-Star Competitor Flaw: {r['competitor_3star_flaws']}")
    print(f"    Product v2.0 Engineering Fix: {r['upgrade_v2_engineering']}")
    if suppliers:
        print(f"    Suppliers ({len(suppliers)} Verified):")
        for s in suppliers:
            print(f"      • {s['factory_name']} (FOB: {s['fob_unit_price']} | MOQ: {s['moq_units']} units) | Contact: {s['contact_details']}")
print(f"--------------------------------------------------------------------------------")
