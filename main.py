import argparse
import sys
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Load .env first (settings.py does this too, but be explicit here)
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from core.orchestrator import AutonomousProductResearchOrchestrator
from core.excel_manager import update_master_excel
from core.background_daemon import daemon_controller


def run_cli_pipeline(region="India", category="Smart Kitchen Storage", max_candidates=5):
    orchestrator = AutonomousProductResearchOrchestrator()
    res = orchestrator.discover_and_evaluate_products(
        region=region, category=category, max_candidates=max_candidates
    )
    print("\n[RESULT SUMMARY]")
    print(f"Total Discovered & Ingested: {len(res)}")
    return res


def launch_web_ui():
    print("\n=======================================================")
    print("APRS V5 WEB DASHBOARD & AUTONOMOUS DAEMON")
    print("Dashboard URL: http://localhost:8501")
    print("24/7 Background Scraping Daemon: ACTIVE (23 Niches)")
    print("=======================================================\n")

    # Start the continuous background scraping daemon
    daemon_controller.start()

    app_path = Path(__file__).resolve().parent / "web" / "app.py"
    subprocess.run(["streamlit", "run", str(app_path), "--server.headless", "true"])


def run_overnight_daemon():
    """
    Standalone 24/7 overnight daemon — does NOT launch Streamlit.
    Runs background scraping loop indefinitely, logging to console.
    """
    print("\n=======================================================")
    print("APRS V5 OVERNIGHT AUTONOMOUS SCRAPER — DAEMON MODE")
    print("No UI. Background scanning 23 niches indefinitely.")
    print("Press Ctrl+C to stop.")
    print("=======================================================\n")

    daemon_controller.start()

    try:
        while True:
            status = daemon_controller.get_status()
            print(
                f"[{time.strftime('%H:%M:%S')}] "
                f"Niche {status['niche_index']}/{status['total_niches']}: "
                f"{status['current_niche']} | "
                f"Session total: {status['total_discovered_session']} products | "
                f"{'PAUSED' if status['is_paused'] else 'RUNNING'}"
            )
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[OVERNIGHT] Ctrl+C received — stopping daemon.")
        daemon_controller.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="APRS V5 Autonomous Product Discovery Engine")
    parser.add_argument("--region",    type=str,  default="India",               help="Target region")
    parser.add_argument("--category",  type=str,  default="Smart Kitchen Storage", help="Target product category")
    parser.add_argument("--max",       type=int,  default=3,                     help="Max candidates to evaluate")
    parser.add_argument("--web",       action="store_true", help="Launch Web UI + 24/7 background daemon")
    parser.add_argument("--overnight", action="store_true", help="Standalone 24/7 overnight daemon (NO UI)")

    args = parser.parse_args()

    if args.web:
        launch_web_ui()
    elif args.overnight:
        run_overnight_daemon()
    else:
        run_cli_pipeline(region=args.region, category=args.category, max_candidates=args.max)
