"""
Medicine service for inventory CRUD operations and KPI metrics retrieval.
Enforces multi-store tenant isolation across all queries and modifications.
"""
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from database.db import Database, get_db
from models.medicine import Medicine, LOW_STOCK_THRESHOLD, EXPIRING_SOON_DAYS
from services.rbac import (
    require_permission,
    require_store_access,
    PERM_ADD_MEDICINE,
    PERM_UPDATE_MEDICINE,
    PERM_DELETE_MEDICINE,
)


class MedicineService:
    """Handles business logic for medicine inventory management with store-level isolation."""

    def __init__(self, db: Optional[Database] = None, store_id: Optional[str] = None):
        self.db = db or get_db()
        self.store_id = store_id or "STORE-LEGACY-001"

    def _table_exists(self, table_name: str) -> bool:
        """Helper to determine whether a given table exists in SQLite schema."""
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def get_medicines_by_store(self, store_id: Optional[str] = None) -> List[Medicine]:
        target = store_id or self.store_id
        query = """
        SELECT medicine_id, store_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines
        WHERE store_id = ?
        ORDER BY medicine_name ASC
        """
        rows = self.db.fetch_all(query, (target,))
        return [Medicine.from_row(r) for r in rows]

    def get_all_medicines(self) -> List[Medicine]:
        """Retrieves all medicines for the active store."""
        query = """
        SELECT medicine_id, store_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines
        WHERE store_id = ?
        ORDER BY medicine_name ASC
        """
        rows = self.db.fetch_all(query, (self.store_id,))
        return [Medicine.from_row(r) for r in rows]

    def get_medicine_by_id(self, medicine_id: int) -> Optional[Medicine]:
        """Fetches a single medicine by primary key ID, scoped to the active store."""
        query = """
        SELECT medicine_id, store_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines WHERE medicine_id = ? AND store_id = ?
        """
        row = self.db.fetch_one(query, (medicine_id, self.store_id))
        return Medicine.from_row(row) if row else None

    def get_medicine_by_code(self, code: str) -> Optional[Medicine]:
        """Fetches a single medicine by medicine code within the active store."""
        query = """
        SELECT medicine_id, store_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines WHERE medicine_code = ? AND store_id = ?
        """
        row = self.db.fetch_one(query, (code.strip(), self.store_id))
        return Medicine.from_row(row) if row else None

    def add_medicine(
        self,
        medicine: Medicine,
        shelf_code: Optional[str] = None,
        mfg_date: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """
        Validates and inserts a new medicine record scoped to the active store.
        If shelf_code is provided, also automatically registers opening batch in inventory_batches.
        Guarded by PERM_ADD_MEDICINE if acting_user is provided.
        """
        if acting_user is not None:
            require_permission(acting_user, PERM_ADD_MEDICINE, "Adding new medicine")
            require_store_access(acting_user, self.store_id, "Adding new medicine")

        errors = medicine.validate()
        if errors:
            return False, "\n".join(errors)

        # Check for unique medicine code within this store
        existing = self.get_medicine_by_code(medicine.medicine_code)
        if existing:
            return False, f"Medicine code '{medicine.medicine_code}' already exists in your store."

        query = """
        INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            self.store_id,
            medicine.medicine_code.strip(),
            medicine.medicine_name.strip(),
            medicine.category.strip(),
            medicine.manufacturer.strip(),
            medicine.batch_no.strip(),
            float(medicine.price),
            int(medicine.quantity),
            medicine.expiry_date.strip()
        )

        try:
            self.db.execute(query, params)
            new_med = self.get_medicine_by_code(medicine.medicine_code)

            # Auto-register initial inventory batch and shelf location if batches table exists
            if new_med and shelf_code and self._table_exists("inventory_batches"):
                clean_shelf = shelf_code.strip()
                loc_id = None
                if self._table_exists("storage_locations"):
                    loc_row = self.db.fetch_one(
                        "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
                        (self.store_id, clean_shelf)
                    )
                    if loc_row:
                        loc_id = loc_row["location_id"]
                    else:
                        self.db.execute(
                            "INSERT INTO storage_locations (store_id, shelf_code, rack, bin, description, is_active) VALUES (?, ?, ?, 'Bin 1', ?, 1)",
                            (self.store_id, clean_shelf, clean_shelf.split('-')[0] if '-' in clean_shelf else "Rack", f"Shelf {clean_shelf}")
                        )
                        created_loc = self.db.fetch_one(
                            "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
                            (self.store_id, clean_shelf)
                        )
                        loc_id = created_loc["location_id"] if created_loc else None

                b_num = medicine.batch_no.strip() if medicine.batch_no else f"BCH-{new_med.medicine_code}"
                mfg_val = mfg_date.strip() if mfg_date else datetime.now().strftime("%Y-%m-%d")

                self.db.execute(
                    """
                    INSERT INTO inventory_batches (
                        store_id, medicine_id, batch_number, mfg_date, expiry_date,
                        received_date, initial_quantity, current_quantity, purchase_cost, selling_price,
                        location_id, status, verification_flag, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', 0, 'Initial opening batch')
                    """,
                    (
                        self.store_id, new_med.medicine_id, b_num, mfg_val, medicine.expiry_date.strip(),
                        datetime.now().strftime("%Y-%m-%d"), int(medicine.quantity), int(medicine.quantity),
                        round(float(medicine.price) * 0.7, 2), float(medicine.price), loc_id
                    )
                )

                if self._table_exists("stock_movements") and int(medicine.quantity) > 0:
                    b_row = self.db.fetch_one(
                        "SELECT batch_id FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND batch_number = ?",
                        (self.store_id, new_med.medicine_id, b_num)
                    )
                    b_id = b_row["batch_id"] if b_row else None
                    self.db.execute(
                        """
                        INSERT INTO stock_movements (
                            store_id, medicine_id, batch_id, movement_type, quantity_delta,
                            reference_type, notes
                        ) VALUES (?, ?, ?, 'MIGRATION_OPENING', ?, 'INITIAL_STOCK', 'Opening batch stock registered')
                        """,
                        (self.store_id, new_med.medicine_id, b_id, int(medicine.quantity))
                    )

            return True, "Medicine and batch inventory added successfully."
        except Exception as e:
            err_msg = str(e)
            if "UNIQUE constraint failed" in err_msg and "medicine_code" in err_msg:
                return False, f"Medicine code '{medicine.medicine_code}' already exists in your store."
            return False, f"Database insertion error: {err_msg}"

    def update_medicine(
        self,
        medicine: Medicine,
        shelf_code: Optional[str] = None,
        batch_id: Optional[int] = None,
        acting_user: Optional[Any] = None
    ) -> Tuple[bool, str]:
        """
        Validates and updates an existing medicine record belonging to the active store.
        If shelf_code is provided, synchronizes the target batch's storage location
        adhering to the Critical Shelf Allocation Rules and logs the relocation in stock_movements.
        Other batches of the same medicine remain unaltered.
        Guarded by PERM_UPDATE_MEDICINE if acting_user is provided.
        """
        if acting_user is not None:
            require_permission(acting_user, PERM_UPDATE_MEDICINE, "Updating medicine")
            require_store_access(acting_user, self.store_id, "Updating medicine")

        if not medicine.medicine_id:
            return False, "Invalid medicine ID for update operation."

        # Validate ownership
        current = self.get_medicine_by_id(medicine.medicine_id)
        if not current:
            return False, "Medicine not found or access denied."

        errors = medicine.validate()
        if errors:
            return False, "\n".join(errors)

        # Check for code uniqueness conflict with another record in this store
        existing = self.get_medicine_by_code(medicine.medicine_code)
        if existing and existing.medicine_id != medicine.medicine_id:
            return False, f"Medicine code '{medicine.medicine_code}' is assigned to another item in your store."

        query = """
        UPDATE medicines
        SET medicine_code = ?, medicine_name = ?, category = ?, manufacturer = ?,
            batch_no = ?, price = ?, quantity = ?, expiry_date = ?, updated_at = CURRENT_TIMESTAMP
        WHERE medicine_id = ? AND store_id = ?
        """
        params = (
            medicine.medicine_code.strip(),
            medicine.medicine_name.strip(),
            medicine.category.strip(),
            medicine.manufacturer.strip(),
            medicine.batch_no.strip(),
            float(medicine.price),
            int(medicine.quantity),
            medicine.expiry_date.strip(),
            medicine.medicine_id,
            self.store_id
        )

        try:
            self.db.execute(query, params)

            # Shelf/Rack Synchronization & Relocation Tracking
            if shelf_code and self._table_exists("storage_locations") and self._table_exists("inventory_batches"):
                shelf_clean = shelf_code.strip()
                loc_row = self.db.fetch_one(
                    "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
                    (self.store_id, shelf_clean)
                )
                if loc_row:
                    new_loc_id = loc_row["location_id"]
                else:
                    self.db.execute(
                        """
                        INSERT INTO storage_locations (store_id, shelf_code, rack, bin, description, is_active)
                        VALUES (?, ?, ?, 'Bin 1', ?, 1)
                        """,
                        (self.store_id, shelf_clean, shelf_clean.split('-')[0] if '-' in shelf_clean else "Rack", f"Shelf {shelf_clean}")
                    )
                    created_loc = self.db.fetch_one(
                        "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
                        (self.store_id, shelf_clean)
                    )
                    new_loc_id = created_loc["location_id"] if created_loc else None

                if new_loc_id:
                    # Identify target batch to relocate without altering other batches
                    target_b = None
                    if batch_id:
                        target_b = self.db.fetch_one(
                            "SELECT * FROM inventory_batches WHERE store_id = ? AND batch_id = ?",
                            (self.store_id, batch_id)
                        )
                    if not target_b and medicine.batch_no:
                        target_b = self.db.fetch_one(
                            "SELECT * FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND batch_number = ?",
                            (self.store_id, medicine.medicine_id, medicine.batch_no.strip())
                        )
                    if not target_b:
                        target_b = self.db.fetch_one(
                            "SELECT * FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND status = 'Active' ORDER BY expiry_date ASC LIMIT 1",
                            (self.store_id, medicine.medicine_id)
                        )
                    if not target_b:
                        target_b = self.db.fetch_one(
                            "SELECT * FROM inventory_batches WHERE store_id = ? AND medicine_id = ? ORDER BY batch_id DESC LIMIT 1",
                            (self.store_id, medicine.medicine_id)
                        )

                    if target_b:
                        old_loc_id = target_b["location_id"]
                        t_batch_id = target_b["batch_id"]
                        t_expiry = target_b["expiry_date"]

                        # Critical Shelf Allocation Rule 1 Check:
                        # Different expiries of the SAME medicine cannot share the same shelf
                        conflict = self.db.fetch_one(
                            """
                            SELECT batch_number, expiry_date FROM inventory_batches
                            WHERE store_id = ? AND medicine_id = ? AND location_id = ?
                              AND status = 'Active' AND batch_id != ? AND expiry_date != ?
                            """,
                            (self.store_id, medicine.medicine_id, new_loc_id, t_batch_id, t_expiry)
                        )
                        if conflict:
                            return False, (
                                f"Critical Shelf Allocation Rule Violation: Shelf '{shelf_clean}' already holds "
                                f"batch '{conflict['batch_number']}' with different expiry date ({conflict['expiry_date']}). "
                                "Different expiries of the same medicine must be placed on separate shelves."
                            )

                        if old_loc_id != new_loc_id:
                            self.db.execute(
                                "UPDATE inventory_batches SET location_id = ?, updated_at = CURRENT_TIMESTAMP WHERE batch_id = ?",
                                (new_loc_id, t_batch_id)
                            )

                            if self._table_exists("stock_movements"):
                                old_shelf_row = self.db.fetch_one(
                                    "SELECT shelf_code FROM storage_locations WHERE location_id = ?",
                                    (old_loc_id,)
                                ) if old_loc_id else None
                                old_shelf_code = old_shelf_row["shelf_code"] if old_shelf_row else "None"
                                uid = getattr(acting_user, "user_id", None)
                                self.db.execute(
                                    """
                                    INSERT INTO stock_movements (
                                        store_id, medicine_id, batch_id, movement_type, quantity_delta,
                                        reference_type, reference_id, notes, created_by
                                    ) VALUES (?, ?, ?, 'STORE_TRANSFER', 0, 'SHELF_RELOCATION', ?, ?, ?)
                                    """,
                                    (
                                        self.store_id, medicine.medicine_id, t_batch_id,
                                        str(t_batch_id),
                                        f"Relocated batch '{target_b['batch_number']}' from {old_shelf_code} to {shelf_clean}",
                                        uid
                                    )
                                )
                    else:
                        # Opening batch auto-registration on edit if none existed
                        b_num = medicine.batch_no.strip() if medicine.batch_no else f"BCH-{medicine.medicine_code}"
                        self.db.execute(
                            """
                            INSERT INTO inventory_batches (
                                store_id, medicine_id, batch_number, mfg_date, expiry_date,
                                received_date, initial_quantity, current_quantity, purchase_cost, selling_price,
                                location_id, status, verification_flag, notes
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', 0, 'Registered during medicine update')
                            """,
                            (
                                self.store_id, medicine.medicine_id, b_num,
                                datetime.now().strftime("%Y-%m-%d"), medicine.expiry_date.strip(),
                                datetime.now().strftime("%Y-%m-%d"), int(medicine.quantity), int(medicine.quantity),
                                round(float(medicine.price) * 0.7, 2), float(medicine.price), new_loc_id
                            )
                        )

            return True, "Medicine updated successfully."
        except Exception as e:
            err_msg = str(e)
            if "UNIQUE constraint failed" in err_msg and "medicine_code" in err_msg:
                return False, f"Medicine code '{medicine.medicine_code}' is assigned to another item in your store."
            return False, f"Database update error: {err_msg}"

    def delete_medicine(self, medicine_id: int, acting_user: Optional[Any] = None) -> Tuple[bool, str]:
        """
        Deletes a medicine record after verifying store ownership and sales history references.
        Guarded strictly by PERM_DELETE_MEDICINE (Owner/Admin only) if acting_user is provided.
        """
        if acting_user is not None:
            require_permission(acting_user, PERM_DELETE_MEDICINE, "Deleting medicine")
            require_store_access(acting_user, self.store_id, "Deleting medicine")

        # Verify ownership
        current = self.get_medicine_by_id(medicine_id)
        if not current:
            return False, "Medicine not found or access denied."

        # Audit dependencies across foreign key tables
        deps = self.check_delete_dependencies(medicine_id)
        if not deps["can_delete"]:
            reasons_bullet = "\n• ".join(deps["reasons"])
            msg = (
                f"Cannot delete '{current.medicine_name}' ({current.medicine_code}) due to active foreign key references:\n"
                f"• {reasons_bullet}\n\n"
                "Under pharmacy compliance and GDP regulations, records with transaction history cannot be deleted.\n"
                "You can deactivate or archive this medicine instead to preserve audit history."
            )
            return False, msg

        query = "DELETE FROM medicines WHERE medicine_id = ? AND store_id = ?"
        try:
            self.db.execute(query, (medicine_id, self.store_id))
            return True, "Medicine deleted successfully."
        except Exception as e:
            err_str = str(e)
            if "FOREIGN KEY constraint failed" in err_str:
                return False, (
                    f"Deletion blocked by database foreign key constraints: '{current.medicine_name}' "
                    "has linked ledger or batch records. Please archive or deactivate this medicine instead."
                )
            return False, f"Database deletion error: {err_str}"

    def check_delete_dependencies(self, medicine_id: int) -> Dict[str, Any]:
        """
        Audits all potential dependent records referencing this medicine across:
        - inventory_batches
        - sale_items
        - purchase_items
        - stock_movements
        Returns a dictionary of dependency counts and can_delete boolean.
        """
        deps = {
            "stock_quantity": 0,
            "batches_count": 0,
            "sales_count": 0,
            "purchases_count": 0,
            "movements_count": 0,
            "can_delete": True,
            "reasons": []
        }

        # 1. Check current stock
        med = self.get_medicine_by_id(medicine_id)
        if med:
            deps["stock_quantity"] = med.quantity

        def _count_in(table_name: str, col_name: str = "medicine_id") -> int:
            t_check = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
            if not t_check:
                return 0
            cols = [c['name'] for c in self.db.fetch_all(f"PRAGMA table_info({table_name})")]
            if col_name not in cols:
                return 0
            row = self.db.fetch_one(f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {col_name} = ?", (medicine_id,))
            return row["cnt"] if row else 0

        # Check batches
        batches_cnt = _count_in("inventory_batches")
        deps["batches_count"] = batches_cnt
        if batches_cnt > 0:
            deps["can_delete"] = False
            deps["reasons"].append(f"Batch Records: {batches_cnt} batch record(s) exist in inventory")

        # Check sales items
        sales_cnt = _count_in("sale_items")
        deps["sales_count"] = sales_cnt
        if sales_cnt > 0:
            deps["can_delete"] = False
            deps["reasons"].append(f"Sales History: {sales_cnt} past sales transaction item(s)")

        # Check purchase items
        purchases_cnt = _count_in("purchase_items")
        deps["purchases_count"] = purchases_cnt
        if purchases_cnt > 0:
            deps["can_delete"] = False
            deps["reasons"].append(f"Purchasing Records: {purchases_cnt} purchase order item(s)")

        # Check stock movements
        movements_cnt = _count_in("stock_movements")
        deps["movements_count"] = movements_cnt
        if movements_cnt > 0:
            deps["can_delete"] = False
            deps["reasons"].append(f"Stock Movement Ledger: {movements_cnt} audit log entry/entries")

        return deps

    def deactivate_medicine(self, medicine_id: int, acting_user: Optional[Any] = None) -> Tuple[bool, str]:
        """
        Safely deactivates or archives a medicine to prevent further sales while preserving complete transaction history.
        """
        if acting_user is not None:
            require_permission(acting_user, PERM_DELETE_MEDICINE, "Archiving medicine")
            require_store_access(acting_user, self.store_id, "Archiving medicine")

        current = self.get_medicine_by_id(medicine_id)
        if not current:
            return False, "Medicine not found or access denied."

        med_cols = [c['name'] for c in self.db.fetch_all("PRAGMA table_info(medicines)")]
        if "is_active" not in med_cols:
            self.db.execute("ALTER TABLE medicines ADD COLUMN is_active INTEGER DEFAULT 1")

        self.db.execute("UPDATE medicines SET is_active = 0, quantity = 0 WHERE medicine_id = ? AND store_id = ?", (medicine_id, self.store_id))
        return True, f"Medicine '{current.medicine_name}' has been successfully archived/deactivated."

    def get_categories(self) -> List[str]:
        """Returns distinct list of medicine categories for the active store."""
        rows = self.db.fetch_all(
            "SELECT DISTINCT category FROM medicines WHERE store_id = ? ORDER BY category ASC",
            (self.store_id,)
        )
        return [r["category"] for r in rows if r["category"]]

    def get_manufacturers(self) -> List[str]:
        """Returns distinct list of manufacturers for the active store."""
        rows = self.db.fetch_all(
            "SELECT DISTINCT manufacturer FROM medicines WHERE store_id = ? ORDER BY manufacturer ASC",
            (self.store_id,)
        )
        return [r["manufacturer"] for r in rows if r["manufacturer"]]

    def get_inventory_summary(self) -> Dict[str, Any]:
        """Calculates KPI metrics for Dashboard cards scoped exclusively to the active store."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        expiring_threshold = (datetime.now() + timedelta(days=EXPIRING_SOON_DAYS)).strftime("%Y-%m-%d")

        total_meds_row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM medicines WHERE store_id = ?", (self.store_id,))
        total_meds = total_meds_row["cnt"] if total_meds_row else 0

        total_stock_row = self.db.fetch_one("SELECT SUM(quantity) as cnt FROM medicines WHERE store_id = ?", (self.store_id,))
        total_stock = total_stock_row["cnt"] if total_stock_row and total_stock_row["cnt"] else 0

        total_val_row = self.db.fetch_one("SELECT SUM(price * quantity) as val FROM medicines WHERE store_id = ?", (self.store_id,))
        total_value = total_val_row["val"] if total_val_row and total_val_row["val"] else 0.0

        low_stock_query = "SELECT COUNT(*) as cnt FROM medicines WHERE quantity <= ? AND quantity > 0 AND store_id = ?"
        low_stock_row = self.db.fetch_one(low_stock_query, (LOW_STOCK_THRESHOLD, self.store_id))
        low_stock_cnt = low_stock_row["cnt"] if low_stock_row else 0

        out_of_stock_row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM medicines WHERE quantity = 0 AND store_id = ?", (self.store_id,))
        out_of_stock_cnt = out_of_stock_row["cnt"] if out_of_stock_row else 0

        expiring_query = """
        SELECT COUNT(*) as cnt FROM medicines
        WHERE expiry_date >= ? AND expiry_date <= ? AND store_id = ?
        """
        expiring_row = self.db.fetch_one(expiring_query, (today_str, expiring_threshold, self.store_id))
        expiring_cnt = expiring_row["cnt"] if expiring_row else 0

        expired_query = "SELECT COUNT(*) as cnt FROM medicines WHERE expiry_date < ? AND store_id = ?"
        expired_row = self.db.fetch_one(expired_query, (today_str, self.store_id))
        expired_cnt = expired_row["cnt"] if expired_row else 0

        sales_val_row = self.db.fetch_one("SELECT SUM(total_amount) as val FROM sales WHERE store_id = ?", (self.store_id,))
        total_sales_val = sales_val_row["val"] if sales_val_row and sales_val_row["val"] else 0.0

        sales_cnt_row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM sales WHERE store_id = ?", (self.store_id,))
        total_sales_count = sales_cnt_row["cnt"] if sales_cnt_row else 0

        return {
            "total_medicines": total_meds,
            "total_stock_quantity": total_stock,
            "total_inventory_value": round(total_value, 2),
            "low_stock_count": low_stock_cnt,
            "out_of_stock_count": out_of_stock_cnt,
            "expiring_soon_count": expiring_cnt,
            "expired_count": expired_cnt,
            "total_sales_amount": round(total_sales_val, 2),
            "total_sales_transactions": total_sales_count
        }

    def get_owner_summary(self) -> Dict[str, Any]:
        """Calculates executive business metrics for the Owner/Admin dashboard."""
        today_date = datetime.now().strftime("%Y-%m-%d")

        # Today's sales
        today_sales_row = self.db.fetch_one(
            "SELECT COALESCE(SUM(total_amount), 0) as val, COUNT(*) as cnt FROM sales "
            "WHERE store_id = ? AND substr(sale_date, 1, 10) = ?",
            (self.store_id, today_date)
        )
        today_sales = today_sales_row["val"] if today_sales_row else 0.0
        today_bills = today_sales_row["cnt"] if today_sales_row else 0

        # All-time summary
        inv_summary = self.get_inventory_summary()

        # Top 5 selling medicines
        top_meds_rows = self.db.fetch_all(
            """
            SELECT m.medicine_name, m.medicine_code, m.category,
                   SUM(si.quantity) as qty_sold, SUM(si.subtotal) as total_rev
            FROM sale_items si
            JOIN medicines m ON si.medicine_id = m.medicine_id
            WHERE si.store_id = ?
            GROUP BY si.medicine_id
            ORDER BY qty_sold DESC
            LIMIT 5
            """,
            (self.store_id,)
        )
        top_selling = [
            {
                "medicine_name": r["medicine_name"],
                "medicine_code": r["medicine_code"],
                "category": r["category"],
                "qty_sold": r["qty_sold"],
                "total_rev": round(r["total_rev"], 2)
            }
            for r in top_meds_rows
        ]

        # Recent 5 sales transactions
        recent_sales_rows = self.db.fetch_all(
            """
            SELECT s.sale_id, s.invoice_number, s.patient_name, s.sale_date, s.total_amount, u.username
            FROM sales s
            LEFT JOIN users u ON s.user_id = u.user_id
            WHERE s.store_id = ?
            ORDER BY s.sale_id DESC
            LIMIT 5
            """,
            (self.store_id,)
        )
        recent_sales = [
            {
                "sale_id": r["sale_id"],
                "invoice_number": r["invoice_number"] or f"INV-{r['sale_id']}",
                "patient_name": r["patient_name"] or "General Customer",
                "sale_date": r["sale_date"],
                "total_amount": round(r["total_amount"], 2),
                "cashier": r["username"] or "Staff"
            }
            for r in recent_sales_rows
        ]

        # Real Gross Profit: Calculate ONLY when reliable purchase cost data exists.
        # Profit is never fabricated using an assumed margin percentage.
        real_profit = None
        today_real_profit = None
        has_allocations = self._table_exists("sale_batch_allocations") and self._table_exists("inventory_batches")

        if inv_summary["total_sales_amount"] == 0:
            real_profit = 0.0
            today_real_profit = 0.0
        elif has_allocations:
            cogs_row = self.db.fetch_one(
                """
                SELECT 
                    SUM(sba.quantity * ib.purchase_cost) as total_cogs,
                    COUNT(sba.allocation_id) as total_allocs,
                    COUNT(CASE WHEN ib.purchase_cost IS NULL THEN 1 END) as missing_cost_allocs
                FROM sale_batch_allocations sba
                JOIN inventory_batches ib ON sba.batch_id = ib.batch_id
                JOIN sale_items si ON sba.sale_item_id = si.item_id
                JOIN sales s ON si.sale_id = s.sale_id
                WHERE s.store_id = ?
                """,
                (self.store_id,)
            )
            item_count_row = self.db.fetch_one(
                "SELECT COUNT(*) as cnt FROM sale_items si JOIN sales s ON si.sale_id = s.sale_id WHERE s.store_id = ?",
                (self.store_id,)
            )
            total_items = item_count_row["cnt"] if item_count_row else 0

            if (cogs_row and cogs_row["total_allocs"] > 0
                    and cogs_row["missing_cost_allocs"] == 0
                    and cogs_row["total_cogs"] is not None
                    and cogs_row["total_allocs"] >= total_items):
                real_profit = round(inv_summary["total_sales_amount"] - float(cogs_row["total_cogs"]), 2)

                if today_sales > 0:
                    today_cogs_row = self.db.fetch_one(
                        """
                        SELECT SUM(sba.quantity * ib.purchase_cost) as today_cogs
                        FROM sale_batch_allocations sba
                        JOIN inventory_batches ib ON sba.batch_id = ib.batch_id
                        JOIN sale_items si ON sba.sale_item_id = si.item_id
                        JOIN sales s ON si.sale_id = s.sale_id
                        WHERE s.store_id = ? AND substr(s.sale_date, 1, 10) = ?
                        """,
                        (self.store_id, today_date)
                    )
                    if today_cogs_row and today_cogs_row["today_cogs"] is not None:
                        today_real_profit = round(today_sales - float(today_cogs_row["today_cogs"]), 2)

        return {
            **inv_summary,
            "today_sales_amount": round(today_sales, 2),
            "today_bills_count": today_bills,
            "estimated_gross_profit": real_profit,
            "today_estimated_profit": today_real_profit,
            "profit_available": real_profit is not None,
            "top_selling": top_selling,
            "recent_sales": recent_sales,
        }

    def get_pharmacist_summary(self) -> Dict[str, Any]:
        """Calculates clinical inspection and safety metrics for the Pharmacist dashboard."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        expiring_threshold = (datetime.now() + timedelta(days=EXPIRING_SOON_DAYS)).strftime("%Y-%m-%d")

        # Available medicines (in-stock and unexpired)
        avail_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM medicines WHERE store_id = ? AND quantity > 0 AND expiry_date >= ?",
            (self.store_id, today_str)
        )
        avail_cnt = avail_row["cnt"] if avail_row else 0

        # Expired count
        expired_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM medicines WHERE store_id = ? AND expiry_date < ?",
            (self.store_id, today_str)
        )
        expired_cnt = expired_row["cnt"] if expired_row else 0

        # Expiring soon count
        expiring_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM medicines WHERE store_id = ? AND expiry_date >= ? AND expiry_date <= ?",
            (self.store_id, today_str, expiring_threshold)
        )
        expiring_cnt = expiring_row["cnt"] if expiring_row else 0

        # Low stock count
        low_stock_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM medicines WHERE store_id = ? AND quantity <= ? AND quantity > 0",
            (self.store_id, LOW_STOCK_THRESHOLD)
        )
        low_stock_cnt = low_stock_row["cnt"] if low_stock_row else 0

        # Out of stock count
        out_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM medicines WHERE store_id = ? AND quantity = 0",
            (self.store_id,)
        )
        out_cnt = out_row["cnt"] if out_row else 0

        # Attention required count
        attention_total = expired_cnt + expiring_cnt + low_stock_cnt + out_cnt

        # Medicines needing clinical attention
        alert_meds_rows = self.db.fetch_all(
            """
            SELECT medicine_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date
            FROM medicines
            WHERE store_id = ? AND (expiry_date < ? OR expiry_date <= ? OR quantity <= ?)
            ORDER BY expiry_date ASC, quantity ASC
            LIMIT 10
            """,
            (self.store_id, today_str, expiring_threshold, LOW_STOCK_THRESHOLD)
        )
        alert_meds = [Medicine.from_row(r) for r in alert_meds_rows]

        # Recent dispensing history (last 8 items dispensed)
        recent_dispensed_rows = self.db.fetch_all(
            """
            SELECT si.item_id, m.medicine_name, m.medicine_code, m.batch_no, si.quantity, si.price,
                   s.invoice_number, s.patient_name, s.sale_date
            FROM sale_items si
            JOIN medicines m ON si.medicine_id = m.medicine_id
            JOIN sales s ON si.sale_id = s.sale_id
            WHERE si.store_id = ?
            ORDER BY si.item_id DESC
            LIMIT 8
            """,
            (self.store_id,)
        )
        recent_dispensed = [
            {
                "medicine_name": r["medicine_name"],
                "medicine_code": r["medicine_code"],
                "batch_no": r["batch_no"],
                "quantity": r["quantity"],
                "patient_name": r["patient_name"] or "Patient",
                "sale_date": r["sale_date"],
                "invoice": r["invoice_number"] or "INV"
            }
            for r in recent_dispensed_rows
        ]

        return {
            "available_medicines": avail_cnt,
            "attention_total": attention_total,
            "expired_count": expired_cnt,
            "expiring_soon_count": expiring_cnt,
            "low_stock_count": low_stock_cnt,
            "out_of_stock_count": out_cnt,
            "alert_medicines": alert_meds,
            "recent_dispensed": recent_dispensed,
        }

    def get_inventory_manager_summary(self) -> Dict[str, Any]:
        """Calculates stock management and reordering metrics for the Inventory Manager dashboard."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        expiring_threshold = (datetime.now() + timedelta(days=EXPIRING_SOON_DAYS)).strftime("%Y-%m-%d")

        base_summary = self.get_inventory_summary()

        # Low stock reorder list
        reorder_rows = self.db.fetch_all(
            """
            SELECT medicine_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date
            FROM medicines
            WHERE store_id = ? AND quantity <= ?
            ORDER BY quantity ASC, medicine_name ASC
            LIMIT 15
            """,
            (self.store_id, LOW_STOCK_THRESHOLD)
        )
        reorder_items = [Medicine.from_row(r) for r in reorder_rows]

        # Batch & Expiry alerts list (expired or expiring within 60 days)
        expiry_60_days = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
        expiry_alert_rows = self.db.fetch_all(
            """
            SELECT medicine_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date
            FROM medicines
            WHERE store_id = ? AND expiry_date <= ?
            ORDER BY expiry_date ASC
            LIMIT 15
            """,
            (self.store_id, expiry_60_days)
        )
        expiry_items = [Medicine.from_row(r) for r in expiry_alert_rows]

        return {
            **base_summary,
            "reorder_items": reorder_items,
            "expiry_items": expiry_items,
        }
