"""
Automated GUI Screenshot Generator.
Captures high-resolution screenshots of:
  1. Redesigned Two-Column Login Screen (User Cards Directory + Authentication Panel)
  2. Owner Executive Dashboard
  3. Administrator Dashboard
  4. Pharmacist Clinical Dashboard
  5. Cashier Shift POS Dashboard
  6. Inventory Manager Stock Dashboard

Saves all images to reports/screenshots/.
Uses Win32 GDI PrintWindow rendering to guarantee capture even in virtual desktop environments.
Runs strictly on an isolated test database.
"""
import os
import sys
import time
import ctypes
from ctypes import wintypes
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import database.db as db_module
from database.test_seeder import seed_test_dataset, cleanup_test_data
from main import PharmacyApp


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
    time.sleep(0.4)

    hwnd = window.winfo_id()
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    if w <= 0 or h <= 0:
        w = max(window.winfo_width(), 1000)
        h = max(window.winfo_height(), 650)

    hdc_screen = user32.GetDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    gdi32.SelectObject(hdc_mem, hbm)

    # PW_RENDERFULLCONTENT = 2
    res = user32.PrintWindow(hwnd, hdc_mem, 2)
    if not res:
        res = user32.PrintWindow(hwnd, hdc_mem, 0)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    buf = ctypes.create_string_buffer(w * h * 4)
    lines = gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

    success = False
    if lines > 0:
        img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA', 0, 1)
        # Convert to RGB to ensure standard color space
        rgb_img = img.convert("RGB")
        rgb_img.save(filepath, "PNG")
        print(f"  [Screenshot Saved] {filepath} ({w}x{h})")
        success = True
    else:
        print(f"  [Screenshot Error] GetDIBits returned {lines} for {filepath}")

    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_screen)
    return success


def generate_all_screenshots():
    out_dir = os.path.join(PROJECT_ROOT, "reports", "screenshots")
    os.makedirs(out_dir, exist_ok=True)

    test_db_path = os.path.join(PROJECT_ROOT, "data", "test_screenshots.db")
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except Exception:
            pass

    test_db = db_module.get_db(test_db_path)
    seed_test_dataset(test_db, test_tag="TEST")

    print("Launching PharmacyApp for screenshot captures...")
    app = PharmacyApp()
    app.geometry("1150x750")
    app.update_idletasks()
    app.update()

    # 1. Login Screen
    print("Capturing Login Screen...")
    login_path = os.path.join(out_dir, "01_login_screen.png")
    capture_window_gdi(app, login_path)

    # Role dashboards
    roles_to_capture = [
        ("test_owner_alpha", "TestPassword@2026", "02_owner_dashboard.png", "Owner Dashboard"),
        ("test_admin_alpha", "TestPassword@2026", "03_admin_dashboard.png", "Admin Dashboard"),
        ("test_pharma_alpha", "TestPassword@2026", "04_pharmacist_dashboard.png", "Pharmacist Dashboard"),
        ("test_cashier_alpha", "TestPassword@2026", "05_cashier_dashboard.png", "Cashier Dashboard"),
        ("test_inv_alpha", "TestPassword@2026", "06_inventory_manager_dashboard.png", "Inventory Manager Dashboard"),
    ]

    for uname, pwd, filename, label in roles_to_capture:
        print(f"Navigating to {label} ({uname})...")
        if not hasattr(app, "_login_frame") or app._login_frame is None:
            # Need to logout first
            if hasattr(app, "_main_content") and app._main_content:
                app._main_content._handle_logout()
                app.update()
                time.sleep(0.3)

        app._login_frame._user_e.delete(0, "end")
        app._login_frame._user_e.insert(0, uname)
        app._login_frame._pwd_e.delete(0, "end")
        app._login_frame._pwd_e.insert(0, pwd)
        app._login_frame._login()
        app.update()

        # Let the view and subcomponents refresh
        time.sleep(0.5)
        app.update()

        screenshot_path = os.path.join(out_dir, filename)
        capture_window_gdi(app, screenshot_path)

    # Now while still logged in as test_admin_alpha or test_owner_alpha, capture feature screens
    print("Navigating to Billing POS Screen...")
    app._main_content._on_nav_click("Billing")
    app.update()
    time.sleep(0.4)
    # Populate a sample item in cart and phone to show active checkout button
    try:
        billing_view = app._main_content.billing_view
        if billing_view:
            billing_view.pat_phone_entry.delete(0, "end")
            billing_view.pat_phone_entry.insert(0, "9876543210")
            billing_view._on_phone_change()
            # Add an item to cart if medicines exist
            med_rows = billing_view.medicine_service.get_all_medicines()
            if med_rows:
                first_med = med_rows[0]
                billing_view.cart[first_med.medicine_id] = 2
                billing_view.refresh_cart_display()
            app.update()
            time.sleep(0.4)
    except Exception as e:
        print(f"Billing screen setup note: {e}")
    capture_window_gdi(app, os.path.join(out_dir, "07_billing_screen.png"))

    print("Navigating to Populated Batch Inventory Screen...")
    app._main_content._on_nav_click("Batches")
    app.update()
    time.sleep(0.5)
    capture_window_gdi(app, os.path.join(out_dir, "08_batch_inventory.png"))

    print("Navigating to Populated Purchasing Screen...")
    app._main_content._on_nav_click("Purchases")
    app.update()
    time.sleep(0.5)
    capture_window_gdi(app, os.path.join(out_dir, "09_purchases_screen.png"))

    print("Navigating to Staff Accounts Screen...")
    app._main_content._on_nav_click("Staff")
    app.update()
    time.sleep(0.5)
    capture_window_gdi(app, os.path.join(out_dir, "10_staff_management.png"))

    print("All screenshots generated successfully in reports/screenshots/!")
    app.destroy()
    cleanup_test_data(test_db, test_tag="TEST")
    if os.path.exists(test_db_path):
        try:
            os.remove(test_db_path)
        except Exception:
            pass


if __name__ == "__main__":
    generate_all_screenshots()
