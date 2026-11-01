"""
Inventory, FEFO Allocation, and Batch Lifecycle Service.
Implements:
  1. FEFO (First Expiry, First Out) batch selection and allocation preview engine.
  2. Batch inventory queries and expiry/low-stock alerts.
  3. Stock adjustment ledger integration (with strict sign conventions and atomicity).
  4. Physical batch relocation with Critical Shelf Allocation Rule validation.
  5. Multi-dimensional stock reconciliation (physical, eligible, expired, quarantined).
"""
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from database.db import Database
from models.batch import InventoryBatch
from services.rbac import (
    PERM_MANAGE_INVENTORY,
    PERM_VIEW_STOCK_ALERTS,
    PERM_VIEW_MEDICINES,
    require_permission,
    require_store_access
)
from services.shelf_service import ShelfService


@dataclass
class BatchAllocationPreview:
    """Preview of a single batch allocated for a sale item in FEFO order."""
    batch_id: int
    batch_number: str
    expiry_date: str
    shelf_code: Optional[str]
    available_quantity: int
    allocated_quantity: int
    unit_price: float
    subtotal: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "batch_id": self.batch_id,
            "batch_number": self.batch_number,
            "expiry_date": self.expiry_date,
            "shelf_code": self.shelf_code,
            "available_quantity": self.available_quantity,
            "allocated_quantity": self.allocated_quantity,
            "unit_price": self.unit_price,
            "subtotal": self.subtotal
        }


@dataclass
class FefoAllocationResult:
    """Structured result of a FEFO allocation preview."""
    success: bool
    store_id: str
    medicine_id: int
    medicine_name: str
    requested_quantity: int
    allocated_quantity: int
    remaining_unallocated: int
    allocations: List[BatchAllocationPreview] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "store_id": self.store_id,
            "medicine_id": self.medicine_id,
            "medicine_name": self.medicine_name,
            "requested_quantity": self.requested_quantity,
            "allocated_quantity": self.allocated_quantity,
            "remaining_unallocated": self.remaining_unallocated,
            "allocations": [a.to_dict() for a in self.allocations],
            "message": self.message
        }


class InventoryService:
    """Service handling batch inventory, FEFO allocation engine, and stock ledger."""

    def __init__(self, db: Database):
        self.db = db
        self.shelf_service = ShelfService(db)

    # -----------------------------------------------------------------------
    # 1. FEFO Allocation & Selection Engine
    # -----------------------------------------------------------------------

    def preview_fefo_allocation(
        self,
        store_id: str,
        medicine_id: int,
        requested_quantity: int,
        reference_date: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> FefoAllocationResult:
        """
        Calculates eligible stock in strict FEFO (First Expiry, First Out) order.

        Selection & Ordering Rules:
          1. Find batches for the specified medicine and store (Tenant Isolation).
          2. Exclude batches where status != 'Active' (Expired, Quarantined, Recalled).
          3. Exclude batches with current_quantity <= 0.
          4. Exclude batches requiring verification (verification_flag == 1).
          5. Exclude batches where expiry_date < reference_date (Convention: valid through expiry date, expired day after).
          6. Sort eligible batches by earliest expiry date first (expiry_date ASC).
          7. Deterministic tie-breaker for same expiry date: created_at ASC, batch_id ASC.
          8. Allocate requested quantity greedily across sorted eligible batches.

        Safety Invariant:
          This method performs a READ-ONLY PREVIEW. It NEVER modifies stock or updates the database.
        """
        require_store_access(acting_user, store_id, "FEFO allocation preview")

        # 1. Verify medicine exists in store
        med = self.db.fetch_one(
            "SELECT medicine_id, medicine_name, price FROM medicines WHERE medicine_id = ? AND store_id = ?",
            (medicine_id, store_id)
        )
        if not med:
            return FefoAllocationResult(
                success=False,
                store_id=store_id,
                medicine_id=medicine_id,
                medicine_name="Unknown",
                requested_quantity=requested_quantity,
                allocated_quantity=0,
                remaining_unallocated=requested_quantity,
                message=f"Medicine ID {medicine_id} not found in store '{store_id}'."
            )

        med_name = med["medicine_name"]

        if not self._table_exists("inventory_batches"):
            return FefoAllocationResult(
                success=False,
                store_id=store_id,
                medicine_id=medicine_id,
                medicine_name=med_name,
                requested_quantity=requested_quantity,
                allocated_quantity=0,
                remaining_unallocated=requested_quantity,
                message="Batch inventory table (inventory_batches) is not present. Database migration required."
            )

        if requested_quantity <= 0:
            return FefoAllocationResult(
                success=False,
                store_id=store_id,
                medicine_id=medicine_id,
                medicine_name=med_name,
                requested_quantity=requested_quantity,
                allocated_quantity=0,
                remaining_unallocated=requested_quantity,
                message="Requested quantity must be greater than zero."
            )

        ref_date = reference_date or datetime.now().strftime("%Y-%m-%d")

        # 2. Query batches with deterministic sorting
        query = """
        SELECT b.*, l.shelf_code
        FROM inventory_batches b
        LEFT JOIN storage_locations l ON b.location_id = l.location_id
        WHERE b.store_id = ? AND b.medicine_id = ?
        ORDER BY b.expiry_date ASC, b.created_at ASC, b.batch_id ASC
        """
        rows = self.db.fetch_all(query, (store_id, medicine_id))

        # 3. Filter eligible batches
        eligible_batches = []
        for r in rows:
            batch = InventoryBatch.from_row(r)
            # Check active status
            if batch.status != "Active":
                continue
            # Check available quantity
            if batch.current_quantity <= 0:
                continue
            # Check verification flag
            if batch.verification_flag == 1:
                continue
            # Check expiry relative to reference date (convention: valid through expiry date)
            if self.shelf_service.is_expired(batch.expiry_date, ref_date):
                continue

            eligible_batches.append(batch)

        total_eligible_stock = sum(b.current_quantity for b in eligible_batches)

        # 4. Check for sufficient stock
        if total_eligible_stock < requested_quantity:
            return FefoAllocationResult(
                success=False,
                store_id=store_id,
                medicine_id=medicine_id,
                medicine_name=med_name,
                requested_quantity=requested_quantity,
                allocated_quantity=0,
                remaining_unallocated=requested_quantity,
                message=(
                    f"Insufficient eligible stock for '{med_name}' in store '{store_id}'. "
                    f"Requested: {requested_quantity}, Eligible available: {total_eligible_stock}."
                )
            )

        # 5. Greedy FEFO allocation
        needed = requested_quantity
        allocations: List[BatchAllocationPreview] = []

        for b in eligible_batches:
            if needed <= 0:
                break

            alloc_qty = min(b.current_quantity, needed)
            subtotal = round(alloc_qty * b.selling_price, 2)

            allocations.append(
                BatchAllocationPreview(
                    batch_id=b.batch_id,
                    batch_number=b.batch_number,
                    expiry_date=b.expiry_date,
                    shelf_code=b.shelf_code,
                    available_quantity=b.current_quantity,
                    allocated_quantity=alloc_qty,
                    unit_price=b.selling_price,
                    subtotal=subtotal
                )
            )
            needed -= alloc_qty

        allocated_total = requested_quantity - needed

        return FefoAllocationResult(
            success=True,
            store_id=store_id,
            medicine_id=medicine_id,
            medicine_name=med_name,
            requested_quantity=requested_quantity,
            allocated_quantity=allocated_total,
            remaining_unallocated=needed,
            allocations=allocations,
            message=(
                f"Successfully allocated {allocated_total} units across {len(allocations)} "
                f"batch(es) in FEFO order."
            )
        )

    # -----------------------------------------------------------------------
    # 2. Batch Queries & Inventory Visibility
    # -----------------------------------------------------------------------

    def _table_exists(self, table_name: str) -> bool:
        """Helper checking if a table exists in the database."""
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def get_batch_by_id(
        self,
        batch_id: int,
        store_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Optional[InventoryBatch]:
        """Fetches an inventory batch by ID, enforcing store isolation."""
        if not self._table_exists("inventory_batches"):
            return None

        if acting_user and not store_id:
            store_id = getattr(acting_user, "store_id", None)

        query = """
        SELECT b.*, l.shelf_code
        FROM inventory_batches b
        LEFT JOIN storage_locations l ON b.location_id = l.location_id
        WHERE b.batch_id = ?
        """
        params: List[Any] = [batch_id]
        if store_id:
            require_store_access(acting_user, store_id, "Viewing batch details")
            query += " AND b.store_id = ?"
            params.append(store_id)

        row = self.db.fetch_one(query, params)
        if not row:
            return None
        return InventoryBatch.from_row(row)

    def get_batches_by_medicine(
        self,
        medicine_id: int,
        store_id: str,
        include_zero_stock: bool = True,
        acting_user: Optional[Any] = None
    ) -> List[InventoryBatch]:
        """Returns all batches for a specific medicine in store_id, sorted by expiry."""
        if not self._table_exists("inventory_batches"):
            return []

        require_store_access(acting_user, store_id, "Listing medicine batches")

        query = """
        SELECT b.*, l.shelf_code
        FROM inventory_batches b
        LEFT JOIN storage_locations l ON b.location_id = l.location_id
        WHERE b.medicine_id = ? AND b.store_id = ?
        """
        params: List[Any] = [medicine_id, store_id]
        if not include_zero_stock:
            query += " AND b.current_quantity > 0"

        query += " ORDER BY b.expiry_date ASC, b.batch_id ASC"
        rows = self.db.fetch_all(query, params)
        return [InventoryBatch.from_row(r) for r in rows]

    get_batches = None  # alias below
    def get_all_batches(
        self,
        store_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """Returns batches across all medicines in store_id with medicine metadata."""
        if not self._table_exists("inventory_batches"):
            return []

        require_store_access(acting_user, store_id, "Listing store batches")

        query = """
        SELECT b.*, m.medicine_name, m.medicine_code, m.category, l.shelf_code
        FROM inventory_batches b
        JOIN medicines m ON b.medicine_id = m.medicine_id
        LEFT JOIN storage_locations l ON b.location_id = l.location_id
        WHERE b.store_id = ?
        """
        params: List[Any] = [store_id]
        if status:
            query += " AND b.status = ?"
            params.append(status)

        query += " ORDER BY b.expiry_date ASC, b.batch_id ASC LIMIT ?"
        params.append(limit)

        return [dict(r) for r in self.db.fetch_all(query, params)]

    # -----------------------------------------------------------------------
    # 3. Expiry, Low-Stock, and Verification Alerts
    # -----------------------------------------------------------------------

    def get_expired_batches(
        self,
        store_id: str,
        reference_date: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns all batches whose expiry date has passed relative to reference_date.
        Convention: Batch expiring 2026-10-25 is expired on 2026-10-26 (ref > expiry).
        """
        if not self._table_exists("inventory_batches"):
            return []

        require_permission(acting_user, PERM_VIEW_STOCK_ALERTS, "Viewing expired stock alerts")
        require_store_access(acting_user, store_id, "Viewing expired stock alerts in store")

        ref = reference_date or datetime.now().strftime("%Y-%m-%d")

        query = """
        SELECT b.*, m.medicine_name, m.medicine_code, l.shelf_code
        FROM inventory_batches b
        JOIN medicines m ON b.medicine_id = m.medicine_id
        LEFT JOIN storage_locations l ON b.location_id = l.location_id
        WHERE b.store_id = ? AND (b.expiry_date < ? OR b.status = 'Expired')
        ORDER BY b.expiry_date ASC
        """
        return [dict(r) for r in self.db.fetch_all(query, (store_id, ref))]

    def get_near_expiry_batches(
        self,
        store_id: str,
        days: int = 30,
        reference_date: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns active batches with remaining stock expiring within the given days threshold.
        """
        if not self._table_exists("inventory_batches"):
            return []

        require_permission(acting_user, PERM_VIEW_STOCK_ALERTS, "Viewing near-expiry alerts")
        require_store_access(acting_user, store_id, "Viewing near-expiry alerts in store")

        ref = reference_date or datetime.now().strftime("%Y-%m-%d")
        ref_dt = datetime.strptime(ref, "%Y-%m-%d").date()

        query = """
        SELECT b.*, m.medicine_name, m.medicine_code, l.shelf_code
        FROM inventory_batches b
        JOIN medicines m ON b.medicine_id = m.medicine_id
        LEFT JOIN storage_locations l ON b.location_id = l.location_id
        WHERE b.store_id = ? AND b.status = 'Active' AND b.current_quantity > 0 AND b.expiry_date >= ?
        ORDER BY b.expiry_date ASC
        """
        rows = self.db.fetch_all(query, (store_id, ref))

        near_expiry = []
        for r in rows:
            try:
                exp_dt = datetime.strptime(r["expiry_date"], "%Y-%m-%d").date()
                diff = (exp_dt - ref_dt).days
                if 0 <= diff <= days:
                    item = dict(r)
                    item["days_remaining"] = diff
                    near_expiry.append(item)
            except Exception:
                continue

        return near_expiry

    def get_low_stock_medicines(
        self,
        store_id: str,
        threshold: int = 10,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns medicines whose aggregated physical stock is at or below the threshold.
        """
        require_permission(acting_user, PERM_VIEW_STOCK_ALERTS, "Viewing low stock alerts")
        require_store_access(acting_user, store_id, "Viewing low stock alerts in store")

        query = """
        SELECT 
            m.medicine_id,
            m.medicine_code,
            m.medicine_name,
            m.category,
            m.price,
            COALESCE(SUM(b.current_quantity), m.quantity) as total_stock,
            COUNT(b.batch_id) as batch_count
        FROM medicines m
        LEFT JOIN inventory_batches b ON m.medicine_id = b.medicine_id AND m.store_id = b.store_id
        WHERE m.store_id = ?
        GROUP BY m.medicine_id
        HAVING total_stock <= ?
        ORDER BY total_stock ASC
        """
        return [dict(r) for r in self.db.fetch_all(query, (store_id, threshold))]

    def get_batches_needing_verification(
        self,
        store_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> List[Dict[str, Any]]:
        """
        Returns batches migrated from legacy records that have verification_flag = 1
        (e.g., missing original supplier or manufacturing date).
        """
        if store_id:
            require_store_access(acting_user, store_id, "Viewing unverified batches")

        query = """
        SELECT b.*, m.medicine_name, m.medicine_code, l.shelf_code
        FROM inventory_batches b
        JOIN medicines m ON b.medicine_id = m.medicine_id
        LEFT JOIN storage_locations l ON b.location_id = l.location_id
        WHERE b.verification_flag = 1
        """
        params: List[Any] = []
        if store_id:
            query += " AND b.store_id = ?"
            params.append(store_id)

        query += " ORDER BY b.medicine_id ASC, b.batch_id ASC"
        return [dict(r) for r in self.db.fetch_all(query, params)]

    # -----------------------------------------------------------------------
    # 4. Stock Movement Ledger & Adjustments
    # -----------------------------------------------------------------------

    def _validate_user_id(self, acting_user: Optional[Any]) -> Optional[int]:
        """Safely extracts and validates that user_id exists in users table."""
        if not acting_user:
            return None
        user_id = getattr(acting_user, "user_id", None)
        if user_id is not None:
            u_exists = self.db.fetch_one("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if not u_exists:
                return None
        return user_id

    def adjust_stock(
        self,
        store_id: str,
        batch_id: int,
        quantity_delta: int,
        reason: str,
        reference_id: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Executes an atomic stock adjustment with compensating ledger movement.
        Sign convention:
          - Positive (+) delta: Stock addition
          - Negative (-) delta: Stock deduction

        Requires PERM_MANAGE_INVENTORY.
        Never updates stock without recording a corresponding stock_movement ledger entry.
        """
        require_permission(acting_user, PERM_MANAGE_INVENTORY, "Stock adjustment")
        require_store_access(acting_user, store_id, "Stock adjustment in store")

        if quantity_delta == 0:
            raise ValueError("Stock adjustment quantity delta cannot be zero.")
        if not reason or not str(reason).strip():
            raise ValueError("Adjustment reason is required for audit trail.")

        batch = self.get_batch_by_id(batch_id, store_id=store_id, acting_user=acting_user)
        if not batch:
            raise ValueError(f"Batch ID {batch_id} not found in store '{store_id}'.")

        new_quantity = batch.current_quantity + quantity_delta
        if new_quantity < 0:
            raise ValueError(
                f"Adjustment of {quantity_delta} units exceeds current stock ({batch.current_quantity} units). "
                "Current stock cannot become negative."
            )

        user_id = self._validate_user_id(acting_user)

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()

            # 1. Update batch quantity
            cursor.execute(
                """
                UPDATE inventory_batches SET
                    current_quantity = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = ?
                """,
                (new_quantity, batch_id)
            )

            # 2. Record ledger movement
            cursor.execute(
                """
                INSERT INTO stock_movements (
                    store_id, medicine_id, batch_id, movement_type,
                    quantity_delta, reference_type, reference_id, notes, created_by
                ) VALUES (?, ?, ?, 'STOCK_ADJUSTMENT', ?, 'MANUAL_ADJUSTMENT', ?, ?, ?)
                """,
                (
                    store_id,
                    batch.medicine_id,
                    batch_id,
                    quantity_delta,
                    reference_id or f"ADJ-{batch_id}-{int(datetime.now().timestamp())}",
                    reason.strip(),
                    user_id
                )
            )
            movement_id = cursor.lastrowid

            # 3. Synchronize legacy medicines.quantity
            cursor.execute(
                """
                UPDATE medicines SET
                    quantity = (
                        SELECT COALESCE(SUM(current_quantity), 0)
                        FROM inventory_batches
                        WHERE medicine_id = ? AND store_id = ?
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE medicine_id = ? AND store_id = ?
                """,
                (batch.medicine_id, store_id, batch.medicine_id, store_id)
            )

            conn.commit()
            return {
                "status": "SUCCESS",
                "batch_id": batch_id,
                "previous_quantity": batch.current_quantity,
                "quantity_delta": quantity_delta,
                "new_quantity": new_quantity,
                "movement_id": movement_id
            }
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def relocate_batch(
        self,
        store_id: str,
        batch_id: int,
        target_location_id: int,
        reason: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> bool:
        """
        Moves a batch to a new shelf location.
        Enforces the Critical Shelf Allocation Rule:
          "The same medicine must be stored in separate shelf locations when its batches have different expiry dates.
           Batches of the same medicine sharing the same expiry date MAY share a shelf location."

        Requires PERM_MANAGE_INVENTORY.
        """
        require_permission(acting_user, PERM_MANAGE_INVENTORY, "Relocating batch shelf")
        require_store_access(acting_user, store_id, "Relocating batch in store")

        batch = self.get_batch_by_id(batch_id, store_id=store_id, acting_user=acting_user)
        if not batch:
            raise ValueError(f"Batch ID {batch_id} not found in store '{store_id}'.")

        # Validate Critical Shelf Allocation Rule on target location
        ok, err = self.shelf_service.validate_shelf_allocation(
            store_id=store_id,
            medicine_id=batch.medicine_id,
            location_id=target_location_id,
            expiry_date=batch.expiry_date,
            exclude_batch_id=batch.batch_id
        )
        if not ok:
            _, suggested, _ = self.shelf_service.suggest_shelf_location(
                store_id, batch.medicine_id, batch.expiry_date
            )
            raise ValueError(f"Relocation failed shelf allocation: {err} Suggested shelf: '{suggested}'.")

        self.db.execute(
            """
            UPDATE inventory_batches SET
                location_id = ?,
                notes = CASE
                    WHEN notes IS NULL THEN ?
                    ELSE notes || ' | ' || ?
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE batch_id = ?
            """,
            (
                target_location_id,
                f"Relocated: {reason or 'Shelf change'}",
                f"Relocated: {reason or 'Shelf change'}",
                batch_id
            )
        )
        return True

    def quarantine_batch(
        self,
        store_id: str,
        batch_id: int,
        reason: str,
        acting_user: Optional[Any] = None
    ) -> bool:
        """Sets batch status to 'Quarantined' and logs movement. Excludes batch from FEFO."""
        require_permission(acting_user, PERM_MANAGE_INVENTORY, "Quarantining batch")
        require_store_access(acting_user, store_id, "Quarantining batch in store")

        batch = self.get_batch_by_id(batch_id, store_id=store_id, acting_user=acting_user)
        if not batch:
            raise ValueError(f"Batch ID {batch_id} not found.")

        user_id = self._validate_user_id(acting_user)

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE inventory_batches SET status = 'Quarantined', updated_at = CURRENT_TIMESTAMP WHERE batch_id = ?",
                (batch_id,)
            )
            cursor.execute(
                """
                INSERT INTO stock_movements (
                    store_id, medicine_id, batch_id, movement_type,
                    quantity_delta, reference_type, reference_id, notes, created_by
                ) VALUES (?, ?, ?, 'RECALL_QUARANTINE', 0, 'QUARANTINE', ?, ?, ?)
                """,
                (store_id, batch.medicine_id, batch_id, str(batch_id), reason, user_id)
            )
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def write_off_expired_batch(
        self,
        store_id: str,
        batch_id: int,
        reason: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Writes off remaining stock of an expired batch, setting quantity to 0
        and recording an EXPIRY_WRITE_OFF negative delta movement.
        """
        require_permission(acting_user, PERM_MANAGE_INVENTORY, "Writing off expired batch")
        require_store_access(acting_user, store_id, "Writing off expired batch in store")

        batch = self.get_batch_by_id(batch_id, store_id=store_id, acting_user=acting_user)
        if not batch:
            raise ValueError(f"Batch ID {batch_id} not found.")

        qty_to_write_off = batch.current_quantity
        if qty_to_write_off <= 0:
            return {"status": "ALREADY_ZERO", "batch_id": batch_id, "written_off_units": 0}

        user_id = self._validate_user_id(acting_user)

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE inventory_batches SET
                    current_quantity = 0,
                    status = 'Expired',
                    updated_at = CURRENT_TIMESTAMP
                WHERE batch_id = ?
                """,
                (batch_id,)
            )

            # Negative delta for deduction
            cursor.execute(
                """
                INSERT INTO stock_movements (
                    store_id, medicine_id, batch_id, movement_type,
                    quantity_delta, reference_type, reference_id, notes, created_by
                ) VALUES (?, ?, ?, 'EXPIRY_WRITE_OFF', ?, 'WRITE_OFF', ?, ?, ?)
                """,
                (
                    store_id,
                    batch.medicine_id,
                    batch_id,
                    -qty_to_write_off,
                    str(batch_id),
                    reason or f"Expired batch write-off ({qty_to_write_off} units)",
                    user_id
                )
            )

            # Synchronize legacy medicines.quantity
            cursor.execute(
                """
                UPDATE medicines SET
                    quantity = (
                        SELECT COALESCE(SUM(current_quantity), 0)
                        FROM inventory_batches
                        WHERE medicine_id = ? AND store_id = ?
                    ),
                    updated_at = CURRENT_TIMESTAMP
                WHERE medicine_id = ? AND store_id = ?
                """,
                (batch.medicine_id, store_id, batch.medicine_id, store_id)
            )

            conn.commit()
            return {
                "status": "SUCCESS",
                "batch_id": batch_id,
                "written_off_units": qty_to_write_off
            }
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    # -----------------------------------------------------------------------
    # 5. Multi-Dimensional Quantity Reconciliation
    # -----------------------------------------------------------------------

    def reconcile_store_inventory(
        self,
        store_id: str,
        acting_user: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Performs multi-dimensional stock reconciliation for store_id:
          - Total physical stock: SUM(current_quantity)
          - Eligible stock: Active, unexpired, verified stock
          - Expired stock: Expired status or passed expiry date
          - Quarantined stock: Quarantined status
          - Unverified stock: verification_flag == 1
          - Legacy quantity comparison
          - Stock movement sum comparison
        """
        require_store_access(acting_user, store_id, "Reconciling store inventory")

        today_str = datetime.now().strftime("%Y-%m-%d")

        query = """
        SELECT 
            m.medicine_id,
            m.medicine_code,
            m.medicine_name,
            m.quantity as legacy_quantity,
            COALESCE(SUM(b.current_quantity), 0) as physical_stock,
            COALESCE(SUM(CASE WHEN b.status = 'Active' AND b.current_quantity > 0 AND b.expiry_date >= ? AND b.verification_flag = 0 THEN b.current_quantity ELSE 0 END), 0) as eligible_stock,
            COALESCE(SUM(CASE WHEN b.expiry_date < ? OR b.status = 'Expired' THEN b.current_quantity ELSE 0 END), 0) as expired_stock,
            COALESCE(SUM(CASE WHEN b.status = 'Quarantined' THEN b.current_quantity ELSE 0 END), 0) as quarantined_stock,
            COALESCE(SUM(CASE WHEN b.verification_flag = 1 THEN b.current_quantity ELSE 0 END), 0) as unverified_stock,
            COALESCE(
                (SELECT SUM(sm.quantity_delta) FROM stock_movements sm WHERE sm.store_id = m.store_id AND sm.medicine_id = m.medicine_id),
                0
            ) as movement_stock
        FROM medicines m
        LEFT JOIN inventory_batches b ON m.medicine_id = b.medicine_id AND m.store_id = b.store_id
        WHERE m.store_id = ?
        GROUP BY m.medicine_id
        ORDER BY m.medicine_name ASC
        """
        rows = self.db.fetch_all(query, (today_str, today_str, store_id))

        reconciliation_items = []
        all_consistent = True

        for r in rows:
            phys = r["physical_stock"]
            leg = r["legacy_quantity"]
            mov = r["movement_stock"]
            is_matched = (phys == leg) and (phys == mov)
            if not is_matched:
                all_consistent = False

            reconciliation_items.append({
                "medicine_id": r["medicine_id"],
                "medicine_code": r["medicine_code"],
                "medicine_name": r["medicine_name"],
                "legacy_quantity": leg,
                "physical_stock": phys,
                "eligible_stock": r["eligible_stock"],
                "expired_stock": r["expired_stock"],
                "quarantined_stock": r["quarantined_stock"],
                "unverified_stock": r["unverified_stock"],
                "movement_stock": mov,
                "is_consistent": is_matched,
                "discrepancy": phys - leg
            })

        return {
            "store_id": store_id,
            "reconciliation_date": today_str,
            "total_medicines": len(reconciliation_items),
            "all_consistent": all_consistent,
            "total_physical_units": sum(it["physical_stock"] for it in reconciliation_items),
            "total_eligible_units": sum(it["eligible_stock"] for it in reconciliation_items),
            "total_expired_units": sum(it["expired_stock"] for it in reconciliation_items),
            "total_quarantined_units": sum(it["quarantined_stock"] for it in reconciliation_items),
            "items": reconciliation_items
        }
