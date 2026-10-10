"""
Medicine service for inventory CRUD operations and KPI metrics retrieval.
"""
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
from database.db import Database, get_db
from models.medicine import Medicine, LOW_STOCK_THRESHOLD, EXPIRING_SOON_DAYS


class MedicineService:
    """Handles business logic for medicine inventory management."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_db()

    def get_all_medicines(self) -> List[Medicine]:
        """Retrieves all medicines from database using explicit column projection."""
        query = """
        SELECT medicine_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines
        ORDER BY medicine_name ASC
        """
        rows = self.db.fetch_all(query)
        return [Medicine.from_row(r) for r in rows]

    def get_medicine_by_id(self, medicine_id: int) -> Optional[Medicine]:
        """Fetches a single medicine by primary key ID."""
        query = """
        SELECT medicine_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines WHERE medicine_id = ?
        """
        row = self.db.fetch_one(query, (medicine_id,))
        return Medicine.from_row(row) if row else None

    def get_medicine_by_code(self, code: str) -> Optional[Medicine]:
        """Fetches a single medicine by unique medicine code."""
        query = """
        SELECT medicine_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines WHERE medicine_code = ?
        """
        row = self.db.fetch_one(query, (code.strip(),))
        return Medicine.from_row(row) if row else None

    def add_medicine(self, medicine: Medicine) -> Tuple[bool, str]:
        """Validates and inserts a new medicine record into the database."""
        errors = medicine.validate()
        if errors:
            return False, "\n".join(errors)

        # Check for unique medicine code
        existing = self.get_medicine_by_code(medicine.medicine_code)
        if existing:
            return False, f"Medicine code '{medicine.medicine_code}' already exists."

        query = """
        INSERT INTO medicines (medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
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
            return False, f"Database insertion error: {str(e)}"

    def update_medicine(self, medicine: Medicine) -> Tuple[bool, str]:
        """Validates and updates an existing medicine record."""
        if not medicine.medicine_id:
            return False, "Invalid medicine ID for update operation."

        errors = medicine.validate()
        if errors:
            return False, "\n".join(errors)

        # Check for code uniqueness conflict with another record
        existing = self.get_medicine_by_code(medicine.medicine_code)
        if existing and existing.medicine_id != medicine.medicine_id:
            return False, f"Medicine code '{medicine.medicine_code}' is assigned to another item."

        query = """
        UPDATE medicines
        SET medicine_code = ?, medicine_name = ?, category = ?, manufacturer = ?,
            batch_no = ?, price = ?, quantity = ?, expiry_date = ?, updated_at = CURRENT_TIMESTAMP
        WHERE medicine_id = ?
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
            medicine.medicine_id
        )

        try:
            self.db.execute(query, params)
            return True, "Medicine updated successfully."
        except Exception as e:
            return False, f"Database update error: {str(e)}"

    def delete_medicine(self, medicine_id: int) -> Tuple[bool, str]:
        """Deletes a medicine record after checking foreign key references."""
        # Check if medicine is present in any sales
        sales_check = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM sale_items WHERE medicine_id = ?",
            (medicine_id,)
        )
        if sales_check and sales_check["cnt"] > 0:
            return False, "Cannot delete medicine because it is referenced in past sales history."

        query = "DELETE FROM medicines WHERE medicine_id = ?"
        try:
            self.db.execute(query, (medicine_id,))
            return True, "Medicine deleted successfully."
        except Exception as e:
            return False, f"Database deletion error: {str(e)}"

    def get_categories(self) -> List[str]:
        """Returns distinct list of medicine categories for filtering drop-downs."""
        rows = self.db.fetch_all("SELECT DISTINCT category FROM medicines ORDER BY category ASC")
        return [r["category"] for r in rows if r["category"]]

    def get_manufacturers(self) -> List[str]:
        """Returns distinct list of manufacturers for filtering drop-downs."""
        rows = self.db.fetch_all("SELECT DISTINCT manufacturer FROM medicines ORDER BY manufacturer ASC")
        return [r["manufacturer"] for r in rows if r["manufacturer"]]

    def get_inventory_summary(self) -> Dict[str, Any]:
        """Calculates KPI metrics for Dashboard cards."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        expiring_threshold = (datetime.now() + timedelta(days=EXPIRING_SOON_DAYS)).strftime("%Y-%m-%d")

        total_meds = self.db.fetch_one("SELECT COUNT(*) as cnt FROM medicines")["cnt"]
        total_stock = self.db.fetch_one("SELECT SUM(quantity) as cnt FROM medicines")["cnt"] or 0
        total_value = self.db.fetch_one("SELECT SUM(price * quantity) as val FROM medicines")["val"] or 0.0

        low_stock_query = "SELECT COUNT(*) as cnt FROM medicines WHERE quantity <= ? AND quantity > 0"
        low_stock_cnt = self.db.fetch_one(low_stock_query, (LOW_STOCK_THRESHOLD,))["cnt"]

        out_of_stock_cnt = self.db.fetch_one("SELECT COUNT(*) as cnt FROM medicines WHERE quantity = 0")["cnt"]

        expiring_query = """
        SELECT COUNT(*) as cnt FROM medicines
        WHERE expiry_date >= ? AND expiry_date <= ?
        """
        expiring_cnt = self.db.fetch_one(expiring_query, (today_str, expiring_threshold))["cnt"]

        expired_query = "SELECT COUNT(*) as cnt FROM medicines WHERE expiry_date < ?"
        expired_cnt = self.db.fetch_one(expired_query, (today_str,))["cnt"]

        total_sales_val = self.db.fetch_one("SELECT SUM(total_amount) as val FROM sales")["val"] or 0.0
        total_sales_count = self.db.fetch_one("SELECT COUNT(*) as cnt FROM sales")["cnt"]

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
