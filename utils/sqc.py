"""
Stage 9 – SQC (Statistical Quality Control) service layer.

Contains:
  - SQC Defect Log (CRUD, filtering, sorting, Pareto calculation)
  - PDCA / Kaizen Continuous Improvement tracker (CRUD, filtering)
  - Fishbone root-cause analysis (static structured data + dynamic causes)
  - SQC Dashboard KPIs (live from DB)

All seeded records are labelled as "Initial/demo quality data –
not historical measurements."

Tables created:
  sqc_defects   – defect checksheet records
  pdca_items    – PDCA / Kaizen improvement items
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from database.db import Database, get_db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFECT_STATUSES   = ("Open", "In Progress", "Closed", "Accepted")
DEFECT_SEVERITIES = ("Low", "Medium", "High", "Critical")
DEFECT_MODULES    = (
    "Medicine Inventory", "Billing & Sales", "Q13 Advanced Search",
    "Authentication", "Database Layer", "Reports & Analytics",
    "Q13 Benchmark", "FMEA Module", "UI / UX",
)

PDCA_STATUSES = ("Plan", "Do", "Check", "Act", "Closed")

SORT_WHITELIST_DEFECTS = {
    "defect_id": "defect_id", "date_reported": "date_reported",
    "module": "module", "defect_type": "defect_type",
    "severity": "severity", "frequency": "frequency",
    "status": "status",
}
SORT_WHITELIST_PDCA = {
    "pdca_id": "pdca_id", "status": "status", "owner": "owner",
    "date_created": "date_created", "improvement_id": "improvement_id",
}

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

SQC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sqc_defects (
    defect_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id         TEXT    REFERENCES stores(store_id),
    date_reported    TEXT NOT NULL,
    module           TEXT NOT NULL,
    defect_type      TEXT NOT NULL,
    description      TEXT NOT NULL,
    severity         TEXT NOT NULL CHECK(severity IN ('Low','Medium','High','Critical')),
    frequency        INTEGER NOT NULL DEFAULT 1 CHECK(frequency >= 1),
    status           TEXT NOT NULL DEFAULT 'Open'
                     CHECK(status IN ('Open','In Progress','Closed','Accepted')),
    root_cause       TEXT NOT NULL DEFAULT '',
    corrective_action TEXT NOT NULL DEFAULT '',
    reported_by      TEXT NOT NULL DEFAULT 'QA Team',
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pdca_items (
    pdca_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id         TEXT    REFERENCES stores(store_id),
    improvement_id   TEXT NOT NULL UNIQUE,
    problem          TEXT NOT NULL,
    plan_action      TEXT NOT NULL,
    do_action        TEXT NOT NULL,
    check_action     TEXT NOT NULL,
    act_action       TEXT NOT NULL,
    owner            TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'Plan'
                     CHECK(status IN ('Plan','Do','Check','Act','Closed')),
    date_created     TEXT NOT NULL,
    result_metric    TEXT NOT NULL DEFAULT '',
    notes            TEXT NOT NULL DEFAULT '',
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sqc_module   ON sqc_defects(module);
CREATE INDEX IF NOT EXISTS idx_sqc_severity ON sqc_defects(severity);
CREATE INDEX IF NOT EXISTS idx_sqc_status   ON sqc_defects(status);
CREATE INDEX IF NOT EXISTS idx_sqc_type     ON sqc_defects(defect_type);
CREATE INDEX IF NOT EXISTS idx_sqc_store    ON sqc_defects(store_id);
CREATE INDEX IF NOT EXISTS idx_pdca_status  ON pdca_items(status);
CREATE INDEX IF NOT EXISTS idx_pdca_store   ON pdca_items(store_id);
"""

# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------

@dataclass
class SQCDefect:
    defect_id:         Optional[int]
    date_reported:     str
    module:            str
    defect_type:       str
    description:       str
    severity:          str
    frequency:         int
    status:            str
    root_cause:        str
    corrective_action: str
    reported_by:       str = "QA Team"
    created_at:        Optional[str] = None
    updated_at:        Optional[str] = None
    store_id:          Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "SQCDefect":
        keys = row.keys()
        return cls(
            defect_id=row["defect_id"],
            date_reported=row["date_reported"],
            module=row["module"],
            defect_type=row["defect_type"],
            description=row["description"],
            severity=row["severity"],
            frequency=int(row["frequency"]),
            status=row["status"],
            root_cause=row["root_cause"],
            corrective_action=row["corrective_action"],
            reported_by=row["reported_by"],
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None,
            store_id=row["store_id"] if "store_id" in keys else None,
        )

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.date_reported.strip():
            errors.append("Date is required.")
        if not self.module.strip():
            errors.append("Module is required.")
        if not self.defect_type.strip():
            errors.append("Defect Type is required.")
        if not self.description.strip():
            errors.append("Description is required.")
        if self.severity not in DEFECT_SEVERITIES:
            errors.append(f"Severity must be one of: {', '.join(DEFECT_SEVERITIES)}.")
        try:
            f = int(self.frequency)
            if f < 1:
                errors.append("Frequency must be >= 1.")
        except (TypeError, ValueError):
            errors.append("Frequency must be a positive integer.")
        if self.status not in DEFECT_STATUSES:
            errors.append(f"Status must be one of: {', '.join(DEFECT_STATUSES)}.")
        return errors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "defect_id": self.defect_id, "date_reported": self.date_reported,
            "module": self.module, "defect_type": self.defect_type,
            "description": self.description, "severity": self.severity,
            "frequency": self.frequency, "status": self.status,
            "root_cause": self.root_cause, "corrective_action": self.corrective_action,
            "reported_by": self.reported_by, "store_id": self.store_id,
        }


@dataclass
class PDCAItem:
    pdca_id:        Optional[int]
    improvement_id: str
    problem:        str
    plan_action:    str
    do_action:      str
    check_action:   str
    act_action:     str
    owner:          str
    status:         str
    date_created:   str
    result_metric:  str
    notes:          str
    created_at:     Optional[str] = None
    updated_at:     Optional[str] = None
    store_id:       Optional[str] = None

    @classmethod
    def from_row(cls, row) -> "PDCAItem":
        keys = row.keys()
        return cls(
            pdca_id=row["pdca_id"],
            improvement_id=row["improvement_id"],
            problem=row["problem"],
            plan_action=row["plan_action"],
            do_action=row["do_action"],
            check_action=row["check_action"],
            act_action=row["act_action"],
            owner=row["owner"],
            status=row["status"],
            date_created=row["date_created"],
            result_metric=row["result_metric"],
            notes=row["notes"],
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None,
            store_id=row["store_id"] if "store_id" in keys else None,
        )

    def validate(self) -> List[str]:
        errors: List[str] = []
        if not self.improvement_id.strip():
            errors.append("Improvement ID is required.")
        if not self.problem.strip():
            errors.append("Problem statement is required.")
        if not self.plan_action.strip():
            errors.append("Plan action is required.")
        if self.status not in PDCA_STATUSES:
            errors.append(f"Status must be one of: {', '.join(PDCA_STATUSES)}.")
        return errors


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------

class SQCService:
    """
    Provides CRUD, filtering, Pareto calculation, and SQC dashboard KPIs
    for the sqc_defects and pdca_items tables.
    """

    def __init__(self, db: Optional[Database] = None, store_id: Optional[str] = None):
        self.db = db or get_db()
        self.store_id = store_id or "STORE-LEGACY-001"

    # ------------------------------------------------------------------
    # SQC Defect CRUD
    # ------------------------------------------------------------------

    def add_defect(self, d: SQCDefect) -> Tuple[bool, str]:
        errors = d.validate()
        if errors:
            return False, "; ".join(errors)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target_store = d.store_id or self.store_id
        try:
            self.db.execute(
                """
                INSERT INTO sqc_defects
                  (store_id, date_reported, module, defect_type, description, severity,
                   frequency, status, root_cause, corrective_action,
                   reported_by, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (target_store, d.date_reported, d.module, d.defect_type, d.description,
                 d.severity, d.frequency, d.status, d.root_cause,
                 d.corrective_action, d.reported_by, now, now),
            )
            return True, "Defect logged successfully."
        except Exception as e:
            return False, str(e)

    def get_all_defects(self, sort_by: str = "date_reported",
                        sort_dir: str = "DESC") -> List[SQCDefect]:
        col = SORT_WHITELIST_DEFECTS.get(sort_by.lower(), "date_reported")
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
        rows = self.db.fetch_all(
            f"SELECT * FROM sqc_defects WHERE store_id = ? ORDER BY {col} {direction}",
            (self.store_id,)
        )
        return [SQCDefect.from_row(r) for r in rows]

    def get_defect_by_id(self, defect_id: int) -> Optional[SQCDefect]:
        row = self.db.fetch_one(
            "SELECT * FROM sqc_defects WHERE defect_id = ? AND store_id = ?",
            (defect_id, self.store_id)
        )
        return SQCDefect.from_row(row) if row else None

    def update_defect(self, d: SQCDefect) -> Tuple[bool, str]:
        if d.defect_id is None:
            return False, "Defect ID required."
        errors = d.validate()
        if errors:
            return False, "; ".join(errors)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.db.execute(
                """
                UPDATE sqc_defects SET
                  date_reported=?, module=?, defect_type=?, description=?,
                  severity=?, frequency=?, status=?, root_cause=?,
                  corrective_action=?, reported_by=?, updated_at=?
                WHERE defect_id=? AND store_id=?
                """,
                (d.date_reported, d.module, d.defect_type, d.description,
                 d.severity, d.frequency, d.status, d.root_cause,
                 d.corrective_action, d.reported_by, now, d.defect_id, self.store_id),
            )
            return True, "Defect updated successfully."
        except Exception as e:
            return False, str(e)

    def delete_defect(self, defect_id: int) -> Tuple[bool, str]:
        try:
            self.db.execute(
                "DELETE FROM sqc_defects WHERE defect_id = ? AND store_id = ?",
                (defect_id, self.store_id)
            )
            return True, "Defect deleted."
        except Exception as e:
            return False, str(e)

    def filter_defects(
        self,
        module: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        defect_type: Optional[str] = None,
        sort_by: str = "date_reported",
        sort_dir: str = "DESC",
    ) -> List[SQCDefect]:
        col = SORT_WHITELIST_DEFECTS.get(sort_by.lower(), "date_reported")
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
        conditions: List[str] = ["store_id = ?"]
        params: List[Any] = [self.store_id]
        if module:
            conditions.append("module = ?"); params.append(module)
        if severity:
            conditions.append("severity = ?"); params.append(severity)
        if status:
            conditions.append("status = ?"); params.append(status)
        if defect_type:
            conditions.append("defect_type LIKE ?"); params.append(f"%{defect_type}%")
        where = f"WHERE {' AND '.join(conditions)}"
        rows = self.db.fetch_all(
            f"SELECT * FROM sqc_defects {where} ORDER BY {col} {direction}",
            tuple(params),
        )
        return [SQCDefect.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Pareto Calculation
    # ------------------------------------------------------------------

    def get_pareto_data(self) -> List[Dict[str, Any]]:
        """
        Returns defect types sorted by total frequency descending,
        with cumulative percentage — ready for a Pareto chart.
        Data is always live from sqc_defects table for active store.
        """
        rows = self.db.fetch_all(
            """
            SELECT defect_type, SUM(frequency) as total_freq
            FROM sqc_defects
            WHERE store_id = ?
            GROUP BY defect_type
            ORDER BY total_freq DESC
            """,
            (self.store_id,)
        )
        if not rows:
            return []
        total = sum(r["total_freq"] for r in rows)
        cumulative = 0
        result = []
        for r in rows:
            cumulative += r["total_freq"]
            result.append({
                "defect_type": r["defect_type"],
                "frequency": r["total_freq"],
                "cumulative_pct": round(cumulative / total * 100, 1) if total > 0 else 0.0,
            })
        return result

    # ------------------------------------------------------------------
    # PDCA CRUD
    # ------------------------------------------------------------------

    def add_pdca(self, p: PDCAItem) -> Tuple[bool, str]:
        errors = p.validate()
        if errors:
            return False, "; ".join(errors)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target_store = p.store_id or self.store_id
        try:
            self.db.execute(
                """
                INSERT INTO pdca_items
                  (store_id, improvement_id, problem, plan_action, do_action,
                   check_action, act_action, owner, status, date_created,
                   result_metric, notes, created_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (target_store, p.improvement_id, p.problem, p.plan_action, p.do_action,
                 p.check_action, p.act_action, p.owner, p.status,
                 p.date_created, p.result_metric, p.notes, now, now),
            )
            return True, "PDCA item added."
        except Exception as e:
            return False, str(e)

    def get_all_pdca(self, sort_by: str = "date_created",
                     sort_dir: str = "DESC") -> List[PDCAItem]:
        col = SORT_WHITELIST_PDCA.get(sort_by.lower(), "date_created")
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
        rows = self.db.fetch_all(
            f"SELECT * FROM pdca_items WHERE store_id = ? ORDER BY {col} {direction}",
            (self.store_id,)
        )
        return [PDCAItem.from_row(r) for r in rows]

    def get_pdca_by_id(self, pdca_id: int) -> Optional[PDCAItem]:
        row = self.db.fetch_one(
            "SELECT * FROM pdca_items WHERE pdca_id = ? AND store_id = ?",
            (pdca_id, self.store_id)
        )
        return PDCAItem.from_row(row) if row else None

    def update_pdca(self, p: PDCAItem) -> Tuple[bool, str]:
        if p.pdca_id is None:
            return False, "PDCA ID required."
        errors = p.validate()
        if errors:
            return False, "; ".join(errors)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.db.execute(
                """
                UPDATE pdca_items SET
                  improvement_id=?, problem=?, plan_action=?, do_action=?,
                  check_action=?, act_action=?, owner=?, status=?,
                  date_created=?, result_metric=?, notes=?, updated_at=?
                WHERE pdca_id=? AND store_id=?
                """,
                (p.improvement_id, p.problem, p.plan_action, p.do_action,
                 p.check_action, p.act_action, p.owner, p.status,
                 p.date_created, p.result_metric, p.notes, now, p.pdca_id, self.store_id),
            )
            return True, "PDCA item updated."
        except Exception as e:
            return False, str(e)

    def delete_pdca(self, pdca_id: int) -> Tuple[bool, str]:
        try:
            self.db.execute(
                "DELETE FROM pdca_items WHERE pdca_id = ? AND store_id = ?",
                (pdca_id, self.store_id)
            )
            return True, "PDCA item deleted."
        except Exception as e:
            return False, str(e)

    def filter_pdca(self, status: Optional[str] = None) -> List[PDCAItem]:
        if status:
            rows = self.db.fetch_all(
                "SELECT * FROM pdca_items WHERE store_id = ? AND status = ? ORDER BY date_created DESC",
                (self.store_id, status),
            )
        else:
            rows = self.db.fetch_all(
                "SELECT * FROM pdca_items WHERE store_id = ? ORDER BY date_created DESC",
                (self.store_id,)
            )
        return [PDCAItem.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # SQC Dashboard KPIs
    # ------------------------------------------------------------------

    def get_dashboard_kpis(self) -> Dict[str, Any]:
        """Returns live SQC KPI metrics from the database for active store."""
        total_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM sqc_defects WHERE store_id = ?",
            (self.store_id,)
        )
        open_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM sqc_defects WHERE status='Open' AND store_id = ?",
            (self.store_id,)
        )
        high_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM sqc_defects WHERE severity IN ('High','Critical') AND store_id = ?",
            (self.store_id,)
        )
        top_type_row = self.db.fetch_one(
            """
            SELECT defect_type, SUM(frequency) as freq
            FROM sqc_defects WHERE store_id = ? GROUP BY defect_type ORDER BY freq DESC LIMIT 1
            """,
            (self.store_id,)
        )
        pdca_open_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM pdca_items WHERE status NOT IN ('Closed') AND store_id = ?",
            (self.store_id,)
        )
        pdca_closed_row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM pdca_items WHERE status='Closed' AND store_id = ?",
            (self.store_id,)
        )
        pareto = self.get_pareto_data()
        top80_count = sum(1 for p in pareto if p["cumulative_pct"] <= 80)
        return {
            "total_defects": total_row["cnt"] if total_row else 0,
            "open_defects": open_row["cnt"] if open_row else 0,
            "high_critical_defects": high_row["cnt"] if high_row else 0,
            "top_defect_type": top_type_row["defect_type"] if top_type_row else "N/A",
            "top_defect_freq": top_type_row["freq"] if top_type_row else 0,
            "pdca_open": pdca_open_row["cnt"] if pdca_open_row else 0,
            "pdca_closed": pdca_closed_row["cnt"] if pdca_closed_row else 0,
            "pareto_80pct_types": top80_count,
        }

    def get_distinct_defect_types(self) -> List[str]:
        rows = self.db.fetch_all(
            "SELECT DISTINCT defect_type FROM sqc_defects WHERE store_id = ? ORDER BY defect_type",
            (self.store_id,)
        )
        return [r["defect_type"] for r in rows]

    def get_distinct_modules(self) -> List[str]:
        rows = self.db.fetch_all(
            "SELECT DISTINCT module FROM sqc_defects WHERE store_id = ? ORDER BY module",
            (self.store_id,)
        )
        return [r["module"] for r in rows]


# ---------------------------------------------------------------------------
# Fishbone structured data (root cause categories for key defects)
# ---------------------------------------------------------------------------

FISHBONE_CAUSES: Dict[str, Dict[str, List[str]]] = {
    "Incorrect / Slow Q13 Search Retrieval": {
        "People":              ["User enters partial/ambiguous search term",
                                "Pharmacist unaware of advanced filter options"],
        "Process":             ["No SOP for medicine code standardization",
                                "Filter conditions applied in incorrect order"],
        "Software / Code":     ["LIKE '%term%' query does not use B-Tree index",
                                "Search logic builds query without result-count check",
                                "Missing automated test for combined filter edge case"],
        "Database / Data":     ["medicine_name not consistently formatted (mixed case)",
                                "Outdated/stale cached data in report view",
                                "Missing index on category or manufacturer column"],
        "Infrastructure":      ["SQLite single-file performance under high-concurrency",
                                "Disk I/O bottleneck on low-spec deployment machine"],
    },
    "Expired Medicine Sold": {
        "People":              ["Pharmacist bypasses cart review before checkout",
                                "Staff not trained on expiry-warning indicators"],
        "Process":             ["No periodic physical expiry audit procedure",
                                "Expired medicines not removed from shelf promptly"],
        "Software / Code":     ["Expiry validation logic not triggered if cart modified post-check",
                                "Edge case: expiry date exactly equals today not handled"],
        "Database / Data":     ["Expiry date stored in wrong format skips validation",
                                "Demo/seed data contains past expiry dates"],
        "Infrastructure":      ["System clock drift causes incorrect 'today' comparison"],
    },
    "Partial / Failed Transaction": {
        "People":              ["Power cut or forced shutdown mid-checkout",
                                "User closes application window during active sale"],
        "Process":             ["No transaction log reviewed after unexpected close",
                                "Manual fallback procedure not documented"],
        "Software / Code":     ["Exception handler not propagating rollback in all code paths",
                                "Background thread not joined before app shutdown"],
        "Database / Data":     ["SQLite WAL mode not enabled; journal file left on crash",
                                "Database file on network share (unsupported for SQLite)"],
        "Infrastructure":      ["UPS not installed; power failure causes abrupt close",
                                "Storage device write-cache enabled without protection"],
    },
}


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
# All records labelled: "Initial/demo quality data – not historical measurements."

SEED_SQC_DEFECTS = [
    # Q13 Search / Retrieval defects
    {
        "date_reported": "2026-08-15", "module": "Q13 Advanced Search",
        "defect_type": "Incorrect Retrieval",
        "description": "[Demo data] Multi-filter combination (category + expiry + stock) returned unexpected empty result for valid medicines.",
        "severity": "High", "frequency": 4, "status": "Closed",
        "root_cause": "AND logic applied to OR conditions when three filters combined simultaneously.",
        "corrective_action": "Fixed filter SQL builder; added test_13 covering combined filter scenario.",
        "reported_by": "Development Team",
    },
    {
        "date_reported": "2026-08-17", "module": "Q13 Advanced Search",
        "defect_type": "Performance Issue",
        "description": "[Demo data] Substring LIKE '%amox%' search noticeably slower than exact-match for 5000+ records.",
        "severity": "Medium", "frequency": 6, "status": "Accepted",
        "root_cause": "Leading wildcard LIKE '%term%' cannot use B-Tree index on medicine_name; performs full table scan.",
        "corrective_action": "Documented as known limitation in benchmark; users advised to use exact-code search for speed. Benchmark screen provides empirical evidence.",
        "reported_by": "QA Team",
    },
    {
        "date_reported": "2026-08-20", "module": "Q13 Advanced Search",
        "defect_type": "Incorrect Sorting",
        "description": "[Demo data] Results sorted by price showed inconsistent order when two medicines had equal price.",
        "severity": "Low", "frequency": 2, "status": "Closed",
        "root_cause": "Tie-breaking not applied; SQLite returns arbitrary order for equal values.",
        "corrective_action": "Added secondary sort by medicine_id to guarantee deterministic order for equal values.",
        "reported_by": "QA Team",
    },
    # Billing defects
    {
        "date_reported": "2026-08-22", "module": "Billing & Sales",
        "defect_type": "Stock Deduction Error",
        "description": "[Demo data] Stock deducted twice when user double-clicked the Confirm Checkout button rapidly.",
        "severity": "Critical", "frequency": 2, "status": "Closed",
        "root_cause": "Checkout button not disabled immediately after first click; second click triggered second transaction.",
        "corrective_action": "Checkout button disabled immediately on first click; re-enabled only on error or completion.",
        "reported_by": "Development Team",
    },
    {
        "date_reported": "2026-08-24", "module": "Billing & Sales",
        "defect_type": "Incorrect Total",
        "description": "[Demo data] Floating-point rounding error caused total to show ₹99.999 instead of ₹100.00 for specific price.",
        "severity": "Medium", "frequency": 3, "status": "Closed",
        "root_cause": "Python float arithmetic: 0.1 * 3 = 0.30000000000000004 stored as display value.",
        "corrective_action": "Applied round(total, 2) to all monetary calculations; added billing precision test.",
        "reported_by": "QA Team",
    },
    # Medicine inventory
    {
        "date_reported": "2026-08-26", "module": "Medicine Inventory",
        "defect_type": "Validation Bypass",
        "description": "[Demo data] Expiry date field accepted month 13 (2026-13-01) due to format-only validation.",
        "severity": "High", "frequency": 1, "status": "Closed",
        "root_cause": "datetime.strptime validated format but not calendar validity for all edge-case months.",
        "corrective_action": "Added secondary check with try/except for calendar validity; added test for invalid month.",
        "reported_by": "Development Team",
    },
    {
        "date_reported": "2026-08-28", "module": "Medicine Inventory",
        "defect_type": "Duplicate Entry",
        "description": "[Demo data] Two medicines with same code inserted when service check bypassed by rapid concurrent add.",
        "severity": "High", "frequency": 1, "status": "Closed",
        "root_cause": "Service-level uniqueness check executed before UNIQUE constraint; race condition allowed duplicate.",
        "corrective_action": "UNIQUE constraint on medicine_code column is the final safeguard; IntegrityError caught and shown to user.",
        "reported_by": "Development Team",
    },
    # Reports
    {
        "date_reported": "2026-09-01", "module": "Reports & Analytics",
        "defect_type": "Stale Data",
        "description": "[Demo data] Inventory report showed previous day's stock count after a large sale, until manual refresh.",
        "severity": "Medium", "frequency": 5, "status": "In Progress",
        "root_cause": "Report data fetched at view-load time and not auto-refreshed on background stock changes.",
        "corrective_action": "Added 'Last Refreshed' label to reports. Auto-refresh on view-activation pending (PDCA-003).",
        "reported_by": "QA Team",
    },
    # Auth
    {
        "date_reported": "2026-09-03", "module": "Authentication",
        "defect_type": "Security Gap",
        "description": "[Demo data] No account lockout after repeated failed login attempts; brute-force not prevented.",
        "severity": "Critical", "frequency": 1, "status": "Open",
        "root_cause": "Authentication module has no attempt counter or lockout mechanism implemented.",
        "corrective_action": "Implement failed-attempt counter and lockout after 5 failures (PDCA-004).",
        "reported_by": "Security Audit",
    },
    # Benchmark
    {
        "date_reported": "2026-09-05", "module": "Q13 Benchmark",
        "defect_type": "Misleading Measurement",
        "description": "[Demo data] Benchmark warm-up loop count insufficient; first few cold runs skewed average.",
        "severity": "Low", "frequency": 3, "status": "Closed",
        "root_cause": "Warm-up default was 2 iterations; SQLite page cache needed 5+ runs to warm.",
        "corrective_action": "Warm-up increased to 5 iterations; configurable via UI. Median reported alongside average.",
        "reported_by": "Development Team",
    },
    # UI
    {
        "date_reported": "2026-09-07", "module": "UI / UX",
        "defect_type": "Usability Issue",
        "description": "[Demo data] FMEA detail modal too narrow on 1366×768 screens; rationale text clipped.",
        "severity": "Low", "frequency": 2, "status": "Open",
        "root_cause": "Dialog geometry set to fixed 760px width; does not adapt to smaller displays.",
        "corrective_action": "Set minimum size and allow resize; wraplength adjusted to dialog width dynamically.",
        "reported_by": "UI Team",
    },
    # More Q13 related
    {
        "date_reported": "2026-09-08", "module": "Q13 Advanced Search",
        "defect_type": "Incorrect Retrieval",
        "description": "[Demo data] Manufacturer filter returned zero results for valid manufacturer due to trailing whitespace in stored name.",
        "severity": "Medium", "frequency": 3, "status": "Closed",
        "root_cause": "Manufacturer name stored with trailing space during manual data entry; exact-match query missed it.",
        "corrective_action": "Added .strip() to all text fields before DB insert; added TRIM() in search query.",
        "reported_by": "QA Team",
    },
    {
        "date_reported": "2026-09-10", "module": "Database Layer",
        "defect_type": "Performance Issue",
        "description": "[Demo data] Application startup slow (2–3 sec) when pharmacy.db contains 500+ medicines.",
        "severity": "Medium", "frequency": 2, "status": "In Progress",
        "root_cause": "Dashboard summary queries running sequentially on startup without index hint.",
        "corrective_action": "Optimize summary query to use indexed columns; add compound index on (category, quantity).",
        "reported_by": "Development Team",
    },
    {
        "date_reported": "2026-09-12", "module": "Billing & Sales",
        "defect_type": "Validation Bypass",
        "description": "[Demo data] Billing allowed quantity entry of 0 for a cart item; subtotal showed ₹0 for that line.",
        "severity": "High", "frequency": 2, "status": "Closed",
        "root_cause": "Cart quantity validation checked >= 1 only for initial add; edit-quantity path did not re-validate.",
        "corrective_action": "Re-validation added in quantity-edit path; automated test added for zero-quantity edit.",
        "reported_by": "QA Team",
    },
    {
        "date_reported": "2026-09-14", "module": "FMEA Module",
        "defect_type": "Data Integrity",
        "description": "[Demo data] FMEA record created with empty severity rationale when form submitted rapidly.",
        "severity": "Low", "frequency": 1, "status": "Closed",
        "root_cause": "Validation ran before textbox content was committed by CTkTextbox on rapid submit.",
        "corrective_action": "Added explicit get() with strip() before validation; validation now re-run on Save click.",
        "reported_by": "Development Team",
    },
]

SEED_PDCA_ITEMS = [
    {
        "improvement_id": "PDCA-001",
        "problem": "Q13 substring search (LIKE '%term%') is slow for large datasets due to full-table scan.",
        "plan_action": "Identify which search patterns are most common. Determine if prefix-search (LIKE 'term%') covers 80% of cases. Design FTS5 virtual table schema.",
        "do_action": "Implement SQLite FTS5 full-text search on medicine_name as optional enhancement. Benchmark prefix-LIKE vs FTS5 vs substring-LIKE on 5000 records.",
        "check_action": "Run benchmark on 3 query types. Verify FTS5 returns correct results. Ensure no regression on existing search tests.",
        "act_action": "If FTS5 shows >50% improvement: add FTS5 table to schema. Update SearchService to use FTS5 for name search. Document in README.",
        "owner": "Development Team",
        "status": "Check",
        "date_created": "2026-08-20",
        "result_metric": "Baseline: avg 2.1 ms (substring LIKE, 5000 rows). Target: <1.0 ms average.",
        "notes": "[Demo PDCA – planned/in-progress improvement, not a completed measured result]",
    },
    {
        "improvement_id": "PDCA-002",
        "problem": "Double-click on Checkout button deducts stock twice, creating inventory inconsistency.",
        "plan_action": "Identify all UI actions that trigger database write operations. Design button-state locking pattern.",
        "do_action": "Disable Checkout button immediately on first click. Re-enable only after transaction completes or fails.",
        "check_action": "Simulate rapid double-click in test. Verify stock deducted only once. Check transaction log shows single COMMIT.",
        "act_action": "Apply button-state locking pattern to all write-action buttons (Add, Edit, Save, Delete). Add automated UI interaction test.",
        "owner": "Development Team",
        "status": "Closed",
        "date_created": "2026-08-24",
        "result_metric": "0 duplicate deductions observed after fix in 20 rapid-click test attempts.",
        "notes": "[Demo PDCA – Closed/completed improvement]",
    },
    {
        "improvement_id": "PDCA-003",
        "problem": "Reports show stale inventory data after stock updates until user manually refreshes.",
        "plan_action": "Survey which reports are most affected. Identify performance cost of auto-refresh. Design refresh-trigger mechanism.",
        "do_action": "Add 'Last Refreshed' timestamp to all reports. Trigger auto-refresh when report tab is activated. Add refresh interval option.",
        "check_action": "Perform stock update then navigate to reports. Verify updated data appears without manual refresh. Confirm performance not degraded.",
        "act_action": "Enable auto-refresh on view activation for all report panels. Document staleness behavior in README.",
        "owner": "UI Team",
        "status": "Do",
        "date_created": "2026-09-02",
        "result_metric": "Target: report always shows data ≤ 1 navigation event old.",
        "notes": "[Demo PDCA – in progress improvement]",
    },
    {
        "improvement_id": "PDCA-004",
        "problem": "No account lockout after repeated failed login attempts; brute-force attack possible.",
        "plan_action": "Define lockout policy: 5 consecutive failures → 15-minute lockout. Design failed-attempt counter storage.",
        "do_action": "Add failed_attempts and locked_until columns to users table. Implement lockout logic in AuthService.authenticate().",
        "check_action": "Test 5 wrong passwords → locked. Test correct password after lockout period → unlocked. Verify System audit log records lockout event.",
        "act_action": "Deploy lockout mechanism. Add admin unlock endpoint. Update security section of README.",
        "owner": "Security Team",
        "status": "Plan",
        "date_created": "2026-09-04",
        "result_metric": "Target: 0 successful brute-force logins after implementing lockout.",
        "notes": "[Demo PDCA – planned improvement, not yet implemented]",
    },
    {
        "improvement_id": "PDCA-005",
        "problem": "Q13 search retrieval correctness not fully covered; edge cases for combined filters missed.",
        "plan_action": "Map all filter combinations (6 filters × multiple values). Identify untested combinations.",
        "do_action": "Add parametrized test cases for all major filter combinations. Add boundary tests for price, expiry, quantity ranges.",
        "check_action": "Run pytest with coverage report. Verify SearchService branch coverage ≥ 90%.",
        "act_action": "Integrate coverage check into CI. Add regression note to CONTRIBUTING.md.",
        "owner": "QA Team",
        "status": "Act",
        "date_created": "2026-08-18",
        "result_metric": "Search test count increased from 10 to 19; all 19 pass.",
        "notes": "[Demo PDCA – Completed, moved to Act/standardize phase]",
    },
]


def seed_sqc_data(db: Database) -> None:
    """Seeds initial SQC defect and PDCA records if tables are empty. Idempotent."""
    d_count = db.fetch_one("SELECT COUNT(*) as cnt FROM sqc_defects WHERE store_id = 'STORE-LEGACY-001'")
    if d_count and d_count["cnt"] == 0:
        svc = SQCService(db, store_id="STORE-LEGACY-001")
        for r in SEED_SQC_DEFECTS:
            d = SQCDefect(
                defect_id=None, date_reported=r["date_reported"],
                module=r["module"], defect_type=r["defect_type"],
                description=r["description"], severity=r["severity"],
                frequency=r["frequency"], status=r["status"],
                root_cause=r["root_cause"],
                corrective_action=r["corrective_action"],
                reported_by=r["reported_by"],
                store_id="STORE-LEGACY-001",
            )
            svc.add_defect(d)

    p_count = db.fetch_one("SELECT COUNT(*) as cnt FROM pdca_items WHERE store_id = 'STORE-LEGACY-001'")
    if p_count and p_count["cnt"] == 0:
        svc = SQCService(db, store_id="STORE-LEGACY-001")
        for r in SEED_PDCA_ITEMS:
            p = PDCAItem(
                pdca_id=None, improvement_id=r["improvement_id"],
                problem=r["problem"], plan_action=r["plan_action"],
                do_action=r["do_action"], check_action=r["check_action"],
                act_action=r["act_action"], owner=r["owner"],
                status=r["status"], date_created=r["date_created"],
                result_metric=r["result_metric"], notes=r["notes"],
                store_id="STORE-LEGACY-001",
            )
            svc.add_pdca(p)


def init_sqc_db(db: Optional[Database] = None) -> Database:
    """Creates SQC tables, indexes, and seeds initial records."""
    db = db or get_db()
    db.execute_script(SQC_SCHEMA_SQL)
    seed_sqc_data(db)
    return db
