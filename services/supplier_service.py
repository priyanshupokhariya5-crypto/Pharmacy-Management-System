"""
Supplier Service for Pharmacy Management System.
Handles vendor records, store association, contact validation, active/inactive toggles,
and multi-store tenant isolation with backend RBAC enforcement.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from database.db import Database
from models.supplier import Supplier
from services.rbac import (
    PERM_MANAGE_SUPPLIERS,
    PERM_MANAGE_PURCHASES,
    PERM_VIEW_MEDICINES,
    require_permission,
    require_store_access
)


class SupplierService:
    """Service managing pharmaceutical suppliers and vendor directories."""

    def __init__(self, db: Database):
        self.db = db

    def create_supplier(
        self,
        store_id: str,
        supplier_code: str,
        supplier_name: str,
        contact_person: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        gst_number: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> int:
        """
        Creates a new supplier within store_id.
        Enforces PERM_MANAGE_SUPPLIERS permission and store isolation.
        """
        require_permission(acting_user, PERM_MANAGE_SUPPLIERS, "Creating a supplier")
        require_store_access(acting_user, store_id, "Creating a supplier in store")

        supplier = Supplier(
            supplier_id=None,
            store_id=store_id.strip() if store_id else "",
            supplier_code=supplier_code.strip().upper() if supplier_code else "",
            supplier_name=supplier_name.strip() if supplier_name else "",
            contact_person=contact_person.strip() if contact_person else None,
            phone=phone.strip() if phone else None,
            email=email.strip() if email else None,
            address=address.strip() if address else None,
            gst_number=gst_number.strip().upper() if gst_number else None,
            is_active=True
        )

        validation_errors = supplier.validate()
        if validation_errors:
            raise ValueError(f"Supplier validation failed: {'; '.join(validation_errors)}")

        # Check for duplicate supplier_code within store
        existing = self.db.fetch_one(
            "SELECT supplier_id FROM suppliers WHERE store_id = ? AND supplier_code = ?",
            (supplier.store_id, supplier.supplier_code)
        )
        if existing:
            raise ValueError(
                f"Supplier with code '{supplier.supplier_code}' already exists in store '{supplier.store_id}'."
            )

        query = """
        INSERT INTO suppliers (
            store_id, supplier_code, supplier_name, contact_person,
            phone, email, address, gst_number, is_active
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """
        supplier_id = self.db.execute(
            query,
            (
                supplier.store_id,
                supplier.supplier_code,
                supplier.supplier_name,
                supplier.contact_person,
                supplier.phone,
                supplier.email,
                supplier.address,
                supplier.gst_number
            )
        )
        return supplier_id

    def _table_exists(self, table_name: str) -> bool:
        """Helper checking if a table exists in the database."""
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def get_supplier_by_id(
        self,
        supplier_id: int,
        store_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Optional[Supplier]:
        """Fetches a single supplier by ID, respecting store isolation."""
        if not self._table_exists("suppliers"):
            return None

        if acting_user and not store_id:
            store_id = getattr(acting_user, "store_id", None)

        query = "SELECT * FROM suppliers WHERE supplier_id = ?"
        params: List[Any] = [supplier_id]
        if store_id:
            require_store_access(acting_user, store_id, "Viewing supplier details")
            query += " AND store_id = ?"
            params.append(store_id)

        row = self.db.fetch_one(query, params)
        if not row:
            return None
        return Supplier.from_row(row)

    def get_supplier_by_code(
        self,
        store_id: str,
        supplier_code: str,
        acting_user: Optional[Any] = None
    ) -> Optional[Supplier]:
        """Fetches a supplier by unique store_id and supplier_code."""
        if not self._table_exists("suppliers"):
            return None

        require_store_access(acting_user, store_id, "Viewing supplier details")
        row = self.db.fetch_one(
            "SELECT * FROM suppliers WHERE store_id = ? AND supplier_code = ?",
            (store_id, supplier_code.strip().upper())
        )
        if not row:
            return None
        return Supplier.from_row(row)

    def get_suppliers(
        self,
        store_id: str,
        is_active: Optional[bool] = None,
        acting_user: Optional[Any] = None
    ) -> List[Supplier]:
        """Returns all suppliers for store_id, optionally filtered by active status."""
        if not self._table_exists("suppliers"):
            return []

        require_store_access(acting_user, store_id, "Listing suppliers")

        query = "SELECT * FROM suppliers WHERE store_id = ?"
        params: List[Any] = [store_id]
        if is_active is not None:
            query += " AND is_active = ?"
            params.append(1 if is_active else 0)

        query += " ORDER BY supplier_name ASC"
        rows = self.db.fetch_all(query, params)
        return [Supplier.from_row(r) for r in rows]

    def search_suppliers(
        self,
        store_id: str,
        search_query: str,
        acting_user: Optional[Any] = None
    ) -> List[Supplier]:
        """Searches suppliers by name, code, contact person, or phone within store_id."""
        if not self._table_exists("suppliers"):
            return []

        require_store_access(acting_user, store_id, "Searching suppliers")
        term = f"%{search_query.strip()}%" if search_query else "%"

        query = """
        SELECT * FROM suppliers
        WHERE store_id = ? AND (
            supplier_name LIKE ? OR
            supplier_code LIKE ? OR
            contact_person LIKE ? OR
            phone LIKE ?
        )
        ORDER BY supplier_name ASC
        """
        rows = self.db.fetch_all(query, (store_id, term, term, term, term))
        return [Supplier.from_row(r) for r in rows]

    def update_supplier(
        self,
        supplier: Supplier,
        acting_user: Optional[Any] = None
    ) -> bool:
        """Updates supplier details. Requires PERM_MANAGE_SUPPLIERS."""
        require_permission(acting_user, PERM_MANAGE_SUPPLIERS, "Updating supplier details")
        require_store_access(acting_user, supplier.store_id, "Updating supplier in store")

        if not supplier.supplier_id:
            raise ValueError("Supplier ID is required for update.")

        errors = supplier.validate()
        if errors:
            raise ValueError(f"Supplier update failed validation: {'; '.join(errors)}")

        # Check code uniqueness
        existing = self.db.fetch_one(
            "SELECT supplier_id FROM suppliers WHERE store_id = ? AND supplier_code = ? AND supplier_id != ?",
            (supplier.store_id, supplier.supplier_code, supplier.supplier_id)
        )
        if existing:
            raise ValueError(
                f"Another supplier with code '{supplier.supplier_code}' already exists in store '{supplier.store_id}'."
            )

        query = """
        UPDATE suppliers SET
            supplier_code = ?,
            supplier_name = ?,
            contact_person = ?,
            phone = ?,
            email = ?,
            address = ?,
            gst_number = ?,
            is_active = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE supplier_id = ? AND store_id = ?
        """
        self.db.execute(
            query,
            (
                supplier.supplier_code,
                supplier.supplier_name,
                supplier.contact_person,
                supplier.phone,
                supplier.email,
                supplier.address,
                supplier.gst_number,
                1 if supplier.is_active else 0,
                supplier.supplier_id,
                supplier.store_id
            )
        )
        return True

    def set_supplier_active_status(
        self,
        supplier_id: int,
        is_active: bool,
        store_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> bool:
        """
        Activates or deactivates a supplier without deleting purchase or batch history.
        Requires PERM_MANAGE_SUPPLIERS.
        """
        require_permission(acting_user, PERM_MANAGE_SUPPLIERS, "Toggling supplier active status")

        existing = self.get_supplier_by_id(supplier_id, store_id=store_id, acting_user=acting_user)
        if not existing:
            raise ValueError(f"Supplier with ID {supplier_id} not found.")

        target_store = existing.store_id
        require_store_access(acting_user, target_store, "Modifying supplier status")

        self.db.execute(
            "UPDATE suppliers SET is_active = ?, updated_at = CURRENT_TIMESTAMP WHERE supplier_id = ?",
            (1 if is_active else 0, supplier_id)
        )
        return True

    def get_supplier_purchases(
        self,
        supplier_id: int,
        store_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetches historical purchases from this supplier for audit/reconciliation.
        Preserved even when supplier is deactivated.
        """
        supplier = self.get_supplier_by_id(supplier_id, store_id=store_id, acting_user=acting_user)
        if not supplier:
            raise ValueError(f"Supplier ID {supplier_id} not found.")

        query = """
        SELECT p.*, u.username as received_by_user
        FROM purchases p
        LEFT JOIN users u ON p.received_by = u.user_id
        WHERE p.supplier_id = ? AND p.store_id = ?
        ORDER BY p.purchase_date DESC, p.purchase_id DESC
        """
        return self.db.fetch_all(query, (supplier_id, supplier.store_id))
