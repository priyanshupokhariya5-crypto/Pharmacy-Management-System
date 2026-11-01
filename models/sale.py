"""
Sale and SaleItem domain models for pharmacy transactions.
Supports multi-store tenancy with store_id.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class SaleItem:
    item_id: Optional[int]
    sale_id: Optional[int]
    medicine_id: int
    medicine_name: str
    quantity: int
    price: float
    subtotal: float
    store_id: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "SaleItem":
        keys = row.keys() if hasattr(row, "keys") else []
        med_name = row["medicine_name"] if "medicine_name" in keys else f"ID:{row['medicine_id']}"
        return cls(
            item_id=row["item_id"],
            sale_id=row["sale_id"],
            medicine_id=row["medicine_id"],
            medicine_name=med_name,
            quantity=int(row["quantity"]),
            price=float(row["price"]),
            subtotal=float(row["subtotal"]),
            store_id=row["store_id"] if "store_id" in keys else None
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "sale_id": self.sale_id,
            "medicine_id": self.medicine_id,
            "medicine_name": self.medicine_name,
            "quantity": self.quantity,
            "price": self.price,
            "subtotal": self.subtotal,
            "store_id": self.store_id
        }


@dataclass
class Sale:
    sale_id: Optional[int]
    invoice_number: Optional[str]
    patient_name: Optional[str]
    patient_phone: Optional[str]
    patient_age: Optional[int]
    sale_date: str
    total_amount: float
    user_id: Optional[int]
    username: Optional[str] = None
    items: List[SaleItem] = field(default_factory=list)
    store_id: Optional[str] = None
    subtotal: float = 0.0
    discount_amount: float = 0.0
    tax_amount: float = 0.0
    rounding_amount: float = 0.0
    payment_method: str = "Cash"
    payment_reference: Optional[str] = None
    status: str = "COMPLETED"

    @classmethod
    def from_row(cls, row) -> "Sale":
        keys = row.keys() if hasattr(row, "keys") else []
        u_name = row["username"] if "username" in keys else None
        tot = float(row["total_amount"])
        sub = float(row["subtotal"]) if "subtotal" in keys and row["subtotal"] is not None else tot
        disc = float(row["discount_amount"]) if "discount_amount" in keys and row["discount_amount"] is not None else 0.0
        tax = float(row["tax_amount"]) if "tax_amount" in keys and row["tax_amount"] is not None else 0.0
        round_amt = float(row["rounding_amount"]) if "rounding_amount" in keys and row["rounding_amount"] is not None else 0.0
        pm = row["payment_method"] if "payment_method" in keys and row["payment_method"] else "Cash"
        pref = row["payment_reference"] if "payment_reference" in keys else None
        stat = row["status"] if "status" in keys and row["status"] else "COMPLETED"
        return cls(
            sale_id=row["sale_id"],
            invoice_number=row["invoice_number"] if "invoice_number" in keys else None,
            patient_name=row["patient_name"] if "patient_name" in keys else None,
            patient_phone=row["patient_phone"] if "patient_phone" in keys else None,
            patient_age=row["patient_age"] if "patient_age" in keys else None,
            sale_date=row["sale_date"],
            total_amount=tot,
            user_id=row["user_id"],
            username=u_name,
            store_id=row["store_id"] if "store_id" in keys else None,
            subtotal=sub,
            discount_amount=disc,
            tax_amount=tax,
            rounding_amount=round_amt,
            payment_method=pm,
            payment_reference=pref,
            status=stat
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sale_id": self.sale_id,
            "invoice_number": self.invoice_number,
            "patient_name": self.patient_name,
            "patient_phone": self.patient_phone,
            "patient_age": self.patient_age,
            "sale_date": self.sale_date,
            "subtotal": self.subtotal,
            "discount_amount": self.discount_amount,
            "tax_amount": self.tax_amount,
            "rounding_amount": self.rounding_amount,
            "total_amount": self.total_amount,
            "payment_method": self.payment_method,
            "payment_reference": self.payment_reference,
            "status": self.status,
            "user_id": self.user_id,
            "username": self.username,
            "items_count": len(self.items),
            "store_id": self.store_id
        }


@dataclass
class SaleReturnItem:
    return_item_id: Optional[int]
    return_id: Optional[int]
    sale_item_id: int
    medicine_id: int
    medicine_name: str
    quantity: int
    unit_price: float
    refund_amount: float
    batch_id: Optional[int] = None
    restocked: int = 1
    restock_condition: str = "SELLABLE"

    @classmethod
    def from_row(cls, row) -> "SaleReturnItem":
        keys = row.keys() if hasattr(row, "keys") else []
        med_name = row["medicine_name"] if "medicine_name" in keys else f"ID:{row['medicine_id']}"
        return cls(
            return_item_id=row["return_item_id"],
            return_id=row["return_id"],
            sale_item_id=row["sale_item_id"],
            medicine_id=row["medicine_id"],
            medicine_name=med_name,
            quantity=int(row["quantity"]),
            unit_price=float(row["unit_price"]),
            refund_amount=float(row["refund_amount"]),
            batch_id=row["batch_id"] if "batch_id" in keys else None,
            restocked=int(row["restocked"]) if "restocked" in keys else 1,
            restock_condition=row["restock_condition"] if "restock_condition" in keys and row["restock_condition"] else "SELLABLE"
        )


@dataclass
class SaleReturn:
    return_id: Optional[int]
    store_id: str
    sale_id: int
    invoice_number: str
    return_date: str
    total_refund: float
    refund_method: str
    reason: str
    created_by: Optional[int]
    username: Optional[str] = None
    created_at: Optional[str] = None
    items: List[SaleReturnItem] = field(default_factory=list)

    @classmethod
    def from_row(cls, row) -> "SaleReturn":
        keys = row.keys() if hasattr(row, "keys") else []
        u_name = row["username"] if "username" in keys else None
        return cls(
            return_id=row["return_id"],
            store_id=row["store_id"],
            sale_id=row["sale_id"],
            invoice_number=row["invoice_number"],
            return_date=row["return_date"],
            total_refund=float(row["total_refund"]),
            refund_method=row["refund_method"] if "refund_method" in keys and row["refund_method"] else "Cash",
            reason=row["reason"] if "reason" in keys and row["reason"] else "",
            created_by=row["created_by"] if "created_by" in keys else None,
            username=u_name,
            created_at=row["created_at"] if "created_at" in keys else None
        )

