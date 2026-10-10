"""
Inventory & Sales Analytical Reports View.
Provides data-driven analytical reports using Pandas DataFrames and embedded Matplotlib charts
for Fact-Based Decision Making.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any
import customtkinter as ctk
import pandas as pd

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ui.theme import Theme
from reports.report_generator import ReportGenerator
from services.medicine_service import MedicineService
from services.sales_service import SalesService
from models.user import User
from utils.logger import get_app_logger


class ReportsView(ctk.CTkFrame):
    """Reports View rendering analytical tables, Pandas summaries, and embedded Matplotlib charts."""

    def __init__(self, parent, user: User):
        super().__init__(parent, fg_color="transparent")
        self.user = user
        self.report_gen = ReportGenerator()
        self.medicine_service = MedicineService()
        self.sales_service = SalesService()
        self.logger = get_app_logger()

        # Canvas references for canvas cleanup on refresh
        self.canvas_cat = None
        self.canvas_status = None

        self._build_ui()
        self.refresh_reports()

    def _build_ui(self) -> None:
        """Constructs header, KPI cards, tabbed views, and Footer banner."""
        # ----------------------------------------------------
        # 1. Header Banner
        # ----------------------------------------------------
        header_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12)
        header_card.pack(fill="x", pady=(0, 10))

        title_lbl = ctk.CTkLabel(
            header_card,
            text="📈 Inventory & Sales Analytical Reports",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        )
        title_lbl.pack(side="left", padx=20, pady=12)

        refresh_btn = ctk.CTkButton(
            header_card,
            text="🔄 Refresh Reports",
            font=Theme.FONT_BOLD,
            height=34,
            width=130,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self.refresh_reports
        )
        refresh_btn.pack(side="right", padx=20, pady=12)

        # ----------------------------------------------------
        # 2. KPI Summary Cards
        # ----------------------------------------------------
        kpi_frame = ctk.CTkFrame(self, fg_color="transparent")
        kpi_frame.pack(fill="x", pady=(0, 10))

        self.card_widgets = {}
        kpi_specs = [
            ("total_meds", "Total Medicines", "0", Theme.PRIMARY),
            ("total_stock", "Total Stock Units", "0", Theme.SECONDARY),
            ("total_inv_val", "Total Inventory Value", "₹0.00", Theme.SUCCESS),
            ("total_sales_tx", "Sales Transactions", "0", Theme.INFO),
            ("total_sales_val", "Total Sales Revenue", "₹0.00", Theme.SUCCESS)
        ]

        for idx, (key, title, default_val, color) in enumerate(kpi_specs):
            card = ctk.CTkFrame(
                kpi_frame,
                fg_color=Theme.BG_CARD,
                corner_radius=10,
                border_width=1,
                border_color=Theme.BORDER_COLOR
            )
            card.grid(row=0, column=idx, padx=4, pady=2, sticky="nsew")
            kpi_frame.columnconfigure(idx, weight=1)

            lbl_title = ctk.CTkLabel(card, text=title, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
            lbl_title.pack(pady=(10, 2), padx=8)

            lbl_val = ctk.CTkLabel(card, text=default_val, font=Theme.FONT_HEADING, text_color=color)
            lbl_val.pack(pady=(0, 10), padx=8)

            self.card_widgets[key] = lbl_val

        # ----------------------------------------------------
        # 3. Tabbed Analytical Container
        # ----------------------------------------------------
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=Theme.BG_CARD,
            segmented_button_fg_color=Theme.INPUT_BG,
            segmented_button_selected_color=Theme.PRIMARY,
            segmented_button_selected_hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_MAIN
        )
        self.tabview.pack(fill="both", expand=True, pady=(0, 8))

        self.tabview.add("Inventory & Stock Alerts")
        self.tabview.add("Sales Analytics & History")
        self.tabview.add("Matplotlib Quality Charts")

        self._build_inventory_tab()
        self._build_sales_tab()
        self._build_charts_tab()

        # ----------------------------------------------------
        # 4. Fact-Based Decision Making Footer Card
        # ----------------------------------------------------
        footer_card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=8,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        footer_card.pack(fill="x")

        footer_text = (
            "🎯 Fact-Based Decision Making: Inventory and sales decisions are supported by actual database records, "
            "calculated KPIs and visual data analysis rather than assumptions. | Data Source: SQLite | Analysis: Pandas | Visualization: Matplotlib"
        )
        footer_lbl = ctk.CTkLabel(
            footer_card,
            text=footer_text,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            anchor="w"
        )
        footer_lbl.pack(padx=15, pady=6, fill="x")

    def _build_inventory_tab(self) -> None:
        """Constructs Low Stock, Out of Stock, Expiry, and Pandas Category Aggregation tables."""
        tab = self.tabview.tab("Inventory & Stock Alerts")

        scroll_container = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll_container.pack(fill="both", expand=True)

        # Style Treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Report.Treeview",
            background=Theme.BG_DARK,
            foreground=Theme.TEXT_MAIN,
            fieldbackground=Theme.BG_DARK,
            rowheight=24,
            font=("Segoe UI", 9)
        )
        style.configure(
            "Report.Treeview.Heading",
            background=Theme.INPUT_BG,
            foreground=Theme.TEXT_MAIN,
            font=("Segoe UI", 9, "bold")
        )

        # Section 1: Low Stock Table
        ctk.CTkLabel(scroll_container, text="⚠️ Low Stock Items (0 < Stock <= 10)", font=Theme.FONT_SUBHEADING, text_color=Theme.WARNING, anchor="w").pack(fill="x", pady=(5, 4))
        
        low_cols = ("code", "name", "category", "manufacturer", "qty", "price", "total_val")
        self.low_tree = ttk.Treeview(scroll_container, columns=low_cols, show="headings", style="Report.Treeview", height=4)
        for c, t, w in [("code", "Code", 80), ("name", "Medicine Name", 160), ("category", "Category", 110), ("manufacturer", "Manufacturer", 120), ("qty", "Qty", 55), ("price", "Price (₹)", 75), ("total_val", "Total Value (₹)", 95)]:
            self.low_tree.heading(c, text=t)
            self.low_tree.column(c, width=w, anchor="center" if c in ("code", "qty", "price", "total_val") else "w")
        self.low_tree.pack(fill="x", pady=(0, 12))

        # Section 2: Out of Stock Table
        ctk.CTkLabel(scroll_container, text="❌ Out-of-Stock Items (Stock = 0)", font=Theme.FONT_SUBHEADING, text_color=Theme.DANGER, anchor="w").pack(fill="x", pady=(0, 4))
        
        out_cols = ("code", "name", "category", "manufacturer", "qty", "price")
        self.out_tree = ttk.Treeview(scroll_container, columns=out_cols, show="headings", style="Report.Treeview", height=3)
        for c, t, w in [("code", "Code", 80), ("name", "Medicine Name", 180), ("category", "Category", 120), ("manufacturer", "Manufacturer", 140), ("qty", "Qty", 60), ("price", "Price (₹)", 80)]:
            self.out_tree.heading(c, text=t)
            self.out_tree.column(c, width=w, anchor="center" if c in ("code", "qty", "price") else "w")
        self.out_tree.pack(fill="x", pady=(0, 12))

        # Section 3: Expiry Status Table
        ctk.CTkLabel(scroll_container, text="📅 Expiry Monitoring Report", font=Theme.FONT_SUBHEADING, text_color=Theme.PRIMARY, anchor="w").pack(fill="x", pady=(0, 4))
        
        exp_cols = ("code", "name", "batch", "expiry", "qty", "expiry_status")
        self.exp_tree = ttk.Treeview(scroll_container, columns=exp_cols, show="headings", style="Report.Treeview", height=4)
        for c, t, w in [("code", "Code", 80), ("name", "Medicine Name", 180), ("batch", "Batch No", 80), ("expiry", "Expiry Date", 100), ("qty", "Qty", 60), ("expiry_status", "Expiry Status", 110)]:
            self.exp_tree.heading(c, text=t)
            self.exp_tree.column(c, width=w, anchor="center" if c in ("code", "batch", "expiry", "qty", "expiry_status") else "w")
        self.exp_tree.pack(fill="x", pady=(0, 12))

        # Section 4: Pandas Category Aggregation Table
        ctk.CTkLabel(scroll_container, text="📊 Category Stock Analysis (Pandas Aggregation)", font=Theme.FONT_SUBHEADING, text_color=Theme.SECONDARY, anchor="w").pack(fill="x", pady=(0, 4))
        
        cat_cols = ("category", "count", "total_qty", "total_val")
        self.cat_agg_tree = ttk.Treeview(scroll_container, columns=cat_cols, show="headings", style="Report.Treeview", height=4)
        for c, t, w in [("category", "Category Name", 160), ("count", "Medicine Count", 120), ("total_qty", "Total Stock Units", 130), ("total_val", "Total Value (₹)", 140)]:
            self.cat_agg_tree.heading(c, text=t)
            self.cat_agg_tree.column(c, width=w, anchor="center" if c != "category" else "w")
        self.cat_agg_tree.pack(fill="x", pady=(0, 10))

    def _build_sales_tab(self) -> None:
        """Constructs Sales History table and analytical sales summary metrics."""
        tab = self.tabview.tab("Sales Analytics & History")

        # Sales Metrics Banner
        m_frame = ctk.CTkFrame(tab, fg_color=Theme.INPUT_BG, corner_radius=8)
        m_frame.pack(fill="x", padx=10, pady=(10, 10))

        self.sales_metrics_lbl = ctk.CTkLabel(
            m_frame,
            text="Transactions: 0  |  Items Sold: 0  |  Revenue: ₹0.00  |  Avg Sale: ₹0.00",
            font=Theme.FONT_HEADING,
            text_color=Theme.SUCCESS
        )
        self.sales_metrics_lbl.pack(padx=15, pady=10)

        # Sales History Table
        ctk.CTkLabel(tab, text="📜 Complete Sales Transaction History (Billing & Invoices)", font=Theme.FONT_SUBHEADING, text_color=Theme.PRIMARY, anchor="w").pack(fill="x", padx=10, pady=(5, 4))

        table_container = ctk.CTkFrame(tab, fg_color="transparent")
        table_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        sales_cols = ("invoice_number", "date", "patient", "cashier", "items_count", "total_amount")
        self.sales_tree = ttk.Treeview(table_container, columns=sales_cols, show="headings", style="Report.Treeview")

        for c, t, w in [("invoice_number", "Invoice #", 130), ("date", "Transaction Date", 140), ("patient", "Patient Name", 150), ("cashier", "Cashier", 110), ("items_count", "Items", 60), ("total_amount", "Total (₹)", 100)]:
            self.sales_tree.heading(c, text=t)
            self.sales_tree.column(c, width=w, anchor="center" if c in ("items_count", "total_amount") else "w")

        sales_vsb = ttk.Scrollbar(table_container, orient="vertical", command=self.sales_tree.yview)
        self.sales_tree.configure(yscrollcommand=sales_vsb.set)
        
        self.sales_tree.pack(side="left", fill="both", expand=True)
        sales_vsb.pack(side="right", fill="y")
        
        # Action Buttons for Sales History
        action_frame = ctk.CTkFrame(tab, fg_color="transparent")
        action_frame.pack(fill="x", padx=10, pady=(0, 15))
        
        view_bill_btn = ctk.CTkButton(
            action_frame,
            text="👁 View Bill / Invoice",
            font=Theme.FONT_BOLD,
            height=34,
            width=150,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self._view_historical_bill
        )
        view_bill_btn.pack(side="right", padx=5)
        
        self.sales_tree.bind("<Double-1>", lambda e: self._view_historical_bill())

    def _view_historical_bill(self):
        """Opens the InvoiceReceiptModal for the selected historical bill."""
        selected = self.sales_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an invoice from the history table first.")
            return
            
        item_values = self.sales_tree.item(selected[0], 'values')
        if not item_values:
            return
            
        # The first column is invoice_number, but if it is INV-LEGACY-000004 or #4, we need sale_id to fetch details.
        # Wait, get_sales_history_dataframe currently returns sale_id but we don't display it directly?
        # Let's see get_sales_history_dataframe. It has sale_id. We should store it in a hidden column or parse from invoice_number if it's #4.
        # Actually, let's just search the database for the invoice_number.
        inv_val = item_values[0]
        
        # We need a robust way to get sale details. Let's just use sales_service to get sale by invoice_number or sale_id.
        sale_id = None
        if inv_val.startswith("#"):
            sale_id = int(inv_val[1:])
        elif inv_val.startswith("INV-LEGACY-"):
            sale_id = int(inv_val.split("-")[-1])
        else:
            # Let's look up sale_id by invoice_number
            db = self.medicine_service.db
            row = db.fetch_one("SELECT sale_id FROM sales WHERE invoice_number = ?", (inv_val,))
            if row:
                sale_id = row['sale_id']
                
        if not sale_id:
            messagebox.showerror("Error", "Could not resolve sale ID for the selected invoice.")
            return
            
        sale_details = self.sales_service.get_sale_details(sale_id)
        if not sale_details:
            messagebox.showerror("Error", "Could not fetch details for this sale.")
            return
            
        from ui.billing import InvoiceReceiptModal
        InvoiceReceiptModal(self, sale_details)

    def _build_charts_tab(self) -> None:
        """Constructs embedded Matplotlib charts layout frame."""
        tab = self.tabview.tab("Matplotlib Quality Charts")

        self.charts_container = ctk.CTkFrame(tab, fg_color="transparent")
        self.charts_container.pack(fill="both", expand=True, padx=10, pady=10)

    def refresh_reports(self) -> None:
        """Re-queries SQLite database, rebuilds Pandas DataFrames, populates tables & Matplotlib figures."""
        # 1. Update KPI Summary Cards
        summary = self.medicine_service.get_inventory_summary()
        sales_metrics = self.report_gen.get_sales_summary_metrics()

        self.card_widgets["total_meds"].configure(text=str(summary["total_medicines"]))
        self.card_widgets["total_stock"].configure(text=str(summary["total_stock_quantity"]))
        self.card_widgets["total_inv_val"].configure(text=f"₹{summary['total_inventory_value']:,.2f}")
        self.card_widgets["total_sales_tx"].configure(text=str(sales_metrics["total_transactions"]))
        self.card_widgets["total_sales_val"].configure(text=f"₹{sales_metrics['total_sales_value']:,.2f}")

        # 2. Populate Low Stock Table
        df_low = self.report_gen.get_low_stock_dataframe()
        for item in self.low_tree.get_children():
            self.low_tree.delete(item)
        if not df_low.empty:
            for _, r in df_low.iterrows():
                self.low_tree.insert("", "end", values=(r["medicine_code"], r["medicine_name"], r["category"], r["manufacturer"], r["quantity"], f"₹{r['price']:.2f}", f"₹{r['total_value']:.2f}"))

        # 3. Populate Out of Stock Table
        df_out = self.report_gen.get_out_of_stock_dataframe()
        for item in self.out_tree.get_children():
            self.out_tree.delete(item)
        if not df_out.empty:
            for _, r in df_out.iterrows():
                self.out_tree.insert("", "end", values=(r["medicine_code"], r["medicine_name"], r["category"], r["manufacturer"], r["quantity"], f"₹{r['price']:.2f}"))

        # 4. Populate Expiry Report Table
        df_exp = self.report_gen.get_expiry_report_dataframe()
        for item in self.exp_tree.get_children():
            self.exp_tree.delete(item)
        if not df_exp.empty:
            for _, r in df_exp.iterrows():
                self.exp_tree.insert("", "end", values=(r["medicine_code"], r["medicine_name"], r["batch_no"], r["expiry_date"], r["quantity"], r["expiry_status"]))

        # 5. Populate Pandas Category Aggregation Table
        df_cat = self.report_gen.get_category_analysis_dataframe()
        for item in self.cat_agg_tree.get_children():
            self.cat_agg_tree.delete(item)
        if not df_cat.empty:
            for _, r in df_cat.iterrows():
                self.cat_agg_tree.insert("", "end", values=(r["category"], r["medicine_count"], r["total_quantity"], f"₹{r['total_inventory_value']:,.2f}"))

        # 6. Populate Sales History & Metrics
        df_sales = self.report_gen.get_sales_history_dataframe()
        for item in self.sales_tree.get_children():
            self.sales_tree.delete(item)

        if not df_sales.empty:
            for _, r in df_sales.iterrows():
                cashier_str = r["cashier"] if pd.notna(r["cashier"]) else "System"
                inv_str = r.get("invoice_number") or f"#{r['sale_id']}"
                pat_str = r.get("patient_name") or "N/A"
                self.sales_tree.insert("", "end", values=(inv_str, r["sale_date"], pat_str, cashier_str, r["total_items"], f"₹{r['total_amount']:.2f}"))
            
            s_text = (
                f"Transactions: {sales_metrics['total_transactions']}  |  "
                f"Items Sold: {sales_metrics['total_items_sold']} units  |  "
                f"Total Revenue: ₹{sales_metrics['total_sales_value']:,.2f}  |  "
                f"Avg Sale: ₹{sales_metrics['avg_sale_value']:.2f}"
            )
            self.sales_metrics_lbl.configure(text=s_text)
        else:
            self.sales_metrics_lbl.configure(text="No sales records available. Perform a sale in Billing to generate history.")

        # 7. Render Embedded Matplotlib Figures
        self._render_charts()

        self.logger.log_event("REPORTS", "Analytical reports and Pandas DataFrames refreshed successfully.")

    def _render_charts(self) -> None:
        """Embeds Matplotlib Figures inside Tkinter canvas."""
        for widget in self.charts_container.winfo_children():
            widget.destroy()

        # Canvas 1: Category Stock Chart
        fig1 = self.report_gen.generate_category_stock_chart()
        canvas1 = FigureCanvasTkAgg(fig1, master=self.charts_container)
        canvas1.draw()
        canvas1.get_tk_widget().pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # Canvas 2: Stock Status Chart
        fig2 = self.report_gen.generate_stock_status_chart()
        canvas2 = FigureCanvasTkAgg(fig2, master=self.charts_container)
        canvas2.draw()
        canvas2.get_tk_widget().pack(side="right", fill="both", expand=True, padx=5, pady=5)
