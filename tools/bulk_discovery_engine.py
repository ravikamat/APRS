import sys
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Ensure project root is importable regardless of working directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8')

from core.orchestrator import AutonomousProductResearchOrchestrator
from core.database import get_all_products

# Comprehensive Multi-Niche Catalogue Targets (US & India)
EXPANDED_NICHES = [
    # --- USA & Global Opportunities ---
    {"region": "USA", "category": "Ultrasonic Retainer and Dental Cleaning Machine", "limit": 4},
    {"region": "USA", "category": "Flame Air Diffuser Humidifier Aromatherapy", "limit": 4},
    {"region": "USA", "category": "Under Desk Foldable Walking Pad Treadmill", "limit": 4},
    {"region": "USA", "category": "MagSafe Magnetic Wireless Car Mount Charger", "limit": 4},
    {"region": "USA", "category": "Inverted Windproof Reflective Compact Travel Umbrella", "limit": 4},
    {"region": "USA", "category": "Smart Mug Warmer with Temperature Presets for Desk", "limit": 4},
    {"region": "USA", "category": "Stainless Steel Wireless Pump Pet Water Fountain", "limit": 4},
    {"region": "USA", "category": "Electric Cordless Pressure Scrubber Bathroom Cleaner", "limit": 4},
    {"region": "USA", "category": "High Speed Cordless Turbo Jet Fan Air Duster", "limit": 4},

    # --- India & Regional Opportunities ---
    {"region": "India", "category": "Rechargeable Self Stirring Magnetic Coffee Mug", "limit": 4},
    {"region": "India", "category": "2 Tier Sliding Under Sink Cabinet Storage Organizer", "limit": 4},
    {"region": "India", "category": "Oil Spray Bottle and Silicone Basting Brush Dispenser", "limit": 4},
    {"region": "India", "category": "Solid Brass Traditional Double Edge Safety Razor", "limit": 4},
    {"region": "India", "category": "Touchless Automatic Foam Soap Dispenser USB Rechargeable", "limit": 4},
    {"region": "India", "category": "Mini Portable Wireless Electric Garlic Food Chopper", "limit": 4},
    {"region": "India", "category": "Reusable Non-Stick Silicone Air Fryer Basket Liners", "limit": 4},
    {"region": "India", "category": "360 Degree Microfiber Spray Mop for Floor Cleaning", "limit": 4}
]

print("================================================================================")
print(f"🚀 INITIATING MASSIVE PARALLEL DISCOVERY ENGINE (17 NICHES) — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("================================================================================")

orchestrator = AutonomousProductResearchOrchestrator()
total_new_discovered = 0

def scan_niche(niche_info):
    reg = niche_info["region"]
    cat = niche_info["category"]
    lim = niche_info["limit"]
    try:
        results = orchestrator.discover_and_evaluate_products(region=reg, category=cat, max_candidates=lim)
        return {"category": cat, "region": reg, "count": len(results), "items": results}
    except Exception as e:
        return {"category": cat, "region": reg, "count": 0, "error": str(e)}

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [executor.submit(scan_niche, n) for n in EXPANDED_NICHES]
    for f in as_completed(futures):
        res = f.result()
        if res.get("count", 0) > 0:
            total_new_discovered += res["count"]
            print(f" ✅ [{res['region']}] '{res['category']}' -> {res['count']} Live Opportunities Ingested")
        else:
            print(f" ⚠️ [{res['region']}] '{res['category']}' -> 0 found ({res.get('error', 'No results')})")

all_prods = get_all_products()

print("\n================================================================================")
print(f"🎉 MASSIVE DISCOVERY SWEEP COMPLETE!")
print(f"📊 Total Active Catalog in Database: {len(all_prods)} Product Opportunities")
print("================================================================================")
