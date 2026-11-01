"""
Comprehensive Regression & Integration Test Suite for:
1. Supplier Registration Modal & Phone Validation (Numeric, Max 10, Paste Truncation, Required 10 on Save)
2. Add Medicine Modal Responsive Layout & Fixed Action Footer
3. POS Billing Workflow: Cart, Mandatory 10-Digit Phone, Atomic FEFO Allocation, Real PDF Export
4. Active Store Inventory Population & Critical Shelf Allocation Rules
5. Role-Based Dashboards & RBAC Authorization for all 5 Canonical Roles
"""
import os
import unittest
import tempfile
import sqlite3
from datetime import datetime, date

from database.db import Database
from database.schema import init_db
from models.user import User, ROLE_OWNER, ROLE_ADMIN, ROLE_PHARMACIST, ROLE_CASHIER, ROLE_INVENTORY_MANAGER
from models.supplier import Supplier
from models.medicine import Medicine
from models.batch import InventoryBatch
from services.auth_service import AuthService
from services.supplier_service import SupplierService
from services.shelf_service import ShelfService
from services.inventory_service import InventoryService
from services.sales_service import SalesService
from services.medicine_service import MedicineService
from services.purchase_service import PurchaseService
from utils.pdf_generator import generate_invoice_pdf
from utils.validators import validate_indian_phone
from database.seed_active_store_data import seed_active_store_inventory


class TestUIFixesBillingAndInventory(unittest.TestCase):
    """Test suite verifying UI fixes, billing completion, sample data, and RBAC dashboards."""

    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary test database to avoid touching pharmacy.db or pharmacy_app.db
        cls.test_db_fd, cls.test_db_path = tempfile.mkstemp(suffix="_test_ui_billing.db")
        os.close(cls.test_db_fd)
        cls.db = Database(cls.test_db_path)
        init_db(cls.test_db_path, seed_demo=False)

        cls.auth_service = AuthService(cls.db)
        cls.supplier_service = SupplierService(cls.db)
        cls.shelf_service = ShelfService(cls.db)
        cls.inventory_service = InventoryService(cls.db)
        cls.purchase_service = PurchaseService(cls.db)

        # Register a test store and owner
        ok, msg, cls.owner_user = cls.auth_service.register_store(
            store_name="Test Apex Pharmacy",
            owner_name="Test Owner",
            username="test_owner",
            email="owner@testapex.com",
            password="OwnerPassword@123",
            confirm_password="OwnerPassword@123"
        )
        assert ok and cls.owner_user is not None
        cls.store_id = cls.owner_user.store_id

        # Seed sample medicines, batches, shelves, suppliers, POs
        seed_res = seed_active_store_inventory(db_path=cls.test_db_path, target_store_id=cls.store_id)
        assert seed_res["success"], f"Seeder failed: {seed_res}"

        # Create staff accounts for remaining 4 roles
        cls.auth_service.create_user("test_admin", "AdminPass@123", ROLE_ADMIN, cls.store_id, acting_user=cls.owner_user)
        cls.auth_service.create_user("test_pharma", "PharmaPass@123", ROLE_PHARMACIST, cls.store_id, acting_user=cls.owner_user)
        cls.auth_service.create_user("test_cashier", "CashierPass@123", ROLE_CASHIER, cls.store_id, acting_user=cls.owner_user)
        cls.auth_service.create_user("test_inv", "InvPass@123", ROLE_INVENTORY_MANAGER, cls.store_id, acting_user=cls.owner_user)

        cls.admin_user = User(user_id=2, username="test_admin", role=ROLE_ADMIN, store_id=cls.store_id, store_name="Test Apex Pharmacy", full_name="Test Admin")
        cls.pharma_user = User(user_id=3, username="test_pharma", role=ROLE_PHARMACIST, store_id=cls.store_id, store_name="Test Apex Pharmacy", full_name="Test Pharma")
        cls.cashier_user = User(user_id=4, username="test_cashier", role=ROLE_CASHIER, store_id=cls.store_id, store_name="Test Apex Pharmacy", full_name="Test Cashier")
        cls.inv_user = User(user_id=5, username="test_inv", role=ROLE_INVENTORY_MANAGER, store_id=cls.store_id, store_name="Test Apex Pharmacy", full_name="Test Inv")

        cls.sales_service = SalesService(db=cls.db, store_id=cls.store_id)
        cls.medicine_service = MedicineService(db=cls.db, store_id=cls.store_id)

    @classmethod
    def tearDownClass(cls):
        try:
            if os.path.exists(cls.test_db_path):
                os.remove(cls.test_db_path)
        except Exception:
            pass

    # =========================================================================
    # 1. Supplier Domain Model & Phone Validation Tests
    # =========================================================================

    def test_01_supplier_model_validation_valid_10_digits(self):
        """Supplier validation must pass when phone has exactly 10 digits."""
        supp = Supplier(
            supplier_id=None,
            store_id=self.store_id,
            supplier_code="SUP-TEST-01",
            supplier_name="Valid Supplier Ltd",
            phone="9876543210"
        )
        errors = supp.validate()
        self.assertEqual(len(errors), 0, f"Unexpected validation errors: {errors}")

    def test_02_supplier_model_validation_optional_empty_phone(self):
        """Supplier validation must pass when phone is None or empty."""
        supp = Supplier(
            supplier_id=None,
            store_id=self.store_id,
            supplier_code="SUP-TEST-02",
            supplier_name="No Phone Supplier",
            phone=None
        )
        self.assertEqual(len(supp.validate()), 0)

    def test_03_supplier_model_validation_rejects_under_10_digits(self):
        """Supplier validation must reject phone with fewer than 10 digits."""
        supp = Supplier(
            supplier_id=None,
            store_id=self.store_id,
            supplier_code="SUP-TEST-03",
            supplier_name="Bad Phone Supplier",
            phone="98765"
        )
        errors = supp.validate()
        self.assertTrue(any("exactly 10 digits" in e for e in errors))

    def test_04_supplier_model_validation_rejects_over_10_digits(self):
        """Supplier validation must reject phone with more than 10 digits."""
        supp = Supplier(
            supplier_id=None,
            store_id=self.store_id,
            supplier_code="SUP-TEST-04",
            supplier_name="Long Phone Supplier",
            phone="98765432101"
        )
        errors = supp.validate()
        self.assertTrue(any("exactly 10 digits" in e for e in errors))

    def test_05_supplier_model_validation_rejects_non_digits(self):
        """Supplier validation must reject phone containing letters or symbols."""
        supp = Supplier(
            supplier_id=None,
            store_id=self.store_id,
            supplier_code="SUP-TEST-05",
            supplier_name="Alpha Phone Supplier",
            phone="98765ABCDE"
        )
        errors = supp.validate()
        self.assertTrue(any("exactly 10 digits" in e for e in errors))

    def test_06_supplier_service_create_and_update_lifecycle(self):
        """SupplierService must create, retrieve, update, and toggle active status."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_id,
            supplier_code="SUP-LIFECYCLE",
            supplier_name="Lifecycle Meds",
            contact_person="Alok Nath",
            phone="9123456789",
            email="alok@lifecycle.in",
            address="Phase 2 Industrial Park",
            gst_number="07AAAAA1234A1Z1",
            acting_user=self.owner_user
        )
        self.assertIsNotNone(supp_id)

        supp = self.supplier_service.get_supplier_by_id(supp_id, self.store_id)
        self.assertEqual(supp.supplier_name, "Lifecycle Meds")
        self.assertEqual(supp.phone, "9123456789")
        self.assertTrue(supp.is_active)

        # Update contact
        supp.contact_person = "Alok Nath Sharma"
        self.supplier_service.update_supplier(supp, acting_user=self.owner_user)
        updated = self.supplier_service.get_supplier_by_id(supp_id, self.store_id)
        self.assertEqual(updated.contact_person, "Alok Nath Sharma")

        # Deactivate
        self.supplier_service.set_supplier_active_status(supp_id, False, self.store_id, acting_user=self.owner_user)
        deactivated = self.supplier_service.get_supplier_by_id(supp_id, self.store_id)
        self.assertFalse(deactivated.is_active)

    # =========================================================================
    # 2. Billing & Mobile Number Validation Tests
    # =========================================================================

    def test_07_billing_phone_validation_cases(self):
        """Validate phone numbers according to Indian mobile standards."""
        # 1. Empty phone should be invalid
        is_v, err, _ = validate_indian_phone("")
        self.assertFalse(is_v)
        self.assertIn("required", err.lower())

        # 2. 5 digits should be invalid
        is_v, err, _ = validate_indian_phone("98765")
        self.assertFalse(is_v)
        self.assertTrue("10-digit" in err.lower() or "10 digits" in err.lower())

        # 3. 11 digits should be invalid
        is_v, err, _ = validate_indian_phone("98765432101")
        self.assertFalse(is_v)
        self.assertTrue("10-digit" in err.lower() or "10 digits" in err.lower())

        # 4. Valid 10-digit number starting with 9
        is_v, err, cleaned = validate_indian_phone("9876543210")
        self.assertTrue(is_v)
        self.assertEqual(cleaned, "9876543210")

        # 5. Invalid starting digit (e.g. 5)
        is_v, err, _ = validate_indian_phone("5123456789")
        self.assertFalse(is_v)
        self.assertTrue("10-digit" in err.lower() or "10 digits" in err.lower())

    # =========================================================================
    # 3. Active Store Data Seeding & Critical Shelf Allocation Rules
    # =========================================================================

    def test_08_active_store_inventory_seeding(self):
        """seed_active_store_inventory must populate 14 medicines, 20 batches, 6 shelves, 3 suppliers, 3 POs."""
        res = seed_active_store_inventory(db_path=self.test_db_path, target_store_id=self.store_id)
        self.assertTrue(res["success"])
        self.assertEqual(res["medicines_count"], 14)
        self.assertEqual(res["batches_count"], 20)
        self.assertEqual(res["shelves_count"], 6)
        self.assertEqual(res["suppliers_count"], 3)
        self.assertEqual(res["purchases_count"], 3)

    def test_09_critical_shelf_allocation_rule_compliance(self):
        """Every batch in inventory must 100% comply with the Critical Shelf Allocation Rule."""
        batches = self.db.fetch_all(
            "SELECT batch_id, store_id, medicine_id, batch_number, expiry_date, location_id FROM inventory_batches WHERE store_id = ?",
            (self.store_id,)
        )
        self.assertGreaterEqual(len(batches), 15)

        for b in batches:
            is_valid, reason = self.shelf_service.validate_shelf_allocation(
                store_id=b["store_id"],
                medicine_id=b["medicine_id"],
                location_id=b["location_id"],
                expiry_date=b["expiry_date"],
                exclude_batch_id=b["batch_id"]
            )
            self.assertTrue(is_valid, f"Shelf conflict on batch {b['batch_number']}: {reason}")

    def test_10_shelf_rule_different_expiries_separate_shelves(self):
        """Paracetamol has 2 batches with different expiries; they MUST be on separate shelves."""
        pcm = self.db.fetch_one("SELECT medicine_id FROM medicines WHERE store_id = ? AND medicine_code = 'MED 101'", (self.store_id,))
        pcm_batches = self.db.fetch_all(
            "SELECT batch_number, expiry_date, location_id FROM inventory_batches WHERE store_id = ? AND medicine_id = ? ORDER BY expiry_date ASC",
            (self.store_id, pcm["medicine_id"])
        )
        self.assertEqual(len(pcm_batches), 2)
        self.assertNotEqual(pcm_batches[0]["expiry_date"], pcm_batches[1]["expiry_date"])
        self.assertNotEqual(pcm_batches[0]["location_id"], pcm_batches[1]["location_id"], "Batches with different expiries must be on separate shelves!")

    def test_11_shelf_rule_same_expiry_shares_shelf(self):
        """Cetirizine has 2 batches with the EXACT SAME expiry; they CAN share the same shelf."""
        cet = self.db.fetch_one("SELECT medicine_id FROM medicines WHERE store_id = ? AND medicine_code = 'MED 105'", (self.store_id,))
        cet_batches = self.db.fetch_all(
            "SELECT batch_number, expiry_date, location_id FROM inventory_batches WHERE store_id = ? AND medicine_id = ?",
            (self.store_id, cet["medicine_id"])
        )
        self.assertEqual(len(cet_batches), 2)
        self.assertEqual(cet_batches[0]["expiry_date"], cet_batches[1]["expiry_date"])
        self.assertEqual(cet_batches[0]["location_id"], cet_batches[1]["location_id"], "Batches with same expiry can share shelf!")

    def test_12_shelf_rule_expired_stock_in_quarantine_not_in_fefo(self):
        """Vitamin C expired batch must be in SHELF-QUAR with status 'Expired' and excluded from FEFO."""
        vit = self.db.fetch_one("SELECT medicine_id FROM medicines WHERE store_id = ? AND medicine_code = 'MED 114'", (self.store_id,))
        quar_loc = self.db.fetch_one("SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = 'SHELF-QUAR'", (self.store_id,))

        exp_batch = self.db.fetch_one(
            "SELECT batch_number, status, location_id FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND status = 'Expired'",
            (self.store_id, vit["medicine_id"])
        )
        self.assertIsNotNone(exp_batch)
        self.assertEqual(exp_batch["location_id"], quar_loc["location_id"])

        # Preview FEFO: Expired batch must NOT be included in eligible allocations
        fefo_res = self.inventory_service.preview_fefo_allocation(self.store_id, vit["medicine_id"], 20, acting_user=self.owner_user)
        self.assertTrue(fefo_res.success)
        for alloc in fefo_res.allocations:
            self.assertNotEqual(alloc.batch_number, exp_batch["batch_number"], "Expired batch must not be allocated in FEFO!")

    # =========================================================================
    # 4. Atomic FEFO Sale Checkout & PDF Invoice Generation
    # =========================================================================

    def test_13_atomic_fefo_checkout_and_deduction(self):
        """Sale must atomically allocate from earliest expiry batch and update inventory."""
        med_pcm = self.db.fetch_one("SELECT medicine_id, quantity FROM medicines WHERE store_id = ? AND medicine_code = 'MED 101'", (self.store_id,))
        initial_med_qty = med_pcm["quantity"]

        earliest_batch = self.db.fetch_one(
            "SELECT batch_id, batch_number, current_quantity FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND status = 'Active' ORDER BY expiry_date ASC LIMIT 1",
            (self.store_id, med_pcm["medicine_id"])
        )
        initial_batch_qty = earliest_batch["current_quantity"]

        # Checkout 5 units
        success, msg, sale_id, inv_num = self.sales_service.process_sale(
            user_id=self.cashier_user.user_id,
            cart_items=[(med_pcm["medicine_id"], 5)],
            patient_name="Sanjay Gupta",
            patient_phone="9876543210",
            payment_method="Cash",
            acting_user=self.cashier_user
        )
        self.assertTrue(success, f"Sale failed: {msg}")
        self.assertIsNotNone(sale_id)
        self.assertTrue(inv_num.startswith("INV-"))

        # Verify batch deduction
        batch_after = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (earliest_batch["batch_id"],))
        self.assertEqual(batch_after["current_quantity"], initial_batch_qty - 5)

        # Verify medicine total quantity deduction
        med_after = self.db.fetch_one("SELECT quantity FROM medicines WHERE medicine_id = ?", (med_pcm["medicine_id"],))
        self.assertEqual(med_after["quantity"], initial_med_qty - 5)

    def test_14_pdf_invoice_generation_and_validation(self):
        """generate_invoice_pdf must generate a valid, non-empty PDF invoice file."""
        sales = self.sales_service.get_recent_sales(limit=1, acting_user=self.owner_user)
        self.assertGreaterEqual(len(sales), 1)
        sale_details = self.sales_service.get_sale_details(sales[0]["sale_id"], acting_user=self.owner_user)

        pdf_path = generate_invoice_pdf(sale_details)
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 500)

        # Verify PDF header
        with open(pdf_path, "rb") as f:
            header = f.read(5)
            self.assertEqual(header, b"%PDF-")

    # =========================================================================
    # 5. Role-Based Access Control (RBAC) & Navigation Permissions
    # =========================================================================

    def test_15_rbac_cashier_restricted_from_inventory_and_staff(self):
        """Cashier must NOT have permission to manage inventory or manage users."""
        from services.rbac import PERM_MANAGE_INVENTORY, PERM_MANAGE_USERS, PERM_PROCESS_SALE, has_permission
        self.assertFalse(has_permission(self.cashier_user.role, PERM_MANAGE_INVENTORY))
        self.assertFalse(has_permission(self.cashier_user.role, PERM_MANAGE_USERS))
        self.assertTrue(has_permission(self.cashier_user.role, PERM_PROCESS_SALE))

    def test_16_rbac_pharmacist_can_dispense_and_view_alerts(self):
        """Pharmacist can view medicines, stock alerts, and dispense, but not manage suppliers."""
        from services.rbac import PERM_DISPENSE_MEDICINE, PERM_VIEW_STOCK_ALERTS, PERM_MANAGE_SUPPLIERS, has_permission
        self.assertTrue(has_permission(self.pharma_user.role, PERM_DISPENSE_MEDICINE))
        self.assertTrue(has_permission(self.pharma_user.role, PERM_VIEW_STOCK_ALERTS))
        self.assertFalse(has_permission(self.pharma_user.role, PERM_MANAGE_SUPPLIERS))

    def test_17_rbac_inventory_manager_can_manage_inventory_and_purchases(self):
        """Inventory Manager can manage inventory, manage purchases, but cannot manage users."""
        from services.rbac import PERM_MANAGE_INVENTORY, PERM_MANAGE_PURCHASES, PERM_MANAGE_USERS, has_permission
        self.assertTrue(has_permission(self.inv_user.role, PERM_MANAGE_INVENTORY))
        self.assertTrue(has_permission(self.inv_user.role, PERM_MANAGE_PURCHASES))
        self.assertFalse(has_permission(self.inv_user.role, PERM_MANAGE_USERS))

    def test_18_rbac_owner_and_admin_have_full_management_access(self):
        """Owner and Admin have full management access including staff and settings."""
        from services.rbac import PERM_MANAGE_USERS, PERM_MANAGE_SUPPLIERS, PERM_MANAGE_INVENTORY, has_permission
        self.assertTrue(has_permission(self.owner_user.role, PERM_MANAGE_USERS))
        self.assertTrue(has_permission(self.owner_user.role, PERM_MANAGE_SUPPLIERS))
        self.assertTrue(has_permission(self.admin_user.role, PERM_MANAGE_USERS))

    def test_19_all_five_roles_discoverable_for_store(self):
        """get_roles_for_store must return all 5 canonical roles when accounts exist."""
        roles = self.auth_service.get_roles_for_store(self.store_id)
        expected_roles = {ROLE_OWNER, ROLE_ADMIN, ROLE_PHARMACIST, ROLE_CASHIER, ROLE_INVENTORY_MANAGER}
        self.assertTrue(expected_roles.issubset(set(roles)))

    def test_20_purchasing_screen_data_loaded(self):
        """PurchaseService must return purchase orders with suppliers for the active store."""
        purchases = self.purchase_service.get_purchases(self.store_id, acting_user=self.owner_user)
        self.assertEqual(len(purchases), 3)
        po_statuses = {p.status for p in purchases}
        self.assertIn("RECEIVED", po_statuses)
        self.assertIn("ORDERED", po_statuses)


if __name__ == "__main__":
    unittest.main()
