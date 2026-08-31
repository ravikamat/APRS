"""
core/background_daemon.py — 24/7 Autonomous Background Scraping & Swarm Validation Daemon.

Runs as a daemon thread inside the same process as main.py or web/app.py.
Cycles through a catalogue of niches, calling the full 6-gate orchestrator
for each, runs the NIM Swarm Orchestrator for validation, integrates
CanonicalProductMatcher for deduplication, and DemandProxyScorer for demand scoring.

Usage:
    from core.background_daemon import daemon_controller
    daemon_controller.start()          # Start background thread
    daemon_controller.pause()          # Pause between niches
    daemon_controller.resume()         # Resume
    status = daemon_controller.get_status()  # Dict with live stats
"""
import threading
import time
import datetime
import logging
from typing import List, Dict, Any

logger = logging.getLogger("aprs.daemon")
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(name)s %(levelname)s — %(message)s")

# ── Static Fallback Niches (used ONLY if dynamic_niches DB table is empty) ──
STATIC_FALLBACK_NICHES: List[Dict[str, Any]] = [
    # ── 🇮🇳 India High-Velocity Micro-Niches (Surat / Moradabad / Rajkot Hubs) ──
    {"region": "India", "category": "2 Tier Sliding Under Sink Cabinet Storage Organizer", "limit": 3},
    {"region": "India", "category": "Oil Spray Bottle Silicone Basting Brush Dispenser", "limit": 3},
    {"region": "India", "category": "Rechargeable Self Stirring Magnetic Coffee Mug", "limit": 3},
    {"region": "India", "category": "Solid Brass Traditional Double Edge Safety Razor", "limit": 3},
    {"region": "India", "category": "Touchless Automatic Foam Soap Dispenser USB Rechargeable", "limit": 3},
    {"region": "India", "category": "Mini Portable Wireless Electric Garlic Food Chopper", "limit": 3},
    {"region": "India", "category": "Reusable Non-Stick Silicone Air Fryer Basket Liners", "limit": 3},
    {"region": "India", "category": "360 Degree Microfiber Spray Mop for Floor Cleaning", "limit": 3},
    {"region": "India", "category": "Stainless Steel Insulated Water Bottle 1 Litre", "limit": 3},
    {"region": "India", "category": "Car Dashboard Mobile Holder Magnetic Mount", "limit": 3},
    {"region": "India", "category": "Cordless Electric Spin Scrubber Bathroom Cleaner", "limit": 3},
    {"region": "India", "category": "Foldable Aluminum Laptop Cooling Riser Stand", "limit": 3},
    {"region": "India", "category": "540 Titanium Needle Derma Roller for Beard Growth", "limit": 3},
    {"region": "India", "category": "Himalayan Natural Green Jade Roller Gua Sha Set", "limit": 3},
    {"region": "India", "category": "Car Seat Gap Filler Storage Box with Fast Charger", "limit": 3},
    {"region": "India", "category": "Portable 12V 150 PSI Digital Tyre Inflator Air Compressor", "limit": 3},
    {"region": "India", "category": "Memory Foam Coccyx Orthopedic Seat Cushion", "limit": 3},
    {"region": "India", "category": "Multi Level Acupressure Lumbar Back Stretcher", "limit": 3},
    {"region": "India", "category": "Airtight Stainless Steel Traditional Masala Dabba", "limit": 3},
    {"region": "India", "category": "Portable Wireless Thermal Bluetooth Label Printer", "limit": 3},
    {"region": "India", "category": "Smart Desktop Coffee Mug Warmer 3 Temp Presets", "limit": 3},
    {"region": "India", "category": "Large Fire Retardant Cable Management Organizer Box", "limit": 3},
    {"region": "India", "category": "Silicone Toilet Cleaning Brush Quick Drying Holder", "limit": 3},
    {"region": "India", "category": "Universal Food Grade Silicone Stretch Lids 6 Pack", "limit": 3},
    {"region": "India", "category": "Magnetic Wireless Charger Stand 3 in 1 Foldable", "limit": 3},
    {"region": "India", "category": "Electric Handheld Milk Frother USB Rechargeable", "limit": 3},

    # ── 🇺🇸 USA Winning Amazon FBA Problem-Solvers ─────────────────────────────
    {"region": "USA", "category": "Ultrasonic Retainer Dental Cleaning Machine", "limit": 3},
    {"region": "USA", "category": "Flame Air Diffuser Humidifier Aromatherapy", "limit": 3},
    {"region": "USA", "category": "Under Desk Foldable Walking Pad Treadmill", "limit": 3},
    {"region": "USA", "category": "MagSafe Magnetic Wireless Car Mount Charger", "limit": 3},
    {"region": "USA", "category": "Smart Mug Warmer with Temperature Presets for Desk", "limit": 3},
    {"region": "USA", "category": "Stainless Steel Wireless Pump Pet Water Fountain", "limit": 3},
    {"region": "USA", "category": "Electric Cordless Pressure Scrubber Bathroom Cleaner", "limit": 3},
    {"region": "USA", "category": "Self Cleaning Slicker Brush for Dogs and Cats", "limit": 3},
    {"region": "USA", "category": "Ergonomic Neck Cloud Cervical Traction Pillow", "limit": 3},
    {"region": "USA", "category": "Collapsible Silicone Food Storage Containers Set", "limit": 3},
    {"region": "USA", "category": "Rechargeable Flameless Electric Candle Lighter", "limit": 3},
    {"region": "USA", "category": "Motion Sensor Under Cabinet LED Closet Light Bar", "limit": 3},
    {"region": "USA", "category": "Portable UV-C Sanitizer Wand for Phone and Keys", "limit": 3},
    {"region": "USA", "category": "Mini Portable Neck Fan with LED Display", "limit": 3},

    # ── 🏭 GCC / Middle East High AOV Marketplaces (Amazon.ae / Noon) ─────────
    {"region": "GCC_MiddleEast", "category": "Arabic Perfume Oud Reed Diffuser Gift Set", "limit": 2},
    {"region": "GCC_MiddleEast", "category": "Portable Electric Coffee Grinder USB Rechargeable", "limit": 2},
    {"region": "GCC_MiddleEast", "category": "Foldable Car Windshield Umbrella UV Sunshade", "limit": 2},
    {"region": "GCC_MiddleEast", "category": "Rechargeable Bladeless Portable Neck Fan", "limit": 2},
    {"region": "GCC_MiddleEast", "category": "Luxury Bakhoor Electric Incense Burner USB", "limit": 2},

    # ── 🇪🇺 Europe / UK Eco & Tech Micro-Niches ────────────────────────────────
    {"region": "Europe", "category": "Bamboo Kitchen Utensil Set Eco Friendly", "limit": 2},
    {"region": "Europe", "category": "Smart Plug Energy Monitor Wi-Fi App Controlled", "limit": 2},
    {"region": "Europe", "category": "Reusable Beeswax Food Wrap Set Organic Cotton", "limit": 2},
    {"region": "UK", "category": "Roll Up Dish Drying Rack Over the Sink Stainless Steel", "limit": 2},
    {"region": "UK", "category": "Magnetic Knife Holder Wall Mounted Bamboo", "limit": 2},
]

# Unique regions for multi-region trend scouting
DAEMON_REGIONS = list(set(n["region"] for n in STATIC_FALLBACK_NICHES))


class DaemonController:
    """
    Controls the 24/7 autonomous background scraping and swarm validation thread.
    Thread-safe pause/resume via threading.Event.
    """

    def __init__(self):
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

        # Live status — read by get_status()
        self._lock = threading.Lock()
        self._current_niche: str = "Not started"
        self._niche_index: int = 0
        self._total_niches: int = len(STATIC_FALLBACK_NICHES)
        self._total_discovered_session: int = 0
        self._swarm_pass_count: int = 0
        self._swarm_fail_count: int = 0
        self._is_paused: bool = False
        self._recent_logs: List[str] = []
        self._started: bool = False

    def _log(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        logger.info(msg)
        with self._lock:
            self._recent_logs.append(entry)
            if len(self._recent_logs) > 40:
                self._recent_logs = self._recent_logs[-40:]

    def _worker(self):
        """Dual-loop: scans dynamic niches from DB, harvests real-time trends, runs universal scraper + swarm validation.
        ALL online tasks are registered with AI Supervisor for active monitoring, validation, and improvement."""
        from core.orchestrator import AutonomousProductResearchOrchestrator
        from tools.trend_scout.trend_aggregator import OpenWebTrendScout
        from tools.universal_browser_scraper import UniversalBrowserScraper
        from models.nim_swarm_orchestrator import NIMSwarmOrchestrator
        from core.product_matcher import CanonicalProductMatcher, DemandProxyScorer
        from core.database import get_all_products
        from tools.ai_supervisor import get_supervisor

        # ── Boot AI Supervisor (start active monitoring thread) ──────────────
        supervisor = get_supervisor()
        supervisor.start_monitoring()
        self._log("🧠 AI SUPERVISOR: Active monitoring STARTED — all online tasks will be supervised")

        self._log("🟢 24/7 Swarm Daemon started — universal multi-platform discovery")
        trend_scout = OpenWebTrendScout()
        universal_scraper = UniversalBrowserScraper()
        swarm = NIMSwarmOrchestrator()
        matcher = CanonicalProductMatcher()
        demand_scorer = DemandProxyScorer()
        cycle = 0

        while not self._stop_event.is_set():
            # ── STEP 0: NIM Discovery Cycle — AI Supervised ──────────────────
            try:
                from tools.discovery_engine import NIMDiscoveryEngine
                discovery = NIMDiscoveryEngine()

                # Bootstrap static data into DB on first run
                if cycle == 0:
                    discovery.seed_initial_data()
                    self._log("Bootstrap: Seeded initial niches, keywords, sources into DB")

                # Run discovery for each region — AI Supervised
                for region in DAEMON_REGIONS:
                    if self._stop_event.is_set():
                        break
                    try:
                        self._log(f"Discovery [{region}]: NIM finding new sources, niches, keywords...")
                        # Register discovery task with AI Supervisor
                        disc_task_id = supervisor.register_task(
                            "discover", f"full_discovery_{region}", region=region
                        )
                        with supervisor.supervise(disc_task_id) as disc_task:
                            disc_result = discovery.run_full_discovery_cycle(region)
                            disc_task.data_collected = disc_result  # Supervisor will validate this

                        n_src   = len(disc_result.get("new_sources",     []))
                        n_mkt   = len(disc_result.get("new_marketplaces", []))
                        n_niche = len(disc_result.get("new_niches",       []))
                        n_seed  = len(disc_result.get("new_seeds",        []))
                        n_url   = len(disc_result.get("url_extractions",  []))
                        self._log(
                            f"  Discovery [{region}]: +{n_src} sources, +{n_mkt} marketplaces, "
                            f"+{n_niche} niches, +{n_seed} seeds, +{n_url} URLs — AI Supervised ✓"
                        )
                    except Exception as de:
                        self._log(f"  Discovery [{region}] notice: {de}")
                        logger.warning(f"Discovery cycle error for {region}: {de}", exc_info=True)
            except Exception as de:
                self._log(f"Discovery engine init notice: {de}")
                logger.warning(f"Discovery engine init failed: {de}", exc_info=True)

            # ── STEP 1: Dynamic Open-Web Trend Scouting — AI Supervised ──────
            for region in DAEMON_REGIONS:
                if self._stop_event.is_set():
                    break
                try:
                    self._log(f"Trend Scout [{region}]: Sensing Google Trends & social breakouts...")
                    # Register trend task with AI Supervisor
                    trend_task_id = supervisor.register_task(
                        "search_products", f"trend_harvest_{region}", region=region
                    )
                    with supervisor.supervise(trend_task_id) as trend_task:
                        active_trends = trend_scout.harvest_all_active_trends(region=region, max_signals=6)
                        trend_task.data_collected = {"trends": active_trends, "region": region}

                    if active_trends:
                        self._log(
                            f"  [{region}] Harvested {len(active_trends)} live trend signals "
                            f"(AI validated): {', '.join(t['keyword'][:25] for t in active_trends[:3])}"
                        )
                        # Feed validated trend keywords back as new niches
                        from core.database import record_dynamic_niche
                        for t in active_trends:
                            try:
                                record_dynamic_niche(
                                    category=t["keyword"],
                                    region=t.get("region", region),
                                    priority_score=t.get("velocity_score", 50.0),
                                    discovered_by="trend_scout_feedback",
                                    source_signal=t.get("platform", "")
                                )
                            except Exception:
                                pass
                except Exception as te:
                    self._log(f"  [{region}] Trend scouting notice: {te}")
                    logger.warning(f"Trend scouting error for {region}: {te}", exc_info=True)

            # ── STEP 2: Load Dynamic Niches from DB (self-expanding) ─────────
            from core.database import get_dynamic_niches, update_niche_scan
            db_niches = get_dynamic_niches(limit=200)
            if db_niches:
                active_niches = [{"region": n["region"], "category": n["category"],
                                  "limit": n.get("search_limit", 3), "niche_id": n.get("niche_id")}
                                 for n in db_niches]
                self._log(f"Dynamic niches loaded from DB: {len(active_niches)} (self-expanding)")
            else:
                active_niches = STATIC_FALLBACK_NICHES
                self._log(f"Using static fallback niches: {len(active_niches)}")

            with self._lock:
                self._total_niches = len(active_niches)

            # ── STEP 3: Niche Rotation & Swarm Validation ────────────────────
            for idx, niche in enumerate(active_niches):
                if self._stop_event.is_set():
                    break

                # Pause checkpoint
                self._pause_event.wait()

                region = niche["region"]
                category = niche["category"]
                limit = niche.get("limit", 3)
                niche_id = niche.get("niche_id")

                with self._lock:
                    self._current_niche = f"{region} / {category[:40]}"
                    self._niche_index = idx + 1

                self._log(f"Scanning [{idx+1}/{len(active_niches)}] {region} -- {category[:45]}")

                try:
                    orch = AutonomousProductResearchOrchestrator()
                    results = orch.discover_and_evaluate_products(
                        region=region, category=category, max_candidates=limit
                    )
                    found = len(results)
                    with self._lock:
                        self._total_discovered_session += found

                    # Update niche scan counter in DB
                    if niche_id:
                        try:
                            update_niche_scan(niche_id, products_found=found)
                        except Exception:
                            pass

                    if found:
                        self._log(f"  {found} SKUs evaluated for {category[:35]}")

                        # ── Canonical Deduplication ──────────────────────────
                        existing_products = get_all_products(include_deleted=False)
                        for r in results:
                            pid = r.get("product_id")
                            pname = r.get("name", "")
                            pprice = float(r.get("planned_msrp") or r.get("price") or 0)
                            if pid and pname:
                                # Check for duplicates against existing products
                                is_dup = False
                                for ep in existing_products:
                                    if ep.get("product_id") == pid:
                                        continue  # skip self
                                    match = matcher.evaluate_match_confidence(
                                        pname, ep.get("name", ""),
                                        pprice, float(ep.get("planned_msrp") or 0)
                                    )
                                    if match.get("classification") == "EXACT_MATCH":
                                        self._log(f"  Dedup: {pname[:30]} ~ {ep.get('name', '')[:30]}")
                                        is_dup = True
                                        break

                                # Attach multi-platform listings via Universal Scraper (browser-use + DB config)
                                if not is_dup:
                                    try:
                                        listings = universal_scraper.scrape_all_marketplaces(region=region, query=category, max_pages=2)
                                        total_listings = sum(len(p) for p in listings.values())
                                        self._log(f"  Universal scrape [{pid[:15]}]: {total_listings} listings from {len(listings)} marketplaces")
                                        # Store listings in DB via record_multi_platform_listing
                                        from core.database import record_multi_platform_listing
                                        for marketplace, products in listings.items():
                                            for p in products:
                                                record_multi_platform_listing(
                                                    product_id=pid,
                                                    platform=marketplace.lower().replace(" ", "_"),
                                                    title=p.title,
                                                    price=float(p.price or 0.0),
                                                    listing_url=p.product_url,
                                                    rating=p.rating,
                                                    review_count=p.review_count,
                                                    currency=p.currency
                                                )
                                    except Exception as ue:
                                        self._log(f"  Universal scrape notice for {pid[:15]}: {ue}")

                                # Compute demand proxy score
                                try:
                                    demand = demand_scorer.calculate_demand_proxy(
                                        bsr_current=int(r.get("bsr_rank") or 0),
                                        bsr_30d_ago=int(r.get("bsr_rank_30d") or int(r.get("bsr_rank") or 0) * 1.1),
                                        review_count=int(r.get("review_count") or 0),
                                        reviews_30d_ago=max(0, int(r.get("review_count") or 0) - 5),
                                        ad_days_seen=14,
                                        price_current=pprice,
                                        price_30d_ago=pprice * 1.02,
                                        avg_rating=float(r.get("rating") or 4.0)
                                    )
                                    self._log(f"  Demand [{pname[:25]}]: {demand.get('demand_proxy_score', 0)}/100 ({demand.get('tier', 'UNKNOWN')})")
                                except Exception as de:
                                    logger.warning(f"Demand scoring error for {pid}: {de}", exc_info=True)

                        # ── Run Swarm Audit on discovered products ──────────
                        for r in results:
                            pid = r.get("product_id")
                            if not pid:
                                continue
                            try:
                                swarm_result = swarm.run_full_swarm_audit(r)
                                consensus = swarm_result.get("consensus_status", "UNKNOWN")
                                with self._lock:
                                    if consensus == "CONSENSUS_PASS":
                                        self._swarm_pass_count += 1
                                    else:
                                        self._swarm_fail_count += 1
                                self._log(f"  Swarm [{pid[:15]}]: {consensus} (Score: {swarm_result.get('overall_score', 0)})")
                            except Exception as se:
                                self._log(f"  Swarm error for {pid[:15]}: {se}")
                                logger.warning(f"Swarm audit error for {pid}: {se}", exc_info=True)

                        # ── AI Supervisor: Validate ALL discovered products ──
                        try:
                            validation_summary = supervisor.validate_products_batch(
                                products=results,
                                marketplace=region.lower(),
                                region=region
                            )
                            self._log(
                                f"  🧠 AI Validation [{category[:25]}]: "
                                f"{validation_summary['valid']} valid, "
                                f"{validation_summary['invalid']} flagged, "
                                f"{validation_summary['auto_deleted']} auto-deleted"
                            )
                        except Exception as ve:
                            self._log(f"  AI validation notice for {category[:25]}: {ve}")
                    else:
                        self._log(f"  Niche complete: {category[:30]}")
                except Exception as e:
                    self._log(f"  Error scanning {category[:30]}: {e}")
                    logger.warning(f"Niche scan error {category}: {e}", exc_info=True)

                # Polite delay between niches
                if not self._stop_event.is_set():
                    time.sleep(6)

            cycle += 1
            self._log(f"Cycle {cycle} complete — search space: {len(active_niches)} niches — restarting")
            if not self._stop_event.is_set():
                time.sleep(45)

        self._log("Daemon stopped.")

    def start(self):
        """Start the background daemon thread (idempotent — safe to call multiple times)."""
        if self._started and self._thread and self._thread.is_alive():
            return  # Already running
        self._stop_event.clear()
        self._pause_event.set()
        self._thread = threading.Thread(
            target=self._worker,
            name="aprs-daemon",
            daemon=True  # dies with the process
        )
        self._thread.start()
        self._started = True
        logger.info("DaemonController: background thread started")

    def pause(self):
        """Pause scraping between niches."""
        self._pause_event.clear()
        with self._lock:
            self._is_paused = True
        logger.info("DaemonController: paused")

    def resume(self):
        """Resume scraping."""
        self._pause_event.set()
        with self._lock:
            self._is_paused = False
        logger.info("DaemonController: resumed")

    def stop(self):
        """Signal the daemon to stop after current niche completes."""
        self._stop_event.set()
        self._pause_event.set()  # unblock if paused
        logger.info("DaemonController: stop requested")

    def get_status(self) -> Dict[str, Any]:
        """Return current daemon status as a plain dict (safe to read from any thread)."""
        with self._lock:
            return {
                "is_paused":               self._is_paused,
                "current_niche":           self._current_niche,
                "niche_index":             self._niche_index,
                "total_niches":            self._total_niches,
                "total_discovered_session": self._total_discovered_session,
                "swarm_pass_count":        self._swarm_pass_count,
                "swarm_fail_count":        self._swarm_fail_count,
                "recent_logs":             list(self._recent_logs[-20:]),
                "thread_alive":            bool(self._thread and self._thread.is_alive()),
            }


# ── Module-level singleton — imported by main.py and web/app.py ───────────
daemon_controller = DaemonController()
