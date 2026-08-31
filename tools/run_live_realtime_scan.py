import sys
import datetime
from pathlib import Path

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Add project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.orchestrator import AutonomousProductResearchOrchestrator
from core.database import get_all_products

print("================================================================================")
print(f"🚀 INITIATING LIVE REAL-TIME PRODUCT DISCOVERY RUN — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("================================================================================")

orchestrator = AutonomousProductResearchOrchestrator()

# Categories to scan live right now
scan_targets = [
    {"region": "USA", "category": "Ultrasonic Jewelry Cleaner Machine", "max": 2},
    {"region": "USA", "category": "Electric Spin Scrubber Cordless Cleaning Brush", "max": 2},
    {"region": "USA", "category": "Car Seat Gap Filler Organizer with USB Fast Charger", "max": 2},
    {"region": "India", "category": "Self Stirring Magnetic Coffee Mug Stainless Steel", "max": 2},
    {"region": "India", "category": "Oil Dispenser Bottle with Silicone Basting Brush", "max": 2}
]

fresh_discovered = []

for target in scan_targets:
    reg = target["region"]
    cat = target["category"]
    m = target["max"]
    print(f"\n[LIVE PROBE] Scraping live marketplace signals for '{cat}' in {reg}...")
    try:
        results = orchestrator.discover_and_evaluate_products(region=reg, category=cat, max_candidates=m)
        print(f" -> Found & Evaluated {len(results)} live products!")
        fresh_discovered.extend(results)
    except Exception as e:
        print(f" -> Error during scan: {e}")

print("\n================================================================================")
print(f"✅ REAL-TIME SCAN COMPLETED: {len(fresh_discovered)} FRESH LIVE PRODUCTS DISCOVERED & INDEXED")
print("================================================================================")
