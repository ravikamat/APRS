#!/usr/bin/env python3
"""
main.py — APRS V6 Pro CLI Entry Point.

Commands:
  scan      Run discovery + 4-gate pipeline for niches (batch, no daemon)
  web       Launch 4-tab Streamlit dashboard
  eval      Evaluate single product through 4-gate pipeline
  list      List products in database
  backup    Database backup/restore operations
"""
import argparse
import asyncio
import json
import sys
import subprocess
from pathlib import Path
from typing import List, Optional

# Ensure project root on path
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.settings import settings
from core.database import init_db, get_all_products
from core.validation import CanonicalProduct
from core.gate_engine import GateEngine
from core.rule_engine import create_rule_engine
from core.economics_engine import Comprehensive15FactorEconomics
from core.pipeline import run_pipeline_cli, run_full_pipeline, PipelineConfig


def setup_database():
    """Initialize database on startup."""
    init_db()
    print("[INIT] Database initialized")


def cmd_scan(args):
    """Run batch discovery and evaluation."""
    print(f"[SCAN] Starting batch scan: region={args.region}, category={args.category}")
    print(f"       max_niches={args.max_niches}, max_candidates={args.max_candidates}")
    
    config = PipelineConfig(
        region=args.region,
        category=args.category or "General",
        max_niches=args.max_niches,
        max_candidates_per_niche=args.max_candidates,
        max_pages=args.max_pages,
        use_seed_keywords=not args.no_seeds,
        competitor_count=args.competitors,
        min_margin_pct=args.min_margin,
        min_score=args.min_score,
    )
    
    results = asyncio.run(run_full_pipeline(config))
    
    # Output results
    if args.output:
        with open(args.output, "w") as f:
            json.dump([
                {
                    "product": r.product.canonical_title,
                    "verdict": r.final_verdict,
                    "score": r.score_breakdown.get("total_score", 0) if r.score_breakdown else 0,
                    "gates_passed": sum(1 for g in r.gate_results if g.passed),
                }
                for r in results
            ], f, indent=2)
        print(f"[SCAN] Results saved to {args.output}")
    else:
        print(json.dumps([
            {
                "product": r.product.canonical_title,
                "verdict": r.final_verdict,
                "score": r.score_breakdown.get("total_score", 0) if r.score_breakdown else 0,
            }
            for r in results
        ], indent=2))


def cmd_web(args):
    """Launch Streamlit web dashboard."""
    print("[WEB] Launching APRS V6 Pro Dashboard...")
    print("      Dashboard will be available at http://localhost:8501")
    
    app_path = _ROOT / "web" / "app.py"
    env = dict(**sys.environ)
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    
    try:
        subprocess.run(
            ["streamlit", "run", str(app_path), "--server.headless", "true"],
            env=env,
            check=True,
        )
    except KeyboardInterrupt:
        print("\n[WEB] Dashboard stopped")
    except subprocess.CalledProcessError as e:
        print(f"[WEB] Error launching dashboard: {e}")
        sys.exit(1)


def cmd_eval(args):
    """Evaluate a single product through 4-gate pipeline."""
    print(f"[EVAL] Evaluating: {args.title}")
    
    # Create canonical product from args
    product = CanonicalProduct(
        canonical_title=args.title,
        category=args.category,
        retail_price_inr=args.msrp,
        amazon_asin=args.asin,
        amazon_bsr=args.bsr,
        rating=args.rating,
        review_count=args.reviews,
        factory_fob_inr=args.fob,
    )
    
    gate_engine = GateEngine()
    rule_engine = create_rule_engine()
    
    # Gate 1: Signal
    g1 = gate_engine.run_gate_1_signal(
        product=product,
        bsr_current=args.bsr or 50000,
        price_current=args.msrp,
        price_30d_ago=args.msrp * 1.02,
    )
    print(f"\nGate 1 (Signal): {g1.status.value}")
    print(f"  BSR: {g1.details.get('bsr_current')} (threshold: {g1.details.get('bsr_threshold')})")
    print(f"  Price CV: {g1.details.get('price_cv'):.4f} (threshold: {g1.details.get('cv_threshold')})")
    
    if not g1.passed:
        print("  -> FAILED: Stopping pipeline")
        return
    
    # Gate 2: Defects
    print("\nGate 2 (Defects): SKIPPED (requires Ollama + 3-star reviews)")
    print("  Provide --reviews with 3-star review texts to enable")
    
    # Gate 3: Economics
    g3 = gate_engine.run_gate_3_economics(
        product=product,
        fob_price=args.fob or args.msrp * 0.25,
        planned_msrp=args.msrp,
        region=args.region,
        category=args.category,
    )
    print(f"\nGate 3 (Economics): {g3.status.value}")
    exp = g3.details.get("expected", {})
    print(f"  Expected Net Margin: {exp.get('net_margin_pct', 0):.2f}%")
    print(f"  Expected Gross Margin: {exp.get('gross_margin_pct', 0):.2f}%")
    print(f"  Landed COGS: Rs.{exp.get('landed_cogs', 0):.2f}")
    print(f"  Conservative Net Margin: {g3.details.get('conservative', {}).get('net_margin_pct', 0):.2f}%")
    
    if not g3.passed:
        print("  -> FAILED: Stopping pipeline")
        return
    
    # Gate 4: Scoring
    g4 = gate_engine.run_gate_4_scoring(
        product=product,
        bsr=args.bsr,
        rating=args.rating,
        review_count=args.reviews,
        net_margin_pct=exp.get("net_margin_pct", 0),
        has_defects=args.has_defects,
        competitor_count=args.competitors,
    )
    print(f"\nGate 4 (Scoring): {g4.status.value}")
    print(f"  Total Score: {g4.details.get('total_score', 0):.1f} (threshold: {g4.details.get('threshold')})")
    print(f"  Verdict: {g4.details.get('verdict')}")
    print(f"  Breakdown:")
    for k, v in g4.details.get("breakdown", {}).items():
        print(f"    {k}: {v:.1f}")
    
    # Rule engine evaluation
    gate_results = {1: g1.details, 3: g3.details, 4: g4.details}
    rule_result = rule_engine.evaluate_product({
        "product_id": args.asin or "manual",
        "bsr": args.bsr,
        "price_cv": g1.details.get("price_cv", 0),
        "category": args.category,
        "net_margin_pct": exp.get("net_margin_pct", 0),
        "rating": args.rating,
        "review_count": args.reviews,
        "competitor_count": args.competitors,
        "lead_time_days": 30,
        "trend_half_life_days": 90,
        "has_defects": args.has_defects,
        "actionable_defects": 1 if args.has_defects else 0,
        "score": g4.details.get("total_score", 0),
    }, gate_results)
    
    print(f"\nRule Engine:")
    print(f"  Adjusted Score: {rule_result['adjusted_score']:.1f}")
    print(f"  Verdict: {rule_result['verdict']}")
    if rule_result['warnings']:
        for w in rule_result['warnings']:
            print(f"  - {w}")
    
    # Final result
    final = "PROCEED" if g4.passed and rule_result['verdict'] != "REJECT" else "REJECT"
    print(f"\n{'='*50}")
    print(f"FINAL VERDICT: {final}")
    print(f"{'='*50}")


def cmd_list(args):
    """List products in database."""
    products = get_all_products(include_deleted=args.include_deleted)
    
    if args.region:
        products = [p for p in products if p.get("region") == args.region]
    if args.category:
        products = [p for p in products if p.get("category") == args.category]
    if args.shortlisted:
        products = [p for p in products if p.get("is_shortlisted") == 1]
    
    print(f"Found {len(products)} products")
    for p in products[:args.limit]:
        print(f"  {p['product_id']}: {p['name'][:60]} | {p['region']} | "
              f"Score: {p.get('overall_score', 0):.0f} | "
              f"Net: {p.get('net_profit_pct', 0):.1f}% | "
              f"Status: {p.get('status', 'N/A')}")


def cmd_backup(args):
    """Database backup/restore operations."""
    from core.backup import DatabaseBackup, main as backup_main
    import sys
    sys.argv = ["backup"] + sys.argv[2:]
    backup_main()


def main():
    parser = argparse.ArgumentParser(
        description="APRS V6 Pro — Autonomous Product Research System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run batch discovery scan
  python main.py scan --region India --max-niches 5 --max-candidates 3
  
  # Launch web dashboard
  python main.py web
  
  # Evaluate single product
  python main.py eval --title "Stainless Steel Water Bottle" --msrp 1299 --fob 350 --bsr 15000
  
  # List products in DB
  python main.py list --region India --shortlisted
  
  # Database backup
  python main.py backup --backup
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # scan command
    scan_parser = subparsers.add_parser("scan", help="Run batch discovery scan")
    scan_parser.add_argument("--region", default="India", help="Target region")
    scan_parser.add_argument("--category", default="General", help="Product category")
    scan_parser.add_argument("--max-niches", type=int, default=5, help="Max niches to process")
    scan_parser.add_argument("--max-candidates", type=int, default=3, help="Max candidates per niche")
    scan_parser.add_argument("--max-pages", type=int, default=2, help="Max pages per search")
    scan_parser.add_argument("--no-seeds", action="store_true", help="Don't use seed keywords")
    scan_parser.add_argument("--competitors", type=int, default=10, help="Default competitor count")
    scan_parser.add_argument("--min-margin", type=float, default=20.0, help="Min net margin %")
    scan_parser.add_argument("--min-score", type=int, default=75, help="Min score threshold")
    scan_parser.add_argument("--output", help="Save results to JSON file")
    
    # web command
    web_parser = subparsers.add_parser("web", help="Launch Streamlit dashboard")
    
    # eval command
    eval_parser = subparsers.add_parser("eval", help="Evaluate single product")
    eval_parser.add_argument("--title", required=True, help="Product title")
    eval_parser.add_argument("--category", default="General", help="Product category")
    eval_parser.add_argument("--msrp", type=float, required=True, help="Planned MSRP (INR)")
    eval_parser.add_argument("--fob", type=float, help="Factory FOB price (INR)")
    eval_parser.add_argument("--bsr", type=int, help="Amazon BSR rank")
    eval_parser.add_argument("--rating", type=float, default=4.0, help="Product rating")
    eval_parser.add_argument("--reviews", type=int, default=100, help="Review count")
    eval_parser.add_argument("--asin", help="Amazon ASIN")
    eval_parser.add_argument("--region", default="India", help="Target region")
    eval_parser.add_argument("--competitors", type=int, default=10, help="Competitor count")
    eval_parser.add_argument("--has-defects", action="store_true", help="Has actionable defects")
    
    # list command
    list_parser = subparsers.add_parser("list", help="List products in database")
    list_parser.add_argument("--region", help="Filter by region")
    list_parser.add_argument("--category", help="Filter by category")
    list_parser.add_argument("--shortlisted", action="store_true", help="Only shortlisted")
    list_parser.add_argument("--include-deleted", action="store_true", help="Include deleted")
    list_parser.add_argument("--limit", type=int, default=50, help="Max results")
    
    # backup command
    backup_parser = subparsers.add_parser("backup", help="Database backup/restore")
    backup_parser.add_argument("--backup", action="store_true", help="Create backup now")
    backup_parser.add_argument("--list", action="store_true", help="List backups")
    backup_parser.add_argument("--restore", help="Restore from backup name")
    backup_parser.add_argument("--max-backups", type=int, default=30, help="Max backups to retain")
    
    args = parser.parse_args()
    
    # Initialize database
    setup_database()
    
    # Route to command
    if args.command == "scan":
        cmd_scan(args)
    elif args.command == "web":
        cmd_web(args)
    elif args.command == "eval":
        cmd_eval(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "backup":
        cmd_backup(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()