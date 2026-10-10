"""
Dashboard view with live KPI metrics and Q13 Quick-Search feature.
Includes 250ms search debouncing, instant auto-suggestions, and medicine detail popups.
"""
import time
import tkinter as tk
from typing import Optional, List
import customtkinter as ctk

from ui.theme import Theme
from services.medicine_service import MedicineService
from services.search_service import SearchService
from models.medicine import Medicine
from models.user import User
from utils.logger import get_app_logger


class MedicineDetailModal(ctk.CTkToplevel):
    """Modal popup dialog showing complete details for a selected medicine."""

    def __init__(self, parent, medicine: Medicine):
        super().__init__(parent)
        self.medicine = medicine

        self.title(f"Medicine Details - {medicine.medicine_name}")
        self.geometry("480x520")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_DARK)

        # Make modal stay on top and grab focus
        self.transient(parent)
        self.grab_set()

        # Center on parent window
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (240)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (260)
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
    """Dashboard view featuring live inventory KPI summary cards and Q13 Quick-Search."""

    def __init__(self, parent, user: User):
        super().__init__(parent, fg_color="transparent")
        self.user = user
        self.medicine_service = MedicineService()
        self.search_service = SearchService()
        self.logger = get_app_logger()

        # Debounce timer reference
        self._search_timer_id = None

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        """Constructs the dashboard layout."""
        # Top Header Banner
        header = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12)
        header.pack(fill="x", pady=(0, 15))

        title_label = ctk.CTkLabel(
            header,
            text=f"Welcome back, {self.user.username} 👋",
            font=Theme.FONT_TITLE,
            text_color=Theme.TEXT_MAIN
        )
        title_label.pack(side="left", padx=20, pady=15)

        subtitle_label = ctk.CTkLabel(
            header,
            text=f"Role: {self.user.role} | Pharmacy Management System",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED
        )
        subtitle_label.pack(side="right", padx=20, pady=15)

        # ----------------------------------------------------
        # 1. KPI Cards Section
        # ----------------------------------------------------
        self.kpi_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.kpi_frame.pack(fill="x", pady=(0, 20))

        # We will create 5 KPI Cards in a responsive grid
        self.card_widgets = {}
        kpi_specs = [
            ("total_medicines", "Total Medicines", "0", Theme.PRIMARY),
            ("total_stock_quantity", "Total Stock Units", "0", Theme.SECONDARY),
            ("low_stock_count", "Low Stock Alert (<=10)", "0", Theme.WARNING),
            ("expiring_soon_count", "Expiring Soon (<30d)", "0", Theme.WARNING),
            ("total_sales_amount", "Total Sales Value", "₹0.00", Theme.SUCCESS)
        ]

        for idx, (key, title, default_val, color) in enumerate(kpi_specs):
            card = ctk.CTkFrame(
                self.kpi_frame,
                fg_color=Theme.BG_CARD,
                corner_radius=12,
                border_width=1,
                border_color=Theme.BORDER_COLOR
            )
            card.grid(row=0, column=idx, padx=6, pady=5, sticky="nsew")
            self.kpi_frame.columnconfigure(idx, weight=1)

            lbl_title = ctk.CTkLabel(
                card,
                text=title,
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_MUTED
            )
            lbl_title.pack(pady=(12, 2), padx=10)

            lbl_val = ctk.CTkLabel(
                card,
                text=default_val,
                font=Theme.FONT_TITLE,
                text_color=color
            )
            lbl_val.pack(pady=(0, 12), padx=10)

            self.card_widgets[key] = lbl_val

        # ----------------------------------------------------
        # 2. Q13 Quick Search Section
        # ----------------------------------------------------
        search_card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=14,
            border_width=1,
            border_color=Theme.PRIMARY
        )
        search_card.pack(fill="both", expand=True, pady=(0, 10))

        # Search Header
        search_header = ctk.CTkFrame(search_card, fg_color="transparent")
        search_header.pack(fill="x", padx=20, pady=(15, 5))

        q13_title = ctk.CTkLabel(
            search_header,
            text="⚡ Quick Search & Retrieval",
            font=Theme.FONT_HEADING,
            text_color=Theme.PRIMARY
        )
        q13_title.pack(side="left")

        self.perf_metric_lbl = ctk.CTkLabel(
            search_header,
            text="Query latency: 0.000 ms",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        )
        q13_title_sub = ctk.CTkLabel(
            search_card,
            text="Find medicines instantly by name, medicine code, category or manufacturer with live debounced search.",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            anchor="w"
        )
        q13_title_sub.pack(fill="x", padx=20, pady=(0, 10))

        self.perf_metric_lbl.pack(side="right")

        # Search Entry Bar
        search_entry_frame = ctk.CTkFrame(search_card, fg_color="transparent")
        search_entry_frame.pack(fill="x", padx=20, pady=(0, 10))

        self.search_entry = ctk.CTkEntry(
            search_entry_frame,
            placeholder_text="🔍 Type medicine name, code, category or manufacturer (e.g. 'para', 'amox', 'Cipla')...",
            height=44,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.PRIMARY,
            border_width=1,
            text_color=Theme.TEXT_MAIN
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_entry.bind("<KeyRelease>", self._on_key_release)

        clear_btn = ctk.CTkButton(
            search_entry_frame,
            text="Clear",
            width=80,
            height=44,
            font=Theme.FONT_BOLD,
            fg_color=Theme.BG_HEADER,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self._clear_search
        )
        clear_btn.pack(side="right")

        # Scrollable Suggestions / Results Panel
        self.results_scroll_frame = ctk.CTkScrollableFrame(
            search_card,
            fg_color=Theme.BG_DARK,
            corner_radius=10,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        self.results_scroll_frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        self._show_initial_search_prompt()

    def refresh(self) -> None:
        """Refreshes KPI metrics from SQLite database via MedicineService."""
        summary = self.medicine_service.get_inventory_summary()
        self.card_widgets["total_medicines"].configure(text=str(summary["total_medicines"]))
        self.card_widgets["total_stock_quantity"].configure(text=str(summary["total_stock_quantity"]))
        self.card_widgets["low_stock_count"].configure(text=str(summary["low_stock_count"]))
        self.card_widgets["expiring_soon_count"].configure(text=str(summary["expiring_soon_count"]))
        self.card_widgets["total_sales_amount"].configure(text=f"₹{summary['total_sales_amount']:.2f}")

    def _on_key_release(self, event) -> None:
        """
        Keystroke handler with 250ms debouncing mechanism using Tkinter after_cancel().
        Prevents redundant SQL queries during active typing.
        """
        # Cancel any pending timer
        if self._search_timer_id:
            self.after_cancel(self._search_timer_id)

        # Schedule search execution after 250ms
        self._search_timer_id = self.after(250, self._perform_search)

    def _clear_search(self) -> None:
        """Clears search entry and resets results view."""
        if self._search_timer_id:
            self.after_cancel(self._search_timer_id)
        self.search_entry.delete(0, "end")
        self.perf_metric_lbl.configure(text="Query latency: 0.000 ms")
        self._show_initial_search_prompt()

    def _show_initial_search_prompt(self) -> None:
        """Displays initial guidance text when search box is empty."""
        for widget in self.results_scroll_frame.winfo_children():
            widget.destroy()

        prompt_lbl = ctk.CTkLabel(
            self.results_scroll_frame,
            text="Type in the search bar above to see instant live results matching medicines...",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED
        )
        prompt_lbl.pack(pady=40)

    def _perform_search(self) -> None:
        """Executes the search query via SearchService and renders matching items."""
        query_text = self.search_entry.get().strip()

        if not query_text:
            self._show_initial_search_prompt()
            self.perf_metric_lbl.configure(text="Query latency: 0.000 ms")
            return

        # Execute search and measure latency
        start_t = time.perf_counter()
        medicines, latency_ms = self.search_service.search_medicines(query_text=query_text, limit=30)
        
        self.perf_metric_lbl.configure(text=f"Query latency: {latency_ms:.3f} ms | Found: {len(medicines)}")

        # Log Activity
        self.logger.log_search_query({"quick_search": query_text}, latency_ms, len(medicines))

        # Clear existing result cards
        for widget in self.results_scroll_frame.winfo_children():
            widget.destroy()

        if not medicines:
            no_res_lbl = ctk.CTkLabel(
                self.results_scroll_frame,
                text=f"No medicines found matching '{query_text}'.",
                font=Theme.FONT_BODY,
                text_color=Theme.DANGER
            )
            no_res_lbl.pack(pady=30)
            return

        # Render Matching Medicine Result Items
        for med in medicines:
            self._render_medicine_result_card(med)

    def _render_medicine_result_card(self, med: Medicine) -> None:
        """Renders an interactive search result card with badge indicators."""
        card = ctk.CTkFrame(
            self.results_scroll_frame,
            fg_color=Theme.BG_CARD,
            corner_radius=8,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.pack(fill="x", padx=5, pady=4)

        # Left Info Block: Name, Code, Category, Manufacturer
        info_block = ctk.CTkFrame(card, fg_color="transparent")
        info_block.pack(side="left", fill="both", expand=True, padx=12, pady=8)

        name_lbl = ctk.CTkLabel(
            info_block,
            text=f"{med.medicine_name}  ({med.medicine_code})",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        )
        name_lbl.pack(anchor="w")

        sub_info = f"Category: {med.category}  |  Manufacturer: {med.manufacturer}  |  Batch: {med.batch_no}"
        sub_lbl = ctk.CTkLabel(
            info_block,
            text=sub_info,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            anchor="w"
        )
        sub_lbl.pack(anchor="w", pady=(2, 0))

        # Right Block: Badges, Price, View Details Button
        right_block = ctk.CTkFrame(card, fg_color="transparent")
        right_block.pack(side="right", padx=12, pady=8)

        # Badges
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

        exp_color = Theme.get_expiry_color(med.expiry_status)
        exp_badge = ctk.CTkLabel(
            right_block,
            text=f" {med.expiry_status} ",
            font=Theme.FONT_SMALL,
            fg_color=exp_color,
            text_color=Theme.TEXT_DARK,
            corner_radius=4
        )
        exp_badge.pack(side="left", padx=4)

        price_lbl = ctk.CTkLabel(
            right_block,
            text=f"₹{med.price:.2f}",
            font=Theme.FONT_HEADING,
            text_color=Theme.PRIMARY
        )
        price_lbl.pack(side="left", padx=12)

        view_btn = ctk.CTkButton(
            right_block,
            text="View Details",
            width=90,
            height=28,
            font=Theme.FONT_SMALL,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=lambda m=med: self._open_medicine_details(m)
        )
        view_btn.pack(side="left", padx=4)

    def _open_medicine_details(self, med: Medicine) -> None:
        """Opens modal dialog displaying medicine details without leaving the dashboard."""
        MedicineDetailModal(self, med)
