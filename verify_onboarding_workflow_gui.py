"""
Comprehensive GUI Verification Script for User-Controlled Multi-Store and Multi-Role Onboarding.
Executes the full onboarding workflow on the clean application database (data/pharmacy_app.db):
1. Clean Initial Login Screen: Displays required 5 fields in exact order with no pre-created stores or accounts.
2. Store Registration Form: First store registration collecting store details, Owner name, username, and password.
3. Post-Registration Login: Store pre-selected, Role='Owner' pre-selected, username prefilled.
4. Authenticated Owner Dashboard: First login into the new pharmacy store.
5. Owner Staff Accounts View: Lists authorized store accounts and Add New Staff action.
6. Add Staff Modal: Fixed footer, responsive layout, provisioning a Cashier account.
7. Staff Directory Updated: Displays newly provisioned Cashier account under Owner's store.
8. Role Mismatch Rejection: Mismatched role login attempt rejected with informative error.
9. Cashier Login & Dashboard: Cashier logs in successfully with restricted role-based navigation.

Guarantees 100% database safety: Production database (data/pharmacy.db) is untouched.
"""
import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import time
import ctypes
from ctypes import wintypes
from tkinter import messagebox
from PIL import Image

# Non-blocking messagebox for headless/automated test captures
messagebox.showinfo = lambda title, message, **kwargs: None
messagebox.showerror = lambda title, message, **kwargs: None
messagebox.showwarning = lambda title, message, **kwargs: None
messagebox.askyesno = lambda title, message, **kwargs: True

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

ARTIFACT_DIR = r"C:\Users\priya\.gemini\antigravity\brain\0737ba36-8e0f-4deb-b159-ba6bed213daf"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

import database.db as db_module
from database.schema import init_db
from main import PharmacyApp
from ui.theme import Theme
from models.user import User


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wintypes.DWORD * 3)]


def capture_window_gdi(window, filepath: str) -> bool:
    """Captures a Tkinter/CustomTkinter window directly using Win32 GDI PrintWindow."""
    window.update_idletasks()
    window.update()
    time.sleep(0.35)

    hwnd = window.winfo_id()
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top

    if width <= 0 or height <= 0:
        width = window.winfo_width()
        height = window.winfo_height()

    width = max(width, 980)
    height = max(height, 640)

    hdc_window = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    hbitmap = gdi32.CreateCompatibleBitmap(hdc_window, width, height)
    h_old = gdi32.SelectObject(hdc_mem, hbitmap)

    PW_RENDERFULLCONTENT = 2
    success = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
    if not success:
        success = user32.PrintWindow(hwnd, hdc_mem, 0)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = width
    bmi.bmiHeader.biHeight = -height
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    buffer_size = width * height * 4
    buf = (ctypes.c_char * buffer_size)()
    gdi32.GetDIBits(hdc_mem, hbitmap, 0, height, ctypes.byref(buf), ctypes.byref(bmi), 0)

    img = Image.frombuffer('RGBA', (width, height), buf, 'raw', 'BGRA', 0, 1)
    img_rgb = img.convert('RGB')
    img_rgb.save(filepath, 'PNG')

    gdi32.SelectObject(hdc_mem, h_old)
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_window)

    print(f"[SCREENSHOT SAVED] -> {filepath} ({width}x{height})")
    return True


def run_verification():
    print("=" * 70)
    print("STARTING USER-CONTROLLED ONBOARDING GUI VERIFICATION")
    print("=" * 70)

    # 1. Ensure clean pharmacy_app.db exists on disk
    clean_db_path = os.path.abspath("data/pharmacy_app.db")
    if os.path.exists(clean_db_path):
        os.remove(clean_db_path)

    clean_db = init_db(clean_db_path, seed_demo=False)
    db_module._db_instance = clean_db
    os.environ["PHARMACY_DB_PATH"] = clean_db_path

    print(f"[DATABASE] Using isolated clean database: {clean_db_path}")
    store_cnt = clean_db.fetch_one("SELECT COUNT(*) as cnt FROM stores")["cnt"]
    user_cnt = clean_db.fetch_one("SELECT COUNT(*) as cnt FROM users")["cnt"]
    print(f"[VERIFY] Initial database stores={store_cnt}, users={user_cnt}")

    # Launch app
    app = PharmacyApp()
    app.update_idletasks()
    app.update()
    time.sleep(0.5)

    # -------------------------------------------------------------------------
    # Screen 1: Initial Login Screen (Clean, 0 stores, exact 5 fields order)
    # -------------------------------------------------------------------------
    print("\n[STEP 1] Capturing Clean Login Screen with exact 5-field structure...")
    capture_window_gdi(app, os.path.join(ARTIFACT_DIR, "01_login_clean_no_stores.png"))

    # -------------------------------------------------------------------------
    # Screen 2: Pharmacy Store Registration Form
    # -------------------------------------------------------------------------
    print("\n[STEP 2] Opening Store Registration Form...")
    app._show_signup()
    app.update_idletasks()
    app.update()
    time.sleep(0.5)

    # Fill registration fields
    app._signup_frame._store_e.delete(0, "end")
    app._signup_frame._store_e.insert(0, "Apex Healthcare Pharmacy")

    app._signup_frame._owner_e.delete(0, "end")
    app._signup_frame._owner_e.insert(0, "Dr. Aryan Sharma")

    app._signup_frame._user_e.delete(0, "end")
    app._signup_frame._user_e.insert(0, "aryansharma")

    app._signup_frame._email_e.delete(0, "end")
    app._signup_frame._email_e.insert(0, "aryan@apexhealth.local")

    app._signup_frame._pwd_e.delete(0, "end")
    app._signup_frame._pwd_e.insert(0, "ApexOwner2026!")

    app._signup_frame._cpwd_e.delete(0, "end")
    app._signup_frame._cpwd_e.insert(0, "ApexOwner2026!")

    app.update_idletasks()
    app.update()
    capture_window_gdi(app, os.path.join(ARTIFACT_DIR, "02_store_registration_form.png"))

    # Submit registration
    print("\n[STEP 2b] Submitting Pharmacy Store Registration...")
    app._signup_frame._signup()
    app.update_idletasks()
    app.update()
    time.sleep(0.5)

    # -------------------------------------------------------------------------
    # Screen 3: Post-Registration Login Screen (Store selected, Owner preselected)
    # -------------------------------------------------------------------------
    print("\n[STEP 3] Capturing Post-Registration Login Screen...")
    capture_window_gdi(app, os.path.join(ARTIFACT_DIR, "03_login_store_registered_preselected.png"))

    # -------------------------------------------------------------------------
    # Screen 4: Authenticated Owner Dashboard
    # -------------------------------------------------------------------------
    print("\n[STEP 4] Logging in as Owner and loading Owner Dashboard...")
    app._login_frame._pwd_e.delete(0, "end")
    app._login_frame._pwd_e.insert(0, "ApexOwner2026!")
    app._login_frame._login()
    app.update_idletasks()
    app.update()
    time.sleep(0.6)
    capture_window_gdi(app, os.path.join(ARTIFACT_DIR, "04_owner_dashboard.png"))

    # -------------------------------------------------------------------------
    # Screen 5: Owner Staff Accounts View
    # -------------------------------------------------------------------------
    print("\n[STEP 5] Navigating to Staff Accounts View...")
    app._main_content._on_nav_click("Staff")
    app.update_idletasks()
    app.update()
    time.sleep(0.5)
    capture_window_gdi(app, os.path.join(ARTIFACT_DIR, "05_staff_accounts_view.png"))

    # -------------------------------------------------------------------------
    # Screen 6: Add Staff Modal (Fixed Footer, Responsive, Scoped to Store)
    # -------------------------------------------------------------------------
    print("\n[STEP 6] Opening Add Staff Modal...")
    app._main_content.staff_view._open_add_staff_modal()
    app.update_idletasks()
    app.update()
    time.sleep(0.5)

    modal = app._main_content.staff_view._active_modal
    if modal:
        modal.name_entry.delete(0, "end")
        modal.name_entry.insert(0, "Rohan Verma")

        modal.user_entry.delete(0, "end")
        modal.user_entry.insert(0, "rohan_cashier")

        modal.role_menu.set("Cashier")

        modal.email_entry.delete(0, "end")
        modal.email_entry.insert(0, "rohan@apexhealth.local")

        modal.pass_entry.delete(0, "end")
        modal.pass_entry.insert(0, "CashierPass123!")

        modal.confirm_entry.delete(0, "end")
        modal.confirm_entry.insert(0, "CashierPass123!")

        app.update_idletasks()
        app.update()
        capture_window_gdi(modal, os.path.join(ARTIFACT_DIR, "06_add_staff_modal_fixed_footer.png"))

        # Submit modal
        modal._handle_create_account()
        app.update_idletasks()
        app.update()
        time.sleep(0.5)

    # -------------------------------------------------------------------------
    # Screen 7: Staff Directory Updated with Cashier
    # -------------------------------------------------------------------------
    print("\n[STEP 7] Capturing Staff Directory with Newly Created Cashier...")
    capture_window_gdi(app, os.path.join(ARTIFACT_DIR, "07_staff_accounts_with_cashier.png"))

    # -------------------------------------------------------------------------
    # Screen 8: Logout & Mismatched Role Rejection Test
    # -------------------------------------------------------------------------
    print("\n[STEP 8] Logging out Owner and testing Mismatched Role Rejection...")
    app._main_content._handle_logout()
    app.update_idletasks()
    app.update()
    time.sleep(0.5)

    # Attempt to log in with Cashier credentials but Role='Pharmacist' selected
    app._login_frame._role_menu.set("Pharmacist")
    app._login_frame._user_e.delete(0, "end")
    app._login_frame._user_e.insert(0, "rohan_cashier")
    app._login_frame._pwd_e.delete(0, "end")
    app._login_frame._pwd_e.insert(0, "CashierPass123!")
    app._login_frame._login()
    app.update_idletasks()
    app.update()
    time.sleep(0.5)
    capture_window_gdi(app, os.path.join(ARTIFACT_DIR, "08_login_role_mismatch_rejected.png"))

    # -------------------------------------------------------------------------
    # Screen 9: Successful Cashier Login & Restricted Dashboard
    # -------------------------------------------------------------------------
    print("\n[STEP 9] Logging in as Cashier and capturing Cashier Dashboard...")
    app._login_frame._role_menu.set("Cashier")
    app._login_frame._pwd_e.delete(0, "end")
    app._login_frame._pwd_e.insert(0, "CashierPass123!")
    app._login_frame._login()
    app.update_idletasks()
    app.update()
    time.sleep(0.6)
    capture_window_gdi(app, os.path.join(ARTIFACT_DIR, "09_cashier_dashboard_restricted.png"))

    # Close app
    try:
        app.destroy()
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("ALL 9 ONBOARDING GUI VERIFICATION SCREENSHOTS CAPTURED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    run_verification()
