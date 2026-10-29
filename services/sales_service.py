"""
Sales Service for transaction billing, stock deduction, and sales reporting.
Enforces Poka-Yoke error prevention rules: blocks expired and out-of-stock items,
and guarantees atomic SQLite transaction behavior with multi-store tenant isolation.
"""
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from database.db import Database, get_db
from models.sale import Sale, SaleItem
from models.medicine import Medicine
from utils.logger import get_app_logger


class SalesService:
    """Manages billing checkout transactions and stock deductions atomically with store isolation."""

    def __init__(self, db: Optional[Database] = None, store_id: Optional[str] = None):
        self.db = db or get_db()
        self.store_id = store_id or "STORE-LEGACY-001"
        self.logger = get_app_logger()

    def validate_cart_item(self, medicine_id: int, quantity: int) -> Tuple[bool, str, Optional[Medicine]]:
        """
        Validates if a medicine item can be sold within the active store.
        Checks existence, non-expired status, and sufficient stock.
        """
        if quantity <= 0:
            return False, "Quantity must be greater than zero.", None

        med_row = self.db.fetch_one(
            "SELECT medicine_id, store_id, medicine_code, medicine_name, category, manufacturer, "
            "batch_no, price, quantity, expiry_date, created_at, updated_at "
            "FROM medicines WHERE medicine_id = ? AND store_id = ?",
            (medicine_id, self.store_id)
        )
        if not med_row:
            return False, f"Medicine ID {medicine_id} not found in store inventory.", None

        med = Medicine.from_row(med_row)

        # 1. Poka-Yoke Check: Block Expired Medicine
        if med.is_expired:
            self.logger.log_poka_yoke(
                "Expired Medicine Block",
                f"Blocked sale of expired medicine '{med.medicine_name}' (Expired: {med.expiry_date})"
            )
            return False, f"Sale blocked: '{med.medicine_name}' has expired on {med.expiry_date}.", med

        # 2. Stock Check: Block Insufficient Quantity
        if med.quantity < quantity:
            self.logger.log_poka_yoke(
                "Insufficient Stock Block",
                f"Blocked sale of '{med.medicine_name}': requested {quantity}, available {med.quantity}"
            )
            return False, f"Insufficient stock. Available quantity: {med.quantity}.", med

        return True, "Valid item.", med

    def process_sale(
        self,
        user_id: int,
        cart_items: List[Tuple[int, int]],
        patient_name: str,
        patient_phone: str = "",
        patient_age: Optional[int] = None
    ) -> Tuple[bool, str, Optional[int], Optional[str]]:
        """
        Processes a complete sales checkout transaction atomically within the active store.
        cart_items: List of (medicine_id, quantity) tuples.
        Returns (success_boolean, message, sale_id, invoice_number).
        Uses BEGIN TRANSACTION ... COMMIT / ROLLBACK with conditional SQL updates.
        """
        if not cart_items:
            self.logger.log_poka_yoke("Empty Checkout Attempt", "Blocked checkout attempt on an empty cart.")
            return False, "Cart is empty. Add medicines before confirming sale.", None, None
            
        patient_name = patient_name.strip()
        if not patient_name:
            return False, "Patient name is required.", None, None

        sale_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            
            # Re-read fresh database records inside transaction block (scoped to store_id)
            validated_items: List[Tuple[Medicine, int, float]] = []
            total_amount = 0.0

            for med_id, qty in cart_items:
                cursor.execute(
                    "SELECT medicine_id, store_id, medicine_code, medicine_name, category, manufacturer, "
                    "batch_no, price, quantity, expiry_date, created_at, updated_at "
                    "FROM medicines WHERE medicine_id = ? AND store_id = ?",
                    (med_id, self.store_id)
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Medicine ID {med_id} no longer exists or does not belong to this store.")

                med = Medicine.from_row(row)

                if med.is_expired:
                    self.logger.log_poka_yoke(
                        "Transaction Rollback - Expired Medicine",
                        f"Transaction aborted: '{med.medicine_name}' is expired ({med.expiry_date})."
                    )
                    raise ValueError(f"Sale blocked: '{med.medicine_name}' has expired on {med.expiry_date}.")

                if med.quantity < qty:
                    self.logger.log_poka_yoke(
                        "Transaction Rollback - Insufficient Stock",
                        f"Transaction aborted: '{med.medicine_name}' requested {qty}, available {med.quantity}."
                    )
                    raise ValueError(f"Insufficient stock for '{med.medicine_name}'. Available: {med.quantity}.")

                subtotal = round(med.price * qty, 2)
                total_amount += subtotal
                validated_items.append((med, qty, subtotal))

            total_amount = round(total_amount, 2)

            import uuid
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
            
            # 1. Insert Sales Header with store_id
            cursor.execute(
                "INSERT INTO sales (store_id, invoice_number, patient_name, patient_phone, patient_age, sale_date, total_amount, user_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (self.store_id, invoice_number, patient_name, patient_phone, patient_age, sale_date, total_amount, user_id)
            )
            sale_id = cursor.lastrowid

            # 2. Insert Sale Line Items and Perform Conditional Stock Deductions scoped to store_id
            for med, qty, subtotal in validated_items:
                cursor.execute(
                    "INSERT INTO sale_items (store_id, sale_id, medicine_id, quantity, price, subtotal) VALUES (?, ?, ?, ?, ?, ?)",
                    (self.store_id, sale_id, med.medicine_id, qty, med.price, subtotal)
                )

                # Conditional atomic stock deduction: WHERE quantity >= ? AND store_id = ?
                cursor.execute(
                    "UPDATE medicines SET quantity = quantity - ?, updated_at = CURRENT_TIMESTAMP "
                    "WHERE medicine_id = ? AND store_id = ? AND quantity >= ?",
                    (qty, med.medicine_id, self.store_id, qty)
                )

                if cursor.rowcount != 1:
                    raise ValueError(f"Stock deduction conflict for '{med.medicine_name}'. Available quantity changed.")

            # Commit Transaction
            conn.commit()
            self.logger.log_event(
                "SALES",
                f"Sale #{sale_id} completed by user_id {user_id} in store {self.store_id}. Total: ₹{total_amount:.2f} ({len(validated_items)} items)."
            )
            return True, f"Sale #{sale_id} completed successfully! Total: ₹{total_amount:.2f}", sale_id, invoice_number

        except Exception as e:
            # Atomic Rollback on any failure
            conn.rollback()
            err_msg = str(e)
            self.logger.log_poka_yoke("Transaction Rollback Executed", f"Sale transaction rolled back: {err_msg}")
            return False, f"Transaction Error: {err_msg}", None, None
        finally:
            conn.close()

    def get_recent_sales(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent sales history for the active store."""
        query = """
        SELECT s.sale_id, s.store_id, s.invoice_number, s.patient_name, s.patient_phone, s.patient_age,
               s.sale_date, s.total_amount, s.user_id, u.username,
               (SELECT COUNT(*) FROM sale_items si WHERE si.sale_id = s.sale_id AND (si.store_id = ? OR (si.store_id IS NULL AND ? = 'STORE-LEGACY-001'))) as items_count
        FROM sales s
        LEFT JOIN users u ON s.user_id = u.user_id
        WHERE (s.store_id = ? OR (s.store_id IS NULL AND ? = 'STORE-LEGACY-001'))
        ORDER BY s.sale_id DESC
        LIMIT ?
        """
        rows = self.db.fetch_all(query, (self.store_id, self.store_id, self.store_id, self.store_id, limit))
        return [dict(r) for r in rows]

    def get_sale_details(self, sale_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves sale details including line items for invoice display, strictly verified against store_id."""
        sale_row = self.db.fetch_one(
            "SELECT s.sale_id, s.store_id, s.invoice_number, s.patient_name, s.patient_phone, s.patient_age, "
            "s.sale_date, s.total_amount, s.user_id, u.username "
            "FROM sales s LEFT JOIN users u ON s.user_id = u.user_id "
            "WHERE s.sale_id = ? AND (s.store_id = ? OR (s.store_id IS NULL AND ? = 'STORE-LEGACY-001'))",
            (sale_id, self.store_id, self.store_id)
        )
        if not sale_row:
            return None

        items_rows = self.db.fetch_all(
            "SELECT si.item_id, si.store_id, si.sale_id, si.medicine_id, m.medicine_name, m.medicine_code, "
            "si.quantity, si.price, si.subtotal "
            "FROM sale_items si "
            "JOIN medicines m ON si.medicine_id = m.medicine_id "
            "WHERE si.sale_id = ? AND (si.store_id = ? OR (si.store_id IS NULL AND ? = 'STORE-LEGACY-001'))",
            (sale_id, self.store_id, self.store_id)
        )
        items = [dict(r) for r in items_rows]

        result = dict(sale_row)
        result["items"] = items
        return result
