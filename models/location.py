"""
StorageLocation domain model for pharmacy physical shelf/rack/bin organization.
Supports multi-store tenancy with store_id.
"""
from dataclasses import dataclass
from typing import Optional, List, Dict, Any


@dataclass
class StorageLocation:
    location_id: Optional[int]
    store_id: str
    shelf_code: str
    rack: Optional[str] = None
    bin: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "StorageLocation":
        """Factory method to construct a StorageLocation from an SQLite Row."""
        keys = row.keys() if hasattr(row, "keys") else []
        return cls(
            location_id=row["location_id"],
            store_id=row["store_id"],
            shelf_code=row["shelf_code"],
            rack=row["rack"] if "rack" in keys else None,
            bin=row["bin"] if "bin" in keys else None,
            description=row["description"] if "description" in keys else None,
            is_active=bool(row["is_active"]) if "is_active" in keys else True,
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None
        )

    def validate(self) -> List[str]:
        """Validates storage location attributes."""
        errors = []
        if not self.shelf_code or not str(self.shelf_code).strip():
            errors.append("Shelf code is required.")
        if not self.store_id or not str(self.store_id).strip():
            errors.append("Store ID is required.")
        return errors

    @property
    def display_name(self) -> str:
        parts = [self.shelf_code]
        if self.rack:
            parts.append(f"Rack: {self.rack}")
        if self.bin:
            parts.append(f"Bin: {self.bin}")
        return " | ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location_id": self.location_id,
            "store_id": self.store_id,
            "shelf_code": self.shelf_code,
            "rack": self.rack,
            "bin": self.bin,
            "description": self.description,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
