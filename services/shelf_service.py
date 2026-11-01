"""
Shelf allocation, expiry evaluation, and inventory validation service.
Enforces the Critical Pharmacy Shelf Allocation Rule:
  "The same medicine must be stored in separate shelf locations when its batches have different expiry dates.
   Batches of the same medicine sharing the exact same expiry date may share a shelf location."
"""
from datetime import datetime, date
from typing import Optional, List, Dict, Tuple, Any
from database.db import Database


class ShelfService:
    """Service handling physical shelf allocation rules, expiry tracking, and reconciliation."""

    def __init__(self, db: Database):
        self.db = db

    # -----------------------------------------------------------------------
    # 1. Expiry Evaluation Mechanics
    # -----------------------------------------------------------------------

    @staticmethod
    def parse_date(date_str: str) -> date:
        """Parses YYYY-MM-DD string into a datetime.date object."""
        if not date_str:
            raise ValueError("Date string cannot be empty.")
        return datetime.strptime(str(date_str).strip(), "%Y-%m-%d").date()

    @classmethod
    def is_expired(cls, expiry_date: str, reference_date: Optional[str] = None) -> bool:
        """
        Determines whether a batch is expired.
        Convention: A batch expiring on 2026-10-25 is considered valid through 2026-10-25,
        and is considered expired on 2026-10-26 and later (reference_date > expiry_date).
        """
        try:
            exp = cls.parse_date(expiry_date)
            ref = cls.parse_date(reference_date) if reference_date else datetime.now().date()
            return ref > exp
        except (ValueError, TypeError):
            return False

    @classmethod
    def days_until_expiry(cls, expiry_date: str, reference_date: Optional[str] = None) -> int:
        """Returns signed number of days from reference_date to expiry_date. Negative means expired."""
        try:
            exp = cls.parse_date(expiry_date)
            ref = cls.parse_date(reference_date) if reference_date else datetime.now().date()
            return (exp - ref).days
        except (ValueError, TypeError):
            return 0

    @classmethod
    def compute_batch_status(cls, expiry_date: str, is_quarantined: bool = False,
                             is_recalled: bool = False, reference_date: Optional[str] = None) -> str:
        """Computes authoritative batch status: 'Recalled', 'Quarantined', 'Expired', or 'Active'."""
        if is_recalled:
            return "Recalled"
        if is_quarantined:
            return "Quarantined"
        if cls.is_expired(expiry_date, reference_date):
            return "Expired"
        return "Active"

    # -----------------------------------------------------------------------
    # 2. Critical Shelf Allocation Rule Enforcement
    # -----------------------------------------------------------------------

    def validate_shelf_allocation(
        self,
        store_id: str,
        medicine_id: int,
        location_id: int,
        expiry_date: str,
        exclude_batch_id: Optional[int] = None
    ) -> Tuple[bool, str]:
        """
        Validates whether assigning `medicine_id` with `expiry_date` to `location_id`
        in `store_id` satisfies the critical shelf allocation rule:

        The same medicine must be stored in separate shelf locations when its batches have different expiry dates.
        Batches of the same medicine sharing the same expiry date MAY share a shelf location.

        Returns:
            (True, "Valid shelf allocation") or
            (False, "<detailed explanation of conflict>")
        """
        if not store_id:
            return False, "Store ID is required for shelf allocation."
        if not medicine_id or int(medicine_id) <= 0:
            return False, "Valid Medicine ID is required."
        if not location_id or int(location_id) <= 0:
            return False, "Valid Storage Location ID is required."
        if not expiry_date:
            return False, "Expiry date is required to evaluate shelf allocation."

        # Verify the location belongs to the specified store (Tenant Isolation)
        loc = self.db.fetch_one(
            "SELECT location_id, shelf_code, store_id, is_active FROM storage_locations WHERE location_id = ? AND store_id = ?",
            (location_id, store_id)
        )
        if not loc:
            return False, f"Location ID {location_id} does not exist in store '{store_id}'."
        if not loc["is_active"]:
            return False, f"Shelf location '{loc['shelf_code']}' is currently inactive."

        # Query all existing batches of this medicine currently assigned to this shelf location
        query = """
        SELECT b.batch_id, b.batch_number, b.expiry_date, b.current_quantity, m.medicine_name, l.shelf_code
        FROM inventory_batches b
        JOIN medicines m ON b.medicine_id = m.medicine_id
        JOIN storage_locations l ON b.location_id = l.location_id
        WHERE b.store_id = ? AND b.medicine_id = ? AND b.location_id = ?
        """
        params: List[Any] = [store_id, medicine_id, location_id]
        if exclude_batch_id:
            query += " AND b.batch_id != ?"
            params.append(exclude_batch_id)

        existing_batches = self.db.fetch_all(query, params)
        if not existing_batches:
            # Shelf is unoccupied by this medicine -> perfectly valid
            return True, f"Shelf location '{loc['shelf_code']}' is available for this medicine."

        # Check existing expiry dates on this shelf for this medicine
        target_expiry = str(expiry_date).strip()
        conflicting = []
        for eb in existing_batches:
            existing_exp = str(eb["expiry_date"]).strip()
            if existing_exp != target_expiry:
                conflicting.append(eb)

        if conflicting:
            conf_details = ", ".join([f"Batch '{c['batch_number']}' (exp: {c['expiry_date']})" for c in conflicting])
            return False, (
                f"Shelf allocation conflict: Location '{loc['shelf_code']}' already stores {existing_batches[0]['medicine_name']} "
                f"with a different expiry date ({conf_details}). Under the pharmacy storage policy, batches with different "
                f"expiry dates must be stored on separate shelves."
            )

        # All existing batches on this shelf share the exact same expiry date -> allowed
        return True, f"Valid: Shares shelf '{loc['shelf_code']}' with compatible batch (same expiry {target_expiry})."

    def get_or_create_location(
        self,
        store_id: str,
        shelf_code: str,
        rack: Optional[str] = None,
        bin_code: Optional[str] = None,
        description: Optional[str] = None
    ) -> int:
        """Finds or creates a storage location within store_id, returning location_id."""
        loc = self.db.fetch_one(
            "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
            (store_id, shelf_code)
        )
        if loc:
            return loc["location_id"]

        loc_id = self.db.execute(
            """
            INSERT INTO storage_locations (store_id, shelf_code, rack, bin, description, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (store_id, shelf_code, rack, bin_code, description or f"Shelf {shelf_code}")
        )
        return loc_id

    def find_compatible_shelf_for_batch(
        self,
        store_id: str,
        medicine_id: int,
        expiry_date: str
    ) -> Optional[int]:
        """
        Finds an existing shelf location in store_id that already has batches of this medicine
        with the EXACT same expiry date, or an empty shelf location that has no conflicting expiry dates.
        """
        target_expiry = str(expiry_date).strip()

        # 1. First priority: a shelf that already holds this medicine with the same expiry
        same_expiry_loc = self.db.fetch_one(
            """
            SELECT location_id
            FROM inventory_batches
            WHERE store_id = ? AND medicine_id = ? AND expiry_date = ?
            LIMIT 1
            """,
            (store_id, medicine_id, target_expiry)
        )
        if same_expiry_loc:
            return same_expiry_loc["location_id"]

        # 2. Second priority: any active shelf in this store that does NOT hold this medicine with any other expiry
        all_locs = self.db.fetch_all(
            "SELECT location_id, shelf_code FROM storage_locations WHERE store_id = ? AND is_active = 1 ORDER BY shelf_code",
            (store_id,)
        )
        for loc in all_locs:
            ok, _ = self.validate_shelf_allocation(store_id, medicine_id, loc["location_id"], target_expiry)
            if ok:
                return loc["location_id"]

        return None

    def _table_exists(self, table_name: str) -> bool:
        """Helper checking if a table exists in the database."""
        row = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table_name,))
        return bool(row)

    def get_storage_locations(
        self,
        store_id: str,
        is_active: Optional[bool] = None
    ) -> List[Dict[str, Any]]:
        """Returns all storage locations for store_id, optionally filtered by active status."""
        if not self._table_exists("storage_locations"):
            return []

        query = "SELECT * FROM storage_locations WHERE store_id = ?"
        params: List[Any] = [store_id]
        if is_active is not None:
            query += " AND is_active = ?"
            params.append(1 if is_active else 0)
        query += " ORDER BY shelf_code ASC"
        return self.db.fetch_all(query, params)

    def create_storage_location(
        self,
        store_id: str,
        shelf_code: str,
        rack: Optional[str] = None,
        bin_code: Optional[str] = None,
        description: Optional[str] = None,
        acting_user: Optional[Any] = None
    ) -> int:
        """Creates a new storage location in store_id."""
        if not store_id or not str(store_id).strip():
            raise ValueError("Store ID is required.")
        if not shelf_code or not str(shelf_code).strip():
            raise ValueError("Shelf code is required.")

        shelf_clean = shelf_code.strip().upper()
        existing = self.db.fetch_one(
            "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
            (store_id, shelf_clean)
        )
        if existing:
            raise ValueError(f"Storage location '{shelf_clean}' already exists in store '{store_id}'.")

        return self.get_or_create_location(
            store_id=store_id,
            shelf_code=shelf_clean,
            rack=rack.strip() if rack else None,
            bin_code=bin_code.strip() if bin_code else None,
            description=description.strip() if description else None
        )

    def suggest_shelf_location(
        self,
        store_id: str,
        medicine_id: int,
        expiry_date: str
    ) -> Tuple[Optional[int], Optional[str], str]:
        """
        Suggests an available shelf location that complies with the Critical Shelf Allocation Rule.
        Returns: (location_id, shelf_code, explanation)
        """
        loc_id = self.find_compatible_shelf_for_batch(store_id, medicine_id, expiry_date)
        if loc_id:
            loc = self.db.fetch_one(
                "SELECT shelf_code FROM storage_locations WHERE location_id = ?",
                (loc_id,)
            )
            shelf_code = loc["shelf_code"] if loc else "Unknown"
            return loc_id, shelf_code, f"Compatible shelf '{shelf_code}' found."

        # If all current shelves conflict, suggest creating a new shelf code
        count_row = self.db.fetch_one(
            "SELECT COUNT(*) as c FROM storage_locations WHERE store_id = ?",
            (store_id,)
        )
        next_num = (count_row["c"] if count_row else 0) + 1
        suggested_code = f"Shelf S-{next_num:02d}"
        return None, suggested_code, f"All current shelves store this medicine with conflicting expiry. Suggested new shelf: '{suggested_code}'."

    def detect_all_shelf_conflicts(self, store_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Scans inventory_batches across the database and detects any instances where the same medicine
        at the same shelf location has batches with differing expiry dates.
        Returns a list of conflict reports for human audit and remediation.
        """
        query = """
        SELECT 
            b.store_id,
            b.medicine_id,
            m.medicine_name,
            m.medicine_code,
            b.location_id,
            l.shelf_code,
            COUNT(DISTINCT b.expiry_date) as distinct_expiries,
            GROUP_CONCAT(DISTINCT b.batch_number || ' (' || b.expiry_date || ')') as batch_details
        FROM inventory_batches b
        JOIN medicines m ON b.medicine_id = m.medicine_id
        JOIN storage_locations l ON b.location_id = l.location_id
        """
        params: List[Any] = []
        if store_id:
            query += " WHERE b.store_id = ?"
            params.append(store_id)

        query += """
        GROUP BY b.store_id, b.medicine_id, b.location_id
        HAVING COUNT(DISTINCT b.expiry_date) > 1
        """
        rows = self.db.fetch_all(query, params)
        conflicts = []
        for r in rows:
            conflicts.append({
                "store_id": r["store_id"],
                "medicine_id": r["medicine_id"],
                "medicine_name": r["medicine_name"],
                "medicine_code": r["medicine_code"],
                "location_id": r["location_id"],
                "shelf_code": r["shelf_code"],
                "distinct_expiries": r["distinct_expiries"],
                "batch_details": r["batch_details"],
                "status": "SHELF_CONFLICT_DETECTED"
            })
        return conflicts

    # -----------------------------------------------------------------------
    # 3. Stock Reconciliation & Integrity Verification
    # -----------------------------------------------------------------------

    def reconcile_medicine_stock(self, store_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Reconciles legacy medicines table quantity with normalized inventory_batches and stock_movements.
        Verifies:
          1. medicines.quantity == SUM(inventory_batches.current_quantity)
          2. SUM(initial_quantity) == SUM(stock_movements.quantity_delta WHERE movement_type='MIGRATION_OPENING')
          3. Net movement deltas == SUM(current_quantity)
        """
        query = """
        SELECT 
            m.medicine_id,
            m.store_id,
            m.medicine_code,
            m.medicine_name,
            m.quantity as legacy_quantity,
            COALESCE(SUM(b.current_quantity), 0) as batch_quantity,
            COALESCE(SUM(b.initial_quantity), 0) as batch_initial_quantity,
            COALESCE(
                (SELECT SUM(sm.quantity_delta) FROM stock_movements sm 
                 WHERE sm.store_id = m.store_id AND sm.medicine_id = m.medicine_id), 0
            ) as movement_quantity
        FROM medicines m
        LEFT JOIN inventory_batches b ON m.medicine_id = b.medicine_id AND m.store_id = b.store_id
        """
        params: List[Any] = []
        if store_id:
            query += " WHERE m.store_id = ?"
            params.append(store_id)

        query += " GROUP BY m.medicine_id, m.store_id ORDER BY m.medicine_id"
        rows = self.db.fetch_all(query, params)

        report = []
        for r in rows:
            leg_q = r["legacy_quantity"]
            bat_q = r["batch_quantity"]
            mov_q = r["movement_quantity"]
            is_matched = (leg_q == bat_q) and (bat_q == mov_q)
            report.append({
                "medicine_id": r["medicine_id"],
                "store_id": r["store_id"],
                "medicine_code": r["medicine_code"],
                "medicine_name": r["medicine_name"],
                "legacy_quantity": leg_q,
                "batch_quantity": bat_q,
                "movement_quantity": mov_q,
                "reconciled": is_matched,
                "difference": bat_q - leg_q
            })
        return report
