"""
core/backup.py — Database Backup Automation for APRS V6 Pro.

Provides automated SQLite backup with rotation and compression.
"""
import gzip
import logging
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import settings

logger = logging.getLogger("aprs.backup")


class DatabaseBackup:
    """Handles automated SQLite database backups with rotation."""
    
    def __init__(
        self,
        db_path: Path = None,
        backup_dir: Path = None,
        max_backups: int = 30,
        compress: bool = True,
    ):
        self.db_path = db_path or settings.database_path
        self.backup_dir = backup_dir or (self.db_path.parent / "backups")
        self.max_backups = max_backups
        self.compress = compress
        
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def create_backup(self, suffix: str = "") -> Optional[Path]:
        """
        Create a consistent backup using SQLite's backup API.
        
        Returns path to backup file, or None on failure.
        """
        if not self.db_path.exists():
            logger.error(f"Database not found: {self.db_path}")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{self.db_path.stem}_{timestamp}"
        if suffix:
            backup_name += f"_{suffix}"
        
        if self.compress:
            backup_name += ".sqlite.gz"
        else:
            backup_name += ".sqlite"
        
        backup_path = self.backup_dir / backup_name
        
        try:
            # Use SQLite backup API for consistent snapshot
            source_conn = sqlite3.connect(str(self.db_path))
            dest_conn = sqlite3.connect(str(backup_path.with_suffix(".sqlite")))
            
            with dest_conn:
                source_conn.backup(dest_conn)
            
            source_conn.close()
            dest_conn.close()
            
            # Compress if requested
            if self.compress:
                with open(backup_path.with_suffix(".sqlite"), "rb") as f_in:
                    with gzip.open(backup_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out)
                backup_path.with_suffix(".sqlite").unlink()
            
            logger.info(f"Backup created: {backup_path} ({backup_path.stat().st_size / 1024:.1f} KB)")
            
            # Rotate old backups
            self._rotate_backups()
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            if backup_path.exists():
                backup_path.unlink(missing_ok=True)
            return None
    
    def _rotate_backups(self):
        """Remove old backups beyond max_backups limit."""
        backups = sorted(
            self.backup_dir.glob(f"{self.db_path.stem}_*.sqlite*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        
        for old_backup in backups[self.max_backups:]:
            try:
                old_backup.unlink()
                logger.info(f"Rotated old backup: {old_backup.name}")
            except Exception as e:
                logger.warning(f"Failed to rotate backup {old_backup}: {e}")
    
    def list_backups(self) -> list:
        """List all available backups with metadata."""
        backups = []
        for bp in sorted(self.backup_dir.glob(f"{self.db_path.stem}_*.sqlite*"), 
                        key=lambda p: p.stat().st_mtime, reverse=True):
            stat = bp.stat()
            backups.append({
                "name": bp.name,
                "path": str(bp),
                "size_kb": stat.st_size / 1024,
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "compressed": bp.suffix == ".gz",
            })
        return backups
    
    def restore_backup(self, backup_name: str, target_path: Path = None) -> bool:
        """Restore database from a backup file."""
        target = target_path or self.db_path
        backup_path = self.backup_dir / backup_name
        
        if not backup_path.exists():
            logger.error(f"Backup not found: {backup_path}")
            return False
        
        try:
            # Decompress if needed
            if backup_path.suffix == ".gz":
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
                    with gzip.open(backup_path, "rb") as f_in:
                        with open(tmp.name, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    restore_source = Path(tmp.name)
            else:
                restore_source = backup_path
            
            # Copy to target
            shutil.copy2(restore_source, target)
            
            if restore_source != backup_path:
                restore_source.unlink(missing_ok=True)
            
            logger.info(f"Restored database from {backup_name}")
            return True
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False


def create_cron_job(backup_script: Path = None, schedule: str = "0 2 * * *"):
    """
    Generate cron entry for automated backups.
    
    Default: Daily at 2 AM.
    """
    script = backup_script or Path(__file__).resolve()
    cron_entry = f"{schedule} {sys.executable} {script} --backup\n"
    return cron_entry


def main():
    """CLI entry point for backup operations."""
    import argparse
    
    parser = argparse.ArgumentParser(description="APRS V6 Pro Database Backup")
    parser.add_argument("--backup", action="store_true", help="Create backup now")
    parser.add_argument("--list", action="store_true", help="List backups")
    parser.add_argument("--restore", help="Restore from backup name")
    parser.add_argument("--cron", action="store_true", help="Print cron entry")
    parser.add_argument("--max-backups", type=int, default=30, help="Max backups to retain")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s — %(message)s")
    
    backup = DatabaseBackup(max_backups=args.max_backups)
    
    if args.cron:
        print(create_cron_job())
        return
    
    if args.backup:
        result = backup.create_backup()
        if result:
            print(f"✅ Backup created: {result}")
        else:
            print("❌ Backup failed")
            sys.exit(1)
    
    elif args.list:
        backups = backup.list_backups()
        if not backups:
            print("No backups found")
        else:
            for b in backups:
                print(f"  {b['name']}  |  {b['size_kb']:.1f} KB  |  {b['created']}  |  {'gz' if b['compressed'] else 'raw'}")
    
    elif args.restore:
        if backup.restore_backup(args.restore):
            print(f"✅ Restored from {args.restore}")
        else:
            print("❌ Restore failed")
            sys.exit(1)
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()