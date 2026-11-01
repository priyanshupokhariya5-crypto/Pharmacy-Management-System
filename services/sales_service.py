"""
Sales Service for transaction billing, FEFO batch stock deduction, returns/refunds,
and cashier shift reconciliation.
Enforces Poka-Yoke error prevention rules:
  - Blocks expired, quarantined, recalled, and unverified batches
  - Mandates valid 10-digit Indian customer phone numbers
  - Records Cash, UPI, and Card payment methods with references
  - Guarantees atomic SQLite transaction behavior across sales, batches, and stock ledger
  - Enforces strict multi-store tenant isolation and role-based permissions
"""
import uuid
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any
from database.db import Database, get_db
from models.sale import Sale, SaleItem, SaleReturn, SaleReturnItem
from models.medicine import Medicine
from utils.logger import get_app_logger
from utils.validators import validate_indian_phone, calculate_bill_totals
from services.rbac import (
    require_permission,
    require_store_access,
    PERM_PROCESS_SALE,
    PERM_VIEW_SALES_HISTORY,
    PERM_MANAGE_INVENTORY,
)
from services.audit_service import AuditService


class SalesService:
    """Manages billing checkout transactions, FEFO stock deductions, returns, and cashier reconciliation."""

    def __init__(self, db: Optional[Database] = None, store_id: Optional[str] = None):
        self.db = db or get_db()
        self.store_id = store_id or "STORE-LEGACY-001"
        self.logger = get_app_logger()
        self.audit_service = AuditService(self.db)

    def _table_exists(self, table_name: str) -> bool:
        """Helper checking if a table exists in the database."""
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def _column_exists(self, table_name: str, column_name: str) -> bool:
        """Helper checking if a column exists in a given table."""
        if not self._table_exists(table_name):
            return False
        cols = [c["name"] for c in self.db.fetch_all(f"PRAGMA table_info({table_name})")]
        return column_name in cols

    def validate_cart_item(self, medicine_id: int, quantity: int) -> Tuple[bool, str, Optional[Medicine]]:
        """
        Validates if a medicine item can be sold within the active store.
        Checks existence, non-expired status, and sufficient stock.
        If batch inventory is active, validates against eligible unexpired batches.
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

        # 1. Check legacy medicine expiration
        if med.is_expired:
            self.logger.log_poka_yoke(
                "Expired Medicine Block",
                f"Blocked sale of expired medicine '{med.medicine_name}' (Expired: {med.expiry_date})"
            )
            return False, f"Sale blocked: '{med.medicine_name}' has expired on {med.expiry_date}.", med

        # 2. If batch inventory exists, check available eligible batches
        if self._table_exists("inventory_batches"):
            today_str = datetime.now().strftime("%Y-%m-%d")
            batch_count_row = self.db.fetch_one(
                "SELECT COUNT(*) as cnt FROM inventory_batches WHERE store_id = ? AND medicine_id = ?",
                (self.store_id, medicine_id)
            )
            has_batches = (batch_count_row["cnt"] if batch_count_row else 0) > 0
            if has_batches:
                batch_stock_row = self.db.fetch_one(
                    """
                    SELECT COALESCE(SUM(current_quantity), 0) as eligible_qty
                    FROM inventory_batches
                    WHERE store_id = ? AND medicine_id = ? AND status = 'Active'
                      AND verification_flag = 0 AND current_quantity > 0 AND expiry_date >= ?
                    """,
                    (self.store_id, medicine_id, today_str)
                )
                eligible_batch_qty = batch_stock_row["eligible_qty"] if batch_stock_row else 0
                if eligible_batch_qty < quantity:
                    return False, f"Insufficient stock: insufficient eligible stock. Available batch stock: {eligible_batch_qty}.", med

        # 3. Stock Check: Block Insufficient Quantity on medicine
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
        patient_name: str = "Walk-in Customer",
        patient_phone: str = "",
        patient_age: Optional[int] = None,
        discount_amount: float = 0.0,
        tax_rate: float = 0.0,
        payment_method: str = "Cash",
        payment_reference: Optional[str] = None,
        sale_date: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Tuple[bool, str, Optional[int], Optional[str]]:
        """
        Processes a complete sales checkout transaction atomically within the active store.
        Integrates:
          1. Mandatory 10-digit Indian customer phone validation
          2. Payment method (Cash, UPI, Card) and transaction reference
          3. Real FEFO batch deduction, allocating across batches by earliest expiry date
          4. Stock movement ledger tracking (SALE_DISPENSE, -delta)
          5. Sale batch allocations recording for full traceability
          6. Atomic SQLite transaction rollback on any failure
        """
        if acting_user is not None:
            require_permission(acting_user, PERM_PROCESS_SALE, "Processing sales billing")
            require_store_access(acting_user, self.store_id, "Processing sales billing")

        if not cart_items:
            self.logger.log_poka_yoke("Empty Checkout Attempt", "Blocked checkout attempt on an empty cart.")
            return False, "Cart is empty. Add medicines before confirming sale.", None, None

        # 1. Validate Customer Info & Mandatory Phone
        patient_name = (patient_name or "").strip() or "Walk-in Customer"

        is_phone_valid, phone_err, cleaned_phone = validate_indian_phone(patient_phone)
        if not is_phone_valid:
            self.logger.log_poka_yoke("Invalid Customer Phone", f"Phone validation failed: '{patient_phone}' - {phone_err}")
            return False, f"Validation Error: {phone_err}", None, None

        # 2. Validate Payment Method
        payment_method = (payment_method or "Cash").strip()
        if payment_method not in ("Cash", "UPI", "Card"):
            return False, "Invalid payment method. Must be Cash, UPI, or Card.", None, None

        payment_reference = (payment_reference or "").strip() if payment_reference else None

        now_time = datetime.now().strftime("%H:%M:%S")
        if sale_date and sale_date.strip():
            s_date = sale_date.strip().split()[0]
            sale_date = f"{s_date} {now_time}"
            today_date = s_date
        else:
            sale_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today_date = datetime.now().strftime("%Y-%m-%d")

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Verify acting user foreign key exists in users table
            valid_user_id = None
            if user_id:
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if cursor.fetchone():
                    valid_user_id = user_id

            # 3. Calculate Base Subtotal and Validate Each Cart Item
            validated_items: List[Tuple[Medicine, int, float]] = []
            raw_subtotal = 0.0

            for med_id, qty in cart_items:
                if qty <= 0:
                    raise ValueError(f"Quantity for medicine ID {med_id} must be greater than zero.")

                cursor.execute(
                    "SELECT medicine_id, store_id, medicine_code, medicine_name, category, manufacturer, "
                    "batch_no, price, quantity, expiry_date, created_at, updated_at "
                    "FROM medicines WHERE medicine_id = ? AND store_id = ?",
                    (med_id, self.store_id)
                )
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Medicine ID {med_id} no longer exists or does not belong to store '{self.store_id}'.")

                med = Medicine.from_row(row)

                if med.is_expired:
                    self.logger.log_poka_yoke(
                        "Transaction Rollback - Expired Medicine",
                        f"Transaction aborted: '{med.medicine_name}' is expired ({med.expiry_date})."
                    )
                    raise ValueError(f"Sale blocked: '{med.medicine_name}' has expired on {med.expiry_date}.")

                line_subtotal = round(med.price * qty, 2)
                raw_subtotal += line_subtotal
                validated_items.append((med, qty, line_subtotal))

            # 4. Compute Financials
            totals = calculate_bill_totals(
                subtotal=raw_subtotal,
                discount_amount=discount_amount,
                tax_rate=tax_rate,
                enable_rounding=True
            )
            grand_total = totals["grand_total"]

            # 5. Generate Invoice Number
            invoice_number = f"INV-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"

            # 6. Insert Sales Header
            has_extended_cols = self._column_exists("sales", "subtotal") and self._column_exists("sales", "payment_method")
            if has_extended_cols:
                cursor.execute(
                    """
                    INSERT INTO sales (
                        store_id, invoice_number, patient_name, patient_phone, patient_age,
                        sale_date, subtotal, discount_amount, tax_amount, rounding_amount,
                        total_amount, payment_method, payment_reference, status, user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'COMPLETED', ?)
                    """,
                    (
                        self.store_id, invoice_number, patient_name, cleaned_phone, patient_age,
                        sale_date, totals["subtotal"], totals["discount_amount"], totals["tax_amount"],
                        totals["rounding_amount"], grand_total, payment_method, payment_reference, valid_user_id
                    )
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO sales (
                        store_id, invoice_number, patient_name, patient_phone, patient_age,
                        sale_date, total_amount, user_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (self.store_id, invoice_number, patient_name, cleaned_phone, patient_age, sale_date, grand_total, valid_user_id)
                )
            sale_id = cursor.lastrowid

            # 7. Check if Normalized Batch Inventory Exists
            use_batches = self._table_exists("inventory_batches")
            has_allocations_table = self._table_exists("sale_batch_allocations")
            has_movements_table = self._table_exists("stock_movements")

            # 8. Insert Line Items and Perform Atomic Stock Deductions (FEFO)
            for med, qty, line_subtotal in validated_items:
                cursor.execute(
                    "INSERT INTO sale_items (store_id, sale_id, medicine_id, quantity, price, subtotal) VALUES (?, ?, ?, ?, ?, ?)",
                    (self.store_id, sale_id, med.medicine_id, qty, med.price, line_subtotal)
                )
                sale_item_id = cursor.lastrowid

                # Real FEFO Batch Allocation and Deduction
                if use_batches:
                    cursor.execute(
                        "SELECT COUNT(*) FROM inventory_batches WHERE store_id = ? AND medicine_id = ?",
                        (self.store_id, med.medicine_id)
                    )
                    med_has_batches = cursor.fetchone()[0] > 0

                    if med_has_batches:
                        cursor.execute(
                            """
                            SELECT batch_id, batch_number, expiry_date, current_quantity, selling_price, created_at
                            FROM inventory_batches
                            WHERE store_id = ? AND medicine_id = ? AND status = 'Active'
                              AND verification_flag = 0 AND current_quantity > 0 AND expiry_date >= ?
                            ORDER BY expiry_date ASC, created_at ASC, batch_id ASC
                            """,
                            (self.store_id, med.medicine_id, today_date)
                        )
                        eligible_batches = cursor.fetchall()
                        total_available_in_batches = sum(b[3] for b in eligible_batches)

                        if total_available_in_batches < qty:
                            raise ValueError(
                                f"Insufficient stock for '{med.medicine_name}': "
                                f"Requested: {qty}, Available eligible batch stock: {total_available_in_batches}."
                            )

                        remaining_to_allocate = qty
                        for b_row in eligible_batches:
                            if remaining_to_allocate <= 0:
                                break
                            b_id, b_num, b_exp, b_curr_qty, b_price, _ = b_row
                            deduct_qty = min(remaining_to_allocate, b_curr_qty)
                            deduct_subtotal = round(deduct_qty * med.price, 2)

                            # Deduct from batch
                            cursor.execute(
                                """
                                UPDATE inventory_batches
                                SET current_quantity = current_quantity - ?, updated_at = CURRENT_TIMESTAMP
                                WHERE batch_id = ? AND current_quantity >= ?
                                """,
                                (deduct_qty, b_id, deduct_qty)
                            )
                            if cursor.rowcount != 1:
                                raise ValueError(f"Concurrent inventory conflict: Batch {b_num} quantity changed.")

                            # Record sale_batch_allocations
                            if has_allocations_table:
                                cursor.execute(
                                    """
                                    INSERT INTO sale_batch_allocations (
                                        sale_item_id, batch_id, quantity, unit_price, subtotal
                                    ) VALUES (?, ?, ?, ?, ?)
                                    """,
                                    (sale_item_id, b_id, deduct_qty, med.price, deduct_subtotal)
                                )

                            # Record stock movement ledger entry (-delta)
                            if has_movements_table:
                                cursor.execute(
                                    """
                                    INSERT INTO stock_movements (
                                        store_id, medicine_id, batch_id, movement_type,
                                        quantity_delta, reference_type, reference_id, notes, created_by
                                    ) VALUES (?, ?, ?, 'SALE_DISPENSE', ?, 'SALE', ?, ?, ?)
                                    """,
                                    (
                                        self.store_id, med.medicine_id, b_id,
                                        -deduct_qty, invoice_number, f"Dispensed on invoice {invoice_number}", valid_user_id
                                    )
                                )

                            remaining_to_allocate -= deduct_qty
                    else:
                        if med.quantity < qty:
                            raise ValueError(f"Insufficient stock for '{med.medicine_name}'. Available: {med.quantity}, Requested: {qty}")

                # Sync medicines.quantity field (-delta or batch sync)
                if use_batches and med_has_batches:
                    cursor.execute(
                        """
                        UPDATE medicines
                        SET quantity = (
                            SELECT COALESCE(SUM(current_quantity), 0)
                            FROM inventory_batches
                            WHERE store_id = ? AND medicine_id = ? AND status = 'Active'
                        ), updated_at = CURRENT_TIMESTAMP
                        WHERE medicine_id = ? AND store_id = ?
                        """,
                        (self.store_id, med.medicine_id, med.medicine_id, self.store_id)
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE medicines
                        SET quantity = MAX(0, quantity - ?), updated_at = CURRENT_TIMESTAMP
                        WHERE medicine_id = ? AND store_id = ? AND quantity >= ?
                        """,
                        (qty, med.medicine_id, self.store_id, qty)
                    )
                    if cursor.rowcount != 1:
                        raise ValueError(f"Stock deduction conflict for '{med.medicine_name}'. Available quantity changed.")

            # 9. Commit Transaction
            conn.commit()

            # 10. Audit Log
            self.audit_service.log_event(
                store_id=self.store_id,
                user_id=valid_user_id,
                action="SALE_CHECKOUT",
                entity_type="sale",
                entity_id=str(sale_id),
                details=f"Invoice {invoice_number}, Total: ₹{grand_total:.2f}, Payment: {payment_method}, Customer: {patient_name} ({cleaned_phone})"
            )

            self.logger.log_event(
                "SALES",
                f"Sale #{sale_id} completed by user_id {user_id} in store {self.store_id}. Total: ₹{grand_total:.2f} ({len(validated_items)} items)."
            )
            return True, f"Sale #{sale_id} completed successfully! Invoice: {invoice_number}, Total: ₹{grand_total:.2f}", sale_id, invoice_number

        except Exception as e:
            # Atomic Rollback on any failure
            conn.rollback()
            err_msg = str(e)
            self.logger.log_poka_yoke("Transaction Rollback Executed", f"Sale transaction rolled back: {err_msg}")
            return False, f"Transaction Error: {err_msg}", None, None
        finally:
            conn.close()

    def process_sale_return(
        self,
        sale_id: int,
        return_items: List[Dict[str, Any]],
        refund_method: str = "Cash",
        reason: str = "Customer Return",
        acting_user: Optional[Any] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Processes an authorized sale return and refund transaction atomically.
        Requirements:
          - Validates return items against original sale and past returns
          - Prevents returning more than the originally sold quantity
          - Evaluates restock eligibility (expired stock is NEVER returned to sellable inventory)
          - Writes stock movements (+delta, CUSTOMER_RETURN) for restocked items
          - Updates sale status to PARTIALLY_REFUNDED or REFUNDED
          - Preserves full audit trail
        """
        if acting_user is not None:
            require_permission(acting_user, PERM_PROCESS_SALE, "Processing sale returns")
            require_store_access(acting_user, self.store_id, "Processing sale returns")

        if not return_items:
            return False, "No items specified for return.", None

        if not self._table_exists("sale_returns"):
            return False, "Sale returns table is not available in current database.", None

        refund_method = (refund_method or "Cash").strip()
        if refund_method not in ("Cash", "UPI", "Card", "Original"):
            return False, "Invalid refund method.", None

        acting_user_id = getattr(acting_user, "user_id", None) if acting_user else None

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # Verify valid user
            valid_user_id = None
            if acting_user_id:
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (acting_user_id,))
                if cursor.fetchone():
                    valid_user_id = acting_user_id

            # 1. Fetch original sale record
            cursor.execute(
                "SELECT sale_id, store_id, invoice_number, total_amount, status FROM sales WHERE sale_id = ? AND store_id = ?",
                (sale_id, self.store_id)
            )
            sale_row = cursor.fetchone()
            if not sale_row:
                return False, f"Sale ID #{sale_id} not found in store '{self.store_id}'.", None

            orig_invoice = sale_row[2]

            # 2. Fetch original sale items and past returned quantities
            cursor.execute(
                """
                SELECT si.item_id, si.medicine_id, m.medicine_name, si.quantity, si.price,
                       COALESCE(
                           (SELECT SUM(sri.quantity) FROM sale_return_items sri WHERE sri.sale_item_id = si.item_id),
                           0
                       ) as already_returned_qty
                FROM sale_items si
                JOIN medicines m ON si.medicine_id = m.medicine_id
                WHERE si.sale_id = ?
                """,
                (sale_id,)
            )
            orig_items_raw = cursor.fetchall()
            orig_items_map = {r[0]: {"medicine_id": r[1], "medicine_name": r[2], "sold_qty": r[3], "price": r[4], "already_returned": r[5]} for r in orig_items_raw}

            # 3. Validate each item to return
            validated_return_items: List[Dict[str, Any]] = []
            total_refund = 0.0
            today_date = datetime.now().strftime("%Y-%m-%d")

            for ret in return_items:
                sale_item_id = ret.get("sale_item_id")
                qty = int(ret.get("quantity", 0))
                cond = ret.get("restock_condition", "SELLABLE").upper()

                if sale_item_id not in orig_items_map:
                    raise ValueError(f"Sale item ID {sale_item_id} does not belong to sale #{sale_id}.")

                item_info = orig_items_map[sale_item_id]
                max_returnable = item_info["sold_qty"] - item_info["already_returned"]

                if qty <= 0:
                    raise ValueError(f"Return quantity for '{item_info['medicine_name']}' must be greater than zero.")

                if qty > max_returnable:
                    raise ValueError(
                        f"Cannot return {qty} units of '{item_info['medicine_name']}'. "
                        f"Sold: {item_info['sold_qty']}, Already Returned: {item_info['already_returned']}, Max Returnable: {max_returnable}."
                    )

                refund_subtotal = round(qty * item_info["price"], 2)
                total_refund += refund_subtotal

                # Find allocated batch if available
                batch_id = None
                batch_exp = None
                if self._table_exists("sale_batch_allocations"):
                    cursor.execute(
                        """
                        SELECT sba.batch_id, ib.expiry_date
                        FROM sale_batch_allocations sba
                        LEFT JOIN inventory_batches ib ON sba.batch_id = ib.batch_id
                        WHERE sba.sale_item_id = ?
                        ORDER BY sba.allocation_id ASC LIMIT 1
                        """,
                        (sale_item_id,)
                    )
                    alloc_row = cursor.fetchone()
                    if alloc_row:
                        batch_id = alloc_row[0]
                        batch_exp = alloc_row[1]

                # Safety check: expired stock can NEVER be restocked to sellable inventory
                can_restock = 1
                if cond != "SELLABLE":
                    can_restock = 0
                elif batch_exp and batch_exp < today_date:
                    can_restock = 0
                    cond = "EXPIRED"

                validated_return_items.append({
                    "sale_item_id": sale_item_id,
                    "medicine_id": item_info["medicine_id"],
                    "medicine_name": item_info["medicine_name"],
                    "quantity": qty,
                    "unit_price": item_info["price"],
                    "refund_amount": refund_subtotal,
                    "batch_id": batch_id,
                    "restocked": can_restock,
                    "restock_condition": cond
                })

            total_refund = round(total_refund, 2)
            return_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 4. Insert sale_returns header
            cursor.execute(
                """
                INSERT INTO sale_returns (
                    store_id, sale_id, invoice_number, return_date, total_refund,
                    refund_method, reason, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (self.store_id, sale_id, orig_invoice, return_date, total_refund, refund_method, reason, valid_user_id)
            )
            return_id = cursor.lastrowid

            has_movements = self._table_exists("stock_movements")
            has_batches = self._table_exists("inventory_batches")

            # 5. Insert sale_return_items and Restock if eligible
            for v_item in validated_return_items:
                cursor.execute(
                    """
                    INSERT INTO sale_return_items (
                        return_id, sale_item_id, medicine_id, batch_id, quantity,
                        unit_price, refund_amount, restocked, restock_condition
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        return_id, v_item["sale_item_id"], v_item["medicine_id"], v_item["batch_id"],
                        v_item["quantity"], v_item["unit_price"], v_item["refund_amount"],
                        v_item["restocked"], v_item["restock_condition"]
                    )
                )

                if v_item["restocked"] == 1:
                    # Restock batch
                    if has_batches and v_item["batch_id"]:
                        cursor.execute(
                            """
                            UPDATE inventory_batches
                            SET current_quantity = current_quantity + ?, updated_at = CURRENT_TIMESTAMP
                            WHERE batch_id = ?
                            """,
                            (v_item["quantity"], v_item["batch_id"])
                        )

                    # Restock medicines table
                    cursor.execute(
                        """
                        UPDATE medicines
                        SET quantity = quantity + ?, updated_at = CURRENT_TIMESTAMP
                        WHERE medicine_id = ? AND store_id = ?
                        """,
                        (v_item["quantity"], v_item["medicine_id"], self.store_id)
                    )

                    # Write stock movement (+delta)
                    if has_movements:
                        cursor.execute(
                            """
                            INSERT INTO stock_movements (
                                store_id, medicine_id, batch_id, movement_type,
                                quantity_delta, reference_type, reference_id, notes, created_by
                            ) VALUES (?, ?, ?, 'CUSTOMER_RETURN', ?, 'RETURN', ?, ?, ?)
                            """,
                            (
                                self.store_id, v_item["medicine_id"], v_item["batch_id"],
                                v_item["quantity"], orig_invoice, f"Customer return #{return_id} on invoice {orig_invoice}", valid_user_id
                            )
                        )

            # 6. Check if sale is fully or partially refunded
            # Re-sum all returned quantities
            cursor.execute(
                """
                SELECT SUM(si.quantity),
                       COALESCE(
                           (SELECT SUM(sri.quantity) FROM sale_return_items sri
                            JOIN sale_returns sr ON sri.return_id = sr.return_id
                            WHERE sr.sale_id = ?),
                           0
                       )
                FROM sale_items si WHERE si.sale_id = ?
                """,
                (sale_id, sale_id)
            )
            agg_row = cursor.fetchone()
            total_sold = agg_row[0] or 0
            total_ret = agg_row[1] or 0

            new_status = "REFUNDED" if total_ret >= total_sold else "PARTIALLY_REFUNDED"
            if self._column_exists("sales", "status"):
                cursor.execute("UPDATE sales SET status = ? WHERE sale_id = ?", (new_status, sale_id))

            conn.commit()

            # 7. Audit log
            self.audit_service.log_event(
                store_id=self.store_id,
                user_id=valid_user_id,
                action="SALE_RETURN",
                entity_type="sale_return",
                entity_id=str(return_id),
                details=f"Return #{return_id} on invoice {orig_invoice}. Refund: ₹{total_refund:.2f} ({refund_method}). Status: {new_status}"
            )

            return True, f"Return #{return_id} processed successfully. Refund: ₹{total_refund:.2f}", return_id

        except Exception as e:
            conn.rollback()
            err_msg = str(e)
            self.logger.log_poka_yoke("Return Transaction Failed", f"Return failed: {err_msg}")
            return False, f"Return Error: {err_msg}", None
        finally:
            conn.close()

    # Alias for process_sale_return
    process_return = process_sale_return

    def get_recent_sales(self, limit: int = 50, acting_user: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Retrieves recent sales history for the active store."""
        if acting_user is not None:
            require_store_access(acting_user, self.store_id, "Viewing sales history")

        has_status = self._column_exists("sales", "status")
        has_pm = self._column_exists("sales", "payment_method")

        status_col = "s.status" if has_status else "'COMPLETED' as status"
        pm_col = "s.payment_method" if has_pm else "'Cash' as payment_method"

        query = f"""
        SELECT s.sale_id, s.store_id, s.invoice_number, s.patient_name, s.patient_phone, s.patient_age,
               s.sale_date, s.total_amount, {pm_col}, {status_col}, s.user_id, u.username,
               (SELECT COUNT(*) FROM sale_items si WHERE si.sale_id = s.sale_id AND (si.store_id = ? OR (si.store_id IS NULL AND ? = 'STORE-LEGACY-001'))) as items_count
        FROM sales s
        LEFT JOIN users u ON s.user_id = u.user_id
        WHERE (s.store_id = ? OR (s.store_id IS NULL AND ? = 'STORE-LEGACY-001'))
        ORDER BY s.sale_id DESC
        LIMIT ?
        """
        rows = self.db.fetch_all(query, (self.store_id, self.store_id, self.store_id, self.store_id, limit))
        return [dict(r) for r in rows]

    def get_sale_details(self, sale_id: int, acting_user: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Retrieves sale details including line items and batch allocations for receipt display."""
        if acting_user is not None:
            require_store_access(acting_user, self.store_id, "Viewing sale receipt details")

        has_pm = self._column_exists("sales", "payment_method")
        has_pref = self._column_exists("sales", "payment_reference")
        has_sub = self._column_exists("sales", "subtotal")
        has_disc = self._column_exists("sales", "discount_amount")
        has_tax = self._column_exists("sales", "tax_amount")
        has_round = self._column_exists("sales", "rounding_amount")
        has_stat = self._column_exists("sales", "status")

        pm_expr = "s.payment_method" if has_pm else "'Cash' as payment_method"
        pref_expr = "s.payment_reference" if has_pref else "NULL as payment_reference"
        sub_expr = "s.subtotal" if has_sub else "s.total_amount as subtotal"
        disc_expr = "s.discount_amount" if has_disc else "0.0 as discount_amount"
        tax_expr = "s.tax_amount" if has_tax else "0.0 as tax_amount"
        round_expr = "s.rounding_amount" if has_round else "0.0 as rounding_amount"
        stat_expr = "s.status" if has_stat else "'COMPLETED' as status"

        sale_row = self.db.fetch_one(
            f"""
            SELECT s.sale_id, s.store_id, s.invoice_number, s.patient_name, s.patient_phone, s.patient_age,
                   s.sale_date, {sub_expr}, {disc_expr}, {tax_expr}, {round_expr}, s.total_amount,
                   {pm_expr}, {pref_expr}, {stat_expr}, s.user_id, u.username
            FROM sales s LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.sale_id = ? AND (s.store_id = ? OR (s.store_id IS NULL AND ? = 'STORE-LEGACY-001'))
            """,
            (sale_id, self.store_id, self.store_id)
        )
        if not sale_row:
            return None

        # Fetch items with batch allocations if table exists
        has_allocations = self._table_exists("sale_batch_allocations")
        if has_allocations:
            items_query = """
            SELECT si.item_id, si.store_id, si.sale_id, si.medicine_id, m.medicine_name, m.medicine_code,
                   si.quantity, si.price, si.subtotal,
                   (SELECT GROUP_CONCAT(ib.batch_number || ' (Exp:' || ib.expiry_date || ')', ', ')
                    FROM sale_batch_allocations sba
                    JOIN inventory_batches ib ON sba.batch_id = ib.batch_id
                    WHERE sba.sale_item_id = si.item_id) as batch_details
            FROM sale_items si
            JOIN medicines m ON si.medicine_id = m.medicine_id
            WHERE si.sale_id = ? AND (si.store_id = ? OR (si.store_id IS NULL AND ? = 'STORE-LEGACY-001'))
            ORDER BY si.item_id ASC
            """
        else:
            items_query = """
            SELECT si.item_id, si.store_id, si.sale_id, si.medicine_id, m.medicine_name, m.medicine_code,
                   si.quantity, si.price, si.subtotal, m.batch_no as batch_details
            FROM sale_items si
            JOIN medicines m ON si.medicine_id = m.medicine_id
            WHERE si.sale_id = ? AND (si.store_id = ? OR (si.store_id IS NULL AND ? = 'STORE-LEGACY-001'))
            ORDER BY si.item_id ASC
            """

        items_rows = self.db.fetch_all(items_query, (sale_id, self.store_id, self.store_id))
        result = dict(sale_row)
        result["items"] = [dict(r) for r in items_rows]
        return result

    def get_cashier_summary(self, cashier_user_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Calculates shift sales and payment method reconciliation metrics for Cashier dashboard.
        Scoped to active store and optionally the current cashier user.
        """
        today_date = datetime.now().strftime("%Y-%m-%d")
        params: List[Any] = [self.store_id, today_date]
        user_filter = ""
        if cashier_user_id is not None:
            user_filter = "AND s.user_id = ?"
            params.append(cashier_user_id)

        has_pm = self._column_exists("sales", "payment_method")
        has_disc = self._column_exists("sales", "discount_amount")

        # 1. Total bill count and gross sales
        base_query = f"""
        SELECT COUNT(*) as bills_count,
               COALESCE(SUM(s.total_amount), 0) as gross_sales
        FROM sales s
        WHERE s.store_id = ? AND substr(s.sale_date, 1, 10) = ? {user_filter}
        """
        row = self.db.fetch_one(base_query, tuple(params))
        bills_count = row["bills_count"] if row else 0
        gross_sales = float(row["gross_sales"]) if row else 0.0

        # 2. Payment method breakdown
        cash_coll = 0.0
        upi_coll = 0.0
        card_coll = 0.0
        total_discount = 0.0

        if has_pm:
            pm_query = f"""
            SELECT s.payment_method, COALESCE(SUM(s.total_amount), 0) as amount
            FROM sales s
            WHERE s.store_id = ? AND substr(s.sale_date, 1, 10) = ? {user_filter}
            GROUP BY s.payment_method
            """
            for pm_r in self.db.fetch_all(pm_query, tuple(params)):
                pm = pm_r["payment_method"]
                amt = float(pm_r["amount"])
                if pm == "Cash":
                    cash_coll += amt
                elif pm == "UPI":
                    upi_coll += amt
                elif pm == "Card":
                    card_coll += amt
        else:
            cash_coll = gross_sales

        if has_disc:
            disc_row = self.db.fetch_one(
                f"SELECT COALESCE(SUM(s.discount_amount), 0) as tot_disc FROM sales s WHERE s.store_id = ? AND substr(s.sale_date, 1, 10) = ? {user_filter}",
                tuple(params)
            )
            total_discount = float(disc_row["tot_disc"]) if disc_row else 0.0

        # 3. Refunds today
        total_refunds = 0.0
        if self._table_exists("sale_returns"):
            ret_params: List[Any] = [self.store_id, today_date]
            ret_user_filter = ""
            if cashier_user_id is not None:
                ret_user_filter = "AND sr.created_by = ?"
                ret_params.append(cashier_user_id)

            ret_row = self.db.fetch_one(
                f"""
                SELECT COALESCE(SUM(sr.total_refund), 0) as tot_ref
                FROM sale_returns sr
                WHERE sr.store_id = ? AND substr(sr.return_date, 1, 10) = ? {ret_user_filter}
                """,
                tuple(ret_params)
            )
            total_refunds = float(ret_row["tot_ref"]) if ret_row else 0.0

        net_settled_sales = round(gross_sales - total_refunds, 2)

        # 4. Recent transactions today
        has_status = self._column_exists("sales", "status")
        stat_expr = "s.status" if has_status else "'COMPLETED' as status"
        pm_expr = "s.payment_method" if has_pm else "'Cash' as payment_method"

        tx_query = f"""
        SELECT s.sale_id, s.invoice_number, s.patient_name, s.patient_phone, s.sale_date,
               s.total_amount, {pm_expr}, {stat_expr},
               (SELECT COUNT(*) FROM sale_items si WHERE si.sale_id = s.sale_id) as items_count
        FROM sales s
        WHERE s.store_id = ? AND substr(s.sale_date, 1, 10) = ? {user_filter}
        ORDER BY s.sale_id DESC
        LIMIT 10
        """
        tx_rows = self.db.fetch_all(tx_query, tuple(params))
        recent_txs = [
            {
                "sale_id": dict(r)["sale_id"],
                "invoice_number": dict(r)["invoice_number"] or f"INV-{dict(r)['sale_id']}",
                "patient_name": dict(r)["patient_name"] or "Walk-in Customer",
                "patient_phone": dict(r).get("patient_phone", ""),
                "sale_date": dict(r)["sale_date"],
                "items_count": dict(r)["items_count"] or 0,
                "total_amount": round(dict(r)["total_amount"], 2),
                "payment_method": dict(r).get("payment_method", "Cash"),
                "status": dict(r).get("status", "COMPLETED")
            }
            for r in tx_rows
        ]

        return {
            "store_id": self.store_id,
            "today_date": today_date,
            "bills_count": bills_count,
            "today_bills_count": bills_count,
            "gross_sales": round(gross_sales, 2),
            "today_sales_total": round(gross_sales, 2),
            "cash_collections": round(cash_coll, 2),
            "cash_total": round(cash_coll, 2),
            "upi_collections": round(upi_coll, 2),
            "upi_total": round(upi_coll, 2),
            "card_collections": round(card_coll, 2),
            "card_total": round(card_coll, 2),
            "total_discounts": round(total_discount, 2),
            "total_refunds": round(total_refunds, 2),
            "net_settled_sales": net_settled_sales,
            "net_sales": net_settled_sales,
            "recent_transactions": recent_txs
        }

    def get_sale_returns(self, limit: int = 50, acting_user: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Retrieves recent returns for the active store."""
        if acting_user is not None:
            require_store_access(acting_user, self.store_id, "Viewing returns history")

        if not self._table_exists("sale_returns"):
            return []

        query = """
        SELECT sr.return_id, sr.store_id, sr.sale_id, sr.invoice_number, sr.return_date,
               sr.total_refund, sr.refund_method, sr.reason, sr.created_by, u.username,
               (SELECT COUNT(*) FROM sale_return_items sri WHERE sri.return_id = sr.return_id) as items_count
        FROM sale_returns sr
        LEFT JOIN users u ON sr.created_by = u.user_id
        WHERE sr.store_id = ?
        ORDER BY sr.return_id DESC
        LIMIT ?
        """
        rows = self.db.fetch_all(query, (self.store_id, limit))
        return [dict(r) for r in rows]

    def get_return_details(self, return_id: int, acting_user: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """Retrieves details of a specific return including line items."""
        if acting_user is not None:
            require_store_access(acting_user, self.store_id, "Viewing return details")

        if not self._table_exists("sale_returns"):
            return None

        ret_row = self.db.fetch_one(
            """
            SELECT sr.*, u.username
            FROM sale_returns sr
            LEFT JOIN users u ON sr.created_by = u.user_id
            WHERE sr.return_id = ? AND sr.store_id = ?
            """,
            (return_id, self.store_id)
        )
        if not ret_row:
            return None

        items_rows = self.db.fetch_all(
            """
            SELECT sri.*, m.medicine_name, m.medicine_code, ib.batch_number
            FROM sale_return_items sri
            JOIN medicines m ON sri.medicine_id = m.medicine_id
            LEFT JOIN inventory_batches ib ON sri.batch_id = ib.batch_id
            WHERE sri.return_id = ?
            ORDER BY sri.return_item_id ASC
            """,
            (return_id,)
        )
        res = dict(ret_row)
        res["items"] = [dict(r) for r in items_rows]
        return res
