"""
Stage 3 Unit Tests for Medicine Inventory CRUD Management & Poka-Yoke Validations.
Tests addition, updates, deletions, uniqueness checks, input bounds, stock/expiry status logic.
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from database.db import Database
from database.schema import init_db
from models.medicine import Medicine
from services.medicine_service import MedicineService


class TestMedicineCRUD(unittest.TestCase):
    """Test suite for Medicine CRUD operations and Poka-Yoke validation rules."""

    def setUp(self):
        """Creates an isolated temporary database for test execution."""
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)

        self.db = init_db(self.temp_db_path)
        self.med_service = MedicineService(self.db)

    def tearDown(self):
        """Removes the temporary database file after tests finish."""
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except PermissionError:
                pass

    def test_1_add_valid_medicine(self):
        """Verifies adding a valid medicine record to inventory."""
        exp_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
        med = Medicine(
            medicine_id=None,
            medicine_code="MED2001",
            medicine_name="Dolo 650mg",
            category="Analgesic",
            manufacturer="Micro Labs",
            batch_no="B202615",
            price=30.00,
            quantity=150,
            expiry_date=exp_date
        )

        ok, msg = self.med_service.add_medicine(med)
        self.assertTrue(ok, f"Add valid medicine failed: {msg}")

        inserted = self.med_service.get_medicine_by_code("MED2001")
        self.assertIsNotNone(inserted)
        self.assertEqual(inserted.medicine_name, "Dolo 650mg")
        self.assertEqual(inserted.price, 30.00)

    def test_2_reject_duplicate_medicine_code(self):
        """Verifies Poka-Yoke prevention: blocks inserting duplicate medicine code."""
        exp_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
        # MED1001 exists in seed data
        dup_med = Medicine(
            medicine_id=None,
            medicine_code="MED1001",
            medicine_name="Duplicate Para",
            category="Analgesic",
            manufacturer="Test Lab",
            batch_no="B202699",
            price=15.00,
            quantity=50,
            expiry_date=exp_date
        )

        ok, msg = self.med_service.add_medicine(dup_med)
        self.assertFalse(ok)
        self.assertIn("already exists", msg)

    def test_3_reject_negative_price(self):
        """Verifies Poka-Yoke prevention: blocks negative price inputs."""
        exp_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
        bad_med = Medicine(
            medicine_id=None,
            medicine_code="MED2002",
            medicine_name="Bad Price Med",
            category="Test",
            manufacturer="Test Lab",
            batch_no="B202600",
            price=-10.50,
            quantity=50,
            expiry_date=exp_date
        )

        errors = bad_med.validate()
        self.assertTrue(any("non-negative" in e for e in errors))

    def test_4_reject_negative_quantity(self):
        """Verifies Poka-Yoke prevention: blocks negative quantity inputs."""
        exp_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
        bad_med = Medicine(
            medicine_id=None,
            medicine_code="MED2003",
            medicine_name="Bad Qty Med",
            category="Test",
            manufacturer="Test Lab",
            batch_no="B202600",
            price=15.00,
            quantity=-5,
            expiry_date=exp_date
        )

        errors = bad_med.validate()
        self.assertTrue(any("non-negative" in e for e in errors))

    def test_5_reject_invalid_expiry_date(self):
        """Verifies Poka-Yoke prevention: blocks invalid YYYY-MM-DD date formats."""
        bad_med = Medicine(
            medicine_id=None,
            medicine_code="MED2004",
            medicine_name="Bad Date Med",
            category="Test",
            manufacturer="Test Lab",
            batch_no="B202600",
            price=15.00,
            quantity=50,
            expiry_date="2026-99-99"  # Invalid date
        )

        errors = bad_med.validate()
        self.assertTrue(any("YYYY-MM-DD" in e for e in errors))

    def test_6_retrieve_medicine(self):
        """Verifies retrieval of medicine records by ID and code."""
        med = self.med_service.get_medicine_by_code("MED1001")
        self.assertIsNotNone(med)
        self.assertEqual(med.medicine_code, "MED1001")

        fetched_by_id = self.med_service.get_medicine_by_id(med.medicine_id)
        self.assertIsNotNone(fetched_by_id)
        self.assertEqual(fetched_by_id.medicine_id, med.medicine_id)

    def test_7_update_medicine(self):
        """Verifies updating an existing medicine record."""
        med = self.med_service.get_medicine_by_code("MED1001")
        original_price = med.price
        med.price = original_price + 5.00
        med.quantity = 250

        ok, msg = self.med_service.update_medicine(med)
        self.assertTrue(ok, f"Update failed: {msg}")

        updated = self.med_service.get_medicine_by_code("MED1001")
        self.assertEqual(updated.price, original_price + 5.00)
        self.assertEqual(updated.quantity, 250)

    def test_8_delete_medicine(self):
        """Verifies deletion of an unreferenced medicine record."""
        exp_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
        temp_med = Medicine(
            medicine_id=None,
            medicine_code="MED9999",
            medicine_name="Temporary Medicine",
            category="Temp",
            manufacturer="Temp Lab",
            batch_no="TMP001",
            price=5.00,
            quantity=10,
            expiry_date=exp_date
        )
        self.med_service.add_medicine(temp_med)
        inserted = self.med_service.get_medicine_by_code("MED9999")

        ok, msg = self.med_service.delete_medicine(inserted.medicine_id)
        self.assertTrue(ok, f"Deletion failed: {msg}")

    def test_9_verify_deleted_record_absent(self):
        """Verifies that a deleted medicine record no longer exists in DB."""
        deleted = self.med_service.get_medicine_by_code("MED9999")
        self.assertIsNone(deleted)

    def test_10_verify_stock_status_logic(self):
        """Verifies stock status calculation logic."""
        exp = (datetime.now() + timedelta(days=100)).strftime("%Y-%m-%d")
        m_available = Medicine(1, "M1", "N1", "C", "M", "B", 10.0, 50, exp)
        m_low = Medicine(2, "M2", "N2", "C", "M", "B", 10.0, 8, exp)
        m_out = Medicine(3, "M3", "N3", "C", "M", "B", 10.0, 0, exp)

        self.assertEqual(m_available.stock_status, "Available")
        self.assertEqual(m_low.stock_status, "Low Stock")
        self.assertEqual(m_out.stock_status, "Out of Stock")

    def test_11_verify_expiry_status_logic(self):
        """Verifies expiry status calculation logic based on current system date."""
        today = datetime.now()
        valid_date = (today + timedelta(days=365)).strftime("%Y-%m-%d")
        expiring_soon_date = (today + timedelta(days=15)).strftime("%Y-%m-%d")
        expired_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")

        m_valid = Medicine(1, "M1", "N1", "C", "M", "B", 10.0, 50, valid_date)
        m_expiring = Medicine(2, "M2", "N2", "C", "M", "B", 10.0, 50, expiring_soon_date)
        m_expired = Medicine(3, "M3", "N3", "C", "M", "B", 10.0, 50, expired_date)

        self.assertEqual(m_valid.expiry_status, "Valid")
        self.assertEqual(m_expiring.expiry_status, "Expiring Soon")
        self.assertEqual(m_expired.expiry_status, "Expired")


if __name__ == "__main__":
    unittest.main()
