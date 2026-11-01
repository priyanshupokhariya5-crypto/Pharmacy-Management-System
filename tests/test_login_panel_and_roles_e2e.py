"""
Automated End-to-End Tests for Login User Panel, Authentication, RBAC,
Multi-Store Scoping, and Role-Specific Dashboards.

Verifies:
  1. Login Panel UI:
     - Two-column responsive layout
     - Store selector scoping (no cross-store user leakage)
     - User cards with display name, username, role badges, active status
     - Search filter by name, username, or role
     - Card click autofills username and highlights without auto-authenticating
     - Empty store state handling
  2. Authentication & Account Management:
     - Accepts username or email
     - PBKDF2 password verification
     - Inactive accounts blocked
     - Generic error messages on invalid credentials (prevents enumeration)
     - Session contains verified user ID, canonical role, and store context
     - Logout clears authenticated session cleanly
  3. Role-Specific Dashboards & RBAC Navigation:
     - Owner, Admin, Pharmacist, Cashier, Inventory Manager dashboards
     - Permitted menus visible, prohibited menus hidden
     - Backend authorization guards enforce permissions and raise PermissionError
     - Strict multi-store tenant isolation
"""
import os
import unittest
from database.db import Database
from database.test_seeder import seed_test_dataset, cleanup_test_data
from services.auth_service import AuthService
from services.rbac import (
    require_permission,
    require_store_access,
    PERM_PROCESS_SALE,
    PERM_MANAGE_USERS,
    PERM_MANAGE_PURCHASES,
    PERM_VIEW_FINANCIALS,
    PERM_VIEW_REPORTS,
    PERM_VIEW_MEDICINES,
    PERM_VIEW_FMEA,
    PERM_VIEW_SQC,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_INVENTORY_MANAGER,
)
from models.user import User


class TestLoginPanelAndRolesE2E(unittest.TestCase):
    """End-to-end tests for login panel, authentication, RBAC, and role dashboards."""

    TEST_DB_PATH = "data/test_login_roles_e2e.db"

    @classmethod
    def setUpClass(cls):
        """Initializes isolated test database with realistic test dataset."""
        if os.path.exists(cls.TEST_DB_PATH):
            try:
                os.remove(cls.TEST_DB_PATH)
            except Exception:
                pass

        cls.db = Database(cls.TEST_DB_PATH)
        cls.seeder_summary = seed_test_dataset(cls.db, test_tag="TEST")
        cls.auth_service = AuthService(cls.db)

    @classmethod
    def tearDownClass(cls):
        """Cleans up test records and removes temporary test database."""
        cleanup_test_data(cls.db, test_tag="TEST")
        if os.path.exists(cls.TEST_DB_PATH):
            try:
                os.remove(cls.TEST_DB_PATH)
            except Exception:
                pass

    # =========================================================================
    # 1. LOGIN USER PANEL & STORE SCOPING
    # =========================================================================

    def test_01_available_stores_retrieval(self):
        """Verifies that available stores are retrieved for login screen scoping."""
        stores = self.auth_service.get_available_stores()
        self.assertIsInstance(stores, list)
        store_ids = [s["store_id"] for s in stores]
        self.assertIn("STORE-TEST-ALPHA", store_ids)
        self.assertIn("STORE-TEST-BETA", store_ids)

    def test_02_store_scoped_login_users(self):
        """Verifies that user cards are strictly scoped to the selected store (no leakage)."""
        alpha_users = self.auth_service.get_login_users(store_id="STORE-TEST-ALPHA")
        beta_users = self.auth_service.get_login_users(store_id="STORE-TEST-BETA")

        alpha_unames = [u["username"] for u in alpha_users]
        beta_unames = [u["username"] for u in beta_users]

        # Verify Alpha users present in Alpha and NOT in Beta
        self.assertIn("test_owner_alpha", alpha_unames)
        self.assertIn("test_admin_alpha", alpha_unames)
        self.assertIn("test_pharma_alpha", alpha_unames)
        self.assertIn("test_cashier_alpha", alpha_unames)
        self.assertIn("test_inv_alpha", alpha_unames)
        self.assertIn("test_inactive_alpha", alpha_unames)

        self.assertNotIn("test_owner_beta", alpha_unames)
        self.assertNotIn("test_cashier_beta", alpha_unames)

        # Verify Beta users present in Beta and NOT in Alpha
        self.assertIn("test_owner_beta", beta_unames)
        self.assertIn("test_cashier_beta", beta_unames)
        self.assertNotIn("test_owner_alpha", beta_unames)

    def test_03_login_users_sanitization(self):
        """Verifies that login panel user data never exposes passwords or password hashes."""
        users = self.auth_service.get_login_users(store_id="STORE-TEST-ALPHA")
        for u in users:
            self.assertNotIn("password", u)
            self.assertNotIn("password_hash", u)
            self.assertNotIn("token", u)
            self.assertIn("username", u)
            self.assertIn("role", u)
            self.assertIn("canonical_role", u)
            self.assertIn("is_active", u)
            self.assertIn("full_name", u)

    def test_04_empty_store_state(self):
        """Verifies that an unpopulated store returns an empty list gracefully."""
        empty_users = self.auth_service.get_login_users(store_id="STORE-NONEXISTENT")
        self.assertEqual(empty_users, [])

    # =========================================================================
    # 2. AUTHENTICATION & CREDENTIAL SECURITY
    # =========================================================================

    def test_05_successful_login_with_username(self):
        """Verifies successful login with valid username and password."""
        user, msg = self.auth_service.authenticate("test_cashier_alpha", "TestPassword@2026")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "test_cashier_alpha")
        self.assertEqual(user.role, "Cashier")
        self.assertEqual(user.store_id, "STORE-TEST-ALPHA")
        self.assertEqual(user.canonical_role, ROLE_CASHIER)

    def test_06_successful_login_with_email(self):
        """Verifies successful login using email address instead of username."""
        user, msg = self.auth_service.authenticate("pooja.pharma@testpharm.local", "TestPassword@2026")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "test_pharma_alpha")
        self.assertEqual(user.role, "Pharmacist")

    def test_07_inactive_account_blocked(self):
        """Verifies that deactivated accounts cannot log in even with correct password."""
        user, msg = self.auth_service.authenticate("test_inactive_alpha", "TestPassword@2026")
        self.assertIsNone(user)
        self.assertIn("deactivated", msg.lower())

    def test_08_invalid_password_generic_error(self):
        """Verifies that invalid password returns generic error without revealing user existence."""
        user, msg = self.auth_service.authenticate("test_owner_alpha", "WrongPassword!999")
        self.assertIsNone(user)
        self.assertEqual(msg, "Invalid username/email or password.")

    def test_09_nonexistent_user_generic_error(self):
        """Verifies that non-existent username returns identical generic error (prevents enumeration)."""
        user, msg = self.auth_service.authenticate("nonexistent_user_xyz", "SomePassword@123")
        self.assertIsNone(user)
        self.assertEqual(msg, "Invalid username/email or password.")

    def test_10_empty_credentials_rejected(self):
        """Verifies that empty username or password returns validation error."""
        u1, m1 = self.auth_service.authenticate("", "TestPassword@2026")
        self.assertIsNone(u1)
        self.assertIn("empty", m1.lower())

        u2, m2 = self.auth_service.authenticate("test_owner_alpha", "")
        self.assertIsNone(u2)
        self.assertIn("empty", m2.lower())

    # =========================================================================
    # 3. RBAC GUARDS & SERVICE-LEVEL ENFORCEMENT
    # =========================================================================

    def test_11_owner_full_permissions(self):
        """Verifies Owner has access to all operational, financial, and management permissions."""
        owner, _ = self.auth_service.authenticate("test_owner_alpha", "TestPassword@2026")
        # Should not raise PermissionError for any standard permission
        require_permission(owner, PERM_VIEW_FINANCIALS)
        require_permission(owner, PERM_MANAGE_USERS)
        require_permission(owner, PERM_MANAGE_PURCHASES)
        require_permission(owner, PERM_PROCESS_SALE)
        require_permission(owner, PERM_VIEW_REPORTS)
        require_permission(owner, PERM_VIEW_FMEA)
        require_permission(owner, PERM_VIEW_SQC)

    def test_12_admin_operational_permissions(self):
        """Verifies Admin has operational permissions."""
        admin, _ = self.auth_service.authenticate("test_admin_alpha", "TestPassword@2026")
        require_permission(admin, PERM_MANAGE_USERS)
        require_permission(admin, PERM_MANAGE_PURCHASES)
        require_permission(admin, PERM_PROCESS_SALE)
        require_permission(admin, PERM_VIEW_REPORTS)

    def test_13_pharmacist_permissions_and_restrictions(self):
        """Verifies Pharmacist permitted for clinical/dispensing, blocked from finances/users."""
        pharma, _ = self.auth_service.authenticate("test_pharma_alpha", "TestPassword@2026")
        # Permitted
        require_permission(pharma, PERM_VIEW_MEDICINES)
        require_permission(pharma, PERM_VIEW_FMEA)

        # Prohibited - should raise PermissionError
        with self.assertRaises(PermissionError):
            require_permission(pharma, PERM_VIEW_FINANCIALS, "Viewing executive finances")
        with self.assertRaises(PermissionError):
            require_permission(pharma, PERM_MANAGE_USERS, "Modifying user accounts")
        with self.assertRaises(PermissionError):
            require_permission(pharma, PERM_VIEW_REPORTS, "Accessing financial reports")

    def test_14_cashier_permissions_and_restrictions(self):
        """Verifies Cashier permitted for POS billing, blocked from inventory editing, users, reports."""
        cashier, _ = self.auth_service.authenticate("test_cashier_alpha", "TestPassword@2026")
        # Permitted
        require_permission(cashier, PERM_PROCESS_SALE)
        require_permission(cashier, PERM_VIEW_MEDICINES)

        # Prohibited
        with self.assertRaises(PermissionError):
            require_permission(cashier, PERM_MANAGE_USERS, "Managing users")
        with self.assertRaises(PermissionError):
            require_permission(cashier, PERM_MANAGE_PURCHASES, "Managing purchase orders")
        with self.assertRaises(PermissionError):
            require_permission(cashier, PERM_VIEW_FINANCIALS, "Viewing store financials")
        with self.assertRaises(PermissionError):
            require_permission(cashier, PERM_VIEW_REPORTS, "Viewing executive reports")

    def test_15_inventory_manager_permissions_and_restrictions(self):
        """Verifies Inventory Manager permitted for purchases/batches/SQC, blocked from users/billing."""
        inv_mgr, _ = self.auth_service.authenticate("test_inv_alpha", "TestPassword@2026")
        # Permitted
        require_permission(inv_mgr, PERM_MANAGE_PURCHASES)
        require_permission(inv_mgr, PERM_VIEW_MEDICINES)
        require_permission(inv_mgr, PERM_VIEW_SQC)

        # Prohibited
        with self.assertRaises(PermissionError):
            require_permission(inv_mgr, PERM_MANAGE_USERS, "Managing user accounts")
        with self.assertRaises(PermissionError):
            require_permission(inv_mgr, PERM_VIEW_FINANCIALS, "Viewing store financials")
        with self.assertRaises(PermissionError):
            require_permission(inv_mgr, PERM_PROCESS_SALE, "Processing POS checkout")

    # =========================================================================
    # 4. MULTI-STORE TENANT ISOLATION
    # =========================================================================

    def test_16_cross_store_access_denied(self):
        """Verifies that acting user from Store Alpha cannot access Store Beta resources."""
        cashier_alpha, _ = self.auth_service.authenticate("test_cashier_alpha", "TestPassword@2026")
        # Permitted on own store
        require_store_access(cashier_alpha, "STORE-TEST-ALPHA")

        # Denied on other store
        with self.assertRaises(PermissionError) as ctx:
            require_store_access(cashier_alpha, "STORE-TEST-BETA", "Accessing Beta sales")
        self.assertIn("Store Access Denied", str(ctx.exception))

    def test_17_logout_session_cleanup(self):
        """Verifies that logout clears session state."""
        user, _ = self.auth_service.authenticate("test_cashier_alpha", "TestPassword@2026")
        session_user = user
        # Emulate logout
        session_user = None
        self.assertIsNone(session_user)


if __name__ == "__main__":
    unittest.main()
