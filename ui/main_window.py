"""
Main Application Window Content.

Exported as MainWindowContent (a CTkFrame) so it can be embedded
inside PharmacyApp (the single root window) without opening a second
window.

For backward compatibility the class is also aliased as MainWindow
(the old entry point used by tests that import it).
"""
import tkinter as tk
from typing import Callable, Optional
import customtkinter as ctk

from ui.theme import Theme
from ui.dashboard import DashboardView
from models.user import User
from utils.logger import get_app_logger


class MainWindowContent(ctk.CTkFrame):
    """
    All main-window chrome (top bar, sidebar, content area) as a Frame.
    Embedded inside PharmacyApp root – no separate Tk/CTk root needed.
    """

    def __init__(self, parent, user: User,
                 on_logout_callback: Optional[Callable[[], None]] = None,
                 **kwargs):
        super().__init__(parent, fg_color=Theme.BG_DARK, **kwargs)
        self.user = user
        self.on_logout_callback = on_logout_callback
        self.logger = get_app_logger()
        self._build_ui()

    def _build_ui(self) -> None:
        """Constructs top header, left sidebar navigation, and main content area."""
        # -------------------------------------------------- Top Header
        self.header_frame = ctk.CTkFrame(
            self, fg_color=Theme.BG_HEADER, corner_radius=0, height=50
        )
        self.header_frame.pack(side="top", fill="x")
        self.header_frame.pack_propagate(False)

        ctk.CTkLabel(
            self.header_frame,
            text="🏥  Pharmacy Management System",
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_MAIN,
        ).pack(side="left", padx=20, pady=10)

        ctk.CTkButton(
            self.header_frame, text="Logout",
            width=75, height=28, font=Theme.FONT_SMALL,
            fg_color=Theme.DANGER, hover_color="#e05f7e",
            text_color=Theme.TEXT_DARK, command=self._handle_logout,
        ).pack(side="right", padx=10, pady=10)

        ctk.CTkLabel(
            self.header_frame,
            text=f"👤 {self.user.username}  ({self.user.role})",
            font=Theme.FONT_SUBHEADING, text_color=Theme.PRIMARY,
        ).pack(side="right", padx=(10, 0), pady=10)

        # -------------------------------------------------- Body row
        self.body_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.body_frame.pack(side="top", fill="both", expand=True)

        # -------------------------------------------------- Sidebar
        self.sidebar_frame = ctk.CTkFrame(
            self.body_frame,
            fg_color=Theme.BG_SIDEBAR, corner_radius=0, width=210,
        )
        self.sidebar_frame.pack(side="left", fill="y")
        self.sidebar_frame.pack_propagate(False)

        ctk.CTkLabel(
            self.sidebar_frame, text="NAVIGATION",
            font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED, anchor="w",
        ).pack(fill="x", padx=20, pady=(20, 10))

        self.nav_buttons: dict = {}
        nav_items = [
            ("Dashboard",  "📊  Dashboard",                   True),
            ("Medicines",  "💊  Medicines",                   False),
            ("Search",     "🔍  Advanced Search",             False),
            ("Billing",    "🛒  Sales & Billing",             False),
            ("Reports",    "📈  Reports & Analytics",         False),
            ("Benchmark",  "⚡  Search Benchmark",            False),
            ("FMEA",       "🛡️  FMEA & Risk Audit",          False),
            ("SQC",        "📋  SQC & Kaizen",               False),
        ]

        for key, label_text, is_active in nav_items:
            btn = ctk.CTkButton(
                self.sidebar_frame, text=label_text,
                font=Theme.FONT_BODY, height=38, anchor="w",
                fg_color=Theme.PRIMARY if is_active else "transparent",
                text_color=Theme.TEXT_DARK if is_active else Theme.TEXT_MAIN,
                hover_color=Theme.PRIMARY_HOVER,
                command=lambda k=key: self._on_nav_click(k),
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = btn

        ctk.CTkButton(
            self.sidebar_frame, text="🚪  Logout",
            font=Theme.FONT_BODY, height=38, anchor="w",
            fg_color="transparent", text_color=Theme.DANGER,
            hover_color=Theme.INPUT_BG, command=self._handle_logout,
        ).pack(side="bottom", fill="x", padx=12, pady=20)

        # -------------------------------------------------- Content area
        self.content_container = ctk.CTkFrame(
            self.body_frame, fg_color="transparent"
        )
        self.content_container.pack(
            side="right", fill="both", expand=True, padx=14, pady=14
        )

        # Instantiate all views (hidden until navigated to)
        self.dashboard_view  = DashboardView(self.content_container, self.user)
        self.dashboard_view.pack(fill="both", expand=True)   # first visible

        self.medicines_view  = None
        self.search_view     = None
        self.billing_view    = None
        self.reports_view    = None
        self.benchmark_view  = None
        self.fmea_view       = None
        self.sqc_view        = None

        self.current_nav = "Dashboard"

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _all_views(self):
        return [v for v in [
            self.dashboard_view, self.medicines_view, self.search_view,
            self.billing_view, self.reports_view, self.benchmark_view,
            self.fmea_view, self.sqc_view
        ] if v is not None]

    def _on_nav_click(self, nav_key: str) -> None:
        self.current_nav = nav_key

        for key, btn in self.nav_buttons.items():
            if key == nav_key:
                btn.configure(fg_color=Theme.PRIMARY, text_color=Theme.TEXT_DARK)
            else:
                btn.configure(fg_color="transparent", text_color=Theme.TEXT_MAIN)

        for v in self._all_views():
            v.pack_forget()

        if nav_key == "Dashboard":
            self.dashboard_view.refresh()
            self.dashboard_view.pack(fill="both", expand=True)
        elif nav_key == "Medicines":
            if self.medicines_view is None:
                from ui.medicines import MedicinesView
                self.medicines_view = MedicinesView(self.content_container, self.user)
            self.medicines_view.refresh_table()
            self.medicines_view.pack(fill="both", expand=True)
        elif nav_key == "Search":
            if self.search_view is None:
                from ui.search import AdvancedSearchView
                self.search_view = AdvancedSearchView(self.content_container, self.user)
            self.search_view.pack(fill="both", expand=True)
        elif nav_key == "Billing":
            if self.billing_view is None:
                from ui.billing import BillingView
                self.billing_view = BillingView(self.content_container, self.user)
            self.billing_view.refresh_cart_display()
            self.billing_view.pack(fill="both", expand=True)
        elif nav_key == "Reports":
            if self.reports_view is None:
                from ui.reports_view import ReportsView
                self.reports_view = ReportsView(self.content_container, self.user)
            self.reports_view.refresh_reports()
            self.reports_view.pack(fill="both", expand=True)
        elif nav_key == "Benchmark":
            if self.benchmark_view is None:
                from ui.benchmark_view import BenchmarkView
                self.benchmark_view = BenchmarkView(self.content_container)
            self.benchmark_view.pack(fill="both", expand=True)
        elif nav_key == "FMEA":
            if self.fmea_view is None:
                from ui.fmea_view import FMEAView
                self.fmea_view = FMEAView(self.content_container)
            self.fmea_view.pack(fill="both", expand=True)
        elif nav_key == "SQC":
            if self.sqc_view is None:
                from ui.sqc_view import SQCView
                self.sqc_view = SQCView(self.content_container)
            self.sqc_view.pack(fill="both", expand=True)

    def _handle_logout(self) -> None:
        self.logger.log_event("AUTH", f"User '{self.user.username}' logged out.")
        if self.on_logout_callback:
            self.on_logout_callback()


# ---------------------------------------------------------------------------
# Backward-compatibility alias
# Tests and any code that imported MainWindow still work.
# ---------------------------------------------------------------------------

class MainWindow(ctk.CTk):
    """
    Legacy standalone window – kept for backward compatibility.
    New code should use PharmacyApp + MainWindowContent instead.
    """

    def __init__(self, user: User,
                 on_logout_callback: Optional[Callable[[], None]] = None):
        super().__init__()
        self.user = user
        self.on_logout_callback = on_logout_callback

        self.title("Pharmacy Management System")
        self.geometry("1200x760")
        self.minsize(980, 620)
        self.configure(fg_color=Theme.BG_DARK)

        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")

        self._content = MainWindowContent(
            self, user, on_logout_callback=self._legacy_logout
        )
        self._content.pack(fill="both", expand=True)

    def _legacy_logout(self) -> None:
        self.destroy()
        if self.on_logout_callback:
            self.on_logout_callback()
