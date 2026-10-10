"""
Unit tests for Stage 1 Database Foundation and Core Services.
Tests schema creation, indexes, user auth, medicine CRUD, and parameterized query safety.
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from database.db import Database
from database.schema import init_db
from models.medicine import Medicine
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from services.search_service import SearchService


class TestDatabaseFoundation(unittest.TestCase):
    """Test suite for database layer, schema, indexes, and service business logic."""

    def setUp(self):
        """Sets up a temporary SQLite database file for isolated testing."""
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)

        # Initialize schema and seed data on test DB
        self.db = init_db(self.temp_db_path)
        self.auth_service = AuthService(self.db)
        self.med_service = MedicineService(self.db)
        self.search_service = SearchService(self.db)

    def tearDown(self):
        """Cleans up the temporary database file after tests complete."""
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except PermissionError:
                pass

    def test_1_database_initialization(self):
        """Verifies that all required tables exist in the database schema."""
        rows = self.db.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [r["name"] for r in rows]
        
        self.assertIn("users", table_names)
        self.assertIn("medicines", table_names)
        self.assertIn("sales", table_names)
        self.assertIn("sale_items", table_names)

    def test_2_user_creation_and_login(self):
        """Verifies user creation, password hashing, and login authentication."""
        # Test default seed users
        admin_user, msg = self.auth_service.authenticate("admin", "admin123")
        self.assertIsNotNone(admin_user)
        self.assertEqual(admin_user.role, "Admin")

        pharma_user, msg = self.auth_service.authenticate("pharmacist", "pharma123")
        self.assertIsNotNone(pharma_user)
        self.assertEqual(pharma_user.role, "Pharmacist")

        # Test invalid credentials
        bad_user, msg = self.auth_service.authenticate("admin", "wrongpass")
        self.assertIsNone(bad_user)
        self.assertIn("Invalid", msg)

        # Test user creation
        ok, msg = self.auth_service.create_user("testuser", "test1234", "Pharmacist")
        self.assertTrue(ok)

        new_user, msg = self.auth_service.authenticate("testuser", "test1234")
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user.username, "testuser")

    def test_3_medicine_insertion(self):
        """Verifies insertion of new medicine with validation checks."""
        exp_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
        new_med = Medicine(
            medicine_id=None,
            medicine_code="MED9999",
            medicine_name="Test Medicine 500mg",
            category="Testing",
            manufacturer="Test Lab",
            batch_no="TEST001",
            price=25.50,
            quantity=100,
            expiry_date=exp_date
        )

        ok, msg = self.med_service.add_medicine(new_med)
        self.assertTrue(ok, f"Insertion failed: {msg}")

        inserted = self.med_service.get_medicine_by_code("MED9999")
        self.assertIsNotNone(inserted)
        self.assertEqual(inserted.medicine_name, "Test Medicine 500mg")
        self.assertEqual(inserted.price, 25.50)
        self.assertEqual(inserted.quantity, 100)

    def test_4_medicine_retrieval(self):
        """Verifies medicine fetching by ID, code, and list retrieval."""
        all_meds = self.med_service.get_all_medicines()
        self.assertGreater(len(all_meds), 0)

        first_med = all_meds[0]
        fetched_by_id = self.med_service.get_medicine_by_id(first_med.medicine_id)
        self.assertIsNotNone(fetched_by_id)
        self.assertEqual(fetched_by_id.medicine_code, first_med.medicine_code)

        fetched_by_code = self.med_service.get_medicine_by_code(first_med.medicine_code)
        self.assertIsNotNone(fetched_by_code)
        self.assertEqual(fetched_by_code.medicine_id, first_med.medicine_id)

    def test_5_medicine_update(self):
        """Verifies medicine attribute modification and update persistence."""
        exp_date = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")
        med = Medicine(
            medicine_id=None,
            medicine_code="MED8888",
            medicine_name="Original Name",
            category="Analgesic",
            manufacturer="Original Lab",
            batch_no="BATCH88",
            price=10.00,
            quantity=50,
            expiry_date=exp_date
        )
        self.med_service.add_medicine(med)

        inserted = self.med_service.get_medicine_by_code("MED8888")
        inserted.medicine_name = "Updated Name"
        inserted.price = 15.75
        inserted.quantity = 75

        ok, msg = self.med_service.update_medicine(inserted)
        self.assertTrue(ok, f"Update failed: {msg}")

        updated = self.med_service.get_medicine_by_code("MED8888")
        self.assertEqual(updated.medicine_name, "Updated Name")
        self.assertEqual(updated.price, 15.75)
        self.assertEqual(updated.quantity, 75)

    def test_6_medicine_deletion(self):
        """Verifies record deletion from database."""
        exp_date = (datetime.now() + timedelta(days=200)).strftime("%Y-%m-%d")
        med = Medicine(
            medicine_id=None,
            medicine_code="MED7777",
            medicine_name="ToDelete",
            category="Temp",
            manufacturer="Temp",
            batch_no="TMP",
            price=5.00,
            quantity=10,
            expiry_date=exp_date
        )
        self.med_service.add_medicine(med)
        inserted = self.med_service.get_medicine_by_code("MED7777")
        
        ok, msg = self.med_service.delete_medicine(inserted.medicine_id)
        self.assertTrue(ok, f"Deletion failed: {msg}")

        deleted = self.med_service.get_medicine_by_code("MED7777")
        self.assertIsNone(deleted)

    def test_7_indexed_columns_existence(self):
        """Verifies that all required Q13 SQLite B-Tree indexes exist in the database."""
        rows = self.db.fetch_all("SELECT name FROM sqlite_master WHERE type='index'")
        idx_names = [r["name"] for r in rows]

        self.assertIn("idx_medicines_name", idx_names)
        self.assertIn("idx_medicines_category", idx_names)
        self.assertIn("idx_medicines_manufacturer", idx_names)
        self.assertIn("idx_medicines_expiry", idx_names)
        self.assertIn("idx_medicines_code", idx_names)

    def test_8_parameterized_query_execution(self):
        """Verifies parameterized query execution, multi-filter search, and SQL injection safety."""
        # Search for Paracetamol using parameterized query
        results, exec_time = self.search_service.search_medicines(query_text="Paracetamol")
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertIn("Paracetamol", m.medicine_name)

        # SQL Injection attempt safely handled
        injection_text = "' OR '1'='1"
        results_inj, exec_time_inj = self.search_service.search_medicines(query_text=injection_text)
        # Should return no results safely because no medicine has that exact literal string in name/code
        self.assertEqual(len(results_inj), 0)


if __name__ == "__main__":
    unittest.main()
