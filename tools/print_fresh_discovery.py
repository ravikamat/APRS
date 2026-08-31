import sqlite3
import sys
import os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import get_db_path

DB_PATH = str(get_db_path())
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute('''
    SELECT product_id, name, category, region, planned_msrp, landed_cogs,
           gross_margin_pct, estimated_cac, net_profit_pct, worst_case_stress_margin_pct,
           status, overall_score, sourcing_cluster, marketplace_url,
           competitor_3star_flaws, upgrade_v2_engineering, updated_at
    FROM master_products
    WHERE product_id LIKE 'US_%' OR product_id LIKE 'IN_%'
    ORDER BY updated_at DESC
''')

rows = cur.fetchall()
print(f"TOTAL FRESH LIVE PRODUCTS SCANNED IN REAL-TIME: {len(rows)}\n")

for i, r in enumerate(rows, 1):
    reg = r['region']
    sym = '₹' if reg.lower() == 'india' else '$'
    
    cur.execute('SELECT factory_name, fob_unit_price, moq_units, contact_details FROM product_suppliers WHERE product_id = ?', (r['product_id'],))
    suppliers = cur.fetchall()
    
    print(f"--------------------------------------------------------------------------------")
    print(f"#{i} [{r['product_id']}] {r['name']}")
    print(f"    Region: {reg} | Category: {r['category']} | Status: {r['status']} | Score: {r['overall_score']:.1f}/100")
    print(f"    Live Scraped MSRP: {sym}{r['planned_msrp']:,.2f} | 12-Factor Landed COGS: {sym}{r['landed_cogs']:,.2f} | Gross Margin: {r['gross_margin_pct']:.1f}%")
    print(f"    Est. Ad CAC: {sym}{r['estimated_cac']:,.2f} | Net Margin: {r['net_profit_pct']:.1f}% | Worst-Case Stress Margin: {r['worst_case_stress_margin_pct']:.1f}%")
    print(f"    Sourcing Hub: {r['sourcing_cluster']}")
    print(f"    Verified Live URL: {r['marketplace_url']}")
    print(f"    3-Star Competitor Flaw: {r['competitor_3star_flaws']}")
    print(f"    Product v2.0 Engineering Fix: {r['upgrade_v2_engineering']}")
    if suppliers:
        s = suppliers[0]
        print(f"    Factory: {s['factory_name']} (FOB: {s['fob_unit_price']} | MOQ: {s['moq_units']} units)")
        print(f"    Direct Contact: {s['contact_details']}")
print(f"--------------------------------------------------------------------------------")
