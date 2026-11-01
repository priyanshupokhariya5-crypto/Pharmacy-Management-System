"""
Audit Logging Service for tracking sensitive system, security, and transaction events.
Guarantees multi-store isolation and role-based access control.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from database.db import Database, get_db
from utils.logger import get_app_logger
from services.rbac import require_permission, require_store_access, PERM_VIEW_AUDIT_LOGS


class AuditService:
    """Manages recording and querying structured audit logs."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_db()
        self.logger = get_app_logger()

    def _table_exists(self, table_name: str) -> bool:
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def log_event(
        self,
        store_id: Optional[str],
        user_id: Optional[int],
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = "127.0.0.1"
    ) -> bool:
        """
        Records a sensitive audit event into the audit_logs table.
        Non-blocking: if the audit_logs table does not exist (e.g. unmigrated DB),
        logs to application file logger without throwing an exception.
        """
        self.logger.log_event("AUDIT", f"[{action}] store={store_id} user={user_id} entity={entity_type}:{entity_id} - {details}")

        if not self._table_exists("audit_logs"):
            return False

        try:
            # Validate user_id exists in users table to satisfy foreign key constraint if users table exists
            valid_user_id = None
            if user_id is not None:
                user_row = self.db.fetch_one("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                if user_row:
                    valid_user_id = user_id

            # Validate store_id exists
            valid_store_id = store_id
            if store_id:
                store_row = self.db.fetch_one("SELECT store_id FROM stores WHERE store_id = ?", (store_id,))
                if not store_row:
                    valid_store_id = None

            self.db.execute(
                """
                INSERT INTO audit_logs (store_id, user_id, action, entity_type, entity_id, details, ip_address)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (valid_store_id, valid_user_id, action, entity_type, str(entity_id) if entity_id else None, details, ip_address)
            )
            return True
        except Exception as e:
            self.logger.error(f"Failed to write audit log: {e}")
            return False

    def get_audit_logs(
        self,
        store_id: Optional[str] = None,
        action_filter: Optional[str] = None,
        limit: int = 100,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves recent audit logs, guarded by PERM_VIEW_AUDIT_LOGS and store isolation.
        """
        if acting_user is not None:
            require_permission(acting_user, PERM_VIEW_AUDIT_LOGS, "Viewing audit logs")
            if store_id:
                require_store_access(acting_user, store_id, "Viewing audit logs")

        if not self._table_exists("audit_logs"):
            return []

        query = """
        SELECT a.log_id, a.store_id, a.user_id, u.username, a.action,
               a.entity_type, a.entity_id, a.details, a.ip_address, a.created_at
        FROM audit_logs a
        LEFT JOIN users u ON a.user_id = u.user_id
        WHERE 1=1
        """
        params: List[Any] = []
        if store_id:
            query += " AND a.store_id = ?"
            params.append(store_id)
        if action_filter:
            query += " AND a.action = ?"
            params.append(action_filter)

        query += " ORDER BY a.log_id DESC LIMIT ?"
        params.append(limit)

        rows = self.db.fetch_all(query, tuple(params))
        return [dict(r) for r in rows]
