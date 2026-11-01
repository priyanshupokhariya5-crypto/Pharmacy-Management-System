"""
Comprehensive Automated Test Suite for Stage 2 Architecture & Database Migration.
Tests:
  1. Safe schema migration on a copy of representative legacy database.
  2. 100% preservation of all existing tables and records (users, stores, medicines, sales, fmea, sqc, pdca).
  3. Migration of all 23 audited medicine records into normalized inventory_batches.
  4. Quantity reconciliation between medicines.quantity, inventory_batches, and stock_movements.
  5. Idempotent repeat migration without duplicate batches or movements.
  6. Foreign key enforcement and PRAGMA foreign_key_check.
  7. Critical Shelf Allocation Rule (same medicine with different expiry requires distinct shelves; same expiry can share).
  8. Store isolation across storage locations and batches.
  9. Expiry evaluation and status assignment rules.
  10. Stock movement sign conventions and ledger integrity.
  11. Safe rollback and re-application.
"""
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime, date

from database.db import Database
from database.migration_stage2 import (
    apply_stage2_migration,
    is_migration_applied,
    rollback_stage2_migration,
    MIGRATION_VERSION
)
from services.shelf_service import ShelfService


class TestStage2DatabaseMigration(unittest.TestCase):
    """Test suite for Stage 2 normalized schema, data migration, and shelf rules."""

    @classmethod
    def setUpClass(cls):
        # We test against an isolated copy of data/pharmacy.db
        cls.source_db_path = os.path.abspath("data/pharmacy.db")

    def setUp(self):
        # Create a fresh temporary file copy for each test
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "pharmacy_test_copy.db")
        shutil.copyfile(self.source_db_path, self.test_db_path)
        self.db = Database(self.test_db_path)

    def tearDown(self):
        # Clean up temporary directory and database
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Migration Execution & Baseline Preservation Tests
    # -----------------------------------------------------------------------

    def test_01_migration_execution_and_preservation(self):
        """Verifies migration runs successfully on a database copy and preserves all baseline rows."""
        # Baseline counts before migration
        pre_users = self.db.fetch_one("SELECT COUNT(*) as c FROM users")["c"]
        pre_stores = self.db.fetch_one("SELECT COUNT(*) as c FROM stores")["c"]
        pre_meds = self.db.fetch_one("SELECT COUNT(*) as c FROM medicines")["c"]
        pre_sales = self.db.fetch_one("SELECT COUNT(*) as c FROM sales")["c"]
        pre_items = self.db.fetch_one("SELECT COUNT(*) as c FROM sale_items")["c"]
        pre_fmea = self.db.fetch_one("SELECT COUNT(*) as c FROM fmea_records")["c"]
        pre_sqc = self.db.fetch_one("SELECT COUNT(*) as c FROM sqc_defects")["c"]
        pre_pdca = self.db.fetch_one("SELECT COUNT(*) as c FROM pdca_items")["c"]

        self.assertEqual(pre_users, 4)
        self.assertEqual(pre_stores, 3)
        self.assertEqual(pre_meds, 23)
        self.assertEqual(pre_sales, 3)
        self.assertEqual(pre_items, 5)

        # Run migration with fixed reference date matching baseline inspection (2026-10-29)
        report = apply_stage2_migration(self.db, reference_date="2026-10-29")

        self.assertEqual(report["status"], "SUCCESS")
        self.assertEqual(report["medicines_scanned"], 23)
        self.assertEqual(report["batches_created"], 23)
        self.assertEqual(report["stock_movements_logged"], 23)
        self.assertTrue(report["reconciled"])

        # Verify all pre-existing baseline tables and row counts remain 100% untouched
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM users")["c"], pre_users)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM stores")["c"], pre_stores)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM medicines")["c"], pre_meds)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM sales")["c"], pre_sales)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM sale_items")["c"], pre_items)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM fmea_records")["c"], pre_fmea)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM sqc_defects")["c"], pre_sqc)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM pdca_items")["c"], pre_pdca)

    def test_02_idempotency_and_repeat_execution(self):
        """Verifies calling migration repeatedly is idempotent and does not create duplicates."""
        report1 = apply_stage2_migration(self.db, reference_date="2026-10-29")
        self.assertEqual(report1["status"], "SUCCESS")

        batches_after_first = self.db.fetch_one("SELECT COUNT(*) as c FROM inventory_batches")["c"]
        movements_after_first = self.db.fetch_one("SELECT COUNT(*) as c FROM stock_movements")["c"]

        # Run migration a second time
        report2 = apply_stage2_migration(self.db, reference_date="2026-10-29")
        self.assertEqual(report2["status"], "ALREADY_APPLIED")
        self.assertTrue(report2["already_applied"])

        # Counts must not increase
        batches_after_second = self.db.fetch_one("SELECT COUNT(*) as c FROM inventory_batches")["c"]
        movements_after_second = self.db.fetch_one("SELECT COUNT(*) as c FROM stock_movements")["c"]

        self.assertEqual(batches_after_first, batches_after_second)
        self.assertEqual(movements_after_first, movements_after_second)

    def test_03_quantity_reconciliation(self):
        """Verifies exact 1:1 quantity reconciliation across all 23 medicines."""
        apply_stage2_migration(self.db, reference_date="2026-10-29")
        shelf_service = ShelfService(self.db)
        reconciliation = shelf_service.reconcile_medicine_stock()

        self.assertEqual(len(reconciliation), 23)
        for item in reconciliation:
            self.assertTrue(
                item["reconciled"],
                f"Medicine {item['medicine_code']} unreconciled: legacy={item['legacy_quantity']}, batch={item['batch_quantity']}, movement={item['movement_quantity']}"
            )
            self.assertEqual(item["legacy_quantity"], item["batch_quantity"])
            self.assertEqual(item["batch_quantity"], item["movement_quantity"])

        # Total inventory stock check
        total_legacy_stock = sum(r["legacy_quantity"] for r in reconciliation)
        total_batch_stock = sum(r["batch_quantity"] for r in reconciliation)
        self.assertEqual(total_legacy_stock, 1903)
        self.assertEqual(total_batch_stock, 1903)

    def test_04_foreign_key_integrity(self):
        """Verifies PRAGMA foreign_key_check returns zero violations on migrated schema."""
        apply_stage2_migration(self.db, reference_date="2026-10-29")
        with self.db.get_connection() as conn:
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            self.assertEqual(len(violations), 0, f"Foreign key violations found: {violations}")

    # -----------------------------------------------------------------------
    # Expiry Rules & Status Tests
    # -----------------------------------------------------------------------

    def test_05_expiry_evaluation_convention(self):
        """Verifies strict calendar date comparison convention."""
        shelf_service = ShelfService(self.db)

        # Batch expiring on 2026-10-25
        exp_date = "2026-10-25"
        # On 2026-10-25, not yet expired (valid through the day)
        self.assertFalse(shelf_service.is_expired(exp_date, reference_date="2026-10-25"))
        # On 2026-10-26, it is expired
        self.assertTrue(shelf_service.is_expired(exp_date, reference_date="2026-10-26"))
        # On 2026-10-29 (current local audit date), it is expired
        self.assertTrue(shelf_service.is_expired(exp_date, reference_date="2026-10-29"))

        # Days until expiry
        self.assertEqual(shelf_service.days_until_expiry(exp_date, reference_date="2026-10-20"), 5)
        self.assertEqual(shelf_service.days_until_expiry(exp_date, reference_date="2026-10-25"), 0)
        self.assertEqual(shelf_service.days_until_expiry(exp_date, reference_date="2026-10-26"), -1)

    def test_06_migrated_batch_status_distribution(self):
        """Verifies expired batches are flagged as 'Expired' and future batches as 'Active'."""
        report = apply_stage2_migration(self.db, reference_date="2026-10-29")

        # Based on audited expiry dates relative to 2026-10-29:
        # Expired: MED1015 (2026-08-11 in STORE-LEGACY-001, 2026-08-15 in STORE-81C3C6BF),
        #          MED1016 (2026-08-11 in STORE-LEGACY-001),
        #          MED1013 (2026-10-25 in STORE-LEGACY-001),
        #          MED1014 (2026-10-25 in STORE-LEGACY-001).
        # Total expired: 5 batches.
        self.assertEqual(report["expired_batches_flagged"], 5)
        self.assertEqual(report["active_batches_created"], 18)

        # Verify in database
        expired_in_db = self.db.fetch_all("SELECT batch_number, expiry_date FROM inventory_batches WHERE status = 'Expired'")
        self.assertEqual(len(expired_in_db), 5)
        for b in expired_in_db:
            self.assertTrue(b["expiry_date"] < "2026-10-29")

        active_in_db = self.db.fetch_all("SELECT batch_number, expiry_date FROM inventory_batches WHERE status = 'Active'")
        self.assertEqual(len(active_in_db), 18)
        for b in active_in_db:
            self.assertTrue(b["expiry_date"] >= "2026-10-29")

    # -----------------------------------------------------------------------
    # Critical Shelf Allocation Rule Tests
    # -----------------------------------------------------------------------

    def test_07_critical_shelf_allocation_rule(self):
        """
        Enforces:
        - The same medicine must be stored in separate shelf locations when its batches have different expiry dates.
        - Batches of the same medicine sharing the same expiry date may share a location.
        """
        apply_stage2_migration(self.db, reference_date="2026-10-29")
        shelf_service = ShelfService(self.db)
        store_id = "STORE-LEGACY-001"
        med_id = 1  # Paracetamol 500mg

        loc_a = shelf_service.get_or_create_location(store_id, "SHELF-TEST-A", "Rack T", "Bin 1")
        loc_b = shelf_service.get_or_create_location(store_id, "SHELF-TEST-B", "Rack T", "Bin 2")

        # 1. Add Batch 1: Expiry 2027-01-15 on Shelf A
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'P101', '2027-01-15', 100, 100, 15.0, ?, 'Active')
            """,
            (store_id, med_id, loc_a)
        )

        # 2. Try to assign Batch 2 with DIFFERENT expiry (2027-06-30) to SAME Shelf A -> MUST FAIL
        ok, msg = shelf_service.validate_shelf_allocation(store_id, med_id, loc_a, "2027-06-30")
        self.assertFalse(ok)
        self.assertIn("Shelf allocation conflict", msg)

        # 3. Assign Batch 2 with different expiry (2027-06-30) to DIFFERENT Shelf B -> MUST SUCCEED
        ok, msg = shelf_service.validate_shelf_allocation(store_id, med_id, loc_b, "2027-06-30")
        self.assertTrue(ok)
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'P102', '2027-06-30', 150, 150, 15.0, ?, 'Active')
            """,
            (store_id, med_id, loc_b)
        )

        # 4. Add Batch 3 with SAME expiry (2027-06-30) to Shelf B -> MUST SUCCEED (allowed to share!)
        ok, msg = shelf_service.validate_shelf_allocation(store_id, med_id, loc_b, "2027-06-30")
        self.assertTrue(ok)
        self.assertIn("Shares shelf", msg)
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'P103', '2027-06-30', 80, 80, 15.0, ?, 'Active')
            """,
            (store_id, med_id, loc_b)
        )

        # 5. Verify batch-level quantities are preserved independently
        batches = self.db.fetch_all(
            "SELECT batch_number, current_quantity, location_id FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND batch_number IN ('P101', 'P102', 'P103') ORDER BY batch_number",
            (store_id, med_id)
        )
        self.assertEqual(len(batches), 3)
        self.assertEqual(batches[0]["batch_number"], "P101")
        self.assertEqual(batches[0]["current_quantity"], 100)
        self.assertEqual(batches[0]["location_id"], loc_a)

        self.assertEqual(batches[1]["batch_number"], "P102")
        self.assertEqual(batches[1]["current_quantity"], 150)
        self.assertEqual(batches[1]["location_id"], loc_b)

        self.assertEqual(batches[2]["batch_number"], "P103")
        self.assertEqual(batches[2]["current_quantity"], 80)
        self.assertEqual(batches[2]["location_id"], loc_b)

    def test_08_store_isolation_on_locations_and_batches(self):
        """Verifies identical shelf codes across different stores are isolated and cannot conflict."""
        apply_stage2_migration(self.db, reference_date="2026-10-29")
        shelf_service = ShelfService(self.db)

        # Shelf 'SHELF-A01' exists in both STORE-LEGACY-001 and STORE-81C3C6BF
        loc_store1 = self.db.fetch_one(
            "SELECT location_id FROM storage_locations WHERE store_id = 'STORE-LEGACY-001' AND shelf_code = 'SHELF-A01'"
        )["location_id"]
        loc_store2 = self.db.fetch_one(
            "SELECT location_id FROM storage_locations WHERE store_id = 'STORE-81C3C6BF' AND shelf_code = 'SHELF-A01'"
        )["location_id"]

        self.assertNotEqual(loc_store1, loc_store2)

        # Attempting to assign store 1 medicine to store 2 location must fail tenant validation
        ok, msg = shelf_service.validate_shelf_allocation("STORE-LEGACY-001", 1, loc_store2, "2027-01-01")
        self.assertFalse(ok)
        self.assertIn("does not exist in store 'STORE-LEGACY-001'", msg)

    # -----------------------------------------------------------------------
    # Ledger & Constraints Tests
    # -----------------------------------------------------------------------

    def test_09_stock_movement_ledger_sign_convention(self):
        """Verifies opening balance sign convention is positive (+)."""
        apply_stage2_migration(self.db, reference_date="2026-10-29")

        movements = self.db.fetch_all("SELECT movement_type, quantity_delta FROM stock_movements")
        self.assertEqual(len(movements), 23)
        for m in movements:
            self.assertEqual(m["movement_type"], "MIGRATION_OPENING")
            self.assertGreaterEqual(m["quantity_delta"], 0)

    def test_10_negative_quantity_rejection(self):
        """Verifies check constraints block negative quantities in batches."""
        apply_stage2_migration(self.db, reference_date="2026-10-29")

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """
                INSERT INTO inventory_batches (
                    store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                    current_quantity, selling_price, status
                ) VALUES ('STORE-LEGACY-001', 1, 'NEG-TEST', '2027-01-01', -5, -5, 10.0, 'Active')
                """
            )

    def test_11_rollback_recovery(self):
        """Verifies migration can be cleanly rolled back and re-applied without error."""
        apply_stage2_migration(self.db, reference_date="2026-10-29")
        self.assertTrue(is_migration_applied(self.db))

        # Rollback
        rollback_ok = rollback_stage2_migration(self.db)
        self.assertTrue(rollback_ok)
        self.assertFalse(is_migration_applied(self.db))

        # Verify normalized tables are dropped
        tbl = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_batches'")
        self.assertIsNone(tbl)

        # Verify legacy tables remain 100% intact
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM medicines")["c"], 23)
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM users")["c"], 4)

        # Re-apply migration
        report = apply_stage2_migration(self.db, reference_date="2026-10-29")
        self.assertEqual(report["status"], "SUCCESS")
        self.assertTrue(report["reconciled"])
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) as c FROM inventory_batches")["c"], 23)


if __name__ == "__main__":
    unittest.main()
