"""
Batch-wise Medicine Inventory, Shelf Allocation, and FEFO Engine View.
Features:
  1. Complete Batch Directory with Expiry Badges and Physical Shelf Locations.
  2. Interactive FEFO Allocation Preview Engine Simulator.
  3. Real-Time Expiry and Low-Stock Warning Panels.
  4. Immutable Stock Movement Ledger Audit Inspection.
  5. Physical Batch Relocation with Critical Shelf Allocation Rule Enforcement.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict, Any
from datetime import datetime
import customtkinter as ctk

from ui.theme import Theme
from models.user import User
from models.batch import InventoryBatch
from services.inventory_service import InventoryService, FefoAllocationResult
from services.shelf_service import ShelfService
from services.medicine_service import MedicineService
from database.db import get_db
from utils.logger import get_app_logger


class BatchInventoryView(ctk.CTkFrame):
    """Batch-wise inventory management, FEFO simulation, and shelf location screen."""

    def __init__(self, parent, user: User, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_DARK, **kwargs)
        self.user = user
        self.logger = get_app_logger()
        self.db = get_db()
        self.inventory_service = InventoryService(self.db)
        self.shelf_service = ShelfService(self.db)
        self.medicine_service = MedicineService(self.db)

        self._build_ui()
        self._load_active_tab()

    def _build_ui(self) -> None:
        """Constructs header toolbar, navigation tabs, and content area."""
        toolbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=60, corner_radius=8)
        toolbar.pack(side="top", fill="x", padx=16, pady=(16, 10))
        toolbar.pack_propagate(False)

        ctk.CTkLabel(
            toolbar,
            text="🏷️  Batch Inventory & FEFO Allocation",
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_MAIN
        ).pack(side="left", padx=16, pady=12)

        ctk.CTkButton(
            toolbar,
            text="🔄 Refresh",
            width=90,
            height=32,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self._load_active_tab
        ).pack(side="right", padx=16, pady=12)

        # Tab Segmented Button
        self.tab_var = tk.StringVar(value="Batch Directory")
        self.tab_selector = ctk.CTkSegmentedButton(
            self,
            values=["Batch Directory", "FEFO Simulator", "Expiry & Stock Alerts", "Stock Movements"],
            variable=self.tab_var,
            font=Theme.FONT_SUBHEADING,
            selected_color=Theme.PRIMARY,
            selected_hover_color=Theme.PRIMARY_HOVER,
            command=lambda v: self._on_tab_change(v)
        )
        self.tab_selector.pack(side="top", fill="x", padx=16, pady=(0, 8))

        # Help & Information Banner
        info_bar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=36, corner_radius=6, border_width=1, border_color=Theme.BORDER_COLOR)
        info_bar.pack(side="top", fill="x", padx=16, pady=(0, 8))
        info_bar.pack_propagate(False)

        ctk.CTkLabel(
            info_bar,
            text="ℹ️ Storage Rules: Differing expiries must occupy separate shelves | Cold chain on SHELF-COLD | Expired stock on SHELF-QUAR | Automatic FEFO allocation upon sale",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(side="left", padx=12, pady=6)

        # Main scrollable content
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.pack(side="top", fill="both", expand=True, padx=16, pady=(0, 16))

    def _on_tab_change(self, tab_name: str) -> None:
        """Switches content according to selected tab."""
        self._load_active_tab()

    def _table_exists(self, table_name: str) -> bool:
        """Helper checking if a table exists in the database."""
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def _load_active_tab(self) -> None:
        """Loads data into active tab."""
        for w in self.content_container.winfo_children():
            w.destroy()

        if not self._table_exists("inventory_batches"):
            card = ctk.CTkFrame(self.content_container, fg_color=Theme.BG_CARD, corner_radius=8, height=140)
            card.pack(fill="x", pady=10)
            ctk.CTkLabel(
                card,
                text="⚠️ Batch-wise inventory tables (inventory_batches) are not present in this database.\n"
                     "The original production database remains safely unmigrated per Stage 4 safety policy.\n"
                     "Batch tracking, FEFO preview, and shelf allocation will activate once Stage 2 migration is approved.",
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MUTED
            ).pack(expand=True, pady=30)
            return

        tab = self.tab_var.get()
        if tab == "Batch Directory":
            self._render_batch_directory()
        elif tab == "FEFO Simulator":
            self._render_fefo_simulator()
        elif tab == "Expiry & Stock Alerts":
            self._render_alerts_panel()
        elif tab == "Stock Movements":
            self._render_movements_ledger()

    # -----------------------------------------------------------------------
    # Tab 1: Batch Directory
    # -----------------------------------------------------------------------

    def _render_batch_directory(self) -> None:
        """Renders directory of all batches for current store."""
        scroll = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        batches = self.inventory_service.get_all_batches(self.user.store_id, acting_user=self.user, limit=150)
        if not batches:
            card = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=8, height=100)
            card.pack(fill="x", pady=10)
            ctk.CTkLabel(card, text="No batch records found in inventory.", font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(expand=True, pady=30)
            return

        for b in batches:
            b = dict(b)
            card = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=8)
            card.pack(fill="x", pady=4, padx=2)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=14, pady=(10, 4))

            ctk.CTkLabel(
                top,
                text=f"💊 {b['medicine_name']}",
                font=Theme.FONT_SUBHEADING,
                text_color=Theme.TEXT_MAIN
            ).pack(side="left")

            ctk.CTkLabel(
                top,
                text=f"Batch: {b['batch_number']}",
                font=Theme.FONT_BOLD,
                text_color=Theme.PRIMARY
            ).pack(side="left", padx=12)

            # Badge
            st = b["status"]
            if st == "Active":
                b_color = Theme.SUCCESS
            elif st == "Expired":
                b_color = Theme.DANGER
            else:
                b_color = Theme.WARNING

            ctk.CTkLabel(
                top,
                text=f" {st} ",
                font=Theme.FONT_SMALL,
                fg_color=b_color,
                text_color=Theme.TEXT_DARK,
                corner_radius=4
            ).pack(side="left", padx=6)

            ctk.CTkLabel(
                top,
                text=f"Stock: {b['current_quantity']} / {b['initial_quantity']} units",
                font=Theme.FONT_BOLD,
                text_color=Theme.TEXT_MAIN
            ).pack(side="right")

            # Bottom details row
            bot = ctk.CTkFrame(card, fg_color="transparent")
            bot.pack(fill="x", padx=14, pady=(0, 10))

            shelf_text = f"📍 Shelf: {dict(b).get('shelf_code') or 'Unassigned'}"
            exp_text = f"⏳ Expiry: {b['expiry_date']}"
            price_text = f"💰 MRP: ₹{b['selling_price']:,.2f}"

            ctk.CTkLabel(
                bot,
                text=f"{shelf_text}   |   {exp_text}   |   {price_text}",
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_MUTED
            ).pack(side="left")

            # Actions (Relocate, Adjust)
            if self.user.canonical_role in ("Owner", "Admin", "Inventory Manager"):
                act_frame = ctk.CTkFrame(bot, fg_color="transparent")
                act_frame.pack(side="right")

                ctk.CTkButton(
                    act_frame,
                    text="📦 Relocate",
                    width=75,
                    height=24,
                    font=Theme.FONT_SMALL,
                    fg_color=Theme.INPUT_BG,
                    text_color=Theme.TEXT_MAIN,
                    hover_color=Theme.BORDER_COLOR,
                    command=lambda bid=b["batch_id"]: self._open_relocate_modal(bid)
                ).pack(side="left", padx=2)

                ctk.CTkButton(
                    act_frame,
                    text="⚖️ Adjust",
                    width=65,
                    height=24,
                    font=Theme.FONT_SMALL,
                    fg_color=Theme.INPUT_BG,
                    text_color=Theme.TEXT_MAIN,
                    hover_color=Theme.BORDER_COLOR,
                    command=lambda bid=b["batch_id"]: self._open_adjust_modal(bid)
                ).pack(side="left", padx=2)

    # -----------------------------------------------------------------------
    # Tab 2: FEFO Simulator & Allocation Preview
    # -----------------------------------------------------------------------

    def _render_fefo_simulator(self) -> None:
        """Renders interactive FEFO selection preview tester with live batch priorities table."""
        medicines = self.medicine_service.get_medicines_by_store(self.user.store_id)
        if not medicines:
            ctk.CTkLabel(self.content_container, text="No medicines found in catalog.", font=Theme.FONT_BODY).pack(pady=30)
            return

        med_map = {f"{m.medicine_name} ({m.medicine_code})": m for m in medicines}

        # 1. Interactive Simulation Controls Card
        card = ctk.CTkFrame(self.content_container, fg_color=Theme.BG_CARD, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
        card.pack(fill="x", pady=(4, 8))

        top_hdr = ctk.CTkFrame(card, fg_color="transparent")
        top_hdr.pack(fill="x", padx=16, pady=(12, 4))

        ctk.CTkLabel(
            top_hdr,
            text="⚡  FEFO (First Expiry, First Out) Allocation Simulator",
            font=Theme.FONT_HEADING,
            text_color=Theme.PRIMARY
        ).pack(side="left")

        ctk.CTkLabel(
            card,
            text=(
                "Simulates how the billing engine greedily allocates requested stock across eligible batches based on earliest expiry date. "
                "Preview is read-only and strictly excludes expired, quarantined, recalled, or unverified stock."
            ),
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", padx=16, pady=(0, 10))

        input_row = ctk.CTkFrame(card, fg_color="transparent")
        input_row.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(input_row, text="Select Medicine:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(side="left", padx=(0, 6))
        med_combo = ctk.CTkComboBox(input_row, values=list(med_map.keys()), width=290, height=32, font=Theme.FONT_BODY)
        med_combo.pack(side="left", padx=(0, 16))

        ctk.CTkLabel(input_row, text="Required Qty:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(side="left", padx=(0, 6))
        qty_entry = ctk.CTkEntry(input_row, width=80, height=32, font=Theme.FONT_BODY)
        qty_entry.pack(side="left", padx=(0, 16))
        qty_entry.insert(0, "15")

        # 2. Results Container for Simulation
        res_frame = ctk.CTkFrame(card, fg_color=Theme.BG_DARK, corner_radius=8, border_width=1, border_color=Theme.BORDER_COLOR)
        res_frame.pack(fill="x", padx=16, pady=(0, 12))

        def _run_preview():
            for w in res_frame.winfo_children():
                w.destroy()

            m_val = med_combo.get()
            med = med_map.get(m_val)
            if not med:
                return

            try:
                qty_val = int(qty_entry.get().strip())
                if qty_val <= 0:
                    messagebox.showwarning("Invalid Quantity", "Quantity must be greater than zero.", parent=self)
                    return
            except ValueError:
                messagebox.showerror("Invalid Input", "Quantity must be an integer.", parent=self)
                return

            res: FefoAllocationResult = self.inventory_service.preview_fefo_allocation(
                store_id=self.user.store_id,
                medicine_id=med.medicine_id,
                requested_quantity=qty_val,
                acting_user=self.user
            )

            hdr = ctk.CTkFrame(res_frame, fg_color="transparent")
            hdr.pack(fill="x", padx=14, pady=10)

            icon = "✅" if res.success else "⚠️"
            status_color = Theme.SUCCESS if res.success else Theme.WARNING
            ctk.CTkLabel(
                hdr,
                text=f"{icon} {res.message}",
                font=Theme.FONT_SUBHEADING,
                text_color=status_color
            ).pack(side="left")

            total_val = sum(getattr(a, "subtotal", 0.0) for a in res.allocations) if res.allocations else 0.0
            alloc_summary = f"Allocated: {res.allocated_quantity} / {res.requested_quantity} units | Value: ₹{total_val:,.2f}"
            ctk.CTkLabel(
                hdr,
                text=alloc_summary,
                font=Theme.FONT_BOLD,
                text_color=Theme.PRIMARY if res.success else Theme.DANGER
            ).pack(side="right")

            # Sequence Breakdown
            if res.allocations:
                seq_box = ctk.CTkFrame(res_frame, fg_color="transparent")
                seq_box.pack(fill="x", padx=14, pady=(0, 10))

                for idx, alloc in enumerate(res.allocations, start=1):
                    item_frame = ctk.CTkFrame(seq_box, fg_color=Theme.BG_CARD, corner_radius=6)
                    item_frame.pack(fill="x", pady=2)

                    row_c = ctk.CTkFrame(item_frame, fg_color="transparent")
                    row_c.pack(fill="x", padx=12, pady=6)

                    ctk.CTkLabel(
                        row_c,
                        text=f"Priority #{idx}: Batch {alloc.batch_number}",
                        font=Theme.FONT_BOLD,
                        text_color=Theme.TEXT_MAIN
                    ).pack(side="left")

                    ctk.CTkLabel(
                        row_c,
                        text=f"📍 Shelf: {alloc.shelf_code or 'SHELF-A01'}   |   ⏳ Expiry: {alloc.expiry_date}   |   Available: {alloc.available_quantity}",
                        font=Theme.FONT_SMALL,
                        text_color=Theme.TEXT_MUTED
                    ).pack(side="left", padx=16)

                    ctk.CTkLabel(
                        row_c,
                        text=f"Deducted: {alloc.allocated_quantity} units (₹{alloc.subtotal:,.2f})",
                        font=Theme.FONT_BOLD,
                        text_color=Theme.PRIMARY
                    ).pack(side="right")
            elif not res.success:
                ctk.CTkLabel(
                    res_frame,
                    text="❌ Insufficient active, verified, non-expired stock to fulfill requested quantity.",
                    font=Theme.FONT_BODY,
                    text_color=Theme.DANGER
                ).pack(anchor="w", padx=14, pady=(0, 10))

        ctk.CTkButton(
            input_row,
            text="⚡ Simulate FEFO",
            font=Theme.FONT_BOLD,
            height=32,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=_run_preview
        ).pack(side="left")

        med_combo.configure(command=lambda v: _run_preview())

        # 3. Live Batch Inventory Table with FEFO Priority & Allocation Status
        table_card = ctk.CTkFrame(self.content_container, fg_color=Theme.BG_CARD, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
        table_card.pack(fill="both", expand=True, pady=(0, 6))

        tbl_hdr = ctk.CTkFrame(table_card, fg_color="transparent")
        tbl_hdr.pack(fill="x", padx=16, pady=(10, 4))

        ctk.CTkLabel(
            tbl_hdr,
            text="📋 Real Inventory Batch Data & Live FEFO Allocation Priorities",
            font=Theme.FONT_HEADING,
            text_color=Theme.TEXT_MAIN
        ).pack(side="left")

        # Treeview styling
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Fefo.Treeview",
            background=Theme.BG_CARD,
            foreground=Theme.TEXT_MAIN,
            fieldbackground=Theme.BG_CARD,
            rowheight=26,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Fefo.Treeview.Heading",
            background=Theme.DEEP_NAVY,
            foreground=Theme.TEXT_DARK,
            font=("Segoe UI", 9, "bold")
        )

        fefo_cols = ("med_name", "med_code", "batch", "expiry", "shelf", "qty", "status", "priority", "eligibility")
        tree_frame = ctk.CTkFrame(table_card, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        tree = ttk.Treeview(tree_frame, columns=fefo_cols, show="headings", style="Fefo.Treeview", selectmode="browse")
        headers = [
            ("med_name", "Medicine Name", 160),
            ("med_code", "Code", 75),
            ("batch", "Batch Number", 90),
            ("expiry", "Expiry Date", 90),
            ("shelf", "Shelf / Rack", 85),
            ("qty", "Available Qty", 85),
            ("status", "Batch Status", 85),
            ("priority", "FEFO Priority", 110),
            ("eligibility", "Allocation Status", 130)
        ]
        for cid, title, w in headers:
            tree.heading(cid, text=title)
            tree.column(cid, width=w, anchor="center" if cid not in ("med_name",) else "w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # Populate Batch Table
        batches = self.inventory_service.get_all_batches(self.user.store_id, acting_user=self.user) if hasattr(self.inventory_service, "get_all_batches") else self.inventory_service.get_batches(self.user.store_id, acting_user=self.user)
        # Group by medicine_id to calculate real FEFO priorities
        med_batches = {}
        for b in batches:
            mid = b.get("medicine_id")
            if mid not in med_batches:
                med_batches[mid] = []
            med_batches[mid].append(b)

        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")

        for mid, b_list in med_batches.items():
            # Sort by expiry ASC
            sorted_b = sorted(b_list, key=lambda x: x.get("expiry_date", "9999-99-99"))
            active_rank = 1
            for b in sorted_b:
                st = b.get("status", "Active")
                exp = b.get("expiry_date", "")
                v_flag = b.get("verification_flag", 0)
                cur_qty = b.get("current_quantity", 0)

                is_exp = exp < today_str
                if st == "Active" and not is_exp and v_flag == 0 and cur_qty > 0:
                    prio_text = f"Priority #{active_rank}"
                    elig_text = "✅ Eligible for Sale"
                    active_rank += 1
                elif is_exp:
                    prio_text = "Excluded"
                    elig_text = "❌ Expired Stock"
                elif st == "Quarantined":
                    prio_text = "Excluded"
                    elig_text = "⚠️ Quarantined"
                elif st == "Recalled":
                    prio_text = "Excluded"
                    elig_text = "⛔ Recalled Stock"
                elif v_flag == 1:
                    prio_text = "Excluded"
                    elig_text = "🔒 Unverified Stock"
                elif cur_qty <= 0:
                    prio_text = "Depleted"
                    elig_text = "⚪ Zero Stock"
                else:
                    prio_text = "Inactive"
                    elig_text = "Inactive Batch"

                tree.insert(
                    "",
                    "end",
                    values=(
                        b.get("medicine_name", "-"),
                        b.get("medicine_code", "-"),
                        b.get("batch_number", "-"),
                        exp,
                        b.get("shelf_code") or "SHELF-A01",
                        cur_qty,
                        st,
                        prio_text,
                        elig_text
                    )
                )

        # Trigger initial simulation so data is visible immediately on load
        _run_preview()


    # -----------------------------------------------------------------------
    # Tab 3: Expiry & Stock Alerts
    # -----------------------------------------------------------------------

    def _render_alerts_panel(self) -> None:
        """Renders near-expiry batches (<30 days), expired stock, and low-stock alerts."""
        scroll = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        expired = self.inventory_service.get_expired_batches(self.user.store_id, acting_user=self.user)
        near_exp = self.inventory_service.get_near_expiry_batches(self.user.store_id, days=30, acting_user=self.user)
        low_stock = self.inventory_service.get_low_stock_medicines(self.user.store_id, threshold=10, acting_user=self.user)

        # 1. Expired Stock Alert Card
        if expired:
            ctk.CTkLabel(scroll, text=f"🚨 Expired Batches ({len(expired)}) — Blocked From Dispensing", font=Theme.FONT_SUBHEADING, text_color=Theme.DANGER).pack(anchor="w", pady=(8, 4))
            for b in expired:
                c = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=8)
                c.pack(fill="x", pady=2)
                r = ctk.CTkFrame(c, fg_color="transparent")
                r.pack(fill="x", padx=14, pady=8)
                ctk.CTkLabel(r, text=f"💊 {b['medicine_name']} (Batch {b['batch_number']})", font=Theme.FONT_BODY, text_color=Theme.DANGER).pack(side="left")
                ctk.CTkLabel(r, text=f"Expired on: {b['expiry_date']}  |  Stock: {b['current_quantity']} units", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(side="left", padx=16)

                if self.user.canonical_role in ("Owner", "Admin", "Inventory Manager") and b["current_quantity"] > 0:
                    ctk.CTkButton(
                        r, text="Write Off", width=80, height=24, font=Theme.FONT_SMALL,
                        fg_color=Theme.DANGER, text_color=Theme.TEXT_DARK,
                        command=lambda bid=b["batch_id"]: self._write_off_batch(bid)
                    ).pack(side="right")

        # 2. Near Expiry Stock Card
        ctk.CTkLabel(scroll, text=f"⚠️ Batches Expiring Within 30 Days ({len(near_exp)})", font=Theme.FONT_SUBHEADING, text_color=Theme.WARNING).pack(anchor="w", pady=(14, 4))
        if near_exp:
            for b in near_exp:
                c = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=8)
                c.pack(fill="x", pady=2)
                r = ctk.CTkFrame(c, fg_color="transparent")
                r.pack(fill="x", padx=14, pady=8)
                ctk.CTkLabel(r, text=f"💊 {b['medicine_name']} (Batch {b['batch_number']})", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).pack(side="left")
                days_left = b.get("days_remaining", 0)
                ctk.CTkLabel(r, text=f"Expires in {days_left} day(s) ({b['expiry_date']})  |  Available: {b['current_quantity']} units", font=Theme.FONT_SMALL, text_color=Theme.WARNING).pack(side="left", padx=16)
        else:
            c = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=8)
            c.pack(fill="x", pady=2)
            ctk.CTkLabel(c, text="No active batches expiring within the next 30 days.", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(pady=10)

        # 3. Low Stock Medicines Card
        ctk.CTkLabel(scroll, text=f"📉 Critical Low-Stock Medicines <=10 Units ({len(low_stock)})", font=Theme.FONT_SUBHEADING, text_color=Theme.PRIMARY).pack(anchor="w", pady=(14, 4))
        if low_stock:
            for m in low_stock:
                c = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=8)
                c.pack(fill="x", pady=2)
                r = ctk.CTkFrame(c, fg_color="transparent")
                r.pack(fill="x", padx=14, pady=8)
                ctk.CTkLabel(r, text=f"💊 {m['medicine_name']} ({m['medicine_code']})", font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN).pack(side="left")
                ctk.CTkLabel(r, text=f"Category: {m['category']}  |  Total Physical Stock: {m['total_stock']} units", font=Theme.FONT_SMALL, text_color=Theme.DANGER if m['total_stock'] == 0 else Theme.WARNING).pack(side="left", padx=16)

    # -----------------------------------------------------------------------
    # Tab 4: Stock Movement Ledger
    # -----------------------------------------------------------------------

    def _render_movements_ledger(self) -> None:
        """Renders immutable stock movements ledger entries."""
        scroll = ctk.CTkScrollableFrame(self.content_container, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        query = """
        SELECT sm.*, m.medicine_name, b.batch_number, u.username
        FROM stock_movements sm
        JOIN medicines m ON sm.medicine_id = m.medicine_id
        LEFT JOIN inventory_batches b ON sm.batch_id = b.batch_id
        LEFT JOIN users u ON sm.created_by = u.user_id
        WHERE sm.store_id = ?
        ORDER BY sm.created_at DESC, sm.movement_id DESC
        LIMIT 100
        """
        movements = self.db.fetch_all(query, (self.user.store_id,))
        if not movements:
            ctk.CTkLabel(scroll, text="No stock movements logged yet.", font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(pady=30)
            return

        for sm in movements:
            sm = dict(sm)
            c = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=8)
            c.pack(fill="x", pady=3)

            r = ctk.CTkFrame(c, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=8)

            delta = sm["quantity_delta"]
            delta_color = Theme.SUCCESS if delta > 0 else Theme.DANGER
            delta_sign = f"+{delta}" if delta > 0 else str(delta)

            ctk.CTkLabel(
                r,
                text=f"  {delta_sign} units  ",
                font=Theme.FONT_BOLD,
                fg_color=delta_color,
                text_color=Theme.TEXT_DARK,
                corner_radius=4
            ).pack(side="left")

            ctk.CTkLabel(
                r,
                text=f"💊 {sm['medicine_name']} (Batch {sm['batch_number'] or 'N/A'})",
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MAIN
            ).pack(side="left", padx=12)

            ctk.CTkLabel(
                r,
                text=f"Type: {sm['movement_type']}   |   Ref: {sm.get('reference_type') or ''} #{sm.get('reference_id') or ''}",
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_MUTED
            ).pack(side="left", padx=8)

            ctk.CTkLabel(
                r,
                text=f"🕒 {sm['created_at']} by {sm.get('username') or 'System'}",
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_MUTED
            ).pack(side="right")

    # -----------------------------------------------------------------------
    # Batch Actions: Relocate & Adjust Modals
    # -----------------------------------------------------------------------

    def _open_relocate_modal(self, batch_id: int) -> None:
        """Modal to change shelf assignment with live Critical Shelf Allocation Rule validation."""
        batch = self.inventory_service.get_batch_by_id(batch_id, store_id=self.user.store_id, acting_user=self.user)
        if not batch:
            return

        locations = self.shelf_service.get_storage_locations(self.user.store_id, is_active=True)
        loc_map = {f"{l['shelf_code']} ({dict(l).get('rack') or 'General'})": l['location_id'] for l in locations}

        modal = ctk.CTkToplevel(self)
        modal.title(f"Relocate Batch {batch.batch_number}")
        modal.geometry("450x320")
        modal.transient(self)
        modal.grab_set()

        form = ctk.CTkFrame(modal, fg_color=Theme.BG_CARD, corner_radius=8)
        form.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(form, text=f"📦 Relocate Batch: {batch.batch_number}", font=Theme.FONT_HEADING, text_color=Theme.TEXT_MAIN).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(form, text=f"Current Shelf: {batch.shelf_code or 'Unassigned'} | Expiry: {batch.expiry_date}", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=16, pady=(0, 10))

        ctk.CTkLabel(form, text="Select Target Shelf Location *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=16, pady=(6, 2))
        combo = ctk.CTkComboBox(form, values=list(loc_map.keys()), width=380, height=32, font=Theme.FONT_BODY)
        combo.pack(fill="x", padx=16, pady=(0, 8))

        warn_lbl = ctk.CTkLabel(form, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER, wraplength=380)
        warn_lbl.pack(fill="x", padx=16, pady=4)

        def _check_target(*_):
            txt = combo.get()
            t_id = loc_map.get(txt)
            if t_id:
                ok, msg = self.shelf_service.validate_shelf_allocation(
                    self.user.store_id, batch.medicine_id, t_id, batch.expiry_date, exclude_batch_id=batch.batch_id
                )
                if not ok:
                    warn_lbl.configure(text=f"⚠️ {msg}", text_color=Theme.DANGER)
                else:
                    warn_lbl.configure(text="✅ Target shelf satisfies storage policy.", text_color=Theme.SUCCESS)

        combo.configure(command=lambda _: _check_target())

        def _save():
            txt = combo.get()
            t_id = loc_map.get(txt)
            if not t_id:
                return
            try:
                self.inventory_service.relocate_batch(
                    store_id=self.user.store_id,
                    batch_id=batch.batch_id,
                    target_location_id=t_id,
                    reason="Relocated via UI",
                    acting_user=self.user
                )
                modal.destroy()
                self._load_active_tab()
                messagebox.showinfo("Success", f"Batch {batch.batch_number} relocated to new shelf.")
            except Exception as e:
                warn_lbl.configure(text=str(e), text_color=Theme.DANGER)

        ctk.CTkButton(form, text="Confirm Relocation", font=Theme.FONT_SUBHEADING, fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK, command=_save).pack(fill="x", padx=16, pady=14)

    def _open_adjust_modal(self, batch_id: int) -> None:
        """Modal to perform stock adjustment with mandatory audit reason."""
        batch = self.inventory_service.get_batch_by_id(batch_id, store_id=self.user.store_id, acting_user=self.user)
        if not batch:
            return

        modal = ctk.CTkToplevel(self)
        modal.title(f"Adjust Stock — Batch {batch.batch_number}")
        modal.geometry("450x340")
        modal.transient(self)
        modal.grab_set()

        form = ctk.CTkFrame(modal, fg_color=Theme.BG_CARD, corner_radius=8)
        form.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(form, text=f"⚖️ Stock Adjustment: {batch.batch_number}", font=Theme.FONT_HEADING, text_color=Theme.TEXT_MAIN).pack(anchor="w", padx=16, pady=(12, 4))
        ctk.CTkLabel(form, text=f"Current Stock: {batch.current_quantity} units", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=16, pady=(0, 10))

        ctk.CTkLabel(form, text="Quantity Delta * (e.g. +5 or -3)", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=16, pady=(4, 2))
        q_ent = ctk.CTkEntry(form, placeholder_text="+/- integer", height=32, font=Theme.FONT_BODY)
        q_ent.pack(fill="x", padx=16, pady=(0, 6))

        ctk.CTkLabel(form, text="Reason for Adjustment *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=16, pady=(4, 2))
        r_ent = ctk.CTkEntry(form, placeholder_text="e.g. Stock audit count correction", height=32, font=Theme.FONT_BODY)
        r_ent.pack(fill="x", padx=16, pady=(0, 6))

        err_lbl = ctk.CTkLabel(form, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER)
        err_lbl.pack(padx=16, pady=4)

        def _save():
            try:
                delta = int(q_ent.get().strip())
                reason = r_ent.get().strip()
                self.inventory_service.adjust_stock(
                    store_id=self.user.store_id,
                    batch_id=batch.batch_id,
                    quantity_delta=delta,
                    reason=reason,
                    acting_user=self.user
                )
                modal.destroy()
                self._load_active_tab()
                messagebox.showinfo("Success", f"Stock adjusted by {delta:+d} units.")
            except Exception as e:
                err_lbl.configure(text=str(e))

        ctk.CTkButton(form, text="Post Adjustment", font=Theme.FONT_SUBHEADING, fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK, command=_save).pack(fill="x", padx=16, pady=12)

    def _write_off_batch(self, batch_id: int) -> None:
        """Prompts confirmation to write off expired batch."""
        if messagebox.askyesno("Confirm Write-Off", "Write off remaining units of this expired batch?"):
            try:
                self.inventory_service.write_off_expired_batch(
                    store_id=self.user.store_id,
                    batch_id=batch_id,
                    reason="Expired stock write-off via UI",
                    acting_user=self.user
                )
                self._load_active_tab()
            except Exception as e:
                messagebox.showerror("Error", f"Failed write-off: {e}")
