"""
User domain model representing authenticated application users.
Supports multi-store tenancy with store_id, store_name, full_name, email, and is_active flag.
Defines canonical roles, granular permissions, the permission matrix, and role normalization.
"""
from dataclasses import dataclass
from typing import Optional, Dict, Set, Any

# ============================================================================
# 1. Canonical Role Constants
# ============================================================================
ROLE_OWNER = "Owner"
ROLE_ADMIN = "Admin"
ROLE_PHARMACIST = "Pharmacist"
ROLE_CASHIER = "Cashier"
ROLE_INVENTORY_MANAGER = "Inventory Manager"

ALL_ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_PHARMACIST, ROLE_CASHIER, ROLE_INVENTORY_MANAGER)

# ============================================================================
# 2. Granular Permission Constants
# ============================================================================
PERM_VIEW_DASHBOARD = "view_dashboard"
PERM_VIEW_FINANCIALS = "view_financials"
PERM_VIEW_REPORTS = "view_reports"
PERM_VIEW_AUDIT_LOGS = "view_audit_logs"

PERM_MANAGE_USERS = "manage_users"
PERM_MANAGE_STORE_SETTINGS = "manage_store_settings"

PERM_VIEW_MEDICINES = "view_medicines"
PERM_ADD_MEDICINE = "add_medicine"
PERM_UPDATE_MEDICINE = "update_medicine"
PERM_DELETE_MEDICINE = "delete_medicine"

PERM_PROCESS_SALE = "process_sale"
PERM_VIEW_SALES_HISTORY = "view_sales_history"
PERM_REPRINT_RECEIPT = "reprint_receipt"

PERM_MANAGE_INVENTORY = "manage_inventory"
PERM_VIEW_STOCK_ALERTS = "view_stock_alerts"
PERM_DISPENSE_MEDICINE = "dispense_medicine"
PERM_MANAGE_SUPPLIERS = "manage_suppliers"
PERM_MANAGE_PURCHASES = "manage_purchases"

PERM_VIEW_FMEA = "view_fmea"
PERM_VIEW_SQC = "view_sqc"

# ============================================================================
# 3. Role-Permission Matrix
# ============================================================================
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    ROLE_OWNER: {
        PERM_VIEW_DASHBOARD,
        PERM_VIEW_FINANCIALS,
        PERM_VIEW_REPORTS,
        PERM_VIEW_AUDIT_LOGS,
        PERM_MANAGE_USERS,
        PERM_MANAGE_STORE_SETTINGS,
        PERM_VIEW_MEDICINES,
        PERM_ADD_MEDICINE,
        PERM_UPDATE_MEDICINE,
        PERM_DELETE_MEDICINE,
        PERM_PROCESS_SALE,
        PERM_VIEW_SALES_HISTORY,
        PERM_REPRINT_RECEIPT,
        PERM_MANAGE_INVENTORY,
        PERM_VIEW_STOCK_ALERTS,
        PERM_DISPENSE_MEDICINE,
        PERM_MANAGE_SUPPLIERS,
        PERM_MANAGE_PURCHASES,
        PERM_VIEW_FMEA,
        PERM_VIEW_SQC,
    },
    ROLE_ADMIN: {
        PERM_VIEW_DASHBOARD,
        PERM_VIEW_FINANCIALS,
        PERM_VIEW_REPORTS,
        PERM_VIEW_AUDIT_LOGS,
        PERM_MANAGE_USERS,
        PERM_MANAGE_STORE_SETTINGS,
        PERM_VIEW_MEDICINES,
        PERM_ADD_MEDICINE,
        PERM_UPDATE_MEDICINE,
        PERM_DELETE_MEDICINE,
        PERM_PROCESS_SALE,
        PERM_VIEW_SALES_HISTORY,
        PERM_REPRINT_RECEIPT,
        PERM_MANAGE_INVENTORY,
        PERM_VIEW_STOCK_ALERTS,
        PERM_DISPENSE_MEDICINE,
        PERM_MANAGE_SUPPLIERS,
        PERM_MANAGE_PURCHASES,
        PERM_VIEW_FMEA,
        PERM_VIEW_SQC,
    },
    ROLE_PHARMACIST: {
        PERM_VIEW_DASHBOARD,
        PERM_VIEW_MEDICINES,
        PERM_ADD_MEDICINE,
        PERM_UPDATE_MEDICINE,
        PERM_DISPENSE_MEDICINE,
        PERM_VIEW_STOCK_ALERTS,
        PERM_VIEW_FMEA,
    },
    ROLE_CASHIER: {
        PERM_VIEW_DASHBOARD,
        PERM_VIEW_MEDICINES,
        PERM_PROCESS_SALE,
        PERM_VIEW_SALES_HISTORY,
        PERM_REPRINT_RECEIPT,
    },
    ROLE_INVENTORY_MANAGER: {
        PERM_VIEW_DASHBOARD,
        PERM_VIEW_MEDICINES,
        PERM_ADD_MEDICINE,
        PERM_UPDATE_MEDICINE,
        PERM_MANAGE_INVENTORY,
        PERM_MANAGE_PURCHASES,
        PERM_VIEW_STOCK_ALERTS,
        PERM_VIEW_SQC,
    },
}


def normalize_role(role: Optional[str]) -> str:
    """Maps a role string into a canonical role. Returns 'Unknown' for unrecognized roles."""
    if not role or not isinstance(role, str):
        return "Unknown"
    cleaned = role.strip().lower()
    if cleaned in ("owner", "admin"):
        return ROLE_OWNER if cleaned == "owner" else ROLE_ADMIN
    elif cleaned == "pharmacist":
        return ROLE_PHARMACIST
    elif cleaned == "cashier":
        return ROLE_CASHIER
    elif cleaned in ("inventory manager", "inventory_manager", "inventory"):
        return ROLE_INVENTORY_MANAGER
    return "Unknown"


def has_permission(role: Optional[str], permission: str) -> bool:
    """Checks if a given role has the requested permission."""
    canonical = normalize_role(role)
    perms = ROLE_PERMISSIONS.get(canonical, set())
    return permission in perms


@dataclass
class User:
    user_id: Optional[int]
    username: str
    role: str  # 'Owner', 'Admin', 'Pharmacist', 'Cashier', or 'Inventory Manager'
    store_id: Optional[str] = "STORE-LEGACY-001"
    store_name: Optional[str] = "Default Pharmacy Store"
    full_name: Optional[str] = ""
    email: Optional[str] = ""
    is_active: bool = True

    @property
    def canonical_role(self) -> str:
        """Returns the normalized canonical role string."""
        return normalize_role(self.role)

    @property
    def is_owner(self) -> bool:
        """Returns True if the user is a Store Owner or System Admin."""
        return self.canonical_role in (ROLE_OWNER, ROLE_ADMIN)

    @property
    def is_admin(self) -> bool:
        """Backward compatibility: returns True for Admin and Owner roles."""
        return self.canonical_role in (ROLE_ADMIN, ROLE_OWNER)

    @property
    def is_pharmacist(self) -> bool:
        """Returns True if the user is a Pharmacist."""
        return self.canonical_role == ROLE_PHARMACIST

    @property
    def is_cashier(self) -> bool:
        """Returns True if the user is a Cashier."""
        return self.canonical_role == ROLE_CASHIER

    @property
    def is_inventory_manager(self) -> bool:
        """Returns True if the user is an Inventory Manager."""
        return self.canonical_role == ROLE_INVENTORY_MANAGER

    def has_permission(self, permission: str) -> bool:
        """Checks if user has the specified RBAC permission."""
        if not self.is_active:
            return False
        return has_permission(self.role, permission)

    @classmethod
    def from_row(cls, row) -> "User":
        """Creates a User instance from an SQLite Row object."""
        keys = row.keys() if hasattr(row, "keys") else []
        is_active_val = True
        if "is_active" in keys and row["is_active"] is not None:
            is_active_val = bool(row["is_active"])

        return cls(
            user_id=row["user_id"],
            username=row["username"],
            role=row["role"],
            store_id=row["store_id"] if "store_id" in keys and row["store_id"] else "STORE-LEGACY-001",
            store_name=row["store_name"] if "store_name" in keys and row["store_name"] else "Default Pharmacy Store",
            full_name=row["full_name"] if "full_name" in keys and row["full_name"] else "",
            email=row["email"] if "email" in keys and row["email"] else "",
            is_active=is_active_val,
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
            "is_active": self.is_active,
        }
