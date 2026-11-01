"""
StockMovement domain model representing the immutable inventory ledger.
Enforces standard sign convention:
  - Positive (+) delta: Stock additions (MIGRATION_OPENING, PURCHASE_RECEIPT, CUSTOMER_RETURN, positive ADJUSTMENT)
  - Negative (-) delta: Stock deductions (SALE_DISPENSE, EXPIRY_WRITE_OFF, negative ADJUSTMENT, STORE_TRANSFER)
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

VALID_MOVEMENT_TYPES = (
    "MIGRATION_OPENING",
    "PURCHASE_RECEIPT",
    "SALE_DISPENSE",
    "CUSTOMER_RETURN",
    "STOCK_ADJUSTMENT",
    "STORE_TRANSFER",
    "EXPIRY_WRITE_OFF",
    "RECALL_QUARANTINE"
)


@dataclass
class StockMovement:
    movement_id: Optional[int]
    store_id: str
    medicine_id: int
    batch_id: int
    movement_type: str
    quantity_delta: int
    reference_type: Optional[str] = None
    reference_id: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "StockMovement":
        keys = row.keys() if hasattr(row, "keys") else []
        return cls(
            movement_id=row["movement_id"],
            store_id=row["store_id"],
            medicine_id=row["medicine_id"],
            batch_id=row["batch_id"],
            movement_type=row["movement_type"],
            quantity_delta=int(row["quantity_delta"]),
            reference_type=row["reference_type"] if "reference_type" in keys else None,
            reference_id=row["reference_id"] if "reference_id" in keys else None,
            notes=row["notes"] if "notes" in keys else None,
            created_by=row["created_by"] if "created_by" in keys else None,
            created_at=row["created_at"] if "created_at" in keys else None
        )

    def validate(self) -> List[str]:
        errors = []
        if not self.store_id or not str(self.store_id).strip():
            errors.append("Store ID is required.")
        if not self.medicine_id or int(self.medicine_id) <= 0:
            errors.append("Valid Medicine ID is required.")
        if not self.batch_id or int(self.batch_id) <= 0:
            errors.append("Valid Batch ID is required.")
        if self.movement_type not in VALID_MOVEMENT_TYPES:
            errors.append(f"Invalid movement type '{self.movement_type}'.")
        if self.quantity_delta == 0 and self.movement_type != "MIGRATION_OPENING":
            errors.append("Quantity delta cannot be zero for non-opening stock movements.")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "movement_id": self.movement_id,
            "store_id": self.store_id,
            "medicine_id": self.medicine_id,
            "batch_id": self.batch_id,
            "movement_type": self.movement_type,
            "quantity_delta": self.quantity_delta,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "notes": self.notes,
            "created_by": self.created_by,
            "created_at": self.created_at
        }
