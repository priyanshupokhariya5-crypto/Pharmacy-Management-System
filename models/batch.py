"""
InventoryBatch domain model for individual stock batches and FEFO tracking.
Supports multi-store tenancy with store_id and physical storage location mapping.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class InventoryBatch:
    batch_id: Optional[int]
    store_id: str
    medicine_id: int
    batch_number: str
    expiry_date: str  # YYYY-MM-DD
    initial_quantity: int
    current_quantity: int
    selling_price: float
    location_id: Optional[int] = None
    supplier_id: Optional[int] = None
    mfg_date: Optional[str] = None
    received_date: Optional[str] = None
    purchase_cost: Optional[float] = None
    status: str = "Active"  # Active, Expired, Quarantined, Recalled
    verification_flag: int = 0  # 1 if legacy data missing supplier/mfg details
    notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    shelf_code: Optional[str] = None  # joined for UI convenience

    @classmethod
    def from_row(cls, row) -> "InventoryBatch":
        """Factory method to construct an InventoryBatch from an SQLite Row."""
        keys = row.keys() if hasattr(row, "keys") else []
        return cls(
            batch_id=row["batch_id"],
            store_id=row["store_id"],
            medicine_id=row["medicine_id"],
            batch_number=row["batch_number"],
            expiry_date=row["expiry_date"],
            initial_quantity=int(row["initial_quantity"]),
            current_quantity=int(row["current_quantity"]),
            selling_price=float(row["selling_price"]),
            location_id=row["location_id"] if "location_id" in keys else None,
            supplier_id=row["supplier_id"] if "supplier_id" in keys else None,
            mfg_date=row["mfg_date"] if "mfg_date" in keys else None,
            received_date=row["received_date"] if "received_date" in keys else None,
            purchase_cost=float(row["purchase_cost"]) if "purchase_cost" in keys and row["purchase_cost"] is not None else None,
            status=row["status"] if "status" in keys else "Active",
            verification_flag=int(row["verification_flag"]) if "verification_flag" in keys else 0,
            notes=row["notes"] if "notes" in keys else None,
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None,
            shelf_code=row["shelf_code"] if "shelf_code" in keys else None
        )

    def is_expired(self, reference_date: Optional[str] = None) -> bool:
        """
        Determines whether the batch is expired relative to reference_date (or current local date).
        Standard rule: A batch expiring on 2026-10-25 is expired once the date is 2026-10-26 or later.
        """
        try:
            exp = datetime.strptime(self.expiry_date, "%Y-%m-%d").date()
            ref = datetime.strptime(reference_date, "%Y-%m-%d").date() if reference_date else datetime.now().date()
            return exp < ref
        except (ValueError, TypeError):
            return False

    def days_until_expiry(self, reference_date: Optional[str] = None) -> int:
        """Returns days remaining until expiry. Negative if already expired."""
        try:
            exp = datetime.strptime(self.expiry_date, "%Y-%m-%d").date()
            ref = datetime.strptime(reference_date, "%Y-%m-%d").date() if reference_date else datetime.now().date()
            return (exp - ref).days
        except (ValueError, TypeError):
            return 0

    @property
    def is_eligible_for_sale(self) -> bool:
        """Returns True if the batch is active, has remaining stock, and has not passed its expiry date."""
        if self.status != "Active":
            return False
        if self.current_quantity <= 0:
            return False
        if self.is_expired():
            return False
        return True

    def validate(self) -> List[str]:
        """Validates batch data attributes before creation or update."""
        errors = []
        if not self.batch_number or not str(self.batch_number).strip():
            errors.append("Batch number is required.")
        if not self.store_id or not str(self.store_id).strip():
            errors.append("Store ID is required.")
        if not self.medicine_id or int(self.medicine_id) <= 0:
            errors.append("Valid Medicine ID is required.")
        if self.initial_quantity < 0:
            errors.append("Initial quantity cannot be negative.")
        if self.current_quantity < 0:
            errors.append("Current quantity cannot be negative.")
        if self.current_quantity > self.initial_quantity:
            errors.append("Current quantity cannot exceed initial quantity without an adjustment.")
        if self.selling_price < 0:
            errors.append("Selling price must be non-negative.")
        if self.purchase_cost is not None and self.purchase_cost < 0:
            errors.append("Purchase cost must be non-negative.")
        if not self.expiry_date:
            errors.append("Expiry date is required.")
        else:
            try:
                datetime.strptime(self.expiry_date, "%Y-%m-%d")
            except ValueError:
                errors.append("Expiry date must be in YYYY-MM-DD format.")
        if self.mfg_date:
            try:
                datetime.strptime(self.mfg_date, "%Y-%m-%d")
            except ValueError:
                errors.append("Manufacturing date must be in YYYY-MM-DD format.")
        if self.status not in ("Active", "Expired", "Quarantined", "Recalled"):
            errors.append(f"Invalid batch status '{self.status}'. Must be Active, Expired, Quarantined, or Recalled.")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "store_id": self.store_id,
            "medicine_id": self.medicine_id,
            "batch_number": self.batch_number,
            "expiry_date": self.expiry_date,
            "initial_quantity": self.initial_quantity,
            "current_quantity": self.current_quantity,
            "selling_price": self.selling_price,
            "location_id": self.location_id,
            "supplier_id": self.supplier_id,
            "mfg_date": self.mfg_date,
            "received_date": self.received_date,
            "purchase_cost": self.purchase_cost,
            "status": self.status,
            "verification_flag": self.verification_flag,
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "shelf_code": self.shelf_code
        }
