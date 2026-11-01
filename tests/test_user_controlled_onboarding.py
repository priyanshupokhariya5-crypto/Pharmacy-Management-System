"""
Comprehensive Test Suite for User-Controlled Multi-Store and Multi-Role Onboarding/Login.
Verifies the complete 10-requirement lifecycle:
  1. Fresh database starts completely empty (0 stores, 0 users, 0 medicines, 0 batches).
  2. Owner registers Store 1 (only Owner can be registered; store & owner created).
  3. Owner logs in using store dropdown + role dropdown + username + password.
  4. Owner creates staff accounts: Pharmacist, Cashier, Admin, and Inventory Manager.
  5. Each staff member logs in successfully with their assigned store and role.
  6. Mismatched role login attempts are strictly rejected.
  7. Mismatched store login attempts are strictly rejected.
  8. Deactivated/inactive accounts cannot log in.
  9. Store 2 is registered independently.
  10. Strict tenant data isolation confirmed between Store 1 and Store 2.
"""
import os
import unittest
import tempfile
import sqlite3

from database.db import Database
from database.schema import init_db
from models.user import User
from models.medicine import Medicine
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from services.inventory_service import InventoryService


class TestUserControlledOnboardingAndLogin(unittest.TestCase):
    """Test suite executing the 10 requirements of user-controlled onboarding."""

    def setUp(self):
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db", prefix="test_onboarding_")
        os.close(self.temp_db_fd)
        # Initialize database without demo/seeded data (clean normal onboarding)
        self.db = init_db(self.temp_db_path, seed_demo=False)
        self.auth = AuthService(self.db)

    def tearDown(self):
        # Explicitly close and clean up
        try:
            if os.path.exists(self.temp_db_path):
                os.remove(self.temp_db_path)
        except OSError:
            pass

    def test_01_fresh_database_starts_empty(self):
        """1. Verify fresh database starts empty with no pre-created stores, users, or medicines."""
        stores_cnt = self.db.fetch_one("SELECT COUNT(*) as cnt FROM stores")["cnt"]
        users_cnt = self.db.fetch_one("SELECT COUNT(*) as cnt FROM users")["cnt"]
        meds_cnt = self.db.fetch_one("SELECT COUNT(*) as cnt FROM medicines")["cnt"]
        has_batches = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_batches'")
        batches_cnt = self.db.fetch_one("SELECT COUNT(*) as cnt FROM inventory_batches")["cnt"] if has_batches else 0
        sales_cnt = self.db.fetch_one("SELECT COUNT(*) as cnt FROM sales")["cnt"]

        self.assertEqual(stores_cnt, 0, "Clean database must have 0 stores.")
        self.assertEqual(users_cnt, 0, "Clean database must have 0 users.")
        self.assertEqual(meds_cnt, 0, "Clean database must have 0 medicines.")
        self.assertEqual(batches_cnt, 0, "Clean database must have 0 inventory batches.")
        self.assertEqual(sales_cnt, 0, "Clean database must have 0 sales.")

        # Dropdown options in normal mode must be empty
        available_stores = self.auth.get_available_stores(include_test=False)
        self.assertEqual(len(available_stores), 0, "No pre-created stores in dropdown.")

    def test_02_owner_registers_store_1(self):
        """2. Verify first store registration collects required fields and assigns Owner role."""
        ok, msg, created_owner = self.auth.register_store(
            store_name="City Care Pharmacy",
            owner_name="Dr. John Doe",
            username="johndoe",
            email="john@citycare.com",
            password="SecurePassword123!",
            confirm_password="SecurePassword123!"
        )
        self.assertTrue(ok, f"Store registration failed: {msg}")
        self.assertIsNotNone(created_owner)
        self.assertEqual(created_owner.role, "Owner")
        self.assertEqual(created_owner.username, "johndoe")
        self.assertEqual(created_owner.store_name, "City Care Pharmacy")
        self.assertTrue(created_owner.store_id.startswith("STORE-"))

        # Verify in database
        store_row = self.db.fetch_one("SELECT * FROM stores WHERE store_id = ?", (created_owner.store_id,))
        self.assertIsNotNone(store_row)
        self.assertEqual(store_row["store_name"], "City Care Pharmacy")

        user_row = self.db.fetch_one("SELECT * FROM users WHERE username = 'johndoe'")
        self.assertIsNotNone(user_row)
        self.assertEqual(user_row["role"], "Owner")
        self.assertEqual(user_row["is_active"], 1)

        # Verify dropdown now shows exactly 1 store
        stores = self.auth.get_available_stores(include_test=False)
        self.assertEqual(len(stores), 1)
        self.assertEqual(stores[0]["store_name"], "City Care Pharmacy")

    def test_03_owner_logs_in_successfully(self):
        """3. Verify Owner logs in using Store ID, Role, Username, and Password."""
        # Register store
        ok, _, owner = self.auth.register_store(
            store_name="HealthPlus Pharmacy",
            owner_name="Sarah Connor",
            username="sconnor",
            email="sarah@healthplus.local",
            password="Terminator123!",
            confirm_password="Terminator123!"
        )
        self.assertTrue(ok)

        # Login as Owner
        user, msg = self.auth.authenticate_with_store_and_role(
            store_id=owner.store_id,
            role="Owner",
            username="sconnor",
            password="Terminator123!"
        )
        self.assertIsNotNone(user, f"Owner login failed: {msg}")
        self.assertEqual(user.username, "sconnor")
        self.assertEqual(user.canonical_role, "Owner")
        self.assertEqual(user.store_id, owner.store_id)

    def test_04_and_05_owner_provisions_all_staff_and_each_logs_in(self):
        """4 & 5. Owner creates Admin, Pharmacist, Cashier, Inv Manager; each logs in."""
        # 1. Register Store
        ok, _, owner = self.auth.register_store(
            store_name="Apex Care Chemist",
            owner_name="Robert Bruce",
            username="rbruce",
            email="bruce@apexcare.com",
            password="ApexOwner2026!",
            confirm_password="ApexOwner2026!"
        )
        self.assertTrue(ok)

        # 2. Owner provisions the 4 staff roles
        staff_specs = [
            ("Admin", "admin_bob", "Bob Admin", "bob@apexcare.com", "AdminPass123!"),
            ("Pharmacist", "pharma_clara", "Clara Pharmacist", "clara@apexcare.com", "PharmaPass123!"),
            ("Cashier", "cash_dan", "Dan Cashier", "dan@apexcare.com", "CashierPass123!"),
            ("Inventory Manager", "inv_evan", "Evan Inventory", "evan@apexcare.com", "InvPass123!"),
        ]

        for role, uname, fname, mail, pwd in staff_specs:
            create_ok, create_msg = self.auth.create_user(
                username=uname,
                password=pwd,
                role=role,
                store_id=owner.store_id,
                email=mail,
                full_name=fname,
                acting_user=owner
            )
            self.assertTrue(create_ok, f"Failed to create {role}: {create_msg}")

        # 3. Each staff logs in with their credentials, store, and role
        for role, uname, fname, mail, pwd in staff_specs:
            user, msg = self.auth.authenticate_with_store_and_role(
                store_id=owner.store_id,
                role=role,
                username=uname,
                password=pwd
            )
            self.assertIsNotNone(user, f"Login failed for {role} ({uname}): {msg}")
            self.assertEqual(user.username, uname)
            self.assertEqual(user.canonical_role, role)
            self.assertEqual(user.store_id, owner.store_id)

    def test_06_mismatched_roles_rejected(self):
        """6. Verify mismatched role login attempts are strictly rejected."""
        ok, _, owner = self.auth.register_store(
            store_name="Metro Meds",
            owner_name="Alice Smith",
            username="asmith",
            email="asmith@metromeds.local",
            password="Password123!",
            confirm_password="Password123!"
        )
        self.assertTrue(ok)

        # Create Cashier
        self.auth.create_user(
            username="cash_alex",
            password="AlexPass123!",
            role="Cashier",
            store_id=owner.store_id,
            acting_user=owner
        )

        # Also create a Pharmacist so role 'Pharmacist' exists in store
        self.auth.create_user(
            username="pharma_pam",
            password="PamPass123!",
            role="Pharmacist",
            store_id=owner.store_id,
            acting_user=owner
        )

        # Attempt to log in as Pharmacist using Cashier credentials
        user, msg = self.auth.authenticate_with_store_and_role(
            store_id=owner.store_id,
            role="Pharmacist",
            username="cash_alex",
            password="AlexPass123!"
        )
        self.assertIsNone(user, "Should reject login when role does not match.")
        self.assertIn("does not have the 'Pharmacist' role", msg)

        # Attempt to log in with a role that has no accounts in this store (e.g. Admin)
        user, msg = self.auth.authenticate_with_store_and_role(
            store_id=owner.store_id,
            role="Admin",
            username="cash_alex",
            password="AlexPass123!"
        )
        self.assertIsNone(user, "Should reject login when role has no accounts in store.")
        self.assertIn("No active accounts found for role 'Admin' in this store", msg)

    def test_07_mismatched_stores_rejected(self):
        """7. Verify mismatched store login attempts are strictly rejected."""
        # Register Store A
        _, _, owner_a = self.auth.register_store(
            store_name="Store Alpha",
            owner_name="Alpha Owner",
            username="alpha_owner",
            email="alpha@test.local",
            password="AlphaPassword123!",
            confirm_password="AlphaPassword123!"
        )

        # Register Store B
        _, _, owner_b = self.auth.register_store(
            store_name="Store Beta",
            owner_name="Beta Owner",
            username="beta_owner",
            email="beta@test.local",
            password="BetaPassword123!",
            confirm_password="BetaPassword123!"
        )

        # Attempt to log into Store B using Store A Owner credentials
        user, msg = self.auth.authenticate_with_store_and_role(
            store_id=owner_b.store_id,
            role="Owner",
            username="alpha_owner",
            password="AlphaPassword123!"
        )
        self.assertIsNone(user, "Cross-store login attempt must be rejected.")
        self.assertIn("not registered under store 'Store Beta'", msg)

    def test_08_inactive_accounts_rejected(self):
        """8. Verify inactive accounts are rejected with clear message."""
        ok, _, owner = self.auth.register_store(
            store_name="SafeCare Chemist",
            owner_name="Safe Owner",
            username="safe_owner",
            email="safe@care.local",
            password="SafePassword123!",
            confirm_password="SafePassword123!"
        )
        self.assertTrue(ok)

        # Create Cashier
        self.auth.create_user(
            username="temp_cashier",
            password="CashierPass123!",
            role="Cashier",
            store_id=owner.store_id,
            acting_user=owner
        )

        # Verify active login works
        user, msg = self.auth.authenticate_with_store_and_role(
            store_id=owner.store_id,
            role="Cashier",
            username="temp_cashier",
            password="CashierPass123!"
        )
        self.assertIsNotNone(user)

        # Deactivate user
        target_row = self.db.fetch_one("SELECT user_id FROM users WHERE username = 'temp_cashier'")
        status_ok, status_msg = self.auth.set_user_active_status(
            user_id=target_row["user_id"],
            is_active=False,
            acting_user=owner
        )
        self.assertTrue(status_ok)

        # Attempt login after deactivation
        user, msg = self.auth.authenticate_with_store_and_role(
            store_id=owner.store_id,
            role="Cashier",
            username="temp_cashier",
            password="CashierPass123!"
        )
        self.assertIsNone(user, "Deactivated account must be rejected.")
        self.assertTrue("deactivated" in msg.lower() or "no active accounts" in msg.lower())

    def test_09_and_10_multiple_stores_and_strict_data_isolation(self):
        """9 & 10. Independent Store 2 registration and strict cross-store data isolation."""
        # 1. Register Store 1
        _, _, owner1 = self.auth.register_store(
            store_name="Store East",
            owner_name="East Owner",
            username="owner_east",
            email="east@pharma.local",
            password="EastPassword123!",
            confirm_password="EastPassword123!"
        )

        # 2. Register Store 2 independently
        _, _, owner2 = self.auth.register_store(
            store_name="Store West",
            owner_name="West Owner",
            username="owner_west",
            email="west@pharma.local",
            password="WestPassword123!",
            confirm_password="WestPassword123!"
        )

        self.assertNotEqual(owner1.store_id, owner2.store_id)

        # 3. Create staff in Store 1
        self.auth.create_user(
            username="east_cashier",
            password="Password123!",
            role="Cashier",
            store_id=owner1.store_id,
            acting_user=owner1
        )

        # Create staff in Store 2
        self.auth.create_user(
            username="west_cashier",
            password="Password123!",
            role="Cashier",
            store_id=owner2.store_id,
            acting_user=owner2
        )

        # 4. Verify staff directory isolation
        east_staff = self.auth.get_store_users(owner1.store_id, acting_user=owner1)
        west_staff = self.auth.get_store_users(owner2.store_id, acting_user=owner2)

        east_usernames = {u.username for u in east_staff}
        west_usernames = {u.username for u in west_staff}

        self.assertIn("owner_east", east_usernames)
        self.assertIn("east_cashier", east_usernames)
        self.assertNotIn("west_cashier", east_usernames)
        self.assertNotIn("owner_west", east_usernames)

        self.assertIn("owner_west", west_usernames)
        self.assertIn("west_cashier", west_usernames)
        self.assertNotIn("east_cashier", west_usernames)
        self.assertNotIn("owner_east", west_usernames)

        # 5. Verify Medicine inventory isolation
        med_svc1 = MedicineService(self.db, store_id=owner1.store_id)
        med_svc2 = MedicineService(self.db, store_id=owner2.store_id)

        med1 = Medicine(
            medicine_id=None,
            medicine_code="MED-EAST-01",
            medicine_name="East Cold Syrup",
            category="Syrup",
            manufacturer="East Pharma",
            batch_no="B-EAST-1",
            price=50.0,
            quantity=100,
            expiry_date="2027-12-31",
            store_id=owner1.store_id
        )
        add_ok, add_msg = med_svc1.add_medicine(med1, acting_user=owner1)
        self.assertTrue(add_ok, add_msg)

        # Query medicines in Store 1 vs Store 2
        east_meds = med_svc1.get_all_medicines()
        west_meds = med_svc2.get_all_medicines()

        self.assertEqual(len(east_meds), 1)
        self.assertEqual(east_meds[0].medicine_name, "East Cold Syrup")
        self.assertEqual(len(west_meds), 0, "Store 2 must not see Store 1 medicines.")


if __name__ == "__main__":
    unittest.main()
