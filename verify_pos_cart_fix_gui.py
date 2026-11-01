"""
Automated GUI Verification for POS Cart Items Visibility Fix.

This script executes the exact sequence required by the user:
1. Connects to an isolated copy of the database (data/test_pos_cart.db).
2. Launches the real CustomTkinter PharmacyApp as Owner (Priyanshu Pokhariya).
3. Navigates to Point of Sale (POS) Billing view.
4. Selects 'Cough Syrup 100ml' (MED 109).
5. Sets quantity to 1 and clicks 'Add to Cart'.
6. Asserts right-side table immediately displays MED 109, Cough Syrup 100ml, CS-2611, SHELF-B01, Qty 1, Price ₹95.00, Subtotal ₹95.00.
7. Asserts Payable Total is exactly ₹95.00.
8. Adds a second medicine ('Paracetamol 650mg') and confirms both rows appear in the cart table.
9. Captures a genuine high-resolution screenshot showing both visible cart rows.
10. Edits the first item's quantity to 2 and verifies updated subtotal and total.
11. Removes an item and verifies the recalculated total.
12. Clears the cart and confirms table is empty and total is ₹0.00.
"""

import os
import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import time
import shutil
import ctypes
from ctypes import wintypes
from PIL import Image

# Non-blocking dialog mocks for automated execution
from tkinter import messagebox, simpledialog
messagebox.showinfo = lambda title, message, **kwargs: None
messagebox.showerror = lambda title, message, **kwargs: None
messagebox.showwarning = lambda title, message, **kwargs: None
messagebox.askyesno = lambda title, message, **kwargs: True

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

ARTIFACT_DIR = r"C:\Users\priya\.gemini\antigravity\brain\0737ba36-8e0f-4deb-b159-ba6bed213daf"
REPORT_IMG_DIR = os.path.join(PROJECT_ROOT, "reports", "screenshots", "audit_final")
os.makedirs(ARTIFACT_DIR, exist_ok=True)
os.makedirs(REPORT_IMG_DIR, exist_ok=True)

# Win32 GDI capture for high-resolution authentic screenshots
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

def capture_window_gdi(window, filename):
    window.update_idletasks()
    window.update()
    hwnd = window.winfo_id()

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = max(1, rect.right - rect.left)
    h = max(1, rect.bottom - rect.top)

    hwnd_dc = user32.GetWindowDC(hwnd)
    mfc_dc = gdi32.CreateCompatibleDC(hwnd_dc)
    save_bit_map = gdi32.CreateCompatibleBitmap(hwnd_dc, w, h)
    gdi32.SelectObject(mfc_dc, save_bit_map)

    PW_RENDERFULLCONTENT = 0x00000002
    res = user32.PrintWindow(hwnd, mfc_dc, PW_RENDERFULLCONTENT)
    if not res:
        user32.PrintWindow(hwnd, mfc_dc, 0)

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0

    buffer_len = w * h * 4
    image_bytes = bytearray(buffer_len)
    buf_type = ctypes.c_char * buffer_len
    c_buf = buf_type.from_buffer(image_bytes)

    gdi32.GetDIBits(mfc_dc, save_bit_map, 0, h, ctypes.byref(c_buf), ctypes.byref(bmi), 0)

    gdi32.DeleteObject(save_bit_map)
    gdi32.DeleteDC(mfc_dc)
    user32.ReleaseDC(hwnd, hwnd_dc)

    img = Image.frombuffer('RGBA', (w, h), bytes(image_bytes), 'raw', 'BGRA', 0, 1).convert('RGB')

    report_path = os.path.join(REPORT_IMG_DIR, filename)
    artifact_path = os.path.join(ARTIFACT_DIR, filename)
    img.save(report_path, "PNG")
    img.save(artifact_path, "PNG")
    print(f"  [SAVED] {report_path} ({w}x{h})")
    print(f"  [SAVED] {artifact_path} ({w}x{h})")
    return report_path


def run_pos_cart_verification():
    print("=" * 70)
    print("STARTING POS CART ITEMS VISIBILITY GUI VERIFICATION")
    print("=" * 70)

    # 1. Setup isolated database
    test_db_path = os.path.join(PROJECT_ROOT, "data", "test_pos_cart.db")
    src_db_path = os.path.join(PROJECT_ROOT, "data", "pharmacy_app.db")
    shutil.copy2(src_db_path, test_db_path)
    print(f"[INIT] Created isolated test database at: {test_db_path}")

    # Point Database singleton to test_db_path
    import database.db as db_module
    db_module._instance = db_module.Database(test_db_path)
    orig_get_db = db_module.get_db
    db_module.get_db = lambda p=None: db_module._instance

    try:
        from main import PharmacyApp
        from models.user import User

        app = PharmacyApp()
        app.update_idletasks()
        app.update()

        # Login as Owner into store STORE-B5457089
        user_row = db_module._instance.fetch_one("SELECT * FROM users WHERE username = 'pokhariya'")
        assert user_row is not None, "Owner user 'pokhariya' not found in database!"
        owner_user = User.from_row(user_row)
        app._on_login_success(owner_user)
        app.update_idletasks()
        app.update()
        time.sleep(0.3)

        print("[NAV] Navigating to Sales & Billing (POS)...")
        app._main_content._on_nav_click("Billing")
        app.update_idletasks()
        app.update()
        time.sleep(0.3)

        bview = app._main_content.billing_view
        assert bview is not None, "BillingView failed to initialize!"

        # Step 1: Search for Cough Syrup 100ml
        print("[STEP 1-4] Searching and selecting 'Cough Syrup 100ml'...")
        bview.search_entry.delete(0, "end")
        bview.search_entry.insert(0, "Cough")
        bview._on_search_medicine()
        app.update_idletasks()
        app.update()

        # Find Cough Syrup row
        inv_children = bview.inv_tree.get_children()
        assert len(inv_children) > 0, "No search results returned for 'Cough'!"
        cs_iid = inv_children[0]
        bview.inv_tree.selection_set(cs_iid)
        bview._on_inventory_select(None)
        app.update_idletasks()
        app.update()

        # Set qty to 1 and Add to Cart
        bview.add_qty_entry.delete(0, "end")
        bview.add_qty_entry.insert(0, "1")
        bview._on_add_to_cart()
        app.update_idletasks()
        app.update()

        # Step 5-6: Verify right-side table displays all 8 columns for Cough Syrup
        print("[STEP 5-6] Verifying right-side cart table displays Cough Syrup 100ml...")
        cart_rows = bview.cart_tree.get_children()
        print(f"  Cart row count: {len(cart_rows)}")
        assert len(cart_rows) == 1, f"Expected 1 cart row, got {len(cart_rows)}"

        cs_row = bview.cart_tree.item(cart_rows[0])["values"]
        print(f"  Cough Syrup row values: {cs_row}")
        # Expected values: [id, code, name, batch, shelf, qty, price, subtotal]
        assert str(cs_row[1]) == "MED 109", f"Expected code 'MED 109', got '{cs_row[1]}'"
        assert "Cough Syrup" in str(cs_row[2]), f"Expected medicine name to contain 'Cough Syrup', got '{cs_row[2]}'"
        assert str(cs_row[3]) == "CS-2611", f"Expected batch 'CS-2611', got '{cs_row[3]}'"
        assert str(cs_row[4]) == "SHELF-B01", f"Expected shelf 'SHELF-B01', got '{cs_row[4]}'"
        assert int(cs_row[5]) == 1, f"Expected qty 1, got {cs_row[5]}"
        assert "95" in str(cs_row[6]), f"Expected price ₹95, got '{cs_row[6]}'"
        assert "95" in str(cs_row[7]), f"Expected subtotal ₹95, got '{cs_row[7]}'"

        # Verify Payable Total matches cart contents exactly
        tot_text = bview.grand_total_lbl.cget("text")
        print(f"  Payable Total: {tot_text}")
        assert "95.00" in tot_text, f"Expected total ₹95.00, got '{tot_text}'"

        # Step 7: Add a second medicine ('Paracetamol 650mg')
        print("[STEP 7] Adding second medicine to cart...")
        bview.search_entry.delete(0, "end")
        bview.search_entry.insert(0, "Paracetamol")
        bview._on_search_medicine()
        app.update_idletasks()
        app.update()

        p_children = bview.inv_tree.get_children()
        assert len(p_children) > 0, "No search results returned for 'Paracetamol'!"
        p_iid = p_children[0]
        bview.inv_tree.selection_set(p_iid)
        bview._on_inventory_select(None)
        bview.add_qty_entry.delete(0, "end")
        bview.add_qty_entry.insert(0, "2")
        bview._on_add_to_cart()
        app.update_idletasks()
        app.update()

        # Populate customer details for a complete, realistic POS screen
        bview.pat_name_entry.delete(0, "end")
        bview.pat_name_entry.insert(0, "Priyanshu Sharma")
        bview.pat_phone_entry.delete(0, "end")
        bview.pat_phone_entry.insert(0, "9876543210")
        bview.discount_entry.delete(0, "end")
        bview.discount_entry.insert(0, "0.00")
        bview.refresh_cart_display()
        app.update_idletasks()
        app.update()

        cart_rows_2 = bview.cart_tree.get_children()
        print(f"  Cart row count after 2nd item: {len(cart_rows_2)}")
        assert len(cart_rows_2) == 2, f"Expected 2 cart rows, got {len(cart_rows_2)}"
        print(f"  Row 1: {bview.cart_tree.item(cart_rows_2[0])['values']}")
        print(f"  Row 2: {bview.cart_tree.item(cart_rows_2[1])['values']}")
        print(f"  Updated Payable Total: {bview.grand_total_lbl.cget('text')}")

        # Check cart table geometry / visibility
        tree_h = bview.cart_tree.winfo_height()
        print(f"  cart_tree height in window: {tree_h}px (visible={bview.cart_tree.winfo_viewable()})")
        assert tree_h > 100, f"Cart tree height too small ({tree_h}px)!"

        # Capture authentic screenshot showing at least two visible cart rows!
        print("[CAPTURE] Capturing authentic screenshot showing both visible cart rows...")
        capture_window_gdi(app, "audit_pos_cart_two_rows_visible.png")
        capture_window_gdi(app, "audit_09_pos_billing_eight_columns_cart.png")

        # Step 8: Edit first item's quantity
        print("[STEP 8] Editing first item's quantity to 2...")
        bview.cart_tree.selection_set(cart_rows_2[0])
        # Mock simpledialog to return '2'
        simpledialog.askstring = lambda title, prompt, **kw: "2"
        bview._on_edit_cart_qty()
        app.update_idletasks()
        app.update()

        updated_row = bview.cart_tree.item(cart_rows_2[0])["values"]
        print(f"  Updated Row 1 values: {updated_row}")
        assert int(updated_row[5]) == 2, f"Expected updated qty 2, got {updated_row[5]}"
        assert "190" in str(updated_row[7]), f"Expected updated subtotal ₹190, got {updated_row[7]}"

        # Step 9: Remove second item
        print("[STEP 9] Removing second item from cart...")
        bview.cart_tree.selection_set(cart_rows_2[1])
        bview._on_remove_cart_item()
        app.update_idletasks()
        app.update()

        cart_rows_after_rm = bview.cart_tree.get_children()
        print(f"  Cart row count after removal: {len(cart_rows_after_rm)}")
        assert len(cart_rows_after_rm) == 1, f"Expected 1 cart row after removal, got {len(cart_rows_after_rm)}"
        rem_tot_text = bview.grand_total_lbl.cget("text")
        print(f"  Total after removal: {rem_tot_text}")
        assert "190.00" in rem_tot_text, f"Expected total ₹190.00, got '{rem_tot_text}'"

        # Step 10: Clear cart and verify empty state and ₹0.00
        print("[STEP 10] Clearing cart and verifying empty state...")
        bview._on_clear_cart()
        app.update_idletasks()
        app.update()

        final_rows = bview.cart_tree.get_children()
        print(f"  Final cart row count: {len(final_rows)}")
        assert len(final_rows) == 0, f"Expected 0 cart rows after clear, got {len(final_rows)}"

        final_tot_text = bview.grand_total_lbl.cget("text")
        print(f"  Final total label: {final_tot_text}")
        assert "0.00" in final_tot_text, f"Expected total ₹0.00, got '{final_tot_text}'"

        app.destroy()
        print("\n" + "=" * 70)
        print("ALL 10 POS CART VISIBILITY VERIFICATION STEPS PASSED SUCCESSFULLY!")
        print("=" * 70)

    finally:
        db_module.get_db = orig_get_db
        # Clean up test DB
        try:
            if os.path.exists(test_db_path):
                os.remove(test_db_path)
        except Exception:
            pass

if __name__ == "__main__":
    run_pos_cart_verification()
