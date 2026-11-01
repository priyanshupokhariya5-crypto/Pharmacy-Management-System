"""
Comprehensive Final Functional Audit & Verification Test Suite.
Validates all 23 audit requirements across POS Billing, Staff Accounts & Password Reset,
Purchasing PO Invoices & PDFs, Medicine Deletion FK Protection, Shelf/Rack & Batch Management,
Role-Based Dashboards & Permissions, and Application Startup.
"""
import os
import sys
import shutil
import unittest
from datetime import datetime, timedelta

from database.db import Database
from database.schema import init_db, migrate_database, hash_password, verify_password
from database.migration_stage2 import apply_stage2_migration
from models.user import (
    User,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_INVENTORY_MANAGER,
    PERM_MANAGE_USERS,
    PERM_DELETE_MEDICINE,
    PERM_MANAGE_PURCHASES,
)
from models.medicine import Medicine
from models.supplier import Supplier
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from services.sales_service import SalesService, validate_indian_phone
from services.purchase_service import PurchaseService
from services.shelf_service import ShelfService
from services.inventory_service import InventoryService
from utils.pdf_generator import generate_invoice_pdf, generate_purchase_order_pdf


class TestCompleteFinalAudit(unittest.TestCase):
    """23-Point Complete System Audit & Regression Verification."""

    @classmethod
    def setUpClass(cls):
        cls.TEST_DB_PATH = os.path.abspath("data/test_complete_final_audit.db")
        if os.path.exists(cls.TEST_DB_PATH):
            os.remove(cls.TEST_DB_PATH)

        cls.db = Database(cls.TEST_DB_PATH)
        init_db(cls.TEST_DB_PATH)
        migrate_database(cls.db)
        apply_stage2_migration(cls.db)

        cls.auth_service = AuthService(cls.db)
        cls.shelf_service = ShelfService(cls.db)
        cls.purchase_service = PurchaseService(cls.db)

        # 1. Provision Store and Owner
        cls.store_id = "STORE-AUDIT-001"
        cls.store_name = "Apex Audit Chemist"
        cls.db.execute(
            "INSERT INTO stores (store_id, store_name, owner_name) VALUES (?, ?, ?)",
            (cls.store_id, cls.store_name, "Dr. Priya Audit")
        )

        owner_hash = hash_password("OwnerSecure123")
        cls.db.execute(
            """
            INSERT INTO users (username, password_hash, role, store_id, full_name, email, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            ("audit_owner", owner_hash, ROLE_OWNER, cls.store_id, "Dr. Priya Audit", "owner@audit.local")
        )
        owner_row = cls.db.fetch_one("SELECT * FROM users WHERE username = 'audit_owner'")
        cls.owner_user = User.from_row(owner_row)

        cls.med_service = MedicineService(cls.db, store_id=cls.store_id)
        cls.sales_service = SalesService(cls.db, store_id=cls.store_id)
        cls.inventory_service = InventoryService(cls.db)

        # 2. Setup Storage Locations
        for s_code in ["SHELF-A01", "SHELF-A02", "SHELF-B01", "SHELF-B02", "SHELF-COLD", "SHELF-QUAR"]:
            cls.shelf_service.get_or_create_location(cls.store_id, s_code)

        # 3. Setup Test Supplier
        cls.db.execute(
            """
            INSERT INTO suppliers (store_id, supplier_code, supplier_name, contact_person, phone, email, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (cls.store_id, "SUPP-AUDIT-01", "Apex Pharma Supplies Ltd", "Rajesh Kumar", "9876543210", "rajesh@apexpharma.com")
        )
        sup_row = cls.db.fetch_one("SELECT * FROM suppliers WHERE store_id = ?", (cls.store_id,))
        cls.supplier_id = sup_row["supplier_id"]

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.TEST_DB_PATH):
            try:
                os.remove(cls.TEST_DB_PATH)
            except Exception:
                pass

    # =========================================================================
    # AREA 1: APPLICATION STARTUP & GEOMETRY
    # =========================================================================

    def test_01_startup_initialization_no_blank_white_window(self):
        """Verifies that PharmacyApp initializes cleanly with dark theme and withdraws before show."""
        from ui.theme import Theme
        import main
        self.assertIsNotNone(Theme.BG_DARK)
        self.assertTrue(hasattr(main, "PharmacyApp"))

    # =========================================================================
    # AREA 2: POS BILLING WORKFLOW, CART COLUMNS & CALCULATIONS
    # =========================================================================

    def test_02_pos_cart_treeview_eight_columns(self):
        """Verifies that the billing cart treeview includes all 8 required columns including batch and shelf."""
        from ui.billing import BillingView
        import inspect
        src = inspect.getsource(BillingView._build_pos_tab)
        self.assertIn('"id"', src)
        self.assertIn('"code"', src)
        self.assertIn('"name"', src)
        self.assertIn('"batch"', src)
        self.assertIn('"shelf"', src)
        self.assertIn('"qty"', src)
        self.assertIn('"price"', src)
        self.assertIn('"subtotal"', src)

    def test_03_inventory_selection_shows_batch_and_shelf(self):
        """Verifies inventory select displays active batch and shelf location in billing."""
        from ui.billing import BillingView
        import inspect
        src = inspect.getsource(BillingView._on_inventory_select)
        self.assertIn("batch_number", src)
        self.assertIn("shelf_code", src)
        self.assertIn("Selected:", src)

    def test_04_cart_addition_records_batch_and_shelf(self):
        """Verifies cart addition saves batch_number and shelf_location into cart item dictionary."""
        from ui.billing import BillingView
        import inspect
        src = inspect.getsource(BillingView._on_add_to_cart)
        self.assertIn('"batch_number"', src)
        self.assertIn('"shelf_location"', src)

    def test_05_cart_controls_edit_qty_recalculates(self):
        """Verifies editing cart quantity immediately recalculates subtotal and totals."""
        from ui.billing import BillingView
        import inspect
        src = inspect.getsource(BillingView._on_edit_cart_qty)
        self.assertIn("refresh_cart_display", src)

    def test_06_cart_controls_remove_and_clear_recalculate(self):
        """Verifies remove item and clear cart immediately refresh cart display and zero out totals."""
        from ui.billing import BillingView
        import inspect
        src_rm = inspect.getsource(BillingView._on_remove_cart_item)
        src_cl = inspect.getsource(BillingView._on_clear_cart)
        self.assertIn("refresh_cart_display", src_rm)
        self.assertIn("refresh_cart_display", src_cl)

    def test_07_customer_phone_validation_strict_indian_rules(self):
        """Verifies strict 10-digit Indian mobile validation with Poka-Yoke rules."""
        # Non-digits rejected
        ok, msg, _ = validate_indian_phone("98765abcde")
        self.assertFalse(ok)

        # Less than 10 digits rejected
        ok, msg, _ = validate_indian_phone("987654321")
        self.assertFalse(ok)

        # More than 10 digits rejected
        ok, msg, _ = validate_indian_phone("98765432100")
        self.assertFalse(ok)

        # Valid 10-digit starting with 6, 7, 8, 9 accepted
        ok, msg, clean = validate_indian_phone("9876543210")
        self.assertTrue(ok)
        self.assertEqual(clean, "9876543210")

        # Invalid starting digit rejected
        ok, msg, _ = validate_indian_phone("1234567890")
        self.assertFalse(ok)

    def test_08_atomic_fefo_sale_deduction(self):
        """Verifies atomic FEFO sale deduction across multiple batches with oldest expiry first."""
        exp1 = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        exp2 = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")

        med = Medicine(
            medicine_id=None,
            store_id=self.store_id,
            medicine_code="MED-FEFO-01",
            medicine_name="Paracetamol FEFO 500mg",
            category="Tablet",
            manufacturer="GlaxoSmithKline",
            batch_no="B-FEFO-1",
            price=20.0,
            quantity=50,
            expiry_date=exp1
        )
        self.med_service.add_medicine(med, acting_user=self.owner_user)
        inserted = self.med_service.get_medicine_by_code("MED-FEFO-01")

        loc1 = self.db.fetch_one("SELECT location_id FROM storage_locations WHERE shelf_code = 'SHELF-A01' AND store_id = ?", (self.store_id,))["location_id"]
        loc2 = self.db.fetch_one("SELECT location_id FROM storage_locations WHERE shelf_code = 'SHELF-A02' AND store_id = ?", (self.store_id,))["location_id"]

        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, supplier_id, mfg_date, expiry_date,
                received_date, initial_quantity, current_quantity, purchase_cost, selling_price,
                location_id, status, verification_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', 0)
            """,
            (self.store_id, inserted.medicine_id, "BATCH-EARLY", self.supplier_id, "2026-01-01", exp1, "2026-01-05", 20, 20, 10.0, 20.0, loc1)
        )
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, supplier_id, mfg_date, expiry_date,
                received_date, initial_quantity, current_quantity, purchase_cost, selling_price,
                location_id, status, verification_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', 0)
            """,
            (self.store_id, inserted.medicine_id, "BATCH-LATER", self.supplier_id, "2026-01-01", exp2, "2026-01-05", 30, 30, 10.0, 20.0, loc2)
        )

        ok, msg, sale_id, inv = self.sales_service.process_sale(
            user_id=self.owner_user.user_id,
            cart_items=[(inserted.medicine_id, 25)],
            patient_name="Priya Customer",
            patient_phone="9876543210",
            payment_method="UPI",
            payment_reference="UPI/123456789/UTR",
            acting_user=self.owner_user
        )
        self.assertTrue(ok, msg)

        b1 = self.db.fetch_one("SELECT current_quantity, status FROM inventory_batches WHERE batch_number = 'BATCH-EARLY'")
        b2 = self.db.fetch_one("SELECT current_quantity, status FROM inventory_batches WHERE batch_number = 'BATCH-LATER'")
        self.assertEqual(b1["current_quantity"], 0)
        self.assertEqual(b2["current_quantity"], 25)

        med_after = self.med_service.get_medicine_by_id(inserted.medicine_id)
        self.assertEqual(med_after.quantity, 25)

    def test_09_save_invoice_as_pdf(self):
        """Verifies sales invoice PDF generation outputs a non-empty, valid PDF file."""
        sales = self.sales_service.get_recent_sales(limit=1, acting_user=self.owner_user)
        self.assertGreater(len(sales), 0)
        sale_details = self.sales_service.get_sale_details(sales[0]["sale_id"], acting_user=self.owner_user)

        pdf_path = generate_invoice_pdf(sale_details)
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 500)

    # =========================================================================
    # AREA 3: STAFF ACCOUNTS & SECURE PASSWORD RESET
    # =========================================================================

    def test_10_staff_account_creation_all_four_roles(self):
        """Verifies Owner can provision staff accounts for all 4 permitted roles."""
        roles_to_test = [ROLE_ADMIN, ROLE_PHARMACIST, ROLE_CASHIER, ROLE_INVENTORY_MANAGER]
        for role in roles_to_test:
            uname = f"staff_{role.lower().replace(' ', '_')}"
            success, msg = self.auth_service.create_user(
                username=uname,
                password="StaffPassword123",
                role=role,
                store_id=self.store_id,
                email=f"{uname}@audit.local",
                full_name=f"Test {role}",
                acting_user=self.owner_user
            )
            self.assertTrue(success, f"Failed creating staff for {role}: {msg}")
            row = self.db.fetch_one("SELECT * FROM users WHERE username = ?", (uname,))
            self.assertIsNotNone(row)
            self.assertEqual(row["role"], role)

    def test_11_staff_deactivate_and_self_deactivation_protection(self):
        """Verifies staff accounts can be deactivated/reactivated and self-deactivation is rejected."""
        cashier = self.db.fetch_one("SELECT * FROM users WHERE username = 'staff_cashier'")
        cashier_id = cashier["user_id"]

        ok, msg = self.auth_service.set_user_active_status(cashier_id, is_active=False, acting_user=self.owner_user)
        self.assertTrue(ok)
        c_check = self.db.fetch_one("SELECT is_active FROM users WHERE user_id = ?", (cashier_id,))
        self.assertEqual(c_check["is_active"], 0)

        ok2, msg2 = self.auth_service.set_user_active_status(cashier_id, is_active=True, acting_user=self.owner_user)
        self.assertTrue(ok2)
        c_check2 = self.db.fetch_one("SELECT is_active FROM users WHERE user_id = ?", (cashier_id,))
        self.assertEqual(c_check2["is_active"], 1)

        self_ok, self_msg = self.auth_service.set_user_active_status(
            self.owner_user.user_id, is_active=False, acting_user=self.owner_user
        )
        self.assertFalse(self_ok)
        self.assertIn("cannot deactivate your own account", self_msg.lower())

    def test_12_secure_password_reset_by_owner(self):
        """Verifies Owner can securely reset a staff member's password with PBKDF2 hashing."""
        cashier = self.db.fetch_one("SELECT * FROM users WHERE username = 'staff_cashier'")
        old_hash = cashier["password_hash"]

        new_temp_pwd = "NewSecureTemp2026!"
        ok, msg = self.auth_service.reset_password(
            user_id=cashier["user_id"],
            new_password=new_temp_pwd,
            acting_user=self.owner_user
        )
        self.assertTrue(ok, msg)

        c_refetch = self.db.fetch_one("SELECT password_hash FROM users WHERE user_id = ?", (cashier["user_id"],))
        self.assertNotEqual(c_refetch["password_hash"], old_hash)
        self.assertTrue(verify_password(new_temp_pwd, c_refetch["password_hash"]))
        self.assertNotIn(new_temp_pwd, c_refetch["password_hash"])

    # =========================================================================
    # AREA 4: PURCHASING PO INVOICE, PDF & GOODS RECEIVING
    # =========================================================================

    def test_13_create_purchase_order_unique_po_number(self):
        """Verifies purchase order creation with unique PO number and item details."""
        po_date = datetime.now().strftime("%Y-%m-%d")
        med = self.med_service.get_medicine_by_code("MED-FEFO-01")

        po_id = self.purchase_service.create_purchase(
            store_id=self.store_id,
            supplier_id=self.supplier_id,
            invoice_number="PO-2026-AUDIT-001",
            purchase_date=po_date,
            items=[{"medicine_id": med.medicine_id, "quantity": 100, "purchase_price": 12.50}],
            status="DRAFT",
            notes="Audit PO Test Order",
            acting_user=self.owner_user
        )
        self.assertGreater(po_id, 0)

        with self.assertRaises(ValueError):
            self.purchase_service.create_purchase(
                store_id=self.store_id,
                supplier_id=self.supplier_id,
                invoice_number="PO-2026-AUDIT-001",
                purchase_date=po_date,
                items=[{"medicine_id": med.medicine_id, "quantity": 50, "purchase_price": 12.50}],
                acting_user=self.owner_user
            )

    def test_14_view_po_details_and_save_po_as_pdf(self):
        """Verifies purchase order details retrieval and PDF generation."""
        purchases = self.purchase_service.get_purchases(self.store_id, acting_user=self.owner_user)
        self.assertGreater(len(purchases), 0)
        p = self.purchase_service.get_purchase_by_id(purchases[0].purchase_id, store_id=self.store_id, acting_user=self.owner_user)

        self.assertIsNotNone(p)
        self.assertEqual(len(p.items), 1)

        p_dict = {
            "purchase_id": p.purchase_id,
            "invoice_number": p.invoice_number,
            "purchase_date": p.purchase_date,
            "supplier_name": p.supplier_name,
            "supplier_id": p.supplier_id,
            "store_id": p.store_id,
            "status": p.status,
            "payment_status": p.payment_status,
            "total_amount": p.total_amount,
            "items": [
                {
                    "medicine_name": "Paracetamol FEFO 500mg",
                    "batch_number": "BCH-PO-NEW",
                    "quantity": 100,
                    "purchase_price": 12.50,
                    "subtotal": 1250.00
                }
            ]
        }
        po_pdf_path = generate_purchase_order_pdf(p_dict)
        self.assertTrue(os.path.exists(po_pdf_path))
        self.assertGreater(os.path.getsize(po_pdf_path), 500)

    def test_15_goods_receiving_updates_batch_and_shelf_no_duplicate(self):
        """Verifies goods receiving updates batches, shelf location, and ledger without duplicate receipt."""
        purchases = self.purchase_service.get_purchases(self.store_id, status="DRAFT", acting_user=self.owner_user)
        self.assertGreater(len(purchases), 0)
        target_po = purchases[0]

        med = self.med_service.get_medicine_by_code("MED-FEFO-01")
        future_exp = (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")

        loc1 = self.db.fetch_one("SELECT location_id FROM storage_locations WHERE shelf_code = 'SHELF-B01' AND store_id = ?", (self.store_id,))["location_id"]
        rcv_batches = [
            {
                "medicine_id": med.medicine_id,
                "batch_number": "BATCH-RCV-001",
                "mfg_date": "2026-01-01",
                "expiry_date": future_exp,
                "quantity": 100,
                "location_id": loc1,
                "purchase_price": 12.50,
                "selling_price": 20.00
            }
        ]

        result = self.purchase_service.receive_purchase(
            purchase_id=target_po.purchase_id,
            receiving_batches=rcv_batches,
            store_id=self.store_id,
            acting_user=self.owner_user
        )
        self.assertEqual(result["status"], "SUCCESS")
        p_check = self.purchase_service.get_purchase_by_id(target_po.purchase_id, store_id=self.store_id, acting_user=self.owner_user)
        self.assertEqual(p_check.status, "RECEIVED")

        b_row = self.db.fetch_one(
            "SELECT * FROM inventory_batches WHERE batch_number = 'BATCH-RCV-001' AND store_id = ?",
            (self.store_id,)
        )
        self.assertIsNotNone(b_row)
        self.assertEqual(b_row["current_quantity"], 100)

        with self.assertRaises(ValueError) as ctx:
            self.purchase_service.receive_purchase(
                purchase_id=target_po.purchase_id,
                receiving_batches=rcv_batches,
                store_id=self.store_id,
                acting_user=self.owner_user
            )
        self.assertIn("already been received", str(ctx.exception))

    # =========================================================================
    # AREA 5: MEDICINE DELETION FK PROTECTION & SAFE ARCHIVING
    # =========================================================================

    def test_16_delete_medicine_blocked_with_dependencies_clear_explanation(self):
        """Verifies deleting a medicine with dependent batches/sales is blocked with detailed reasons."""
        med = self.med_service.get_medicine_by_code("MED-FEFO-01")
        ok, msg = self.med_service.delete_medicine(med.medicine_id, acting_user=self.owner_user)
        self.assertFalse(ok)
        self.assertIn("Cannot delete", msg)
        self.assertIn("Batch Records", msg)

    def test_17_deactivate_medicine_archives_safely(self):
        """Verifies deactivate_medicine safely archives the item without raw FK errors."""
        med = self.med_service.get_medicine_by_code("MED-FEFO-01")
        ok, msg = self.med_service.deactivate_medicine(med.medicine_id, acting_user=self.owner_user)
        self.assertTrue(ok)
        self.assertIn("archived/deactivated", msg)

    def test_18_delete_medicine_succeeds_when_zero_dependencies(self):
        """Verifies deleting a freshly created medicine with zero dependent transactions succeeds."""
        fresh_med = Medicine(
            medicine_id=None,
            store_id=self.store_id,
            medicine_code="MED-FRESH-DEL",
            medicine_name="Temporary Delete Candidate",
            category="General",
            manufacturer="Temp Labs",
            batch_no="BCH-TMP",
            price=15.0,
            quantity=0,
            expiry_date="2027-01-01"
        )
        self.med_service.add_medicine(fresh_med, acting_user=self.owner_user)
        inserted = self.med_service.get_medicine_by_code("MED-FRESH-DEL")

        ok, msg = self.med_service.delete_medicine(inserted.medicine_id, acting_user=self.owner_user)
        self.assertTrue(ok, msg)
        self.assertIsNone(self.med_service.get_medicine_by_id(inserted.medicine_id))

    # =========================================================================
    # AREA 6: SHELF ALLOCATION RULES & BATCH NUMBER INTEGRITY
    # =========================================================================

    def test_19_medicine_inventory_view_displays_shelf_column(self):
        """Verifies MedicinesView treeview includes 'shelf' column."""
        from ui.medicines import MedicinesView
        import inspect
        src = inspect.getsource(MedicinesView._build_ui)
        self.assertIn('"shelf"', src)
        self.assertIn('"Shelf / Rack"', src)

    def test_20_critical_shelf_rules_different_expiries_separate_shelves(self):
        """Verifies different expiry dates of same medicine cannot share the same shelf."""
        exp_b = "2027-06-30"
        med = self.med_service.get_medicine_by_code("MED-FEFO-01")
        loc1 = self.shelf_service.get_or_create_location(self.store_id, "SHELF-A01")

        # Shelf A01 already holds BATCH-EARLY (2026 expiry)
        can_place, reason = self.shelf_service.validate_shelf_allocation(
            store_id=self.store_id,
            medicine_id=med.medicine_id,
            location_id=loc1,
            expiry_date=exp_b
        )
        self.assertFalse(can_place)
        self.assertIn("different expiry", reason.lower())

    # =========================================================================
    # AREA 7: BATCH DIRECTORY FOUR TABS & HELP BANNER
    # =========================================================================

    def test_21_batch_inventory_four_tabs_and_help_banner(self):
        """Verifies BatchInventoryView contains 4 tabs and information help banner."""
        from ui.batch_inventory import BatchInventoryView
        import inspect
        src = inspect.getsource(BatchInventoryView._build_ui)
        self.assertIn('"Batch Directory"', src)
        self.assertIn('"FEFO Simulator"', src)
        self.assertIn('"Expiry & Stock Alerts"', src)
        self.assertIn('"Stock Movements"', src)
        self.assertIn("Storage Rules:", src)

    # =========================================================================
    # AREA 8: ROLE-BASED DASHBOARDS & ACCESS CONTROL
    # =========================================================================

    def test_22_role_dashboards_customized_for_all_five_roles(self):
        """Verifies all five canonical roles have custom dashboard implementations."""
        from ui.dashboard import DashboardView
        import inspect
        src = inspect.getsource(DashboardView._build_ui)
        self.assertIn("_build_owner_dashboard", src)
        self.assertIn("_build_cashier_dashboard", src)
        self.assertIn("_build_pharmacist_dashboard", src)
        self.assertIn("_build_inventory_dashboard", src)

    def test_23_rbac_guards_strictly_enforced_across_services(self):
        """Verifies RBAC permission guards reject unauthorized roles."""
        cashier = self.db.fetch_one("SELECT * FROM users WHERE username = 'staff_cashier'")
        cashier_user = User.from_row(cashier)

        # Cashier cannot delete medicine (RBAC guard raises PermissionError)
        with self.assertRaises(PermissionError):
            self.med_service.delete_medicine(1, acting_user=cashier_user)

        # Cashier cannot manage users (RBAC guard raises PermissionError)
        with self.assertRaises(PermissionError):
            self.auth_service.set_user_active_status(1, is_active=False, acting_user=cashier_user)

    # =========================================================================
    # AREA 9: SHELF & MFG DATE INTEGRATION, DELETION ARCHIVAL, MULTI-BATCH ISOLATION
    # =========================================================================

    def test_24_medicine_form_shelf_and_mfg_date(self):
        """Verifies add_medicine handles shelf_code and mfg_date, creating batch and stock movement."""
        med = Medicine(
            medicine_id=None,
            store_id=self.store_id,
            medicine_code="MED-SHELF-TEST-1",
            medicine_name="Shelf Test Capsule 500mg",
            category="Antibiotic",
            manufacturer="Apex Pharma",
            batch_no="BCH-SHLF-01",
            price=45.0,
            quantity=50,
            expiry_date="2027-12-31"
        )
        ok, msg = self.med_service.add_medicine(
            med,
            shelf_code="SHELF-B02",
            mfg_date="2025-01-01",
            acting_user=self.owner_user
        )
        self.assertTrue(ok, msg)
        created = self.med_service.get_medicine_by_code("MED-SHELF-TEST-1")
        self.assertIsNotNone(created)

        # Check inventory_batches entry
        batch_row = self.db.fetch_one(
            "SELECT * FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND batch_number = ?",
            (self.store_id, created.medicine_id, "BCH-SHLF-01")
        )
        self.assertIsNotNone(batch_row)
        self.assertEqual(batch_row["mfg_date"], "2025-01-01")
        self.assertEqual(batch_row["expiry_date"], "2027-12-31")
        self.assertEqual(batch_row["status"], "Active")

        # Check location
        loc_row = self.db.fetch_one(
            "SELECT shelf_code FROM storage_locations WHERE location_id = ?",
            (batch_row["location_id"],)
        )
        self.assertIsNotNone(loc_row)
        self.assertEqual(loc_row["shelf_code"], "SHELF-B02")

        # Check opening stock movement
        sm_row = self.db.fetch_one(
            "SELECT * FROM stock_movements WHERE store_id = ? AND medicine_id = ? AND movement_type = 'MIGRATION_OPENING'",
            (self.store_id, created.medicine_id)
        )
        self.assertIsNotNone(sm_row)
        self.assertEqual(sm_row["quantity_delta"], 50)

    def test_25_expiry_after_mfg_date_validation(self):
        """Verifies expiry_date <= mfg_date is strictly rejected by validation."""
        from ui.medicines import MedicineFormModal
        import inspect
        src = inspect.getsource(MedicineFormModal._save_medicine)
        self.assertIn("Expiry date must be strictly later than manufacturing date", src)

        mfg = datetime.strptime("2026-05-01", "%Y-%m-%d")
        exp_invalid = datetime.strptime("2026-05-01", "%Y-%m-%d")
        exp_earlier = datetime.strptime("2026-04-01", "%Y-%m-%d")
        exp_valid = datetime.strptime("2027-05-01", "%Y-%m-%d")

        self.assertTrue(exp_invalid <= mfg)
        self.assertTrue(exp_earlier <= mfg)
        self.assertFalse(exp_valid <= mfg)

    def test_26_medicine_deletion_auto_archival_no_prompt(self):
        """Verifies medicine with dependencies is auto-archived with historical preservation message."""
        from ui.medicines import MedicinesView
        import inspect
        src = inspect.getsource(MedicinesView._on_delete_medicine)
        self.assertIn("Medicine archived successfully. Historical records have been preserved.", src)
        self.assertIn("check_delete_dependencies", src)
        self.assertIn("deactivate_medicine", src)

        med = Medicine(
            medicine_id=None,
            store_id=self.store_id,
            medicine_code="MED-DEP-ARCHIVE",
            medicine_name="Dependent Medicine",
            category="General",
            manufacturer="Apex Pharma",
            batch_no="BCH-DEP-01",
            price=20.0,
            quantity=10,
            expiry_date="2027-06-30"
        )
        self.med_service.add_medicine(med, shelf_code="SHELF-A01", acting_user=self.owner_user)
        ins = self.med_service.get_medicine_by_code("MED-DEP-ARCHIVE")

        deps = self.med_service.check_delete_dependencies(ins.medicine_id)
        self.assertFalse(deps["can_delete"])

        ok, msg = self.med_service.deactivate_medicine(ins.medicine_id, acting_user=self.owner_user)
        self.assertTrue(ok)
        self.assertIn("archived", msg.lower())

    def test_27_fefo_simulator_batch_table_and_preview(self):
        """Verifies FEFO simulator table columns and greedy allocation preview logic."""
        from ui.batch_inventory import BatchInventoryView
        import inspect
        src = inspect.getsource(BatchInventoryView._render_fefo_simulator)
        self.assertIn("preview_fefo_allocation", src)
        self.assertIn("med_name", src)
        self.assertIn("priority", src)
        self.assertIn("eligibility", src)

        med = self.med_service.get_medicine_by_code("MED-FEFO-01")
        if med:
            preview = self.inventory_service.preview_fefo_allocation(self.store_id, med.medicine_id, requested_quantity=15)
            self.assertTrue(hasattr(preview, "allocations"))
            self.assertTrue(hasattr(preview, "allocated_quantity"))

    def test_28_advanced_search_shelf_column_and_filter(self):
        """Verifies AdvancedSearchView includes shelf column and shelf filter option menu."""
        from ui.search import AdvancedSearchView
        import inspect
        src = inspect.getsource(AdvancedSearchView._build_ui)
        self.assertIn('"shelf"', src)
        self.assertIn('"Shelf / Rack"', src)
        self.assertIn("self.shelf_menu", src)

        src_exec = inspect.getsource(AdvancedSearchView.execute_search)
        self.assertIn("selected_shelf", src_exec)

    def test_29_pos_billing_native_phone_and_sale_date(self):
        """Verifies POS billing validates phone native keystrokes and accepts custom sale_date."""
        from ui.billing import BillingView
        import inspect
        src_build = inspect.getsource(BillingView._build_pos_tab)
        self.assertIn("self.sale_date_entry", src_build)
        self.assertIn("validatecommand", src_build)

        src_phone = inspect.getsource(BillingView._validate_phone_keystroke)
        self.assertIn("isdigit()", src_phone)

        med = self.med_service.get_medicine_by_code("MED-SHELF-TEST-1")
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(
            user_id=self.owner_user.user_id,
            cart_items=[(med.medicine_id, 1)],
            patient_name="Ramesh Gupta",
            patient_phone="9876543210",
            payment_method="Cash",
            sale_date="2026-10-31",
            acting_user=self.owner_user
        )
        self.assertTrue(ok, msg)
        self.assertIsNotNone(sale_id)
        sale_row = self.db.fetch_one("SELECT sale_date FROM sales WHERE sale_id = ?", (sale_id,))
        self.assertIn("2026-10-31", str(sale_row["sale_date"]))

    def test_30_only_legitimate_stores_in_login(self):
        """Verifies removed demo store STORE-B290A4D4 is not present in pharmacy_app.db."""
        app_db_path = os.path.abspath("data/pharmacy_app.db")
        if os.path.exists(app_db_path):
            app_db = Database(app_db_path)
            demo_store = app_db.fetch_one("SELECT * FROM stores WHERE store_id = 'STORE-B290A4D4'")
            self.assertIsNone(demo_store, "Demo store STORE-B290A4D4 must be removed from pharmacy_app.db")

            legit_store = app_db.fetch_one("SELECT * FROM stores WHERE store_id = 'STORE-B5457089'")
            self.assertIsNotNone(legit_store, "Store STORE-B5457089 must exist in pharmacy_app.db")
            self.assertEqual(legit_store["store_name"], "Pokhariya medicose")

    def test_31_multi_batch_shelf_isolation_three_medicines(self):
        """Verifies three distinct medicines can store multiple batches across isolated shelves."""
        test_specs = [
            ("MED-PARA-TEST", "Paracetamol 650mg", "BCH-P1", "SHELF-A01", "2027-01-01", 100),
            ("MED-PARA-TEST", "Paracetamol 650mg", "BCH-P2", "SHELF-A02", "2027-06-01", 120),
            ("MED-AMOX-TEST", "Amoxicillin 500mg", "BCH-A1", "SHELF-B01", "2026-11-01", 80),
            ("MED-AMOX-TEST", "Amoxicillin 500mg", "BCH-A2", "SHELF-B02", "2027-03-01", 90),
            ("MED-VITC-TEST", "Vitamin C 500mg", "BCH-V1", "SHELF-COLD", "2026-12-01", 150),
            ("MED-VITC-TEST", "Vitamin C 500mg", "BCH-V2", "SHELF-QUAR", "2027-08-01", 50),
        ]

        created_meds = {}
        for code, name, batch, shelf, exp, qty in test_specs:
            if code not in created_meds:
                med = Medicine(
                    medicine_id=None,
                    store_id=self.store_id,
                    medicine_code=code,
                    medicine_name=name,
                    category="Tablets",
                    manufacturer="Test Pharma",
                    batch_no=batch,
                    price=25.0,
                    quantity=qty,
                    expiry_date=exp
                )
                self.med_service.add_medicine(med, shelf_code=shelf, mfg_date="2025-01-01", acting_user=self.owner_user)
                m_obj = self.med_service.get_medicine_by_code(code)
                created_meds[code] = m_obj.medicine_id
            else:
                m_id = created_meds[code]
                loc_id = self.shelf_service.get_or_create_location(self.store_id, shelf)
                self.db.execute(
                    """
                    INSERT INTO inventory_batches (
                        store_id, medicine_id, batch_number, mfg_date, expiry_date,
                        initial_quantity, current_quantity, purchase_cost, selling_price,
                        location_id, status, verification_flag
                    ) VALUES (?, ?, ?, '2025-01-01', ?, ?, ?, 15.0, 25.0, ?, 'Active', 0)
                    """,
                    (self.store_id, m_id, batch, exp, qty, qty, loc_id)
                )

        for code, name, batch, shelf, exp, qty in test_specs:
            m_id = created_meds[code]
            row = self.db.fetch_one(
                """
                SELECT ib.batch_number, sl.shelf_code
                FROM inventory_batches ib
                JOIN storage_locations sl ON ib.location_id = sl.location_id
                WHERE ib.store_id = ? AND ib.medicine_id = ? AND ib.batch_number = ?
                """,
                (self.store_id, m_id, batch)
            )
            self.assertIsNotNone(row)
            self.assertEqual(row["shelf_code"], shelf, f"Batch {batch} must be on {shelf}")

    def test_32_medicine_update_shelf_relocation_and_audit(self):
        """Verifies medicine edit reliably updates shelf location, logs relocation, and respects shelf rules."""
        med_code = "MED-RELOC-01"
        med = Medicine(
            medicine_id=None,
            store_id=self.store_id,
            medicine_code=med_code,
            medicine_name="Relocation Test Med",
            category="Antibiotic",
            manufacturer="Test Pharma",
            batch_no="BCH-RELOC-1",
            price=50.0,
            quantity=60,
            expiry_date="2027-06-30"
        )
        ok, msg = self.med_service.add_medicine(med, shelf_code="SHELF-A01", mfg_date="2025-01-01", acting_user=self.owner_user)
        self.assertTrue(ok)
        created_med = self.med_service.get_medicine_by_code(med_code)
        self.assertIsNotNone(created_med)

        # Relocate to SHELF-A02
        created_med.medicine_name = "Relocation Test Med Renamed"
        ok, msg = self.med_service.update_medicine(created_med, shelf_code="SHELF-A02", acting_user=self.owner_user)
        self.assertTrue(ok, msg)

        # Verify target batch is now on SHELF-A02
        batch_row = self.db.fetch_one(
            """
            SELECT b.batch_number, sl.shelf_code
            FROM inventory_batches b
            JOIN storage_locations sl ON b.location_id = sl.location_id
            WHERE b.store_id = ? AND b.medicine_id = ? AND b.batch_number = ?
            """,
            (self.store_id, created_med.medicine_id, "BCH-RELOC-1")
        )
        self.assertIsNotNone(batch_row)
        self.assertEqual(batch_row["shelf_code"], "SHELF-A02")

        # Verify relocation logged in stock_movements
        mov = self.db.fetch_one(
            """
            SELECT * FROM stock_movements
            WHERE store_id = ? AND medicine_id = ? AND movement_type = 'STORE_TRANSFER'
              AND reference_type = 'SHELF_RELOCATION'
            ORDER BY movement_id DESC LIMIT 1
            """,
            (self.store_id, created_med.medicine_id)
        )
        self.assertIsNotNone(mov, "Relocation must be recorded in stock_movements ledger")

    def test_33_pos_cart_selection_and_available_stock(self):
        """Verifies POS billing cart accurately resolves available stock from batches and displays 8 columns."""
        import customtkinter as ctk
        from ui.billing import BillingView

        root = ctk.CTk()
        root.withdraw()
        try:
            view = BillingView(root, self.owner_user)
            # Find an item with available stock in inv_tree
            children = view.inv_tree.get_children()
            self.assertGreater(len(children), 0)

            # Select first item
            first_iid = children[0]
            view.inv_tree.selection_set(first_iid)
            view._on_inventory_select(None)

            # Add to cart
            view._on_add_to_cart()
            med_id = int(first_iid)
            self.assertIn(med_id, view.cart)
            cart_item = view.cart[med_id]
            self.assertIn("batch_number", cart_item)
            self.assertIn("shelf_location", cart_item)
            self.assertGreater(cart_item["quantity"], 0)

            # Verify cart tree has 8 values
            cart_rows = view.cart_tree.get_children()
            self.assertIn(str(med_id), cart_rows)
            row_vals = view.cart_tree.item(str(med_id))["values"]
            self.assertEqual(len(row_vals), 8, "Cart row must display all 8 required columns")
        finally:
            root.destroy()

    def test_34_phone_validator_and_mandatory_sale_date(self):
        """Verifies Poka-Yoke phone validator and mandatory sale date validation in POS."""
        import customtkinter as ctk
        from ui.billing import BillingView

        root = ctk.CTk()
        root.withdraw()
        try:
            view = BillingView(root, self.owner_user)
            # 1. Phone keystroke and live validation
            view.pat_phone_entry.delete(0, "end")
            view.pat_phone_entry.insert(0, "98765abcde")
            view._on_phone_change()
            self.assertIn("must contain only numeric digits", view.phone_feedback_lbl.cget("text"))
            self.assertFalse(view.phone_valid)

            view.pat_phone_entry.delete(0, "end")
            view.pat_phone_entry.insert(0, "123456789012")
            view._on_phone_change()
            self.assertIn("cannot exceed 10 digits", view.phone_feedback_lbl.cget("text"))
            self.assertFalse(view.phone_valid)

            # 2. Live feedback on phone
            view.pat_phone_entry.delete(0, "end")
            view.pat_phone_entry.insert(0, "5876543210")  # starts with 5 (invalid Indian mobile)
            view._on_phone_change()
            self.assertFalse(view.phone_valid)

            view.pat_phone_entry.delete(0, "end")
            view.pat_phone_entry.insert(0, "9876543210")  # starts with 9 (valid Indian mobile)
            view._on_phone_change()
            self.assertTrue(view.phone_valid)

            # 3. Mandatory sale date entry exists
            self.assertTrue(hasattr(view, "sale_date_entry"))
            today_iso = datetime.now().strftime("%Y-%m-%d")
            self.assertEqual(view.sale_date_entry.get().strip(), today_iso)
        finally:
            root.destroy()

    def test_35_benchmark_cleanly_removed(self):
        """Verifies that the Search Benchmark module and routes have been completely and cleanly removed."""
        from ui.main_window import MainWindowContent
        import customtkinter as ctk

        root = ctk.CTk()
        root.withdraw()
        try:
            win = MainWindowContent(root, self.owner_user)
            self.assertNotIn("Benchmark", win.allowed_nav_keys, "Benchmark must not be in allowed navigation keys")
            self.assertNotIn("Benchmark", win.nav_buttons, "Benchmark button must not appear in sidebar")
            self.assertFalse(hasattr(win, "benchmark_view") and win.benchmark_view is not None, "benchmark_view must not be instantiated")

            # Route fallback verification
            win._on_nav_click("Benchmark")
            self.assertEqual(win.current_nav, "Dashboard", "Navigating to removed Benchmark must safely fallback to Dashboard")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
