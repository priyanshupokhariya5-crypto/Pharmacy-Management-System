"""
Automated GUI Workflow Verification for main.py.
Exercises the actual CustomTkinter PharmacyApp UI lifecycle:
 1. Startup: root window displays _LoginPanel (no unauthenticated dashboard)
 2. Navigation to _SignupPanel
 3. Store 1 registration ("Ram Medical Store")
 4. Automatic redirect to _LoginPanel with pre-fill and success banner
 5. Login to Store 1 -> window swaps to MainWindowContent with Store 1 title & header
 6. Inventory inspection in Store 1
 7. Header Logout -> root window swaps back to _LoginPanel, session cleared
 8. Navigation to _SignupPanel -> Store 2 registration ("Sharma Pharmacy")
 9. Login to Store 2 -> MainWindowContent with Store 2 title & header
 10. Data isolation check in GUI: Store 2 has 0 of Store 1's medicines
 11. Add Store 2 medicine -> Logout -> Re-login Store 1 -> Verify complete isolation
"""
import os
import sys
import tempfile

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database.db as db_module
from database.schema import init_db
from models.medicine import Medicine
from services.medicine_service import MedicineService


def test_complete_gui_lifecycle():
    print("=" * 80)
    print("STARTING FULL GUI WORKFLOW VERIFICATION (main.py - PharmacyApp)")
    print("=" * 80)

    # 1. Setup disposable database
    temp_fd, temp_db_path = tempfile.mkstemp(suffix="_gui_verify.db")
    os.close(temp_fd)

    try:
        # Initialize schema on temp DB and set singleton
        init_db(temp_db_path)
        db_module.get_db(temp_db_path)

        # Import PharmacyApp from main.py
        from main import PharmacyApp, _LoginPanel, _SignupPanel
        from ui.main_window import MainWindowContent

        print("\n[Step 1] Initializing PharmacyApp GUI root window...")
        app = PharmacyApp()
        app.update()

        # Check startup state
        assert isinstance(app._login_frame, _LoginPanel), "Expected _LoginPanel on initial startup!"
        assert not hasattr(app, "_main_content") or app._main_content is None, "Main content must NOT be created before login!"
        print(f"  -> Title: '{app.title()}'")
        print("  -> Verified: Application launches cleanly into _LoginPanel.")

        # [Step 2 & 3] Transition to Signup and register Store 1
        print("\n[Step 2 & 3] Transitioning to _SignupPanel and registering 'Ram Medical Store'...")
        app._show_signup()
        app.update()
        assert isinstance(app._signup_frame, _SignupPanel), "Expected _SignupPanel after clicking signup!"

        # Fill fields for Ram Medical Store
        app._signup_frame._store_e.delete(0, "end"); app._signup_frame._store_e.insert(0, "Ram Medical Store")
        app._signup_frame._owner_e.delete(0, "end"); app._signup_frame._owner_e.insert(0, "Ram Sharma")
        app._signup_frame._user_e.delete(0, "end"); app._signup_frame._user_e.insert(0, "ramstore")
        app._signup_frame._email_e.delete(0, "end"); app._signup_frame._email_e.insert(0, "ram@example.com")
        app._signup_frame._pwd_e.delete(0, "end"); app._signup_frame._pwd_e.insert(0, "Password123")
        app._signup_frame._cpwd_e.delete(0, "end"); app._signup_frame._cpwd_e.insert(0, "Password123")

        # Submit registration
        app._signup_frame._signup()
        app.update()

        # [Step 4] Verify automatic redirect to login with pre-fill
        assert isinstance(app._login_frame, _LoginPanel), "Expected redirect to _LoginPanel on successful signup!"
        assert app._login_frame._user_e.get() == "ramstore", f"Expected prefill 'ramstore', got '{app._login_frame._user_e.get()}'"
        assert "registered successfully" in app._login_frame._msg.cget("text"), "Expected green success message!"
        print(f"  -> Redirect verified: Username pre-filled ('{app._login_frame._user_e.get()}'), Banner: '{app._login_frame._msg.cget('text')}'")

        # [Step 5] Log in as Ram Medical Store
        print("\n[Step 5] Submitting credentials to log in to Ram Medical Store...")
        app._login_frame._pwd_e.insert(0, "Password123")
        app._login_frame._login()
        app.update()

        assert hasattr(app, "_main_content") and isinstance(app._main_content, MainWindowContent), "Expected MainWindowContent on login!"
        assert app._main_content.user.username == "ramstore"
        assert app._main_content.user.store_name == "Ram Medical Store"
        assert "Ram Medical Store" in app.title(), f"Title should have store name, got '{app.title()}'"
        print(f"  -> Logged in successfully: User='{app._main_content.user.username}', Store='{app._main_content.user.store_name}'")
        print(f"  -> Window Title: '{app.title()}'")

        # [Step 6] Add 2 medicines for Ram Medical Store
        print("\n[Step 6] Adding 2 medicines in Ram Medical Store...")
        ram_store_id = app._main_content.user.store_id
        med_service_ram = MedicineService(db_module.get_db(), store_id=ram_store_id)
        med_service_ram.add_medicine(Medicine(
            medicine_id=None, medicine_code="RAM-01", medicine_name="Paracetamol 500mg",
            category="Tablet", manufacturer="Cipla", batch_no="BAT-R1", price=15.0, quantity=100, expiry_date="2027-12-31"
        ))
        med_service_ram.add_medicine(Medicine(
            medicine_id=None, medicine_code="RAM-02", medicine_name="Amoxicillin 250mg",
            category="Capsule", manufacturer="Sun", batch_no="BAT-R2", price=30.0, quantity=50, expiry_date="2027-11-30"
        ))
        ram_meds = med_service_ram.get_all_medicines()
        assert len(ram_meds) == 2
        print(f"  -> Ram Medical Store Inventory: {[m.medicine_name for m in ram_meds]}")

        # [Step 7] Logout from Ram Medical Store
        print("\n[Step 7] Triggering GUI Logout...")
        app._on_logout()
        app.update()
        assert isinstance(app._login_frame, _LoginPanel), "Expected _LoginPanel after logout!"
        print("  -> Verified: Application successfully swapped back to _LoginPanel on logout.")

        # [Step 8] Register Store 2: "Sharma Pharmacy"
        print("\n[Step 8] Registering second store 'Sharma Pharmacy'...")
        app._show_signup()
        app.update()
        app._signup_frame._store_e.delete(0, "end"); app._signup_frame._store_e.insert(0, "Sharma Pharmacy")
        app._signup_frame._owner_e.delete(0, "end"); app._signup_frame._owner_e.insert(0, "Sharma Ji")
        app._signup_frame._user_e.delete(0, "end"); app._signup_frame._user_e.insert(0, "sharmastore")
        app._signup_frame._email_e.delete(0, "end"); app._signup_frame._email_e.insert(0, "sharma@example.com")
        app._signup_frame._pwd_e.delete(0, "end"); app._signup_frame._pwd_e.insert(0, "Password123")
        app._signup_frame._cpwd_e.delete(0, "end"); app._signup_frame._cpwd_e.insert(0, "Password123")
        app._signup_frame._signup()
        app.update()

        # [Step 9] Login to Sharma Pharmacy
        print("\n[Step 9] Logging into Sharma Pharmacy...")
        app._login_frame._pwd_e.insert(0, "Password123")
        app._login_frame._login()
        app.update()
        assert app._main_content.user.username == "sharmastore"
        assert "Sharma Pharmacy" in app.title()
        print(f"  -> Logged in successfully: User='{app._main_content.user.username}', Store='{app._main_content.user.store_name}'")

        # [Step 10] Verify Data Isolation in GUI
        print("\n[Step 10] Verifying Sharma Pharmacy data isolation in GUI...")
        sharma_store_id = app._main_content.user.store_id
        assert sharma_store_id != ram_store_id, "Store IDs must be distinct!"
        med_service_sharma = MedicineService(db_module.get_db(), store_id=sharma_store_id)
        sharma_meds = med_service_sharma.get_all_medicines()
        assert len(sharma_meds) == 0, f"Sharma Pharmacy should have 0 medicines, found {len(sharma_meds)}!"
        print("  -> Verified: Sharma Pharmacy sees 0 medicines. Complete store isolation confirmed.")

        # [Step 11] Add medicine to Sharma Pharmacy, then switch back to Ram Medical Store
        print("\n[Step 11] Adding medicine to Sharma Pharmacy and switching back to Ram...")
        med_service_sharma.add_medicine(Medicine(
            medicine_id=None, medicine_code="SHA-01", medicine_name="Cetirizine 10mg",
            category="Tablet", manufacturer="Dr. Reddy", batch_no="BAT-S1", price=8.0, quantity=200, expiry_date="2028-06-30"
        ))
        assert len(med_service_sharma.get_all_medicines()) == 1

        # Logout Sharma
        app._on_logout()
        app.update()

        # Re-login Ram via email
        app._login_frame._user_e.delete(0, "end"); app._login_frame._user_e.insert(0, "ram@example.com")
        app._login_frame._pwd_e.delete(0, "end"); app._login_frame._pwd_e.insert(0, "Password123")
        app._login_frame._login()
        app.update()

        assert app._main_content.user.username == "ramstore"
        ram_meds_final = MedicineService(db_module.get_db(), store_id=app._main_content.user.store_id).get_all_medicines()
        ram_final_names = [m.medicine_name for m in ram_meds_final]
        assert len(ram_meds_final) == 2
        assert "Cetirizine 10mg" not in ram_final_names, "Sharma's medicine leaked into Ram's store!"
        print(f"  -> Verified: Ram Medical Store has exactly its 2 medicines: {ram_final_names}")

        # Clean GUI shutdown
        app.destroy()
        print("\n" + "=" * 80)
        print("ALL GUI STEPS PASSED SUCCESSFULLY WITHOUT ERRORS!")
        print("=" * 80)

    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except PermissionError:
                pass


if __name__ == "__main__":
    test_complete_gui_lifecycle()
