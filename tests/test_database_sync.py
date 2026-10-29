"""
Regression test suite for database synchronization, authentication migration,
and multi-store persistence between source development and packaged environments.
"""
import os
import tempfile
import unittest

from database.db import Database
from database.schema import init_db, hash_password
from database.sync import sync_databases, get_source_db_candidate, auto_sync_from_source_if_needed
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from services.sales_service import SalesService
from models.medicine import Medicine


class TestDatabaseSyncAndAuth(unittest.TestCase):
    """Test suite ensuring accounts and stores safely migrate and authenticate."""

    def setUp(self):
        # Create separate temporary files for source and target DBs
        self.src_fd, self.src_path = tempfile.mkstemp(suffix="_src.db")
        os.close(self.src_fd)
        self.dst_fd, self.dst_path = tempfile.mkstemp(suffix="_dst.db")
        os.close(self.dst_fd)

        # Initialize clean schemas
        self.src_db = init_db(self.src_path)
        self.dst_db = init_db(self.dst_path)

        # Seed source DB with a pre-packaging registered store and owner
        self.auth_src = AuthService(self.src_db)
        ok, msg, self.user_src = self.auth_src.register_store(
            store_name="PrePackage Meds",
            owner_name="Original Owner",
            username="orig_owner",
            email="owner@prepackage.org",
            password="SecurePassword2026!",
            confirm_password="SecurePassword2026!"
        )
        self.assertTrue(ok, f"Pre-packaging store registration failed: {msg}")

        # Add a medicine and sale in source
        self.med_service_src = MedicineService(self.src_db, store_id=self.user_src.store_id)
        med = Medicine(
            medicine_id=None,
            store_id=self.user_src.store_id,
            medicine_code="PPM-101",
            medicine_name="PrePackage Paracetamol",
            category="Analgesic",
            manufacturer="PrePackage Labs",
            batch_no="B-PPM-1",
            price=25.0,
            quantity=100,
            expiry_date="2027-12-31"
        )
        add_ok, add_msg = self.med_service_src.add_medicine(med)
        self.assertTrue(add_ok, f"Add medicine failed: {add_msg}")
        self.added_med = self.med_service_src.get_medicine_by_code("PPM-101")

        # Process a sale in source
        self.sales_service_src = SalesService(self.src_db, store_id=self.user_src.store_id)
        sale_ok, sale_msg, self.sale_id, self.inv_num = self.sales_service_src.process_sale(
            user_id=self.user_src.user_id,
            cart_items=[(self.added_med.medicine_id, 2)],
            patient_name="Original Patient"
        )
        self.assertTrue(sale_ok, f"Process sale failed: {sale_msg}")

    def tearDown(self):
        for path in [self.src_path, self.dst_path]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def test_1_account_registered_before_packaging_authenticates(self):
        """Verify that an account registered before packaging authenticates against target DB after sync."""
        summary = sync_databases(self.src_path, self.dst_path)
        self.assertGreaterEqual(summary["stores"], 1)
        self.assertGreaterEqual(summary["users"], 1)

        # Authenticate on target DB with original credentials
        auth_dst = AuthService(self.dst_db)
        user, msg = auth_dst.authenticate("orig_owner", "SecurePassword2026!")
        self.assertIsNotNone(user, f"Authentication failed: {msg}")
        self.assertEqual(user.username, "orig_owner")
        self.assertEqual(user.store_name, "PrePackage Meds")
        self.assertEqual(user.role, "Owner")

    def test_2_incorrect_password_is_rejected(self):
        """Verify that wrong passwords are properly rejected after migration."""
        sync_databases(self.src_path, self.dst_path)
        auth_dst = AuthService(self.dst_db)

        # Incorrect password
        user, msg = auth_dst.authenticate("orig_owner", "WrongPassword!")
        self.assertIsNone(user)
        self.assertEqual(msg, "Invalid username/email or password.")

        # Empty password
        user_empty, msg_empty = auth_dst.authenticate("orig_owner", "")
        self.assertIsNone(user_empty)
        self.assertEqual(msg_empty, "Password cannot be empty.")

    def test_3_newly_registered_account_can_login(self):
        """Verify that newly registered accounts on target DB work alongside synced accounts."""
        sync_databases(self.src_path, self.dst_path)
        auth_dst = AuthService(self.dst_db)

        # Register brand new account on target
        ok, msg, new_user = auth_dst.register_store(
            store_name="Brand New Store",
            owner_name="New Owner",
            username="brand_new_owner",
            email="new@owner.org",
            password="BrandNewPass2026!",
            confirm_password="BrandNewPass2026!"
        )
        self.assertTrue(ok)

        # Log in with newly registered account
        user, msg = auth_dst.authenticate("brand_new_owner", "BrandNewPass2026!")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "brand_new_owner")

        # Verify original synced account still authenticates
        orig_user, orig_msg = auth_dst.authenticate("orig_owner", "SecurePassword2026!")
        self.assertIsNotNone(orig_user)

    def test_4_store_isolation_remains_intact(self):
        """Verify that multi-store data isolation is strictly preserved after sync."""
        sync_databases(self.src_path, self.dst_path)

        # Check that legacy store cannot see PPM-101
        legacy_med_service = MedicineService(self.dst_db, store_id="STORE-LEGACY-001")
        legacy_meds = legacy_med_service.get_all_medicines()
        self.assertFalse(any(m.medicine_code == "PPM-101" for m in legacy_meds))

        # Check that synced store has PPM-101
        synced_med_service = MedicineService(self.dst_db, store_id=self.user_src.store_id)
        synced_meds = synced_med_service.get_all_medicines()
        self.assertTrue(any(m.medicine_code == "PPM-101" for m in synced_meds))
        self.assertEqual(len(synced_meds), 1)

    def test_5_medicines_and_sales_survive_migration(self):
        """Verify that medicines and sales records survive the sync with correct relationships."""
        summary = sync_databases(self.src_path, self.dst_path)
        self.assertGreaterEqual(summary["medicines"], 1)
        self.assertGreaterEqual(summary["sales"], 1)
        self.assertGreaterEqual(summary["sale_items"], 1)

        conn = self.dst_db.get_connection()
        row = conn.execute("SELECT * FROM sales WHERE invoice_number = ?", (self.inv_num,)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["patient_name"], "Original Patient")
        self.assertEqual(row["store_id"], self.user_src.store_id)

        items = conn.execute("SELECT * FROM sale_items WHERE sale_id = ?", (row["sale_id"],)).fetchall()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity"], 2)
        conn.close()

    def test_6_restart_does_not_erase_accounts(self):
        """Verify that closing and reopening the database connection preserves all records."""
        sync_databases(self.src_path, self.dst_path)

        # Simulate restart by instantiating a fresh Database object
        restarted_db = Database(self.dst_path)
        auth_restarted = AuthService(restarted_db)

        user, msg = auth_restarted.authenticate("orig_owner", "SecurePassword2026!")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "orig_owner")

    def test_7_idempotent_sync_does_not_duplicate(self):
        """Verify that running sync multiple times does not create duplicate stores or users."""
        res1 = sync_databases(self.src_path, self.dst_path)
        self.assertGreater(res1["users"], 0)

        # Second sync
        res2 = sync_databases(self.src_path, self.dst_path)
        self.assertEqual(res2["stores"], 0)
        self.assertEqual(res2["users"], 0)
        self.assertEqual(res2["medicines"], 0)
        self.assertEqual(res2["sales"], 0)


if __name__ == "__main__":
    unittest.main()
