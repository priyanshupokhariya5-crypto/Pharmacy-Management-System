"""
Medicine service for inventory CRUD operations and KPI metrics retrieval.
Enforces multi-store tenant isolation across all queries and modifications.
"""
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from database.db import Database, get_db
from models.medicine import Medicine, LOW_STOCK_THRESHOLD, EXPIRING_SOON_DAYS


class MedicineService:
    """Handles business logic for medicine inventory management with store-level isolation."""

    def __init__(self, db: Optional[Database] = None, store_id: Optional[str] = None):
        self.db = db or get_db()
        self.store_id = store_id or "STORE-LEGACY-001"

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

    def add_medicine(self, medicine: Medicine) -> Tuple[bool, str]:
        """Validates and inserts a new medicine record scoped to the active store."""
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
            return True, "Medicine added successfully."
        except Exception as e:
            err_msg = str(e)
            if "UNIQUE constraint failed" in err_msg and "medicine_code" in err_msg:
                return False, f"Medicine code '{medicine.medicine_code}' already exists in your store."
            return False, f"Database insertion error: {err_msg}"

    def update_medicine(self, medicine: Medicine) -> Tuple[bool, str]:
        """Validates and updates an existing medicine record belonging to the active store."""
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
            return True, "Medicine updated successfully."
        except Exception as e:
            err_msg = str(e)
            if "UNIQUE constraint failed" in err_msg and "medicine_code" in err_msg:
                return False, f"Medicine code '{medicine.medicine_code}' is assigned to another item in your store."
            return False, f"Database update error: {err_msg}"

    def delete_medicine(self, medicine_id: int) -> Tuple[bool, str]:
        """Deletes a medicine record after verifying store ownership and sales history references."""
        # Verify ownership
        current = self.get_medicine_by_id(medicine_id)
        if not current:
            return False, "Medicine not found or access denied."

        # Check if medicine is present in any sales for this store
        sales_check = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM sale_items WHERE medicine_id = ? AND store_id = ?",
            (medicine_id, self.store_id)
        )
        if sales_check and sales_check["cnt"] > 0:
            return False, "Cannot delete medicine because it is referenced in past sales history."

        query = "DELETE FROM medicines WHERE medicine_id = ? AND store_id = ?"
        try:
            self.db.execute(query, (medicine_id, self.store_id))
            return True, "Medicine deleted successfully."
        except Exception as e:
            return False, f"Database deletion error: {str(e)}"

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
