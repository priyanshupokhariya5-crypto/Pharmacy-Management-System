"""
Purchase and PurchaseItem domain models for pharmacy supplier procurement.
Supports multi-store tenancy with store_id.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class PurchaseItem:
    item_id: Optional[int]
    purchase_id: Optional[int]
    medicine_id: int
    quantity: int
    unit_cost: float
    subtotal: float
    batch_id: Optional[int] = None
    medicine_name: Optional[str] = None
    batch_number: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "PurchaseItem":
        keys = row.keys() if hasattr(row, "keys") else []
        return cls(
            item_id=row["item_id"],
            purchase_id=row["purchase_id"],
            medicine_id=row["medicine_id"],
            quantity=int(row["quantity"]),
            unit_cost=float(row["unit_cost"]),
            subtotal=float(row["subtotal"]),
            batch_id=row["batch_id"] if "batch_id" in keys else None,
            medicine_name=row["medicine_name"] if "medicine_name" in keys else None,
            batch_number=row["batch_number"] if "batch_number" in keys else None
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "purchase_id": self.purchase_id,
            "medicine_id": self.medicine_id,
            "quantity": self.quantity,
            "unit_cost": self.unit_cost,
            "subtotal": self.subtotal,
            "batch_id": self.batch_id,
            "medicine_name": self.medicine_name,
            "batch_number": self.batch_number
        }


@dataclass
class Purchase:
    purchase_id: Optional[int]
    store_id: str
    supplier_id: int
    invoice_number: str
    purchase_date: str
    total_amount: float
    payment_status: str = "PAID"  # PAID, PENDING, PARTIAL
    status: str = "RECEIVED"  # DRAFT, ORDERED, RECEIVED, CANCELLED
    received_by: Optional[int] = None
    notes: Optional[str] = None
    items: List[PurchaseItem] = field(default_factory=list)
    supplier_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Purchase":
        keys = row.keys() if hasattr(row, "keys") else []
        return cls(
            purchase_id=row["purchase_id"],
            store_id=row["store_id"],
            supplier_id=row["supplier_id"],
            invoice_number=row["invoice_number"],
            purchase_date=row["purchase_date"],
            total_amount=float(row["total_amount"]),
            payment_status=row["payment_status"] if "payment_status" in keys else "PAID",
            status=row["status"] if "status" in keys and row["status"] else "RECEIVED",
            received_by=row["received_by"] if "received_by" in keys else None,
            notes=row["notes"] if "notes" in keys else None,
            supplier_name=row["supplier_name"] if "supplier_name" in keys else None,
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None
        )

    def validate(self) -> List[str]:
        errors = []
        if not self.invoice_number or not str(self.invoice_number).strip():
            errors.append("Purchase invoice number is required.")
        if not self.supplier_id or int(self.supplier_id) <= 0:
            errors.append("Valid Supplier ID is required.")
        if not self.store_id or not str(self.store_id).strip():
            errors.append("Store ID is required.")
        if self.total_amount < 0:
            errors.append("Total amount cannot be negative.")
        if self.payment_status not in ("PAID", "PENDING", "PARTIAL"):
            errors.append(f"Invalid payment status '{self.payment_status}'.")
        if self.status not in ("DRAFT", "ORDERED", "RECEIVED", "CANCELLED"):
            errors.append(f"Invalid purchase status '{self.status}'.")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purchase_id": self.purchase_id,
            "store_id": self.store_id,
            "supplier_id": self.supplier_id,
            "invoice_number": self.invoice_number,
            "purchase_date": self.purchase_date,
            "total_amount": self.total_amount,
            "payment_status": self.payment_status,
            "status": self.status,
            "received_by": self.received_by,
            "notes": self.notes,
            "supplier_name": self.supplier_name,
            "items": [it.to_dict() for it in self.items],
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
