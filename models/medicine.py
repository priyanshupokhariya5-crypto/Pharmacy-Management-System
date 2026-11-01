"""
Medicine domain model with data validation and inventory status helpers.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

LOW_STOCK_THRESHOLD = 10
EXPIRING_SOON_DAYS = 30


@dataclass
class Medicine:
    medicine_id: Optional[int]
    medicine_code: str
    medicine_name: str
    category: str
    manufacturer: str
    batch_no: str
    price: float
    quantity: int
    expiry_date: str  # YYYY-MM-DD
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    store_id: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Medicine":
        """Factory method to construct a Medicine model from an SQLite row."""
        keys = row.keys() if hasattr(row, "keys") else []
        return cls(
            medicine_id=row["medicine_id"],
            medicine_code=row["medicine_code"],
            medicine_name=row["medicine_name"],
            category=row["category"],
            manufacturer=row["manufacturer"],
            batch_no=row["batch_no"],
            price=float(row["price"]),
            quantity=int(row["quantity"]),
            expiry_date=row["expiry_date"],
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None,
            store_id=row["store_id"] if "store_id" in keys else None
        )

    def validate(self) -> List[str]:
        """
        Validates medicine data attributes.
        Returns a list of validation error messages. An empty list indicates valid data.
        """
        errors = []

        if not self.medicine_code or not str(self.medicine_code).strip():
            errors.append("Medicine code is required.")
        
        if not self.medicine_name or not str(self.medicine_name).strip():
            errors.append("Medicine name is required.")

        if not self.category or not str(self.category).strip():
            errors.append("Category is required.")

        if not self.manufacturer or not str(self.manufacturer).strip():
            errors.append("Manufacturer is required.")

        if not self.batch_no or not str(self.batch_no).strip():
            errors.append("Batch number is required.")

        try:
            val_price = float(self.price)
            if val_price < 0:
                errors.append("Price must be a non-negative number.")
        except (ValueError, TypeError):
            errors.append("Price must be a valid numeric value.")

        try:
            val_qty = int(self.quantity)
            if val_qty < 0:
                errors.append("Quantity must be a non-negative integer.")
        except (ValueError, TypeError):
            errors.append("Quantity must be a valid integer.")

        if not self.expiry_date:
            errors.append("Expiry date is required.")
        else:
            try:
                datetime.strptime(self.expiry_date, "%Y-%m-%d")
            except ValueError:
                errors.append("Expiry date must be in YYYY-MM-DD format.")

        return errors

    @property
    def is_expired(self) -> bool:
        """Returns True if the medicine has passed its expiry date."""
        try:
            exp = datetime.strptime(self.expiry_date, "%Y-%m-%d").date()
            return exp < datetime.now().date()
        except ValueError:
            return False

    @property
    def is_expiring_soon(self) -> bool:
        """Returns True if medicine expires within the configured threshold (e.g. 30 days)."""
        try:
            exp = datetime.strptime(self.expiry_date, "%Y-%m-%d").date()
            today = datetime.now().date()
            return today <= exp <= (today + timedelta(days=EXPIRING_SOON_DAYS))
        except ValueError:
            return False

    @property
    def stock_status(self) -> str:
        """Returns stock classification string: 'Out of Stock', 'Low Stock', or 'Available'."""
        if self.quantity == 0:
            return "Out of Stock"
        elif self.quantity <= LOW_STOCK_THRESHOLD:
            return "Low Stock"
        return "Available"

    @property
    def expiry_status(self) -> str:
        """Returns expiry status string: 'Expired', 'Expiring Soon', or 'Valid'."""
        if self.is_expired:
            return "Expired"
        elif self.is_expiring_soon:
            return "Expiring Soon"
        return "Valid"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "medicine_id": self.medicine_id,
            "medicine_code": self.medicine_code,
            "medicine_name": self.medicine_name,
            "category": self.category,
            "manufacturer": self.manufacturer,
            "batch_no": self.batch_no,
            "price": self.price,
            "quantity": self.quantity,
            "expiry_date": self.expiry_date,
            "stock_status": self.stock_status,
            "expiry_status": self.expiry_status,
            "store_id": self.store_id
        }
