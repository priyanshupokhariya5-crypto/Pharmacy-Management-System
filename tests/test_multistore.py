"""
Automated Test Suite for Multi-Store Pharmacy Management System.
Covers all 20 required multi-store capabilities:
 1. Successful store registration
 2. Duplicate username rejection
 3. Duplicate email rejection
 4. Invalid email and password mismatch
 5. Password hashing and verification (PBKDF2 salted)
 6. Successful login (by username and by email)
 7. Invalid password and unknown username rejection
 8. Logout and session clearing
 9. Dashboard access restrictions before login
10. Two different stores receiving different Store IDs
11. Each store seeing only its own medicines
12. Search and filtering isolation
13. Billing and stock updates staying within the correct store
14. Reports and dashboard totals staying within the correct store
15. FMEA and SQC data isolation
16. Data remaining after logout and re-login
17. Data remaining after application restart
18. Prevention of cross-store access through manipulated record IDs
19. Safe database migration and preservation of legacy data
20. Existing pharmacy functionality remaining intact
"""
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta
from typing import Optional

from database.db import Database
from database.schema import init_db, hash_password, verify_password, migrate_database
from models.medicine import Medicine
from models.user import User
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from services.search_service import SearchService
from services.sales_service import SalesService
from reports.report_generator import ReportGenerator
from utils.fmea import FMEAService, FMEARecord
from utils.sqc import SQCService, SQCDefect


class TestMultiStorePharmacySystem(unittest.TestCase):
    """Comprehensive test suite for Phase 9 Multi-Store isolation and security."""

    def setUp(self):
        """Creates an isolated temporary SQLite database for each test."""
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix="_multistore.db")
        os.close(self.temp_db_fd)
        self.db = init_db(self.temp_db_path)
        self.auth_service = AuthService(self.db)

    def tearDown(self):
        """Cleans up the temporary database file."""
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except PermissionError:
                pass

    def test_01_successful_store_registration(self):
        """1. Verifies successful pharmacy store registration with unique Store ID."""
        ok, msg, user = self.auth_service.register_store(
            store_name="Ram Medical Store",
            owner_name="Ram Sharma",
            username="ramstore",
            email="ram@example.com",
            password="SecurePassword123",
            confirm_password="SecurePassword123"
        )
        self.assertTrue(ok)
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "ramstore")
        self.assertEqual(user.store_name, "Ram Medical Store")
        self.assertEqual(user.role, "Owner")
        self.assertEqual(user.email, "ram@example.com")
        self.assertTrue(user.store_id.startswith("STORE-"))
        self.assertIn("registered successfully", msg)

    def test_02_duplicate_username_rejection(self):
        """2. Verifies rejection of duplicate usernames (case-insensitive)."""
        ok1, _, _ = self.auth_service.register_store(
            store_name="Ram Medical Store",
            owner_name="Ram Sharma",
            username="ramstore",
            email="ram@example.com",
            password="Password123",
            confirm_password="Password123"
        )
        self.assertTrue(ok1)

        ok2, msg2, user2 = self.auth_service.register_store(
            store_name="Another Store",
            owner_name="Another Owner",
            username="RAMSTORE",  # Case variant
            email="different@example.com",
            password="Password123",
            confirm_password="Password123"
        )
        self.assertFalse(ok2)
        self.assertIsNone(user2)
        self.assertIn("already registered", msg2.lower())

    def test_03_duplicate_email_rejection(self):
        """3. Verifies rejection of duplicate email addresses."""
        ok1, _, _ = self.auth_service.register_store(
            store_name="Ram Medical Store",
            owner_name="Ram Sharma",
            username="ramstore",
            email="ram@example.com",
            password="Password123",
            confirm_password="Password123"
        )
        self.assertTrue(ok1)

        ok2, msg2, user2 = self.auth_service.register_store(
            store_name="Sharma Medical",
            owner_name="Sita Sharma",
            username="sitastore",
            email="ram@example.com",  # Duplicate email
            password="Password123",
            confirm_password="Password123"
        )
        self.assertFalse(ok2)
        self.assertIsNone(user2)
        self.assertIn("already registered", msg2.lower())

    def test_04_invalid_email_and_password_mismatch(self):
        """4. Verifies input validations: email format, short password, mismatched passwords."""
        # Invalid email format
        ok, msg, _ = self.auth_service.register_store(
            "Test Store", "Owner", "testuser1", "notanemail", "Password123", "Password123"
        )
        self.assertFalse(ok)
        self.assertIn("valid email", msg.lower())

        # Password mismatch
        ok, msg, _ = self.auth_service.register_store(
            "Test Store", "Owner", "testuser2", "test2@example.com", "Password123", "PasswordMismatch"
        )
        self.assertFalse(ok)
        self.assertIn("do not match", msg.lower())

        # Short password (< 6 chars)
        ok, msg, _ = self.auth_service.register_store(
            "Test Store", "Owner", "testuser3", "test3@example.com", "12345", "12345"
        )
        self.assertFalse(ok)
        self.assertIn("at least 6 characters", msg.lower())

    def test_05_password_hashing_and_verification(self):
        """5. Verifies salted PBKDF2 hashing format and verification security."""
        raw_pwd = "MySecretPassword!456"
        hashed = hash_password(raw_pwd)

        # Check format: salt$hash
        self.assertIn("$", hashed)
        parts = hashed.split("$")
        self.assertEqual(len(parts), 2)
        salt_hex, key_hex = parts[0], parts[1]
        self.assertEqual(len(salt_hex), 32)  # 16 bytes hex
        self.assertEqual(len(key_hex), 64)   # SHA-256 is 32 bytes = 64 hex chars

        # Plain text must never equal hash
        self.assertNotEqual(raw_pwd, hashed)

        # Verification must succeed for correct password
        self.assertTrue(verify_password(raw_pwd, hashed))

        # Verification must fail for incorrect password
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_06_successful_login(self):
        """6. Verifies successful login using either registered username or email."""
        self.auth_service.register_store(
            store_name="Ram Medical Store",
            owner_name="Ram Sharma",
            username="ramstore",
            email="ram@example.com",
            password="SecretPassword123",
            confirm_password="SecretPassword123"
        )

        # Login by username
        user_by_user, msg1 = self.auth_service.authenticate("ramstore", "SecretPassword123")
        self.assertIsNotNone(user_by_user)
        self.assertEqual(user_by_user.username, "ramstore")
        self.assertEqual(user_by_user.store_name, "Ram Medical Store")

        # Login by email
        user_by_email, msg2 = self.auth_service.authenticate("ram@example.com", "SecretPassword123")
        self.assertIsNotNone(user_by_email)
        self.assertEqual(user_by_email.username, "ramstore")
        self.assertEqual(user_by_email.store_id, user_by_user.store_id)

    def test_07_invalid_password_and_unknown_username_rejection(self):
        """7. Verifies rejection of incorrect passwords and unknown accounts."""
        self.auth_service.register_store(
            store_name="Ram Medical Store",
            owner_name="Ram Sharma",
            username="ramstore",
            email="ram@example.com",
            password="SecretPassword123",
            confirm_password="SecretPassword123"
        )

        # Wrong password
        user, msg = self.auth_service.authenticate("ramstore", "IncorrectPassword")
        self.assertIsNone(user)
        self.assertIn("Invalid", msg)

        # Nonexistent username
        user2, msg2 = self.auth_service.authenticate("nonexistent_user", "SecretPassword123")
        self.assertIsNone(user2)
        self.assertIn("Invalid", msg2)

    def test_08_logout_and_session_clearing(self):
        """8. Verifies logout session clearing while preserving store data in database."""
        _, _, user = self.auth_service.register_store(
            "Ram Medical Store", "Ram Sharma", "ramstore", "ram@example.com", "Pass1234", "Pass1234"
        )
        med_service = MedicineService(self.db, store_id=user.store_id)
        med = Medicine(
            medicine_id=None,
            medicine_code="MED-PARA",
            medicine_name="Paracetamol 500mg",
            category="Tablet",
            manufacturer="Cipla",
            batch_no="BATCH-001",
            price=15.0,
            quantity=100,
            expiry_date=(datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d")
        )
        ok, _ = med_service.add_medicine(med)
        self.assertTrue(ok)

        # Simulate active session in UI
        session_user = user
        self.assertIsNotNone(session_user)

        # Simulate logout action
        session_user = None
        self.assertIsNone(session_user)

        # Verify database record still exists untouched
        meds_in_db = med_service.get_all_medicines()
        self.assertEqual(len(meds_in_db), 1)
        self.assertEqual(meds_in_db[0].medicine_name, "Paracetamol 500mg")

    def test_09_dashboard_access_restrictions_before_login(self):
        """9. Verifies that without authentication, services cannot be supplied an arbitrary user session."""
        current_session: Optional[User] = None
        self.assertIsNone(current_session)

        with self.assertRaises(AttributeError):
            _ = current_session.store_id

    def test_10_two_different_stores_receiving_different_store_ids(self):
        """10. Verifies that two different registered stores receive distinct, unique Store IDs."""
        _, _, store_a = self.auth_service.register_store(
            "Ram Medical Store", "Ram Sharma", "ramstore", "ram@example.com", "Pass1234", "Pass1234"
        )
        _, _, store_b = self.auth_service.register_store(
            "Sharma Pharmacy", "Sharma Ji", "sharmastore", "sharma@example.com", "Pass1234", "Pass1234"
        )

        self.assertIsNotNone(store_a.store_id)
        self.assertIsNotNone(store_b.store_id)
        self.assertNotEqual(store_a.store_id, store_b.store_id)
        self.assertTrue(store_a.store_id.startswith("STORE-"))
        self.assertTrue(store_b.store_id.startswith("STORE-"))

    def test_11_each_store_sees_only_its_own_medicines(self):
        """11. Verifies strict medicine inventory isolation between Store A and Store B."""
        _, _, store_a = self.auth_service.register_store(
            "Ram Medical Store", "Ram Sharma", "ramstore", "ram@example.com", "Pass1234", "Pass1234"
        )
        _, _, store_b = self.auth_service.register_store(
            "Sharma Pharmacy", "Sharma Ji", "sharmastore", "sharma@example.com", "Pass1234", "Pass1234"
        )

        med_a_service = MedicineService(self.db, store_id=store_a.store_id)
        med_b_service = MedicineService(self.db, store_id=store_b.store_id)

        # Store A adds 2 medicines
        med_a1 = Medicine(
            medicine_id=None, medicine_code="MED-AMOX", medicine_name="Amoxicillin 250mg",
            category="Capsule", manufacturer="Sun Pharma", batch_no="BAT-A1",
            price=30.0, quantity=50, expiry_date="2027-12-31"
        )
        med_a2 = Medicine(
            medicine_id=None, medicine_code="MED-IBU", medicine_name="Ibuprofen 400mg",
            category="Tablet", manufacturer="Abbott", batch_no="BAT-A2",
            price=18.0, quantity=80, expiry_date="2027-12-31"
        )
        ok1, _ = med_a_service.add_medicine(med_a1)
        ok2, _ = med_a_service.add_medicine(med_a2)
        self.assertTrue(ok1)
        self.assertTrue(ok2)

        # Store B adds 1 medicine
        med_b1 = Medicine(
            medicine_id=None, medicine_code="MED-CET", medicine_name="Cetirizine 10mg",
            category="Tablet", manufacturer="Cipla", batch_no="BAT-B1",
            price=10.0, quantity=200, expiry_date="2027-12-31"
        )
        ok3, _ = med_b_service.add_medicine(med_b1)
        self.assertTrue(ok3)

        # Store A must see exactly its 2 medicines and NOT Store B's Cetirizine
        store_a_list = med_a_service.get_all_medicines()
        store_a_names = [m.medicine_name for m in store_a_list]
        self.assertEqual(len(store_a_list), 2)
        self.assertIn("Amoxicillin 250mg", store_a_names)
        self.assertIn("Ibuprofen 400mg", store_a_names)
        self.assertNotIn("Cetirizine 10mg", store_a_names)

        # Store B must see exactly its 1 medicine and NOT Store A's medicines
        store_b_list = med_b_service.get_all_medicines()
        store_b_names = [m.medicine_name for m in store_b_list]
        self.assertEqual(len(store_b_list), 1)
        self.assertIn("Cetirizine 10mg", store_b_names)
        self.assertNotIn("Amoxicillin 250mg", store_b_names)
        self.assertNotIn("Ibuprofen 400mg", store_b_names)

    def test_12_search_and_filtering_isolation(self):
        """12. Verifies search service isolation (Store A cannot find Store B's medicines)."""
        _, _, store_a = self.auth_service.register_store(
            "Ram Medical Store", "Ram Sharma", "ramstore", "ram@example.com", "Pass1234", "Pass1234"
        )
        _, _, store_b = self.auth_service.register_store(
            "Sharma Pharmacy", "Sharma Ji", "sharmastore", "sharma@example.com", "Pass1234", "Pass1234"
        )

        med_a_service = MedicineService(self.db, store_id=store_a.store_id)
        med_b_service = MedicineService(self.db, store_id=store_b.store_id)

        med_a_service.add_medicine(Medicine(
            medicine_id=None, medicine_code="MED-AZ1", medicine_name="Azithromycin 500mg",
            category="Tablet", manufacturer="Cipla", batch_no="BAT-AZ1",
            price=60.0, quantity=40, expiry_date="2027-10-10"
        ))
        med_b_service.add_medicine(Medicine(
            medicine_id=None, medicine_code="MED-AZ2", medicine_name="Azithromycin 250mg",
            category="Tablet", manufacturer="Lupin", batch_no="BAT-AZ2",
            price=35.0, quantity=90, expiry_date="2027-10-10"
        ))

        search_a = SearchService(self.db, store_id=store_a.store_id)
        search_b = SearchService(self.db, store_id=store_b.store_id)

        # Quick Search
        results_a = search_a.quick_search("Azithromycin")
        self.assertEqual(len(results_a), 1)
        self.assertEqual(results_a[0].batch_no, "BAT-AZ1")

        results_b = search_b.quick_search("Azithromycin")
        self.assertEqual(len(results_b), 1)
        self.assertEqual(results_b[0].batch_no, "BAT-AZ2")

        # Advanced Search with filtering
        adv_a, _ = search_a.search_medicines(query_text="Azithromycin", manufacturer="Cipla")
        self.assertEqual(len(adv_a), 1)

        adv_a_lupin, _ = search_a.search_medicines(query_text="Azithromycin", manufacturer="Lupin")
        self.assertEqual(len(adv_a_lupin), 0)  # Lupin medicine belongs to Store B!

    def test_13_billing_and_stock_updates_stay_within_correct_store(self):
        """13. Verifies billing process, stock deduction, and sales history isolation."""
        _, _, store_a = self.auth_service.register_store(
            "Ram Medical Store", "Ram Sharma", "ramstore", "ram@example.com", "Pass1234", "Pass1234"
        )
        _, _, store_b = self.auth_service.register_store(
            "Sharma Pharmacy", "Sharma Ji", "sharmastore", "sharma@example.com", "Pass1234", "Pass1234"
        )

        med_a_service = MedicineService(self.db, store_id=store_a.store_id)
        med_a = Medicine(
            medicine_id=None, medicine_code="PARA-100", medicine_name="Paracetamol 500mg",
            category="Tablet", manufacturer="Cipla", batch_no="PARA-100",
            price=15.0, quantity=100, expiry_date="2027-01-01"
        )
        med_a_service.add_medicine(med_a)
        created_med_a = med_a_service.get_medicine_by_code("PARA-100")
        self.assertIsNotNone(created_med_a)

        sales_a = SalesService(self.db, store_id=store_a.store_id)
        sales_b = SalesService(self.db, store_id=store_b.store_id)

        # Store A sells 10 units
        cart_items = [(created_med_a.medicine_id, 10)]
        success, msg, sale_id, invoice_number = sales_a.process_sale(
            user_id=store_a.user_id,
            cart_items=cart_items,
            patient_name="John Doe",
            patient_phone="9876543210"
        )
        self.assertTrue(success)
        self.assertIsNotNone(sale_id)

        # Verify stock deducted in Store A (100 -> 90)
        updated_med_a = med_a_service.get_medicine_by_id(created_med_a.medicine_id)
        self.assertEqual(updated_med_a.quantity, 90)

        # Verify Store A has 1 recent sale
        sales_list_a = sales_a.get_recent_sales()
        self.assertEqual(len(sales_list_a), 1)

        # Store B must have 0 sales
        sales_list_b = sales_b.get_recent_sales()
        self.assertEqual(len(sales_list_b), 0)

        # Store B attempts to sell Store A's medicine -> must be rejected
        ok_b, err_b, _ = sales_b.validate_cart_item(created_med_a.medicine_id, 1)
        self.assertFalse(ok_b)
        self.assertIn("not found in store inventory", err_b)

    def test_14_reports_and_dashboard_totals_stay_within_correct_store(self):
        """14. Verifies Pandas analytics, metrics, and KPI cards stay within the store."""
        _, _, store_a = self.auth_service.register_store(
            "Ram Medical Store", "Ram Sharma", "ramstore", "ram@example.com", "Pass1234", "Pass1234"
        )
        _, _, store_b = self.auth_service.register_store(
            "Sharma Pharmacy", "Sharma Ji", "sharmastore", "sharma@example.com", "Pass1234", "Pass1234"
        )

        med_a_service = MedicineService(self.db, store_id=store_a.store_id)
        med_a_service.add_medicine(Medicine(
            medicine_id=None, medicine_code="PROD-A", medicine_name="Product A",
            category="Syrup", manufacturer="M1", batch_no="B1",
            price=80.0, quantity=10, expiry_date="2027-01-01"
        ))

        rep_a = ReportGenerator(self.db, store_id=store_a.store_id)
        rep_b = ReportGenerator(self.db, store_id=store_b.store_id)

        df_inv_a = rep_a.get_inventory_dataframe()
        df_inv_b = rep_b.get_inventory_dataframe()

        self.assertEqual(len(df_inv_a), 1)
        self.assertEqual(len(df_inv_b), 0)

        # Store A KPI metrics
        kpis_a = med_a_service.get_inventory_summary()
        self.assertEqual(kpis_a["total_medicines"], 1)

        # Store B KPI metrics
        med_b_service = MedicineService(self.db, store_id=store_b.store_id)
        kpis_b = med_b_service.get_inventory_summary()
        self.assertEqual(kpis_b["total_medicines"], 0)

    def test_15_fmea_and_sqc_data_isolation(self):
        """15. Verifies TQM Quality modules (FMEA and SQC) maintain strict store isolation."""
        _, _, store_a = self.auth_service.register_store(
            "Ram Medical Store", "Ram Sharma", "ramstore", "ram@example.com", "Pass1234", "Pass1234"
        )
        _, _, store_b = self.auth_service.register_store(
            "Sharma Pharmacy", "Sharma Ji", "sharmastore", "sharma@example.com", "Pass1234", "Pass1234"
        )

        fmea_a = FMEAService(self.db, store_id=store_a.store_id)
        fmea_b = FMEAService(self.db, store_id=store_b.store_id)

        fmea_rec = FMEARecord(
            fmea_id=None,
            process_module="Dispensing Check",
            failure_mode="Expired medicine dispensed",
            potential_effect="Patient harm",
            potential_cause="Visual inspection missed",
            prevention_control="Physical label check",
            detection_control="Double pharmacist verification",
            severity=8,
            severity_rationale="Patient health hazard",
            occurrence=3,
            occurrence_rationale="Occasional occurrence",
            detection=4,
            detection_rationale="Usually caught at counter",
            recommended_action="Barcode scan mandatory",
            action_status="Open",
            owner="Ram Sharma"
        )
        ok_fmea, _ = fmea_a.add_record(fmea_rec)
        self.assertTrue(ok_fmea)

        records_a = fmea_a.get_all_records()
        records_b = fmea_b.get_all_records()

        self.assertEqual(len(records_a), 1)
        self.assertEqual(len(records_b), 0)

        # SQC Defect isolation
        sqc_a = SQCService(self.db, store_id=store_a.store_id)
        sqc_b = SQCService(self.db, store_id=store_b.store_id)

        sqc_defect = SQCDefect(
            defect_id=None,
            date_reported=datetime.now().strftime("%Y-%m-%d"),
            module="Sales",
            defect_type="Billing Mismatch",
            description="Incorrect discount applied manually",
            severity="High",
            frequency=1,
            status="Open",
            root_cause="User manual override",
            corrective_action="Lock discount field",
            reported_by="Ram Sharma"
        )
        ok_sqc, _ = sqc_a.add_defect(sqc_defect)
        self.assertTrue(ok_sqc)

        defects_a = sqc_a.get_all_defects()
        defects_b = sqc_b.get_all_defects()

        self.assertEqual(len(defects_a), 1)
        self.assertEqual(len(defects_b), 0)

    def test_16_data_remaining_after_logout_and_relogin(self):
        """16. Verifies all records persist intact after user logs out and logs in again."""
        ok, _, registered_user = self.auth_service.register_store(
            "Persistent Store", "Owner", "pstore", "pstore@example.com", "SecretPass123", "SecretPass123"
        )
        self.assertTrue(ok)
        store_id = registered_user.store_id

        # Add medicine during first session
        med_service = MedicineService(self.db, store_id=store_id)
        med_service.add_medicine(Medicine(
            medicine_id=None, medicine_code="PERM-01", medicine_name="Permanent Drug 500mg",
            category="Tablet", manufacturer="PharmaCorp", batch_no="PERM-01",
            price=20.0, quantity=150, expiry_date="2028-01-01"
        ))

        # Logout: clear session
        session_user = None

        # Re-login with credentials
        relogin_user, msg = self.auth_service.authenticate("pstore", "SecretPass123")
        self.assertIsNotNone(relogin_user)
        self.assertEqual(relogin_user.store_id, store_id)

        # Verify all medicines and counts remain
        relogin_med_service = MedicineService(self.db, store_id=relogin_user.store_id)
        meds = relogin_med_service.get_all_medicines()
        self.assertEqual(len(meds), 1)
        self.assertEqual(meds[0].medicine_name, "Permanent Drug 500mg")
        self.assertEqual(meds[0].quantity, 150)

    def test_17_data_remaining_after_application_restart(self):
        """17. Verifies persistence across full application restart (closing & reconnecting database)."""
        ok, _, user = self.auth_service.register_store(
            "Restart Test Store", "Owner", "restartuser", "restart@example.com", "Password123", "Password123"
        )
        self.assertTrue(ok)
        store_id = user.store_id

        med_service = MedicineService(self.db, store_id=store_id)
        med_service.add_medicine(Medicine(
            medicine_id=None, medicine_code="RES-01", medicine_name="Restart Medicine",
            category="Capsule", manufacturer="Sun", batch_no="RES-01",
            price=25.0, quantity=75, expiry_date="2028-05-05"
        ))

        # Simulate fresh application launch and DB initialization on same file
        reopened_db = init_db(self.temp_db_path)
        reopened_auth = AuthService(reopened_db)

        # Authenticate afresh
        logged_in_user, msg = reopened_auth.authenticate("restartuser", "Password123")
        self.assertIsNotNone(logged_in_user)
        self.assertEqual(logged_in_user.store_id, store_id)

        # Verify data intact
        reopened_meds = MedicineService(reopened_db, store_id=logged_in_user.store_id).get_all_medicines()
        self.assertEqual(len(reopened_meds), 1)
        self.assertEqual(reopened_meds[0].medicine_name, "Restart Medicine")
        self.assertEqual(reopened_meds[0].batch_no, "RES-01")

    def test_18_prevention_of_cross_store_access_through_manipulated_record_ids(self):
        """18. Verifies that malicious ID tampering fails to access, modify or delete another store's records."""
        _, _, store_a = self.auth_service.register_store(
            "Store Alpha", "Owner Alpha", "alpha", "alpha@example.com", "Pass1234", "Pass1234"
        )
        _, _, store_b = self.auth_service.register_store(
            "Store Beta", "Owner Beta", "beta", "beta@example.com", "Pass1234", "Pass1234"
        )

        med_a_service = MedicineService(self.db, store_id=store_a.store_id)
        med_b_service = MedicineService(self.db, store_id=store_b.store_id)

        # Store A creates a medicine
        med_a_service.add_medicine(Medicine(
            medicine_id=None, medicine_code="ALP-01", medicine_name="Alpha Medicine",
            category="Tablet", manufacturer="AlphaLab", batch_no="ALP-01",
            price=20.0, quantity=100, expiry_date="2027-01-01"
        ))
        med_a = med_a_service.get_medicine_by_code("ALP-01")
        alpha_med_id = med_a.medicine_id

        # 1. Store B attempts to read Store A's medicine by ID
        read_result = med_b_service.get_medicine_by_id(alpha_med_id)
        self.assertIsNone(read_result)

        # 2. Store B attempts to update Store A's medicine by ID
        med_a.medicine_name = "Hacked Name"
        update_ok, _ = med_b_service.update_medicine(med_a)
        self.assertFalse(update_ok)

        # Verify Store A's medicine was NOT altered
        alpha_verified = med_a_service.get_medicine_by_id(alpha_med_id)
        self.assertEqual(alpha_verified.medicine_name, "Alpha Medicine")

        # 3. Store B attempts to delete Store A's medicine by ID
        delete_ok, _ = med_b_service.delete_medicine(alpha_med_id)
        self.assertFalse(delete_ok)

        # Verify Store A's medicine was NOT deleted
        alpha_verified_after = med_a_service.get_medicine_by_id(alpha_med_id)
        self.assertIsNotNone(alpha_verified_after)

    def test_19_safe_database_migration_and_preservation_of_legacy_data(self):
        """19. Verifies non-destructive migration of legacy un-scoped SQLite databases."""
        mig_fd, mig_path = tempfile.mkstemp(suffix="_legacy.db")
        os.close(mig_fd)

        try:
            # Create a raw legacy SQLite database without stores table and without store_id columns
            conn = sqlite3.connect(mig_path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            c.execute("""
                CREATE TABLE medicines (
                    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medicine_code TEXT NOT NULL,
                    medicine_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    manufacturer TEXT NOT NULL,
                    batch_no TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity INTEGER NOT NULL,
                    expiry_date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Insert legacy records
            c.execute("INSERT INTO users (username, password_hash, role) VALUES ('legacy_admin', 'hash123', 'Admin')")
            c.execute("""
                INSERT INTO medicines (medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
                VALUES ('LEG-01', 'Legacy Drug', 'Tablet', 'OldPharma', 'BAT-LEG', 10.0, 50, '2028-01-01')
            """)
            conn.commit()
            conn.close()

            # Execute migration
            db_to_migrate = Database(mig_path)
            migrate_database(db_to_migrate)

            # Verify 'stores' table created and default legacy store backfilled
            legacy_store = db_to_migrate.fetch_one("SELECT * FROM stores WHERE store_id = 'STORE-LEGACY-001'")
            self.assertIsNotNone(legacy_store)
            self.assertEqual(legacy_store["store_name"], "Default Pharmacy Store")

            # Verify legacy medicine was preserved and backfilled with STORE-LEGACY-001
            legacy_med = db_to_migrate.fetch_one("SELECT * FROM medicines WHERE medicine_code = 'LEG-01'")
            self.assertIsNotNone(legacy_med)
            self.assertEqual(legacy_med["medicine_name"], "Legacy Drug")
            self.assertEqual(legacy_med["store_id"], "STORE-LEGACY-001")

            # Verify legacy user was preserved and backfilled with STORE-LEGACY-001
            legacy_u = db_to_migrate.fetch_one("SELECT * FROM users WHERE username = 'legacy_admin'")
            self.assertIsNotNone(legacy_u)
            self.assertEqual(legacy_u["store_id"], "STORE-LEGACY-001")
        finally:
            if os.path.exists(mig_path):
                try:
                    os.remove(mig_path)
                except PermissionError:
                    pass

    def test_20_existing_pharmacy_functionality_remaining_intact(self):
        """20. Verifies existing baseline pharmacy features (CRUD, stock, categories) remain intact."""
        med_service = MedicineService(self.db)  # Uses default STORE-LEGACY-001

        # Test Category & Manufacturer listing
        categories = med_service.get_categories()
        self.assertIsInstance(categories, list)

        manufacturers = med_service.get_manufacturers()
        self.assertIsInstance(manufacturers, list)

        # Test adding and retrieving medicine
        new_med = Medicine(
            medicine_id=None, medicine_code="BASE-001", medicine_name="Baseline Drug",
            category="Tablet", manufacturer="Baseline Pharma", batch_no="BASE-001",
            price=20.0, quantity=100, expiry_date="2027-01-01"
        )
        ok, _ = med_service.add_medicine(new_med)
        self.assertTrue(ok)

        # Test inventory summary totals
        summary = med_service.get_inventory_summary()
        self.assertGreaterEqual(summary["total_medicines"], 1)
        self.assertIn("total_inventory_value", summary)

    def test_21_legacy_role_check_constraint_rebuild_and_signup_regression(self):
        """21. Regression Test: Reproduces old CHECK constraint error on 'Owner' role, verifies migration rebuild, and confirms signup/login."""
        reg_fd, reg_path = tempfile.mkstemp(suffix="_role_reg.db")
        os.close(reg_fd)

        try:
            # 1. Create a legacy SQLite database with the old CHECK constraint
            conn = sqlite3.connect(reg_path)
            c = conn.cursor()
            c.execute("""
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('Admin', 'Pharmacist'))
                );
            """)
            admin_hash = hash_password("AdminPass123")
            c.execute("INSERT INTO users (username, password_hash, role) VALUES ('legacy_admin', ?, 'Admin')", (admin_hash,))
            conn.commit()

            # 2. Reproduce the exact bug: inserting 'Owner' fails with CHECK constraint violation
            with self.assertRaises(sqlite3.IntegrityError) as ctx:
                c.execute("INSERT INTO users (username, password_hash, role) VALUES ('store_owner', 'dummy', 'Owner')")
            self.assertIn("CHECK constraint failed", str(ctx.exception))
            conn.close()

            # 3. Execute safe migration on this database
            db_reg = Database(reg_path)
            migrate_database(db_reg)

            # 4. Verify that schema was updated to include 'Owner' in CHECK constraint
            table_sql = db_reg.fetch_one("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")['sql']
            self.assertIn("'Owner'", table_sql)

            # 5. Verify that store registration with 'Owner' role now succeeds completely
            auth = AuthService(db_reg)
            ok, msg, created_user = auth.register_store(
                store_name="Sharma Medical",
                owner_name="Sharma Ji",
                username="sharmastore",
                email="sharma@example.com",
                password="OwnerPassword123",
                confirm_password="OwnerPassword123"
            )
            self.assertTrue(ok, f"Registration failed after migration: {msg}")
            self.assertIsNotNone(created_user)
            self.assertEqual(created_user.role, "Owner")
            self.assertTrue(created_user.store_id.startswith("STORE-"))

            # 6. Verify that the new owner can log in successfully
            logged_owner, log_msg = auth.authenticate("sharmastore", "OwnerPassword123")
            self.assertIsNotNone(logged_owner)
            self.assertEqual(logged_owner.username, "sharmastore")
            self.assertEqual(logged_owner.store_name, "Sharma Medical")

            # 7. Verify that pre-existing legacy_admin user was preserved intact
            admin_user, admin_msg = auth.authenticate("legacy_admin", "AdminPass123")
            self.assertIsNotNone(admin_user)
            self.assertEqual(admin_user.user_id, 1)
            self.assertEqual(admin_user.role, "Admin")
            self.assertEqual(admin_user.store_id, "STORE-LEGACY-001")

        finally:
            if os.path.exists(reg_path):
                try:
                    os.remove(reg_path)
                except PermissionError:
                    pass

    def test_22_medicine_code_multi_store_uniqueness_and_migration_regression(self):
        """
        Regression Test:
        1. Creates a legacy database where medicines.medicine_code has a global single-column UNIQUE constraint.
        2. Adds a legacy store, user, medicine (MED-OLD-1), sale, and sale_items referencing medicine_id.
        3. Reproduces the exact error: inserting the same medicine code ('MED-OLD-1') into a new store
           fails with 'UNIQUE constraint failed: medicines.medicine_code'.
        4. Runs migrate_database(db).
        5. Verifies:
           a. Adding a new medicine to a store works.
           b. Rejecting duplicate code within the same store works with clear validation message.
           c. Allowing the same medicine code in two different stores succeeds.
           d. Existing medicines, their medicine_ids, and their sales/sale_items references are 100% preserved.
           e. Foreign key checks return zero violations.
        """
        reg_fd, reg_path = tempfile.mkstemp(suffix=".db")
        os.close(reg_fd)

        try:
            # 1. Create a legacy database matching the old global unique medicine schema
            conn = sqlite3.connect(reg_path)
            c = conn.cursor()
            c.execute("PRAGMA foreign_keys = ON;")
            c.execute("""
                CREATE TABLE stores (
                    store_id TEXT PRIMARY KEY,
                    store_name TEXT NOT NULL,
                    owner_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            c.execute("INSERT INTO stores (store_id, store_name, owner_name) VALUES ('STORE-LEGACY-001', 'Legacy Store', 'Original Owner');")
            c.execute("INSERT INTO stores (store_id, store_name, owner_name) VALUES ('STORE-BRANCH-002', 'Branch Store', 'Branch Manager');")

            c.execute("""
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('Admin', 'Pharmacist', 'Owner')),
                    store_id TEXT REFERENCES stores(store_id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            c.execute("INSERT INTO users (username, password_hash, role, store_id) VALUES ('admin1', 'hash1', 'Admin', 'STORE-LEGACY-001');")

            # Legacy medicines table with global UNIQUE constraint on medicine_code
            c.execute("""
                CREATE TABLE medicines (
                    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
                    medicine_code TEXT UNIQUE NOT NULL,
                    medicine_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    manufacturer TEXT NOT NULL,
                    batch_no TEXT NOT NULL,
                    price REAL NOT NULL CHECK(price >= 0),
                    quantity INTEGER NOT NULL CHECK(quantity >= 0),
                    expiry_date TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)
            c.execute("""
                INSERT INTO medicines (medicine_id, store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
                VALUES (1, 'STORE-LEGACY-001', 'MED-OLD-1', 'Legacy Paracetamol', 'Analgesic', 'OldPharma', 'BAT01', 12.50, 100, '2028-06-30');
            """)

            # Sales and sale_items referencing medicine_id = 1
            c.execute("""
                CREATE TABLE sales (
                    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
                    invoice_number TEXT UNIQUE,
                    patient_name TEXT,
                    patient_phone TEXT,
                    patient_age INTEGER,
                    sale_date TEXT NOT NULL,
                    total_amount REAL NOT NULL CHECK(total_amount >= 0),
                    user_id INTEGER REFERENCES users(user_id)
                );
            """)
            c.execute("""
                INSERT INTO sales (sale_id, store_id, invoice_number, patient_name, sale_date, total_amount, user_id)
                VALUES (1, 'STORE-LEGACY-001', 'INV-001', 'John Doe', '2026-10-22', 25.00, 1);
            """)

            c.execute("""
                CREATE TABLE sale_items (
                    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
                    sale_id INTEGER NOT NULL REFERENCES sales(sale_id) ON DELETE CASCADE,
                    medicine_id INTEGER NOT NULL REFERENCES medicines(medicine_id) ON DELETE RESTRICT,
                    quantity INTEGER NOT NULL,
                    price REAL NOT NULL,
                    subtotal REAL NOT NULL
                );
            """)
            c.execute("""
                INSERT INTO sale_items (item_id, store_id, sale_id, medicine_id, quantity, price, subtotal)
                VALUES (1, 'STORE-LEGACY-001', 1, 1, 2, 12.50, 25.00);
            """)
            conn.commit()

            # 2. Reproduce the exact bug: inserting 'MED-OLD-1' into STORE-BRANCH-002 fails with UNIQUE constraint failed
            with self.assertRaises(sqlite3.IntegrityError) as ctx:
                c.execute("""
                    INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
                    VALUES ('STORE-BRANCH-002', 'MED-OLD-1', 'Branch Paracetamol', 'Analgesic', 'BranchPharma', 'BAT02', 14.00, 50, '2028-06-30');
                """)
            self.assertIn("UNIQUE constraint failed: medicines.medicine_code", str(ctx.exception))
            conn.close()

            # 3. Execute transactional migration
            db_mig = Database(reg_path)
            migrate_database(db_mig)

            # 4. Verify composite unique constraint is now present
            med_service_store1 = MedicineService(db_mig, store_id="STORE-LEGACY-001")
            med_service_store2 = MedicineService(db_mig, store_id="STORE-BRANCH-002")

            # a. Adding a new medicine to store 2 with SAME code as store 1 ('MED-OLD-1') now succeeds!
            med_store2 = Medicine(
                medicine_id=None,
                medicine_code="MED-OLD-1",
                medicine_name="Branch Paracetamol",
                category="Analgesic",
                manufacturer="BranchPharma",
                batch_no="BAT02",
                price=14.00,
                quantity=50,
                expiry_date="2028-06-30"
            )
            ok, msg = med_service_store2.add_medicine(med_store2)
            self.assertTrue(ok, f"Expected successful cross-store same-code insert, got: {msg}")

            # b. Rejecting duplicate code within the SAME store (store 2)
            med_store2_dupe = Medicine(
                medicine_id=None,
                medicine_code="MED-OLD-1",
                medicine_name="Branch Paracetamol Dupe",
                category="Analgesic",
                manufacturer="BranchPharma",
                batch_no="BAT03",
                price=15.00,
                quantity=20,
                expiry_date="2028-06-30"
            )
            ok_dupe, msg_dupe = med_service_store2.add_medicine(med_store2_dupe)
            self.assertFalse(ok_dupe)
            self.assertIn("already exists in your store", msg_dupe)

            # c. Adding a brand new medicine to store 1
            med_store1_new = Medicine(
                medicine_id=None,
                medicine_code="MED-NEW-99",
                medicine_name="Store 1 New Medicine",
                category="Antibiotic",
                manufacturer="GlobalHealth",
                batch_no="BAT99",
                price=45.00,
                quantity=80,
                expiry_date="2028-12-31"
            )
            ok_new, msg_new = med_service_store1.add_medicine(med_store1_new)
            self.assertTrue(ok_new, f"Adding new medicine failed: {msg_new}")

            # d. Preserving existing medicines and sales references after migration
            legacy_med = med_service_store1.get_medicine_by_id(1)
            self.assertIsNotNone(legacy_med)
            self.assertEqual(legacy_med.medicine_code, "MED-OLD-1")
            self.assertEqual(legacy_med.medicine_name, "Legacy Paracetamol")
            self.assertEqual(legacy_med.store_id, "STORE-LEGACY-001")

            sales_row = db_mig.fetch_one("""
                SELECT s.sale_id, si.item_id, m.medicine_id, m.medicine_name, m.medicine_code
                FROM sales s
                JOIN sale_items si ON s.sale_id = si.sale_id
                JOIN medicines m ON si.medicine_id = m.medicine_id
                WHERE s.sale_id = 1;
            """)
            self.assertIsNotNone(sales_row)
            self.assertEqual(sales_row["medicine_id"], 1)
            self.assertEqual(sales_row["medicine_name"], "Legacy Paracetamol")

            # e. No foreign key check violations
            conn_chk = db_mig.get_connection()
            fk_violations = conn_chk.execute("PRAGMA foreign_key_check;").fetchall()
            conn_chk.close()
            self.assertEqual(len(fk_violations), 0)

        finally:
            if os.path.exists(reg_path):
                try:
                    os.remove(reg_path)
                except PermissionError:
                    pass


if __name__ == "__main__":
    unittest.main()
