"""
Role-Based Access Control (RBAC) Architecture and Backend Authorization Guards.
Defines backend authorization guards (require_permission, require_store_access)
and re-exports canonical roles and permissions from models.user.
"""
from typing import Optional, Any
from models.user import (
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_INVENTORY_MANAGER,
    ALL_ROLES,
    ROLE_PERMISSIONS,
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
    normalize_role,
    has_permission,
)


def require_permission(acting_user: Any, permission: str, action_desc: str = "This operation") -> None:
    """
    Backend RBAC guard: Raises PermissionError if acting_user lacks the required permission.
    If acting_user is None (legacy unauthenticated callers or internal tasks), operation is permitted.
    """
    if acting_user is None:
        return

    user_role = getattr(acting_user, "role", None)
    if not has_permission(user_role, permission):
        username = getattr(acting_user, "username", "anonymous")
        raise PermissionError(
            f"Access Denied: {action_desc} requires '{permission}' permission. "
            f"User '{username}' with role '{user_role}' is not authorized."
        )


def require_store_access(acting_user: Any, target_store_id: str, action_desc: str = "This operation") -> None:
    """
    Multi-store tenant isolation guard: Raises PermissionError if acting_user belongs to a different store.
    If acting_user is None or target_store_id is empty, operation is permitted.
    """
    if acting_user is None or not target_store_id:
        return

    user_store = getattr(acting_user, "store_id", None)
    if user_store and user_store != target_store_id:
        username = getattr(acting_user, "username", "anonymous")
        raise PermissionError(
            f"Store Access Denied: User '{username}' belongs to store '{user_store}' "
            f"and is not authorized to access or modify resources in store '{target_store_id}'."
        )
