"""
Supplier domain model for pharmacy inventory vendor management.
Supports multi-store tenancy with store_id.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class Supplier:
    supplier_id: Optional[int]
    store_id: str
    supplier_code: str
    supplier_name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "Supplier":
        """Factory method to construct a Supplier from an SQLite Row."""
        keys = row.keys() if hasattr(row, "keys") else []
        return cls(
            supplier_id=row["supplier_id"],
            store_id=row["store_id"],
            supplier_code=row["supplier_code"],
            supplier_name=row["supplier_name"],
            contact_person=row["contact_person"] if "contact_person" in keys else None,
            phone=row["phone"] if "phone" in keys else None,
            email=row["email"] if "email" in keys else None,
            address=row["address"] if "address" in keys else None,
            gst_number=row["gst_number"] if "gst_number" in keys else None,
            is_active=bool(row["is_active"]) if "is_active" in keys else True,
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None
        )

    def validate(self) -> List[str]:
        """Validates supplier attributes before creation or update."""
        errors = []
        if not self.supplier_name or not str(self.supplier_name).strip():
            errors.append("Supplier name is required.")
        if not self.supplier_code or not str(self.supplier_code).strip():
            errors.append("Supplier code is required.")
        if not self.store_id or not str(self.store_id).strip():
            errors.append("Store ID is required.")
        if self.phone:
            clean_phone = str(self.phone).strip()
            if not clean_phone.isdigit() or len(clean_phone) != 10:
                errors.append("Phone number must contain exactly 10 digits when provided.")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supplier_id": self.supplier_id,
            "store_id": self.store_id,
            "supplier_code": self.supplier_code,
            "supplier_name": self.supplier_name,
            "contact_person": self.contact_person,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "gst_number": self.gst_number,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
