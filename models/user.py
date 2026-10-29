"""
User domain model representing authenticated application users.
Supports multi-store tenancy with store_id, store_name, full_name, and email.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    user_id: Optional[int]
    username: str
    role: str  # 'Admin', 'Pharmacist', or 'Owner'
    store_id: Optional[str] = "STORE-LEGACY-001"
    store_name: Optional[str] = "Default Pharmacy Store"
    full_name: Optional[str] = ""
    email: Optional[str] = ""

    @property
    def is_admin(self) -> bool:
        return self.role.lower() in ("admin", "owner")

    @property
    def is_pharmacist(self) -> bool:
        return self.role.lower() == "pharmacist"

    @classmethod
    def from_row(cls, row) -> "User":
        """Creates a User instance from an SQLite Row object."""
        keys = row.keys() if hasattr(row, "keys") else []
        return cls(
            user_id=row["user_id"],
            username=row["username"],
            role=row["role"],
            store_id=row["store_id"] if "store_id" in keys and row["store_id"] else "STORE-LEGACY-001",
            store_name=row["store_name"] if "store_name" in keys and row["store_name"] else "Default Pharmacy Store",
            full_name=row["full_name"] if "full_name" in keys and row["full_name"] else "",
            email=row["email"] if "email" in keys and row["email"] else "",
        )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "store_id": self.store_id,
            "store_name": self.store_name,
            "full_name": self.full_name,
            "email": self.email,
        }
