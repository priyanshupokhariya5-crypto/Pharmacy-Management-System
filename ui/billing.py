"""
Sales & Checkout Billing System View & Invoice Receipt Modal.
Provides medicine search, cart management, duplicate item merging, subtotal/total calculations in ₹,
Poka-Yoke expired & out-of-stock validation blocks, and atomic transaction checkout execution.
"""
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional, List, Dict, Any, Tuple
import customtkinter as ctk

from ui.theme import Theme
from services.sales_service import SalesService
from services.search_service import SearchService
from services.medicine_service import MedicineService
from models.medicine import Medicine
from models.user import User
from utils.logger import get_app_logger


class InvoiceReceiptModal(ctk.CTkToplevel):
    """Modal popup dialog displaying formatted invoice receipt after successful sale."""

    def __init__(self, parent, sale_details: dict):
        super().__init__(parent)
        self.sale_details = sale_details

        self.title(f"Invoice Receipt - {sale_details.get('invoice_number', sale_details['sale_id'])}")
        
        # Calculate dynamic size based on screen
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        
        # Sizing that works well for 1366x768 up to 1920x1080
        width = 750
        height = min(750, int(screen_h * 0.85))
        
        # Center horizontally and vertically
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_DARK)

        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self._build_ui()

    def _build_ui(self) -> None:
        card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=14, border_width=1, border_color=Theme.PRIMARY)
        card.pack(padx=20, pady=20, fill="both", expand=True)

        # ----------------------------------------------------
        # 1. FOOTER & ACTION BUTTONS (Packed BOTTOM first to ensure visibility)
        # ----------------------------------------------------
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=15, pady=(0, 15))
        
        dl_btn = ctk.CTkButton(btn_frame, text="Download PDF", font=Theme.FONT_BOLD, width=150, height=42, 
                               fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK, 
                               command=self._download_pdf)
        dl_btn.pack(side="left", padx=(0, 10))
        
        print_btn = ctk.CTkButton(btn_frame, text="Print", font=Theme.FONT_BOLD, width=120, height=42, 
                                  fg_color=Theme.SECONDARY, hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK, 
                                  command=self._print_pdf)
        print_btn.pack(side="left", padx=(0, 10))
        
        close_btn = ctk.CTkButton(btn_frame, text="Close", font=Theme.FONT_BOLD, width=120, height=42, 
                                  fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK, 
                                  command=self.destroy)
        close_btn.pack(side="right")

        footer_frame = ctk.CTkFrame(card, fg_color=Theme.INPUT_BG, corner_radius=8)
        footer_frame.pack(side="bottom", fill="x", padx=15, pady=(0, 15))

        total_amount = self.sale_details.get("total_amount", 0.0)
        items = self.sale_details.get("items", [])
        total_items_count = sum(item.get("quantity", 0) for item in items)
        
        ctk.CTkLabel(footer_frame, text=f"Total Items: {total_items_count} units", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).pack(anchor="e", padx=15, pady=(10, 2))
        ctk.CTkLabel(footer_frame, text=f"GRAND TOTAL: ₹{total_amount:.2f}", font=Theme.FONT_HEADING, text_color=Theme.SUCCESS).pack(anchor="e", padx=15, pady=(0, 10))

        # ----------------------------------------------------
        # 2. HEADER (Packed TOP)
        # ----------------------------------------------------
        ctk.CTkLabel(card, text="🏥 PHARMACY MANAGEMENT SYSTEM", font=Theme.FONT_TITLE, text_color=Theme.PRIMARY).pack(side="top", pady=(15, 2))
        ctk.CTkLabel(card, text="Official Sales & Transaction Invoice", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="top", pady=(0, 15))

        # Meta Info (Grid Layout)
        meta_frame = ctk.CTkFrame(card, fg_color=Theme.INPUT_BG, corner_radius=8)
        meta_frame.pack(side="top", fill="x", padx=15, pady=(0, 10))

        inv_num = self.sale_details.get("invoice_number", "N/A")
        s_date = self.sale_details.get("sale_date", "N/A")
        pat_name = self.sale_details.get("patient_name", "Walk-in Patient")
        pat_phone = self.sale_details.get("patient_phone", "")
        pat_age = self.sale_details.get("patient_age", "")
        cashier = self.sale_details.get("username", "System User")

        ctk.CTkLabel(meta_frame, text=f"Invoice No: {inv_num}", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(meta_frame, text=f"Date: {s_date}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).grid(row=0, column=1, sticky="e", padx=12, pady=(10, 2))
        
        ctk.CTkLabel(meta_frame, text=f"Patient: {pat_name}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).grid(row=1, column=0, sticky="w", padx=12, pady=2)
        ctk.CTkLabel(meta_frame, text=f"Billed By: {cashier}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).grid(row=1, column=1, sticky="e", padx=12, pady=2)
        
        p_extra = []
        if pat_phone: p_extra.append(f"Phone: {pat_phone}")
        if pat_age: p_extra.append(f"Age: {pat_age}")
        if p_extra:
            ctk.CTkLabel(meta_frame, text=" | ".join(p_extra), font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 10))
        else:
            meta_frame.grid_rowconfigure(2, minsize=10) # padding

        meta_frame.columnconfigure(0, weight=1)
        meta_frame.columnconfigure(1, weight=1)

        # ----------------------------------------------------
        # 3. LINE ITEMS (Packed remaining space)
        # ----------------------------------------------------
        items_frame = ctk.CTkScrollableFrame(card, fg_color=Theme.BG_DARK, corner_radius=8)
        items_frame.pack(side="top", fill="both", expand=True, padx=15, pady=(0, 10))

        h_frame = ctk.CTkFrame(items_frame, fg_color=Theme.INPUT_BG, corner_radius=4)
        h_frame.pack(fill="x", pady=(0, 4))
        
        ctk.CTkLabel(h_frame, text="Code", font=Theme.FONT_BOLD, width=70, anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(h_frame, text="Name / Batch", font=Theme.FONT_BOLD, width=220, anchor="w").pack(side="left", padx=5)
        ctk.CTkLabel(h_frame, text="Qty", font=Theme.FONT_BOLD, width=40, anchor="center").pack(side="left", padx=5)
        ctk.CTkLabel(h_frame, text="Price", font=Theme.FONT_BOLD, width=80, anchor="e").pack(side="left", padx=5)
        ctk.CTkLabel(h_frame, text="Subtotal", font=Theme.FONT_BOLD, width=90, anchor="e").pack(side="left", padx=5)

        for item in items:
            r_frame = ctk.CTkFrame(items_frame, fg_color="transparent")
            r_frame.pack(fill="x", pady=2)

            name_batch = item["medicine_name"]
            
            ctk.CTkLabel(r_frame, text=item.get("medicine_code", ""), font=Theme.FONT_SMALL, width=70, anchor="w").pack(side="left", padx=5)
            ctk.CTkLabel(r_frame, text=name_batch, font=Theme.FONT_SMALL, width=220, anchor="w").pack(side="left", padx=5)
            ctk.CTkLabel(r_frame, text=str(item["quantity"]), font=Theme.FONT_SMALL, width=40, anchor="center").pack(side="left", padx=5)
            ctk.CTkLabel(r_frame, text=f"₹{item['price']:.2f}", font=Theme.FONT_SMALL, width=80, anchor="e").pack(side="left", padx=5)
            ctk.CTkLabel(r_frame, text=f"₹{item['subtotal']:.2f}", font=Theme.FONT_SMALL, width=90, anchor="e").pack(side="left", padx=5)

    def _download_pdf(self):
        from utils.pdf_generator import generate_invoice_pdf
        import os
        from tkinter import filedialog, messagebox
        
        inv_num = self.sale_details.get("invoice_number", f"Sale_{self.sale_details['sale_id']}")
        default_name = f"Invoice_{inv_num}.pdf"
        
        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=default_name,
            title="Save Invoice PDF",
            filetypes=[("PDF Files", "*.pdf")]
        )
        if filepath:
            success = generate_invoice_pdf(self.sale_details, filepath)
            if success:
                messagebox.showinfo("Success", f"Invoice saved successfully to:\n{filepath}")
            else:
                messagebox.showerror("Error", "Failed to generate PDF. Check permissions or if file is open.")
                
    def _print_pdf(self):
        from utils.pdf_generator import generate_invoice_pdf
        import os
        import tempfile
        from tkinter import messagebox
        
        try:
            inv_num = self.sale_details.get("invoice_number", f"Sale_{self.sale_details['sale_id']}")
            temp_dir = tempfile.gettempdir()
            filepath = os.path.join(temp_dir, f"Invoice_{inv_num}.pdf")
            
            success = generate_invoice_pdf(self.sale_details, filepath)
            if not success:
                messagebox.showerror("Error", "Failed to generate PDF for printing.")
                return
                
            if os.name == 'nt':
                try:
                    os.startfile(filepath, "print")
                except Exception as e:
                    # Fallback to just opening it
                    os.startfile(filepath)
                    messagebox.showinfo("Print Fallback", "Direct printing unavailable. The PDF has been opened for manual printing.")
            else:
                messagebox.showinfo("Print Instructions", f"PDF generated at:\n{filepath}\nPlease print it manually.")
        except Exception as e:
            messagebox.showerror("Print Error", f"An error occurred while printing:\n{e}")

class BillingView(ctk.CTkFrame):
    """Sales & Checkout Billing System View."""

    def __init__(self, parent, user: User):
        super().__init__(parent, fg_color="transparent")
        self.user = user
        self.sales_service = SalesService()
        self.search_service = SearchService()
        self.medicine_service = MedicineService()
        self.logger = get_app_logger()

        # Cart Data Structure: Dict[medicine_id, {"medicine": Medicine, "quantity": int, "subtotal": float}]
        self.cart: Dict[int, Dict[str, Any]] = {}

        self._build_ui()
        self._on_search_medicine()

    def _build_ui(self) -> None:
        """Constructs the split-panel layout: Search & Selection (Top/Left), Cart & Checkout (Bottom/Right)."""
        # Header Banner
        header_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12)
        header_card.pack(fill="x", pady=(0, 10))

        title_lbl = ctk.CTkLabel(
            header_card,
            text="🛒 Sales & Checkout Billing System",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        )
        title_lbl.pack(side="left", padx=20, pady=12)

        subtitle_lbl = ctk.CTkLabel(
            header_card,
            text="Poka-Yoke Expired & Low-Stock Prevention | Atomic SQLite Checkout | All Prices in ₹",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        )
        subtitle_lbl.pack(side="right", padx=20, pady=12)

        # Main Split Container (PanedWindow / Horizontal Frames)
        main_split = ctk.CTkFrame(self, fg_color="transparent")
        main_split.pack(fill="both", expand=True)

        # ----------------------------------------------------
        # Left Panel: Inventory Search & Selection
        # ----------------------------------------------------
        left_panel = ctk.CTkFrame(main_split, fg_color=Theme.BG_CARD, corner_radius=12)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))

        p1_title = ctk.CTkLabel(
            left_panel,
            text="🔍 Medicine Inventory Search",
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_MAIN
        )
        p1_title.pack(anchor="w", padx=15, pady=(12, 6))

        # Search Bar
        search_box = ctk.CTkFrame(left_panel, fg_color="transparent")
        search_box.pack(fill="x", padx=15, pady=(0, 8))

        self.search_entry = ctk.CTkEntry(
            search_box,
            placeholder_text="Search medicine name or code (e.g. 'para', 'MED1001')...",
            height=36,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self._on_search_medicine())
        self.search_entry.bind("<Return>", lambda e: self._on_search_medicine())

        srch_btn = ctk.CTkButton(
            search_box,
            text="Search",
            width=75,
            height=36,
            font=Theme.FONT_BOLD,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self._on_search_medicine
        )
        srch_btn.pack(side="right")

        # Inventory Table (Treeview)
        inv_table_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        inv_table_frame.pack(fill="both", expand=True, padx=15, pady=(0, 8))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "BillingInv.Treeview",
            background=Theme.BG_DARK,
            foreground=Theme.TEXT_MAIN,
            fieldbackground=Theme.BG_DARK,
            rowheight=26,
            font=("Segoe UI", 9)
        )
        style.configure(
            "BillingInv.Treeview.Heading",
            background=Theme.INPUT_BG,
            foreground=Theme.TEXT_MAIN,
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            "BillingInv.Treeview",
            background=[("selected", Theme.PRIMARY)],
            foreground=[("selected", Theme.TEXT_DARK)]
        )

        inv_cols = ("id", "code", "name", "price", "stock", "expiry_date", "stock_st", "exp_st")
        self.inv_tree = ttk.Treeview(
            inv_table_frame,
            columns=inv_cols,
            show="headings",
            style="BillingInv.Treeview",
            selectmode="browse"
        )

        inv_headers = [
            ("id", "ID", 35),
            ("code", "Code", 75),
            ("name", "Medicine Name", 140),
            ("price", "Price (₹)", 70),
            ("stock", "Stock", 55),
            ("expiry_date", "Expiry", 80),
            ("stock_st", "Stock Status", 85),
            ("exp_st", "Expiry Status", 85)
        ]

        for col_id, title, width in inv_headers:
            self.inv_tree.heading(col_id, text=title)
            self.inv_tree.column(col_id, width=width, anchor="center" if col_id not in ("name", "category") else "w")

        inv_vsb = ttk.Scrollbar(inv_table_frame, orient="vertical", command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=inv_vsb.set)

        self.inv_tree.pack(side="left", fill="both", expand=True)
        inv_vsb.pack(side="right", fill="y")

        self.inv_tree.bind("<<TreeviewSelect>>", self._on_inventory_select)

        # Quantity Selection & Add to Cart Frame
        add_frame = ctk.CTkFrame(left_panel, fg_color=Theme.INPUT_BG, corner_radius=8)
        add_frame.pack(fill="x", padx=15, pady=(0, 12))

        self.selected_med_lbl = ctk.CTkLabel(
            add_frame,
            text="Select a medicine from table to add to cart",
            font=Theme.FONT_BODY,
            text_color=Theme.TEXT_MUTED,
            anchor="w"
        )
        self.selected_med_lbl.pack(padx=12, pady=(8, 4), fill="x")

        qty_bar = ctk.CTkFrame(add_frame, fg_color="transparent")
        qty_bar.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(qty_bar, text="Qty:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(side="left", padx=(0, 4))
        self.add_qty_entry = ctk.CTkEntry(
            qty_bar,
            width=65,
            height=32,
            font=Theme.FONT_BODY,
            fg_color=Theme.BG_DARK,
            border_color=Theme.BORDER_COLOR
        )
        self.add_qty_entry.insert(0, "1")
        self.add_qty_entry.pack(side="left", padx=(0, 12))

        self.add_cart_btn = ctk.CTkButton(
            qty_bar,
            text="➕ Add to Cart",
            font=Theme.FONT_BOLD,
            height=32,
            fg_color=Theme.SUCCESS,
            hover_color="#8ed087",
            text_color=Theme.TEXT_DARK,
            state="disabled",
            command=self._on_add_to_cart
        )
        self.add_cart_btn.pack(side="left", fill="x", expand=True)

        # ----------------------------------------------------
        # Right Panel: Shopping Cart & Checkout
        # ----------------------------------------------------
        right_panel = ctk.CTkFrame(main_split, fg_color=Theme.BG_CARD, corner_radius=12)
        right_panel.pack(side="right", fill="both", expand=True, padx=(6, 0))

        p2_title = ctk.CTkLabel(
            right_panel,
            text="🛒 Shopping Cart & Billing",
            font=Theme.FONT_HEADING,
            text_color=Theme.PRIMARY
        )
        p2_title.pack(anchor="w", padx=15, pady=(12, 6))
        
        # Patient Info Frame
        patient_frame = ctk.CTkFrame(right_panel, fg_color=Theme.INPUT_BG, corner_radius=8)
        patient_frame.pack(fill="x", padx=15, pady=(0, 10))
        
        ctk.CTkLabel(patient_frame, text="👤 Patient Details", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w", padx=12, pady=(8,4))
        
        patient_inputs = ctk.CTkFrame(patient_frame, fg_color="transparent")
        patient_inputs.pack(fill="x", padx=12, pady=(0,10))
        
        self.pat_name_entry = ctk.CTkEntry(patient_inputs, placeholder_text="Patient Name (Required)*", width=180, fg_color=Theme.BG_DARK, border_color=Theme.BORDER_COLOR)
        self.pat_name_entry.pack(side="left", padx=(0, 6))
        
        self.pat_phone_entry = ctk.CTkEntry(patient_inputs, placeholder_text="Phone (Optional)", width=120, fg_color=Theme.BG_DARK, border_color=Theme.BORDER_COLOR)
        self.pat_phone_entry.pack(side="left", padx=(0, 6))
        
        self.pat_age_entry = ctk.CTkEntry(patient_inputs, placeholder_text="Age", width=60, fg_color=Theme.BG_DARK, border_color=Theme.BORDER_COLOR)
        self.pat_age_entry.pack(side="left")

        # Cart Table (Treeview)
        cart_table_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        cart_table_frame.pack(fill="both", expand=True, padx=15, pady=(0, 8))

        style.configure(
            "Cart.Treeview",
            background=Theme.BG_DARK,
            foreground=Theme.TEXT_MAIN,
            fieldbackground=Theme.BG_DARK,
            rowheight=26,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Cart.Treeview.Heading",
            background=Theme.INPUT_BG,
            foreground=Theme.TEXT_MAIN,
            font=("Segoe UI", 9, "bold")
        )

        cart_cols = ("id", "code", "name", "qty", "price", "subtotal")
        self.cart_tree = ttk.Treeview(
            cart_table_frame,
            columns=cart_cols,
            show="headings",
            style="Cart.Treeview",
            selectmode="browse"
        )

        cart_headers = [
            ("id", "ID", 35),
            ("code", "Code", 75),
            ("name", "Medicine Name", 150),
            ("qty", "Qty", 45),
            ("price", "Unit Price", 75),
            ("subtotal", "Subtotal (₹)", 85)
        ]

        for col_id, title, width in cart_headers:
            self.cart_tree.heading(col_id, text=title)
            self.cart_tree.column(col_id, width=width, anchor="center" if col_id in ("id", "code", "qty", "price", "subtotal") else "w")

        cart_vsb = ttk.Scrollbar(cart_table_frame, orient="vertical", command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=cart_vsb.set)

        self.cart_tree.pack(side="left", fill="both", expand=True)
        cart_vsb.pack(side="right", fill="y")

        # Cart Item Controls (Edit Qty, Remove Item, Clear Cart)
        cart_ctrl_bar = ctk.CTkFrame(right_panel, fg_color="transparent")
        cart_ctrl_bar.pack(fill="x", padx=15, pady=(0, 8))

        edit_qty_btn = ctk.CTkButton(
            cart_ctrl_bar,
            text="✏️ Edit Qty",
            width=90,
            height=30,
            font=Theme.FONT_SMALL,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self._on_edit_cart_qty
        )
        edit_qty_btn.pack(side="left", padx=(0, 6))

        remove_item_btn = ctk.CTkButton(
            cart_ctrl_bar,
            text="🗑️ Remove",
            width=90,
            height=30,
            font=Theme.FONT_SMALL,
            fg_color=Theme.DANGER,
            hover_color="#e05f7e",
            text_color=Theme.TEXT_DARK,
            command=self._on_remove_cart_item
        )
        remove_item_btn.pack(side="left", padx=(0, 6))

        clear_cart_btn = ctk.CTkButton(
            cart_ctrl_bar,
            text="Clear Cart",
            width=90,
            height=30,
            font=Theme.FONT_SMALL,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MUTED,
            command=self._on_clear_cart
        )
        clear_cart_btn.pack(side="right")

        # Cart Summary & Checkout Box
        checkout_box = ctk.CTkFrame(right_panel, fg_color=Theme.INPUT_BG, corner_radius=10)
        checkout_box.pack(fill="x", padx=15, pady=(0, 12))

        self.summary_lbl = ctk.CTkLabel(
            checkout_box,
            text="Total Items: 0  |  TOTAL: ₹0.00",
            font=Theme.FONT_TITLE,
            text_color=Theme.SUCCESS,
            anchor="e"
        )
        self.summary_lbl.pack(padx=15, pady=(10, 8), fill="x")

        checkout_btn = ctk.CTkButton(
            checkout_box,
            text="💳 Complete Checkout & Generate Invoice",
            font=Theme.FONT_HEADING,
            height=42,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self._on_checkout
        )
        checkout_btn.pack(padx=15, pady=(0, 12), fill="x")

    def _on_search_medicine(self) -> None:
        """Executes medicine search and fills inventory Treeview."""
        query_text = self.search_entry.get().strip()
        medicines, _ = self.search_service.search_medicines(query_text=query_text, limit=100)

        for item in self.inv_tree.get_children():
            self.inv_tree.delete(item)

        for med in medicines:
            self.inv_tree.insert(
                "",
                "end",
                iid=str(med.medicine_id),
                values=(
                    med.medicine_id,
                    med.medicine_code,
                    med.medicine_name,
                    f"₹{med.price:.2f}",
                    med.quantity,
                    med.expiry_date,
                    med.stock_status,
                    med.expiry_status
                )
            )

    def _on_inventory_select(self, event) -> None:
        """Handles selection of a row in the inventory search table."""
        selected_items = self.inv_tree.selection()
        if not selected_items:
            self.selected_med_lbl.configure(text="Select a medicine from table to add to cart", text_color=Theme.TEXT_MUTED)
            self.add_cart_btn.configure(state="disabled")
            return

        med_id = int(selected_items[0])
        med = self.medicine_service.get_medicine_by_id(med_id)
        if not med:
            return

        # Display Selected Item Status Summary
        status_text = f"Selected: {med.medicine_name} ({med.medicine_code}) | Stock: {med.quantity} | Price: ₹{med.price:.2f}"
        
        if med.is_expired:
            status_text += f" | ⚠️ EXPIRED ({med.expiry_date})"
            self.selected_med_lbl.configure(text=status_text, text_color=Theme.DANGER)
            self.add_cart_btn.configure(state="disabled")
        elif med.quantity == 0:
            status_text += " | ⚠️ OUT OF STOCK"
            self.selected_med_lbl.configure(text=status_text, text_color=Theme.DANGER)
            self.add_cart_btn.configure(state="disabled")
        else:
            self.selected_med_lbl.configure(text=status_text, text_color=Theme.PRIMARY)
            self.add_cart_btn.configure(state="normal")

    def _on_add_to_cart(self) -> None:
        """Validates inputs and adds item to cart with duplicate merging & Poka-Yoke checks."""
        selected_items = self.inv_tree.selection()
        if not selected_items:
            return

        med_id = int(selected_items[0])
        med = self.medicine_service.get_medicine_by_id(med_id)
        if not med:
            return

        # Poka-Yoke Check 1: Expired Medicine Block
        if med.is_expired:
            messagebox.showerror("Sale Blocked", f"Sale blocked: '{med.medicine_name}' has expired on {med.expiry_date}.")
            self.logger.log_poka_yoke("Expired Medicine Block", f"Blocked adding expired medicine '{med.medicine_name}' to cart.")
            return

        # Quantity Validation
        qty_str = self.add_qty_entry.get().strip()
        try:
            req_qty = int(qty_str)
            if req_qty <= 0:
                messagebox.showwarning("Invalid Quantity", "Quantity must be greater than zero.")
                return
        except ValueError:
            messagebox.showwarning("Invalid Quantity", "Quantity must be a valid integer number.")
            return

        # Check existing cart quantity for duplicate item merging
        existing_cart_qty = self.cart.get(med_id, {}).get("quantity", 0)
        total_combined_qty = existing_cart_qty + req_qty

        # Poka-Yoke Check 2: Stock Bounds Check
        if total_combined_qty > med.quantity:
            messagebox.showerror(
                "Insufficient Stock",
                f"Insufficient stock. Available quantity: {med.quantity}. Already in cart: {existing_cart_qty}."
            )
            self.logger.log_poka_yoke("Insufficient Stock Block", f"Blocked adding {req_qty} units of '{med.medicine_name}' (Stock: {med.quantity}).")
            return

        # Add or Update Cart
        subtotal = round(med.price * total_combined_qty, 2)
        self.cart[med_id] = {
            "medicine": med,
            "quantity": total_combined_qty,
            "subtotal": subtotal
        }

        self.refresh_cart_display()

    def _on_edit_cart_qty(self) -> None:
        """Prompts user to change quantity for selected cart item."""
        selected = self.cart_tree.selection()
        if not selected:
            messagebox.showwarning("Select Cart Item", "Please select a cart item to edit quantity.")
            return

        med_id = int(selected[0])
        cart_item = self.cart.get(med_id)
        if not cart_item:
            return

        med = cart_item["medicine"]
        new_qty_str = simpledialog.askstring("Edit Quantity", f"Enter new quantity for '{med.medicine_name}' (Available: {med.quantity}):", initialvalue=str(cart_item["quantity"]))
        if new_qty_str is None:
            return

        try:
            new_qty = int(new_qty_str.strip())
            if new_qty <= 0:
                messagebox.showwarning("Invalid Quantity", "Quantity must be greater than zero. To remove, use Remove button.")
                return
            if new_qty > med.quantity:
                messagebox.showerror("Insufficient Stock", f"Insufficient stock. Available quantity: {med.quantity}.")
                return

            cart_item["quantity"] = new_qty
            cart_item["subtotal"] = round(med.price * new_qty, 2)
            self.refresh_cart_display()
        except ValueError:
            messagebox.showwarning("Invalid Quantity", "Quantity must be a valid integer.")

    def _on_remove_cart_item(self) -> None:
        """Removes selected item from cart."""
        selected = self.cart_tree.selection()
        if not selected:
            messagebox.showwarning("Select Cart Item", "Please select a cart item to remove.")
            return

        med_id = int(selected[0])
        if med_id in self.cart:
            del self.cart[med_id]
            self.refresh_cart_display()

    def _on_clear_cart(self) -> None:
        """Clears all cart items after confirmation."""
        if not self.cart:
            return

        confirm = messagebox.askyesno("Clear Cart", "Are you sure you want to clear the shopping cart?")
        if confirm:
            self.cart.clear()
            self.refresh_cart_display()

    def refresh_cart_display(self) -> None:
        """Re-renders cart items in Treeview and updates total calculations in ₹."""
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)

        total_items = 0
        total_amount = 0.0

        for med_id, item_data in self.cart.items():
            med = item_data["medicine"]
            qty = item_data["quantity"]
            subtotal = item_data["subtotal"]

            total_items += qty
            total_amount += subtotal

            self.cart_tree.insert(
                "",
                "end",
                iid=str(med_id),
                values=(
                    med.medicine_id,
                    med.medicine_code,
                    med.medicine_name,
                    qty,
                    f"₹{med.price:.2f}",
                    f"₹{subtotal:.2f}"
                )
            )

        self.summary_lbl.configure(text=f"Total Items: {total_items}  |  TOTAL: ₹{total_amount:.2f}")

    def _on_checkout(self) -> None:
        """Executes pre-checkout validation and atomic SQLite checkout transaction."""
        if not self.cart:
            messagebox.showwarning("Empty Cart", "Cart is empty. Please add medicines before checkout.")
            self.logger.log_poka_yoke("Empty Checkout Attempt", "Blocked checkout attempt on empty cart.")
            return

        patient_name = getattr(self, 'pat_name_entry', None) and self.pat_name_entry.get().strip()
        if not patient_name:
            messagebox.showerror("Validation Error", "Patient Name is mandatory.")
            return
            
        patient_phone = getattr(self, 'pat_phone_entry', None) and self.pat_phone_entry.get().strip() or None
        patient_age_str = getattr(self, 'pat_age_entry', None) and self.pat_age_entry.get().strip() or None
        patient_age = None
        if patient_age_str:
            try:
                patient_age = int(patient_age_str)
            except ValueError:
                messagebox.showerror("Validation Error", "Patient Age must be a valid integer.")
                return

        # Prepare cart_items tuple list: (medicine_id, quantity)
        cart_items_list = [(med_id, item_data["quantity"]) for med_id, item_data in self.cart.items()]

        # Process Atomic Sale Transaction
        try:
            success, msg, sale_id, inv_num = self.sales_service.process_sale(self.user.user_id, cart_items_list, patient_name, patient_phone, patient_age)
        except Exception as e:
            messagebox.showerror("Checkout Failed", str(e))
            return

        if success and sale_id:
            # Fetch sale details for Invoice Receipt
            sale_details = self.sales_service.get_sale_details(sale_id)
            if sale_details:
                InvoiceReceiptModal(self, sale_details)

            # Post Checkout Reset
            self.cart.clear()
            if getattr(self, 'pat_name_entry', None): self.pat_name_entry.delete(0, 'end')
            if getattr(self, 'pat_phone_entry', None): self.pat_phone_entry.delete(0, 'end')
            if getattr(self, 'pat_age_entry', None): self.pat_age_entry.delete(0, 'end')
            self.refresh_cart_display()
            self._on_search_medicine()
        else:
            messagebox.showerror("Checkout Failed", msg)
