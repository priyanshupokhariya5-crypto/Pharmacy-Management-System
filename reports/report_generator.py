"""
Report Generator module using Pandas and Matplotlib.
Provides analytical DataFrames, category aggregations, and Matplotlib figures for Fact-Based Decision Making.
Enforces multi-store tenant isolation across all reporting metrics and charts.
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import pandas as pd
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

from database.db import Database, get_db
from models.medicine import LOW_STOCK_THRESHOLD, EXPIRING_SOON_DAYS


class ReportGenerator:
    """Generates inventory/sales DataFrames and Matplotlib figures scoped to the active store."""

    def __init__(self, db: Optional[Database] = None, store_id: Optional[str] = None):
        self.db = db or get_db()
        self.store_id = store_id or "STORE-LEGACY-001"

    def get_inventory_dataframe(self) -> pd.DataFrame:
        """Returns a Pandas DataFrame of store inventory with calculated total value."""
        query = """
        SELECT medicine_id, store_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, (price * quantity) as total_value
        FROM medicines
        WHERE store_id = ?
        ORDER BY medicine_name ASC
        """
        conn = self.db.get_connection()
        try:
            df = pd.read_sql_query(query, conn, params=(self.store_id,))
            return df
        finally:
            conn.close()

    def get_low_stock_dataframe(self, threshold: int = LOW_STOCK_THRESHOLD) -> pd.DataFrame:
        """Returns a Pandas DataFrame of low stock medicines (0 < quantity <= 10) in active store."""
        query = """
        SELECT medicine_code, medicine_name, category, manufacturer, quantity, price, (price * quantity) as total_value
        FROM medicines
        WHERE store_id = ? AND quantity > 0 AND quantity <= ?
        ORDER BY quantity ASC
        """
        conn = self.db.get_connection()
        try:
            df = pd.read_sql_query(query, conn, params=(self.store_id, threshold))
            return df
        finally:
            conn.close()

    def get_out_of_stock_dataframe(self) -> pd.DataFrame:
        """Returns a Pandas DataFrame of out-of-stock medicines (quantity == 0) in active store."""
        query = """
        SELECT medicine_code, medicine_name, category, manufacturer, quantity, price
        FROM medicines
        WHERE store_id = ? AND quantity = 0
        ORDER BY medicine_name ASC
        """
        conn = self.db.get_connection()
        try:
            df = pd.read_sql_query(query, conn, params=(self.store_id,))
            return df
        finally:
            conn.close()

    def get_expiry_report_dataframe(self) -> pd.DataFrame:
        """Returns a Pandas DataFrame of medicine expiry statuses for active store."""
        df = self.get_inventory_dataframe()
        if df.empty:
            return df

        today = datetime.now().date()
        soon_threshold = today + timedelta(days=EXPIRING_SOON_DAYS)

        def classify_expiry(date_str: str) -> str:
            try:
                exp = datetime.strptime(date_str, "%Y-%m-%d").date()
                if exp < today:
                    return "Expired"
                elif today <= exp <= soon_threshold:
                    return "Expiring Soon"
                return "Valid"
            except Exception:
                return "Unknown"

        df["expiry_status"] = df["expiry_date"].apply(classify_expiry)
        return df

    def get_sales_history_dataframe(self) -> pd.DataFrame:
        """Returns a Pandas DataFrame summarizing total sales transactions and line items for active store."""
        query = """
        SELECT s.sale_id, s.store_id, s.invoice_number, s.patient_name, s.patient_phone, s.patient_age,
               s.sale_date, s.total_amount, u.username as cashier,
               (SELECT SUM(quantity) FROM sale_items si WHERE si.sale_id = s.sale_id AND si.store_id = s.store_id) as total_items
        FROM sales s
        LEFT JOIN users u ON s.user_id = u.user_id
        WHERE s.store_id = ?
        ORDER BY s.sale_id DESC
        """
        conn = self.db.get_connection()
        try:
            df = pd.read_sql_query(query, conn, params=(self.store_id,))
            if not df.empty:
                df["total_items"] = df["total_items"].fillna(0).astype(int)
            return df
        finally:
            conn.close()

    def get_category_analysis_dataframe(self) -> pd.DataFrame:
        """Performs Pandas aggregation grouped by category for the active store."""
        df = self.get_inventory_dataframe()
        if df.empty:
            return pd.DataFrame(columns=["category", "medicine_count", "total_quantity", "total_inventory_value"])

        summary = df.groupby("category").agg(
            medicine_count=("medicine_id", "count"),
            total_quantity=("quantity", "sum"),
            total_inventory_value=("total_value", "sum")
        ).reset_index()

        summary = summary.sort_values(by="total_quantity", ascending=False)
        return summary

    def get_sales_summary_metrics(self) -> Dict[str, Any]:
        """Calculates analytical sales KPIs for the active store."""
        df_sales = self.get_sales_history_dataframe()
        if df_sales.empty:
            return {
                "total_transactions": 0,
                "total_items_sold": 0,
                "total_sales_value": 0.0,
                "avg_sale_value": 0.0
            }

        total_tx = len(df_sales)
        total_items = int(df_sales["total_items"].sum())
        total_val = float(df_sales["total_amount"].sum())
        avg_val = float(df_sales["total_amount"].mean()) if total_tx > 0 else 0.0

        return {
            "total_transactions": total_tx,
            "total_items_sold": total_items,
            "total_sales_value": round(total_val, 2),
            "avg_sale_value": round(avg_val, 2)
        }

    def generate_category_stock_chart(self) -> plt.Figure:
        """Generates a Matplotlib Bar Chart figure showing total stock quantity by category for active store."""
        df = self.get_category_analysis_dataframe()

        fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=100)
        fig.patch.set_facecolor("#1e1e2e")
        ax.set_facecolor("#1e1e2e")

        if not df.empty:
            bars = ax.bar(df["category"], df["total_quantity"], color="#89b4fa", edgecolor="#313244")
            ax.set_title("Stock Quantity by Category", color="#cdd6f4", fontsize=11, fontweight="bold")
            ax.set_xlabel("Category", color="#a6adc8", fontsize=9)
            ax.set_ylabel("Total Units", color="#a6adc8", fontsize=9)
            ax.tick_params(colors="#cdd6f4", labelsize=8)
            plt.xticks(rotation=20, ha="right")

            for bar in bars:
                height = bar.get_height()
                ax.annotate(f"{int(height)}",
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 2),
                            textcoords="offset points",
                            ha="center", va="bottom", color="#cdd6f4", fontsize=8)
        else:
            ax.text(0.5, 0.5, "No Inventory Data", color="#a6adc8", ha="center", va="center")

        fig.tight_layout()
        return fig

    def generate_stock_status_chart(self) -> plt.Figure:
        """Generates a Matplotlib Bar Chart figure showing medicine counts by stock status for active store."""
        df = self.get_inventory_dataframe()

        fig, ax = plt.subplots(figsize=(5.5, 3.2), dpi=100)
        fig.patch.set_facecolor("#1e1e2e")
        ax.set_facecolor("#1e1e2e")

        if not df.empty:
            available_cnt = len(df[df["quantity"] > LOW_STOCK_THRESHOLD])
            low_cnt = len(df[(df["quantity"] > 0) & (df["quantity"] <= LOW_STOCK_THRESHOLD)])
            out_cnt = len(df[df["quantity"] == 0])

            categories = ["Available", "Low Stock", "Out of Stock"]
            counts = [available_cnt, low_cnt, out_cnt]
            colors = ["#a6e3a1", "#f9e2af", "#f38ba8"]

            bars = ax.bar(categories, counts, color=colors, edgecolor="#313244")
            ax.set_title("Medicine Count by Stock Status", color="#cdd6f4", fontsize=11, fontweight="bold")
            ax.set_xlabel("Stock Classification", color="#a6adc8", fontsize=9)
            ax.set_ylabel("Number of Medicines", color="#a6adc8", fontsize=9)
            ax.tick_params(colors="#cdd6f4", labelsize=8)

            for bar in bars:
                height = bar.get_height()
                ax.annotate(f"{int(height)}",
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 2),
                            textcoords="offset points",
                            ha="center", va="bottom", color="#cdd6f4", fontsize=8)
        else:
            ax.text(0.5, 0.5, "No Inventory Data", color="#a6adc8", ha="center", va="center")

        fig.tight_layout()
        return fig
