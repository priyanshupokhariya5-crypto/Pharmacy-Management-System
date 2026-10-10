"""
Main Entry Point for Pharmacy Management System Desktop Application.
Initializes database schema and launches the CustomTkinter GUI application.

Login flow: a single CTk root window shows the login panel first, then
swaps to the main application content in-place (no second window opened).
"""
import sys
import os

# Add project root directory to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import customtkinter as ctk

from database.schema import init_db
from models.user import User
from ui.theme import Theme
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from utils.benchmark import SearchBenchmark
from utils.logger import get_app_logger

ctk.set_appearance_mode(Theme.APPEARANCE_MODE)
ctk.set_default_color_theme(Theme.COLOR_THEME)


class PharmacyApp(ctk.CTk):
    """
    Single root-window application.

    Shows the login panel on startup.
    On successful authentication the login panel is destroyed and the
    MainWindow content is built inside the same root window so the OS
    window is never destroyed or replaced.
    On logout the main content is destroyed and the login panel is
    rebuilt inside the same window.
    """

    def __init__(self):
        super().__init__()
        self.logger = get_app_logger()
        self.title("Pharmacy Management System")
        self.geometry("450x620")
        self.configure(fg_color=Theme.BG_DARK)
        self.resizable(False, False)
        self._center()
        self._apply_global_scroll_patch()
        self._show_login()

    def _apply_global_scroll_patch(self) -> None:
        """
        Creates ONE reliable centralized scrolling mechanism for the entire app.
        Replaces conflicting/buggy CustomTkinter and Tkinter default handlers.
        """
        import tkinter as tk
        from tkinter import ttk

        # 1. Unbind native class handlers that steal and trap events
        self.unbind_class('Treeview', '<MouseWheel>')
        self.unbind_class('Text', '<MouseWheel>')
        self.unbind_class('Canvas', '<MouseWheel>')

        # 2. Bind at the Window level (runs after instance/class, but BEFORE bind_all)
        self.bind('<MouseWheel>', self._on_global_mousewheel)

        # Patch CustomTkinter Dropdowns for readability
        import customtkinter as ctk
        ctk.ThemeManager.theme["CTkOptionMenu"]["fg_color"] = ["#FFFFFF", "#FFFFFF"]
        ctk.ThemeManager.theme["CTkOptionMenu"]["button_color"] = [Theme.PRIMARY, Theme.PRIMARY]
        ctk.ThemeManager.theme["CTkOptionMenu"]["button_hover_color"] = [Theme.PRIMARY_HOVER, Theme.PRIMARY_HOVER]
        ctk.ThemeManager.theme["CTkOptionMenu"]["text_color"] = [Theme.TEXT_MAIN, Theme.TEXT_MAIN]
        ctk.ThemeManager.theme["DropdownMenu"]["fg_color"] = ["#FFFFFF", "#FFFFFF"]
        ctk.ThemeManager.theme["DropdownMenu"]["hover_color"] = [Theme.INPUT_BG, Theme.INPUT_BG]
        ctk.ThemeManager.theme["DropdownMenu"]["text_color"] = [Theme.TEXT_MAIN, Theme.TEXT_MAIN]

    def _on_global_mousewheel(self, event):
        import tkinter as tk
        from tkinter import ttk

        delta = event.delta
        if not delta:
            return 'break'
            
        scroll_dir = -1 if delta > 0 else 1
        
        # Find the actual widget under the pointer
        x, y = self.winfo_pointerxy()
        try:
            target = self.winfo_containing(x, y)
        except Exception:
            target = event.widget

        curr = target
        while curr:
            scrolled = False
            
            # Check Treeview
            if isinstance(curr, ttk.Treeview) and curr.cget('yscrollcommand'):
                yview = curr.yview()
                if not ((scroll_dir < 0 and yview[0] <= 0.001) or (scroll_dir > 0 and yview[1] >= 0.999)):
                    curr.yview_scroll(int(-1 * (delta / 120)), 'units')
                    scrolled = True

            # Check Text / CTkTextbox
            elif isinstance(curr, tk.Text):
                yview = curr.yview()
                if not ((scroll_dir < 0 and yview[0] <= 0.001) or (scroll_dir > 0 and yview[1] >= 0.999)):
                    curr.yview_scroll(int(-1 * (delta / 120)), 'units')
                    scrolled = True

            # Check Canvas (CTkScrollableFrame uses a Canvas internally)
            elif isinstance(curr, tk.Canvas):
                scrollregion = curr.cget("scrollregion")
                if scrollregion:
                    yview = curr.yview()
                    if not ((scroll_dir < 0 and yview[0] <= 0.001) or (scroll_dir > 0 and yview[1] >= 0.999)):
                        # CustomTkinter Canvas uses yscrollincrement=1 (1 unit = 1 px).
                        # Multiply by 60 to scroll a standard 60 pixels per notch.
                        scroll_amount = int(-1 * (delta / 120) * 60)
                        curr.yview_scroll(scroll_amount, 'units')
                        scrolled = True

            if scrolled:
                break
                
            curr = curr.master
            
        # Always break to prevent CTk bind_all from firing and causing jumps
        return 'break'

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    # ------------------------------------------------------------------
    # Login panel
    # ------------------------------------------------------------------

    def _show_login(self) -> None:
        """Build the login card inside the root window."""
        # Resize to login dimensions
        self.geometry("450x620")
        self.resizable(False, False)
        self.title("Pharmacy Management System – Login")

        self._login_frame = _LoginPanel(self, on_success=self._on_login_success)
        self._login_frame.pack(fill="both", expand=True)

    def _on_login_success(self, user: User) -> None:
        """Swap login panel → main content in the same window."""
        self.logger.log_event("AUTH",
                              f"User '{user.username}' ({user.role}) logged in successfully.")
        # Destroy login panel
        self._login_frame.destroy()

        # Resize and unlock for main window
        self.geometry("1200x760")
        self.minsize(980, 620)
        self.resizable(True, True)
        self.title("Pharmacy Management System")
        try:
            self.state('zoomed')
        except Exception:
            self._center()

        # Build main window content inside the same root
        from ui.main_window import MainWindowContent
        self._main_content = MainWindowContent(
            self, user, on_logout_callback=self._on_logout
        )
        self._main_content.pack(fill="both", expand=True)

    def _on_logout(self) -> None:
        """Swap main content → login panel in the same window."""
        self._main_content.destroy()
        self.minsize(0, 0)
        self.resizable(False, False)
        self._show_login()
        self._center()


# ---------------------------------------------------------------------------
# Embedded login panel (Frame, not a CTk root)
# ---------------------------------------------------------------------------

class _LoginPanel(ctk.CTkFrame):
    """Login form as a Frame so it can live inside the PharmacyApp root."""

    def __init__(self, parent, on_success):
        super().__init__(parent, fg_color=Theme.BG_DARK)
        self._on_success = on_success
        self._auth = AuthService()
        self._logger = get_app_logger()
        self._build()

    def _build(self) -> None:
        import tkinter as tk

        card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD,
                            corner_radius=16, border_width=1,
                            border_color=Theme.BORDER_COLOR)
        card.pack(padx=25, pady=25, fill="both", expand=True)

        ctk.CTkLabel(card, text="🏥  Pharmacy Management System",
                     font=Theme.FONT_TITLE, text_color=Theme.PRIMARY
                     ).pack(pady=(25, 4))

        ctk.CTkLabel(card,
                     text="Pharmacy Management System  |  Q13: Faster Search & Retrieval",
                     font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED
                     ).pack(pady=(0, 20))

        self._msg = ctk.CTkLabel(card, text="", font=Theme.FONT_SMALL,
                                 text_color=Theme.DANGER, wraplength=350)
        self._msg.pack(pady=(0, 10))

        # Username
        ctk.CTkLabel(card, text="Username", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w"
                     ).pack(padx=30, fill="x", pady=(0, 2))
        self._user_e = ctk.CTkEntry(card, placeholder_text="Enter username",
                                    height=40, font=Theme.FONT_BODY,
                                    fg_color=Theme.INPUT_BG,
                                    border_color=Theme.BORDER_COLOR,
                                    text_color=Theme.TEXT_MAIN)
        self._user_e.pack(padx=30, fill="x", pady=(0, 15))
        self._user_e.focus()

        # Password
        ctk.CTkLabel(card, text="Password", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w"
                     ).pack(padx=30, fill="x", pady=(0, 2))
        self._pwd_e = ctk.CTkEntry(card, placeholder_text="Enter password",
                                   show="*", height=40, font=Theme.FONT_BODY,
                                   fg_color=Theme.INPUT_BG,
                                   border_color=Theme.BORDER_COLOR,
                                   text_color=Theme.TEXT_MAIN)
        self._pwd_e.pack(padx=30, fill="x", pady=(0, 8))
        self._pwd_e.bind("<Return>", lambda e: self._login())

        # Show/hide
        self._show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(card, text="Show Password",
                        variable=self._show_var,
                        command=self._toggle_pwd,
                        font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED,
                        checkbox_width=18, checkbox_height=18,
                        border_color=Theme.BORDER_COLOR,
                        hover_color=Theme.PRIMARY_HOVER,
                        fg_color=Theme.PRIMARY
                        ).pack(padx=30, anchor="w", pady=(0, 20))

        # Login button
        ctk.CTkButton(card, text="LOGIN", font=Theme.FONT_HEADING,
                      height=42, fg_color=Theme.PRIMARY,
                      hover_color=Theme.PRIMARY_HOVER,
                      text_color=Theme.TEXT_DARK, corner_radius=8,
                      command=self._login
                      ).pack(padx=30, fill="x", pady=(0, 15))

        # Demo credentials
        demo = ctk.CTkFrame(card, fg_color=Theme.INPUT_BG, corner_radius=8)
        demo.pack(padx=30, fill="x", pady=(0, 15))
        ctk.CTkLabel(demo, text="Demo Credentials (Click to Auto-Fill):",
                     font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED
                     ).pack(pady=(6, 4))
        bb = ctk.CTkFrame(demo, fg_color="transparent")
        bb.pack(pady=(0, 6))
        ctk.CTkButton(bb, text="Admin  (admin / admin123)",
                      font=Theme.FONT_SMALL, height=26,
                      fg_color=Theme.BG_CARD, hover_color=Theme.BORDER_COLOR,
                      text_color=Theme.PRIMARY,
                      command=lambda: self._fill("admin", "admin123")
                      ).pack(side="left", padx=5)
        ctk.CTkButton(bb, text="Pharmacist  (pharmacist / pharma123)",
                      font=Theme.FONT_SMALL, height=26,
                      fg_color=Theme.BG_CARD, hover_color=Theme.BORDER_COLOR,
                      text_color=Theme.SECONDARY,
                      command=lambda: self._fill("pharmacist", "pharma123")
                      ).pack(side="left", padx=5)

    def _toggle_pwd(self) -> None:
        self._pwd_e.configure(show="" if self._show_var.get() else "*")

    def _fill(self, u: str, p: str) -> None:
        self._user_e.delete(0, "end"); self._user_e.insert(0, u)
        self._pwd_e.delete(0, "end");  self._pwd_e.insert(0, p)
        self._msg.configure(text="")

    def _login(self) -> None:
        username = self._user_e.get().strip()
        password = self._pwd_e.get().strip()
        user, message = self._auth.authenticate(username, password)
        if user:
            self._msg.configure(text="Login successful! Loading…",
                                text_color=Theme.SUCCESS)
            self.update_idletasks()
            self._on_success(user)
        else:
            self._logger.log_event("AUTH",
                                   f"Failed login for '{username}'",
                                   level="WARNING")
            self._msg.configure(text=message, text_color=Theme.DANGER)


# ---------------------------------------------------------------------------
# CLI verification (unchanged)
# ---------------------------------------------------------------------------

def run_stage1_cli_verification():
    """Initializes database and prints Stage 1 foundation verification summary in CLI."""
    print("=" * 70)
    print("  PHARMACY MANAGEMENT SYSTEM PROJECT")
    print("  Pharmacy Management System - Faster Search & Retrieval")
    print("  Student: Priyanshu Pokhariya | Enrollment No: 2410303005")
    print("  Branch: CSE | Section: C | Session: 2026-27")
    print("=" * 70)

    logger = get_app_logger()
    logger.log_event("SYSTEM", "Initializing Stage 1 CLI Verification...")

    db = init_db()
    print("\n[OK] Database file initialized at: data/pharmacy.db")

    tables = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    table_names = [t["name"] for t in tables if not t["name"].startswith("sqlite_")]
    print(f"[OK] Created Database Tables ({len(table_names)}): {', '.join(table_names)}")

    indexes = db.fetch_all("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';")
    idx_names = [i["name"] for i in indexes]
    print(f"[OK] Created SQLite B-Tree Indexes ({len(idx_names)}): {', '.join(idx_names)}")

    auth_service = AuthService(db)
    admin_user, _ = auth_service.authenticate("admin", "admin123")
    pharma_user, _ = auth_service.authenticate("pharmacist", "pharma123")
    print(f"[OK] Seed User Accounts Verified:")
    print(f"    - Admin: '{admin_user.username if admin_user else 'FAIL'}' (Role: {admin_user.role if admin_user else 'N/A'})")
    print(f"    - Pharmacist: '{pharma_user.username if pharma_user else 'FAIL'}' (Role: {pharma_user.role if pharma_user else 'N/A'})")

    med_service = MedicineService(db)
    kpis = med_service.get_inventory_summary()
    print(f"[OK] Seed Inventory Loaded:")
    print(f"    - Total Medicines: {kpis['total_medicines']}")
    print(f"    - Total Stock Quantity: {kpis['total_stock_quantity']}")
    try:
        print(f"    - Total Inventory Value: ₹{kpis['total_inventory_value']:.2f}")
    except UnicodeEncodeError:
        print(f"    - Total Inventory Value: Rs. {kpis['total_inventory_value']:.2f}")
    print(f"    - Low Stock Items (<=10): {kpis['low_stock_count']}")
    print(f"    - Out of Stock Items: {kpis['out_of_stock_count']}")
    print(f"    - Expiring Soon Items: {kpis['expiring_soon_count']}")
    print(f"    - Expired Items: {kpis['expired_count']}")

    bm = SearchBenchmark(db)
    res = bm.benchmark_query(
        "SELECT medicine_id, medicine_name FROM medicines WHERE medicine_code = ?",
        ("MED1001",)
    )
    print(f"[OK] Search Performance Baseline:")
    print(f"    - Query: Exact Code Lookup ('MED1001')")
    print(f"    - Execution Time: {res['avg_time_ms']:.4f} ms")
    print(f"    - Query Plan: {res['query_plan']}")
    print(f"    - Index Used: {res['uses_index']}")

    print("\n[OK] STAGE 1 DATABASE FOUNDATION SUCCESSFULLY VERIFIED!")
    print("=" * 70)


def launch_app():
    """Launches the single-window pharmacy application."""
    logger = get_app_logger()
    logger.log_event("SYSTEM", "Starting Pharmacy Management System...")
    init_db()
    app = PharmacyApp()
    app.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        run_stage1_cli_verification()
    else:
        launch_app()
