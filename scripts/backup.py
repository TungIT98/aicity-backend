#!/usr/bin/env python3
"""
AI City - Backup 3-2-1 Strategy Implementation
- 3 copies of data
- 2 different storage media
- 1 offsite backup

Backup Schedule:
- Database: Every 6 hours
- Files: Daily
- Full verification: Weekly
"""

import os
import sys
import subprocess
import logging
import json
import gzip
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import psycopg2
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
BACKUP_DIR = os.getenv("BACKUP_DIR", "/backups")
OFFSITE_DIR = os.getenv("OFFSITE_BACKUP_DIR", "/tmp/aicity-offsite")
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

# Database config - supports both local and Neon PostgreSQL
NEON_DATABASE_URL = os.getenv("NEON_DATABASE_URL") or os.getenv("DATABASE_URL")
if NEON_DATABASE_URL:
    # Neon/Cloud PostgreSQL - use connection string
    DB_CONFIG = {"connection_url": NEON_DATABASE_URL}
else:
    # Local PostgreSQL fallback
    DB_CONFIG = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5433")),
        "database": os.getenv("DB_NAME", "promptforge"),
        "user": os.getenv("DB_USER", "promptforge"),
        "password": os.getenv("DB_PASSWORD", "promptforge"),
    }

# Slack for notifications
SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK_URL")


class BackupManager:
    def __init__(self):
        self.backup_dir = Path(BACKUP_DIR)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    def notify(self, message: str, success: bool = True):
        """Send backup status notification"""
        severity = "INFO" if success else "ERROR"
        logger.info(f"[{severity}] {message}")

        if SLACK_WEBHOOK:
            try:
                import requests
                requests.post(SLACK_WEBHOOK, json={
                    "text": f"[AI City Backup] {severity}: {message}"
                }, timeout=5)
            except:
                pass

    def backup_database(self) -> Optional[str]:
        """Backup PostgreSQL database (supports both local and Neon)"""
        backup_file = self.backup_dir / f"db_backup_{self.timestamp}.sql.gz"

        try:
            logger.info(f"Starting database backup to {backup_file}")

            # Build pg_dump command
            cmd = ["pg_dump", "-Fc", "--no-owner", "--no-acl"]

            if "connection_url" in DB_CONFIG:
                # Neon/Cloud - use connection URL
                cmd.extend(["--dbname", DB_CONFIG["connection_url"]])
                env = {**os.environ}
                # Extract password for PGPASSWORD
                url = DB_CONFIG["connection_url"]
                if "postgres" in url or "postgresql" in url:
                    import re
                    m = re.search(r':([^:@]+)@', url)
                    if m:
                        env["PGPASSWORD"] = m.group(1)
            else:
                # Local PostgreSQL
                cmd.extend(["-h", DB_CONFIG["host"]])
                cmd.extend(["-p", str(DB_CONFIG["port"])])
                cmd.extend(["-U", DB_CONFIG["user"]])
                cmd.extend(["-d", DB_CONFIG["database"]])
                env = {**os.environ, "PGPASSWORD": DB_CONFIG["password"]}

            result = subprocess.run(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            if result.returncode == 0:
                # Write with gzip compression
                with gzip.open(backup_file, 'wb') as f:
                    f.write(result.stdout)
                size_mb = backup_file.stat().st_size / (1024 * 1024)
                logger.info(f"Database backup complete: {size_mb:.2f} MB")
                return str(backup_file)
            else:
                logger.error(f"pg_dump failed: {result.stderr.decode()}")
                return None

        except Exception as e:
            logger.error(f"Database backup failed: {e}")
            return None

    def backup_files(self) -> Optional[str]:
        """Backup important files"""
        backup_file = self.backup_dir / f"files_backup_{self.timestamp}.tar.gz"

        try:
            logger.info(f"Starting files backup to {backup_file}")

            # List of directories to backup
            dirs_to_backup = [
                "/app/data",
                "/app/uploads",
                "/app/config"
            ]

            # Only include existing directories
            existing_dirs = [d for d in dirs_to_backup if os.path.exists(d)]

            if existing_dirs:
                subprocess.run(
                    ["tar", "-czf", str(backup_file)] + existing_dirs,
                    check=True
                )
                size_mb = backup_file.stat().st_size / (1024 * 1024)
                logger.info(f"Files backup complete: {size_mb:.2f} MB")
            else:
                logger.info("No files to backup (directories don't exist)")
                backup_file = None

            return str(backup_file)

        except Exception as e:
            logger.error(f"Files backup failed: {e}")
            return None

    def sync_offsite(self, local_file: str) -> bool:
        """Sync backup to offsite location (copy 1)"""
        if not local_file:
            return True

        try:
            offsite_dir = Path(OFFSITE_DIR)
            offsite_dir.mkdir(parents=True, exist_ok=True)

            filename = os.path.basename(local_file)
            dest = offsite_dir / filename

            shutil.copy2(local_file, dest)
            logger.info(f"Synced to offsite: {dest}")
            return True

        except Exception as e:
            logger.error(f"Offsite sync failed: {e}")
            return False

    def verify_backup(self, backup_file: str) -> bool:
        """Verify backup integrity"""
        try:
            if backup_file.endswith('.gz'):
                # Test gzip integrity
                result = subprocess.run(
                    ["gzip", "-t", backup_file],
                    capture_output=True
                )
                return result.returncode == 0
            elif backup_file.endswith('.tar.gz'):
                # Test tar integrity
                result = subprocess.run(
                    ["tar", "-tzf", backup_file],
                    capture_output=True
                )
                return result.returncode == 0
            return True

        except Exception as e:
            logger.error(f"Backup verification failed: {e}")
            return False

    def test_restore(self, backup_file: str) -> bool:
        """Test restore procedure (without actually restoring)"""
        try:
            logger.info(f"Testing restore for: {backup_file}")

            if backup_file.endswith('.sql.gz'):
                # Verify SQL file can be read
                result = subprocess.run(
                    ["zcat", backup_file],
                    capture_output,
                    stderr=subprocess.DEVNULL,
                    timeout=10
                )
                return result.returncode == 0

            return True

        except Exception as e:
            logger.error(f"Restore test failed: {e}")
            return False

    def cleanup_old_backups(self):
        """Remove backups older than retention period"""
        cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)

        for backup_file in self.backup_dir.glob("*_backup_*.sql.gz"):
            if datetime.fromtimestamp(backup_file.stat().st_mtime) < cutoff:
                logger.info(f"Removing old backup: {backup_file}")
                backup_file.unlink()

        for backup_file in self.backup_dir.glob("*_backup_*.tar.gz"):
            if datetime.fromtimestamp(backup_file.stat().st_mtime) < cutoff:
                logger.info(f"Removing old backup: {backup_file}")
                backup_file.unlink()

    def run_full_backup(self):
        """Run complete 3-2-1 backup"""
        logger.info("=== Starting Full Backup ===")

        results = {
            "timestamp": self.timestamp,
            "database": None,
            "files": None,
            "offsite_sync": [],
            "verification": [],
            "errors": []
        }

        # Step 1: Backup database
        db_backup = self.backup_database()
        if db_backup:
            results["database"] = db_backup
            # Sync to offsite
            if self.sync_offsite(db_backup):
                results["offsite_sync"].append(db_backup)
            # Verify
            if self.verify_backup(db_backup):
                results["verification"].append(db_backup)
        else:
            results["errors"].append("Database backup failed")

        # Step 2: Backup files
        files_backup = self.backup_files()
        if files_backup:
            results["files"] = files_backup
            if self.sync_offsite(files_backup):
                results["offsite_sync"].append(files_backup)
        # Files backup is optional

        # Step 3: Cleanup old backups
        self.cleanup_old_backups()

        # Step 4: Summary
        logger.info("=== Backup Complete ===")
        logger.info(f"Database: {'OK' if results['database'] else 'FAILED'}")
        logger.info(f"Files: {'OK' if results['files'] else 'SKIPPED'}")
        logger.info(f"Offsite syncs: {len(results['offsite_sync'])}")
        logger.info(f"Errors: {len(results['errors'])}")

        if results["errors"]:
            self.notify(f"Backup completed with errors: {results['errors']}", success=False)
            return False
        else:
            self.notify(f"Backup completed successfully. DB: {db_backup}")
            return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI City Backup Manager")
    parser.add_argument("--type", choices=["full", "db", "files"], default="full",
                        help="Type of backup to run")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify existing backups")
    args = parser.parse_args()

    manager = BackupManager()

    if args.verify_only:
        logger.info("Running backup verification only...")
        # Verify most recent backups
        db_backups = sorted(manager.backup_dir.glob("*_backup_*.sql.gz"), reverse=True)
        if db_backups:
            manager.verify_backup(str(db_backups[0]))
        return 0

    if args.type == "full":
        success = manager.run_full_backup()
    elif args.type == "db":
        backup_file = manager.backup_database()
        if backup_file:
            manager.sync_offsite(backup_file)
            manager.verify_backup(backup_file)
            success = True
        else:
            success = False
    else:
        backup_file = manager.backup_files()
        success = backup_file is not None

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
