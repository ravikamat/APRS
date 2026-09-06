"""
core/maintenance.py — Database Maintenance & TTL Jobs.

Automated cleanup, backups, and health checks.
"""
import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

from core.database import get_connection, get_db_path

logger = logging.getLogger("aprs.maintenance")


class MaintenanceManager:
    """Database maintenance and TTL job manager."""
    
    def __init__(self):
        self.db_path = get_db_path()
    
    def cleanup_old_data(self) -> Dict[str, int]:
        """Run all TTL cleanup jobs. Returns count of deleted rows per table."""
        conn = get_connection()
        cur = conn.cursor()
        
        results = {}
        
        # 1. ai_supervisor_logs: 14 days (uses timestamp)
        cur.execute("DELETE FROM ai_supervisor_logs WHERE timestamp < datetime('now', '-14 days')")
        results["ai_supervisor_logs"] = cur.rowcount
        
        # 2. scraped_listings: 30 days after validation (keep validated ones)
        cur.execute("""
            DELETE FROM scraped_listings 
            WHERE extracted_at < datetime('now', '-30 days')
            AND listing_id NOT IN (
                SELECT DISTINCT listing_id FROM scraper_validations
            )
        """)
        results["scraped_listings"] = cur.rowcount
        
        # 3. swarm_audit_log: 90 days (uses timestamp)
        cur.execute("DELETE FROM swarm_audit_log WHERE timestamp < datetime('now', '-90 days')")
        results["swarm_audit_log"] = cur.rowcount
        
        # 4. gate_logs: 180 days (uses created_at)
        cur.execute("DELETE FROM gate_logs WHERE created_at < datetime('now', '-180 days')")
        results["gate_logs"] = cur.rowcount
        
        # 5. arbiter_decision_log: 180 days (uses evaluation_date)
        cur.execute("DELETE FROM arbiter_decision_log WHERE evaluation_date < date('now', '-180 days')")
        results["arbiter_decision_log"] = cur.rowcount
        
        # 6. daily_snapshots: 365 days (keep 1 year of history)
        cur.execute("DELETE FROM daily_snapshots WHERE date < date('now', '-365 days')")
        results["daily_snapshots"] = cur.rowcount
        
        # 7. agent_health: 30 days (keep recent health checks, uses checked_at)
        cur.execute("DELETE FROM agent_health WHERE checked_at < datetime('now', '-30 days')")
        results["agent_health"] = cur.rowcount
        
        # 8. trend_signals: 90 days (keep recent trends, uses created_at)
        cur.execute("DELETE FROM trend_signals WHERE created_at < datetime('now', '-90 days')")
        results["trend_signals"] = cur.rowcount
        
        # 9. review_snapshots: 180 days (uses scraped_at)
        cur.execute("DELETE FROM review_snapshots WHERE scraped_at < datetime('now', '-180 days')")
        results["review_snapshots"] = cur.rowcount
        
        # 10. url_validation_log: 30 days (uses validated_at)
        cur.execute("DELETE FROM url_validation_log WHERE validated_at < datetime('now', '-30 days')")
        results["url_validation_log"] = cur.rowcount
        
        # 11. website_capture_stats: 30 days (uses created_at)
        cur.execute("DELETE FROM website_capture_stats WHERE created_at < datetime('now', '-30 days')")
        results["website_capture_stats"] = cur.rowcount
        
        # 12. Clean up resolved pending_human_decisions older than 7 days
        cur.execute("""
            DELETE FROM pending_human_decisions 
            WHERE status IN ('RESOLVED', 'EXPIRED') 
            AND decided_at < datetime('now', '-7 days')
        """)
        results["pending_human_decisions"] = cur.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"TTL cleanup completed: {results}")
        return results
    
    def vacuum_database(self) -> Dict[str, Any]:
        """Run VACUUM to reclaim space and optimize."""
        logger.info("Starting database VACUUM...")
        
        before_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("VACUUM")
        conn.close()
        
        after_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        reclaimed = before_size - after_size
        
        result = {
            "before_size_mb": round(before_size / 1024 / 1024, 2),
            "after_size_mb": round(after_size / 1024 / 1024, 2),
            "reclaimed_mb": round(reclaimed / 1024 / 1024, 2),
            "reclaimed_pct": round(reclaimed / before_size * 100, 1) if before_size > 0 else 0,
        }
        
        logger.info(f"VACUUM completed: {result}")
        return result
    
    def analyze_database(self) -> Dict[str, Any]:
        """Run ANALYZE to update query planner statistics."""
        logger.info("Running ANALYZE...")
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("ANALYZE")
        conn.close()
        
        return {"status": "completed"}
    
    def check_integrity(self) -> Dict[str, Any]:
        """Run PRAGMA integrity_check."""
        logger.info("Running integrity check...")
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        result = cur.fetchone()[0]
        conn.close()
        
        return {
            "integrity_check": result,
            "healthy": result == "ok",
        }
    
    def get_table_stats(self) -> List[Dict[str, Any]]:
        """Get row counts and sizes for all tables."""
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cur.fetchall()]
        
        stats = []
        for table in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                stats.append({"table": table, "row_count": count})
            except:
                stats.append({"table": table, "row_count": -1})
        
        conn.close()
        return sorted(stats, key=lambda x: x["row_count"], reverse=True)
    
    def create_backup(self, backup_dir: str = None) -> str:
        """Create a timestamped backup of the database."""
        if backup_dir is None:
            backup_dir = self.db_path.parent / "backups"
        else:
            backup_dir = Path(backup_dir)
        
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"research_engine_{timestamp}.db"
        backup_path = backup_dir / backup_name
        
        # Use SQLite backup API for consistent backup
        source = sqlite3.connect(str(self.db_path))
        dest = sqlite3.connect(str(backup_path))
        
        source.backup(dest)
        
        source.close()
        dest.close()
        
        # Compress backup
        compressed_path = backup_path.with_suffix(".db.gz")
        subprocess.run(["gzip", "-f", str(backup_path)], capture_output=True)
        
        size_mb = compressed_path.stat().st_size / 1024 / 1024
        
        logger.info(f"Backup created: {compressed_path} ({size_mb:.1f} MB)")
        return str(compressed_path)
    
    def cleanup_old_backups(self, backup_dir: str = None, max_backups: int = 30) -> int:
        """Remove old backups, keeping only the most recent N."""
        if backup_dir is None:
            backup_dir = self.db_path.parent / "backups"
        else:
            backup_dir = Path(backup_dir)
        
        if not backup_dir.exists():
            return 0
        
        backups = sorted(backup_dir.glob("research_engine_*.db.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
        
        deleted = 0
        for backup in backups[max_backups:]:
            backup.unlink()
            deleted += 1
        
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old backups")
        
        return deleted
    
    def run_full_maintenance(self) -> Dict[str, Any]:
        """Run complete maintenance cycle."""
        logger.info("=" * 50)
        logger.info("STARTING FULL MAINTENANCE CYCLE")
        logger.info("=" * 50)
        
        results = {}
        
        # 1. TTL Cleanup
        results["ttl_cleanup"] = self.cleanup_old_data()
        
        # 2. Integrity Check
        results["integrity"] = self.check_integrity()
        
        if not results["integrity"]["healthy"]:
            logger.error("Integrity check FAILED - skipping VACUUM")
            results["vacuum"] = {"error": "Integrity check failed"}
            return results
        
        # 3. VACUUM
        results["vacuum"] = self.vacuum_database()
        
        # 4. ANALYZE
        results["analyze"] = self.analyze_database()
        
        # 5. Backup
        results["backup"] = self.create_backup()
        
        # 6. Cleanup old backups
        results["backup_cleanup"] = self.cleanup_old_backups()
        
        # 7. Table stats
        results["table_stats"] = self.get_table_stats()
        
        logger.info("=" * 50)
        logger.info("MAINTENANCE CYCLE COMPLETE")
        logger.info("=" * 50)
        
        return results


async def run_maintenance() -> Dict[str, Any]:
    """Run maintenance cycle."""
    manager = MaintenanceManager()
    return manager.run_full_maintenance()


async def run_ttl_cleanup() -> Dict[str, Any]:
    """Run just TTL cleanup."""
    manager = MaintenanceManager()
    return manager.cleanup_old_data()


async def create_backup() -> str:
    """Create a database backup."""
    manager = MaintenanceManager()
    return manager.create_backup()


if __name__ == "__main__":
    import asyncio
    result = asyncio.run(run_maintenance())
    print(f"Maintenance completed:")
    print(f"  TTL Cleanup: {result['ttl_cleanup']}")
    print(f"  Integrity: {result['integrity']}")
    print(f"  Vacuum: {result['vacuum']}")
    print(f"  Backup: {result['backup']}")