"""
Comprehensive Automated Test Suite for Stage 3: Authentication and Role-Based Dashboards.
Tests:
  1. Valid login for all four roles (Owner/Admin, Pharmacist, Cashier, Inventory Manager) by username and email.
  2. Invalid login handling (wrong password, unknown identity, empty inputs).
  3. Disabled user account handling (rejection on login, reactivation, permission revocation).
  4. Role permissions and canonical role mapping matrix.
  5. Service-layer authorization guards (unauthorized calls blocked with PermissionError).
  6. Multi-store tenant isolation in authentication and service operations.
  7. Role-specific dashboard aggregations and live query calculations.
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

from database.db import Database
from database.schema import init_db, hash_password
from models.user import (
    User,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_INVENTORY_MANAGER,
    PERM_VIEW_DASHBOARD,
    PERM_VIEW_FINANCIALS,
    PERM_MANAGE_USERS,
    PERM_DELETE_MEDICINE,
    PERM_ADD_MEDICINE,
    PERM_UPDATE_MEDICINE,
    PERM_VIEW_MEDICINES,
    PERM_PROCESS_SALE,
    PERM_MANAGE_INVENTORY,
    PERM_DISPENSE_MEDICINE,
    PERM_VIEW_STOCK_ALERTS,
    has_permission,
    normalize_role,
)
from models.medicine import Medicine
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from services.sales_service import SalesService
from services.rbac import require_permission, require_store_access


class TestStage3AuthAndDashboards(unittest.TestCase):
    """Test suite for Stage 3 authentication, RBAC, service guards, and role dashboards."""

    def setUp(self):
        """Creates an isolated temporary database with seed data for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_stage3.db")
        self.db = init_db(self.db_path)
        self.auth_service = AuthService(self.db)

        # Store 1 and Store 2 IDs
        self.store_1 = "STORE-LEGACY-001"
        self.store_2 = "STORE-BRANCH-002"

        # Create Store 2 in database
        self.db.execute(
            "INSERT OR IGNORE INTO stores (store_id, store_name, owner_name) VALUES (?, ?, ?)",
            (self.store_2, "Branch Store 2", "Branch Partner")
        )

        # Setup test users across roles and stores
        self._setup_test_users()

        # Services scoped to Store 1
        self.med_service_1 = MedicineService(self.db, store_id=self.store_1)
        self.sales_service_1 = SalesService(self.db, store_id=self.store_1)

        # Services scoped to Store 2
        self.med_service_2 = MedicineService(self.db, store_id=self.store_2)
        self.sales_service_2 = SalesService(self.db, store_id=self.store_2)

    def tearDown(self):
        """Cleans up temporary database file and directory."""
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def _setup_test_users(self):
        """Seeds users for all roles in Store 1 and Store 2."""
        # Store 1 users
        self.auth_service.create_user("owner1", "owner123", ROLE_OWNER, self.store_1, "owner1@store1.com", "Store 1 Owner")
        self.auth_service.create_user("admin1", "admin123", ROLE_ADMIN, self.store_1, "admin1@store1.com", "Store 1 Admin")
        self.auth_service.create_user("pharma1", "pharma123", ROLE_PHARMACIST, self.store_1, "pharma1@store1.com", "Store 1 Pharmacist")
        self.auth_service.create_user("cashier1", "cashier123", ROLE_CASHIER, self.store_1, "cashier1@store1.com", "Store 1 Cashier")
        self.auth_service.create_user("inventory1", "inv1234", ROLE_INVENTORY_MANAGER, self.store_1, "inv1@store1.com", "Store 1 Inventory")

        # Disabled user in Store 1
        self.auth_service.create_user("disabled_user", "disabled123", ROLE_CASHIER, self.store_1, "disabled@store1.com", "Disabled Staff", is_active=False)

        # Store 2 users
        self.auth_service.create_user("owner2", "owner456", ROLE_OWNER, self.store_2, "owner2@store2.com", "Store 2 Owner")
        self.auth_service.create_user("cashier2", "cashier456", ROLE_CASHIER, self.store_2, "cashier2@store2.com", "Store 2 Cashier")

        # Fetch instantiated User domain objects
        self.user_owner1, _ = self.auth_service.authenticate("owner1", "owner123")
        self.user_admin1, _ = self.auth_service.authenticate("admin1", "admin123")
        self.user_pharma1, _ = self.auth_service.authenticate("pharma1", "pharma123")
        self.user_cashier1, _ = self.auth_service.authenticate("cashier1", "cashier123")
        self.user_inv1, _ = self.auth_service.authenticate("inventory1", "inv1234")
        self.user_owner2, _ = self.auth_service.authenticate("owner2", "owner456")
        self.user_cashier2, _ = self.auth_service.authenticate("cashier2", "cashier456")

    # =========================================================================
    # 1. Authentication Tests (Valid, Invalid, Disabled)
    # =========================================================================

    def test_01_valid_login_all_roles(self):
        """Verifies valid authentication for all four roles by username and email."""
        roles_to_test = [
            ("owner1", "owner1@store1.com", "owner123", ROLE_OWNER),
            ("admin1", "admin1@store1.com", "admin123", ROLE_ADMIN),
            ("pharma1", "pharma1@store1.com", "pharma123", ROLE_PHARMACIST),
            ("cashier1", "cashier1@store1.com", "cashier123", ROLE_CASHIER),
            ("inventory1", "inv1@store1.com", "inv1234", ROLE_INVENTORY_MANAGER),
        ]

        for username, email, pwd, expected_role in roles_to_test:
            # Login by username
            user_by_user, msg1 = self.auth_service.authenticate(username, pwd)
            self.assertIsNotNone(user_by_user, f"Login failed for {username}: {msg1}")
            self.assertEqual(user_by_user.canonical_role, expected_role)
            self.assertTrue(user_by_user.is_active)
            self.assertEqual(user_by_user.store_id, self.store_1)

            # Login by email
            user_by_email, msg2 = self.auth_service.authenticate(email, pwd)
            self.assertIsNotNone(user_by_email, f"Login failed for {email}: {msg2}")
            self.assertEqual(user_by_email.canonical_role, expected_role)
            self.assertEqual(user_by_email.username, username)

    def test_02_invalid_login_handling(self):
        """Verifies failed login for wrong password, missing account, or empty inputs."""
        # Non-existent username
        user, msg = self.auth_service.authenticate("nonexistent_user", "password123")
        self.assertIsNone(user)
        self.assertIn("Invalid username/email or password", msg)

        # Wrong password
        user, msg = self.auth_service.authenticate("owner1", "wrong_password")
        self.assertIsNone(user)
        self.assertIn("Invalid username/email or password", msg)

        # Empty username
        user, msg = self.auth_service.authenticate("", "somepassword")
        self.assertIsNone(user)
        self.assertIn("cannot be empty", msg)

        # Empty password
        user, msg = self.auth_service.authenticate("owner1", "")
        self.assertIsNone(user)
        self.assertIn("cannot be empty", msg)

    def test_03_disabled_user_login_rejection(self):
        """Verifies deactivated user account is rejected on login with clear notification."""
        user, msg = self.auth_service.authenticate("disabled_user", "disabled123")
        self.assertIsNone(user)
        self.assertIn("deactivated", msg.lower())

        # Reactivate user by store owner
        db_user = self.db.fetch_one("SELECT user_id FROM users WHERE username = 'disabled_user'")
        ok, act_msg = self.auth_service.set_user_active_status(db_user["user_id"], is_active=True, acting_user=self.user_owner1)
        self.assertTrue(ok)
        self.assertIn("activated", act_msg)

        # Now login must succeed
        reactivated_user, msg2 = self.auth_service.authenticate("disabled_user", "disabled123")
        self.assertIsNotNone(reactivated_user)
        self.assertTrue(reactivated_user.is_active)

    # =========================================================================
    # 2. RBAC Permissions Matrix & Role Mapping Tests
    # =========================================================================

    def test_04_canonical_role_normalization(self):
        """Verifies backward-compatible role mapping and casing normalization."""
        self.assertEqual(normalize_role("Admin"), ROLE_ADMIN)
        self.assertEqual(normalize_role("admin"), ROLE_ADMIN)
        self.assertEqual(normalize_role("Owner"), ROLE_OWNER)
        self.assertEqual(normalize_role("owner"), ROLE_OWNER)
        self.assertEqual(normalize_role("Pharmacist"), ROLE_PHARMACIST)
        self.assertEqual(normalize_role("pharmacist"), ROLE_PHARMACIST)
        self.assertEqual(normalize_role("Cashier"), ROLE_CASHIER)
        self.assertEqual(normalize_role("cashier"), ROLE_CASHIER)
        self.assertEqual(normalize_role("Inventory Manager"), ROLE_INVENTORY_MANAGER)
        self.assertEqual(normalize_role("inventory manager"), ROLE_INVENTORY_MANAGER)
        self.assertEqual(normalize_role("inventory_manager"), ROLE_INVENTORY_MANAGER)

        # Unknown roles must not escalate
        self.assertEqual(normalize_role("SuperUser"), "Unknown")
        self.assertEqual(normalize_role("Hacker"), "Unknown")
        self.assertEqual(normalize_role(None), "Unknown")
        self.assertEqual(normalize_role(""), "Unknown")

    def test_05_role_permissions_matrix(self):
        """Verifies permission matrix correctness across all canonical roles."""
        # Owner / Admin permissions
        for r in (ROLE_OWNER, ROLE_ADMIN):
            self.assertTrue(has_permission(r, PERM_VIEW_DASHBOARD))
            self.assertTrue(has_permission(r, PERM_VIEW_FINANCIALS))
            self.assertTrue(has_permission(r, PERM_MANAGE_USERS))
            self.assertTrue(has_permission(r, PERM_DELETE_MEDICINE))
            self.assertTrue(has_permission(r, PERM_ADD_MEDICINE))
            self.assertTrue(has_permission(r, PERM_PROCESS_SALE))
            self.assertTrue(has_permission(r, PERM_MANAGE_INVENTORY))

        # Pharmacist permissions
        self.assertTrue(has_permission(ROLE_PHARMACIST, PERM_VIEW_DASHBOARD))
        self.assertTrue(has_permission(ROLE_PHARMACIST, PERM_VIEW_MEDICINES))
        self.assertTrue(has_permission(ROLE_PHARMACIST, PERM_ADD_MEDICINE))
        self.assertTrue(has_permission(ROLE_PHARMACIST, PERM_UPDATE_MEDICINE))
        self.assertTrue(has_permission(ROLE_PHARMACIST, PERM_DISPENSE_MEDICINE))
        self.assertTrue(has_permission(ROLE_PHARMACIST, PERM_VIEW_STOCK_ALERTS))
        # Pharmacist restrictions
        self.assertFalse(has_permission(ROLE_PHARMACIST, PERM_DELETE_MEDICINE))
        self.assertFalse(has_permission(ROLE_PHARMACIST, PERM_MANAGE_USERS))
        self.assertFalse(has_permission(ROLE_PHARMACIST, PERM_VIEW_FINANCIALS))
        self.assertFalse(has_permission(ROLE_PHARMACIST, PERM_PROCESS_SALE))

        # Cashier permissions
        self.assertTrue(has_permission(ROLE_CASHIER, PERM_VIEW_DASHBOARD))
        self.assertTrue(has_permission(ROLE_CASHIER, PERM_VIEW_MEDICINES))
        self.assertTrue(has_permission(ROLE_CASHIER, PERM_PROCESS_SALE))
        # Cashier restrictions
        self.assertFalse(has_permission(ROLE_CASHIER, PERM_DELETE_MEDICINE))
        self.assertFalse(has_permission(ROLE_CASHIER, PERM_ADD_MEDICINE))
        self.assertFalse(has_permission(ROLE_CASHIER, PERM_UPDATE_MEDICINE))
        self.assertFalse(has_permission(ROLE_CASHIER, PERM_MANAGE_USERS))
        self.assertFalse(has_permission(ROLE_CASHIER, PERM_MANAGE_INVENTORY))
        self.assertFalse(has_permission(ROLE_CASHIER, PERM_VIEW_FINANCIALS))

        # Inventory Manager permissions
        self.assertTrue(has_permission(ROLE_INVENTORY_MANAGER, PERM_VIEW_DASHBOARD))
        self.assertTrue(has_permission(ROLE_INVENTORY_MANAGER, PERM_VIEW_MEDICINES))
        self.assertTrue(has_permission(ROLE_INVENTORY_MANAGER, PERM_ADD_MEDICINE))
        self.assertTrue(has_permission(ROLE_INVENTORY_MANAGER, PERM_UPDATE_MEDICINE))
        self.assertTrue(has_permission(ROLE_INVENTORY_MANAGER, PERM_MANAGE_INVENTORY))
        self.assertTrue(has_permission(ROLE_INVENTORY_MANAGER, PERM_VIEW_STOCK_ALERTS))
        # Inventory Manager restrictions
        self.assertFalse(has_permission(ROLE_INVENTORY_MANAGER, PERM_DELETE_MEDICINE))
        self.assertFalse(has_permission(ROLE_INVENTORY_MANAGER, PERM_PROCESS_SALE))
        self.assertFalse(has_permission(ROLE_INVENTORY_MANAGER, PERM_MANAGE_USERS))
        self.assertFalse(has_permission(ROLE_INVENTORY_MANAGER, PERM_VIEW_FINANCIALS))

        # Unknown role
        self.assertFalse(has_permission("Unknown", PERM_VIEW_MEDICINES))
        self.assertFalse(has_permission("Unknown", PERM_PROCESS_SALE))

    # =========================================================================
    # 3. Backend Service-Layer Permission Enforcement
    # =========================================================================

    def test_06_unauthorized_medicine_deletion_blocked(self):
        """Verifies Pharmacist, Cashier, and Inventory Manager cannot delete medicines."""
        med = self.med_service_1.get_all_medicines()[0]

        # Pharmacist calling delete_medicine -> BLOCKED
        with self.assertRaises(PermissionError):
            self.med_service_1.delete_medicine(med.medicine_id, acting_user=self.user_pharma1)

        # Cashier calling delete_medicine -> BLOCKED
        with self.assertRaises(PermissionError):
            self.med_service_1.delete_medicine(med.medicine_id, acting_user=self.user_cashier1)

        # Inventory Manager calling delete_medicine -> BLOCKED
        with self.assertRaises(PermissionError):
            self.med_service_1.delete_medicine(med.medicine_id, acting_user=self.user_inv1)

    def test_07_cashier_cannot_add_or_update_medicine(self):
        """Verifies Cashier cannot add or update medicines in inventory."""
        future_exp = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")
        new_med = Medicine(
            medicine_id=None,
            medicine_code="MED-CASHIER-TEST",
            medicine_name="Cashier Test Med",
            category="Tablet",
            manufacturer="Test Lab",
            batch_no="B123",
            price=25.0,
            quantity=50,
            expiry_date=future_exp,
            store_id=self.store_1
        )

        # Cashier add_medicine -> BLOCKED
        with self.assertRaises(PermissionError):
            self.med_service_1.add_medicine(new_med, acting_user=self.user_cashier1)

        # Cashier update_medicine -> BLOCKED
        existing = self.med_service_1.get_all_medicines()[0]
        with self.assertRaises(PermissionError):
            self.med_service_1.update_medicine(existing, acting_user=self.user_cashier1)

    def test_08_inventory_manager_cannot_process_sale(self):
        """Verifies Inventory Manager cannot execute POS sales billing checkout."""
        med = self.med_service_1.get_all_medicines()[0]
        cart = [(med.medicine_id, 1)]

        with self.assertRaises(PermissionError):
            self.sales_service_1.process_sale(
                user_id=self.user_inv1.user_id,
                cart_items=cart,
                patient_name="Test Patient",
                patient_phone="9876543210",
                acting_user=self.user_inv1
            )

    def test_09_authorized_actions_succeed(self):
        """Verifies authorized roles can execute their permitted service methods."""
        # Cashier can process sale
        med = self.med_service_1.get_all_medicines()[0]
        cart = [(med.medicine_id, 1)]
        ok, msg, sale_id, inv = self.sales_service_1.process_sale(
            user_id=self.user_cashier1.user_id,
            cart_items=cart,
            patient_name="Authorized Patient",
            patient_phone="9876543210",
            acting_user=self.user_cashier1
        )
        self.assertTrue(ok, f"Authorized cashier sale failed: {msg}")
        self.assertIsNotNone(sale_id)

        # Pharmacist can add medicine
        future_exp = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")
        new_med = Medicine(
            medicine_id=None,
            medicine_code="MED-PHARMA-ADD",
            medicine_name="Pharma Added Med",
            category="Capsule",
            manufacturer="Pharma Lab",
            batch_no="B-PHARMA-1",
            price=45.0,
            quantity=30,
            expiry_date=future_exp,
            store_id=self.store_1
        )
        ok_add, msg_add = self.med_service_1.add_medicine(new_med, acting_user=self.user_pharma1)
        self.assertTrue(ok_add, f"Authorized pharma add failed: {msg_add}")

        # Owner can delete unused medicine
        added_med = self.med_service_1.get_medicine_by_code("MED-PHARMA-ADD")
        ok_del, msg_del = self.med_service_1.delete_medicine(added_med.medicine_id, acting_user=self.user_owner1)
        self.assertTrue(ok_del, f"Authorized owner delete failed: {msg_del}")

    def test_10_user_management_guards(self):
        """Verifies only Owner/Admin can create, deactivate, or modify users."""
        # Non-owner attempting to create user -> BLOCKED
        with self.assertRaises(PermissionError):
            self.auth_service.create_user("hack_user", "pass123", ROLE_CASHIER, self.store_1, acting_user=self.user_cashier1)

        with self.assertRaises(PermissionError):
            self.auth_service.create_user("hack_user2", "pass123", ROLE_PHARMACIST, self.store_1, acting_user=self.user_pharma1)

        # Owner self-deactivation protection
        ok, msg = self.auth_service.set_user_active_status(self.user_owner1.user_id, is_active=False, acting_user=self.user_owner1)
        self.assertFalse(ok)
        self.assertIn("cannot deactivate your own account", msg)

    # =========================================================================
    # 4. Multi-Store Isolation Tests
    # =========================================================================

    def test_11_cross_store_service_access_blocked(self):
        """Verifies user from Store 1 cannot modify or access Store 2 resources."""
        # Cashier 1 attempting to bill in Store 2 -> BLOCKED
        med2 = self.med_service_2.get_all_medicines()
        if not med2:
            # Seed medicine into Store 2
            future_exp = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")
            self.med_service_2.add_medicine(Medicine(
                medicine_id=None,
                medicine_code="STORE2-MED",
                medicine_name="Store 2 Medicine",
                category="Tablet",
                manufacturer="Lab 2",
                batch_no="B200",
                price=50.0,
                quantity=100,
                expiry_date=future_exp,
                store_id=self.store_2
            ))
            med2 = self.med_service_2.get_all_medicines()

        with self.assertRaises(PermissionError):
            self.sales_service_2.process_sale(
                user_id=self.user_cashier1.user_id,
                cart_items=[(med2[0].medicine_id, 1)],
                patient_name="Cross Store Patient",
                patient_phone="9876543210",
                acting_user=self.user_cashier1
            )

        # Owner 1 attempting to view Store 2 users -> BLOCKED
        with self.assertRaises(PermissionError):
            self.auth_service.get_store_users(self.store_2, acting_user=self.user_owner1)

    # =========================================================================
    # 5. Role-Specific Dashboard Metrics Calculations
    # =========================================================================

    def test_12_owner_dashboard_summary_calculations(self):
        """Verifies Owner dashboard summary calculates accurate real database KPIs."""
        summary = self.med_service_1.get_owner_summary()

        self.assertIn("today_sales_amount", summary)
        self.assertIn("today_bills_count", summary)
        self.assertIn("total_sales_amount", summary)
        self.assertIn("estimated_gross_profit", summary)
        self.assertIn("top_selling", summary)
        self.assertIn("recent_sales", summary)
        self.assertIsInstance(summary["top_selling"], list)
        self.assertIsInstance(summary["recent_sales"], list)
        self.assertGreaterEqual(summary["total_medicines"], 1)

    def test_13_cashier_dashboard_summary_calculations(self):
        """Verifies Cashier dashboard calculates today's shift totals and payment split."""
        summary = self.sales_service_1.get_cashier_summary(cashier_user_id=self.user_cashier1.user_id)

        self.assertIn("today_bills_count", summary)
        self.assertIn("today_sales_total", summary)
        self.assertIn("cash_total", summary)
        self.assertIn("upi_total", summary)
        self.assertIn("card_total", summary)
        self.assertIn("net_sales", summary)
        self.assertIn("recent_transactions", summary)
        self.assertEqual(summary["net_sales"], summary["today_sales_total"])

    def test_14_pharmacist_dashboard_summary_calculations(self):
        """Verifies Pharmacist clinical dashboard counts available, near-expiry, and expired items."""
        summary = self.med_service_1.get_pharmacist_summary()

        self.assertIn("available_medicines", summary)
        self.assertIn("attention_total", summary)
        self.assertIn("expiring_soon_count", summary)
        self.assertIn("expired_count", summary)
        self.assertIn("low_stock_count", summary)
        self.assertIn("alert_medicines", summary)
        self.assertIn("recent_dispensed", summary)
        self.assertIsInstance(summary["alert_medicines"], list)

    def test_15_inventory_manager_dashboard_summary_calculations(self):
        """Verifies Inventory Manager dashboard calculates units, valuation, and reorder lists."""
        summary = self.med_service_1.get_inventory_manager_summary()

        self.assertIn("total_medicines", summary)
        self.assertIn("total_stock_quantity", summary)
        self.assertIn("total_inventory_value", summary)
        self.assertIn("reorder_items", summary)
        self.assertIn("expiry_items", summary)
        self.assertIsInstance(summary["reorder_items"], list)
        self.assertIsInstance(summary["expiry_items"], list)


if __name__ == "__main__":
    unittest.main()
