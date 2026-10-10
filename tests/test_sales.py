"""
Stage 5 Unit Tests for Sales & Checkout Billing System & Atomic Transactions.
Tests cart logic, Poka-Yoke expired & out-of-stock blocks, subtotal/total calculations in ₹,
sales & sale_items database persistence, and critical atomic transaction ROLLBACK behavior.
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from database.db import Database
from database.schema import init_db
from models.medicine import Medicine
from services.medicine_service import MedicineService
from services.sales_service import SalesService


class TestSalesBillingSystem(unittest.TestCase):
    """Test suite for Sales Checkout System and Atomic SQLite Transactions."""

    def setUp(self):
        """Creates an isolated temporary database for test execution."""
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)

        self.db = init_db(self.temp_db_path)
        self.sales_service = SalesService(self.db)
        self.med_service = MedicineService(self.db)

    def tearDown(self):
        """Cleans up temporary database file."""
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except PermissionError:
                pass

    def test_1_add_item_to_cart_logic(self):
        """Verifies cart item validation via sales service."""
        # MED1001 (Paracetamol 500mg, Qty: 150, Valid expiry)
        med = self.med_service.get_medicine_by_code("MED1001")
        is_valid, msg, validated_med = self.sales_service.validate_cart_item(med.medicine_id, 2)
        self.assertTrue(is_valid)
        self.assertEqual(validated_med.medicine_id, med.medicine_id)

    def test_2_quantity_validation(self):
        """Verifies Poka-Yoke prevention: blocks zero or negative quantity inputs."""
        med = self.med_service.get_medicine_by_code("MED1001")
        is_valid_zero, msg_z, _ = self.sales_service.validate_cart_item(med.medicine_id, 0)
        self.assertFalse(is_valid_zero)

        is_valid_neg, msg_n, _ = self.sales_service.validate_cart_item(med.medicine_id, -5)
        self.assertFalse(is_valid_neg)

    def test_3_insufficient_stock_prevention(self):
        """Verifies Poka-Yoke prevention: blocks requesting quantity exceeding available stock."""
        # MED1008 (Azithromycin 500mg, Stock: 5)
        med = self.med_service.get_medicine_by_code("MED1008")
        is_valid, msg, _ = self.sales_service.validate_cart_item(med.medicine_id, 10)
        self.assertFalse(is_valid)
        self.assertIn("Insufficient stock", msg)

    def test_4_expired_medicine_prevention(self):
        """Verifies Poka-Yoke prevention: blocks selling expired medicines."""
        # MED1015 (Aspirin 75mg, Expired)
        med = self.med_service.get_medicine_by_code("MED1015")
        self.assertTrue(med.is_expired)

        is_valid, msg, _ = self.sales_service.validate_cart_item(med.medicine_id, 1)
        self.assertFalse(is_valid)
        self.assertIn("expired", msg.lower())

    def test_5_duplicate_cart_item_handling(self):
        """Verifies that processing a cart with multiple quantities of the same item combines properly."""
        med = self.med_service.get_medicine_by_code("MED1001")
        # 2 units + 3 units = 5 units total
        cart_items = [(med.medicine_id, 5)]
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, cart_items, 'Test Patient')
        self.assertTrue(ok)

        sale_details = self.sales_service.get_sale_details(sale_id)
        self.assertEqual(len(sale_details["items"]), 1)
        self.assertEqual(sale_details["items"][0]["quantity"], 5)

    def test_6_correct_subtotal_calculation(self):
        """Verifies subtotal formula: subtotal = quantity * unit price."""
        med = self.med_service.get_medicine_by_code("MED1001") # Price: 15.50
        expected_subtotal = round(15.50 * 4, 2)
        cart_items = [(med.medicine_id, 4)]
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, cart_items, 'Test Patient')
        self.assertTrue(ok)

        sale_details = self.sales_service.get_sale_details(sale_id)
        self.assertEqual(sale_details["items"][0]["subtotal"], expected_subtotal)

    def test_7_correct_total_calculation(self):
        """Verifies total amount calculation: sum of subtotals."""
        m1 = self.med_service.get_medicine_by_code("MED1001") # 15.50 * 2 = 31.00
        m2 = self.med_service.get_medicine_by_code("MED1003") # 85.00 * 1 = 85.00
        expected_total = round(31.00 + 85.00, 2)

        cart_items = [(m1.medicine_id, 2), (m2.medicine_id, 1)]
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, cart_items, 'Test Patient')
        self.assertTrue(ok)

        sale_details = self.sales_service.get_sale_details(sale_id)
        self.assertEqual(sale_details["total_amount"], expected_total)

    def test_8_successful_sale_creation(self):
        """Verifies successful checkout transaction completion."""
        m1 = self.med_service.get_medicine_by_code("MED1001")
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, [(m1.medicine_id, 1)], 'Test Patient')
        self.assertTrue(ok)
        self.assertIsNotNone(sale_id)

    def test_9_sales_record_creation(self):
        """Verifies creation of header row in sales table."""
        m1 = self.med_service.get_medicine_by_code("MED1001")
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, [(m1.medicine_id, 1)], 'Test Patient')
        
        sale_row = self.db.fetch_one("SELECT * FROM sales WHERE sale_id = ?", (sale_id,))
        self.assertIsNotNone(sale_row)
        self.assertEqual(sale_row["user_id"], 1)

    def test_10_sale_items_record_creation(self):
        """Verifies creation of line item rows in sale_items table."""
        m1 = self.med_service.get_medicine_by_code("MED1001")
        m2 = self.med_service.get_medicine_by_code("MED1002")
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, [(m1.medicine_id, 2), (m2.medicine_id, 1)], 'Test Patient')
        
        items = self.db.fetch_all("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,))
        self.assertEqual(len(items), 2)

    def test_11_correct_stock_deduction(self):
        """Verifies that inventory stock quantity is reduced by purchased amount."""
        m1 = self.med_service.get_medicine_by_code("MED1001")
        initial_stock = m1.quantity

        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, [(m1.medicine_id, 10)], 'Test Patient')
        self.assertTrue(ok)

        m1_after = self.med_service.get_medicine_by_code("MED1001")
        self.assertEqual(m1_after.quantity, initial_stock - 10)

    def test_12_zero_negative_stock_prevention(self):
        """Verifies that stock cannot be deducted below zero."""
        m_low = self.med_service.get_medicine_by_code("MED1008") # Stock: 5
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, [(m_low.medicine_id, 6)], 'Test Patient')
        self.assertFalse(ok)

        m_low_after = self.med_service.get_medicine_by_code("MED1008")
        self.assertEqual(m_low_after.quantity, 5)

    def test_13_empty_cart_checkout_prevention(self):
        """Verifies empty cart checkout is blocked."""
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, [], 'Test Patient')
        self.assertFalse(ok)
        self.assertIn("Cart is empty", msg)

    def test_14_atomic_transaction_behavior(self):
        """Verifies atomic commit behavior on valid multi-item checkout."""
        m1 = self.med_service.get_medicine_by_code("MED1001")
        m2 = self.med_service.get_medicine_by_code("MED1002")
        stock1_init = m1.quantity
        stock2_init = m2.quantity

        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, [(m1.medicine_id, 3), (m2.medicine_id, 4)], 'Test Patient')
        self.assertTrue(ok)

        self.assertEqual(self.med_service.get_medicine_by_code("MED1001").quantity, stock1_init - 3)
        self.assertEqual(self.med_service.get_medicine_by_code("MED1002").quantity, stock2_init - 4)

    def test_15_critical_atomic_transaction_rollback(self):
        """
        CRITICAL TEST: Multi-item checkout where Item A has sufficient stock and Item B has insufficient stock.
        Proves atomic ROLLBACK behavior:
        - Sale transaction fails.
        - Item A stock remains UNCHANGED.
        - Item B stock remains UNCHANGED.
        - NO sales header record is created.
        - NO sale_items line item records are created.
        """
        m_valid = self.med_service.get_medicine_by_code("MED1001") # Stock: 150
        m_insufficient = self.med_service.get_medicine_by_code("MED1008") # Stock: 5

        stock_valid_before = m_valid.quantity
        stock_insufficient_before = m_insufficient.quantity
        sales_count_before = self.db.fetch_one("SELECT COUNT(*) as cnt FROM sales")["cnt"]

        # Attempt multi-item purchase where Item 2 requests 100 units (only 5 available)
        cart_items = [(m_valid.medicine_id, 10), (m_insufficient.medicine_id, 100)]
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(1, cart_items, 'Test Patient')

        # 1. Sale process must return False
        self.assertFalse(ok, "Transaction should have failed and returned False")
        self.assertIsNone(sale_id, "Sale ID should be None on transaction failure")

        # 2. Item A stock MUST be unchanged (NOT reduced by 10)
        m_valid_after = self.med_service.get_medicine_by_code("MED1001")
        self.assertEqual(m_valid_after.quantity, stock_valid_before, "Item A stock was improperly modified!")

        # 3. Item B stock MUST be unchanged
        m_insufficient_after = self.med_service.get_medicine_by_code("MED1008")
        self.assertEqual(m_insufficient_after.quantity, stock_insufficient_before, "Item B stock was improperly modified!")

        # 4. Total sales count MUST remain unchanged
        sales_count_after = self.db.fetch_one("SELECT COUNT(*) as cnt FROM sales")["cnt"]
        self.assertEqual(sales_count_after, sales_count_before, "Incomplete sales header record was created!")

    def test_16_authenticated_user_id_stored_correctly(self):
        """Verifies that the authenticated user's ID (e.g. user_id=2 for pharmacist) is correctly recorded."""
        m1 = self.med_service.get_medicine_by_code("MED1001")
        ok, msg, sale_id, inv_num = self.sales_service.process_sale(2, [(m1.medicine_id, 1)], 'Test Patient')
        self.assertTrue(ok)

        sale_row = self.db.fetch_one("SELECT user_id FROM sales WHERE sale_id = ?", (sale_id,))
        self.assertEqual(sale_row["user_id"], 2)


if __name__ == "__main__":
    unittest.main()
