"""
Purchase Order Entry and Goods Receiving View for Pharmacy Management System.
Allows procurement staff and store managers to record supplier invoices,
receive manufacturer batches, validate shelf locations on the fly, and post to ledger.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict, Any
from datetime import datetime
import customtkinter as ctk

from ui.theme import Theme
from models.user import User
from models.purchase import Purchase
from services.purchase_service import PurchaseService
from services.supplier_service import SupplierService
from services.shelf_service import ShelfService
from services.medicine_service import MedicineService
from database.db import get_db
from utils.logger import get_app_logger



class PurchaseOrderInvoiceModal(ctk.CTkToplevel):
    """Modal dialog displaying official Purchase Order invoice with PDF and print options."""

    def __init__(self, parent, purchase: Purchase):
        super().__init__(parent)
        self.purchase = purchase

        inv_num = purchase.invoice_number or f"PO-{purchase.purchase_id}"
        self.title(f"Purchase Order Invoice - {inv_num}")
        self.geometry("720x620")
        self.minsize(600, 480)
        self.resizable(True, True)
        self.configure(fg_color=Theme.BG_DARK)

        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self._build_ui()

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        # 1. Header Frame (Top)
        hdr = ctk.CTkFrame(container, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4), side="top")

        ctk.CTkLabel(hdr, text="📄 Purchase Order & Supplier Invoice", font=Theme.FONT_TITLE, text_color=Theme.PRIMARY).pack(anchor="w")

        p = self.purchase
        supp_name = p.supplier_name or f"Supplier #{p.supplier_id}"
        sub_text = f"PO #{p.invoice_number} | Supplier: {supp_name} | Date: {p.purchase_date} | Status: {p.status}"
        ctk.CTkLabel(hdr, text=sub_text, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(2, 0))

        # 2. Fixed Footer Buttons (Bottom)
        ftr = ctk.CTkFrame(container, fg_color="transparent")
        ftr.pack(fill="x", padx=16, pady=(10, 14), side="bottom")

        ctk.CTkButton(
            ftr,
            text="Close",
            width=90,
            height=34,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self.destroy
        ).pack(side="left")

        ctk.CTkButton(
            ftr,
            text="🖨️ Print Invoice",
            width=120,
            height=34,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self._handle_print
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            ftr,
            text="💾 Save PO as PDF",
            width=140,
            height=34,
            font=Theme.FONT_BOLD,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self._handle_save_pdf
        ).pack(side="right")

        # 3. Summary & Line Items Table (Middle)
        body = ctk.CTkScrollableFrame(container, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=(6, 6), side="top")

        # Info card
        info_card = ctk.CTkFrame(body, fg_color=Theme.BG_DARK, corner_radius=8, border_width=1, border_color=Theme.BORDER_COLOR)
        info_card.pack(fill="x", pady=(0, 10))

        r1 = ctk.CTkFrame(info_card, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(8, 2))
        ctk.CTkLabel(r1, text=f"Store ID: {p.store_id}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).pack(side="left")
        ctk.CTkLabel(r1, text=f"Payment Status: {p.payment_status}", font=Theme.FONT_BOLD, text_color=Theme.SUCCESS if p.payment_status == 'PAID' else Theme.WARNING).pack(side="right")

        if p.notes:
            r2 = ctk.CTkFrame(info_card, fg_color="transparent")
            r2.pack(fill="x", padx=12, pady=(0, 8))
            ctk.CTkLabel(r2, text=f"Notes: {p.notes}", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="left")

        # Items Table Header
        th = ctk.CTkFrame(body, fg_color=Theme.DEEP_NAVY, corner_radius=6)
        th.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(th, text="#", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=30, anchor="center").pack(side="left", padx=4)
        ctk.CTkLabel(th, text="Medicine Description", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=220, anchor="w").pack(side="left", padx=6)
        ctk.CTkLabel(th, text="Batch", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=100, anchor="center").pack(side="left", padx=4)
        ctk.CTkLabel(th, text="Qty", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=50, anchor="center").pack(side="left", padx=4)
        ctk.CTkLabel(th, text="Rate (₹)", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=80, anchor="e").pack(side="left", padx=4)
        ctk.CTkLabel(th, text="Subtotal (₹)", font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK, width=90, anchor="e").pack(side="left", padx=6)

        total_units = 0
        total_val = 0.0
        for idx, item in enumerate(p.items, start=1):
            row = ctk.CTkFrame(body, fg_color=Theme.BG_DARK if idx % 2 == 0 else "transparent", corner_radius=4)
            row.pack(fill="x", pady=2)

            med_name = getattr(item, "medicine_name", f"Medicine #{item.medicine_id}")
            batch_no = getattr(item, "batch_number", None) or "-"
            qty = getattr(item, "quantity", 0)
            rate = getattr(item, "purchase_price", 0.0)
            subtotal = getattr(item, "subtotal", qty * rate)

            total_units += qty
            total_val += subtotal

            ctk.CTkLabel(row, text=str(idx), font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED, width=30, anchor="center").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=med_name, font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=220, anchor="w").pack(side="left", padx=6)
            ctk.CTkLabel(row, text=batch_no, font=Theme.FONT_SMALL, text_color=Theme.PRIMARY, width=100, anchor="center").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=str(qty), font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=50, anchor="center").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{rate:.2f}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN, width=80, anchor="e").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=f"₹{subtotal:.2f}", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN, width=90, anchor="e").pack(side="left", padx=6)

        # Totals Row
        tot_row = ctk.CTkFrame(body, fg_color=Theme.BG_CARD, corner_radius=6, border_width=1, border_color=Theme.BORDER_COLOR)
        tot_row.pack(fill="x", pady=(10, 4))
        ctk.CTkLabel(tot_row, text=f"Total Units: {total_units}", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MUTED).pack(side="left", padx=16, pady=8)
        grand_total = p.total_amount or total_val
        ctk.CTkLabel(tot_row, text=f"TOTAL PURCHASE VALUE: ₹{grand_total:,.2f}", font=Theme.FONT_TITLE, text_color=Theme.PRIMARY).pack(side="right", padx=16, pady=8)

    def _handle_save_pdf(self) -> None:
        try:
            from utils.pdf_generator import generate_purchase_order_pdf
            p_dict = {
                "purchase_id": self.purchase.purchase_id,
                "invoice_number": self.purchase.invoice_number,
                "purchase_date": self.purchase.purchase_date,
                "supplier_name": self.purchase.supplier_name,
                "supplier_id": self.purchase.supplier_id,
                "store_id": self.purchase.store_id,
                "status": self.purchase.status,
                "payment_status": self.purchase.payment_status,
                "total_amount": self.purchase.total_amount,
                "notes": self.purchase.notes,
                "items": [
                    {
                        "medicine_name": getattr(it, "medicine_name", f"Medicine #{it.medicine_id}"),
                        "batch_number": getattr(it, "batch_number", "-"),
                        "quantity": it.quantity,
                        "purchase_price": it.purchase_price,
                        "subtotal": it.subtotal
                    }
                    for it in self.purchase.items
                ]
            }
            filepath = generate_purchase_order_pdf(p_dict)
            messagebox.showinfo("PO PDF Exported", f"Purchase Order PDF saved successfully:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to generate PO PDF: {e}", parent=self)

    def _handle_print(self) -> None:
        try:
            from utils.pdf_generator import generate_purchase_order_pdf, print_pdf
            p_dict = {
                "purchase_id": self.purchase.purchase_id,
                "invoice_number": self.purchase.invoice_number,
                "purchase_date": self.purchase.purchase_date,
                "supplier_name": self.purchase.supplier_name,
                "supplier_id": self.purchase.supplier_id,
                "store_id": self.purchase.store_id,
                "status": self.purchase.status,
                "payment_status": self.purchase.payment_status,
                "total_amount": self.purchase.total_amount,
                "notes": self.purchase.notes,
                "items": [
                    {
                        "medicine_name": getattr(it, "medicine_name", f"Medicine #{it.medicine_id}"),
                        "batch_number": getattr(it, "batch_number", "-"),
                        "quantity": it.quantity,
                        "purchase_price": it.purchase_price,
                        "subtotal": it.subtotal
                    }
                    for it in self.purchase.items
                ]
            }
            filepath = generate_purchase_order_pdf(p_dict)
            print_pdf(filepath)
            messagebox.showinfo("Printing", "Purchase Order document sent to printer.", parent=self)
        except Exception as e:
            messagebox.showerror("Print Error", f"Print failed: {e}", parent=self)


class PurchaseEntryView(ctk.CTkFrame):
    """Purchase management and goods receiving screen."""

    def __init__(self, parent, user: User, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_DARK, **kwargs)
        self.user = user
        self.logger = get_app_logger()
        self.db = get_db()
        self.purchase_service = PurchaseService(self.db)
        self.supplier_service = SupplierService(self.db)
        self.shelf_service = ShelfService(self.db)
        self.medicine_service = MedicineService(self.db)

        self.purchases_cache: List[Purchase] = []

        self._build_ui()
        self.refresh_table()

    def _build_ui(self) -> None:
        """Constructs header toolbar, status filter bar, and purchase list."""
        toolbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60, corner_radius=8)
        toolbar.pack(side="top", fill="x", padx=16, pady=(16, 10))
        toolbar.pack_propagate(False)

        ctk.CTkLabel(
            toolbar,
            text="📦  Purchasing & Goods Receiving",
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_MAIN
        ).pack(side="left", padx=16, pady=12)

        # "+ New Purchase Order" button
        if self.user.canonical_role in ("Owner", "Admin", "Inventory Manager"):
            ctk.CTkButton(
                toolbar,
                text="➕  New Purchase Order",
                font=Theme.FONT_SUBHEADING,
                fg_color=Theme.PRIMARY,
                hover_color=Theme.PRIMARY_HOVER,
                text_color=Theme.TEXT_DARK,
                command=self._open_new_purchase_modal
            ).pack(side="right", padx=16, pady=12)

        # Filter bar
        filter_bar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50, corner_radius=8)
        filter_bar.pack(side="top", fill="x", padx=16, pady=(0, 10))
        filter_bar.pack_propagate(False)

        ctk.CTkLabel(filter_bar, text="Filter Status:", font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(side="left", padx=(16, 8))

        self.status_filter_var = tk.StringVar(value="All")
        self.status_combo = ctk.CTkComboBox(
            filter_bar,
            values=["All", "DRAFT", "RECEIVED", "CANCELLED"],
            variable=self.status_filter_var,
            width=130,
            height=32,
            font=Theme.FONT_BODY,
            command=lambda v: self._apply_filter()
        )
        self.status_combo.pack(side="left", padx=8, pady=8)

        ctk.CTkButton(
            filter_bar,
            text="🔄 Refresh",
            width=90,
            height=32,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self.refresh_table
        ).pack(side="right", padx=16, pady=8)

        # Scrollable purchase items container
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(side="top", fill="both", expand=True, padx=16, pady=(0, 16))

    def refresh_table(self) -> None:
        """Fetches purchases for store."""
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        if not self.purchase_service._table_exists("purchases"):
            card = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_CARD, corner_radius=8, height=120)
            card.pack(fill="x", pady=10)
            ctk.CTkLabel(
                card,
                text="⚠️ Purchasing tables (purchases) are not present in this database.\n"
                     "The original production database remains safely unmigrated per Stage 4 safety policy.",
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MUTED
            ).pack(expand=True, pady=30)
            return

        try:
            self.purchases_cache = self.purchase_service.get_purchases(
                store_id=self.user.store_id,
                acting_user=self.user,
                limit=100
            )
            self._apply_filter()
        except Exception as e:
            self.logger.log_event("PURCHASES", f"Error loading purchases: {e}", level="ERROR")

    def _apply_filter(self) -> None:
        """Applies status filter to cached purchases and renders cards."""
        status_val = self.status_filter_var.get()
        filtered = [
            p for p in self.purchases_cache
            if status_val == "All" or p.status == status_val
        ]
        self._render_purchases(filtered)

    def _render_purchases(self, purchases: List[Purchase]) -> None:
        """Renders purchase cards."""
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        if not purchases:
            empty_card = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_CARD, corner_radius=8, height=120)
            empty_card.pack(fill="x", pady=10)
            ctk.CTkLabel(
                empty_card,
                text="No purchases found. Click 'New Purchase Order' to initiate vendor procurement.",
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MUTED
            ).pack(expand=True, pady=30)
            return

        for p in purchases:
            card = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_CARD, corner_radius=8)
            card.pack(fill="x", pady=6, padx=2)

            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=16, pady=(12, 6))

            ctk.CTkLabel(
                top_row,
                text=f"📄 Invoice #{p.invoice_number}",
                font=Theme.FONT_SUBHEADING,
                text_color=Theme.TEXT_MAIN
            ).pack(side="left")

            # Status Badge
            if p.status == "RECEIVED":
                badge_color = Theme.SUCCESS
            elif p.status == "DRAFT":
                badge_color = Theme.WARNING
            else:
                badge_color = Theme.DANGER

            ctk.CTkLabel(
                top_row,
                text=f"  {p.status}  ",
                font=Theme.FONT_SMALL,
                fg_color=badge_color,
                text_color=Theme.TEXT_DARK,
                corner_radius=4
            ).pack(side="left", padx=12)

            ctk.CTkLabel(
                top_row,
                text=f"🏢 Supplier: {p.supplier_name or 'ID ' + str(p.supplier_id)}",
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MUTED
            ).pack(side="left", padx=8)

            ctk.CTkLabel(
                top_row,
                text=f"Total: ₹{p.total_amount:,.2f}",
                font=Theme.FONT_BOLD,
                text_color=Theme.PRIMARY
            ).pack(side="right")

            # Middle meta row
            mid_row = ctk.CTkFrame(card, fg_color="transparent")
            mid_row.pack(fill="x", padx=16, pady=(0, 10))

            meta_text = f"📅 Purchase Date: {p.purchase_date}"
            if p.notes:
                meta_text += f"   |   Notes: {p.notes}"
            ctk.CTkLabel(
                mid_row,
                text=meta_text,
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_MUTED
            ).pack(side="left")

            # Action buttons for ALL purchase records
            btn_frame = ctk.CTkFrame(mid_row, fg_color="transparent")
            btn_frame.pack(side="right")

            # 1. View PO Invoice Modal
            ctk.CTkButton(
                btn_frame,
                text="📄 View PO Invoice",
                width=115,
                height=28,
                font=Theme.FONT_SMALL,
                fg_color=Theme.INPUT_BG,
                hover_color=Theme.BORDER_COLOR,
                text_color=Theme.TEXT_MAIN,
                command=lambda pid=p.purchase_id: self._open_po_invoice_modal(pid)
            ).pack(side="left", padx=3)

            # 2. Save PO as PDF
            ctk.CTkButton(
                btn_frame,
                text="💾 Save PDF",
                width=85,
                height=28,
                font=Theme.FONT_SMALL,
                fg_color=Theme.INPUT_BG,
                hover_color=Theme.BORDER_COLOR,
                text_color=Theme.TEXT_MAIN,
                command=lambda pid=p.purchase_id: self._save_po_pdf(pid)
            ).pack(side="left", padx=3)

            # 3. Actions for DRAFT status (Receive Goods & Cancel)
            if p.status == "DRAFT" and self.user.canonical_role in ("Owner", "Admin", "Inventory Manager"):
                ctk.CTkButton(
                    btn_frame,
                    text="📥 Receive Goods",
                    width=115,
                    height=28,
                    font=Theme.FONT_SMALL,
                    fg_color=Theme.PRIMARY,
                    hover_color=Theme.PRIMARY_HOVER,
                    text_color=Theme.TEXT_DARK,
                    command=lambda pid=p.purchase_id: self._open_goods_receiving_modal(pid)
                ).pack(side="left", padx=3)

                ctk.CTkButton(
                    btn_frame,
                    text="❌ Cancel",
                    width=70,
                    height=28,
                    font=Theme.FONT_SMALL,
                    fg_color="transparent",
                    text_color=Theme.DANGER,
                    hover_color=Theme.INPUT_BG,
                    command=lambda pid=p.purchase_id: self._cancel_purchase(pid)
                ).pack(side="left", padx=3)

    def _cancel_purchase(self, purchase_id: int) -> None:
        """Prompts confirmation to cancel draft purchase."""
        if messagebox.askyesno("Confirm Cancellation", "Are you sure you want to cancel this purchase order?"):
            try:
                self.purchase_service.cancel_purchase(
                    purchase_id=purchase_id,
                    reason="User requested cancellation via UI",
                    store_id=self.user.store_id,
                    acting_user=self.user
                )
                self.refresh_table()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to cancel purchase: {e}")

    def _open_new_purchase_modal(self) -> None:
        """Opens modal dialog to create a new purchase order."""
        suppliers = self.supplier_service.get_suppliers(self.user.store_id, is_active=True, acting_user=self.user)
        if not suppliers:
            messagebox.showwarning(
                "No Suppliers Found",
                "Please add at least one active supplier before creating a purchase order."
            )
            return

        medicines = self.medicine_service.get_medicines_by_store(self.user.store_id)
        if not medicines:
            messagebox.showwarning("No Medicines", "No medicines found in catalog.")
            return

        modal = ctk.CTkToplevel(self)
        modal.title("New Purchase Order")
        modal.geometry("640x620")
        modal.transient(self)
        modal.grab_set()

        form = ctk.CTkFrame(modal, fg_color=Theme.BG_CARD, corner_radius=8)
        form.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(form, text="📦  Create Purchase Order", font=Theme.FONT_HEADING, text_color=Theme.TEXT_MAIN).pack(anchor="w", padx=20, pady=(16, 12))

        # Supplier selector
        ctk.CTkLabel(form, text="Select Supplier *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=20, pady=(4, 2))
        supp_map = {f"{s.supplier_name} ({s.supplier_code})": s.supplier_id for s in suppliers}
        supp_combo = ctk.CTkComboBox(form, values=list(supp_map.keys()), width=400, height=32, font=Theme.FONT_BODY)
        supp_combo.pack(fill="x", padx=20, pady=(0, 6))

        # Invoice Number & Date row
        row1 = ctk.CTkFrame(form, fg_color="transparent")
        row1.pack(fill="x", padx=20, pady=(0, 8))

        inv_col = ctk.CTkFrame(row1, fg_color="transparent")
        inv_col.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkLabel(inv_col, text="Invoice Number *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")
        inv_ent = ctk.CTkEntry(inv_col, height=32, font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        inv_ent.pack(fill="x")
        inv_ent.insert(0, f"INV-{int(datetime.now().timestamp())}")

        date_col = ctk.CTkFrame(row1, fg_color="transparent")
        date_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(date_col, text="Purchase Date * (YYYY-MM-DD)", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")
        date_ent = ctk.CTkEntry(date_col, height=32, font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        date_ent.pack(fill="x")
        date_ent.insert(0, datetime.now().strftime("%Y-%m-%d"))

        # Items section
        ctk.CTkLabel(form, text="Purchase Items:", font=Theme.FONT_SUBHEADING, text_color=Theme.TEXT_MAIN).pack(anchor="w", padx=20, pady=(10, 4))

        med_map = {f"{m.medicine_name} ({m.medicine_code})": m for m in medicines}
        items_frame = ctk.CTkScrollableFrame(form, fg_color=Theme.INPUT_BG, height=180, corner_radius=6)
        items_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        item_rows = []

        def _add_item_row():
            r = ctk.CTkFrame(items_frame, fg_color=Theme.BG_CARD, corner_radius=6)
            r.pack(fill="x", pady=4, padx=4)

            m_combo = ctk.CTkComboBox(r, values=list(med_map.keys()), width=240, height=28, font=Theme.FONT_SMALL)
            m_combo.pack(side="left", padx=4, pady=4)

            q_ent = ctk.CTkEntry(r, placeholder_text="Qty", width=70, height=28, font=Theme.FONT_SMALL)
            q_ent.pack(side="left", padx=4, pady=4)

            c_ent = ctk.CTkEntry(r, placeholder_text="Unit Cost", width=80, height=28, font=Theme.FONT_SMALL)
            c_ent.pack(side="left", padx=4, pady=4)

            sub_lbl = ctk.CTkLabel(r, text="₹0.00", width=80, font=Theme.FONT_SMALL, text_color=Theme.PRIMARY)
            sub_lbl.pack(side="left", padx=4, pady=4)

            def _recalc(*_):
                try:
                    q = int(q_ent.get() or 0)
                    c = float(c_ent.get() or 0.0)
                    sub_lbl.configure(text=f"₹{q * c:,.2f}")
                except Exception:
                    pass

            q_ent.bind("<KeyRelease>", _recalc)
            c_ent.bind("<KeyRelease>", _recalc)

            item_rows.append({"med_combo": m_combo, "qty_ent": q_ent, "cost_ent": c_ent, "frame": r})

        _add_item_row()

        ctk.CTkButton(
            form, text="➕ Add Another Item", font=Theme.FONT_SMALL,
            height=26, fg_color="transparent", text_color=Theme.PRIMARY,
            command=_add_item_row
        ).pack(anchor="w", padx=20, pady=(0, 8))

        err_label = ctk.CTkLabel(form, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER)
        err_label.pack(padx=20, pady=2)

        def _save_po():
            supp_name = supp_combo.get()
            supplier_id = supp_map.get(supp_name)
            inv_num = inv_ent.get().strip()
            p_date = date_ent.get().strip()

            items_to_save = []
            for ir in item_rows:
                m_label = ir["med_combo"].get()
                med = med_map.get(m_label)
                if not med:
                    continue
                try:
                    qty = int(ir["qty_ent"].get() or 0)
                    cost = float(ir["cost_ent"].get() or 0.0)
                except ValueError:
                    err_label.configure(text="Quantities must be integers and unit costs must be numbers.")
                    return

                if qty <= 0:
                    continue
                items_to_save.append({
                    "medicine_id": med.medicine_id,
                    "quantity": qty,
                    "unit_cost": cost,
                    "subtotal": round(qty * cost, 2)
                })

            if not items_to_save:
                err_label.configure(text="Please specify at least one valid item with quantity > 0.")
                return

            try:
                self.purchase_service.create_purchase(
                    store_id=self.user.store_id,
                    supplier_id=supplier_id,
                    invoice_number=inv_num,
                    purchase_date=p_date,
                    items=items_to_save,
                    status="DRAFT",
                    acting_user=self.user
                )
                modal.destroy()
                self.refresh_table()
                messagebox.showinfo("Success", f"Purchase order '{inv_num}' created as DRAFT.")
            except Exception as ex:
                err_label.configure(text=str(ex))

        ctk.CTkButton(
            form, text="Save Purchase Order",
            font=Theme.FONT_SUBHEADING, fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK,
            command=_save_po
        ).pack(fill="x", padx=20, pady=12)

    def _open_goods_receiving_modal(self, purchase_id: int) -> None:
        """
        Goods Receiving Modal:
        Enforces Critical Shelf Allocation Rule on each batch before receipt.
        """
        purchase = self.purchase_service.get_purchase_by_id(purchase_id, store_id=self.user.store_id, acting_user=self.user)
        if not purchase:
            return

        locations = self.shelf_service.get_storage_locations(self.user.store_id, is_active=True)
        if not locations:
            # Seed standard default shelf if none exists
            loc_id = self.shelf_service.get_or_create_location(self.user.store_id, "Shelf A-01")
            locations = self.shelf_service.get_storage_locations(self.user.store_id, is_active=True)

        loc_map = {f"{l['shelf_code']} ({l.get('rack') or 'General'})": l['location_id'] for l in locations}

        modal = ctk.CTkToplevel(self)
        modal.title(f"Receive Goods — Invoice #{purchase.invoice_number}")
        modal.geometry("700x640")
        modal.transient(self)
        modal.grab_set()

        form = ctk.CTkFrame(modal, fg_color=Theme.BG_CARD, corner_radius=8)
        form.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            form,
            text=f"📥  Receive Goods: Invoice #{purchase.invoice_number}",
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_MAIN
        ).pack(anchor="w", padx=20, pady=(16, 6))

        ctk.CTkLabel(
            form,
            text="Assign manufacturer batch number, expiry date, and storage shelf for each delivered medicine.",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", padx=20, pady=(0, 10))

        scroll_items = ctk.CTkScrollableFrame(form, fg_color=Theme.INPUT_BG, height=380, corner_radius=6)
        scroll_items.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        receipt_rows = []

        for it in purchase.items:
            item_box = ctk.CTkFrame(scroll_items, fg_color=Theme.BG_CARD, corner_radius=6)
            item_box.pack(fill="x", pady=6, padx=4)

            # Medicine title
            m_row = ctk.CTkFrame(item_box, fg_color="transparent")
            m_row.pack(fill="x", padx=10, pady=(8, 4))
            ctk.CTkLabel(
                m_row,
                text=f"💊 {it.medicine_name or 'Medicine ID ' + str(it.medicine_id)}",
                font=Theme.FONT_SUBHEADING,
                text_color=Theme.TEXT_MAIN
            ).pack(side="left")
            ctk.CTkLabel(
                m_row,
                text=f"Ordered: {it.quantity} units @ ₹{it.unit_cost:,.2f}",
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_MUTED
            ).pack(side="right")

            fields_row = ctk.CTkFrame(item_box, fg_color="transparent")
            fields_row.pack(fill="x", padx=10, pady=(0, 8))

            # Batch Number
            b_frame = ctk.CTkFrame(fields_row, fg_color="transparent")
            b_frame.pack(side="left", padx=4)
            ctk.CTkLabel(b_frame, text="Batch Number *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")
            b_ent = ctk.CTkEntry(b_frame, placeholder_text="e.g. B202701", width=110, height=28, font=Theme.FONT_SMALL)
            b_ent.pack()

            # Expiry Date
            exp_frame = ctk.CTkFrame(fields_row, fg_color="transparent")
            exp_frame.pack(side="left", padx=4)
            ctk.CTkLabel(exp_frame, text="Expiry (YYYY-MM-DD) *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")
            exp_ent = ctk.CTkEntry(exp_frame, placeholder_text="2027-12-31", width=120, height=28, font=Theme.FONT_SMALL)
            exp_ent.pack()

            # Shelf Location
            loc_frame = ctk.CTkFrame(fields_row, fg_color="transparent")
            loc_frame.pack(side="left", padx=4)
            ctk.CTkLabel(loc_frame, text="Shelf Location *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")
            loc_combo = ctk.CTkComboBox(loc_frame, values=list(loc_map.keys()), width=150, height=28, font=Theme.FONT_SMALL)
            loc_combo.pack()

            # Qty Received
            qty_frame = ctk.CTkFrame(fields_row, fg_color="transparent")
            qty_frame.pack(side="left", padx=4)
            ctk.CTkLabel(qty_frame, text="Qty Received *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")
            q_ent = ctk.CTkEntry(qty_frame, width=70, height=28, font=Theme.FONT_SMALL)
            q_ent.pack()
            q_ent.insert(0, str(it.quantity))

            # Live conflict indicator
            warn_lbl = ctk.CTkLabel(item_box, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER, anchor="w")
            warn_lbl.pack(fill="x", padx=10, pady=(0, 4))

            def _check_shelf(*_, exp_e=exp_ent, loc_c=loc_combo, w_lbl=warn_lbl, mid=it.medicine_id):
                exp_val = exp_e.get().strip()
                loc_txt = loc_c.get()
                l_id = loc_map.get(loc_txt)
                if exp_val and l_id:
                    ok, msg = self.shelf_service.validate_shelf_allocation(
                        self.user.store_id, mid, l_id, exp_val
                    )
                    if not ok:
                        _, sug, _ = self.shelf_service.suggest_shelf_location(self.user.store_id, mid, exp_val)
                        w_lbl.configure(text=f"⚠️ {msg} Suggested: '{sug}'", text_color=Theme.DANGER)
                    else:
                        w_lbl.configure(text="✅ Shelf allocation rule satisfied.", text_color=Theme.SUCCESS)

            exp_ent.bind("<KeyRelease>", _check_shelf)
            loc_combo.configure(command=lambda _: _check_shelf())

            receipt_rows.append({
                "item_id": it.item_id,
                "medicine_id": it.medicine_id,
                "batch_ent": b_ent,
                "exp_ent": exp_ent,
                "loc_combo": loc_combo,
                "qty_ent": q_ent,
                "unit_cost": it.unit_cost,
                "warn_lbl": warn_lbl
            })

        err_label = ctk.CTkLabel(form, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER)
        err_label.pack(padx=20, pady=2)

        def _post_receipt():
            receiving_data = []
            for rr in receipt_rows:
                b_num = rr["batch_ent"].get().strip().upper()
                e_date = rr["exp_ent"].get().strip()
                l_text = rr["loc_combo"].get()
                l_id = loc_map.get(l_text)

                try:
                    q_val = int(rr["qty_ent"].get().strip())
                except ValueError:
                    err_label.configure(text="Quantity received must be a valid integer.")
                    return

                if not b_num:
                    err_label.configure(text="Batch number is required for all receiving items.")
                    return
                if not e_date:
                    err_label.configure(text="Expiry date is required for all receiving items.")
                    return
                if not l_id:
                    err_label.configure(text="Valid shelf location is required for all receiving items.")
                    return

                receiving_data.append({
                    "item_id": rr["item_id"],
                    "medicine_id": rr["medicine_id"],
                    "batch_number": b_num,
                    "expiry_date": e_date,
                    "quantity": q_val,
                    "unit_cost": rr["unit_cost"],
                    "selling_price": 0.0,
                    "location_id": l_id
                })

            try:
                res = self.purchase_service.receive_purchase(
                    purchase_id=purchase.purchase_id,
                    receiving_batches=receiving_data,
                    store_id=self.user.store_id,
                    acting_user=self.user
                )
                modal.destroy()
                self.refresh_table()
                messagebox.showinfo(
                    "Goods Received",
                    f"Successfully received {res['batches_recorded']} batch(es) for Invoice #{purchase.invoice_number}.\n"
                    "Inventory batches and stock movement ledger updated atomically."
                )
            except Exception as ex:
                err_label.configure(text=str(ex))

        ctk.CTkButton(
            form,
            text="Confirm & Post Goods Receipt",
            font=Theme.FONT_SUBHEADING,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=_post_receipt
        ).pack(fill="x", padx=20, pady=12)


    def _open_po_invoice_modal(self, purchase_id: int) -> None:
        """Loads complete purchase with items and opens PO invoice modal."""
        try:
            purchase = self.purchase_service.get_purchase_by_id(
                purchase_id=purchase_id,
                store_id=self.user.store_id,
                acting_user=self.user
            )
            if not purchase:
                messagebox.showerror("Error", f"Purchase ID {purchase_id} not found.", parent=self)
                return
            self._active_po_modal = PurchaseOrderInvoiceModal(self, purchase)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load purchase details: {e}", parent=self)

    def _save_po_pdf(self, purchase_id: int) -> None:
        """Directly exports purchase order as PDF."""
        try:
            from utils.pdf_generator import generate_purchase_order_pdf
            purchase = self.purchase_service.get_purchase_by_id(
                purchase_id=purchase_id,
                store_id=self.user.store_id,
                acting_user=self.user
            )
            if not purchase:
                messagebox.showerror("Error", f"Purchase ID {purchase_id} not found.", parent=self)
                return

            p_dict = {
                "purchase_id": purchase.purchase_id,
                "invoice_number": purchase.invoice_number,
                "purchase_date": purchase.purchase_date,
                "supplier_name": purchase.supplier_name,
                "supplier_id": purchase.supplier_id,
                "store_id": purchase.store_id,
                "status": purchase.status,
                "payment_status": purchase.payment_status,
                "total_amount": purchase.total_amount,
                "notes": purchase.notes,
                "items": [
                    {
                        "medicine_name": getattr(it, "medicine_name", f"Medicine #{it.medicine_id}"),
                        "batch_number": getattr(it, "batch_number", "-"),
                        "quantity": it.quantity,
                        "purchase_price": it.purchase_price,
                        "subtotal": it.subtotal
                    }
                    for it in purchase.items
                ]
            }
            filepath = generate_purchase_order_pdf(p_dict)
            messagebox.showinfo("PO PDF Exported", f"Purchase Order PDF saved successfully:\n{filepath}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to save PO PDF: {e}", parent=self)
