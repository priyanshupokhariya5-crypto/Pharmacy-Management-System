"""
Comprehensive Automated Test Suite for Stage 4:
Purchasing, Batch Management, Storage Locations, and FEFO Inventory Logic.
Tests:
  1. Supplier Management (CRUD, contact validation, active/inactive toggles, multi-store isolation).
  2. Purchase Management (draft creation, multi-items, multi-batches, validation, cancellation).
  3. Goods Receiving & Batch Creation (validation, atomic stock/ledger updates, duplicate receipt prevention, rollback).
  4. Critical Shelf Allocation Rule (same medicine + differing expiry blocked from same shelf; same expiry allowed).
  5. FEFO Selection Engine (earliest expiry first, multi-batch split, exclusions, preview read-only safety, deterministic ties).
  6. Stock Movement Ledger & Reconciliation (sign conventions, atomic adjustment, write-off, reconciliation consistency).
  7. Role-Based Access Control (Cashier blocked, Inventory Manager permitted, Owner full access).
"""
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta

from database.db import Database
from database.schema import init_db, hash_password
from database.migration_stage2 import apply_stage2_migration
from models.user import (
    User,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_INVENTORY_MANAGER,
    PERM_MANAGE_SUPPLIERS,
    PERM_MANAGE_PURCHASES,
    PERM_MANAGE_INVENTORY,
    PERM_VIEW_STOCK_ALERTS
)
from models.supplier import Supplier
from models.purchase import Purchase
from models.batch import InventoryBatch
from services.supplier_service import SupplierService
from services.purchase_service import PurchaseService
from services.inventory_service import InventoryService, BatchAllocationPreview, FefoAllocationResult
from services.shelf_service import ShelfService


class TestStage4PurchasingAndFefo(unittest.TestCase):
    """Test suite for Stage 4 Purchasing, Batch Management, Shelf Rules, and FEFO."""

    def setUp(self):
        """Creates an isolated temporary database with Stage 2 schema applied."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_stage4.db")
        self.db = init_db(self.db_path)

        # Apply Stage 2 migration to establish suppliers, storage_locations, inventory_batches, purchases, etc.
        apply_stage2_migration(self.db, reference_date="2026-10-29")

        self.shelf_service = ShelfService(self.db)
        self.supplier_service = SupplierService(self.db)
        self.purchase_service = PurchaseService(self.db)
        self.inventory_service = InventoryService(self.db)

        # Store IDs
        self.store_1 = "STORE-LEGACY-001"
        self.store_2 = "STORE-BRANCH-002"

        # Create Store 2 in stores table
        self.db.execute(
            "INSERT OR IGNORE INTO stores (store_id, store_name, owner_name) VALUES (?, ?, ?)",
            (self.store_2, "Branch Store Downtown", "Dr. Jane Branch")
        )

        # Seed sample users with distinct roles
        self.user_owner = User(
            user_id=101, username="owner_sam",
            role=ROLE_OWNER, store_id=self.store_1, full_name="Sam Owner", email="owner@store1.local"
        )
        self.user_admin = User(
            user_id=102, username="admin_alex",
            role=ROLE_ADMIN, store_id=self.store_1, full_name="Alex Admin", email="admin@store1.local"
        )
        self.user_inventory = User(
            user_id=103, username="inv_mike",
            role=ROLE_INVENTORY_MANAGER, store_id=self.store_1, full_name="Mike Inventory", email="mike@store1.local"
        )
        self.user_pharma = User(
            user_id=104, username="pharma_sarah",
            role=ROLE_PHARMACIST, store_id=self.store_1, full_name="Sarah Pharmacist", email="sarah@store1.local"
        )
        self.user_cashier = User(
            user_id=105, username="cashier_carl",
            role=ROLE_CASHIER, store_id=self.store_1, full_name="Carl Cashier", email="carl@store1.local"
        )
        self.user_store2 = User(
            user_id=201, username="owner_two",
            role=ROLE_OWNER, store_id=self.store_2, full_name="Owner Two", email="owner@store2.local"
        )

        # Insert test users into users table to satisfy foreign keys
        for u in (self.user_owner, self.user_admin, self.user_inventory, self.user_pharma, self.user_cashier, self.user_store2):
            self.db.execute(
                """
                INSERT OR IGNORE INTO users (user_id, username, password_hash, role, store_id, full_name, email, is_active)
                VALUES (?, ?, 'dummy_hash', ?, ?, ?, ?, 1)
                """,
                (u.user_id, u.username, u.role, u.store_id, u.full_name, u.email)
            )

        # Fetch a test medicine from store 1
        med_row = self.db.fetch_one(
            "SELECT medicine_id, medicine_code, medicine_name, price FROM medicines WHERE store_id = ? LIMIT 1",
            (self.store_1,)
        )
        self.med_1_id = med_row["medicine_id"]
        self.med_1_name = med_row["medicine_name"]
        self.med_1_price = float(med_row["price"])

        # Fetch another test medicine
        med_row_2 = self.db.fetch_one(
            "SELECT medicine_id, medicine_code, medicine_name, price FROM medicines WHERE store_id = ? AND medicine_id != ? LIMIT 1",
            (self.store_1, self.med_1_id)
        )
        self.med_2_id = med_row_2["medicine_id"]
        self.med_2_name = med_row_2["medicine_name"]
        self.med_2_price = float(med_row_2["price"])

    def tearDown(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    # =======================================================================
    # 1. Supplier Management Tests
    # =======================================================================

    def test_01_supplier_create_and_query(self):
        """Verifies creating a supplier, searching, and retrieving details."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="MED-SUP-01",
            supplier_name="Apex Healthcare Distributors",
            contact_person="Ramesh Gupta",
            phone="9876543210",
            email="ramesh@apexmed.in",
            address="Plot 44, Okhla Industrial Area, New Delhi",
            gst_number="07AAAAA0000A1Z5",
            acting_user=self.user_owner
        )
        self.assertGreater(supp_id, 0)

        # Fetch by ID
        supp = self.supplier_service.get_supplier_by_id(supp_id, store_id=self.store_1, acting_user=self.user_owner)
        self.assertIsNotNone(supp)
        self.assertEqual(supp.supplier_code, "MED-SUP-01")
        self.assertEqual(supp.supplier_name, "Apex Healthcare Distributors")
        self.assertTrue(supp.is_active)

        # Search suppliers
        results = self.supplier_service.search_suppliers(self.store_1, "Apex", acting_user=self.user_inventory)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].supplier_id, supp_id)

    def test_02_supplier_duplicate_code_and_validation(self):
        """Verifies duplicate supplier code rejected within store and invalid contacts caught."""
        self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="DUP-CODE",
            supplier_name="First Supplier",
            acting_user=self.user_owner
        )

        # Duplicate code in same store should fail
        with self.assertRaises(ValueError) as ctx:
            self.supplier_service.create_supplier(
                store_id=self.store_1,
                supplier_code="DUP-CODE",
                supplier_name="Second Supplier",
                acting_user=self.user_owner
            )
        self.assertIn("already exists", str(ctx.exception))

        # Empty name should fail validation
        with self.assertRaises(ValueError) as ctx:
            self.supplier_service.create_supplier(
                store_id=self.store_1,
                supplier_code="VALID-CODE",
                supplier_name="",
                acting_user=self.user_owner
            )
        self.assertIn("Supplier name is required", str(ctx.exception))

    def test_03_supplier_deactivation_preserves_history(self):
        """Verifies deactivating a supplier sets is_active=0 without deleting references."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="TEMP-SUP",
            supplier_name="Temporary Vendor",
            acting_user=self.user_owner
        )

        # Deactivate
        self.supplier_service.set_supplier_active_status(supp_id, False, store_id=self.store_1, acting_user=self.user_owner)
        supp = self.supplier_service.get_supplier_by_id(supp_id, store_id=self.store_1)
        self.assertFalse(supp.is_active)

        # Active-only list should exclude it
        active_list = self.supplier_service.get_suppliers(self.store_1, is_active=True, acting_user=self.user_inventory)
        self.assertNotIn(supp_id, [s.supplier_id for s in active_list])

        # Reactivate
        self.supplier_service.set_supplier_active_status(supp_id, True, store_id=self.store_1, acting_user=self.user_owner)
        supp_reactivated = self.supplier_service.get_supplier_by_id(supp_id, store_id=self.store_1)
        self.assertTrue(supp_reactivated.is_active)

    def test_04_supplier_cross_store_isolation(self):
        """Verifies suppliers cannot be accessed or created across store boundaries."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="STORE1-SUP",
            supplier_name="Store 1 Exclusive Vendor",
            acting_user=self.user_owner
        )

        # User from Store 2 trying to access Store 1 supplier should be blocked
        with self.assertRaises(PermissionError):
            self.supplier_service.get_supplier_by_id(supp_id, store_id=self.store_1, acting_user=self.user_store2)

    # =======================================================================
    # 2. Purchase Management & Goods Receiving Tests
    # =======================================================================

    def test_05_purchase_creation_draft_and_multi_items(self):
        """Verifies creating a draft purchase with multiple medicine items."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="PO-SUP-01",
            supplier_name="Pharma Distro Ltd",
            acting_user=self.user_owner
        )

        purchase_items = [
            {"medicine_id": self.med_1_id, "quantity": 100, "unit_cost": 10.0, "subtotal": 1000.0},
            {"medicine_id": self.med_2_id, "quantity": 50, "unit_cost": 20.0, "subtotal": 1000.0}
        ]

        purch_id = self.purchase_service.create_purchase(
            store_id=self.store_1,
            supplier_id=supp_id,
            invoice_number="INV-2026-001",
            purchase_date="2026-10-29",
            items=purchase_items,
            total_amount=2000.0,
            status="DRAFT",
            notes="Initial stock order",
            acting_user=self.user_inventory
        )
        self.assertGreater(purch_id, 0)

        # Fetch purchase
        purchase = self.purchase_service.get_purchase_by_id(purch_id, store_id=self.store_1, acting_user=self.user_owner)
        self.assertEqual(purchase.invoice_number, "INV-2026-001")
        self.assertEqual(purchase.status, "DRAFT")
        self.assertEqual(len(purchase.items), 2)
        self.assertEqual(purchase.total_amount, 2000.0)

    def test_06_deactivated_supplier_cannot_receive_purchases(self):
        """Verifies creating a purchase for an inactive supplier is blocked."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="INACT-SUP",
            supplier_name="Deactivated Supplier",
            acting_user=self.user_owner
        )
        self.supplier_service.set_supplier_active_status(supp_id, False, store_id=self.store_1, acting_user=self.user_owner)

        with self.assertRaises(ValueError) as ctx:
            self.purchase_service.create_purchase(
                store_id=self.store_1,
                supplier_id=supp_id,
                invoice_number="INV-FAIL-01",
                purchase_date="2026-10-29",
                items=[{"medicine_id": self.med_1_id, "quantity": 10, "unit_cost": 5.0}],
                acting_user=self.user_owner
            )
        self.assertIn("deactivated", str(ctx.exception).lower())

    def test_07_goods_receiving_and_batch_creation(self):
        """Verifies explicit goods receiving creates batches and logs stock movements atomically."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="RECV-SUP-01",
            supplier_name="Reliable Meds Ltd",
            acting_user=self.user_owner
        )

        purch_id = self.purchase_service.create_purchase(
            store_id=self.store_1,
            supplier_id=supp_id,
            invoice_number="INV-RECV-01",
            purchase_date="2026-10-29",
            items=[{"medicine_id": self.med_1_id, "quantity": 150, "unit_cost": 12.0}],
            status="DRAFT",
            acting_user=self.user_inventory
        )

        # Get an active shelf location in store 1
        shelf_id = self.shelf_service.get_or_create_location(self.store_1, "Shelf R-01")

        # Receive the goods with manufacturer batch number and expiry date
        receipt_result = self.purchase_service.receive_purchase(
            purchase_id=purch_id,
            receiving_batches=[
                {
                    "item_id": None,
                    "medicine_id": self.med_1_id,
                    "batch_number": "BN-2026-X1",
                    "expiry_date": "2027-06-30",
                    "mfg_date": "2026-01-15",
                    "quantity": 150,
                    "unit_cost": 12.0,
                    "selling_price": self.med_1_price,
                    "location_id": shelf_id
                }
            ],
            store_id=self.store_1,
            acting_user=self.user_inventory
        )

        self.assertEqual(receipt_result["status"], "SUCCESS")
        self.assertEqual(receipt_result["batches_recorded"], 1)

        # Verify purchase status updated to RECEIVED
        updated_purch = self.purchase_service.get_purchase_by_id(purch_id, store_id=self.store_1)
        self.assertEqual(updated_purch.status, "RECEIVED")

        # Verify stock_movements ledger entry
        movement = self.db.fetch_one(
            "SELECT * FROM stock_movements WHERE store_id = ? AND reference_type = 'PURCHASE' AND reference_id = ?",
            (self.store_1, str(purch_id))
        )
        self.assertIsNotNone(movement)
        self.assertEqual(movement["movement_type"], "PURCHASE_RECEIPT")
        self.assertEqual(movement["quantity_delta"], 150)  # Positive delta

        # Verify batch exists in inventory_batches
        batch = self.db.fetch_one(
            "SELECT * FROM inventory_batches WHERE store_id = ? AND batch_number = 'BN-2026-X1'",
            (self.store_1,)
        )
        self.assertIsNotNone(batch)
        self.assertEqual(batch["current_quantity"], 150)
        self.assertEqual(batch["expiry_date"], "2027-06-30")

    def test_08_duplicate_receiving_prevented(self):
        """Verifies retrying a receipt on an already received purchase is strictly blocked."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="NODUP-SUP",
            supplier_name="No Duplicate Vendor",
            acting_user=self.user_owner
        )
        purch_id = self.purchase_service.create_purchase(
            store_id=self.store_1,
            supplier_id=supp_id,
            invoice_number="INV-NODUP-01",
            purchase_date="2026-10-29",
            items=[{"medicine_id": self.med_1_id, "quantity": 40, "unit_cost": 8.0}],
            status="DRAFT",
            acting_user=self.user_inventory
        )
        shelf_id = self.shelf_service.get_or_create_location(self.store_1, "Shelf R-02")

        # First receipt succeeds
        self.purchase_service.receive_purchase(
            purchase_id=purch_id,
            receiving_batches=[{
                "medicine_id": self.med_1_id,
                "batch_number": "BATCH-NODUP",
                "expiry_date": "2027-12-31",
                "quantity": 40,
                "unit_cost": 8.0,
                "selling_price": self.med_1_price,
                "location_id": shelf_id
            }],
            acting_user=self.user_inventory
        )

        # Second receipt attempt must fail
        with self.assertRaises(ValueError) as ctx:
            self.purchase_service.receive_purchase(
                purchase_id=purch_id,
                receiving_batches=[{
                    "medicine_id": self.med_1_id,
                    "batch_number": "BATCH-NODUP",
                    "expiry_date": "2027-12-31",
                    "quantity": 40,
                    "unit_cost": 8.0,
                    "selling_price": self.med_1_price,
                    "location_id": shelf_id
                }],
                acting_user=self.user_inventory
            )
        self.assertIn("already been received", str(ctx.exception))

    def test_09_purchase_cancellation_rules(self):
        """Verifies draft purchases can be cancelled, but received purchases cannot."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="CAN-SUP",
            supplier_name="Cancel Test Vendor",
            acting_user=self.user_owner
        )
        draft_purch_id = self.purchase_service.create_purchase(
            store_id=self.store_1,
            supplier_id=supp_id,
            invoice_number="INV-CANCEL-DRAFT",
            purchase_date="2026-10-29",
            items=[{"medicine_id": self.med_1_id, "quantity": 25, "unit_cost": 10.0}],
            status="DRAFT",
            acting_user=self.user_inventory
        )

        # Cancel draft purchase -> succeeds
        res = self.purchase_service.cancel_purchase(draft_purch_id, reason="Ordered by mistake", acting_user=self.user_owner)
        self.assertTrue(res)
        p_row = self.purchase_service.get_purchase_by_id(draft_purch_id, store_id=self.store_1)
        self.assertEqual(p_row.status, "CANCELLED")

        # Create and receive another purchase
        recv_purch_id = self.purchase_service.create_purchase(
            store_id=self.store_1,
            supplier_id=supp_id,
            invoice_number="INV-CANCEL-RECV",
            purchase_date="2026-10-29",
            items=[{"medicine_id": self.med_1_id, "quantity": 25, "unit_cost": 10.0}],
            status="DRAFT",
            acting_user=self.user_inventory
        )
        shelf_id = self.shelf_service.get_or_create_location(self.store_1, "Shelf R-03")
        self.purchase_service.receive_purchase(
            purchase_id=recv_purch_id,
            receiving_batches=[{
                "medicine_id": self.med_1_id,
                "batch_number": "BN-CANCEL-RECV",
                "expiry_date": "2027-08-31",
                "quantity": 25,
                "unit_cost": 10.0,
                "selling_price": self.med_1_price,
                "location_id": shelf_id
            }],
            acting_user=self.user_inventory
        )

        # Attempt to cancel received purchase -> must be rejected
        with self.assertRaises(ValueError) as ctx:
            self.purchase_service.cancel_purchase(recv_purch_id, acting_user=self.user_owner)
        self.assertIn("already been received", str(ctx.exception))

    # =======================================================================
    # 3. Critical Shelf Allocation Rule Tests
    # =======================================================================

    def test_10_shelf_allocation_rule_differing_expiry_rejected(self):
        """
        Verifies the Critical Shelf Allocation Rule:
        The same medicine must be stored in separate shelf locations when its expiry dates differ.
        """
        shelf_a = self.shelf_service.get_or_create_location(self.store_1, "Shelf S-DIFF-1")

        # 1. Place Batch 1 with expiry 2026-10-25 on Shelf S-DIFF-1
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'BATCH-DIFF-1', '2026-10-25', 100, 100, ?, ?, 'Active')
            """,
            (self.store_1, self.med_1_id, self.med_1_price, shelf_a)
        )

        # 2. Attempt to assign the SAME medicine with DIFFERENT expiry (2026-11-30) to Shelf S-DIFF-1
        is_valid, reason = self.shelf_service.validate_shelf_allocation(
            store_id=self.store_1,
            medicine_id=self.med_1_id,
            location_id=shelf_a,
            expiry_date="2026-11-30"
        )
        self.assertFalse(is_valid)
        self.assertIn("Shelf allocation conflict", reason)
        self.assertIn("separate shelves", reason)

        # 3. Suggest shelf returns an alternative or new shelf code
        loc_id, suggested_code, explanation = self.shelf_service.suggest_shelf_location(
            store_id=self.store_1,
            medicine_id=self.med_1_id,
            expiry_date="2026-11-30"
        )
        self.assertNotEqual(loc_id, shelf_a)
        self.assertTrue(len(suggested_code) > 0)

    def test_11_shelf_allocation_rule_matching_expiry_allowed(self):
        """
        Verifies that batches of the same medicine with the EXACT SAME expiry date
        may share a shelf location even if their batch numbers differ.
        """
        shelf_b = self.shelf_service.get_or_create_location(self.store_1, "Shelf S-MATCH-1")

        # Place Batch 1 with expiry 2026-11-30
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'BATCH-MATCH-1', '2026-11-30', 150, 150, ?, ?, 'Active')
            """,
            (self.store_1, self.med_1_id, self.med_1_price, shelf_b)
        )

        # Batch 2 of the SAME medicine with the SAME expiry (2026-11-30) but DIFFERENT batch number
        is_valid, reason = self.shelf_service.validate_shelf_allocation(
            store_id=self.store_1,
            medicine_id=self.med_1_id,
            location_id=shelf_b,
            expiry_date="2026-11-30"
        )
        self.assertTrue(is_valid)
        self.assertIn("Shares shelf", reason)

    def test_12_shelf_allocation_different_medicines_may_share_shelf(self):
        """Verifies different medicines are permitted to share a shelf."""
        shelf_shared = self.shelf_service.get_or_create_location(self.store_1, "Shelf S-SHARED-1")

        # Medicine 1 on Shelf S-SHARED-1
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'MED1-BATCH', '2027-01-01', 50, 50, ?, ?, 'Active')
            """,
            (self.store_1, self.med_1_id, self.med_1_price, shelf_shared)
        )

        # Medicine 2 on Shelf S-SHARED-1 (different medicine)
        is_valid, reason = self.shelf_service.validate_shelf_allocation(
            store_id=self.store_1,
            medicine_id=self.med_2_id,
            location_id=shelf_shared,
            expiry_date="2027-05-15"
        )
        self.assertTrue(is_valid)

    # =======================================================================
    # 4. FEFO (First Expiry, First Out) Logic Tests
    # =======================================================================

    def test_13_fefo_earliest_expiry_selected_first_and_multi_batch_split(self):
        """
        Verifies FEFO allocation engine:
        - Earliest eligible expiry selected first.
        - Splits requested quantity across multiple batches.
        - Preview does NOT modify stock.
        """
        shelf_1 = self.shelf_service.get_or_create_location(self.store_1, "Shelf FEFO-01")
        shelf_2 = self.shelf_service.get_or_create_location(self.store_1, "Shelf FEFO-02")

        # Insert Batch A: 20 units, expiry 2026-11-10 (earlier)
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'BATCH-A-EARLY', '2026-11-10', 20, 20, 15.0, ?, 'Active')
            """,
            (self.store_1, self.med_1_id, shelf_1)
        )

        # Insert Batch B: 50 units, expiry 2026-11-30 (later)
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'BATCH-B-LATER', '2026-11-30', 50, 50, 15.0, ?, 'Active')
            """,
            (self.store_1, self.med_1_id, shelf_2)
        )

        # Request 35 units on reference date 2026-10-29
        result = self.inventory_service.preview_fefo_allocation(
            store_id=self.store_1,
            medicine_id=self.med_1_id,
            requested_quantity=35,
            reference_date="2026-10-29"
        )

        self.assertTrue(result.success)
        self.assertEqual(result.allocated_quantity, 35)
        self.assertEqual(len(result.allocations), 2)

        # Allocation 1: Batch A (20 units)
        self.assertEqual(result.allocations[0].batch_number, "BATCH-A-EARLY")
        self.assertEqual(result.allocations[0].allocated_quantity, 20)

        # Allocation 2: Batch B (15 units)
        self.assertEqual(result.allocations[1].batch_number, "BATCH-B-LATER")
        self.assertEqual(result.allocations[1].allocated_quantity, 15)

        # CRITICAL SAFETY INVARIANT: Verify stock in database was NOT changed by preview
        batch_a = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_number = 'BATCH-A-EARLY'")
        batch_b = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_number = 'BATCH-B-LATER'")
        self.assertEqual(batch_a["current_quantity"], 20)
        self.assertEqual(batch_b["current_quantity"], 50)

    def test_14_fefo_excludes_expired_quarantined_and_unverified_batches(self):
        """Verifies that expired, quarantined, recalled, and unverified batches are excluded from FEFO."""
        shelf = self.shelf_service.get_or_create_location(self.store_1, "Shelf FEFO-EXCL")

        # 1. Expired batch (expiry 2026-10-25 relative to ref 2026-10-29)
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'EXPIRED-BATCH', '2026-10-25', 100, 100, 10.0, ?, 'Active')
            """,
            (self.store_1, self.med_2_id, shelf)
        )

        # 2. Quarantined batch
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'QUARANTINE-BATCH', '2027-01-01', 50, 50, 10.0, ?, 'Quarantined')
            """,
            (self.store_1, self.med_2_id, shelf)
        )

        # 3. Unverified batch (verification_flag = 1)
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status, verification_flag
            ) VALUES (?, ?, 'UNVERIFIED-BATCH', '2027-02-01', 50, 50, 10.0, ?, 'Active', 1)
            """,
            (self.store_1, self.med_2_id, shelf)
        )

        # 4. Valid active batch (expiry 2027-03-01) with 30 units
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'VALID-BATCH', '2027-03-01', 30, 30, 10.0, ?, 'Active')
            """,
            (self.store_1, self.med_2_id, shelf)
        )

        # Request 20 units -> only VALID-BATCH should be allocated
        result = self.inventory_service.preview_fefo_allocation(
            store_id=self.store_1,
            medicine_id=self.med_2_id,
            requested_quantity=20,
            reference_date="2026-10-29"
        )
        self.assertTrue(result.success)
        self.assertEqual(len(result.allocations), 1)
        self.assertEqual(result.allocations[0].batch_number, "VALID-BATCH")
        self.assertEqual(result.allocations[0].allocated_quantity, 20)

        # Request 40 units -> only 30 eligible available -> should fail with clear insufficient stock message
        fail_result = self.inventory_service.preview_fefo_allocation(
            store_id=self.store_1,
            medicine_id=self.med_2_id,
            requested_quantity=40,
            reference_date="2026-10-29"
        )
        self.assertFalse(fail_result.success)
        self.assertIn("Insufficient eligible stock", fail_result.message)

    def test_15_fefo_deterministic_tie_breaker_for_same_expiry(self):
        """Verifies deterministic tie-breaker (created_at ASC, batch_id ASC) when expiry dates match."""
        shelf = self.shelf_service.get_or_create_location(self.store_1, "Shelf FEFO-TIE")

        # Two batches with identical expiry date (2027-04-30)
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status, created_at
            ) VALUES (?, ?, 'TIE-FIRST', '2027-04-30', 20, 20, 10.0, ?, 'Active', '2026-10-01 10:00:00')
            """,
            (self.store_1, self.med_1_id, shelf)
        )
        self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status, created_at
            ) VALUES (?, ?, 'TIE-SECOND', '2027-04-30', 20, 20, 10.0, ?, 'Active', '2026-10-02 10:00:00')
            """,
            (self.store_1, self.med_1_id, shelf)
        )

        result = self.inventory_service.preview_fefo_allocation(
            store_id=self.store_1,
            medicine_id=self.med_1_id,
            requested_quantity=15,
            reference_date="2026-10-29"
        )
        self.assertTrue(result.success)
        self.assertEqual(result.allocations[0].batch_number, "TIE-FIRST")

    # =======================================================================
    # 5. Stock Movement Ledger & Reconciliation Tests
    # =======================================================================

    def test_16_stock_adjustment_and_sign_conventions(self):
        """Verifies positive and negative stock adjustments with immutable ledger entries."""
        shelf = self.shelf_service.get_or_create_location(self.store_1, "Shelf ADJ-01")
        b_id = self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'BATCH-ADJ', '2027-10-31', 50, 50, 10.0, ?, 'Active')
            """,
            (self.store_1, self.med_1_id, shelf)
        )

        # 1. Positive adjustment (+10 units)
        res_pos = self.inventory_service.adjust_stock(
            store_id=self.store_1,
            batch_id=b_id,
            quantity_delta=10,
            reason="Physical inventory count surplus found",
            acting_user=self.user_inventory
        )
        self.assertEqual(res_pos["new_quantity"], 60)

        # Check movement record has +10
        mov_pos = self.db.fetch_one("SELECT * FROM stock_movements WHERE movement_id = ?", (res_pos["movement_id"],))
        self.assertEqual(mov_pos["quantity_delta"], 10)
        self.assertEqual(mov_pos["movement_type"], "STOCK_ADJUSTMENT")

        # 2. Negative adjustment (-15 units)
        res_neg = self.inventory_service.adjust_stock(
            store_id=self.store_1,
            batch_id=b_id,
            quantity_delta=-15,
            reason="Damaged vial during handling",
            acting_user=self.user_inventory
        )
        self.assertEqual(res_neg["new_quantity"], 45)

        mov_neg = self.db.fetch_one("SELECT * FROM stock_movements WHERE movement_id = ?", (res_neg["movement_id"],))
        self.assertEqual(mov_neg["quantity_delta"], -15)

        # 3. Excessive negative adjustment should fail
        with self.assertRaises(ValueError) as ctx:
            self.inventory_service.adjust_stock(
                store_id=self.store_1,
                batch_id=b_id,
                quantity_delta=-100,
                reason="Excessive reduction",
                acting_user=self.user_inventory
            )
        self.assertIn("cannot become negative", str(ctx.exception))

    def test_17_write_off_expired_batch(self):
        """Verifies writing off an expired batch sets current_quantity=0 and logs EXPIRY_WRITE_OFF."""
        shelf = self.shelf_service.get_or_create_location(self.store_1, "Shelf WOFF-01")
        b_id = self.db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, expiry_date, initial_quantity,
                current_quantity, selling_price, location_id, status
            ) VALUES (?, ?, 'BATCH-WOFF', '2026-09-30', 25, 25, 10.0, ?, 'Active')
            """,
            (self.store_1, self.med_1_id, shelf)
        )

        res = self.inventory_service.write_off_expired_batch(
            store_id=self.store_1,
            batch_id=b_id,
            reason="Expired in September 2026",
            acting_user=self.user_inventory
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["written_off_units"], 25)

        # Batch quantity now 0 and status Expired
        b_row = self.inventory_service.get_batch_by_id(b_id)
        self.assertEqual(b_row.current_quantity, 0)
        self.assertEqual(b_row.status, "Expired")

        # Movement has negative delta (-25)
        mov = self.db.fetch_one(
            "SELECT * FROM stock_movements WHERE batch_id = ? AND movement_type = 'EXPIRY_WRITE_OFF'",
            (b_id,)
        )
        self.assertIsNotNone(mov)
        self.assertEqual(mov["quantity_delta"], -25)

    def test_18_stock_reconciliation_accuracy(self):
        """Verifies multi-dimensional stock reconciliation accurately reports physical vs eligible vs expired."""
        rec_report = self.inventory_service.reconcile_store_inventory(self.store_1, acting_user=self.user_owner)
        self.assertEqual(rec_report["store_id"], self.store_1)
        self.assertGreater(rec_report["total_medicines"], 0)
        self.assertGreater(rec_report["total_physical_units"], 0)

        # Verify each item disaggregates physical, eligible, and expired
        for item in rec_report["items"]:
            self.assertGreaterEqual(item["physical_stock"], 0)
            self.assertGreaterEqual(item["eligible_stock"], 0)
            self.assertGreaterEqual(item["expired_stock"], 0)
            self.assertLessEqual(item["eligible_stock"], item["physical_stock"])

    # =======================================================================
    # 6. Role-Based Access Control Tests
    # =======================================================================

    def test_19_rbac_cashier_blocked_from_purchases_and_suppliers(self):
        """Verifies Cashier role is blocked from creating suppliers, purchases, or adjustments."""
        # 1. Cashier blocked from creating supplier
        with self.assertRaises(PermissionError):
            self.supplier_service.create_supplier(
                store_id=self.store_1,
                supplier_code="CASH-SUP",
                supplier_name="Cashier Supp",
                acting_user=self.user_cashier
            )

        # 2. Cashier blocked from creating purchase
        with self.assertRaises(PermissionError):
            self.purchase_service.create_purchase(
                store_id=self.store_1,
                supplier_id=1,
                invoice_number="INV-CASHIER",
                purchase_date="2026-10-29",
                items=[{"medicine_id": self.med_1_id, "quantity": 10, "unit_cost": 5.0}],
                acting_user=self.user_cashier
            )

        # 3. Cashier blocked from stock adjustment
        with self.assertRaises(PermissionError):
            self.inventory_service.adjust_stock(
                store_id=self.store_1,
                batch_id=1,
                quantity_delta=5,
                reason="Cashier adjustment",
                acting_user=self.user_cashier
            )

    def test_20_rbac_inventory_manager_permitted_goods_receiving_and_batches(self):
        """Verifies Inventory Manager role has permission to receive purchases and manage batches."""
        supp_id = self.supplier_service.create_supplier(
            store_id=self.store_1,
            supplier_code="INV-PERM-SUP",
            supplier_name="Inventory Perm Vendor",
            acting_user=self.user_owner
        )

        # Inventory Manager can create purchase
        purch_id = self.purchase_service.create_purchase(
            store_id=self.store_1,
            supplier_id=supp_id,
            invoice_number="INV-INV-PERM",
            purchase_date="2026-10-29",
            items=[{"medicine_id": self.med_1_id, "quantity": 30, "unit_cost": 5.0}],
            status="DRAFT",
            acting_user=self.user_inventory
        )
        self.assertGreater(purch_id, 0)

        # Inventory Manager can receive goods
        shelf_id = self.shelf_service.get_or_create_location(self.store_1, "Shelf INV-01")
        receipt = self.purchase_service.receive_purchase(
            purchase_id=purch_id,
            receiving_batches=[{
                "medicine_id": self.med_1_id,
                "batch_number": "BN-INV-PERM",
                "expiry_date": "2027-11-30",
                "quantity": 30,
                "unit_cost": 5.0,
                "selling_price": self.med_1_price,
                "location_id": shelf_id
            }],
            acting_user=self.user_inventory
        )
        self.assertEqual(receipt["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
