"""
Dashboard View with Role-Based Architecture and Q13 Quick-Search Feature.
Renders dedicated, live dashboards for all 4 canonical roles:
  1. Owner / Admin Dashboard (Executive revenue, profit estimates, sales trends, top sellers)
  2. Cashier Dashboard (Today's bills, gross sales, payment split, recent sales, prominent New Bill action)
  3. Pharmacist Dashboard (Clinical attention flags, near-expiry/expired items, safety alerts, fast lookup)
  4. Inventory Manager Dashboard (Physical units, stock valuation, low-stock reorder lists, expiry ledger)
All metrics and tables are calculated dynamically using real SQLite queries.
"""
import time
import tkinter as tk
from typing import Optional, List, Dict, Any, Callable
import customtkinter as ctk

from ui.theme import Theme
from services.medicine_service import MedicineService
from services.sales_service import SalesService
from services.search_service import SearchService
from services.rbac import (
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_INVENTORY_MANAGER,
)
from models.medicine import Medicine
from models.user import User
from utils.logger import get_app_logger


class MedicineDetailModal(ctk.CTkToplevel):
    """Modal popup dialog showing complete details for a selected medicine."""

    def __init__(self, parent, medicine: Medicine):
        super().__init__(parent)
        self.medicine = medicine

        self.title(f"Medicine Details - {medicine.medicine_name}")
        self.geometry("480x530")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_DARK)

        # Make modal stay on top and grab focus
        self.transient(parent)
        self.grab_set()

        # Center on parent window
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - 240
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - 265
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self._build_ui()

    def _build_ui(self) -> None:
        card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.pack(padx=20, pady=20, fill="both", expand=True)

        # Title & Code
        title_lbl = ctk.CTkLabel(
            card,
            text=self.medicine.medicine_name,
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY,
            wraplength=400
        )
        title_lbl.pack(pady=(20, 2))

        code_lbl = ctk.CTkLabel(
            card,
            text=f"Code: {self.medicine.medicine_code}",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MUTED
        )
        code_lbl.pack(pady=(0, 15))

        # Status Badges Bar
        badge_frame = ctk.CTkFrame(card, fg_color="transparent")
        badge_frame.pack(pady=(0, 15))

        # Stock Badge
        stock_color = Theme.get_stock_color(self.medicine.stock_status)
        stock_badge = ctk.CTkLabel(
            badge_frame,
            text=f" Stock: {self.medicine.stock_status} ",
            font=Theme.FONT_BOLD,
            fg_color=stock_color,
            text_color=Theme.TEXT_DARK,
            corner_radius=6
        )
        stock_badge.pack(side="left", padx=5)

        # Expiry Badge
        exp_color = Theme.get_expiry_color(self.medicine.expiry_status)
        exp_badge = ctk.CTkLabel(
            badge_frame,
            text=f" Expiry: {self.medicine.expiry_status} ",
            font=Theme.FONT_BOLD,
            fg_color=exp_color,
            text_color=Theme.TEXT_DARK,
            corner_radius=6
        )
        exp_badge.pack(side="left", padx=5)

        # Details Grid
        details = [
            ("Category", self.medicine.category),
            ("Manufacturer", self.medicine.manufacturer),
            ("Batch Number", self.medicine.batch_no),
            ("Unit Price", f"₹{self.medicine.price:.2f}"),
            ("Stock Quantity", f"{self.medicine.quantity} units"),
            ("Expiry Date", self.medicine.expiry_date)
        ]

        grid_frame = ctk.CTkFrame(card, fg_color=Theme.INPUT_BG, corner_radius=10)
        grid_frame.pack(padx=20, fill="x", pady=(0, 20))

        for idx, (label, value) in enumerate(details):
            lbl_key = ctk.CTkLabel(
                grid_frame,
                text=f"{label}:",
                font=Theme.FONT_BOLD,
                text_color=Theme.TEXT_MUTED,
                anchor="w"
            )
            lbl_key.grid(row=idx, column=0, padx=15, pady=6, sticky="w")

            lbl_val = ctk.CTkLabel(
                grid_frame,
                text=str(value),
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MAIN,
                anchor="e"
            )
            lbl_val.grid(row=idx, column=1, padx=15, pady=6, sticky="e")

        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        # Close Button
        close_btn = ctk.CTkButton(
            card,
            text="Close Details",
            font=Theme.FONT_BOLD,
            height=38,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self.destroy
        )
        close_btn.pack(padx=20, fill="x", pady=(0, 15))


class DashboardView(ctk.CTkFrame):
    """
    Role-Based Dashboard View.
    Dynamically renders and populates metrics tailored to the authenticated user's role:
    Owner/Admin, Cashier, Pharmacist, or Inventory Manager.
    """

    def __init__(self, parent, user: User, on_navigate_callback: Optional[Callable[[str], None]] = None):
        super().__init__(parent, fg_color="transparent")
        self.user = user
        self.on_navigate_callback = on_navigate_callback
        self.store_id = getattr(self.user, 'store_id', 'STORE-LEGACY-001')
        self.medicine_service = MedicineService(store_id=self.store_id)
        self.sales_service = SalesService(store_id=self.store_id)
        self.search_service = SearchService(store_id=self.store_id)
        self.logger = get_app_logger()

        # Debounce timer reference for Q13 Quick-Search
        self._search_timer_id = None
        self.card_widgets: Dict[str, ctk.CTkLabel] = {}

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        """Constructs the dashboard layout based on the user's canonical role."""
        # Top Header Banner
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12)
        header.pack(fill="x", pady=(0, 15))

        display_name = getattr(self.user, 'full_name', '') or self.user.username
        store_display = getattr(self.user, 'store_name', '') or "Pharmacy Store"
        canonical_role = self.user.canonical_role

        role_badges = {
            ROLE_OWNER: ("👑 Store Owner Dashboard", Theme.PRIMARY),
            ROLE_ADMIN: ("⚙️ Administrator Dashboard", Theme.PRIMARY),
            ROLE_CASHIER: ("🛒 Cashier POS Shift Dashboard", Theme.SECONDARY),
            ROLE_PHARMACIST: ("💊 Pharmacist Clinical Dashboard", Theme.INFO if hasattr(Theme, "INFO") else Theme.PRIMARY),
            ROLE_INVENTORY_MANAGER: ("📦 Inventory Control Dashboard", Theme.WARNING),
        }
        badge_text, badge_color = role_badges.get(canonical_role, (f"👤 {canonical_role} Dashboard", Theme.PRIMARY))

        left_header = ctk.CTkFrame(header, fg_color="transparent")
        left_header.pack(side="left", padx=20, pady=12)

        title_label = ctk.CTkLabel(
            left_header,
            text=f"Welcome, {display_name} 👋",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_MAIN
        )
        title_label.pack(anchor="w")

        role_badge_lbl = ctk.CTkLabel(
            left_header,
            text=f" {badge_text} ",
            font=Theme.FONT_SMALL,
            fg_color=badge_color,
            text_color=Theme.TEXT_DARK,
            corner_radius=6
        )
        role_badge_lbl.pack(anchor="w", pady=(4, 0))

        subtitle_label = ctk.CTkLabel(
            header,
            text=f"Store: {store_display}\nStore ID: {self.store_id}",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            justify="right"
        )
        subtitle_label.pack(side="right", padx=20, pady=12)

        # Main Body Container
        self.body_container = ctk.CTkFrame(self, fg_color="transparent")
        self.body_container.pack(fill="both", expand=True)

        # Dispatch to role-specific dashboard builder
        if canonical_role in (ROLE_OWNER, ROLE_ADMIN):
            self._build_owner_dashboard()
        elif canonical_role == ROLE_CASHIER:
            self._build_cashier_dashboard()
        elif canonical_role == ROLE_PHARMACIST:
            self._build_pharmacist_dashboard()
        elif canonical_role == ROLE_INVENTORY_MANAGER:
            self._build_inventory_dashboard()
        else:
            self._build_generic_dashboard()

    # =========================================================================
    # 1. OWNER / ADMIN DASHBOARD
    # =========================================================================
    def _build_owner_dashboard(self) -> None:
        """Constructs executive KPI cards, sales trends, top sellers, and Q13 quick-search."""
        # KPI Row
        self.kpi_frame = ctk.CTkFrame(self.body_container, fg_color="transparent")
        self.kpi_frame.pack(fill="x", pady=(0, 15))

        kpi_specs = [
            ("today_sales", "Today's Sales", "₹0.00", Theme.SUCCESS),
            ("today_bills", "Today's Bills", "0", Theme.SECONDARY),
            ("total_sales", "Total Net Sales", "₹0.00", Theme.PRIMARY),
            ("est_profit", "Gross Profit", "₹0.00", Theme.SUCCESS),
            ("stock_alerts", "Low Stock & Expiry Alerts", "0", Theme.WARNING),
        ]

        for idx, (key, title, default_val, color) in enumerate(kpi_specs):
            card = ctk.CTkFrame(self.kpi_frame, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
            card.grid(row=0, column=idx, padx=5, pady=4, sticky="nsew")
            self.kpi_frame.columnconfigure(idx, weight=1)

            lbl_title = ctk.CTkLabel(card, text=title, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
            lbl_title.pack(pady=(10, 2), padx=8)

            lbl_val = ctk.CTkLabel(card, text=default_val, font=Theme.FONT_TITLE, text_color=color)
            lbl_val.pack(pady=(0, 10), padx=8)

            self.card_widgets[key] = lbl_val

        # Quick Actions Bar for Owner / Admin
        quick_action_bar = ctk.CTkFrame(self.body_container, fg_color=Theme.BG_CARD, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
        quick_action_bar.pack(fill="x", pady=(0, 12), padx=2)

        q_left = ctk.CTkFrame(quick_action_bar, fg_color="transparent")
        q_left.pack(side="left", padx=16, pady=10)
        ctk.CTkLabel(q_left, text="⚡ Quick Actions:", font=Theme.FONT_SUBHEADING, text_color=Theme.TEXT_MAIN).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            q_left,
            text="🛒  New Customer Bill (POS)",
            font=Theme.FONT_BODY,
            height=32,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self._on_new_bill_clicked
        ).pack(side="left", padx=6)

        ctk.CTkButton(
            q_left,
            text="👥  Manage Staff Accounts",
            font=Theme.FONT_BODY,
            height=32,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            border_width=1,
            border_color=Theme.BORDER_COLOR,
            command=self._on_manage_staff_clicked
        ).pack(side="left", padx=6)

        # Lower Content: Split View (Search Left, Insights Right)
        content_split = ctk.CTkFrame(self.body_container, fg_color="transparent")
        content_split.pack(fill="both", expand=True)
        content_split.columnconfigure(0, weight=3)
        content_split.columnconfigure(1, weight=2)
        content_split.rowconfigure(0, weight=1)

        # Left Column: Q13 Quick-Search
        self._embed_quick_search_card(content_split, grid_col=0)

        # Right Column: Top Sellers & Recent Transactions
        right_panel = ctk.CTkScrollableFrame(content_split, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # Top Sellers Section
        ctk.CTkLabel(right_panel, text="🏆 Top Selling Medicines", font=Theme.FONT_HEADING, text_color=Theme.PRIMARY).pack(anchor="w", padx=15, pady=(15, 6))
        self.top_sellers_container = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.top_sellers_container.pack(fill="x", padx=15, pady=(0, 15))

        # Recent Sales Section
        ctk.CTkLabel(right_panel, text="📋 Recent Store Transactions", font=Theme.FONT_HEADING, text_color=Theme.SECONDARY).pack(anchor="w", padx=15, pady=(10, 6))
        self.recent_sales_container = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.recent_sales_container.pack(fill="x", padx=15, pady=(0, 15))

    # =========================================================================
    # 2. CASHIER DASHBOARD
    # =========================================================================
    def _build_cashier_dashboard(self) -> None:
        """Constructs cashier shift metrics, payment breakdown, and prominent New Bill action."""
        # Top KPI Frame
        self.kpi_frame = ctk.CTkFrame(self.body_container, fg_color="transparent")
        self.kpi_frame.pack(fill="x", pady=(0, 15))

        cashier_kpi_specs = [
            ("today_bills_count", "Today's Bill Count", "0", Theme.PRIMARY),
            ("today_sales_total", "Today's Gross Sales", "₹0.00", Theme.SUCCESS),
            ("cash_total", "Cash Collections", "₹0.00", Theme.SECONDARY),
            ("upi_card_total", "Digital (UPI / Card)", "₹0.00", Theme.PRIMARY),
            ("net_sales", "Net Settled Sales", "₹0.00", Theme.SUCCESS),
        ]

        for idx, (key, title, default_val, color) in enumerate(cashier_kpi_specs):
            card = ctk.CTkFrame(self.kpi_frame, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
            card.grid(row=0, column=idx, padx=5, pady=4, sticky="nsew")
            self.kpi_frame.columnconfigure(idx, weight=1)

            lbl_title = ctk.CTkLabel(card, text=title, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
            lbl_title.pack(pady=(10, 2), padx=8)

            lbl_val = ctk.CTkLabel(card, text=default_val, font=Theme.FONT_TITLE, text_color=color)
            lbl_val.pack(pady=(0, 10), padx=8)

            self.card_widgets[key] = lbl_val

        # Quick Action Banner for Cashier
        action_card = ctk.CTkFrame(self.body_container, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.PRIMARY)
        action_card.pack(fill="x", pady=(0, 15), padx=2)

        action_inner = ctk.CTkFrame(action_card, fg_color="transparent")
        action_inner.pack(fill="x", padx=20, pady=15)

        action_info = ctk.CTkFrame(action_inner, fg_color="transparent")
        action_info.pack(side="left")

        ctk.CTkLabel(action_info, text="Ready to Bill a Customer?", font=Theme.FONT_HEADING, text_color=Theme.TEXT_MAIN).pack(anchor="w")
        ctk.CTkLabel(action_info, text="Launch the Point of Sale interface to create a new customer bill with automatic stock checking.", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(2, 0))

        new_bill_btn = ctk.CTkButton(
            action_inner,
            text="🛒  OPEN NEW BILL (POS)",
            font=Theme.FONT_HEADING,
            height=46,
            width=220,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self._on_new_bill_clicked
        )
        new_bill_btn.pack(side="right")

        # Bottom Split: Shift Transactions Table & Medicine Price Lookup
        content_split = ctk.CTkFrame(self.body_container, fg_color="transparent")
        content_split.pack(fill="both", expand=True)
        content_split.columnconfigure(0, weight=3)
        content_split.columnconfigure(1, weight=2)
        content_split.rowconfigure(0, weight=1)

        # Left: Today's Shift Transactions
        tx_card = ctk.CTkFrame(content_split, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        tx_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(tx_card, text="🧾 Today's Shift Invoices", font=Theme.FONT_HEADING, text_color=Theme.PRIMARY).pack(anchor="w", padx=15, pady=(15, 6))
        self.cashier_tx_scroll = ctk.CTkScrollableFrame(tx_card, fg_color="transparent")
        self.cashier_tx_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Right: Quick Price & Availability Lookup
        self._embed_quick_search_card(content_split, grid_col=1, title="🔍 Medicine Price & Stock Check")

    # =========================================================================
    # 3. PHARMACIST DASHBOARD
    # =========================================================================
    def _build_pharmacist_dashboard(self) -> None:
        """Constructs clinical attention alerts, near-expiry inspection, and safety checks."""
        # Top KPI Frame
        self.kpi_frame = ctk.CTkFrame(self.body_container, fg_color="transparent")
        self.kpi_frame.pack(fill="x", pady=(0, 15))

        pharma_kpi_specs = [
            ("available_medicines", "Medicines In-Stock", "0", Theme.SUCCESS),
            ("attention_total", "Clinical Attention Required", "0", Theme.WARNING),
            ("expiring_soon_count", "Near-Expiry (<30 Days)", "0", Theme.WARNING),
            ("expired_count", "Expired Stock (BLOCKED)", "0", Theme.DANGER),
            ("low_stock_count", "Critical Low Stock (<=10)", "0", Theme.SECONDARY),
        ]

        for idx, (key, title, default_val, color) in enumerate(pharma_kpi_specs):
            card = ctk.CTkFrame(self.kpi_frame, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
            card.grid(row=0, column=idx, padx=5, pady=4, sticky="nsew")
            self.kpi_frame.columnconfigure(idx, weight=1)

            lbl_title = ctk.CTkLabel(card, text=title, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
            lbl_title.pack(pady=(10, 2), padx=8)

            lbl_val = ctk.CTkLabel(card, text=default_val, font=Theme.FONT_TITLE, text_color=color)
            lbl_val.pack(pady=(0, 10), padx=8)

            self.card_widgets[key] = lbl_val

        # Lower Content: Split View
        content_split = ctk.CTkFrame(self.body_container, fg_color="transparent")
        content_split.pack(fill="both", expand=True)
        content_split.columnconfigure(0, weight=3)
        content_split.columnconfigure(1, weight=2)
        content_split.rowconfigure(0, weight=1)

        # Left: Fast Search & Clinical Inspection
        self._embed_quick_search_card(content_split, grid_col=0, title="🔬 Clinical Medicine & Batch Lookup")

        # Right: Attention Required Items & Recent Dispensing
        right_panel = ctk.CTkScrollableFrame(content_split, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(right_panel, text="⚠️ Medicines Requiring Attention", font=Theme.FONT_HEADING, text_color=Theme.WARNING).pack(anchor="w", padx=15, pady=(15, 6))
        self.pharma_attention_container = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.pharma_attention_container.pack(fill="x", padx=15, pady=(0, 15))

        ctk.CTkLabel(right_panel, text="📋 Recent Dispensing Activity", font=Theme.FONT_HEADING, text_color=Theme.PRIMARY).pack(anchor="w", padx=15, pady=(10, 6))
        self.pharma_dispensed_container = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.pharma_dispensed_container.pack(fill="x", padx=15, pady=(0, 15))

    # =========================================================================
    # 4. INVENTORY MANAGER DASHBOARD
    # =========================================================================
    def _build_inventory_dashboard(self) -> None:
        """Constructs physical units, inventory valuation, reorder priority, and expiry alerts."""
        # Top KPI Frame
        self.kpi_frame = ctk.CTkFrame(self.body_container, fg_color="transparent")
        self.kpi_frame.pack(fill="x", pady=(0, 15))

        inv_kpi_specs = [
            ("total_medicines", "Cataloged Medicines", "0", Theme.PRIMARY),
            ("total_stock_quantity", "Physical Stock Units", "0", Theme.SECONDARY),
            ("total_inventory_value", "Inventory Valuation", "₹0.00", Theme.SUCCESS),
            ("low_stock_count", "Reorder Required (<=10)", "0", Theme.WARNING),
            ("expired_count", "Expired Stock (Quarantine)", "0", Theme.DANGER),
        ]

        for idx, (key, title, default_val, color) in enumerate(inv_kpi_specs):
            card = ctk.CTkFrame(self.kpi_frame, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
            card.grid(row=0, column=idx, padx=5, pady=4, sticky="nsew")
            self.kpi_frame.columnconfigure(idx, weight=1)

            lbl_title = ctk.CTkLabel(card, text=title, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
            lbl_title.pack(pady=(10, 2), padx=8)

            lbl_val = ctk.CTkLabel(card, text=default_val, font=Theme.FONT_TITLE, text_color=color)
            lbl_val.pack(pady=(0, 10), padx=8)

            self.card_widgets[key] = lbl_val

        # Lower Content: Split View
        content_split = ctk.CTkFrame(self.body_container, fg_color="transparent")
        content_split.pack(fill="both", expand=True)
        content_split.columnconfigure(0, weight=1)
        content_split.columnconfigure(1, weight=1)
        content_split.rowconfigure(0, weight=1)

        # Left: Reorder Priority List
        left_card = ctk.CTkFrame(content_split, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        left_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        ctk.CTkLabel(left_card, text="🚨 Low-Stock Reorder Priority List", font=Theme.FONT_HEADING, text_color=Theme.WARNING).pack(anchor="w", padx=15, pady=(15, 6))
        self.reorder_scroll = ctk.CTkScrollableFrame(left_card, fg_color="transparent")
        self.reorder_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Right: Batch & Expiry Alert Ledger
        right_card = ctk.CTkFrame(content_split, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        right_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ctk.CTkLabel(right_card, text="⏳ Batch & Expiration Alerts (<60 Days)", font=Theme.FONT_HEADING, text_color=Theme.DANGER).pack(anchor="w", padx=15, pady=(15, 6))
        self.expiry_scroll = ctk.CTkScrollableFrame(right_card, fg_color="transparent")
        self.expiry_scroll.pack(fill="both", expand=True, padx=15, pady=(0, 15))

    def _build_generic_dashboard(self) -> None:
        """Fallback dashboard for standard users."""
        self._build_owner_dashboard()

    # =========================================================================
    # REUSABLE QUICK-SEARCH COMPONENT (Q13)
    # =========================================================================
    def _embed_quick_search_card(self, parent_grid, grid_col: int = 0, title: str = "⚡ Quick Search & Retrieval") -> None:
        """Embeds the sub-millisecond debounced Q13 Quick-Search widget into a grid cell."""
        search_card = ctk.CTkFrame(parent_grid, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.PRIMARY)
        search_card.grid(row=0, column=grid_col, sticky="nsew", padx=(0, 5 if grid_col == 0 else 0))

        search_header = ctk.CTkFrame(search_card, fg_color="transparent")
        search_header.pack(fill="x", padx=15, pady=(12, 4))

        q13_title = ctk.CTkLabel(search_header, text=title, font=Theme.FONT_HEADING, text_color=Theme.PRIMARY)
        q13_title.pack(side="left")

        self.perf_metric_lbl = ctk.CTkLabel(search_header, text="Query latency: 0.000 ms", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
        self.perf_metric_lbl.pack(side="right")

        q13_title_sub = ctk.CTkLabel(search_card, text="Live debounced search with indexed sub-millisecond lookups.", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED, anchor="w")
        q13_title_sub.pack(fill="x", padx=15, pady=(0, 8))

        # Search Entry Bar
        search_entry_frame = ctk.CTkFrame(search_card, fg_color="transparent")
        search_entry_frame.pack(fill="x", padx=15, pady=(0, 8))

        self.search_entry = ctk.CTkEntry(
            search_entry_frame,
            placeholder_text="🔍 Type medicine name, code, category or manufacturer...",
            height=40,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.PRIMARY,
            border_width=1,
            text_color=Theme.TEXT_MAIN
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", self._on_key_release)

        clear_btn = ctk.CTkButton(
            search_entry_frame,
            text="Clear",
            width=70,
            height=40,
            font=Theme.FONT_BOLD,
            fg_color=Theme.BG_HEADER,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self._clear_search
        )
        clear_btn.pack(side="right")

        self.results_scroll_frame = ctk.CTkScrollableFrame(search_card, fg_color=Theme.BG_DARK, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
        self.results_scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 12))
        self._show_initial_search_prompt()

    # =========================================================================
    # REFRESH & LIVE DATA POPULATION
    # =========================================================================
    def refresh(self) -> None:
        """Refreshes live metrics according to the user's canonical role."""
        role = self.user.canonical_role

        if role in (ROLE_OWNER, ROLE_ADMIN):
            self._refresh_owner_dashboard()
        elif role == ROLE_CASHIER:
            self._refresh_cashier_dashboard()
        elif role == ROLE_PHARMACIST:
            self._refresh_pharmacist_dashboard()
        elif role == ROLE_INVENTORY_MANAGER:
            self._refresh_inventory_dashboard()

    def _refresh_owner_dashboard(self) -> None:
        summary = self.medicine_service.get_owner_summary()

        if "today_sales" in self.card_widgets:
            self.card_widgets["today_sales"].configure(text=f"₹{summary['today_sales_amount']:.2f}")
        if "today_bills" in self.card_widgets:
            self.card_widgets["today_bills"].configure(text=str(summary["today_bills_count"]))
        if "total_sales" in self.card_widgets:
            self.card_widgets["total_sales"].configure(text=f"₹{summary['total_sales_amount']:.2f}")
        if "est_profit" in self.card_widgets:
            profit_val = summary.get("estimated_gross_profit")
            if profit_val is not None:
                self.card_widgets["est_profit"].configure(text=f"₹{profit_val:.2f}")
            else:
                self.card_widgets["est_profit"].configure(text="Unavailable")
        if "stock_alerts" in self.card_widgets:
            total_alerts = summary["low_stock_count"] + summary["expired_count"] + summary["expiring_soon_count"]
            self.card_widgets["stock_alerts"].configure(text=str(total_alerts))

        # Render Top Sellers
        if hasattr(self, "top_sellers_container"):
            for w in self.top_sellers_container.winfo_children():
                w.destroy()
            top_selling = summary.get("top_selling", [])
            if not top_selling:
                ctk.CTkLabel(self.top_sellers_container, text="No sales recorded yet.", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(pady=10)
            else:
                for idx, item in enumerate(top_selling):
                    row_f = ctk.CTkFrame(self.top_sellers_container, fg_color=Theme.INPUT_BG, corner_radius=6)
                    row_f.pack(fill="x", pady=2)
                    ctk.CTkLabel(row_f, text=f"#{idx+1} {item['medicine_name']}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).pack(side="left", padx=8, pady=4)
                    ctk.CTkLabel(row_f, text=f"{item['qty_sold']} sold  (₹{item['total_rev']:.2f})", font=Theme.FONT_BOLD, text_color=Theme.PRIMARY).pack(side="right", padx=8, pady=4)

        # Render Recent Sales
        if hasattr(self, "recent_sales_container"):
            for w in self.recent_sales_container.winfo_children():
                w.destroy()
            recent_sales = summary.get("recent_sales", [])
            if not recent_sales:
                ctk.CTkLabel(self.recent_sales_container, text="No recent sales found.", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(pady=10)
            else:
                for tx in recent_sales:
                    row_f = ctk.CTkFrame(self.recent_sales_container, fg_color=Theme.INPUT_BG, corner_radius=6)
                    row_f.pack(fill="x", pady=2)
                    time_sub = tx["sale_date"][-8:] if len(tx["sale_date"]) >= 8 else tx["sale_date"]
                    ctk.CTkLabel(row_f, text=f"{tx['invoice_number']} ({tx['patient_name']})", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MAIN).pack(side="left", padx=8, pady=4)
                    ctk.CTkLabel(row_f, text=f"₹{tx['total_amount']:.2f} | {time_sub}", font=Theme.FONT_BOLD, text_color=Theme.SUCCESS).pack(side="right", padx=8, pady=4)

    def _refresh_cashier_dashboard(self) -> None:
        summary = self.sales_service.get_cashier_summary(cashier_user_id=getattr(self.user, 'user_id', None))

        if "today_bills_count" in self.card_widgets:
            self.card_widgets["today_bills_count"].configure(text=str(summary["today_bills_count"]))
        if "today_sales_total" in self.card_widgets:
            self.card_widgets["today_sales_total"].configure(text=f"₹{summary['today_sales_total']:.2f}")
        if "cash_total" in self.card_widgets:
            self.card_widgets["cash_total"].configure(text=f"₹{summary['cash_total']:.2f}")
        if "upi_card_total" in self.card_widgets:
            digital_sum = summary["upi_total"] + summary["card_total"]
            self.card_widgets["upi_card_total"].configure(text=f"₹{digital_sum:.2f}")
        if "net_sales" in self.card_widgets:
            self.card_widgets["net_sales"].configure(text=f"₹{summary['net_sales']:.2f}")

        # Render Recent Invoices for Cashier
        if hasattr(self, "cashier_tx_scroll"):
            for w in self.cashier_tx_scroll.winfo_children():
                w.destroy()
            recent_txs = summary.get("recent_transactions", [])
            if not recent_txs:
                ctk.CTkLabel(self.cashier_tx_scroll, text="No bills processed today yet.", font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(pady=30)
            else:
                for tx in recent_txs:
                    card = ctk.CTkFrame(self.cashier_tx_scroll, fg_color=Theme.INPUT_BG, corner_radius=8)
                    card.pack(fill="x", pady=3)
                    left = ctk.CTkFrame(card, fg_color="transparent")
                    left.pack(side="left", padx=10, pady=6)
                    ctk.CTkLabel(left, text=f"{tx['invoice_number']} - {tx['patient_name']}", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w")
                    ctk.CTkLabel(left, text=f"Time: {tx['sale_date']} | Items: {tx['items_count']}", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")

                    ctk.CTkLabel(card, text=f"₹{tx['total_amount']:.2f}", font=Theme.FONT_HEADING, text_color=Theme.SUCCESS).pack(side="right", padx=12, pady=6)

    def _refresh_pharmacist_dashboard(self) -> None:
        summary = self.medicine_service.get_pharmacist_summary()

        if "available_medicines" in self.card_widgets:
            self.card_widgets["available_medicines"].configure(text=str(summary["available_medicines"]))
        if "attention_total" in self.card_widgets:
            self.card_widgets["attention_total"].configure(text=str(summary["attention_total"]))
        if "expiring_soon_count" in self.card_widgets:
            self.card_widgets["expiring_soon_count"].configure(text=str(summary["expiring_soon_count"]))
        if "expired_count" in self.card_widgets:
            self.card_widgets["expired_count"].configure(text=str(summary["expired_count"]))
        if "low_stock_count" in self.card_widgets:
            self.card_widgets["low_stock_count"].configure(text=str(summary["low_stock_count"]))

        # Attention required items
        if hasattr(self, "pharma_attention_container"):
            for w in self.pharma_attention_container.winfo_children():
                w.destroy()
            alerts = summary.get("alert_medicines", [])
            if not alerts:
                ctk.CTkLabel(self.pharma_attention_container, text="All medicines are within safe parameters.", font=Theme.FONT_SMALL, text_color=Theme.SUCCESS).pack(pady=10)
            else:
                for med in alerts:
                    row_f = ctk.CTkFrame(self.pharma_attention_container, fg_color=Theme.INPUT_BG, corner_radius=6)
                    row_f.pack(fill="x", pady=2)
                    ctk.CTkLabel(row_f, text=f"{med.medicine_name} ({med.batch_no})", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MAIN).pack(side="left", padx=8, pady=4)
                    status_lbl = f"{med.expiry_status} | Qty: {med.quantity}"
                    color = Theme.DANGER if med.is_expired else Theme.WARNING
                    ctk.CTkLabel(row_f, text=status_lbl, font=Theme.FONT_SMALL, text_color=color).pack(side="right", padx=8, pady=4)

        # Recent dispensing items
        if hasattr(self, "pharma_dispensed_container"):
            for w in self.pharma_dispensed_container.winfo_children():
                w.destroy()
            dispensed = summary.get("recent_dispensed", [])
            if not dispensed:
                ctk.CTkLabel(self.pharma_dispensed_container, text="No recent dispensing recorded.", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(pady=10)
            else:
                for d in dispensed:
                    row_f = ctk.CTkFrame(self.pharma_dispensed_container, fg_color=Theme.INPUT_BG, corner_radius=6)
                    row_f.pack(fill="x", pady=2)
                    ctk.CTkLabel(row_f, text=f"{d['medicine_name']} ({d['quantity']} units)", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MAIN).pack(side="left", padx=8, pady=4)
                    ctk.CTkLabel(row_f, text=f"Patient: {d['patient_name']}", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="right", padx=8, pady=4)

    def _refresh_inventory_dashboard(self) -> None:
        summary = self.medicine_service.get_inventory_manager_summary()

        if "total_medicines" in self.card_widgets:
            self.card_widgets["total_medicines"].configure(text=str(summary["total_medicines"]))
        if "total_stock_quantity" in self.card_widgets:
            self.card_widgets["total_stock_quantity"].configure(text=str(summary["total_stock_quantity"]))
        if "total_inventory_value" in self.card_widgets:
            self.card_widgets["total_inventory_value"].configure(text=f"₹{summary['total_inventory_value']:.2f}")
        if "low_stock_count" in self.card_widgets:
            self.card_widgets["low_stock_count"].configure(text=str(summary["low_stock_count"]))
        if "expired_count" in self.card_widgets:
            self.card_widgets["expired_count"].configure(text=str(summary["expired_count"]))

        # Reorder items
        if hasattr(self, "reorder_scroll"):
            for w in self.reorder_scroll.winfo_children():
                w.destroy()
            reorders = summary.get("reorder_items", [])
            if not reorders:
                ctk.CTkLabel(self.reorder_scroll, text="No items currently require reordering.", font=Theme.FONT_BODY, text_color=Theme.SUCCESS).pack(pady=20)
            else:
                for med in reorders:
                    card = ctk.CTkFrame(self.reorder_scroll, fg_color=Theme.INPUT_BG, corner_radius=8)
                    card.pack(fill="x", pady=2)
                    left = ctk.CTkFrame(card, fg_color="transparent")
                    left.pack(side="left", padx=10, pady=6)
                    ctk.CTkLabel(left, text=f"{med.medicine_name} ({med.medicine_code})", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w")
                    ctk.CTkLabel(left, text=f"Category: {med.category} | Batch: {med.batch_no}", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")

                    badge_color = Theme.DANGER if med.quantity == 0 else Theme.WARNING
                    ctk.CTkLabel(card, text=f" Stock: {med.quantity} ", font=Theme.FONT_BOLD, fg_color=badge_color, text_color=Theme.TEXT_DARK, corner_radius=4).pack(side="right", padx=10, pady=6)

        # Batch & Expiry items
        if hasattr(self, "expiry_scroll"):
            for w in self.expiry_scroll.winfo_children():
                w.destroy()
            exp_items = summary.get("expiry_items", [])
            if not exp_items:
                ctk.CTkLabel(self.expiry_scroll, text="No upcoming expiry alerts.", font=Theme.FONT_BODY, text_color=Theme.SUCCESS).pack(pady=20)
            else:
                for med in exp_items:
                    card = ctk.CTkFrame(self.expiry_scroll, fg_color=Theme.INPUT_BG, corner_radius=8)
                    card.pack(fill="x", pady=2)
                    left = ctk.CTkFrame(card, fg_color="transparent")
                    left.pack(side="left", padx=10, pady=6)
                    ctk.CTkLabel(left, text=f"{med.medicine_name} ({med.batch_no})", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w")
                    ctk.CTkLabel(left, text=f"Expiry Date: {med.expiry_date} | Stock: {med.quantity}", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")

                    exp_color = Theme.DANGER if med.is_expired else Theme.WARNING
                    ctk.CTkLabel(card, text=f" {med.expiry_status} ", font=Theme.FONT_BOLD, fg_color=exp_color, text_color=Theme.TEXT_DARK, corner_radius=4).pack(side="right", padx=10, pady=6)

    def _on_new_bill_clicked(self) -> None:
        """Navigates directly to the Billing (POS) section."""
        if self.on_navigate_callback:
            self.on_navigate_callback("Billing")

    # =========================================================================
    # Q13 SEARCH LOGIC & AUTO-SUGGESTIONS
    # =========================================================================
    def _on_key_release(self, event) -> None:
        """250ms debouncing mechanism using Tkinter after_cancel."""
        if self._search_timer_id:
            self.after_cancel(self._search_timer_id)
        self._search_timer_id = self.after(250, self._perform_search)

    def _clear_search(self) -> None:
        if self._search_timer_id:
            self.after_cancel(self._search_timer_id)
        if hasattr(self, "search_entry"):
            self.search_entry.delete(0, "end")
        if hasattr(self, "perf_metric_lbl"):
            self.perf_metric_lbl.configure(text="Query latency: 0.000 ms")
        self._show_initial_search_prompt()

    def _show_initial_search_prompt(self) -> None:
        if not hasattr(self, "results_scroll_frame"):
            return
        for widget in self.results_scroll_frame.winfo_children():
            widget.destroy()

        prompt_lbl = ctk.CTkLabel(
            self.results_scroll_frame,
            text="Type in the search bar above to see instant live results matching medicines...",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED
        )
        prompt_lbl.pack(pady=30)

    def _perform_search(self) -> None:
        if not hasattr(self, "search_entry"):
            return
        query_text = self.search_entry.get().strip()

        if not query_text:
            self._show_initial_search_prompt()
            if hasattr(self, "perf_metric_lbl"):
                self.perf_metric_lbl.configure(text="Query latency: 0.000 ms")
            return

        medicines, latency_ms = self.search_service.search_medicines(query_text=query_text, limit=30)

        if hasattr(self, "perf_metric_lbl"):
            self.perf_metric_lbl.configure(text=f"Query latency: {latency_ms:.3f} ms | Found: {len(medicines)}")

        self.logger.log_search_query({"quick_search": query_text}, latency_ms, len(medicines))

        for widget in self.results_scroll_frame.winfo_children():
            widget.destroy()

        if not medicines:
            no_res_lbl = ctk.CTkLabel(
                self.results_scroll_frame,
                text=f"No medicines found matching '{query_text}'.",
                font=Theme.FONT_BODY,
                text_color=Theme.DANGER
            )
            no_res_lbl.pack(pady=20)
            return

        for med in medicines:
            self._render_medicine_result_card(med)

    def _render_medicine_result_card(self, med: Medicine) -> None:
        card = ctk.CTkFrame(
            self.results_scroll_frame,
            fg_color=Theme.BG_CARD,
            corner_radius=8,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.pack(fill="x", padx=4, pady=3)

        info_block = ctk.CTkFrame(card, fg_color="transparent")
        info_block.pack(side="left", fill="both", expand=True, padx=10, pady=6)

        name_lbl = ctk.CTkLabel(
            info_block,
            text=f"{med.medicine_name}  ({med.medicine_code})",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        )
        name_lbl.pack(anchor="w")

        sub_info = f"Category: {med.category}  |  Batch: {med.batch_no}  |  Exp: {med.expiry_date}"
        sub_lbl = ctk.CTkLabel(
            info_block,
            text=sub_info,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            anchor="w"
        )
        sub_lbl.pack(anchor="w", pady=(1, 0))

        right_block = ctk.CTkFrame(card, fg_color="transparent")
        right_block.pack(side="right", padx=10, pady=6)

        stock_color = Theme.get_stock_color(med.stock_status)
        stock_badge = ctk.CTkLabel(
            right_block,
            text=f" {med.stock_status} ({med.quantity}) ",
            font=Theme.FONT_SMALL,
            fg_color=stock_color,
            text_color=Theme.TEXT_DARK,
            corner_radius=4
        )
        stock_badge.pack(side="left", padx=4)

        price_lbl = ctk.CTkLabel(
            right_block,
            text=f"₹{med.price:.2f}",
            font=Theme.FONT_HEADING,
            text_color=Theme.PRIMARY
        )
        price_lbl.pack(side="left", padx=8)

        view_btn = ctk.CTkButton(
            right_block,
            text="View",
            width=65,
            height=26,
            font=Theme.FONT_SMALL,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=lambda m=med: self._open_medicine_details(m)
        )
        view_btn.pack(side="left", padx=2)

    def _open_medicine_details(self, med: Medicine) -> None:
        MedicineDetailModal(self, med)

    def _on_new_bill_clicked(self) -> None:
        """Navigates to the Billing POS interface."""
        if self.on_navigate_callback:
            self.on_navigate_callback("Billing")

    def _on_manage_staff_clicked(self) -> None:
        """Navigates to the Staff Accounts management interface."""
        if self.on_navigate_callback:
            self.on_navigate_callback("Staff")
