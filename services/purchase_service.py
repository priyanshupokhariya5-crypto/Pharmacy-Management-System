"""
Purchase and Goods Receiving Service for Pharmacy Management System.
Handles purchase order creation, goods receipt workflow, manufacturer batch recording,
atomic stock movements, shelf allocation enforcement, and duplicate-receipt prevention.
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from database.db import Database
from models.purchase import Purchase, PurchaseItem
from services.rbac import (
    PERM_MANAGE_PURCHASES,
    PERM_MANAGE_INVENTORY,
    require_permission,
    require_store_access
)
from services.shelf_service import ShelfService


class PurchaseService:
    """Service handling supplier procurement and batch goods receiving."""

    def __init__(self, db: Database):
        self.db = db
        self.shelf_service = ShelfService(db)

    # -----------------------------------------------------------------------
    # 1. Purchase Creation & Management
    # -----------------------------------------------------------------------

    def create_purchase(
        self,
        store_id: str,
        supplier_id: int,
        invoice_number: str,
        purchase_date: str,
        items: List[Dict[str, Any]],
        total_amount: Optional[float] = None,
        payment_status: str = "PAID",
        status: str = "DRAFT",
        notes: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> int:
        """
        Creates a purchase record with items.
        Requires PERM_MANAGE_PURCHASES permission and store tenant match.
        """
        require_permission(acting_user, PERM_MANAGE_PURCHASES, "Creating a purchase order")
        require_store_access(acting_user, store_id, "Creating a purchase order in store")

        if not store_id or not str(store_id).strip():
            raise ValueError("Store ID is required.")
        if not supplier_id or int(supplier_id) <= 0:
            raise ValueError("Valid Supplier ID is required.")
        if not invoice_number or not str(invoice_number).strip():
            raise ValueError("Purchase invoice number is required.")
        if not items:
            raise ValueError("Purchase must contain at least one item.")

        # 1. Verify supplier belongs to this store and is active
        supplier_row = self.db.fetch_one(
            "SELECT supplier_id, is_active FROM suppliers WHERE supplier_id = ? AND store_id = ?",
            (supplier_id, store_id)
        )
        if not supplier_row:
            raise ValueError(f"Supplier ID {supplier_id} not found in store '{store_id}'.")
        if not supplier_row["is_active"]:
            raise ValueError(
                f"Supplier ID {supplier_id} is deactivated. Cannot create purchases for inactive suppliers."
            )

        # 2. Verify invoice_number is unique within store
        clean_invoice = invoice_number.strip().upper()
        existing_inv = self.db.fetch_one(
            "SELECT purchase_id FROM purchases WHERE store_id = ? AND invoice_number = ?",
            (store_id, clean_invoice)
        )
        if existing_inv:
            raise ValueError(
                f"Purchase with invoice number '{clean_invoice}' already exists in store '{store_id}'."
            )

        # 3. Validate purchase date format
        try:
            datetime.strptime(str(purchase_date).strip(), "%Y-%m-%d")
        except ValueError:
            raise ValueError("Purchase date must be in YYYY-MM-DD format.")

        # 4. Validate items and calculate subtotal
        computed_total = 0.0
        validated_items = []
        for idx, item in enumerate(items, start=1):
            med_id = item.get("medicine_id")
            if not med_id or int(med_id) <= 0:
                raise ValueError(f"Item #{idx} missing valid medicine_id.")

            # Verify medicine belongs to this store
            med_row = self.db.fetch_one(
                "SELECT medicine_id, medicine_name FROM medicines WHERE medicine_id = ? AND store_id = ?",
                (med_id, store_id)
            )
            if not med_row:
                raise ValueError(f"Medicine ID {med_id} not found in store '{store_id}'.")

            qty = int(item.get("quantity", 0))
            if qty <= 0:
                raise ValueError(f"Item #{idx} ({med_row['medicine_name']}) quantity must be greater than zero.")

            unit_cost = float(item.get("unit_cost", 0.0))
            if unit_cost < 0:
                raise ValueError(f"Item #{idx} unit cost cannot be negative.")

            subtotal = float(item.get("subtotal", round(qty * unit_cost, 2)))
            computed_total += subtotal

            validated_items.append({
                "medicine_id": med_id,
                "quantity": qty,
                "unit_cost": unit_cost,
                "subtotal": subtotal,
                "batch_id": item.get("batch_id")
            })

        final_total = total_amount if total_amount is not None else round(computed_total, 2)
        if final_total < 0:
            raise ValueError("Total purchase amount cannot be negative.")

        user_id = getattr(acting_user, "user_id", None) if acting_user else None
        if user_id is not None:
            u_exists = self.db.fetch_one("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not u_exists:
                user_id = None

        received_by_val = user_id if status == "RECEIVED" else None

        # 5. Insert purchase and purchase items transactionally
        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO purchases (
                    store_id, supplier_id, invoice_number, purchase_date,
                    total_amount, payment_status, status, received_by, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    store_id,
                    supplier_id,
                    clean_invoice,
                    purchase_date,
                    final_total,
                    payment_status,
                    status,
                    received_by_val,
                    notes
                )
            )
            purchase_id = cursor.lastrowid

            for it in validated_items:
                cursor.execute(
                    """
                    INSERT INTO purchase_items (
                        purchase_id, medicine_id, batch_id, quantity, unit_cost, subtotal
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        purchase_id,
                        it["medicine_id"],
                        it["batch_id"],
                        it["quantity"],
                        it["unit_cost"],
                        it["subtotal"]
                    )
                )

            conn.commit()
            return purchase_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def _table_exists(self, table_name: str) -> bool:
        """Helper checking if a table exists in the database."""
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def get_purchase_by_id(
        self,
        purchase_id: int,
        store_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Optional[Purchase]:
        """Fetches purchase details with all items, enforcing store isolation."""
        if not self._table_exists("purchases"):
            return None

        if acting_user and not store_id:
            store_id = getattr(acting_user, "store_id", None)

        query = """
        SELECT p.*, s.supplier_name
        FROM purchases p
        JOIN suppliers s ON p.supplier_id = s.supplier_id
        WHERE p.purchase_id = ?
        """
        params: List[Any] = [purchase_id]
        if store_id:
            require_store_access(acting_user, store_id, "Viewing purchase details")
            query += " AND p.store_id = ?"
            params.append(store_id)

        row = self.db.fetch_one(query, params)
        if not row:
            return None

        purchase = Purchase.from_row(row)

        # Load purchase items
        items_query = """
        SELECT pi.*, m.medicine_name, b.batch_number
        FROM purchase_items pi
        JOIN medicines m ON pi.medicine_id = m.medicine_id
        LEFT JOIN inventory_batches b ON pi.batch_id = b.batch_id
        WHERE pi.purchase_id = ?
        ORDER BY pi.item_id ASC
        """
        item_rows = self.db.fetch_all(items_query, (purchase_id,))
        purchase.items = [PurchaseItem.from_row(ir) for ir in item_rows]
        return purchase

    def get_purchases(
        self,
        store_id: str,
        status: Optional[str] = None,
        limit: int = 50,
        acting_user: Optional[Any] = None
    ) -> List[Purchase]:
        """Returns recent purchases for store_id."""
        if not self._table_exists("purchases"):
            return []

        require_store_access(acting_user, store_id, "Listing purchases")

        query = """
        SELECT p.*, s.supplier_name
        FROM purchases p
        JOIN suppliers s ON p.supplier_id = s.supplier_id
        WHERE p.store_id = ?
        """
        params: List[Any] = [store_id]
        if status:
            query += " AND p.status = ?"
            params.append(status)

        query += " ORDER BY p.purchase_date DESC, p.purchase_id DESC LIMIT ?"
        params.append(limit)

        rows = self.db.fetch_all(query, params)
        return [Purchase.from_row(r) for r in rows]

    # -----------------------------------------------------------------------
    # 2. Goods Receiving & Batch Creation Workflow
    # -----------------------------------------------------------------------

    def receive_purchase(
        self,
        purchase_id: int,
        receiving_batches: List[Dict[str, Any]],
        store_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Explicit Goods Receiving Workflow:
        Validates manufacturer batches, enforces Critical Shelf Allocation Rule,
        creates/increments batches, logs atomic stock movements, and marks purchase as RECEIVED.

        Prevents duplicate receiving: Retrying a receipt operation will not double inventory.
        Rolls back completely if any item or rule fails.
        """
        require_permission(acting_user, PERM_MANAGE_PURCHASES, "Goods receipt")

        purchase = self.get_purchase_by_id(purchase_id, store_id=store_id, acting_user=acting_user)
        if not purchase:
            raise ValueError(f"Purchase ID {purchase_id} not found.")

        target_store = purchase.store_id
        require_store_access(acting_user, target_store, "Receiving goods into store")

        if purchase.status == "RECEIVED":
            raise ValueError(
                f"Purchase '{purchase.invoice_number}' has already been received. "
                "Duplicate receiving is strictly prevented."
            )
        if purchase.status == "CANCELLED":
            raise ValueError(
                f"Purchase '{purchase.invoice_number}' was cancelled and cannot be received."
            )

        if not receiving_batches:
            raise ValueError("No receiving batch data provided.")

        user_id = getattr(acting_user, "user_id", None) if acting_user else None
        if user_id is not None:
            u_exists = self.db.fetch_one("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not u_exists:
                user_id = None
        receiving_date = datetime.now().strftime("%Y-%m-%d")

        # -------------------------------------------------------------------
        # Validation Phase: Validate all items BEFORE any database mutation
        # -------------------------------------------------------------------
        validated_receipt_items = []
        for idx, rb in enumerate(receiving_batches, start=1):
            item_id = rb.get("item_id")
            med_id = rb.get("medicine_id")
            batch_num = str(rb.get("batch_number", "")).strip().upper()
            expiry_str = str(rb.get("expiry_date", "")).strip()
            mfg_str = str(rb.get("mfg_date", "")).strip() if rb.get("mfg_date") else None
            qty = int(rb.get("quantity", 0))
            cost = float(rb.get("unit_cost", 0.0))
            price = float(rb.get("selling_price", 0.0))
            loc_id = rb.get("location_id")

            if not batch_num:
                raise ValueError(f"Receiving item #{idx}: Manufacturer batch number is required.")
            if not expiry_str:
                raise ValueError(f"Receiving item #{idx}: Expiry date is required.")

            try:
                datetime.strptime(expiry_str, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Receiving item #{idx}: Expiry date '{expiry_str}' must be YYYY-MM-DD.")

            if mfg_str:
                try:
                    datetime.strptime(mfg_str, "%Y-%m-%d")
                except ValueError:
                    raise ValueError(f"Receiving item #{idx}: Manufacturing date '{mfg_str}' must be YYYY-MM-DD.")

            if qty <= 0:
                raise ValueError(f"Receiving item #{idx}: Quantity received must be greater than zero.")
            if cost < 0:
                raise ValueError(f"Receiving item #{idx}: Unit purchase cost cannot be negative.")
            if price < 0:
                raise ValueError(f"Receiving item #{idx}: Selling price cannot be negative.")
            if not loc_id or int(loc_id) <= 0:
                raise ValueError(f"Receiving item #{idx}: Valid storage location (shelf) is required.")

            # Validate medicine belongs to target_store
            med_row = self.db.fetch_one(
                "SELECT medicine_id, medicine_name, price FROM medicines WHERE medicine_id = ? AND store_id = ?",
                (med_id, target_store)
            )
            if not med_row:
                raise ValueError(f"Receiving item #{idx}: Medicine ID {med_id} not found in store '{target_store}'.")

            # Default selling price from medicine catalog if not provided
            if price == 0.0 and med_row["price"] > 0:
                price = float(med_row["price"])

            # ---------------------------------------------------------------
            # CRITICAL SHELF ALLOCATION RULE CHECK
            # "The same medicine must be assigned to separate shelf locations
            #  when its expiry dates differ. Batches with the same expiry date
            #  may share a shelf, even if their batch numbers differ."
            # ---------------------------------------------------------------
            ok, shelf_err = self.shelf_service.validate_shelf_allocation(
                store_id=target_store,
                medicine_id=med_id,
                location_id=loc_id,
                expiry_date=expiry_str
            )
            if not ok:
                _, suggested_shelf, _ = self.shelf_service.suggest_shelf_location(
                    target_store, med_id, expiry_str
                )
                raise ValueError(
                    f"Receiving item #{idx} failed shelf allocation: {shelf_err} "
                    f"Suggested shelf: '{suggested_shelf}'."
                )

            validated_receipt_items.append({
                "item_id": item_id,
                "medicine_id": med_id,
                "medicine_name": med_row["medicine_name"],
                "batch_number": batch_num,
                "expiry_date": expiry_str,
                "mfg_date": mfg_str,
                "quantity": qty,
                "unit_cost": cost,
                "selling_price": price,
                "location_id": loc_id
            })

        # -------------------------------------------------------------------
        # Execution Phase: Atomic Database Transaction
        # -------------------------------------------------------------------
        conn = self.db.get_connection()
        created_batches_summary = []
        try:
            cursor = conn.cursor()

            for item in validated_receipt_items:
                med_id = item["medicine_id"]
                batch_num = item["batch_number"]
                expiry_str = item["expiry_date"]
                qty = item["quantity"]
                cost = item["unit_cost"]
                price = item["selling_price"]
                loc_id = item["location_id"]
                mfg_str = item["mfg_date"]

                # Determine batch status: Expired vs Active
                status = "Expired" if self.shelf_service.is_expired(expiry_str) else "Active"

                # Check if batch (store_id, medicine_id, batch_number) already exists
                cursor.execute(
                    """
                    SELECT batch_id, expiry_date, current_quantity, initial_quantity
                    FROM inventory_batches
                    WHERE store_id = ? AND medicine_id = ? AND batch_number = ?
                    """,
                    (target_store, med_id, batch_num)
                )
                existing_batch = cursor.fetchone()

                if existing_batch:
                    # Check for conflicting expiry dates for the same batch number
                    existing_exp = str(existing_batch[1]).strip()
                    if existing_exp != expiry_str:
                        raise ValueError(
                            f"Batch integrity error: Batch '{batch_num}' already exists in inventory with "
                            f"expiry date '{existing_exp}'. Received expiry date '{expiry_str}' conflicts. "
                            "Conflicting expiry dates for the same manufacturer batch must be verified."
                        )

                    batch_id = existing_batch[0]
                    new_curr = existing_batch[2] + qty
                    new_init = existing_batch[3] + qty

                    cursor.execute(
                        """
                        UPDATE inventory_batches SET
                            current_quantity = ?,
                            initial_quantity = ?,
                            purchase_cost = ?,
                            selling_price = ?,
                            location_id = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE batch_id = ?
                        """,
                        (new_curr, new_init, cost, price, loc_id, batch_id)
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO inventory_batches (
                            store_id, medicine_id, batch_number, supplier_id,
                            mfg_date, expiry_date, received_date, initial_quantity,
                            current_quantity, purchase_cost, selling_price, location_id,
                            status, verification_flag, notes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                        """,
                        (
                            target_store,
                            med_id,
                            batch_num,
                            purchase.supplier_id,
                            mfg_str,
                            expiry_str,
                            receiving_date,
                            qty,
                            qty,
                            cost,
                            price,
                            loc_id,
                            status,
                            f"Received via Purchase Inv #{purchase.invoice_number}"
                        )
                    )
                    batch_id = cursor.lastrowid

                # Link batch_id to purchase_items if item_id provided
                if item["item_id"]:
                    cursor.execute(
                        "UPDATE purchase_items SET batch_id = ? WHERE item_id = ? AND purchase_id = ?",
                        (batch_id, item["item_id"], purchase_id)
                    )

                # Record immutable audit ledger entry in stock_movements
                cursor.execute(
                    """
                    INSERT INTO stock_movements (
                        store_id, medicine_id, batch_id, movement_type,
                        quantity_delta, reference_type, reference_id, notes, created_by
                    ) VALUES (?, ?, ?, 'PURCHASE_RECEIPT', ?, 'PURCHASE', ?, ?, ?)
                    """,
                    (
                        target_store,
                        med_id,
                        batch_id,
                        qty,  # Positive delta for stock addition
                        str(purchase_id),
                        f"Receipt from Inv #{purchase.invoice_number}",
                        user_id
                    )
                )

                # Keep legacy medicines.quantity synchronized (total physical stock)
                cursor.execute(
                    """
                    UPDATE medicines SET
                        quantity = (
                            SELECT COALESCE(SUM(current_quantity), 0)
                            FROM inventory_batches
                            WHERE medicine_id = ? AND store_id = ?
                        ),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE medicine_id = ? AND store_id = ?
                    """,
                    (med_id, target_store, med_id, target_store)
                )

                created_batches_summary.append({
                    "batch_id": batch_id,
                    "medicine_id": med_id,
                    "medicine_name": item["medicine_name"],
                    "batch_number": batch_num,
                    "quantity_received": qty,
                    "expiry_date": expiry_str,
                    "location_id": loc_id
                })

            # Update purchase status to RECEIVED
            cursor.execute(
                """
                UPDATE purchases SET
                    status = 'RECEIVED',
                    received_by = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE purchase_id = ?
                """,
                (user_id, purchase_id)
            )

            conn.commit()

            return {
                "status": "SUCCESS",
                "purchase_id": purchase_id,
                "invoice_number": purchase.invoice_number,
                "store_id": target_store,
                "received_date": receiving_date,
                "batches_recorded": len(created_batches_summary),
                "details": created_batches_summary
            }
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def cancel_purchase(
        self,
        purchase_id: int,
        reason: Optional[str] = None,
        store_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> bool:
        """
        Cancels a draft purchase.
        If already received, cannot be cancelled to preserve stock integrity and ledger history.
        """
        require_permission(acting_user, PERM_MANAGE_PURCHASES, "Cancelling a purchase")

        purchase = self.get_purchase_by_id(purchase_id, store_id=store_id, acting_user=acting_user)
        if not purchase:
            raise ValueError(f"Purchase ID {purchase_id} not found.")

        target_store = purchase.store_id
        require_store_access(acting_user, target_store, "Cancelling a purchase in store")

        if purchase.status == "RECEIVED":
            raise ValueError(
                f"Cannot cancel purchase '{purchase.invoice_number}' because it has already been received "
                "into stock. Use stock write-off or return adjustment to adjust received inventory."
            )
        if purchase.status == "CANCELLED":
            return True

        notes = purchase.notes or ""
        if reason:
            notes = f"{notes} | Cancelled: {reason}".strip(" | ")

        self.db.execute(
            "UPDATE purchases SET status = 'CANCELLED', notes = ?, updated_at = CURRENT_TIMESTAMP WHERE purchase_id = ?",
            (notes, purchase_id)
        )
        return True
