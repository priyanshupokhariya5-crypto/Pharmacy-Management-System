"""
Report and Analytics Service for real database-backed operational reporting.
Provides:
  - Daily & monthly sales summaries with Cash/UPI/Card breakdowns
  - Cashier performance within store scope
  - Medicine-wise sales performance
  - Batch-wise inventory valuation (physical, sellable, expired, quarantined)
  - Supplier procurement summary
  - Stock movement ledger and audit logs
  - Returns and refund analytics
  - CSV export capabilities
"""
import csv
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from database.db import Database, get_db
from utils.logger import get_app_logger
from services.rbac import require_permission, require_store_access, PERM_VIEW_FINANCIALS, PERM_VIEW_AUDIT_LOGS


class ReportService:
    """Service providing tabular operational reports and CSV data export."""

    def __init__(self, db: Optional[Database] = None, store_id: Optional[str] = None):
        self.db = db or get_db()
        self.store_id = store_id or "STORE-LEGACY-001"
        self.logger = get_app_logger()

    def _table_exists(self, table_name: str) -> bool:
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        if not self._table_exists(table_name):
            return False
        cols = [c["name"] for c in self.db.fetch_all(f"PRAGMA table_info({table_name})")]
        return column_name in cols

    def get_sales_summary_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generates real database-backed sales summary with payment method breakdowns.
        """
        if acting_user is not None:
            require_store_access(acting_user, self.store_id, "Generating sales report")

        has_pm = self._column_exists("sales", "payment_method")
        has_disc = self._column_exists("sales", "discount_amount")
        has_tax = self._column_exists("sales", "tax_amount")

        query = "SELECT s.* FROM sales s WHERE (s.store_id = ? OR (s.store_id IS NULL AND ? = 'STORE-LEGACY-001'))"
        params: List[Any] = [self.store_id, self.store_id]

        if start_date:
            query += " AND substr(s.sale_date, 1, 10) >= ?"
            params.append(start_date)
        if end_date:
            query += " AND substr(s.sale_date, 1, 10) <= ?"
            params.append(end_date)

        query += " ORDER BY s.sale_id DESC"
        sales_rows = self.db.fetch_all(query, tuple(params))
        sales = [dict(s) for s in sales_rows]

        total_tx = len(sales)
        gross_sales = sum(float(s["total_amount"]) for s in sales)
        cash_total = sum(float(s["total_amount"]) for s in sales if (s.get("payment_method") or "Cash") == "Cash") if has_pm else gross_sales
        upi_total = sum(float(s["total_amount"]) for s in sales if s.get("payment_method") == "UPI") if has_pm else 0.0
        card_total = sum(float(s["total_amount"]) for s in sales if s.get("payment_method") == "Card") if has_pm else 0.0
        total_discount = sum(float(s["discount_amount"]) for s in sales if s.get("discount_amount")) if has_disc else 0.0
        total_tax = sum(float(s["tax_amount"]) for s in sales if s.get("tax_amount")) if has_tax else 0.0

        # Returns in date range
        total_refunds = 0.0
        if self._table_exists("sale_returns"):
            ret_q = "SELECT COALESCE(SUM(total_refund), 0) as tot_ref FROM sale_returns WHERE store_id = ?"
            ret_p: List[Any] = [self.store_id]
            if start_date:
                ret_q += " AND substr(return_date, 1, 10) >= ?"
                ret_p.append(start_date)
            if end_date:
                ret_q += " AND substr(return_date, 1, 10) <= ?"
                ret_p.append(end_date)
            r_row = self.db.fetch_one(ret_q, tuple(ret_p))
            total_refunds = float(r_row["tot_ref"]) if r_row else 0.0

        net_sales = round(gross_sales - total_refunds, 2)

        return {
            "store_id": self.store_id,
            "start_date": start_date or "All Time",
            "end_date": end_date or "All Time",
            "total_transactions": total_tx,
            "gross_sales": round(gross_sales, 2),
            "cash_collections": round(cash_total, 2),
            "upi_collections": round(upi_total, 2),
            "card_collections": round(card_total, 2),
            "total_discount": round(total_discount, 2),
            "total_tax": round(total_tax, 2),
            "total_refunds": round(total_refunds, 2),
            "net_sales": net_sales,
            "transactions": [dict(s) for s in sales]
        }

    def get_cashier_performance_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """Generates performance report per cashier within active store."""
        if acting_user is not None:
            require_store_access(acting_user, self.store_id, "Viewing cashier performance")

        query = """
        SELECT u.user_id, COALESCE(u.username, 'System / Walk-in') as username,
               COUNT(s.sale_id) as total_bills,
               COALESCE(SUM(s.total_amount), 0) as gross_sales
        FROM sales s
        LEFT JOIN users u ON s.user_id = u.user_id
        WHERE (s.store_id = ? OR (s.store_id IS NULL AND ? = 'STORE-LEGACY-001'))
        """
        params: List[Any] = [self.store_id, self.store_id]
        if start_date:
            query += " AND substr(s.sale_date, 1, 10) >= ?"
            params.append(start_date)
        if end_date:
            query += " AND substr(s.sale_date, 1, 10) <= ?"
            params.append(end_date)

        query += " GROUP BY s.user_id ORDER BY gross_sales DESC"
        rows = self.db.fetch_all(query, tuple(params))
        res = []
        for r in rows:
            uid = r["user_id"]
            gross = float(r["gross_sales"])
            ref_amt = 0.0
            if self._table_exists("sale_returns") and uid:
                ref_q = "SELECT COALESCE(SUM(total_refund), 0) as ref FROM sale_returns WHERE store_id = ? AND created_by = ?"
                ref_row = self.db.fetch_one(ref_q, (self.store_id, uid))
                ref_amt = float(ref_row["ref"]) if ref_row else 0.0
            res.append({
                "user_id": uid,
                "username": r["username"],
                "total_bills": r["total_bills"],
                "gross_sales": round(gross, 2),
                "total_refunds": round(ref_amt, 2),
                "net_sales": round(gross - ref_amt, 2)
            })
        return res

    def get_medicine_sales_report(
        self,
        limit: int = 50,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """Generates medicine sales performance report sorted by units sold."""
        if acting_user is not None:
            require_store_access(acting_user, self.store_id, "Viewing medicine sales report")

        query = """
        SELECT m.medicine_id, m.medicine_code, m.medicine_name, m.category,
               COALESCE(SUM(si.quantity), 0) as total_units_sold,
               COALESCE(SUM(si.subtotal), 0) as total_revenue
        FROM sale_items si
        JOIN medicines m ON si.medicine_id = m.medicine_id
        WHERE (si.store_id = ? OR (si.store_id IS NULL AND ? = 'STORE-LEGACY-001'))
        GROUP BY m.medicine_id
        ORDER BY total_units_sold DESC
        LIMIT ?
        """
        rows = self.db.fetch_all(query, (self.store_id, self.store_id, limit))
        return [
            {
                "medicine_id": r["medicine_id"],
                "medicine_code": r["medicine_code"],
                "medicine_name": r["medicine_name"],
                "category": r["category"],
                "units_sold": int(r["total_units_sold"]),
                "revenue": round(float(r["total_revenue"]), 2)
            }
            for r in rows
        ]

    def get_inventory_valuation_report(
        self,
        acting_user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Generates full inventory valuation report distinguishing physical, sellable,
        expired, and quarantined stock.
        """
        if acting_user is not None:
            require_store_access(acting_user, self.store_id, "Viewing inventory valuation")

        today_str = datetime.now().strftime("%Y-%m-%d")
        has_batches = self._table_exists("inventory_batches")

        if has_batches:
            query = """
            SELECT b.batch_id, b.batch_number, m.medicine_name, m.medicine_code,
                   b.current_quantity, b.selling_price, b.purchase_cost,
                   b.expiry_date, b.status, b.verification_flag,
                   l.shelf_code
            FROM inventory_batches b
            JOIN medicines m ON b.medicine_id = m.medicine_id
            LEFT JOIN storage_locations l ON b.location_id = l.location_id
            WHERE b.store_id = ?
            ORDER BY b.expiry_date ASC
            """
            batches = self.db.fetch_all(query, (self.store_id,))

            total_physical_units = sum(b["current_quantity"] for b in batches)
            sellable_units = sum(
                b["current_quantity"] for b in batches
                if b["status"] == "Active" and b["verification_flag"] == 0 and b["expiry_date"] >= today_str
            )
            expired_units = sum(
                b["current_quantity"] for b in batches
                if b["expiry_date"] < today_str or b["status"] == "Expired"
            )
            quarantined_units = sum(
                b["current_quantity"] for b in batches
                if b["status"] in ("Quarantined", "Recalled")
            )
            unverified_units = sum(
                b["current_quantity"] for b in batches
                if b["verification_flag"] == 1
            )
            total_sales_value = sum(b["current_quantity"] * float(b["selling_price"]) for b in batches)

            return {
                "store_id": self.store_id,
                "has_normalized_batches": True,
                "total_batches_count": len(batches),
                "total_physical_units": total_physical_units,
                "sellable_units": sellable_units,
                "expired_units": expired_units,
                "quarantined_units": quarantined_units,
                "unverified_units": unverified_units,
                "total_valuation": round(total_sales_value, 2),
                "batches": [dict(b) for b in batches]
            }
        else:
            # Fallback for unmigrated legacy database
            meds = self.db.fetch_all(
                "SELECT medicine_id, medicine_code, medicine_name, quantity, price, expiry_date FROM medicines WHERE store_id = ?",
                (self.store_id,)
            )
            total_units = sum(m["quantity"] for m in meds)
            expired_units = sum(m["quantity"] for m in meds if m["expiry_date"] < today_str)
            sellable_units = sum(m["quantity"] for m in meds if m["expiry_date"] >= today_str)
            total_val = sum(m["quantity"] * float(m["price"]) for m in meds)

            return {
                "store_id": self.store_id,
                "has_normalized_batches": False,
                "total_batches_count": len(meds),
                "total_physical_units": total_units,
                "sellable_units": sellable_units,
                "expired_units": expired_units,
                "quarantined_units": 0,
                "unverified_units": 0,
                "total_valuation": round(total_val, 2),
                "batches": [dict(m) for m in meds]
            }

    def export_to_csv(self, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> str:
        """Exports a list of row dicts into RFC 4180 CSV string format."""
        if not rows:
            return ""
        if not fieldnames:
            fieldnames = list(rows[0].keys())

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
        return output.getvalue()
