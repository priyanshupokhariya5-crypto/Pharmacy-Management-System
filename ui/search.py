"""
Q13 Advanced Search & Retrieval View.
Implements multi-criteria search filters, whitelisted SQL sorting, live debounced search toggle,
measured SQL query execution timing, and Q13 quality indicators.
"""
import time
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict, Any
import customtkinter as ctk

from ui.theme import Theme
from ui.dashboard import MedicineDetailModal
from services.search_service import SearchService
from services.medicine_service import MedicineService
from models.medicine import Medicine
from models.user import User
from utils.logger import get_app_logger


class AdvancedSearchView(ctk.CTkFrame):
    """Q13 Advanced Search & Retrieval Screen providing full multi-parameter search capabilities."""

    def __init__(self, parent, user: User):
        super().__init__(parent, fg_color="transparent")
        self.user = user
        self.search_service = SearchService()
        self.medicine_service = MedicineService()
        self.logger = get_app_logger()

        # Debounce timer reference
        self._debounce_timer = None

        self._build_ui()
        self.populate_dropdowns()
        self.execute_search()

    def _build_ui(self) -> None:
        """Constructs header, multi-filter control panel, results treeview, and metrics panel."""
        # ----------------------------------------------------
        # 1. Header Banner
        # ----------------------------------------------------
        header_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12)
        header_card.pack(fill="x", pady=(0, 10))

        title_lbl = ctk.CTkLabel(
            header_card,
            text="⚡ Advanced Search & Retrieval",
            font=Theme.FONT_TITLE,
        )
        title_lbl.pack(side="left", padx=20, pady=(12, 2))

        sub_lbl = ctk.CTkLabel(
            header_card,
            text="Fast, multi-criteria medicine search, whitelisted sorting, and parameterized query execution.",
            font=Theme.FONT_SMALL, 
        )
        sub_lbl.pack(side="left", padx=20, pady=(0, 12))

        # ----------------------------------------------------
        # 2. Filter & Controls Panel
        # ----------------------------------------------------
        filter_card = ctk.CTkFrame(
            self,
            corner_radius=12,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        filter_card.pack(fill="x", pady=(0, 10))

        # Row 1: Text Search Bar + Live Search Checkbox
        row1 = ctk.CTkFrame(filter_card, fg_color="transparent")
        row1.pack(fill="x", padx=15, pady=(12, 6))

        text_lbl = ctk.CTkLabel(row1, text="Text Search:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN)
        text_lbl.pack(side="left", padx=(0, 8))

        self.text_entry = ctk.CTkEntry(
            row1,
            placeholder_text="Search by name, code, category, manufacturer (e.g. 'para', 'amox', 'Cipla')...",
            height=36,
            font=Theme.FONT_BODY,
            border_color=Theme.PRIMARY,
        )
        self.text_entry.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.text_entry.bind("<KeyRelease>", self._on_text_key_release)
        self.text_entry.bind("<Return>", lambda e: self.execute_search())

        # Live Search Toggle
        self.live_search_var = tk.BooleanVar(value=True)
        self.live_search_cb = ctk.CTkCheckBox(
            row1,
            text="Live Search (250ms Debounce)",
            variable=self.live_search_var,
            font=Theme.FONT_SMALL, 
            checkbox_width=18,
            checkbox_height=18,
            border_color=Theme.BORDER_COLOR
        )
        self.live_search_cb.pack(side="right")

        # Row 2: Category, Manufacturer, Stock Status, Expiry Status
        row2 = ctk.CTkFrame(filter_card, fg_color="transparent")
        row2.pack(fill="x", padx=15, pady=(0, 6))

        # Category
        ctk.CTkLabel(row2, text="Category:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.cat_menu = ctk.CTkOptionMenu(
            row2,
            values=["All"],
            width=135,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self._trigger_filter_change()
        )
        self.cat_menu.pack(side="left", padx=(0, 12))

        # Manufacturer
        ctk.CTkLabel(row2, text="Manufacturer:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.mfr_menu = ctk.CTkOptionMenu(
            row2,
            values=["All"],
            width=135,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self._trigger_filter_change()
        )
        self.mfr_menu.pack(side="left", padx=(0, 12))

        # Stock Status
        ctk.CTkLabel(row2, text="Stock Status:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.stock_menu = ctk.CTkOptionMenu(
            row2,
            values=["All", "Available", "Low Stock", "Out of Stock"],
            width=120,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self._trigger_filter_change()
        )
        self.stock_menu.pack(side="left", padx=(0, 12))

        # Expiry Status
        ctk.CTkLabel(row2, text="Expiry Status:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.exp_menu = ctk.CTkOptionMenu(
            row2,
            values=["All", "Valid", "Expiring Soon", "Expired"],
            width=120,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self._trigger_filter_change()
        )
        self.exp_menu.pack(side="left")

        # Row 3: Price Range, Whitelisted Sorting & Buttons
        row3 = ctk.CTkFrame(filter_card, fg_color="transparent")
        row3.pack(fill="x", padx=15, pady=(0, 12))

        # Price Range
        ctk.CTkLabel(row3, text="Price Range (₹):", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.min_price_entry = ctk.CTkEntry(
            row3,
            placeholder_text="Min",
            width=65,
            height=32,
            font=Theme.FONT_SMALL, 
            border_color=Theme.BORDER_COLOR
        )
        self.min_price_entry.pack(side="left", padx=(0, 4))

        ctk.CTkLabel(row3, text="-", font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(side="left", padx=2)

        self.max_price_entry = ctk.CTkEntry(
            row3,
            placeholder_text="Max",
            width=65,
            height=32,
            font=Theme.FONT_SMALL, 
            border_color=Theme.BORDER_COLOR
        )
        self.max_price_entry.pack(side="left", padx=(0, 15))

        # Sorting Controls
        ctk.CTkLabel(row3, text="Sort By:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.sort_field_menu = ctk.CTkOptionMenu(
            row3,
            values=["Medicine Name", "Price", "Quantity", "Expiry Date"],
            width=135,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self._trigger_filter_change()
        )
        self.sort_field_menu.pack(side="left", padx=(0, 6))

        self.sort_order_menu = ctk.CTkOptionMenu(
            row3,
            values=["Ascending", "Descending"],
            width=110,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self._trigger_filter_change()
        )
        self.sort_order_menu.pack(side="left", padx=(0, 15))

        # Buttons
        search_btn = ctk.CTkButton(
            row3,
            text="🔎 Search Medicines",
            font=Theme.FONT_BOLD,
            height=34,
            hover_color=Theme.PRIMARY_HOVER,
            command=self.execute_search
        )
        search_btn.pack(side="left", padx=(0, 8))

        clear_btn = ctk.CTkButton(
            row3,
            text="Clear Filters",
            font=Theme.FONT_BODY,
            height=34,
            width=90,
            hover_color=Theme.BORDER_COLOR,
            command=self.clear_filters
        )
        clear_btn.pack(side="left")

        # ----------------------------------------------------
        # 3. Results Table Area
        # ----------------------------------------------------
        results_container = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=10)
        results_container.pack(fill="both", expand=True, pady=(0, 10))

        # Style Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Search.Treeview",
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_MAIN,
            fieldbackground=Theme.BG_CARD,
            rowheight=30,
            font=("Segoe UI", 10)
        )
        style.configure(
            "Search.Treeview.Heading",
            background=Theme.INPUT_BG,
            foreground=Theme.TEXT_MAIN,
            font=("Segoe UI", 10, "bold")
        )
        style.map(
            "Search.Treeview",
            background=[("selected", Theme.PRIMARY)],
            foreground=[("selected", Theme.TEXT_DARK)]
        )

        columns = (
            "id", "code", "name", "category", "manufacturer",
            "batch", "price", "quantity", "expiry", "stock_status", "expiry_status"
        )
        self.tree = ttk.Treeview(
            results_container,
            columns=columns,
            show="headings",
            style="Search.Treeview",
            selectmode="browse",
            height=20
        )

        headers = [
            ("id", "ID", 40),
            ("code", "Code", 90),
            ("name", "Medicine Name", 190),
            ("category", "Category", 115),
            ("manufacturer", "Manufacturer", 125),
            ("batch", "Batch No", 80),
            ("price", "Price (₹)", 80),
            ("quantity", "Qty", 65),
            ("expiry", "Expiry Date", 95),
            ("stock_status", "Stock Status", 105),
            ("expiry_status", "Expiry Status", 105)
        ]

        for col_id, title, width in headers:
            self.tree.heading(col_id, text=title)
            self.tree.column(col_id, width=width, minwidth=40, anchor="center" if col_id in ("id", "code", "batch", "price", "quantity", "expiry", "stock_status", "expiry_status") else "w")

        vsb = ttk.Scrollbar(results_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(results_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        results_container.grid_rowconfigure(0, weight=1)
        results_container.grid_columnconfigure(0, weight=1)

        # Double click to open detail modal
        self.tree.bind("<Double-1>", lambda e: self._open_selected_details())

        # ----------------------------------------------------
        # 4. Bottom Metrics & Q13 Info Card
        # ----------------------------------------------------
        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x")

        # Left Info: Result Count & Measured Execution Time
        self.count_lbl = ctk.CTkLabel(
            bottom_frame,
            text="Results Found: 0",
            font=Theme.FONT_HEADING,
        )
        self.count_lbl.pack(side="left", padx=10)

        self.query_time_lbl = ctk.CTkLabel(
            bottom_frame,
            text="SQL Query Time: 0.000 ms",
            font=Theme.FONT_SUBHEADING,
        )
        self.query_time_lbl.pack(side="left", padx=20)

        view_detail_btn = ctk.CTkButton(
            bottom_frame,
            text="🔍 View Details",
            font=Theme.FONT_BOLD,
            height=30,
            width=110,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._open_selected_details
        )
        view_detail_btn.pack(side="right", padx=10)

        # Q13 Academic Information Footer
        q13_info_card = ctk.CTkFrame(
            self,
            corner_radius=8,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        q13_info_card.pack(fill="x", pady=(8, 0))

        info_text = (
            "🎯 Q13 Quality Objective: Reduce medicine retrieval effort by providing fast, multi-criteria search, sorting, "
            "and database query optimization. | Method: Parameterized SQL | Indexed Fields: Name, Category, Manufacturer, Expiry Date, Code"
        )
        q13_info_lbl = ctk.CTkLabel(
            q13_info_card,
            text=info_text,
            font=Theme.FONT_SMALL, 
            anchor="w"
        )
        q13_info_lbl.pack(padx=15, pady=6, fill="x")

    def populate_dropdowns(self) -> None:
        """Populates category and manufacturer filter dropdowns dynamically from DB."""
        categories = ["All"] + self.medicine_service.get_categories()
        manufacturers = ["All"] + self.medicine_service.get_manufacturers()

        self.cat_menu.configure(values=categories)
        self.mfr_menu.configure(values=manufacturers)

    def _on_text_key_release(self, event) -> None:
        """Keystroke handler supporting debounced live search when checkbox is enabled."""
        if not self.live_search_var.get():
            return

        if self._debounce_timer:
            self.after_cancel(self._debounce_timer)
        self._debounce_timer = self.after(250, self.execute_search)

    def _trigger_filter_change(self) -> None:
        """Triggers search execution when dropdown filters change."""
        self.execute_search()

    def clear_filters(self) -> None:
        """Resets all filter inputs and re-executes clean query."""
        if self._debounce_timer:
            self.after_cancel(self._debounce_timer)

        self.text_entry.delete(0, "end")
        self.cat_menu.set("All")
        self.mfr_menu.set("All")
        self.stock_menu.set("All")
        self.exp_menu.set("All")
        self.min_price_entry.delete(0, "end")
        self.max_price_entry.delete(0, "end")
        self.sort_field_menu.set("Medicine Name")
        self.sort_order_menu.set("Ascending")
        self.execute_search()

    def validate_price_inputs(self) -> tuple[Optional[float], Optional[float], Optional[str]]:
        """
        Validates price range entries.
        Returns (min_price, max_price, error_message).
        """
        min_str = self.min_price_entry.get().strip()
        max_str = self.max_price_entry.get().strip()
        min_val = None
        max_val = None

        if min_str:
            try:
                min_val = float(min_str)
                if min_val < 0:
                    return None, None, "Minimum price cannot be negative."
            except ValueError:
                return None, None, "Minimum price must be a valid number (e.g. 10.0)."

        if max_str:
            try:
                max_val = float(max_str)
                if max_val < 0:
                    return None, None, "Maximum price cannot be negative."
            except ValueError:
                return None, None, "Maximum price must be a valid number (e.g. 100.0)."

        if min_val is not None and max_val is not None:
            if min_val > max_val:
                return None, None, "Minimum price cannot be greater than maximum price."

        return min_val, max_val, None

    def execute_search(self) -> None:
        """Validates filter inputs, executes parameterized search via SearchService, and populates Treeview."""
        # 1. Price Range Validation
        price_min, price_max, err_msg = self.validate_price_inputs()
        if err_msg:
            messagebox.showwarning("Filter Validation Error", err_msg)
            self.logger.log_poka_yoke("Search Filter Validation", f"Blocked: {err_msg}")
            return

        # 2. Extract Filter Values
        query_text = self.text_entry.get().strip()
        cat = self.cat_menu.get()
        mfr = self.mfr_menu.get()
        stock_st = self.stock_menu.get()
        exp_st = self.exp_menu.get()

        # Map UI Sort Field & Order to Whitelisted Service Parameters
        field_map = {
            "Medicine Name": "medicine_name",
            "Price": "price",
            "Quantity": "quantity",
            "Expiry Date": "expiry_date"
        }
        sort_field = field_map.get(self.sort_field_menu.get(), "medicine_name")
        sort_order = "ASC" if self.sort_order_menu.get() == "Ascending" else "DESC"

        # 3. Execute Search with Measurement
        medicines, latency_ms = self.search_service.search_medicines(
            query_text=query_text,
            category=cat,
            manufacturer=mfr,
            stock_status=stock_st,
            price_min=price_min,
            price_max=price_max,
            expiry_status=exp_st,
            sort_field=sort_field,
            sort_order=sort_order,
            limit=500
        )

        # 4. Render Results in Treeview
        for item in self.tree.get_children():
            self.tree.delete(item)

        for med in medicines:
            self.tree.insert(
                "",
                "end",
                iid=str(med.medicine_id),
                values=(
                    med.medicine_id,
                    med.medicine_code,
                    med.medicine_name,
                    med.category,
                    med.manufacturer,
                    med.batch_no,
                    f"₹{med.price:.2f}",
                    med.quantity,
                    med.expiry_date,
                    med.stock_status,
                    med.expiry_status
                )
            )

        # 5. Update Status Counters & Measured Execution Time
        self.count_lbl.configure(text=f"Results Found: {len(medicines)}")
        self.query_time_lbl.configure(text=f"SQL Query Time: {latency_ms:.3f} ms")

        # Log Search activity
        filter_summary = {
            "query": query_text,
            "category": cat,
            "manufacturer": mfr,
            "stock": stock_st,
            "expiry": exp_st,
            "price_range": f"{price_min}-{price_max}",
            "sort": f"{sort_field} {sort_order}"
        }
        self.logger.log_search_query(filter_summary, latency_ms, len(medicines))

    def _open_selected_details(self) -> None:
        """Opens MedicineDetailModal for the selected record in Treeview."""
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("Select Result", "Please select a medicine record from the table to view details.")
            return

        med_id = int(selected_items[0])
        med = self.medicine_service.get_medicine_by_id(med_id)
        if med:
            MedicineDetailModal(self, med)
