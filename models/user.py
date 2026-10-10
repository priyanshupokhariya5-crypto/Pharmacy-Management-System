

















































































"""
User domain model representing authenticated application users.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class User:
    user_id: Optional[int]
    username: str
    role: str  # 'Admin' or 'Pharmacist'

    @property
    def is_admin(self) -> bool:
        return self.role.lower() == "admin"

    @property
    def is_pharmacist(self) -> bool:
        return self.role.lower() == "pharmacist"

    @classmethod
    def from_row(cls, row) -> "User":
        """Creates a User instance from an SQLite Row object."""
        return cls(
            user_id=row["user_id"],
            username=row["username"],
            role=row["role"]
        )

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role
        }
