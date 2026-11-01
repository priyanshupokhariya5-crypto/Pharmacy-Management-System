"""
Stage 5 Comprehensive Unit and Integration Tests.
Covers:
  1. Mandatory 10-digit Indian mobile number validation
  2. POS bill calculations (subtotal, discount, tax, rounding, grand total)
  3. Cash, UPI, and Card checkout with transaction references
  4. Real FEFO batch stock deductions and multi-batch allocations
  5. Ineligible / expired / quarantined batch exclusion during checkout
  6. Atomic transaction integrity and overselling rollback
  7. Partial and full customer returns, over-return rejection, and restock safety
  8. Cashier shift sales reconciliation and payment method metrics
  9. Audit logging and ReportService tabular / CSV exports
  10. Store isolation enforcement across all operations
"""
import os
import shutil
import unittest
from datetime import datetime, timedelta

from database.db import Database
from database.schema import migrate_database
from database.migration_stage2 import apply_stage2_migration
from models.user import User, ROLE_ADMIN, ROLE_CASHIER, ROLE_PHARMACIST
from models.medicine import Medicine
from services.sales_service import SalesService
from services.inventory_service import InventoryService
from services.shelf_service import ShelfService
from services.audit_service import AuditService
from services.report_service import ReportService
from utils.validators import validate_indian_phone, calculate_bill_totals


class TestStage5BillingPOSReturns(unittest.TestCase):
    """Test suite validating all Stage 5 Billing, FEFO Checkout, and Return requirements."""

    def setUp(self):
        """Create an isolated test database copy with Stage 2/4/5 schema applied."""
        self.test_db_path = f"data/test_stage5_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.db"
        shutil.copyfile(os.path.abspath("data/pharmacy.db"), self.test_db_path)
        self.db = Database(self.test_db_path)
        migrate_database(self.db)
        apply_stage2_migration(self.db)

        self.store_a = "STORE-A"
        self.store_b = "STORE-B"

        self.db.execute("INSERT OR IGNORE INTO stores (store_id, store_name, owner_name) VALUES (?, ?, ?)",
                        (self.store_a, "Apex Pharmacy Store A", "Admin A"))
        self.db.execute("INSERT OR IGNORE INTO stores (store_id, store_name, owner_name) VALUES (?, ?, ?)",
                        (self.store_b, "Beacon Pharmacy Store B", "Admin B"))

        # Create Test Users in users table
        self.db.execute(
            "INSERT INTO users (username, password_hash, role, store_id, full_name, email) VALUES (?, ?, ?, ?, ?, ?)",
            ("admin_a", "dummyhash", "Admin", self.store_a, "Admin User A", "admin_a@pharmacy.test")
        )
        self.admin_a_id = self.db.fetch_one("SELECT user_id FROM users WHERE username = 'admin_a'")["user_id"]
        self.admin_user_a = User(user_id=self.admin_a_id, username="admin_a", role=ROLE_ADMIN, store_id=self.store_a)

        self.db.execute(
            "INSERT INTO users (username, password_hash, role, store_id, full_name, email) VALUES (?, ?, ?, ?, ?, ?)",
            ("cashier_a", "dummyhash", "Cashier", self.store_a, "Cashier User A", "cashier_a@pharmacy.test")
        )
        self.cashier_a_id = self.db.fetch_one("SELECT user_id FROM users WHERE username = 'cashier_a'")["user_id"]
        self.cashier_user_a = User(user_id=self.cashier_a_id, username="cashier_a", role=ROLE_CASHIER, store_id=self.store_a)

        # Seed Test Medicines
        self.today = datetime.now().date()
        self.exp_future1 = (self.today + timedelta(days=60)).strftime("%Y-%m-%d")
        self.exp_future2 = (self.today + timedelta(days=120)).strftime("%Y-%m-%d")
        self.exp_past = (self.today - timedelta(days=10)).strftime("%Y-%m-%d")

        self.db.execute(
            """
            INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.store_a, "MED-PARA", "Paracetamol 500mg", "Analgesic", "Cipla", "B-P100", 5.0, 100, self.exp_future1)
        )
        self.med_para_id = self.db.fetch_one("SELECT medicine_id FROM medicines WHERE medicine_code = 'MED-PARA' AND store_id = ?", (self.store_a,))["medicine_id"]

        self.db.execute(
            """
            INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (self.store_a, "MED-AMOX", "Amoxicillin 250mg", "Antibiotic", "Sun Pharma", "B-A100", 12.0, 50, self.exp_future2)
        )
        self.med_amox_id = self.db.fetch_one("SELECT medicine_id FROM medicines WHERE medicine_code = 'MED-AMOX' AND store_id = ?", (self.store_a,))["medicine_id"]

        # Seed Normalized Batches for Paracetamol in Store A
        # Batch 1: 30 units, earlier expiry (exp_future1)
        self.db.execute(
            """
            INSERT INTO inventory_batches (store_id, medicine_id, batch_number, expiry_date, initial_quantity, current_quantity, purchase_cost, selling_price, status, verification_flag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active', 0)
            """,
            (self.store_a, self.med_para_id, "BATCH-P1", self.exp_future1, 30, 30, 2.5, 5.0)
        )
        self.batch_p1_id = self.db.fetch_one("SELECT batch_id FROM inventory_batches WHERE batch_number = 'BATCH-P1'")["batch_id"]

        # Batch 2: 70 units, later expiry (exp_future2)
        self.db.execute(
            """
            INSERT INTO inventory_batches (store_id, medicine_id, batch_number, expiry_date, initial_quantity, current_quantity, purchase_cost, selling_price, status, verification_flag)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active', 0)
            """,
            (self.store_a, self.med_para_id, "BATCH-P2", self.exp_future2, 70, 70, 2.5, 5.0)
        )
        self.batch_p2_id = self.db.fetch_one("SELECT batch_id FROM inventory_batches WHERE batch_number = 'BATCH-P2'")["batch_id"]

        self.sales_service_a = SalesService(db=self.db, store_id=self.store_a)
        self.audit_service = AuditService(db=self.db)
        self.report_service_a = ReportService(db=self.db, store_id=self.store_a)

    def tearDown(self):
        """Clean up isolated test database."""
        try:
            self.db.close()
        except Exception:
            pass
        if os.path.exists(self.test_db_path):
            try:
                os.remove(self.test_db_path)
            except Exception:
                pass

    # =========================================================================
    # 1. Mandatory Phone Validation Tests
    # =========================================================================
    def test_phone_validation_valid_formats(self):
        """Verifies valid 10-digit Indian mobile numbers starting with 6, 7, 8, 9."""
        valid_samples = [
            ("9876543210", "9876543210"),
            ("8123456789", "8123456789"),
            ("7000012345", "7000012345"),
            ("6999988888", "6999988888"),
            ("+91 9876543210", "9876543210"),
            ("91-98765-43210", "9876543210"),
            ("09876543210", "9876543210")
        ]
        for raw, expected in valid_samples:
            is_valid, msg, cleaned = validate_indian_phone(raw)
            self.assertTrue(is_valid, f"Expected {raw} to be valid: {msg}")
            self.assertEqual(cleaned, expected)

    def test_phone_validation_invalid_formats(self):
        """Verifies rejection of invalid lengths, characters, empty strings, and starting digits."""
        invalid_samples = [
            "",
            "   ",
            None,
            "1234567890",       # Starts with 1
            "5555555555",       # Starts with 5
            "987654321",        # 9 digits
            "98765432101",      # 11 digits
            "98765ABCD0",       # Alphabetic
            "98765@4321",       # Symbols
        ]
        for raw in invalid_samples:
            is_valid, msg, _ = validate_indian_phone(raw)
            self.assertFalse(is_valid, f"Expected {raw} to be rejected.")
            self.assertIn("mobile number", msg.lower())

    # =========================================================================
    # 2. Financial Calculations & Rounding Tests
    # =========================================================================
    def test_calculate_bill_totals(self):
        """Verifies subtotal, discount, tax, rounding, and grand total."""
        totals = calculate_bill_totals(subtotal=100.0, discount_amount=10.0, tax_rate=5.0, enable_rounding=True)
        self.assertEqual(totals["subtotal"], 100.0)
        self.assertEqual(totals["discount_amount"], 10.0)
        # Taxable = 90.0, Tax 5% = 4.50. Total = 94.50 -> rounded to 95.0, rounding = 0.50
        self.assertEqual(totals["tax_amount"], 4.50)
        self.assertEqual(totals["rounding_amount"], 0.50)
        self.assertEqual(totals["grand_total"], 95.0)

    # =========================================================================
    # 3. POS Checkout with Cash, UPI, and Card
    # =========================================================================
    def test_pos_checkout_cash(self):
        """Verifies successful checkout with Cash payment method."""
        cart = [(self.med_para_id, 10)]
        success, msg, sale_id, inv = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Rohan Verma",
            patient_phone="9876543210",
            payment_method="Cash",
            acting_user=self.cashier_user_a
        )
        self.assertTrue(success, f"Checkout failed: {msg}")
        self.assertIsNotNone(sale_id)
        self.assertTrue(inv.startswith("INV-"))

        # Verify sale details
        details = self.sales_service_a.get_sale_details(sale_id)
        self.assertEqual(details["patient_name"], "Rohan Verma")
        self.assertEqual(details["patient_phone"], "9876543210")
        self.assertEqual(details["payment_method"], "Cash")
        self.assertEqual(details["total_amount"], 50.0)

    def test_pos_checkout_upi_with_reference(self):
        """Verifies checkout with UPI and transaction reference."""
        cart = [(self.med_para_id, 5)]
        success, msg, sale_id, inv = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Pooja Sharma",
            patient_phone="8888877777",
            payment_method="UPI",
            payment_reference="UPI-REF-99887766",
            acting_user=self.cashier_user_a
        )
        self.assertTrue(success, f"Checkout failed: {msg}")
        details = self.sales_service_a.get_sale_details(sale_id)
        self.assertEqual(details["payment_method"], "UPI")
        self.assertEqual(details["payment_reference"], "UPI-REF-99887766")

    def test_pos_checkout_card_with_reference(self):
        """Verifies checkout with Card and auth reference."""
        cart = [(self.med_para_id, 4)]
        success, msg, sale_id, inv = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Anil Kumar",
            patient_phone="7777766666",
            payment_method="Card",
            payment_reference="AUTH-CARD-1234",
            acting_user=self.cashier_user_a
        )
        self.assertTrue(success, f"Checkout failed: {msg}")
        details = self.sales_service_a.get_sale_details(sale_id)
        self.assertEqual(details["payment_method"], "Card")
        self.assertEqual(details["payment_reference"], "AUTH-CARD-1234")

    def test_pos_checkout_rejects_invalid_phone(self):
        """Verifies checkout is rejected if customer phone number is invalid."""
        cart = [(self.med_para_id, 5)]
        success, msg, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Invalid Customer",
            patient_phone="12345",  # Invalid
            acting_user=self.cashier_user_a
        )
        self.assertFalse(success)
        self.assertIn("validation error", msg.lower())
        self.assertIsNone(sale_id)

    # =========================================================================
    # 4. FEFO Batch Deduction Integration Tests
    # =========================================================================
    def test_fefo_single_batch_allocation(self):
        """Verifies that stock is deducted from earliest expiring batch (BATCH-P1)."""
        # BATCH-P1 has 30 units (exp_future1), BATCH-P2 has 70 units (exp_future2)
        cart = [(self.med_para_id, 20)]
        success, msg, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="FEFO Test 1",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        self.assertTrue(success)

        # Check BATCH-P1 was deducted from 30 -> 10
        b1_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p1_id,))["current_quantity"]
        self.assertEqual(b1_qty, 10)

        # Check BATCH-P2 remains untouched at 70
        b2_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p2_id,))["current_quantity"]
        self.assertEqual(b2_qty, 70)

        # Check legacy medicines quantity was updated from 100 -> 80
        med_qty = self.db.fetch_one("SELECT quantity FROM medicines WHERE medicine_id = ?", (self.med_para_id,))["quantity"]
        self.assertEqual(med_qty, 80)

        # Check stock movement ledger entry
        mov = self.db.fetch_one("SELECT * FROM stock_movements WHERE batch_id = ? AND movement_type = 'SALE_DISPENSE'", (self.batch_p1_id,))
        self.assertIsNotNone(mov)
        self.assertEqual(mov["quantity_delta"], -20)

    def test_fefo_multi_batch_split_allocation(self):
        """Verifies that a sale spanning across multiple batches allocates sequentially by FEFO."""
        # BATCH-P1 has 30 units, BATCH-P2 has 70 units. Request 45 units.
        # Should take 30 from BATCH-P1 (exhausting it) and 15 from BATCH-P2.
        cart = [(self.med_para_id, 45)]
        success, msg, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Multi Batch Customer",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        self.assertTrue(success)

        b1_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p1_id,))["current_quantity"]
        b2_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p2_id,))["current_quantity"]
        self.assertEqual(b1_qty, 0)
        self.assertEqual(b2_qty, 55)

        # Verify sale_batch_allocations has 2 records
        allocs = self.db.fetch_all(
            """
            SELECT sba.* FROM sale_batch_allocations sba
            JOIN sale_items si ON sba.sale_item_id = si.item_id
            WHERE si.sale_id = ?
            ORDER BY sba.allocation_id ASC
            """,
            (sale_id,)
        )
        self.assertEqual(len(allocs), 2)
        self.assertEqual(allocs[0]["batch_id"], self.batch_p1_id)
        self.assertEqual(allocs[0]["quantity"], 30)
        self.assertEqual(allocs[1]["batch_id"], self.batch_p2_id)
        self.assertEqual(allocs[1]["quantity"], 15)

    def test_fefo_excludes_expired_and_quarantined_batches(self):
        """Verifies that expired, quarantined, or unverified batches are excluded from sale allocation."""
        # Add an expired batch
        self.db.execute(
            """
            INSERT INTO inventory_batches (store_id, medicine_id, batch_number, expiry_date, initial_quantity, current_quantity, purchase_cost, selling_price, status, verification_flag)
            VALUES (?, ?, 'BATCH-EXPIRED', ?, 50, 50, 2.5, 5.0, 'Expired', 0)
            """,
            (self.store_a, self.med_para_id, self.exp_past)
        )
        # Add a quarantined batch
        self.db.execute(
            """
            INSERT INTO inventory_batches (store_id, medicine_id, batch_number, expiry_date, initial_quantity, current_quantity, purchase_cost, selling_price, status, verification_flag)
            VALUES (?, ?, 'BATCH-QUAR', ?, 50, 50, 2.5, 5.0, 'Quarantined', 0)
            """,
            (self.store_a, self.med_para_id, self.exp_future1)
        )

        # Request 10 units: should only come from active BATCH-P1
        cart = [(self.med_para_id, 10)]
        success, msg, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Exclusion Test",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        self.assertTrue(success)

        # Neither expired nor quarantined batch should be deducted
        exp_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_number = 'BATCH-EXPIRED'")["current_quantity"]
        quar_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_number = 'BATCH-QUAR'")["current_quantity"]
        self.assertEqual(exp_qty, 50)
        self.assertEqual(quar_qty, 50)

    def test_checkout_rollback_on_insufficient_stock(self):
        """Verifies transaction rollback when requested quantity exceeds available stock."""
        # Available in batches is 100. Request 150.
        cart = [(self.med_para_id, 150)]
        success, msg, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Oversell Customer",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        self.assertFalse(success)
        self.assertIn("insufficient stock", msg.lower())
        self.assertIsNone(sale_id)

        # Stock must remain unchanged
        b1_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p1_id,))["current_quantity"]
        b2_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p2_id,))["current_quantity"]
        self.assertEqual(b1_qty, 30)
        self.assertEqual(b2_qty, 70)

    def test_cross_store_isolation_in_checkout(self):
        """Verifies that checkout in Store A cannot sell medicines from Store B."""
        # Insert medicine in Store B
        self.db.execute(
            """
            INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
            VALUES (?, 'MED-B-ONLY', 'Store B Tonic', 'Syrup', 'Dabur', 'B-TONIC', 20.0, 50, ?)
            """,
            (self.store_b, self.exp_future1)
        )
        med_b_id = self.db.fetch_one("SELECT medicine_id FROM medicines WHERE medicine_code = 'MED-B-ONLY'")["medicine_id"]

        # Attempt to sell in Store A
        cart = [(med_b_id, 5)]
        success, msg, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Cross Store Attack",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        self.assertFalse(success)
        self.assertIn("does not belong to store", msg.lower())

    # =========================================================================
    # 5. Returns and Refunds Tests
    # =========================================================================
    def test_partial_sale_return_restocks_inventory(self):
        """Verifies partial return restores stock, writes ledger entry, and marks PARTIALLY_REFUNDED."""
        # 1. Complete sale of 10 units
        cart = [(self.med_para_id, 10)]
        success, msg, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Return Customer",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        self.assertTrue(success)

        # 2. Get sale details to identify item_id
        details = self.sales_service_a.get_sale_details(sale_id)
        item_id = details["items"][0]["item_id"]

        # 3. Process return of 4 units
        ret_items = [{"sale_item_id": item_id, "quantity": 4, "restock_condition": "SELLABLE"}]
        ret_success, ret_msg, ret_id = self.sales_service_a.process_sale_return(
            sale_id=sale_id,
            return_items=ret_items,
            refund_method="Cash",
            reason="Customer changed mind",
            acting_user=self.cashier_user_a
        )
        self.assertTrue(ret_success, f"Return failed: {ret_msg}")
        self.assertIsNotNone(ret_id)

        # Verify stock was restored (+4)
        b1_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p1_id,))["current_quantity"]
        # Originally 30 -> 20 after sale -> 24 after return of 4
        self.assertEqual(b1_qty, 24)

        # Verify stock movement ledger has CUSTOMER_RETURN (+4)
        mov = self.db.fetch_one("SELECT * FROM stock_movements WHERE movement_type = 'CUSTOMER_RETURN' AND batch_id = ?", (self.batch_p1_id,))
        self.assertIsNotNone(mov)
        self.assertEqual(mov["quantity_delta"], 4)

        # Verify sale status updated to PARTIALLY_REFUNDED
        updated_sale = self.sales_service_a.get_sale_details(sale_id)
        self.assertEqual(updated_sale["status"], "PARTIALLY_REFUNDED")

    def test_over_return_prevention(self):
        """Verifies that returning more than originally sold is strictly rejected."""
        cart = [(self.med_para_id, 5)]
        success, _, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Over Return Customer",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        details = self.sales_service_a.get_sale_details(sale_id)
        item_id = details["items"][0]["item_id"]

        # Attempt to return 6 units when only 5 were sold
        ret_items = [{"sale_item_id": item_id, "quantity": 6, "restock_condition": "SELLABLE"}]
        ret_success, ret_msg, ret_id = self.sales_service_a.process_sale_return(
            sale_id=sale_id,
            return_items=ret_items,
            acting_user=self.cashier_user_a
        )
        self.assertFalse(ret_success)
        self.assertIn("cannot return", ret_msg.lower())

    def test_return_expired_stock_safety(self):
        """Verifies that returning expired items does not add them back to sellable stock."""
        # 1. Complete sale
        cart = [(self.med_para_id, 5)]
        success, _, sale_id, _ = self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Safety Return",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        details = self.sales_service_a.get_sale_details(sale_id)
        item_id = details["items"][0]["item_id"]

        # Simulate batch expiring right after sale
        self.db.execute("UPDATE inventory_batches SET expiry_date = ? WHERE batch_id = ?", (self.exp_past, self.batch_p1_id))
        pre_ret_b1_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p1_id,))["current_quantity"]

        # 2. Return item
        ret_items = [{"sale_item_id": item_id, "quantity": 2, "restock_condition": "SELLABLE"}]
        ret_success, ret_msg, ret_id = self.sales_service_a.process_sale_return(
            sale_id=sale_id,
            return_items=ret_items,
            acting_user=self.cashier_user_a
        )
        self.assertTrue(ret_success)

        # Batch quantity should NOT be increased because expiry date passed!
        post_ret_b1_qty = self.db.fetch_one("SELECT current_quantity FROM inventory_batches WHERE batch_id = ?", (self.batch_p1_id,))["current_quantity"]
        self.assertEqual(pre_ret_b1_qty, post_ret_b1_qty)

    # =========================================================================
    # 6. Cashier Shift Reconciliation Metrics Tests
    # =========================================================================
    def test_cashier_shift_summary_metrics(self):
        """Verifies cashier dashboard calculation of bills, gross, cash, upi, card, and net sales."""
        # Sale 1: Cash ₹50
        self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=[(self.med_para_id, 10)],
            patient_name="Customer 1",
            patient_phone="9876543210",
            payment_method="Cash",
            acting_user=self.cashier_user_a
        )
        # Sale 2: UPI ₹25
        self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=[(self.med_para_id, 5)],
            patient_name="Customer 2",
            patient_phone="8888877777",
            payment_method="UPI",
            acting_user=self.cashier_user_a
        )

        summary = self.sales_service_a.get_cashier_summary(cashier_user_id=self.cashier_a_id)
        self.assertEqual(summary["bills_count"], 2)
        self.assertEqual(summary["gross_sales"], 75.0)
        self.assertEqual(summary["cash_collections"], 50.0)
        self.assertEqual(summary["upi_collections"], 25.0)
        self.assertEqual(summary["card_collections"], 0.0)
        self.assertEqual(summary["net_settled_sales"], 75.0)

    # =========================================================================
    # 7. Audit Logging Tests
    # =========================================================================
    def test_audit_logs_recorded_on_sale(self):
        """Verifies that completing a sale writes an audit log entry."""
        cart = [(self.med_para_id, 2)]
        self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=cart,
            patient_name="Audit Patient",
            patient_phone="9876543210",
            acting_user=self.cashier_user_a
        )
        logs = self.audit_service.get_audit_logs(store_id=self.store_a, action_filter="SALE_CHECKOUT", acting_user=self.admin_user_a)
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "SALE_CHECKOUT")
        self.assertIn("Audit Patient", logs[0]["details"])

    # =========================================================================
    # 8. Report Service Tabular & CSV Export Tests
    # =========================================================================
    def test_report_service_and_csv_export(self):
        """Verifies report generation and CSV export."""
        self.sales_service_a.process_sale(
            user_id=self.cashier_a_id,
            cart_items=[(self.med_para_id, 2)],
            patient_name="Report Patient",
            patient_phone="9876543210",
            payment_method="Cash",
            acting_user=self.cashier_user_a
        )

        rep = self.report_service_a.get_sales_summary_report(acting_user=self.admin_user_a)
        self.assertGreaterEqual(rep["total_transactions"], 1)
        self.assertGreater(rep["gross_sales"], 0)

        csv_str = self.report_service_a.export_to_csv(rep["transactions"])
        self.assertIn("invoice_number", csv_str)
        self.assertIn("Report Patient", csv_str)


if __name__ == "__main__":
    unittest.main()
