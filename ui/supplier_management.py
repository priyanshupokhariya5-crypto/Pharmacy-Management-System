"""
Supplier Management View for Pharmacy Management System.
Allows Store Owners and Admins to catalog vendors, update contacts, search suppliers,
and activate/deactivate suppliers without breaking historical references.
"""
import re
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict, Any
import customtkinter as ctk

from ui.theme import Theme
from models.user import User
from models.supplier import Supplier
from services.supplier_service import SupplierService
from database.db import get_db
from utils.logger import get_app_logger


class SupplierManagementView(ctk.CTkFrame):
    """Supplier directory management screen with live search and add/edit modals."""

    def __init__(self, parent, user: User, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_DARK, **kwargs)
        self.user = user
        self.logger = get_app_logger()
        self.db = get_db()
        self.supplier_service = SupplierService(self.db)
        self.suppliers_cache: List[Supplier] = []
        self._active_modal: Optional[ctk.CTkToplevel] = None

        self._build_ui()
        self.refresh_table()

    def _build_ui(self) -> None:
        """Constructs header toolbar, search/filter bar, and supplier list."""
        # Top toolbar
        toolbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60, corner_radius=8)
        toolbar.pack(side="top", fill="x", padx=16, pady=(16, 10))
        toolbar.pack_propagate(False)

        ctk.CTkLabel(
            toolbar,
            text="🚚  Supplier & Vendor Management",
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_MAIN
        ).pack(side="left", padx=16, pady=12)

        # + Add Supplier Button
        if self.user.canonical_role in ("Owner", "Admin"):
            ctk.CTkButton(
                toolbar,
                text="➕  Add New Supplier",
                font=Theme.FONT_SUBHEADING,
                fg_color=Theme.PRIMARY,
                hover_color=Theme.PRIMARY_HOVER,
                text_color=Theme.TEXT_DARK,
                command=self._open_add_supplier_modal
            ).pack(side="right", padx=16, pady=12)

        # Search & Filter bar
        filter_bar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=50, corner_radius=8)
        filter_bar.pack(side="top", fill="x", padx=16, pady=(0, 10))
        filter_bar.pack_propagate(False)

        ctk.CTkLabel(filter_bar, text="🔍", font=Theme.FONT_BODY).pack(side="left", padx=(16, 6))

        self.search_var = tk.StringVar()
        self.search_entry = ctk.CTkEntry(
            filter_bar,
            placeholder_text="Search suppliers by name, code, contact person, or phone...",
            textvariable=self.search_var,
            width=380,
            height=32,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR
        )
        self.search_entry.pack(side="left", padx=(0, 12), pady=8)
        self.search_entry.bind("<KeyRelease>", lambda e: self._on_search())

        # Active status toggle
        self.filter_active_var = tk.StringVar(value="All")
        self.active_combo = ctk.CTkComboBox(
            filter_bar,
            values=["All", "Active Only", "Inactive Only"],
            variable=self.filter_active_var,
            width=140,
            height=32,
            font=Theme.FONT_BODY,
            command=lambda v: self._on_search()
        )
        self.active_combo.pack(side="left", padx=10, pady=8)

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

        # Supplier Cards / Table Scroll Area
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.pack(side="top", fill="both", expand=True, padx=16, pady=(0, 16))

    def refresh_table(self) -> None:
        """Fetches and displays all suppliers for the active store."""
        for w in self.scroll_frame.winfo_children():
            w.destroy()

        if not self.supplier_service._table_exists("suppliers"):
            card = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_CARD, corner_radius=8, height=120)
            card.pack(fill="x", pady=10)
            ctk.CTkLabel(
                card,
                text="⚠️ Supplier directory tables (suppliers) are not present in this database.\n"
                     "The original production database remains safely unmigrated per Stage 4 safety policy.",
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MUTED
            ).pack(expand=True, pady=30)
            return

        try:
            self.suppliers_cache = self.supplier_service.get_suppliers(
                self.user.store_id, acting_user=self.user
            )
            self._render_suppliers(self.suppliers_cache)
        except Exception as e:
            self.logger.log_event("SUPPLIERS", f"Failed to refresh suppliers: {e}", level="ERROR")

    def _on_search(self) -> None:
        """Filters cached suppliers based on search query and status."""
        query = self.search_var.get().strip().lower()
        filter_status = self.filter_active_var.get()

        filtered = []
        for s in self.suppliers_cache:
            if filter_status == "Active Only" and not s.is_active:
                continue
            if filter_status == "Inactive Only" and s.is_active:
                continue

            if query:
                match = (
                    query in (s.supplier_name or "").lower() or
                    query in (s.supplier_code or "").lower() or
                    query in (s.contact_person or "").lower() or
                    query in (s.phone or "").lower()
                )
                if not match:
                    continue

            filtered.append(s)

        self._render_suppliers(filtered)

    def _render_suppliers(self, suppliers: List[Supplier]) -> None:
        """Renders list of supplier cards."""
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not suppliers:
            empty_card = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_CARD, corner_radius=8, height=120)
            empty_card.pack(fill="x", pady=10)
            ctk.CTkLabel(
                empty_card,
                text="No suppliers found matching the criteria. Click 'Add New Supplier' to catalog vendors.",
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MUTED
            ).pack(expand=True, pady=30)
            return

        for s in suppliers:
            card = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_CARD, corner_radius=8)
            card.pack(fill="x", pady=5, padx=2)

            header_row = ctk.CTkFrame(card, fg_color="transparent")
            header_row.pack(fill="x", padx=16, pady=(12, 6))

            ctk.CTkLabel(
                header_row,
                text=f"🏢 {s.supplier_name}",
                font=Theme.FONT_SUBHEADING,
                text_color=Theme.TEXT_MAIN
            ).pack(side="left")

            # Status Badge
            badge_color = Theme.SUCCESS if s.is_active else Theme.DANGER
            badge_text = "ACTIVE" if s.is_active else "INACTIVE"
            ctk.CTkLabel(
                header_row,
                text=f"  {badge_text}  ",
                font=Theme.FONT_SMALL,
                fg_color=badge_color,
                text_color=Theme.TEXT_DARK,
                corner_radius=4
            ).pack(side="left", padx=12)

            # Code tag
            ctk.CTkLabel(
                header_row,
                text=f"Code: {s.supplier_code}",
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_MUTED
            ).pack(side="left", padx=6)

            # Action buttons
            if self.user.canonical_role in ("Owner", "Admin"):
                action_row = ctk.CTkFrame(header_row, fg_color="transparent")
                action_row.pack(side="right")

                toggle_txt = "Deactivate" if s.is_active else "Activate"
                toggle_color = Theme.DANGER if s.is_active else Theme.SUCCESS
                ctk.CTkButton(
                    action_row,
                    text=toggle_txt,
                    width=80,
                    height=26,
                    font=Theme.FONT_SMALL,
                    fg_color="transparent",
                    text_color=toggle_color,
                    hover_color=Theme.INPUT_BG,
                    command=lambda sid=s.supplier_id, act=s.is_active: self._toggle_supplier(sid, act)
                ).pack(side="right", padx=4)

                ctk.CTkButton(
                    action_row,
                    text="✏️ Edit",
                    width=65,
                    height=26,
                    font=Theme.FONT_SMALL,
                    fg_color=Theme.INPUT_BG,
                    text_color=Theme.TEXT_MAIN,
                    hover_color=Theme.BORDER_COLOR,
                    command=lambda sup=s: self._open_edit_supplier_modal(sup)
                ).pack(side="right", padx=4)

            # Details row
            details_row = ctk.CTkFrame(card, fg_color="transparent")
            details_row.pack(fill="x", padx=16, pady=(0, 12))

            details = [
                f"👤 Contact: {s.contact_person or 'N/A'}",
                f"📞 Phone: {s.phone or 'N/A'}",
                f"✉️ Email: {s.email or 'N/A'}",
                f"GST: {s.gst_number or 'N/A'}"
            ]
            ctk.CTkLabel(
                details_row,
                text="   |   ".join(details),
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_MUTED,
                anchor="w"
            ).pack(side="left", fill="x")

    def _toggle_supplier(self, supplier_id: int, current_active: bool) -> None:
        """Toggles active status of a supplier with confirmation."""
        new_status = not current_active
        action_word = "deactivate" if current_active else "activate"
        if messagebox.askyesno(
            f"Confirm {action_word.capitalize()}",
            f"Are you sure you want to {action_word} this supplier? "
            "Historical purchase and inventory references will remain intact."
        ):
            try:
                self.supplier_service.set_supplier_active_status(
                    supplier_id=supplier_id,
                    is_active=new_status,
                    store_id=self.user.store_id,
                    acting_user=self.user
                )
                self.refresh_table()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to change status: {e}")

    def _open_add_supplier_modal(self) -> None:
        """Opens modal dialog to register a new supplier."""
        self._supplier_modal(is_edit=False)

    def _open_edit_supplier_modal(self, supplier: Supplier) -> None:
        """Opens modal dialog to edit existing supplier details."""
        self._supplier_modal(is_edit=True, supplier=supplier)

    def _supplier_modal(self, is_edit: bool = False, supplier: Optional[Supplier] = None) -> None:
        """Popup modal form for adding/editing a supplier with responsive layout and fixed action footer."""
        modal = ctk.CTkToplevel(self)
        self._active_modal = modal
        modal.title("Edit Supplier" if is_edit else "Add New Supplier")

        # Responsive dimensions & centering
        screen_w = modal.winfo_screenwidth()
        screen_h = modal.winfo_screenheight()
        modal_w = 520
        modal_h = min(620, max(480, int(screen_h * 0.82)))
        x = max(0, (screen_w - modal_w) // 2)
        y = max(0, (screen_h - modal_h) // 2)
        modal.geometry(f"{modal_w}x{modal_h}+{x}+{y}")
        modal.minsize(440, 420)
        modal.configure(fg_color=Theme.BG_DARK)
        modal.transient(self)
        modal.grab_set()

        # 1. Header Frame (Fixed at top)
        header_frame = ctk.CTkFrame(modal, fg_color=Theme.BG_CARD, corner_radius=10)
        header_frame.pack(side="top", fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            header_frame,
            text="✏️  Edit Supplier Details" if is_edit else "➕  Register New Supplier",
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_MAIN
        ).pack(anchor="w", padx=16, pady=(12, 2))

        ctk.CTkLabel(
            header_frame,
            text="Catalog authorized pharmaceutical vendors. Fields marked with * are required.",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", padx=16, pady=(0, 10))

        # 2. Fixed Footer Frame (Bottom - Never clipped by scrolling)
        footer_frame = ctk.CTkFrame(modal, fg_color=Theme.BG_CARD, height=60, corner_radius=10)
        footer_frame.pack(side="bottom", fill="x", padx=16, pady=(0, 16))

        cancel_btn = ctk.CTkButton(
            footer_frame,
            text="Cancel",
            font=Theme.FONT_SUBHEADING,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            height=38,
            width=120,
            command=modal.destroy
        )
        cancel_btn.pack(side="left", padx=16, pady=11)

        save_btn = ctk.CTkButton(
            footer_frame,
            text="Update Supplier" if is_edit else "Save Supplier",
            font=Theme.FONT_SUBHEADING,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            height=38,
            width=160,
            command=lambda: _save()
        )
        save_btn.pack(side="right", padx=16, pady=11)

        # 3. Vertically Scrollable Form Frame (Middle)
        scroll_form = ctk.CTkScrollableFrame(modal, fg_color=Theme.BG_CARD, corner_radius=10)
        scroll_form.pack(side="top", fill="both", expand=True, padx=16, pady=(0, 8))

        # Error Banner
        err_label = ctk.CTkLabel(scroll_form, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER, wraplength=440)
        err_label.pack(fill="x", padx=16, pady=(6, 2))

        def _make_field(parent, label: str, default: str = "") -> ctk.CTkEntry:
            ctk.CTkLabel(parent, text=label, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=16, pady=(6, 2))
            ent = ctk.CTkEntry(parent, height=32, font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
            ent.pack(fill="x", padx=16, pady=(0, 4))
            if default:
                ent.insert(0, str(default))
            return ent

        code_ent = _make_field(scroll_form, "Supplier Code * (e.g. SUP-001)", supplier.supplier_code if supplier else "")
        name_ent = _make_field(scroll_form, "Supplier / Company Name *", supplier.supplier_name if supplier else "")
        contact_ent = _make_field(scroll_form, "Contact Person", supplier.contact_person if supplier and supplier.contact_person else "")

        # Phone input with real-time numeric constraint, 10-digit limit, and paste truncation
        ctk.CTkLabel(scroll_form, text="Phone Number (10 digits when provided)", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=16, pady=(6, 2))
        phone_var = tk.StringVar(value=supplier.phone if supplier and supplier.phone else "")
        phone_ent = ctk.CTkEntry(scroll_form, textvariable=phone_var, height=32, font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        phone_ent.pack(fill="x", padx=16, pady=(0, 2))

        phone_feedback_lbl = ctk.CTkLabel(scroll_form, text="", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED, anchor="w")
        phone_feedback_lbl.pack(fill="x", padx=16, pady=(0, 4))

        def _sanitize_phone(*args):
            raw = phone_var.get()
            digits = re.sub(r"\D", "", raw)
            if len(raw) > len(digits):
                phone_feedback_lbl.configure(text="⚠️ Only numeric digits (0-9) are allowed.", text_color=Theme.WARNING)
            elif len(digits) > 10:
                digits = digits[:10]
                phone_feedback_lbl.configure(text="⚠️ Phone number truncated to 10 digits.", text_color=Theme.WARNING)
            elif 0 < len(digits) < 10:
                phone_feedback_lbl.configure(text=f"ℹ️ {10 - len(digits)} more digit(s) required.", text_color=Theme.TEXT_MUTED)
            elif len(digits) == 10:
                phone_feedback_lbl.configure(text="✓ Valid 10-digit mobile number.", text_color=Theme.SUCCESS)
            else:
                phone_feedback_lbl.configure(text="", text_color=Theme.TEXT_MUTED)

            if raw != digits:
                phone_var.set(digits)

        phone_var.trace_add("write", _sanitize_phone)
        for evt in ("<KeyRelease>", "<<Paste>>", "<FocusOut>"):
            phone_ent.bind(evt, lambda e: _sanitize_phone())

        email_ent = _make_field(scroll_form, "Email Address", supplier.email if supplier and supplier.email else "")
        address_ent = _make_field(scroll_form, "Address", supplier.address if supplier and supplier.address else "")
        gst_ent = _make_field(scroll_form, "GST Number", supplier.gst_number if supplier and supplier.gst_number else "")

        # Store references on modal for introspection
        modal.code_ent = code_ent
        modal.name_ent = name_ent
        modal.contact_ent = contact_ent
        modal.phone_ent = phone_ent
        modal.phone_var = phone_var
        modal.phone_feedback_lbl = phone_feedback_lbl
        modal.email_ent = email_ent
        modal.address_ent = address_ent
        modal.gst_ent = gst_ent
        modal.err_label = err_label
        modal.cancel_btn = cancel_btn
        modal.save_btn = save_btn

        def _save():
            code = code_ent.get().strip()
            name = name_ent.get().strip()
            contact = contact_ent.get().strip()
            phone = phone_var.get().strip()
            email = email_ent.get().strip()
            address = address_ent.get().strip()
            gst = gst_ent.get().strip()

            if not code:
                err_label.configure(text="Supplier code is required.")
                code_ent.focus()
                return
            if not name:
                err_label.configure(text="Supplier name is required.")
                name_ent.focus()
                return
            if phone and len(phone) != 10:
                err_label.configure(text="Phone number must contain exactly 10 digits when provided.")
                phone_ent.focus()
                return

            try:
                if is_edit and supplier:
                    supplier.supplier_code = code
                    supplier.supplier_name = name
                    supplier.contact_person = contact or None
                    supplier.phone = phone or None
                    supplier.email = email or None
                    supplier.address = address or None
                    supplier.gst_number = gst or None
                    self.supplier_service.update_supplier(supplier, acting_user=self.user)
                else:
                    self.supplier_service.create_supplier(
                        store_id=self.user.store_id,
                        supplier_code=code,
                        supplier_name=name,
                        contact_person=contact or None,
                        phone=phone or None,
                        email=email or None,
                        address=address or None,
                        gst_number=gst or None,
                        acting_user=self.user
                    )
                modal.destroy()
                self._active_modal = None
                self.refresh_table()
            except Exception as ex:
                err_label.configure(text=str(ex))
