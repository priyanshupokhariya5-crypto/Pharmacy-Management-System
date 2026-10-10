"""
Sale and SaleItem domain models for pharmacy transactions.
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

    @classmethod
    def from_row(cls, row) -> "SaleItem":
        med_name = row["medicine_name"] if "medicine_name" in row.keys() else f"ID:{row['medicine_id']}"
        return cls(
            item_id=row["item_id"],
            sale_id=row["sale_id"],
            medicine_id=row["medicine_id"],
            medicine_name=med_name,
            quantity=int(row["quantity"]),
            price=float(row["price"]),
            subtotal=float(row["subtotal"])
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "sale_id": self.sale_id,
            "medicine_id": self.medicine_id,
            "medicine_name": self.medicine_name,
            "quantity": self.quantity,
            "price": self.price,
            "subtotal": self.subtotal
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

    @classmethod
    def from_row(cls, row) -> "Sale":
        u_name = row["username"] if "username" in row.keys() else None
        return cls(
            sale_id=row["sale_id"],
            invoice_number=row["invoice_number"] if "invoice_number" in row.keys() else None,
            patient_name=row["patient_name"] if "patient_name" in row.keys() else None,
            patient_phone=row["patient_phone"] if "patient_phone" in row.keys() else None,
            patient_age=row["patient_age"] if "patient_age" in row.keys() else None,
            sale_date=row["sale_date"],
            total_amount=float(row["total_amount"]),
            user_id=row["user_id"],
            username=u_name
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sale_id": self.sale_id,
            "invoice_number": self.invoice_number,
            "patient_name": self.patient_name,
            "patient_phone": self.patient_phone,
            "patient_age": self.patient_age,
            "sale_date": self.sale_date,
            "total_amount": self.total_amount,
            "user_id": self.user_id,
            "username": self.username,
            "items_count": len(self.items)
        }
