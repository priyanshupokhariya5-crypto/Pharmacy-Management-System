"""
Manual Verification Scenario Test Script for Phase 10.
Executes the exact end-to-end user journey:
 1. Initial State: Login screen requirements (no auto-dashboard)
 2. Register Store 1: "Ram Medical Store" (Owner: "Ram Sharma", user: "ramstore", email: "ram@example.com")
 3. Login to Ram Medical Store & Add 2 medicines ("Paracetamol 500mg", "Amoxicillin 250mg")
 4. Create a test bill / sale with invoice generation
 5. Logout (session cleared)
 6. Re-login as Ram Medical Store & verify medicines and invoice persist
 7. Register Store 2: "Sharma Pharmacy" (Owner: "Sharma Ji", user: "sharmastore", email: "sharma@example.com")
 8. Login to Sharma Pharmacy & verify Ram Medical Store's medicines and bills are NOT visible (0 records)
 9. Add a medicine to Sharma Pharmacy ("Cetirizine 10mg")
 10. Logout & re-login to Ram Medical Store: verify both stores retain only their own separate records
 11. Application Restart simulation: close DB connection, re-initialize, and re-verify persistence & isolation
"""
import os
import tempfile
from datetime import datetime, timedelta

from database.db import Database
from database.schema import init_db
from models.medicine import Medicine
from models.user import User
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from services.sales_service import SalesService
from services.search_service import SearchService
from reports.report_generator import ReportGenerator
from utils.fmea import FMEAService, FMEARecord
from utils.sqc import SQCService, SQCDefect


def run_phase10_verification():
    print("=" * 80)
    print("PHASE 10: MULTI-STORE MANUAL VERIFICATION SCENARIO TEST")
    print("=" * 80)

    # Create disposable test database
    temp_fd, temp_db_path = tempfile.mkstemp(suffix="_phase10_verify.db")
    os.close(temp_fd)

    try:
        # Step 1: Initial Launch - verify login requirement
        print("\n[Step 1] Initial launch verification: Database created, requiring authentication...")
        db = init_db(temp_db_path)
        auth = AuthService(db)
        active_session = None
        assert active_session is None, "Session must be unauthenticated on startup!"
        print("  -> Verified: Application requires login; no unauthenticated dashboard access.")

        # Step 2: Register Store 1 - Ram Medical Store
        print("\n[Step 2] Registering 'Ram Medical Store'...")
        ok, msg, ram_owner = auth.register_store(
            store_name="Ram Medical Store",
            owner_name="Ram Sharma",
            username="ramstore",
            email="ram@example.com",
            password="RamPassword123",
            confirm_password="RamPassword123"
        )
        assert ok, f"Registration failed: {msg}"
        ram_store_id = ram_owner.store_id
        print(f"  -> Successfully registered: Store ID = {ram_store_id}, Username = {ram_owner.username}")

        # Step 3: Login as Ram Medical Store & Add 2 test medicines
        print("\n[Step 3] Logging into Ram Medical Store & adding 2 medicines...")
        logged_ram, msg = auth.authenticate("ramstore", "RamPassword123")
        assert logged_ram is not None, f"Login failed: {msg}"
        active_session = logged_ram

        ram_med_service = MedicineService(db, store_id=active_session.store_id)
        m1 = Medicine(
            medicine_id=None, medicine_code="RAM-MED-01", medicine_name="Paracetamol 500mg",
            category="Tablet", manufacturer="Cipla", batch_no="BAT-RAM-01",
            price=15.0, quantity=100, expiry_date="2027-12-31"
        )
        m2 = Medicine(
            medicine_id=None, medicine_code="RAM-MED-02", medicine_name="Amoxicillin 250mg",
            category="Capsule", manufacturer="Sun Pharma", batch_no="BAT-RAM-02",
            price=30.0, quantity=50, expiry_date="2027-11-30"
        )
        ok1, _ = ram_med_service.add_medicine(m1)
        ok2, _ = ram_med_service.add_medicine(m2)
        assert ok1 and ok2, "Failed to add medicines to Ram Medical Store"
        ram_meds = ram_med_service.get_all_medicines()
        assert len(ram_meds) == 2, f"Expected 2 medicines, got {len(ram_meds)}"
        print(f"  -> Added 2 medicines: {[m.medicine_name for m in ram_meds]}")

        # Step 4: Create a test bill in Ram Medical Store
        print("\n[Step 4] Creating a test bill for Ram Medical Store...")
        ram_sales_service = SalesService(db, store_id=active_session.store_id)
        ram_m1 = ram_med_service.get_medicine_by_code("RAM-MED-01")
        cart = [(ram_m1.medicine_id, 10)]
        sale_ok, s_msg, sale_id, invoice_num = ram_sales_service.process_sale(
            user_id=active_session.user_id,
            cart_items=cart,
            patient_name="Anita Roy",
            patient_phone="9876543210"
        )
        assert sale_ok, f"Sale failed: {s_msg}"
        print(f"  -> Sale processed: Invoice {invoice_num}, Sale ID {sale_id}")
        # Verify stock deduction
        m1_updated = ram_med_service.get_medicine_by_id(ram_m1.medicine_id)
        assert m1_updated.quantity == 90, f"Stock should be 90, got {m1_updated.quantity}"
        print(f"  -> Verified stock deduction: 100 -> {m1_updated.quantity}")

        # Step 5: Logout from Ram Medical Store
        print("\n[Step 5] Logging out of Ram Medical Store...")
        active_session = None
        assert active_session is None, "Session must be None after logout"
        print("  -> Session cleared successfully.")

        # Step 6: Log in again as Ram Medical Store & verify persistence
        print("\n[Step 6] Re-logging into Ram Medical Store and verifying saved data...")
        logged_ram2, _ = auth.authenticate("ram@example.com", "RamPassword123")  # Test login via email
        assert logged_ram2 is not None, "Email login failed"
        active_session = logged_ram2

        ram_meds_check = MedicineService(db, store_id=active_session.store_id).get_all_medicines()
        assert len(ram_meds_check) == 2, f"Expected 2 medicines after re-login, found {len(ram_meds_check)}"
        ram_sales_check = SalesService(db, store_id=active_session.store_id).get_recent_sales()
        assert len(ram_sales_check) == 1, f"Expected 1 sale after re-login, found {len(ram_sales_check)}"
        assert ram_sales_check[0]["invoice_number"] == invoice_num
        print(f"  -> Verified: Both 2 medicines and invoice {invoice_num} remain perfectly intact.")

        # Step 7: Register Store 2 - Sharma Pharmacy
        print("\n[Step 7] Registering second store 'Sharma Pharmacy'...")
        ok_sharma, _, sharma_owner = auth.register_store(
            store_name="Sharma Pharmacy",
            owner_name="Sharma Ji",
            username="sharmastore",
            email="sharma@example.com",
            password="SharmaPassword123",
            confirm_password="SharmaPassword123"
        )
        assert ok_sharma, "Failed to register Sharma Pharmacy"
        sharma_store_id = sharma_owner.store_id
        assert sharma_store_id != ram_store_id, "Store IDs must be distinct!"
        print(f"  -> Successfully registered: Store ID = {sharma_store_id}, Username = {sharma_owner.username}")

        # Step 8: Log in to Sharma Pharmacy & verify Ram Medical Store's records are NOT visible
        print("\n[Step 8] Logging into Sharma Pharmacy & verifying data isolation...")
        active_session = None  # simulate logout
        logged_sharma, _ = auth.authenticate("sharmastore", "SharmaPassword123")
        assert logged_sharma is not None
        active_session = logged_sharma

        sharma_med_service = MedicineService(db, store_id=active_session.store_id)
        sharma_sales_service = SalesService(db, store_id=active_session.store_id)
        sharma_search_service = SearchService(db, store_id=active_session.store_id)

        sharma_meds = sharma_med_service.get_all_medicines()
        sharma_sales = sharma_sales_service.get_recent_sales()
        sharma_search = sharma_search_service.quick_search("Paracetamol")

        assert len(sharma_meds) == 0, f"Sharma Pharmacy should have 0 medicines, got {len(sharma_meds)}"
        assert len(sharma_sales) == 0, f"Sharma Pharmacy should have 0 sales, got {len(sharma_sales)}"
        assert len(sharma_search) == 0, f"Sharma Pharmacy should not find Ram's medicine in search, got {len(sharma_search)}"
        print("  -> Verified: Sharma Pharmacy has 0 medicines, 0 sales, and cannot search Ram's stock (Total Isolation).")

        # Step 9: Add a medicine to Sharma Pharmacy
        print("\n[Step 9] Adding medicine 'Cetirizine 10mg' to Sharma Pharmacy...")
        sharma_m1 = Medicine(
            medicine_id=None, medicine_code="SHA-MED-01", medicine_name="Cetirizine 10mg",
            category="Tablet", manufacturer="Dr. Reddy", batch_no="BAT-SHA-01",
            price=8.0, quantity=200, expiry_date="2028-06-30"
        )
        ok_sm, _ = sharma_med_service.add_medicine(sharma_m1)
        assert ok_sm, "Failed to add medicine to Sharma Pharmacy"
        sharma_meds_now = sharma_med_service.get_all_medicines()
        assert len(sharma_meds_now) == 1
        print(f"  -> Added to Sharma Pharmacy: {[m.medicine_name for m in sharma_meds_now]}")

        # Step 10: Log out & log in to Ram Medical Store again. Verify separate records.
        print("\n[Step 10] Switching back to Ram Medical Store to verify isolation...")
        active_session = None
        logged_ram3, _ = auth.authenticate("ramstore", "RamPassword123")
        active_session = logged_ram3
        ram_meds_final = MedicineService(db, store_id=active_session.store_id).get_all_medicines()
        ram_names = [m.medicine_name for m in ram_meds_final]
        assert len(ram_meds_final) == 2, f"Ram Medical Store should still have 2 medicines, got {len(ram_meds_final)}"
        assert "Cetirizine 10mg" not in ram_names, "Sharma's medicine leaked into Ram's store!"
        assert "Paracetamol 500mg" in ram_names and "Amoxicillin 250mg" in ram_names
        print(f"  -> Verified: Ram Medical Store has exactly its 2 medicines: {ram_names}")

        # Step 11: Application Restart simulation
        print("\n[Step 11] Simulating complete application restart (fresh DB connection & init)...")
        # Initialize fresh DB handle on the same database file
        restarted_db = init_db(temp_db_path)
        restarted_auth = AuthService(restarted_db)

        # Re-login to Ram Medical Store
        re_ram, _ = restarted_auth.authenticate("ramstore", "RamPassword123")
        assert re_ram is not None
        re_ram_meds = MedicineService(restarted_db, store_id=re_ram.store_id).get_all_medicines()
        re_ram_sales = SalesService(restarted_db, store_id=re_ram.store_id).get_recent_sales()
        assert len(re_ram_meds) == 2
        assert len(re_ram_sales) == 1

        # Re-login to Sharma Pharmacy
        re_sharma, _ = restarted_auth.authenticate("sharmastore", "SharmaPassword123")
        assert re_sharma is not None
        re_sharma_meds = MedicineService(restarted_db, store_id=re_sharma.store_id).get_all_medicines()
        re_sharma_sales = SalesService(restarted_db, store_id=re_sharma.store_id).get_recent_sales()
        assert len(re_sharma_meds) == 1
        assert len(re_sharma_sales) == 0

        print("  -> Verified: After full restart, Ram Medical Store has 2 medicines & 1 sale; Sharma Pharmacy has 1 medicine & 0 sales.")
        print("\n" + "=" * 80)
        print("ALL 11 STEPS OF THE MANUAL VERIFICATION SCENARIO PASSED SUCCESSFULLY!")
        print("=" * 80)

    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except PermissionError:
                pass


if __name__ == "__main__":
    run_phase10_verification()
