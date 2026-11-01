"""
Advanced Sales & Point of Sale (POS) Billing View, Shift Reconciliation & Return Management.
Features:
  - Fast medicine search and responsive cart management
  - Mandatory 10-digit Indian mobile number validation with real-time inline warnings
  - Real-time financial calculations (Subtotal, Discount, Tax, Rounding, Grand Total)
  - Cash, UPI, and Card payment methods with transaction reference tracking
  - FEFO batch inventory allocation and atomic checkout execution
  - Shift transaction history, invoice reprinting, and authorized returns/refunds
"""
import re
import time
from datetime import datetime
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
from utils.validators import validate_indian_phone, calculate_bill_totals


class InvoiceReceiptModal(ctk.CTkToplevel):
    """Modal popup dialog displaying formatted invoice receipt with batch allocations."""

    def __init__(self, parent, sale_details: dict):
        super().__init__(parent)
        self.sale_details = sale_details

        inv_num = sale_details.get("invoice_number", f"INV-{sale_details['sale_id']}")
        self.title(f"Invoice Receipt - {inv_num}")

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = 780
        height = min(780, int(screen_h * 0.88))
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
        card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        card.pack(padx=16, pady=16, fill="both", expand=True)

        # 1. Action Buttons (bottom first)
        btn_frame = ctk.CTkFrame(card, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=16, pady=(0, 16))

        dl_btn = ctk.CTkButton(
            btn_frame, text="💾 Save Invoice as PDF", font=Theme.FONT_BOLD, width=160, height=38,
            fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK,
            command=self._download_pdf
        )
        dl_btn.pack(side="left", padx=(0, 10))
        self.dl_btn = dl_btn

        print_btn = ctk.CTkButton(
            btn_frame, text="🖨️ Print Invoice", font=Theme.FONT_BOLD, width=130, height=38,
            fg_color=Theme.SECONDARY, hover_color=Theme.SECONDARY_HOVER, text_color=Theme.TEXT_DARK,
            command=self._print_pdf
        )
        print_btn.pack(side="left", padx=(0, 10))
        self.print_btn = print_btn

        close_btn = ctk.CTkButton(
            btn_frame, text="Close", font=Theme.FONT_BOLD, width=100, height=38,
            fg_color=Theme.INPUT_BG, hover_color=Theme.BORDER_COLOR, text_color=Theme.TEXT_MAIN,
            command=self.destroy
        )
        close_btn.pack(side="right")
        self.close_btn = close_btn

        # 2. Financial Summary Footer
        footer_frame = ctk.CTkFrame(card, fg_color=Theme.BG_DARK, corner_radius=8, border_width=1, border_color=Theme.BORDER_COLOR)
        footer_frame.pack(side="bottom", fill="x", padx=16, pady=(0, 12))

        subtot = self.sale_details.get("subtotal", self.sale_details.get("total_amount", 0.0))
        disc = self.sale_details.get("discount_amount", 0.0)
        tax = self.sale_details.get("tax_amount", 0.0)
        round_amt = self.sale_details.get("rounding_amount", 0.0)
        grand_tot = self.sale_details.get("total_amount", 0.0)
        pm = self.sale_details.get("payment_method", "Cash")
        pref = self.sale_details.get("payment_reference")
        pm_display = f"Paid via {pm}" + (f" (Ref: {pref})" if pref else "")

        f_left = ctk.CTkFrame(footer_frame, fg_color="transparent")
        f_left.pack(side="left", padx=12, pady=10)
        ctk.CTkLabel(f_left, text=pm_display, font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w")
        ctk.CTkLabel(f_left, text="Payment recorded locally. External gateway not integrated.", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")

        f_right = ctk.CTkFrame(footer_frame, fg_color="transparent")
        f_right.pack(side="right", padx=12, pady=10)

        f_details = f"Subtotal: ₹{subtot:.2f}"
        if disc > 0: f_details += f" | Disc: -₹{disc:.2f}"
        if tax > 0: f_details += f" | Tax: +₹{tax:.2f}"
        if round_amt != 0: f_details += f" | Rounding: {'+' if round_amt > 0 else ''}₹{round_amt:.2f}"

        ctk.CTkLabel(f_right, text=f_details, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="e")
        ctk.CTkLabel(f_right, text=f"GRAND TOTAL: ₹{grand_tot:.2f}", font=Theme.FONT_HEADING, text_color=Theme.PRIMARY).pack(anchor="e")

        # 3. Header
        ctk.CTkLabel(card, text="🏥 PHARMACY MANAGEMENT SYSTEM", font=Theme.FONT_TITLE, text_color=Theme.PRIMARY).pack(side="top", pady=(14, 2))
        ctk.CTkLabel(card, text="Official Sales & Transaction Invoice Receipt", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="top", pady=(0, 10))

        # Meta Info
        meta_frame = ctk.CTkFrame(card, fg_color=Theme.BG_DARK, corner_radius=8, border_width=1, border_color=Theme.BORDER_COLOR)
        meta_frame.pack(side="top", fill="x", padx=16, pady=(0, 10))

        inv_num = self.sale_details.get("invoice_number", "N/A")
        s_date = self.sale_details.get("sale_date", "N/A")
        pat_name = self.sale_details.get("patient_name", "Walk-in Customer")
        pat_phone = self.sale_details.get("patient_phone", "N/A")
        cashier = self.sale_details.get("username", "System User")
        status = self.sale_details.get("status", "COMPLETED")

        ctk.CTkLabel(meta_frame, text=f"Invoice No: {inv_num}", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(meta_frame, text=f"Date: {s_date}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).grid(row=0, column=1, sticky="e", padx=12, pady=(8, 2))

        ctk.CTkLabel(meta_frame, text=f"Customer: {pat_name} (Mobile: {pat_phone})", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).grid(row=1, column=0, sticky="w", padx=12, pady=2)
        ctk.CTkLabel(meta_frame, text=f"Billed By: {cashier} | Status: {status}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).grid(row=1, column=1, sticky="e", padx=12, pady=2)
        meta_frame.columnconfigure(0, weight=1)
        meta_frame.columnconfigure(1, weight=1)

        # 4. Line Items Table with Batch Details
        items_frame = ctk.CTkScrollableFrame(card, fg_color=Theme.BG_CARD, corner_radius=8)
        items_frame.pack(side="top", fill="both", expand=True, padx=16, pady=(0, 10))

        h_frame = ctk.CTkFrame(items_frame, fg_color=Theme.DEEP_NAVY, corner_radius=4)
        h_frame.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(h_frame, text="Code", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=65, anchor="w").pack(side="left", padx=6)
        ctk.CTkLabel(h_frame, text="Medicine / Allocated Batch Details", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=330, anchor="w").pack(side="left", padx=6)
        ctk.CTkLabel(h_frame, text="Qty", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=45, anchor="center").pack(side="left", padx=6)
        ctk.CTkLabel(h_frame, text="Unit Price", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=85, anchor="e").pack(side="left", padx=6)
        ctk.CTkLabel(h_frame, text="Subtotal", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=95, anchor="e").pack(side="left", padx=6)

        items = self.sale_details.get("items", [])
        for idx, item in enumerate(items):
            r_frame = ctk.CTkFrame(items_frame, fg_color=Theme.BG_DARK if idx % 2 == 0 else "transparent", corner_radius=4)
            r_frame.pack(fill="x", pady=2)

            med_code = item.get("medicine_code", "")
            med_name = item.get("medicine_name", "Medicine")
            batch_details = item.get("batch_details", "")
            display_name = f"{med_name}" + (f" [{batch_details}]" if batch_details else "")

            qty = item.get("quantity", 1)
            price = item.get("price", 0.0)
            subtotal = item.get("subtotal", 0.0)

            ctk.CTkLabel(r_frame, text=med_code, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED, width=65, anchor="w").pack(side="left", padx=6)
            ctk.CTkLabel(r_frame, text=display_name, font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=330, anchor="w").pack(side="left", padx=6)
            ctk.CTkLabel(r_frame, text=str(qty), font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=45, anchor="center").pack(side="left", padx=6)
            ctk.CTkLabel(r_frame, text=f"₹{price:.2f}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=85, anchor="e").pack(side="left", padx=6)
            ctk.CTkLabel(r_frame, text=f"₹{subtotal:.2f}", font=Theme.FONT_BOLD, text_color=Theme.PRIMARY, width=95, anchor="e").pack(side="left", padx=6)

    def _download_pdf(self) -> None:
        try:
            from utils.pdf_generator import generate_invoice_pdf
            filepath = generate_invoice_pdf(self.sale_details)
            messagebox.showinfo("PDF Downloaded", f"Invoice saved successfully:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"PDF generation failed: {e}")

    def _print_pdf(self) -> None:
        try:
            from utils.pdf_generator import generate_invoice_pdf, print_pdf
            filepath = generate_invoice_pdf(self.sale_details)
            print_pdf(filepath)
            messagebox.showinfo("Printing", "Invoice document sent to system default printer.")
        except Exception as e:
            messagebox.showerror("Print Failed", f"Printing failed: {e}")


class ReturnItemModal(ctk.CTkToplevel):
    """Modal dialog allowing authorized staff to process partial or full returns on past sales."""

    def __init__(self, parent, sales_service: SalesService, user: User, sale_details: dict, on_success_callback):
        super().__init__(parent)
        self.sales_service = sales_service
        self.user = user
        self.sale_details = sale_details
        self.on_success_callback = on_success_callback

        inv_num = sale_details.get("invoice_number", f"INV-{sale_details['sale_id']}")
        self.title(f"Process Return & Refund - {inv_num}")

        self.geometry("700x580")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_DARK)

        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self.return_qty_entries: Dict[int, ctk.CTkEntry] = {}
        self.condition_combos: Dict[int, ctk.CTkComboBox] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        card.pack(padx=16, pady=16, fill="both", expand=True)

        ctk.CTkLabel(card, text="🔄 Return & Refund Processing", font=Theme.FONT_TITLE, text_color=Theme.PRIMARY).pack(pady=(12, 2))
        ctk.CTkLabel(card, text="Select returned items. Expired or damaged items will not be restocked.", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(pady=(0, 10))

        # Sale Header Info
        inv = self.sale_details.get("invoice_number")
        pat = self.sale_details.get("patient_name")
        ctk.CTkLabel(card, text=f"Invoice: {inv} | Customer: {pat}", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(pady=(0, 8))

        # Items Table Frame
        scroll_frame = ctk.CTkScrollableFrame(card, fg_color=Theme.BG_DARK, height=220)
        scroll_frame.pack(fill="x", padx=16, pady=(0, 10))

        h_frame = ctk.CTkFrame(scroll_frame, fg_color=Theme.DEEP_NAVY)
        h_frame.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(h_frame, text="Medicine", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=200, anchor="w").pack(side="left", padx=6)
        ctk.CTkLabel(h_frame, text="Sold", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=50, anchor="center").pack(side="left", padx=4)
        ctk.CTkLabel(h_frame, text="Price", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=70, anchor="e").pack(side="left", padx=4)
        ctk.CTkLabel(h_frame, text="Return Qty", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=80, anchor="center").pack(side="left", padx=6)
        ctk.CTkLabel(h_frame, text="Condition", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=120, anchor="center").pack(side="left", padx=4)

        for item in self.sale_details.get("items", []):
            item_id = item["item_id"]
            med_name = item.get("medicine_name", "")
            qty_sold = item.get("quantity", 0)
            price = item.get("price", 0.0)

            row = ctk.CTkFrame(scroll_frame, fg_color=Theme.BG_CARD)
            row.pack(fill="x", pady=2)

            ctk.CTkLabel(row, text=med_name, font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=200, anchor="w").pack(side="left", padx=6)
            ctk.CTkLabel(row, text=str(qty_sold), font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=50, anchor="center").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{price:.2f}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=70, anchor="e").pack(side="left", padx=4)

            qty_entry = ctk.CTkEntry(row, width=60, font=Theme.FONT_BODY)
            qty_entry.insert(0, "0")
            qty_entry.pack(side="left", padx=16)
            self.return_qty_entries[item_id] = qty_entry

            cond_combo = ctk.CTkComboBox(row, values=["SELLABLE", "DAMAGED", "EXPIRED"], width=110, font=Theme.FONT_SMALL)
            cond_combo.set("SELLABLE")
            cond_combo.pack(side="left", padx=4)
            self.condition_combos[item_id] = cond_combo

        # Refund Method & Reason
        opt_frame = ctk.CTkFrame(card, fg_color="transparent")
        opt_frame.pack(fill="x", padx=16, pady=(0, 10))

        ctk.CTkLabel(opt_frame, text="Refund Method:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).grid(row=0, column=0, sticky="w", pady=4)
        self.refund_method_combo = ctk.CTkComboBox(opt_frame, values=["Cash", "UPI", "Card", "Original"], width=140)
        self.refund_method_combo.set(self.sale_details.get("payment_method", "Cash"))
        self.refund_method_combo.grid(row=0, column=1, sticky="w", padx=10, pady=4)

        ctk.CTkLabel(opt_frame, text="Return Reason:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).grid(row=1, column=0, sticky="w", pady=4)
        self.reason_entry = ctk.CTkEntry(opt_frame, placeholder_text="e.g. Defective packaging / Customer cancellation", width=340)
        self.reason_entry.grid(row=1, column=1, sticky="w", padx=10, pady=4)

        # Action Buttons
        btn_box = ctk.CTkFrame(card, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=10)

        confirm_btn = ctk.CTkButton(
            btn_box, text="Confirm Return & Refund", font=Theme.FONT_BOLD, height=38,
            fg_color=Theme.DANGER, hover_color="#96281B", text_color=Theme.TEXT_DARK,
            command=self._submit_return
        )
        confirm_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        cancel_btn = ctk.CTkButton(
            btn_box, text="Cancel", font=Theme.FONT_BOLD, height=38, width=100,
            fg_color=Theme.INPUT_BG, text_color=Theme.TEXT_MAIN, command=self.destroy
        )
        cancel_btn.pack(side="right")

    def _submit_return(self) -> None:
        return_items = []
        for item_id, q_entry in self.return_qty_entries.items():
            val = q_entry.get().strip()
            try:
                q = int(val)
                if q > 0:
                    cond = self.condition_combos[item_id].get()
                    return_items.append({
                        "sale_item_id": item_id,
                        "quantity": q,
                        "restock_condition": cond
                    })
            except ValueError:
                messagebox.showerror("Invalid Input", "Return quantities must be integer numbers.")
                return

        if not return_items:
            messagebox.showwarning("No Items", "Please specify a return quantity greater than zero for at least one item.")
            return

        method = self.refund_method_combo.get()
        reason = self.reason_entry.get().strip() or "Customer Return"

        success, msg, ret_id = self.sales_service.process_sale_return(
            sale_id=self.sale_details["sale_id"],
            return_items=return_items,
            refund_method=method,
            reason=reason,
            acting_user=self.user
        )

        if success:
            messagebox.showinfo("Return Successful", msg)
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        else:
            messagebox.showerror("Return Failed", msg)


class BillingView(ctk.CTkFrame):
    """
    Polished Point of Sale (POS) and Billing Management View.
    Supports:
      - Split POS Cart & Medicine Search
      - Mandatory 10-digit Indian mobile validation with inline warning banner
      - Real-time financial calculations (Subtotal, Discount, Tax, Rounding, Grand Total)
      - Cash, UPI, and Card payment methods with references
      - Real FEFO batch stock deductions and audit tracking
      - Shift Invoices Tab for transaction lookup, receipt reprinting, and returns
    """

    def __init__(self, parent, user: User):
        super().__init__(parent, fg_color="transparent")
        self.user = user
        store_id = getattr(self.user, 'store_id', 'STORE-LEGACY-001')
        self.sales_service = SalesService(store_id=store_id)
        self.search_service = SearchService(store_id=store_id)
        self.medicine_service = MedicineService(store_id=store_id)
        self.logger = get_app_logger()

        # Cart Data Structure: Dict[medicine_id, {"medicine": Medicine, "quantity": int, "subtotal": float}]
        self.cart: Dict[int, Dict[str, Any]] = {}
        self.phone_valid: bool = False
        self._is_processing_checkout: bool = False
        self.last_sale_details: Optional[Dict[str, Any]] = None
        self._active_invoice_modal: Optional[Any] = None

        self._build_ui()
        self._update_checkout_button_state()
        self._on_search_medicine()

    def _build_ui(self) -> None:
        # Header Banner
        header_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        header_card.pack(fill="x", pady=(0, 10))

        title_lbl = ctk.CTkLabel(
            header_card,
            text="🛒 Point of Sale (POS) & Billing",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        )
        title_lbl.pack(side="left", padx=20, pady=12)

        subtitle_lbl = ctk.CTkLabel(
            header_card,
            text="FEFO Batch Allocation | Mandatory 10-Digit Phone | Cash, UPI & Card",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        )
        subtitle_lbl.pack(side="right", padx=20, pady=12)

        # Tab View for POS vs Shift Invoices
        self.tab_view = ctk.CTkTabview(self, fg_color="transparent")
        self.tab_view.pack(fill="both", expand=True)
        self.tab_view.add("Point of Sale")
        self.tab_view.add("Shift Invoices & Returns")

        self._build_pos_tab(self.tab_view.tab("Point of Sale"))
        self._build_invoices_tab(self.tab_view.tab("Shift Invoices & Returns"))

    def _build_pos_tab(self, parent_frame: ctk.CTkFrame) -> None:
        """Constructs split-panel POS terminal."""
        main_split = ctk.CTkFrame(parent_frame, fg_color="transparent")
        main_split.pack(fill="both", expand=True)

        # ----------------------------------------------------
        # Left Panel: Medicine Search & Inventory Selection
        # ----------------------------------------------------
        left_panel = ctk.CTkFrame(main_split, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))

        p1_title = ctk.CTkLabel(left_panel, text="🔍 Medicine Inventory Search", font=Theme.FONT_HEADING, text_color=Theme.TEXT_MAIN)
        p1_title.pack(anchor="w", padx=15, pady=(12, 6))

        # Search Box
        search_box = ctk.CTkFrame(left_panel, fg_color="transparent")
        search_box.pack(fill="x", padx=15, pady=(0, 8))

        self.search_entry = ctk.CTkEntry(
            search_box,
            placeholder_text="Search medicine name, code, or category...",
            height=36,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.search_entry.bind("<KeyRelease>", lambda e: self._on_search_medicine())
        self.search_entry.bind("<Return>", lambda e: self._on_search_medicine())

        srch_btn = ctk.CTkButton(
            search_box, text="Search", width=75, height=36, font=Theme.FONT_BOLD,
            fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK,
            command=self._on_search_medicine
        )
        srch_btn.pack(side="right")

        # Inventory Table
        inv_table_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        inv_table_frame.pack(fill="both", expand=True, padx=15, pady=(0, 8))

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "BillingInv.Treeview",
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_MAIN,
            fieldbackground=Theme.BG_CARD,
            rowheight=26,
            font=("Segoe UI", 9)
        )
        style.configure(
            "BillingInv.Treeview.Heading",
            background=Theme.DEEP_NAVY,
            foreground=Theme.TEXT_DARK,
            font=("Segoe UI", 9, "bold")
        )
        style.map("BillingInv.Treeview", background=[("selected", Theme.PRIMARY)], foreground=[("selected", Theme.TEXT_DARK)])

        inv_cols = ("id", "code", "name", "price", "stock", "expiry_date", "stock_st", "exp_st")
        self.inv_tree = ttk.Treeview(inv_table_frame, columns=inv_cols, show="headings", style="BillingInv.Treeview", selectmode="browse")

        inv_headers = [
            ("id", "ID", 35),
            ("code", "Code", 70),
            ("name", "Medicine Name", 140),
            ("price", "Price (₹)", 70),
            ("stock", "Stock", 55),
            ("expiry_date", "Expiry", 80),
            ("stock_st", "Stock Status", 85),
            ("exp_st", "Expiry Status", 85)
        ]
        for col_id, title, width in inv_headers:
            self.inv_tree.heading(col_id, text=title)
            self.inv_tree.column(col_id, width=width, anchor="center" if col_id not in ("name",) else "w")

        inv_vsb = ttk.Scrollbar(inv_table_frame, orient="vertical", command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=inv_vsb.set)
        self.inv_tree.pack(side="left", fill="both", expand=True)
        inv_vsb.pack(side="right", fill="y")
        self.inv_tree.bind("<<TreeviewSelect>>", self._on_inventory_select)
        self.inv_tree.bind("<Double-1>", lambda e: self._on_add_to_cart())

        # Quantity Selection & Add to Cart Frame
        add_frame = ctk.CTkFrame(left_panel, fg_color=Theme.BG_DARK, corner_radius=8, border_width=1, border_color=Theme.BORDER_COLOR)
        add_frame.pack(fill="x", padx=15, pady=(0, 12))

        self.selected_med_lbl = ctk.CTkLabel(add_frame, text="Select a medicine to add to cart", font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED, anchor="w")
        self.selected_med_lbl.pack(padx=12, pady=(8, 4), fill="x")

        qty_bar = ctk.CTkFrame(add_frame, fg_color="transparent")
        qty_bar.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(qty_bar, text="Qty:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(side="left", padx=(0, 4))
        self.add_qty_entry = ctk.CTkEntry(qty_bar, width=65, height=32, font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.add_qty_entry.insert(0, "1")
        self.add_qty_entry.pack(side="left", padx=(0, 12))

        self.add_cart_btn = ctk.CTkButton(
            qty_bar, text="➕ Add to Cart", font=Theme.FONT_BOLD, height=32,
            fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK,
            state="disabled", command=self._on_add_to_cart
        )
        self.add_cart_btn.pack(side="left", fill="x", expand=True)

        # ----------------------------------------------------
        # Right Panel: Shopping Cart, Customer & Checkout
        # ----------------------------------------------------
        right_panel = ctk.CTkFrame(main_split, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        right_panel.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # 1. Header (Top - Compact)
        p2_title = ctk.CTkLabel(right_panel, text="🛒 Shopping Cart & Billing", font=Theme.FONT_HEADING, text_color=Theme.PRIMARY)
        p2_title.pack(side="top", anchor="w", padx=15, pady=(8, 2))

        # 2. Customer Details Frame (Top - Compact single-row layout)
        cust_frame = ctk.CTkFrame(right_panel, fg_color=Theme.BG_DARK, corner_radius=8, border_width=1, border_color=Theme.BORDER_COLOR)
        cust_frame.pack(side="top", fill="x", padx=15, pady=(0, 6))

        cust_header_row = ctk.CTkFrame(cust_frame, fg_color="transparent")
        cust_header_row.pack(fill="x", padx=10, pady=(4, 1))

        ctk.CTkLabel(cust_header_row, text="👤 Customer Details", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(side="left")

        # Inline Phone Error / Success Feedback Label placed cleanly on header row
        self.phone_feedback_lbl = ctk.CTkLabel(
            cust_header_row,
            text="",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            anchor="e"
        )
        self.phone_feedback_lbl.pack(side="right")

        cust_inputs = ctk.CTkFrame(cust_frame, fg_color="transparent")
        cust_inputs.pack(fill="x", padx=10, pady=(0, 6))

        self.pat_name_entry = ctk.CTkEntry(cust_inputs, placeholder_text="Customer Name (Required)*", width=145, height=28, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.pat_name_entry.pack(side="left", padx=(0, 4))

        self.pat_phone_entry = ctk.CTkEntry(cust_inputs, placeholder_text="Mobile (10 digits)*", width=125, height=28, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.pat_phone_entry.pack(side="left", padx=(0, 4))
        
        # Native Tkinter entry key validation: reject non-digits and > 10 characters immediately
        vcmd = (self.register(self._validate_phone_keystroke), "%P")
        if hasattr(self.pat_phone_entry, "_entry"):
            self.pat_phone_entry._entry.configure(validate="key", validatecommand=vcmd)
        for evt in ("<KeyRelease>", "<FocusOut>", "<ButtonRelease-1>", "<<Paste>>"):
            self.pat_phone_entry.bind(evt, self._on_phone_change)

        self.pat_age_entry = ctk.CTkEntry(cust_inputs, placeholder_text="Age", width=45, height=28, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.pat_age_entry.pack(side="left", padx=(0, 4))

        # Mandatory Sale Date (defaults to today's date)
        from datetime import datetime
        self.sale_date_entry = ctk.CTkEntry(cust_inputs, placeholder_text="Sale Date*", width=95, height=28, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.sale_date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.sale_date_entry.pack(side="left")

        # 3. Checkout Box (Anchored at Bottom - ALWAYS visible, strictly compact)
        checkout_box = ctk.CTkFrame(right_panel, fg_color=Theme.BG_DARK, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
        checkout_box.pack(side="bottom", fill="x", padx=15, pady=(0, 6))

        # Financial Inputs (Payment Method, Discount)
        self.fin_row = ctk.CTkFrame(checkout_box, fg_color="transparent")
        self.fin_row.pack(fill="x", padx=12, pady=(4, 2))

        ctk.CTkLabel(self.fin_row, text="Payment:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(side="left", padx=(0, 4))
        self.pm_segmented = ctk.CTkSegmentedButton(
            self.fin_row, values=["Cash", "UPI", "Card"], width=160, height=24, font=Theme.FONT_SMALL,
            command=self._on_payment_method_change
        )
        self.pm_segmented.set("Cash")
        self.pm_segmented.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(self.fin_row, text="Discount (₹):", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).pack(side="left", padx=(0, 4))
        self.discount_entry = ctk.CTkEntry(self.fin_row, width=65, height=24, font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG)
        self.discount_entry.insert(0, "0.00")
        self.discount_entry.pack(side="left")
        self.discount_entry.bind("<KeyRelease>", lambda e: self.refresh_cart_display())

        # Payment Reference Entry (Appears for UPI and Card, packed dynamically)
        self.pref_row = ctk.CTkFrame(checkout_box, fg_color="transparent", height=28)
        self.pref_lbl = ctk.CTkLabel(self.pref_row, text="Txn Ref:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
        self.pref_entry = ctk.CTkEntry(self.pref_row, placeholder_text="e.g. UPI UTR / Card Auth Code", height=26, font=Theme.FONT_SMALL, fg_color=Theme.INPUT_BG)
        self.pref_watermark = ctk.CTkLabel(self.pref_row, text="(Shift audit record)", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)

        # Summary Breakdown Display
        self.summary_breakdown_lbl = ctk.CTkLabel(
            checkout_box,
            text="Subtotal: ₹0.00 | Disc: ₹0.00 | Tax (Not Configured): ₹0.00",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            anchor="e"
        )
        self.summary_breakdown_lbl.pack(padx=12, pady=(1, 0), fill="x")

        self.grand_total_lbl = ctk.CTkLabel(
            checkout_box,
            text="PAYABLE TOTAL: ₹0.00",
            font=Theme.FONT_HEADING,
            text_color=Theme.PRIMARY,
            anchor="e"
        )
        self.grand_total_lbl.pack(padx=12, pady=(0, 3), fill="x")

        self.checkout_btn = ctk.CTkButton(
            checkout_box,
            text="💳 Complete FEFO Checkout & Generate Invoice",
            font=Theme.FONT_BOLD,
            height=32,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            state="normal",
            command=self._on_checkout
        )
        self.checkout_btn.pack(padx=12, pady=(0, 4), fill="x")

        # Secondary Actions: View Invoice & Save PDF
        inv_actions_row = ctk.CTkFrame(checkout_box, fg_color="transparent")
        inv_actions_row.pack(fill="x", padx=12, pady=(0, 6))

        self.view_invoice_btn = ctk.CTkButton(
            inv_actions_row,
            text="📄 View Last Invoice",
            font=Theme.FONT_SMALL,
            height=26,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            state="disabled",
            command=self._on_view_last_invoice
        )
        self.view_invoice_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.save_pdf_btn = ctk.CTkButton(
            inv_actions_row,
            text="💾 Save Invoice as PDF",
            font=Theme.FONT_SMALL,
            height=26,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            state="disabled",
            command=self._on_save_pdf
        )
        self.save_pdf_btn.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # 4. Cart Controls Bar (Just above Checkout Box)
        cart_ctrl_bar = ctk.CTkFrame(right_panel, fg_color="transparent")
        cart_ctrl_bar.pack(side="bottom", fill="x", padx=15, pady=(0, 4))

        ctk.CTkButton(cart_ctrl_bar, text="✏️ Edit Qty", width=80, height=26, font=Theme.FONT_SMALL, fg_color=Theme.BG_DARK, text_color=Theme.TEXT_MAIN, command=self._on_edit_cart_qty).pack(side="left", padx=(0, 6))
        ctk.CTkButton(cart_ctrl_bar, text="🗑️ Remove", width=80, height=26, font=Theme.FONT_SMALL, fg_color=Theme.DANGER, hover_color="#96281B", text_color=Theme.TEXT_DARK, command=self._on_remove_cart_item).pack(side="left", padx=(0, 6))
        ctk.CTkButton(cart_ctrl_bar, text="Clear Cart", width=80, height=26, font=Theme.FONT_SMALL, fg_color=Theme.BG_DARK, text_color=Theme.TEXT_MUTED, command=self._on_clear_cart).pack(side="right")

        # 5. Cart Table (Takes ALL remaining space with guaranteed ample height!)
        cart_table_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        cart_table_frame.pack(side="top", fill="both", expand=True, padx=15, pady=(0, 6))

        style.configure(
            "Cart.Treeview",
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_MAIN,
            fieldbackground=Theme.BG_CARD,
            rowheight=26,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Cart.Treeview.Heading",
            background=Theme.DEEP_NAVY,
            foreground=Theme.TEXT_DARK,
            font=("Segoe UI", 9, "bold")
        )
        style.map(
            "Cart.Treeview",
            background=[("selected", Theme.PRIMARY)],
            foreground=[("selected", Theme.TEXT_DARK)]
        )

        cart_cols = ("id", "code", "name", "batch", "shelf", "qty", "price", "subtotal")
        self.cart_tree = ttk.Treeview(cart_table_frame, columns=cart_cols, show="headings", style="Cart.Treeview", selectmode="browse")

        cart_headers = [
            ("id", "ID", 35),
            ("code", "Code", 65),
            ("name", "Medicine Name", 140),
            ("batch", "Batch", 80),
            ("shelf", "Shelf", 75),
            ("qty", "Qty", 45),
            ("price", "Price (₹)", 70),
            ("subtotal", "Total (₹)", 80)
        ]
        for col_id, title, width in cart_headers:
            self.cart_tree.heading(col_id, text=title)
            self.cart_tree.column(col_id, width=width, anchor="center" if col_id not in ("name",) else "w")

        cart_vsb = ttk.Scrollbar(cart_table_frame, orient="vertical", command=self.cart_tree.yview)
        self.cart_tree.configure(yscrollcommand=cart_vsb.set)
        self.cart_tree.pack(side="left", fill="both", expand=True)
        cart_vsb.pack(side="right", fill="y")

    def _build_invoices_tab(self, parent_frame: ctk.CTkFrame) -> None:
        """Constructs shift transaction review, cashier reconciliation, and return processing."""
        # Top Metrics Bar
        self.shift_metrics_frame = ctk.CTkFrame(parent_frame, fg_color=Theme.BG_CARD, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
        self.shift_metrics_frame.pack(fill="x", padx=10, pady=(4, 10))

        self.shift_labels: Dict[str, ctk.CTkLabel] = {}
        metric_cols = [
            ("bills_count", "Today's Bills", "0"),
            ("gross_sales", "Gross Sales", "₹0.00"),
            ("cash_coll", "Cash", "₹0.00"),
            ("upi_coll", "UPI", "₹0.00"),
            ("card_coll", "Card", "₹0.00"),
            ("refunds", "Refunds", "₹0.00"),
            ("net_sales", "Net Settled", "₹0.00")
        ]
        for idx, (m_key, title, d_val) in enumerate(metric_cols):
            box = ctk.CTkFrame(self.shift_metrics_frame, fg_color="transparent")
            box.grid(row=0, column=idx, padx=8, pady=8, sticky="nsew")
            self.shift_metrics_frame.columnconfigure(idx, weight=1)
            ctk.CTkLabel(box, text=title, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack()
            val_lbl = ctk.CTkLabel(box, text=d_val, font=Theme.FONT_BOLD, text_color=Theme.PRIMARY)
            val_lbl.pack()
            self.shift_labels[m_key] = val_lbl

        # Action Buttons for Invoices Tab
        act_bar = ctk.CTkFrame(parent_frame, fg_color="transparent")
        act_bar.pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkButton(act_bar, text="🔄 Refresh Invoices", font=Theme.FONT_SMALL, height=32, command=self._refresh_invoices_tab).pack(side="left", padx=(0, 8))
        ctk.CTkButton(act_bar, text="🧾 Reprint Selected Invoice", font=Theme.FONT_SMALL, height=32, command=self._on_reprint_invoice).pack(side="left", padx=(0, 8))
        ctk.CTkButton(act_bar, text="↩️ Process Return / Refund", font=Theme.FONT_BOLD, height=32, fg_color=Theme.DANGER, hover_color="#96281B", text_color=Theme.TEXT_DARK, command=self._on_open_return_modal).pack(side="right")

        # Invoices Table
        inv_frame = ctk.CTkFrame(parent_frame, fg_color=Theme.BG_CARD, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
        inv_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        inv_tree_cols = ("id", "invoice", "date", "customer", "phone", "amount", "payment", "status", "cashier")
        self.invoice_tree = ttk.Treeview(inv_frame, columns=inv_tree_cols, show="headings", style="BillingInv.Treeview", selectmode="browse")

        inv_tree_headers = [
            ("id", "ID", 40),
            ("invoice", "Invoice Number", 150),
            ("date", "Date & Time", 125),
            ("customer", "Customer", 130),
            ("phone", "Mobile", 95),
            ("amount", "Total (₹)", 80),
            ("payment", "Payment", 75),
            ("status", "Status", 90),
            ("cashier", "Cashier", 90)
        ]
        for cid, title, w in inv_tree_headers:
            self.invoice_tree.heading(cid, text=title)
            self.invoice_tree.column(cid, width=w, anchor="center" if cid not in ("customer", "invoice") else "w")

        inv_tree_vsb = ttk.Scrollbar(inv_frame, orient="vertical", command=self.invoice_tree.yview)
        self.invoice_tree.configure(yscrollcommand=inv_tree_vsb.set)
        self.invoice_tree.pack(side="left", fill="both", expand=True)
        inv_tree_vsb.pack(side="right", fill="y")

        self._refresh_invoices_tab()

    def _on_payment_method_change(self, value: str) -> None:
        """Shows payment reference field for UPI or Card; hides for Cash."""
        if value in ("UPI", "Card"):
            self.pref_lbl.pack(side="left", padx=(0, 4))
            self.pref_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
            self.pref_watermark.pack(side="left")
            if hasattr(self, "pref_row") and not self.pref_row.winfo_ismapped():
                self.pref_row.pack(fill="x", padx=12, pady=(0, 2), after=self.fin_row)
        else:
            self.pref_lbl.pack_forget()
            self.pref_entry.pack_forget()
            self.pref_watermark.pack_forget()
            if hasattr(self, "pref_row") and self.pref_row.winfo_ismapped():
                self.pref_row.pack_forget()

    def _validate_phone_keystroke(self, proposed_text: str) -> bool:
        """Poka-yoke keystroke validator: validates numeric digits up to 10 characters with live feedback."""
        if proposed_text == "":
            self.phone_valid = False
            if hasattr(self, "phone_feedback_lbl"):
                self.phone_feedback_lbl.configure(text="", text_color=Theme.TEXT_MUTED)
            self._update_checkout_button_state()
            return True
        if not proposed_text.isdigit():
            if hasattr(self, "phone_feedback_lbl"):
                self.phone_feedback_lbl.configure(
                    text="⚠️ Mobile number must contain only numeric digits.",
                    text_color=Theme.DANGER
                )
            return True
        if len(proposed_text) > 10:
            if hasattr(self, "phone_feedback_lbl"):
                self.phone_feedback_lbl.configure(
                    text="⚠️ Mobile number cannot exceed 10 digits.",
                    text_color=Theme.DANGER
                )
            return True
        return True

    def _on_phone_change(self, event=None) -> None:
        """
        Validates phone input live with responsive Poka-Yoke feedback rules:
        - Empty field: Do not show error.
        - 1-9 digits: Clean numeric, no live error shown while typing.
        - Non-numeric characters: Show immediate error.
        - More than 10 digits: Show immediate overlength error.
        - Exactly 10 digits: Validate Indian mobile rules (must start with 6-9).
        """
        raw_val = self.pat_phone_entry.get().strip()

        if not raw_val:
            self.phone_valid = False
            self.phone_feedback_lbl.configure(text="", text_color=Theme.TEXT_MUTED)
            self._update_checkout_button_state()
            return

        has_non_digits = any(not ch.isdigit() for ch in raw_val)
        if has_non_digits:
            self.phone_valid = False
            self.phone_feedback_lbl.configure(
                text="⚠️ Mobile number must contain only numeric digits.",
                text_color=Theme.DANGER
            )
            self._update_checkout_button_state()
            return

        if len(raw_val) > 10:
            self.phone_valid = False
            self.phone_feedback_lbl.configure(
                text="⚠️ Mobile number cannot exceed 10 digits.",
                text_color=Theme.DANGER
            )
            self._update_checkout_button_state()
            return

        if len(raw_val) == 10:
            is_valid, err_msg, cleaned = validate_indian_phone(raw_val)
            self.phone_valid = is_valid
            if is_valid:
                self.phone_feedback_lbl.configure(
                    text=f"✓ Valid 10-digit Indian mobile: {cleaned}",
                    text_color=Theme.SUCCESS
                )
            else:
                self.phone_feedback_lbl.configure(
                    text=f"⚠️ {err_msg or 'Mobile number must start with 6, 7, 8, or 9.'}",
                    text_color=Theme.DANGER
                )
        else:
            self.phone_valid = False
            self.phone_feedback_lbl.configure(text="", text_color=Theme.TEXT_MUTED)

        self._update_checkout_button_state()

    def _on_search_medicine(self) -> None:
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
        selected_items = self.inv_tree.selection()
        if not selected_items:
            self.selected_med_lbl.configure(text="Select a medicine from table to add to cart", text_color=Theme.TEXT_MUTED)
            self.add_cart_btn.configure(state="disabled")
            return

        med_id = int(selected_items[0])
        self._selected_med_id = med_id
        med = self.medicine_service.get_medicine_by_id(med_id)
        if not med:
            return

        batch_id = None
        batch_no = med.batch_no
        shelf_loc = "SHELF-A01"
        avail_stock = med.quantity

        if hasattr(self.sales_service, "_table_exists") and self.sales_service._table_exists("inventory_batches"):
            today_iso = datetime.now().strftime("%Y-%m-%d")
            b_row = self.sales_service.db.fetch_one(
                """
                SELECT b.batch_id, b.batch_number, b.current_quantity, COALESCE(sl.shelf_code, 'SHELF-A01') as shelf_code
                FROM inventory_batches b
                LEFT JOIN storage_locations sl ON b.location_id = sl.location_id
                WHERE b.medicine_id = ? AND b.store_id = ? AND b.status IN ('Active', 'AVAILABLE')
                  AND b.current_quantity > 0 AND (b.expiry_date IS NULL OR b.expiry_date >= ?)
                ORDER BY b.expiry_date ASC, b.created_at ASC LIMIT 1
                """,
                (med_id, self.user.store_id, today_iso)
            )
            if b_row:
                batch_id = b_row["batch_id"]
                batch_no = b_row["batch_number"] or batch_no
                shelf_loc = b_row["shelf_code"] or shelf_loc

            b_total = self.sales_service.db.fetch_one(
                """
                SELECT COALESCE(SUM(current_quantity), 0) as total_qty
                FROM inventory_batches
                WHERE medicine_id = ? AND store_id = ? AND status IN ('Active', 'AVAILABLE')
                  AND current_quantity > 0 AND (expiry_date IS NULL OR expiry_date >= ?)
                """,
                (med_id, self.user.store_id, today_iso)
            )
            if b_total and b_total["total_qty"] > 0:
                avail_stock = max(avail_stock, b_total["total_qty"])

        self._selected_batch_id = batch_id
        self._selected_batch_no = batch_no
        self._selected_shelf_loc = shelf_loc
        self._selected_avail_stock = avail_stock

        status_text = f"Selected: {med.medicine_name} ({med.medicine_code}) | Batch: {batch_no} | Shelf: {shelf_loc} | Stock: {avail_stock} | Price: ₹{med.price:.2f}"
        if med.is_expired:
            status_text += f" | ⚠️ EXPIRED ({med.expiry_date})"
            self.selected_med_lbl.configure(text=status_text, text_color=Theme.DANGER)
            self.add_cart_btn.configure(state="disabled")
        elif avail_stock <= 0:
            status_text += " | ⚠️ OUT OF STOCK"
            self.selected_med_lbl.configure(text=status_text, text_color=Theme.DANGER)
            self.add_cart_btn.configure(state="disabled")
        else:
            self.selected_med_lbl.configure(text=status_text, text_color=Theme.PRIMARY)
            self.add_cart_btn.configure(state="normal")

    def _on_add_to_cart(self) -> None:
        selected_items = self.inv_tree.selection()
        med_id = None
        if selected_items:
            try:
                med_id = int(selected_items[0])
            except ValueError:
                med_id = None
            self._selected_med_id = med_id
        elif getattr(self, "_selected_med_id", None) is not None:
            med_id = self._selected_med_id
        else:
            messagebox.showwarning("Select Medicine", "Please select a medicine from the table first.", parent=self)
            return

        med = self.medicine_service.get_medicine_by_id(med_id)
        if not med:
            return

        if med.is_expired:
            messagebox.showerror("Sale Blocked", f"Sale blocked: '{med.medicine_name}' has expired on {med.expiry_date}.", parent=self)
            return

        qty_str = self.add_qty_entry.get().strip()
        try:
            req_qty = int(qty_str)
            if req_qty <= 0:
                messagebox.showwarning("Invalid Quantity", "Quantity must be greater than zero.", parent=self)
                return
        except ValueError:
            messagebox.showwarning("Invalid Quantity", "Quantity must be an integer.", parent=self)
            return

        # Determine available stock and eligible batch
        avail_stock = med.quantity
        batch_id = getattr(self, "_selected_batch_id", None)
        b_no = getattr(self, "_selected_batch_no", med.batch_no)
        s_loc = getattr(self, "_selected_shelf_loc", "SHELF-A01")

        if hasattr(self.sales_service, "_table_exists") and self.sales_service._table_exists("inventory_batches"):
            today_iso = datetime.now().strftime("%Y-%m-%d")
            b_row = self.sales_service.db.fetch_one(
                """
                SELECT b.batch_id, b.batch_number, b.current_quantity, COALESCE(sl.shelf_code, 'SHELF-A01') as shelf_code
                FROM inventory_batches b
                LEFT JOIN storage_locations sl ON b.location_id = sl.location_id
                WHERE b.medicine_id = ? AND b.store_id = ? AND b.status IN ('Active', 'AVAILABLE')
                  AND b.current_quantity > 0 AND (b.expiry_date IS NULL OR b.expiry_date >= ?)
                ORDER BY b.expiry_date ASC, b.created_at ASC LIMIT 1
                """,
                (med_id, self.user.store_id, today_iso)
            )
            if b_row:
                batch_id = b_row["batch_id"]
                b_no = b_row["batch_number"] or b_no
                s_loc = b_row["shelf_code"] or s_loc

            b_total = self.sales_service.db.fetch_one(
                """
                SELECT COALESCE(SUM(current_quantity), 0) as total_qty
                FROM inventory_batches
                WHERE medicine_id = ? AND store_id = ? AND status IN ('Active', 'AVAILABLE')
                  AND current_quantity > 0 AND (expiry_date IS NULL OR expiry_date >= ?)
                """,
                (med_id, self.user.store_id, today_iso)
            )
            if b_total and b_total["total_qty"] > 0:
                avail_stock = max(avail_stock, b_total["total_qty"])

        # Check total quantity already in cart for this medicine
        existing_med_qty = sum(
            item["quantity"] for key, item in self.cart.items()
            if (isinstance(key, int) and key == med_id) or item.get("medicine_id") == med_id or getattr(item.get("medicine"), "medicine_id", None) == med_id
        )
        total_combined_qty = existing_med_qty + req_qty

        if total_combined_qty > avail_stock:
            messagebox.showerror(
                "Insufficient Stock",
                f"Insufficient stock for '{med.medicine_name}'.\n\nAvailable: {avail_stock}\nAlready in cart: {existing_med_qty}\nRequested: {req_qty}",
                parent=self
            )
            return

        # Check if an existing cart item has this exact medicine and batch
        cart_key = None
        for k, v in self.cart.items():
            if (k == med_id or v.get("medicine_id") == med_id) and v.get("batch_number") == b_no:
                cart_key = k
                break

        if cart_key is not None:
            new_qty = self.cart[cart_key]["quantity"] + req_qty
            self.cart[cart_key]["quantity"] = new_qty
            self.cart[cart_key]["subtotal"] = round(med.price * new_qty, 2)
            self.cart[cart_key]["batch_number"] = b_no
            self.cart[cart_key]["shelf_location"] = s_loc
            self.cart[cart_key]["batch_id"] = batch_id
            item_qty_disp = new_qty
        else:
            # If med_id is not yet in self.cart, use med_id as the key
            if med_id not in self.cart:
                cart_key = med_id
            else:
                cart_key = f"{med_id}_{b_no}"

            new_subtotal = round(med.price * req_qty, 2)
            self.cart[cart_key] = {
                "medicine": med,
                "medicine_id": med_id,
                "batch_id": batch_id,
                "quantity": req_qty,
                "batch_number": b_no,
                "shelf_location": s_loc,
                "subtotal": new_subtotal
            }
            item_qty_disp = req_qty

        self.refresh_cart_display()
        self.selected_med_lbl.configure(
            text=f"✓ Added {req_qty}x '{med.medicine_name}' to cart (Batch: {b_no}, Shelf: {s_loc}) | Cart Total: {item_qty_disp}",
            text_color=Theme.SUCCESS
        )

    def _on_edit_cart_qty(self) -> None:
        selected = self.cart_tree.selection()
        if not selected:
            messagebox.showwarning("Select Item", "Please select a cart item from the table to edit quantity.", parent=self)
            return
        cart_key_str = selected[0]
        cart_key = None
        if cart_key_str in self.cart:
            cart_key = cart_key_str
        elif cart_key_str.isdigit() and int(cart_key_str) in self.cart:
            cart_key = int(cart_key_str)

        if cart_key is None or cart_key not in self.cart:
            return

        cart_item = self.cart[cart_key]
        med = cart_item["medicine"]
        new_q_str = simpledialog.askstring("Edit Quantity", f"Enter new quantity for '{med.medicine_name}':", initialvalue=str(cart_item["quantity"]), parent=self)
        if not new_q_str:
            return
        try:
            new_q = int(new_q_str.strip())
            if new_q <= 0:
                messagebox.showwarning("Invalid Quantity", "Quantity must be > 0. To delete, click Remove.", parent=self)
                return

            avail_stock = med.quantity
            if hasattr(self.sales_service, "_table_exists") and self.sales_service._table_exists("inventory_batches"):
                today_iso = datetime.now().strftime("%Y-%m-%d")
                b_total = self.sales_service.db.fetch_one(
                    """
                    SELECT COALESCE(SUM(current_quantity), 0) as total_qty
                    FROM inventory_batches
                    WHERE medicine_id = ? AND store_id = ? AND status IN ('Active', 'AVAILABLE')
                      AND current_quantity > 0 AND (expiry_date IS NULL OR expiry_date >= ?)
                    """,
                    (med.medicine_id, self.user.store_id, today_iso)
                )
                if b_total and b_total["total_qty"] > 0:
                    avail_stock = max(avail_stock, b_total["total_qty"])

            if new_q > avail_stock:
                messagebox.showerror("Insufficient Stock", f"Available stock is {avail_stock}.", parent=self)
                return

            cart_item["quantity"] = new_q
            cart_item["subtotal"] = round(med.price * new_q, 2)
            self.refresh_cart_display()
            self.selected_med_lbl.configure(
                text=f"✓ Updated '{med.medicine_name}' quantity to {new_q} (Subtotal: ₹{cart_item['subtotal']:.2f})",
                text_color=Theme.SUCCESS
            )
        except ValueError:
            messagebox.showwarning("Invalid Quantity", "Quantity must be an integer.", parent=self)

    def _on_remove_cart_item(self) -> None:
        selected = self.cart_tree.selection()
        if not selected:
            messagebox.showwarning("Select Item", "Please select a cart item from the table to remove.", parent=self)
            return
        cart_key_str = selected[0]
        cart_key = None
        if cart_key_str in self.cart:
            cart_key = cart_key_str
        elif cart_key_str.isdigit() and int(cart_key_str) in self.cart:
            cart_key = int(cart_key_str)

        if cart_key is not None and cart_key in self.cart:
            med_name = self.cart[cart_key]["medicine"].medicine_name
            del self.cart[cart_key]
            self.refresh_cart_display()
            self.selected_med_lbl.configure(
                text=f"✓ Removed '{med_name}' from cart.",
                text_color=Theme.PRIMARY
            )

    def _on_clear_cart(self) -> None:
        if not self.cart:
            return
        if messagebox.askyesno("Clear Cart", "Are you sure you want to clear the shopping cart?", parent=self):
            self.cart.clear()
            self.refresh_cart_display()
            self.selected_med_lbl.configure(
                text="🛒 Cart cleared. Select a medicine to add to cart.",
                text_color=Theme.TEXT_MUTED
            )

    def refresh_cart_display(self) -> None:
        self.cart_tree.tag_configure("cart_item", background=Theme.BG_CARD, foreground=Theme.TEXT_MAIN, font=("Segoe UI", 9))
        self.cart_tree.tag_configure("cart_alt", background="#F8FAFC", foreground=Theme.TEXT_MAIN, font=("Segoe UI", 9))
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)

        raw_subtotal = 0.0
        for idx, (cart_key, item_data) in enumerate(self.cart.items()):
            med = item_data.get("medicine")
            if not med:
                continue
            qty = item_data.get("quantity", 0)
            subtot = item_data.get("subtotal", round(med.price * qty, 2))
            b_no = item_data.get("batch_number") or getattr(med, "batch_no", "")
            s_loc = item_data.get("shelf_location") or "SHELF-A01"
            raw_subtotal += subtot

            tag = "cart_item" if idx % 2 == 0 else "cart_alt"
            self.cart_tree.insert(
                "",
                "end",
                iid=str(cart_key),
                values=(
                    med.medicine_id,
                    med.medicine_code,
                    med.medicine_name,
                    b_no,
                    s_loc,
                    qty,
                    f"₹{med.price:.2f}",
                    f"₹{subtot:.2f}"
                ),
                tags=(tag,)
            )

        # Parse discount
        disc_val = 0.0
        try:
            disc_str = self.discount_entry.get().strip() if hasattr(self, "discount_entry") else "0"
            if disc_str:
                disc_val = max(0.0, float(disc_str))
        except Exception:
            disc_val = 0.0

        if not self.cart:
            raw_subtotal = 0.0
            disc_val = 0.0

        totals = calculate_bill_totals(subtotal=raw_subtotal, discount_amount=disc_val, tax_rate=0.0, enable_rounding=True)
        sub_t = totals["subtotal"]
        d_amt = totals["discount_amount"]
        g_tot = totals["grand_total"]

        if hasattr(self, "summary_breakdown_lbl"):
            self.summary_breakdown_lbl.configure(text=f"Subtotal: ₹{sub_t:.2f} | Discount: -₹{d_amt:.2f} | Tax (Not Configured): ₹0.00")
        if hasattr(self, "grand_total_lbl"):
            self.grand_total_lbl.configure(text=f"PAYABLE TOTAL: ₹{g_tot:.2f}")

        self._update_checkout_button_state()

    def _update_checkout_button_state(self) -> None:
        """Updates checkout button visual state and descriptive status text."""
        if getattr(self, "_is_processing_checkout", False):
            self.checkout_btn.configure(
                state="disabled",
                fg_color=Theme.BORDER_COLOR,
                text="⏳ Processing FEFO Checkout..."
            )
            return

        if self.cart and self.phone_valid:
            self.checkout_btn.configure(
                state="normal",
                fg_color=Theme.PRIMARY,
                hover_color=Theme.PRIMARY_HOVER,
                text="💳 Complete FEFO Checkout & Generate Invoice"
            )
        elif not self.cart:
            self.checkout_btn.configure(
                state="normal",
                fg_color=Theme.BORDER_COLOR,
                hover_color="#334155",
                text="💳 Cart Empty — Add Medicines to Checkout"
            )
        else:
            self.checkout_btn.configure(
                state="normal",
                fg_color=Theme.BORDER_COLOR,
                hover_color="#334155",
                text="💳 Enter Valid 10-Digit Mobile to Checkout"
            )

    def _on_checkout(self) -> None:
        """Processes atomic FEFO sale checkout."""
        if getattr(self, "_is_processing_checkout", False):
            return

        # 0. Sale Date Validation (Mandatory)
        sale_date_val = self.sale_date_entry.get().strip() if hasattr(self, "sale_date_entry") else ""
        if not sale_date_val:
            messagebox.showerror("Validation Error", "Sale Date is required (YYYY-MM-DD).", parent=self)
            if hasattr(self, "sale_date_entry"):
                self.sale_date_entry.focus()
            return
        try:
            datetime.strptime(sale_date_val, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Validation Error", "Sale Date must be a valid date in YYYY-MM-DD format.", parent=self)
            if hasattr(self, "sale_date_entry"):
                self.sale_date_entry.focus()
            return

        # 1. Cart Validation
        if not self.cart:
            messagebox.showwarning(
                "Empty Cart",
                "Shopping cart is empty. Please select a medicine and click 'Add to Cart'.",
                parent=self
            )
            return

        # 2. Customer Name (Auto-defaults to 'Walk-in Customer' if empty)
        pat_name = self.pat_name_entry.get().strip() or "Walk-in Customer"

        # 3. Mandatory 10-Digit Indian Mobile Phone Validation (Poka-Yoke)
        pat_phone = self.pat_phone_entry.get().strip()
        if not pat_phone:
            self.phone_feedback_lbl.configure(
                text="⚠️ Customer mobile number is required.",
                text_color=Theme.DANGER
            )
            messagebox.showerror(
                "Validation Error",
                "Customer mobile number is required for billing. Please enter a valid 10-digit Indian mobile number.",
                parent=self
            )
            self.pat_phone_entry.focus()
            return

        is_valid, err_msg, cleaned_phone = validate_indian_phone(pat_phone)
        if not is_valid:
            self.phone_feedback_lbl.configure(text=f"⚠️ {err_msg}", text_color=Theme.DANGER)
            messagebox.showerror(
                "Validation Error",
                f"A valid 10-digit Indian mobile number (starting with 6, 7, 8, or 9) is required for billing.\n\n{err_msg}",
                parent=self
            )
            self.pat_phone_entry.focus()
            return

        # 4. Age Validation
        age_val = None
        age_str = self.pat_age_entry.get().strip()
        if age_str:
            try:
                age_val = int(age_str)
                if age_val < 0 or age_val > 150:
                    raise ValueError()
            except ValueError:
                messagebox.showerror("Validation Error", "Age must be a valid integer between 0 and 150.", parent=self)
                self.pat_age_entry.focus()
                return

        # 5. Discount Calculation
        disc_val = 0.0
        try:
            disc_str = self.discount_entry.get().strip()
            if disc_str:
                disc_val = max(0.0, float(disc_str))
        except ValueError:
            disc_val = 0.0

        # 6. Payment Method and Reference
        pm = self.pm_segmented.get() or "Cash"
        pref = self.pref_entry.get().strip() if pm in ("UPI", "Card") else None

        med_totals: Dict[int, int] = {}
        for k, d in self.cart.items():
            m_id = d.get("medicine_id") or (k if isinstance(k, int) else getattr(d.get("medicine"), "medicine_id", None))
            if m_id:
                med_totals[m_id] = med_totals.get(m_id, 0) + d["quantity"]
        cart_items_list = list(med_totals.items())

        self._is_processing_checkout = True
        self._update_checkout_button_state()
        try:
            success, msg, sale_id, inv_num = self.sales_service.process_sale(
                user_id=self.user.user_id,
                cart_items=cart_items_list,
                patient_name=pat_name,
                patient_phone=cleaned_phone,
                patient_age=age_val,
                discount_amount=disc_val,
                sale_date=sale_date_val,
                tax_rate=0.0,
                payment_method=pm,
                payment_reference=pref,
                acting_user=self.user
            )

            if success and sale_id:
                sale_details = self.sales_service.get_sale_details(sale_id, acting_user=self.user)
                self.last_sale_details = sale_details
                if hasattr(self, "view_invoice_btn"):
                    self.view_invoice_btn.configure(state="normal")
                if hasattr(self, "save_pdf_btn"):
                    self.save_pdf_btn.configure(state="normal")
                if sale_details:
                    self._active_invoice_modal = InvoiceReceiptModal(self, sale_details)

                # Reset Form after successful commit
                self.cart.clear()
                self.pat_name_entry.delete(0, "end")
                self.pat_phone_entry.delete(0, "end")
                self.pat_age_entry.delete(0, "end")
                self.discount_entry.delete(0, "end")
                self.discount_entry.insert(0, "0.00")
                if pm in ("UPI", "Card"):
                    self.pref_entry.delete(0, "end")
                self.phone_valid = False
                self.phone_feedback_lbl.configure(text="", text_color=Theme.TEXT_MUTED)
                self.refresh_cart_display()
                self._on_search_medicine()
                self._refresh_invoices_tab()
            else:
                messagebox.showerror("Checkout Failed", msg, parent=self)
        except Exception as e:
            messagebox.showerror("Checkout Failed", f"Checkout failed due to an unexpected error:\n{e}", parent=self)
        finally:
            self._is_processing_checkout = False
            self._update_checkout_button_state()

    def _on_view_last_invoice(self) -> None:
        """Opens receipt modal for the most recently billed invoice."""
        if self.last_sale_details:
            self._active_invoice_modal = InvoiceReceiptModal(self, self.last_sale_details)
        else:
            messagebox.showinfo("No Invoice", "No invoice available to view. Complete a checkout first.", parent=self)

    def _on_save_pdf(self) -> None:
        """Saves PDF file directly for the most recently billed invoice."""
        if self.last_sale_details:
            try:
                from utils.pdf_generator import generate_invoice_pdf
                filepath = generate_invoice_pdf(self.last_sale_details)
                messagebox.showinfo("PDF Saved", f"Invoice saved successfully as PDF: " + str(filepath), parent=self)
            except Exception as e:
                messagebox.showerror("Export Error", f"Failed to save PDF: {e}", parent=self)
        else:
            messagebox.showinfo("No Invoice", "No invoice available to save. Complete a checkout first.", parent=self)

    def _refresh_invoices_tab(self) -> None:
        # 1. Update Shift Metrics
        summary = self.sales_service.get_cashier_summary(cashier_user_id=None)
        if hasattr(self, "shift_labels"):
            self.shift_labels["bills_count"].configure(text=str(summary.get("bills_count", 0)))
            self.shift_labels["gross_sales"].configure(text=f"₹{summary.get('gross_sales', 0.0):.2f}")
            self.shift_labels["cash_coll"].configure(text=f"₹{summary.get('cash_collections', 0.0):.2f}")
            self.shift_labels["upi_coll"].configure(text=f"₹{summary.get('upi_collections', 0.0):.2f}")
            self.shift_labels["card_coll"].configure(text=f"₹{summary.get('card_collections', 0.0):.2f}")
            self.shift_labels["refunds"].configure(text=f"₹{summary.get('total_refunds', 0.0):.2f}")
            self.shift_labels["net_sales"].configure(text=f"₹{summary.get('net_settled_sales', 0.0):.2f}")

        # 2. Update Invoices Treeview
        for item in self.invoice_tree.get_children():
            self.invoice_tree.delete(item)

        sales = self.sales_service.get_recent_sales(limit=60, acting_user=self.user)
        for s in sales:
            self.invoice_tree.insert(
                "",
                "end",
                iid=str(s["sale_id"]),
                values=(
                    s["sale_id"],
                    s.get("invoice_number", f"INV-{s['sale_id']}"),
                    s.get("sale_date", ""),
                    s.get("patient_name", "Walk-in"),
                    s.get("patient_phone", ""),
                    f"₹{float(s['total_amount']):.2f}",
                    s.get("payment_method", "Cash"),
                    s.get("status", "COMPLETED"),
                    s.get("username", "Staff")
                )
            )

    def _on_reprint_invoice(self) -> None:
        sel = self.invoice_tree.selection()
        if not sel:
            messagebox.showwarning("Select Invoice", "Please select an invoice from the list to reprint.")
            return
        sale_id = int(sel[0])
        sale_details = self.sales_service.get_sale_details(sale_id, acting_user=self.user)
        if sale_details:
            InvoiceReceiptModal(self, sale_details)
        else:
            messagebox.showerror("Error", "Could not load invoice details.")

    def _on_open_return_modal(self) -> None:
        sel = self.invoice_tree.selection()
        if not sel:
            messagebox.showwarning("Select Invoice", "Please select an invoice to process a return.")
            return
        sale_id = int(sel[0])
        sale_details = self.sales_service.get_sale_details(sale_id, acting_user=self.user)
        if not sale_details:
            messagebox.showerror("Error", "Could not load invoice details.")
            return

        if sale_details.get("status") == "REFUNDED":
            messagebox.showwarning("Already Refunded", "This invoice has already been fully refunded.")
            return

        ReturnItemModal(self, self.sales_service, self.user, sale_details, on_success_callback=self._refresh_invoices_tab)
