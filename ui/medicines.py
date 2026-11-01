"""
Medicine Inventory Management View & Modal Dialogs.
Provides complete CRUD functionality (Create, Read, Update, Delete), multi-parameter filtering,
column sorting, role-based permission checks, and Poka-Yoke error prevention validation.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from typing import Optional, List, Dict, Any
import customtkinter as ctk

from ui.theme import Theme
from services.medicine_service import MedicineService
from services.search_service import SearchService
from models.medicine import Medicine
from models.user import User
from utils.logger import get_app_logger


class MedicineFormModal(ctk.CTkToplevel):
    """Modal dialog for Adding or Editing a medicine record with strict input validation."""

    def __init__(self, parent, user: User, medicine: Optional[Medicine] = None, on_success_callback=None):
        super().__init__(parent)
        self.user = user
        self.medicine = medicine
        self.on_success_callback = on_success_callback
        store_id = getattr(self.user, 'store_id', 'STORE-LEGACY-001')
        self.medicine_service = MedicineService(store_id=store_id)
        self.logger = get_app_logger()

        self.is_edit_mode = medicine is not None
        title_text = f"Edit Medicine - {medicine.medicine_name}" if self.is_edit_mode else "Add New Medicine"
        
        self.title(title_text)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        modal_w = 520
        modal_h = min(620, max(460, int(screen_h * 0.82)))
        x = max(0, (screen_w - modal_w) // 2)
        y = max(0, (screen_h - modal_h) // 2)
        self.geometry(f"{modal_w}x{modal_h}+{x}+{y}")
        self.minsize(440, 420)
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_DARK)

        # Make modal stay on top & grab focus
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    def _build_ui(self) -> None:
        """Constructs form fields and buttons."""
        card = ctk.CTkFrame(
            self,
            corner_radius=14,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.pack(padx=20, pady=20, fill="both", expand=True)

        header_text = "Edit Medicine Record" if self.is_edit_mode else "Add Medicine Record"
        header_lbl = ctk.CTkLabel(
            card,
            text=header_text,
            font=Theme.FONT_TITLE,
        )
        header_lbl.pack(pady=(15, 2))

        sub_lbl = ctk.CTkLabel(
            card,
            text="All fields are required. Poka-Yoke error prevention enabled.",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        )
        sub_lbl.pack(pady=(0, 10))

        # Status Error Label
        self.err_label = ctk.CTkLabel(
            card,
            text="",
            font=Theme.FONT_SMALL,
            text_color=Theme.DANGER,
            wraplength=440
        )
        self.err_label.pack(pady=(0, 5))



        # Action Buttons (Fixed Footer at bottom)
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=15, pady=(0, 15))

        save_btn_text = "Update Medicine" if self.is_edit_mode else "Save Medicine"
        self.save_btn = ctk.CTkButton(
            btn_frame,
            text=save_btn_text,
            font=Theme.FONT_BOLD,
            height=38,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self._save_medicine
        )
        self.save_btn.pack(side="right", padx=(5, 0), expand=True, fill="x")

        self.cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            font=Theme.FONT_BODY,
            height=38,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self.destroy
        )
        self.cancel_btn.pack(side="left", padx=(0, 5), expand=True, fill="x")

        # Form Scrollable Area (Middle - fills remaining space)
        form_frame = ctk.CTkScrollableFrame(card, fg_color="transparent")
        form_frame.pack(side="top", fill="both", expand=True, padx=15, pady=(0, 10))

        # Form Fields Configuration
        self.entries: Dict[str, ctk.CTkEntry] = {}
        from datetime import datetime
        today_iso = datetime.now().strftime("%Y-%m-%d")

        fields = [
            ("code", "Medicine Code (Unique)*", "e.g. MED1017"),
            ("name", "Medicine Name*", "e.g. Dolo 650mg"),
            ("category", "Category*", "e.g. Analgesic"),
            ("manufacturer", "Manufacturer*", "e.g. Micro Labs"),
            ("batch", "Batch Number*", "e.g. B202615"),
            ("price", "Selling Price (₹)*", "e.g. 15.50"),
            ("quantity", "Stock Quantity*", "e.g. 100"),
            ("mfg", "Manufacturing Date (YYYY-MM-DD)*", f"e.g. {today_iso}"),
            ("expiry", "Expiry Date (YYYY-MM-DD)*", "e.g. 2027-06-30")
        ]

        for key, label_text, placeholder in fields:
            lbl = ctk.CTkLabel(
                form_frame,
                text=label_text,
                font=Theme.FONT_BOLD,
                anchor="w"
            )
            lbl.pack(fill="x", pady=(5, 1))

            entry = ctk.CTkEntry(
                form_frame,
                placeholder_text=placeholder,
                height=34,
                font=Theme.FONT_BODY,
                border_color=Theme.BORDER_COLOR,
            )
            entry.pack(fill="x", pady=(0, 5))
            self.entries[key] = entry

        # Shelf / Rack Location (Combobox + manual entry)
        shelf_lbl = ctk.CTkLabel(
            form_frame,
            text="Shelf / Rack Location (Required)*",
            font=Theme.FONT_BOLD,
            anchor="w"
        )
        shelf_lbl.pack(fill="x", pady=(5, 1))

        shelf_options = ["SHELF-A01", "SHELF-A02", "SHELF-B01", "SHELF-B02", "SHELF-COLD", "SHELF-QUAR"]
        self.shelf_combo = ctk.CTkComboBox(
            form_frame,
            values=shelf_options,
            height=34,
            font=Theme.FONT_BODY,
            border_color=Theme.BORDER_COLOR
        )
        self.shelf_combo.set("SHELF-A01")
        self.shelf_combo.pack(fill="x", pady=(0, 8))
        # Pre-populate fields if in Edit Mode
        if self.is_edit_mode and self.medicine:
            self.entries["code"].insert(0, self.medicine.medicine_code)
            self.entries["name"].insert(0, self.medicine.medicine_name)
            self.entries["category"].insert(0, self.medicine.category)
            self.entries["manufacturer"].insert(0, self.medicine.manufacturer)
            self.entries["batch"].insert(0, self.medicine.batch_no)
            self.entries["price"].insert(0, str(self.medicine.price))
            self.entries["quantity"].insert(0, str(self.medicine.quantity))
            self.entries["mfg"].insert(0, today_iso)
            self.entries["expiry"].insert(0, self.medicine.expiry_date)
            # Pre-select shelf if found
            if hasattr(self.medicine_service, "db") and self.medicine_service.db:
                b_row = self.medicine_service.db.fetch_one(
                    """
                    SELECT sl.shelf_code FROM inventory_batches b
                    JOIN storage_locations sl ON b.location_id = sl.location_id
                    WHERE b.medicine_id = ? AND b.store_id = ?
                    ORDER BY b.expiry_date ASC LIMIT 1
                    """,
                    (self.medicine.medicine_id, getattr(self.user, "store_id", "STORE-LEGACY-001"))
                )
                if b_row and b_row["shelf_code"]:
                    self.shelf_combo.set(b_row["shelf_code"])
        else:
            self.entries["mfg"].insert(0, today_iso)

    def _save_medicine(self) -> None:
        """Validates inputs and performs Add or Update database operation."""
        code = self.entries["code"].get().strip()
        name = self.entries["name"].get().strip()
        category = self.entries["category"].get().strip()
        manufacturer = self.entries["manufacturer"].get().strip()
        batch = self.entries["batch"].get().strip()
        price_raw = self.entries["price"].get().strip()
        qty_raw = self.entries["quantity"].get().strip()
        mfg_date = self.entries["mfg"].get().strip()
        expiry = self.entries["expiry"].get().strip()
        shelf = self.shelf_combo.get().strip()

        # Poka-Yoke Validation Checks
        errors = []
        if not code:
            errors.append("Medicine code is required.")
        if not name:
            errors.append("Medicine name is required.")
        if not category:
            errors.append("Category is required.")
        if not manufacturer:
            errors.append("Manufacturer is required.")
        if not batch:
            errors.append("Batch number is required.")
        if not shelf:
            errors.append("Shelf / Rack Location is required.")

        try:
            price_val = float(price_raw)
            if price_val < 0:
                errors.append("Price cannot be negative.")
        except ValueError:
            errors.append("Price must be a valid numeric number (e.g. 15.50).")

        try:
            qty_val = int(qty_raw)
            if qty_val < 0:
                errors.append("Quantity cannot be negative.")
        except ValueError:
            errors.append("Quantity must be a valid integer number (e.g. 100).")

        mfg_dt = None
        if not mfg_date:
            errors.append("Manufacturing date is required (YYYY-MM-DD).")
        else:
            try:
                mfg_dt = datetime.strptime(mfg_date, "%Y-%m-%d")
            except ValueError:
                errors.append("Manufacturing date must be a valid date in YYYY-MM-DD format.")

        exp_dt = None
        if not expiry:
            errors.append("Expiry date is required (YYYY-MM-DD).")
        else:
            try:
                exp_dt = datetime.strptime(expiry, "%Y-%m-%d")
            except ValueError:
                errors.append("Expiry date must be a valid date in YYYY-MM-DD format.")

        if mfg_dt and exp_dt:
            if exp_dt <= mfg_dt:
                errors.append("Expiry date must be strictly later than manufacturing date.")

        if errors:
            err_msg = "\n".join(errors)
            self.err_label.configure(text=err_msg)
            self.logger.log_poka_yoke("Medicine Form Validation", f"Blocked invalid entry: {err_msg}")
            return

        # Construct Medicine object
        med_id = self.medicine.medicine_id if self.is_edit_mode and self.medicine else None
        med_obj = Medicine(
            medicine_id=med_id,
            medicine_code=code,
            medicine_name=name,
            category=category,
            manufacturer=manufacturer,
            batch_no=batch,
            price=float(price_raw),
            quantity=int(qty_raw),
            expiry_date=expiry
        )

        # Execute DB Operation
        if self.is_edit_mode:
            success, msg = self.medicine_service.update_medicine(
                med_obj, shelf_code=shelf, acting_user=self.user
            )
        else:
            success, msg = self.medicine_service.add_medicine(
                med_obj, shelf_code=shelf, mfg_date=mfg_date, acting_user=self.user
            )

        if success:
            self.logger.log_event("INVENTORY", f"Medicine '{name}' ({code}) {'updated' if self.is_edit_mode else 'added'} by '{self.user.username}'")
            messagebox.showinfo("Success", msg)
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        else:
            self.err_label.configure(text=msg)
            self.logger.log_poka_yoke("Medicine DB Operation", f"Failed: {msg}")


class MedicinesView(ctk.CTkFrame):
    """Medicines Inventory Management View providing complete Treeview table CRUD, filters, and sorting."""

    def __init__(self, parent, user: User):
        super().__init__(parent, fg_color="transparent")
        self.user = user
        store_id = getattr(self.user, 'store_id', 'STORE-LEGACY-001')
        self.medicine_service = MedicineService(store_id=store_id)
        self.search_service = SearchService(store_id=store_id)
        self.logger = get_app_logger()

        # Sorting Whitelist state
        self.current_sort_col = "medicine_name"
        self.sort_ascending = True

        self._build_ui()
        self.refresh_table()

    def _build_ui(self) -> None:
        """Constructs top header, action toolbar, filter controls, and Treeview table."""
        # ----------------------------------------------------
        # 1. Header Banner
        # ----------------------------------------------------
        header_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12)
        header_card.pack(fill="x", pady=(0, 10))

        title_lbl = ctk.CTkLabel(
            header_card,
            text="💊 Medicine Inventory Management",
            font=Theme.FONT_TITLE,
        )
        title_lbl.pack(side="left", padx=20, pady=12)

        self.records_lbl = ctk.CTkLabel(
            header_card,
            text="Total Records: 0",
            font=Theme.FONT_SUBHEADING,
        )
        self.records_lbl.pack(side="right", padx=20, pady=12)

        # ----------------------------------------------------
        # 2. Action Toolbar (Add, Edit, Delete, Refresh)
        # ----------------------------------------------------
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", pady=(0, 10))

        add_btn = ctk.CTkButton(
            toolbar,
            text="➕ Add Medicine",
            font=Theme.FONT_BOLD,
            height=36,
            hover_color="#8ed087",
            command=self._on_add_medicine
        )
        add_btn.pack(side="left", padx=(0, 8))

        edit_btn = ctk.CTkButton(
            toolbar,
            text="✏️ Edit Medicine",
            font=Theme.FONT_BOLD,
            height=36,
            hover_color=Theme.PRIMARY_HOVER,
            command=self._on_edit_medicine
        )
        edit_btn.pack(side="left", padx=(0, 8))

        delete_btn = ctk.CTkButton(
            toolbar,
            text="🗑️ Delete Medicine",
            font=Theme.FONT_BOLD,
            height=36,
            hover_color="#e05f7e",
            command=self._on_delete_medicine
        )
        delete_btn.pack(side="left", padx=(0, 8))

        refresh_btn = ctk.CTkButton(
            toolbar,
            text="🔄 Refresh",
            font=Theme.FONT_BODY,
            height=36,
            width=90,
            hover_color=Theme.BORDER_COLOR,
            command=self.refresh_table
        )
        refresh_btn.pack(side="right")

        # ----------------------------------------------------
        # 3. Filter Bar (Search Text, Category, Manufacturer, Stock Status, Expiry Status)
        # ----------------------------------------------------
        filter_card = ctk.CTkFrame(
            self,
            corner_radius=10,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        filter_card.pack(fill="x", pady=(0, 10))

        filter_row = ctk.CTkFrame(filter_card, fg_color="transparent")
        filter_row.pack(fill="x", padx=12, pady=10)

        # Search Entry
        self.search_entry = ctk.CTkEntry(
            filter_row,
            placeholder_text="🔍 Filter by name / code...",
            width=180,
            height=32,
            font=Theme.FONT_BODY,
            border_color=Theme.BORDER_COLOR
        )
        self.search_entry.pack(side="left", padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self.apply_filters())

        # Category Dropdown
        cat_lbl = ctk.CTkLabel(filter_row, text="Category:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
        cat_lbl.pack(side="left", padx=(4, 2))
        
        self.cat_menu = ctk.CTkOptionMenu(
            filter_row,
            values=["All"],
            width=120,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self.apply_filters()
        )
        self.cat_menu.pack(side="left", padx=(0, 8))

        # Manufacturer Dropdown
        mfr_lbl = ctk.CTkLabel(filter_row, text="Mfr:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
        mfr_lbl.pack(side="left", padx=(4, 2))

        self.mfr_menu = ctk.CTkOptionMenu(
            filter_row,
            values=["All"],
            width=120,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self.apply_filters()
        )
        self.mfr_menu.pack(side="left", padx=(0, 8))

        # Stock Status Dropdown
        stock_lbl = ctk.CTkLabel(filter_row, text="Stock:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
        stock_lbl.pack(side="left", padx=(4, 2))

        self.stock_menu = ctk.CTkOptionMenu(
            filter_row,
            values=["All", "Available", "Low Stock", "Out of Stock"],
            width=110,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self.apply_filters()
        )
        self.stock_menu.pack(side="left", padx=(0, 8))

        # Expiry Status Dropdown
        exp_lbl = ctk.CTkLabel(filter_row, text="Expiry:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
        exp_lbl.pack(side="left", padx=(4, 2))

        self.exp_menu = ctk.CTkOptionMenu(
            filter_row,
            values=["All", "Valid", "Expiring Soon", "Expired"],
            width=110,
            height=32,
            font=Theme.FONT_SMALL, 
            command=lambda v: self.apply_filters()
        )
        self.exp_menu.pack(side="left", padx=(0, 8))

        # Reset Button
        reset_btn = ctk.CTkButton(
            filter_row,
            text="Reset",
            width=65,
            height=32,
            font=Theme.FONT_SMALL, 
            hover_color=Theme.BORDER_COLOR,
            command=self._reset_filters
        )
        reset_btn.pack(side="right")

        # ----------------------------------------------------
        # 4. Treeview Table Area
        # ----------------------------------------------------
        table_container = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=10)
        table_container.pack(fill="both", expand=True)

        # Style ttk.Treeview for dark theme match
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Medicine.Treeview",
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_MAIN,
            fieldbackground=Theme.BG_CARD,
            rowheight=30,
            font=("Segoe UI", 10),
            bordercolor=Theme.BORDER_COLOR
        )
        style.configure(
            "Medicine.Treeview.Heading",
            background=Theme.INPUT_BG,
            foreground=Theme.TEXT_MAIN,
            font=("Segoe UI", 10, "bold"),
            relief="flat"
        )
        style.map(
            "Medicine.Treeview",
            background=[("selected", Theme.PRIMARY)],
            foreground=[("selected", Theme.TEXT_DARK)]
        )

        columns = (
            "id", "code", "name", "category", "manufacturer",
            "batch", "shelf", "price", "quantity", "expiry", "stock_status", "expiry_status"
        )
        self.tree = ttk.Treeview(
            table_container,
            columns=columns,
            show="headings",
            style="Medicine.Treeview",
            selectmode="browse",
            height=20
        )

        # Column Headers Configuration
        headers = [
            ("id", "ID", 35),
            ("code", "Code ↕", 80),
            ("name", "Medicine Name ↕", 160),
            ("category", "Category ↕", 100),
            ("manufacturer", "Manufacturer ↕", 110),
            ("batch", "Batch No", 80),
            ("shelf", "Shelf / Rack", 85),
            ("price", "Price (₹) ↕", 75),
            ("quantity", "Qty ↕", 55),
            ("expiry", "Expiry Date ↕", 85),
            ("stock_status", "Stock Status", 85),
            ("expiry_status", "Expiry Status", 85)
        ]

        for col_id, title, width in headers:
            self.tree.heading(col_id, text=title, command=lambda c=col_id: self._on_header_click(c))
            self.tree.column(col_id, width=width, minwidth=40, anchor="center" if col_id in ("id", "code", "batch", "price", "quantity", "expiry", "stock_status", "expiry_status") else "w")

        # Scrollbars
        vsb = ttk.Scrollbar(table_container, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

        # Double click handler to view/edit details
        self.tree.bind("<Double-1>", lambda e: self._on_edit_medicine())

    def populate_dropdowns(self) -> None:
        """Populates category and manufacturer filter dropdowns with live DB values while preserving active filter state."""
        curr_cat = self.cat_menu.get() if hasattr(self, "cat_menu") else "All"
        curr_mfr = self.mfr_menu.get() if hasattr(self, "mfr_menu") else "All"

        categories = ["All"] + self.medicine_service.get_categories()
        manufacturers = ["All"] + self.medicine_service.get_manufacturers()

        self.cat_menu.configure(values=categories)
        self.mfr_menu.configure(values=manufacturers)

        if curr_cat in categories:
            self.cat_menu.set(curr_cat)
        else:
            self.cat_menu.set("All")

        if curr_mfr in manufacturers:
            self.mfr_menu.set(curr_mfr)
        else:
            self.mfr_menu.set("All")

    def refresh_table(self) -> None:
        """Reloads medicine records from database and updates dropdowns safely with selection persistence."""
        try:
            self.populate_dropdowns()
            self.apply_filters()
        except Exception as e:
            self.logger.log_poka_yoke("Medicine Refresh Error", f"Failed to refresh medicines: {e}")
            messagebox.showerror("Refresh Error", f"Failed to refresh medicine inventory:\n{e}", parent=self)

    def _reset_filters(self) -> None:
        """Resets all filter controls to default states."""
        self.search_entry.delete(0, "end")
        self.cat_menu.set("All")
        self.mfr_menu.set("All")
        self.stock_menu.set("All")
        self.exp_menu.set("All")
        self.apply_filters()

    def apply_filters(self) -> None:
        """Retrieves filtered and sorted records from SearchService and populates Treeview."""
        # Remember current selection before rebuilding rows
        selected_iids = self.tree.selection()
        prev_selected = selected_iids[0] if selected_iids else None

        text_query = self.search_entry.get().strip()
        cat = self.cat_menu.get()
        mfr = self.mfr_menu.get()
        stock_st = self.stock_menu.get()
        exp_st = self.exp_menu.get()

        # Map current column sort to SearchService sort options
        sort_option_map = {
            "name": "Name A-Z" if self.sort_ascending else "Name Z-A",
            "price": "Price Low-High" if self.sort_ascending else "Price High-Low",
            "quantity": "Quantity Low-High" if self.sort_ascending else "Quantity High-Low",
            "expiry": "Expiry Nearest" if self.sort_ascending else "Expiry Latest",
            "code": "Name A-Z"
        }
        sort_by = sort_option_map.get(self.current_sort_col, "Name A-Z")

        medicines, latency_ms = self.search_service.search_medicines(
            query_text=text_query,
            category=cat,
            manufacturer=mfr,
            stock_status=stock_st,
            expiry_status=exp_st,
            sort_by=sort_by,
            limit=500
        )

        # Clear existing tree rows
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Build batch and shelf resolution map
        shelf_map = {}
        batch_map = {}
        if hasattr(self.medicine_service, "db") and self.medicine_service.db:
            t_check = self.medicine_service.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='inventory_batches'")
            if t_check:
                b_rows = self.medicine_service.db.fetch_all(
                    """
                    SELECT b.medicine_id, b.batch_number, COALESCE(sl.shelf_code, 'SHELF-A01') as shelf_code
                    FROM inventory_batches b
                    LEFT JOIN storage_locations sl ON b.location_id = sl.location_id
                    WHERE b.store_id = ? AND b.status IN ('Active', 'AVAILABLE')
                    ORDER BY (CASE WHEN b.current_quantity > 0 THEN 0 ELSE 1 END), b.expiry_date ASC
                    """,
                    (self.user.store_id,)
                )
                for br in b_rows:
                    m_id = br["medicine_id"]
                    if m_id not in shelf_map:
                        shelf_map[m_id] = br["shelf_code"]
                        batch_map[m_id] = br["batch_number"]

        # Populate treeview with real batch and shelf locations
        for med in medicines:
            real_batch = batch_map.get(med.medicine_id, med.batch_no)
            if real_batch == "INITIAL":
                real_batch = f"BCH-{med.medicine_code}"
            
            shelf_val = shelf_map.get(
                med.medicine_id,
                "SHELF-COLD" if "insulin" in med.medicine_name.lower()
                else ("SHELF-QUAR" if med.is_expired else "SHELF-A01")
            )

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
                    real_batch,
                    shelf_val,
                    f"₹{med.price:.2f}",
                    med.quantity,
                    med.expiry_date,
                    med.stock_status,
                    med.expiry_status
                )
            )

        self.records_lbl.configure(text=f"Showing: {len(medicines)} records")

        # Restore selection if row still exists
        if prev_selected and self.tree.exists(prev_selected):
            self.tree.selection_set(prev_selected)
            self.tree.focus(prev_selected)

    def _on_header_click(self, col_id: str) -> None:
        """Toggles column sorting order for whitelisted sortable columns."""
        whitelisted_cols = ["name", "price", "quantity", "expiry", "code"]
        if col_id in whitelisted_cols:
            if self.current_sort_col == col_id:
                self.sort_ascending = not self.sort_ascending
            else:
                self.current_sort_col = col_id
                self.sort_ascending = True
            self.apply_filters()

    def _get_selected_medicine(self) -> Optional[Medicine]:
        """Returns selected Medicine object from Treeview selection or None."""
        selected_items = self.tree.selection()
        if not selected_items:
            return None
        med_id = int(selected_items[0])
        return self.medicine_service.get_medicine_by_id(med_id)

    def _on_add_medicine(self) -> None:
        """Opens Add Medicine modal form."""
        self._active_modal = MedicineFormModal(self, self.user, medicine=None, on_success_callback=self.refresh_table)

    def _on_edit_medicine(self) -> None:
        """Opens Edit Medicine modal form for selected medicine."""
        med = self._get_selected_medicine()
        if not med:
            messagebox.showwarning("Select Medicine", "Please select a medicine from the table to edit.")
            return
        self._active_modal = MedicineFormModal(self, self.user, medicine=med, on_success_callback=self.refresh_table)

    def _on_delete_medicine(self) -> None:
        """Handles medicine deletion with role-based permission check & automatic archival of items with history."""
        # 1. Role-based Permission Check
        if not self.user.is_admin:
            messagebox.showerror(
                "Permission Denied",
                "PERMISSION BLOCK: Only Owner and Admin users can delete or archive medicines."
            )
            self.logger.log_poka_yoke("Permission Block", f"User '{self.user.username}' attempted to delete medicine.")
            return

        med = self._get_selected_medicine()
        if not med:
            messagebox.showwarning("Select Medicine", "Please select a medicine from the table to delete.")
            return

        # 2. Check dependencies across batches, sales, purchases, stock movements
        deps = self.medicine_service.check_delete_dependencies(med.medicine_id)
        if not deps["can_delete"]:
            # Automatic safe archival to protect historical data without redundant confirmation prompt
            arc_ok, arc_msg = self.medicine_service.deactivate_medicine(med.medicine_id, acting_user=self.user)
            if arc_ok:
                self.logger.log_event("INVENTORY", f"Medicine '{med.medicine_name}' ({med.medicine_code}) automatically archived by '{self.user.username}' to preserve historical audit trail.")
                messagebox.showinfo("Success", "Medicine archived successfully. Historical records have been preserved.")
                self.refresh_table()
            else:
                messagebox.showerror("Archive Error", f"Unable to archive medicine: {arc_msg}")
            return

        # 3. If zero dependencies, ask single standard confirmation for permanent deletion
        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to permanently delete '{med.medicine_name}' ({med.medicine_code})?\n\nThis medicine has zero transaction history. This action cannot be undone."
        )
        if not confirm:
            return

        success, msg = self.medicine_service.delete_medicine(med.medicine_id, acting_user=self.user)
        if success:
            self.logger.log_event("INVENTORY", f"Medicine ID {med.medicine_id} ('{med.medicine_name}') deleted by '{self.user.username}'.")
            messagebox.showinfo("Success", "Medicine deleted successfully.")
            self.refresh_table()
        else:
            messagebox.showerror("Deletion Error", msg)
