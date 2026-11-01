"""
Safe Database Migration Manager.
Handles:
- Schema version detection
- Automated timestamped database backups with verification
- Migration dry-run preview and record reconciliation on isolated temp copies
- Controlled, user-confirmed execution
"""
import os
import shutil
import sqlite3
import hashlib
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from database.db import Database
from database.migration_stage2 import (
    MIGRATION_VERSION,
    apply_stage2_migration,
    rollback_stage2_migration
)

STAGE2_REQUIRED_TABLES = [
    "schema_migrations",
    "suppliers",
    "storage_locations",
    "inventory_batches",
    "purchases",
    "purchase_items",
    "stock_movements",
    "sale_batch_allocations",
    "sale_returns",
    "sale_return_items"
]

class MigrationManager:
    """Manages database schema state, backups, previews, and safe migrations."""

    def __init__(self, db_path: str = "data/pharmacy.db"):
        self.db_path = os.path.abspath(db_path)

    def detect_schema_state(self) -> Dict[str, Any]:
        """Inspects the target database and determines schema version and table status."""
        if not os.path.exists(self.db_path):
            return {
                "exists": False,
                "db_path": self.db_path,
                "version": "NOT_FOUND",
                "is_migrated": False,
                "missing_tables": STAGE2_REQUIRED_TABLES,
                "existing_tables": []
            }

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row[0] for row in cursor.fetchall()]

        missing_tables = [t for t in STAGE2_REQUIRED_TABLES if t not in existing_tables]

        version = "STAGE1_LEGACY"
        if "schema_migrations" in existing_tables:
            cursor.execute("SELECT version FROM schema_migrations ORDER BY migration_id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                version = row[0]

        is_migrated = len(missing_tables) == 0 and version == MIGRATION_VERSION
        conn.close()

        return {
            "exists": True,
            "db_path": self.db_path,
            "version": version,
            "is_migrated": is_migrated,
            "migration_required": not is_migrated,
            "missing_tables": missing_tables,
            "existing_tables": existing_tables
        }

    def create_verified_backup(self, backup_dir: Optional[str] = None) -> Dict[str, Any]:
        """Creates a timestamped backup of the database and verifies its integrity."""
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found at {self.db_path}")

        if backup_dir is None:
            backup_dir = os.path.join(os.path.dirname(self.db_path), "backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.basename(self.db_path)
        backup_filename = f"{base_name}.backup_{timestamp}"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Copy database safely
        shutil.copy2(self.db_path, backup_path)

        # Compute SHA-256 hash for both
        def get_sha256(filepath: str) -> str:
            h = hashlib.sha256()
            with open(filepath, "rb") as f:
                while chunk := f.read(65536):
                    h.update(chunk)
            return h.hexdigest()

        src_hash = get_sha256(self.db_path)
        dst_hash = get_sha256(backup_path)

        if src_hash != dst_hash:
            raise IOError("Backup file hash does not match original database!")

        # Verify backup opens and integrity passes
        conn = sqlite3.connect(backup_path)
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check")
        integrity_result = cur.fetchone()[0]
        conn.close()

        if integrity_result != "ok":
            raise ValueError(f"Backup integrity check failed: {integrity_result}")

        return {
            "status": "SUCCESS",
            "backup_path": backup_path,
            "size_bytes": os.path.getsize(backup_path),
            "sha256": dst_hash,
            "verified": True,
            "created_at": timestamp
        }

    def preview_migration_on_isolated_copy(self) -> Dict[str, Any]:
        """
        Runs migration on an isolated temporary database copy to produce a reconciliation report
        without touching the real database.
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found at {self.db_path}")

        # Create isolated temp copy
        temp_dir = os.path.join(os.path.dirname(self.db_path), "temp_preview")
        os.makedirs(temp_dir, exist_ok=True)
        temp_db_path = os.path.join(temp_dir, f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        shutil.copy2(self.db_path, temp_db_path)

        try:
            # Collect before metrics
            conn = sqlite3.connect(temp_db_path)
            cur = conn.cursor()

            def count_table(cursor: sqlite3.Cursor, table: str) -> int:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    row = cursor.fetchone()
                    return row[0] if row else 0
                except Exception:
                    return 0

            before_counts = {
                "users": count_table(cur, "users"),
                "stores": count_table(cur, "stores"),
                "medicines": count_table(cur, "medicines"),
                "sales": count_table(cur, "sales"),
                "sale_items": count_table(cur, "sale_items"),
                "fmea_records": count_table(cur, "fmea_records"),
                "sqc_defects": count_table(cur, "sqc_defects"),
                "pdca_items": count_table(cur, "pdca_items"),
            }
            conn.close()

            # Run migration on temp copy
            temp_db = Database(temp_db_path)
            migration_report = apply_stage2_migration(temp_db)

            # Collect after metrics
            conn2 = sqlite3.connect(temp_db_path)
            cur2 = conn2.cursor()
            after_counts = {
                "users": count_table(cur2, "users"),
                "stores": count_table(cur2, "stores"),
                "medicines": count_table(cur2, "medicines"),
                "sales": count_table(cur2, "sales"),
                "sale_items": count_table(cur2, "sale_items"),
                "fmea_records": count_table(cur2, "fmea_records"),
                "sqc_defects": count_table(cur2, "sqc_defects"),
                "pdca_items": count_table(cur2, "pdca_items"),
                "inventory_batches": count_table(cur2, "inventory_batches"),
                "suppliers": count_table(cur2, "suppliers"),
                "storage_locations": count_table(cur2, "storage_locations"),
                "purchases": count_table(cur2, "purchases"),
                "stock_movements": count_table(cur2, "stock_movements"),
            }

            # Check foreign key integrity
            cur2.execute("PRAGMA foreign_key_check")
            fk_violations = cur2.fetchall()
            conn2.close()

            # Check counts preservation
            preserved = True
            for key in ["users", "stores", "medicines", "sales", "sale_items", "fmea_records", "sqc_defects", "pdca_items"]:
                if before_counts.get(key, 0) != after_counts.get(key, 0):
                    preserved = False

            return {
                "status": "READY_FOR_APPROVAL",
                "preview_db_path": temp_db_path,
                "before_counts": before_counts,
                "after_counts": after_counts,
                "core_data_preserved": preserved,
                "fk_violations_count": len(fk_violations),
                "fk_violations": fk_violations,
                "reconciliation_summary": migration_report.get("reconciliation_summary"),
                "batches_created": migration_report.get("batches_created"),
                "stock_movements_logged": migration_report.get("stock_movements_logged"),
                "shelf_conflicts_detected": migration_report.get("shelf_conflicts_detected"),
                "details": migration_report
            }
        finally:
            # Clean up temp file
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass

    def execute_approved_migration(self, explicit_confirmation: bool = False) -> Dict[str, Any]:
        """
        Executes the migration on the real database ONLY IF explicit confirmation is granted.
        Creates an automatic backup before running.
        """
        if not explicit_confirmation:
            raise PermissionError(
                "Migration execution refused: explicit confirmation flag is False. "
                "Per academic and safety policy, production database cannot be modified without user approval."
            )

        # 1. Create verified backup
        backup_result = self.create_verified_backup()

        # 2. Run migration
        real_db = Database(self.db_path)
        migration_report = apply_stage2_migration(real_db)

        return {
            "status": "MIGRATED_SUCCESSFULLY",
            "backup": backup_result,
            "migration_report": migration_report,
            "migrated_at": datetime.now().isoformat()
        }
