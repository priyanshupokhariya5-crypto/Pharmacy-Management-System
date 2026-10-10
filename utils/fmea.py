"""
FMEA (Failure Mode and Effects Analysis) domain model and service layer.

RPN = Severity × Occurrence × Detection   (all scores 1–10)

Risk Level Thresholds (project-defined academic categories):
  Low      : RPN   1 –  39
  Medium   : RPN  40 –  79
  High     : RPN  80 – 124
  Critical : RPN 125 – 1000

Detection scale: Higher D = WORSE detectability.
  1–2 → Very likely detected before reaching user/process.
  9–10 → Very difficult to detect.

All S/O/D scores carry a required written rationale.
RPN is always computed (S × O × D) — it cannot be manually overridden.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from database.db import Database, get_db

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_ACTION_STATUSES = ("Open", "In Progress", "Completed", "Accepted")

SORT_WHITELIST = {
    "rpn":           "rpn",
    "severity":      "severity",
    "occurrence":    "occurrence",
    "detection":     "detection",
    "risk_level":    "risk_level",
    "action_status": "action_status",
    "fmea_id":       "fmea_id",
    "process_module": "process_module",
}

# Risk level thresholds (project-defined)
RISK_THRESHOLDS = [
    (125, "Critical"),
    (80,  "High"),
    (40,  "Medium"),
    (1,   "Low"),
]

# FMEA table schema DDL
FMEA_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS fmea_records (
    fmea_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    process_module   TEXT    NOT NULL,
    failure_mode     TEXT    NOT NULL,
    potential_effect TEXT    NOT NULL,
    potential_cause  TEXT    NOT NULL,
    prevention_control TEXT NOT NULL,
    detection_control  TEXT NOT NULL,
    severity         INTEGER NOT NULL CHECK(severity BETWEEN 1 AND 10),
    severity_rationale TEXT  NOT NULL,
    occurrence       INTEGER NOT NULL CHECK(occurrence BETWEEN 1 AND 10),
    occurrence_rationale TEXT NOT NULL,
    detection        INTEGER NOT NULL CHECK(detection BETWEEN 1 AND 10),
    detection_rationale  TEXT NOT NULL,
    rpn              INTEGER NOT NULL,
    risk_level       TEXT    NOT NULL,
    recommended_action TEXT  NOT NULL,
    action_status    TEXT    NOT NULL DEFAULT 'Open'
                     CHECK(action_status IN ('Open', 'In Progress', 'Completed', 'Accepted')),
    owner            TEXT    NOT NULL,
    created_at       TEXT    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_fmea_risk_level ON fmea_records(risk_level);
CREATE INDEX IF NOT EXISTS idx_fmea_rpn        ON fmea_records(rpn);
CREATE INDEX IF NOT EXISTS idx_fmea_process    ON fmea_records(process_module);
CREATE INDEX IF NOT EXISTS idx_fmea_status     ON fmea_records(action_status);
"""

# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------

@dataclass
class FMEARecord:
    """Immutable-after-creation FMEA data record. RPN is always computed."""
    fmea_id:              Optional[int]
    process_module:       str
    failure_mode:         str
    potential_effect:     str
    potential_cause:      str
    prevention_control:   str
    detection_control:    str
    severity:             int
    severity_rationale:   str
    occurrence:           int
    occurrence_rationale: str
    detection:            int
    detection_rationale:  str
    recommended_action:   str
    action_status:        str = "Open"
    owner:                str = "Development Team"
    created_at:           Optional[str] = None
    updated_at:           Optional[str] = None

    @property
    def rpn(self) -> int:
        """RPN = S × O × D.  Computed — never manually settable."""
        return self.severity * self.occurrence * self.detection

    def validate(self) -> List[str]:
        """Returns a list of validation errors. Empty list = valid."""
    
        errors: List[str] = []
    
        for label, val in [
            ("Severity", self.severity),
            ("Occurrence", self.occurrence),
            ("Detection", self.detection),
        ]:
            if not isinstance(val, int):
                errors.append(f"{label} must be an integer.")
            elif not (1 <= val <= 10):
                errors.append(
                    f"{label} must be between 1 and 10 (got {val})."
                )
    
        required_fields = [
            ("Failure Mode", self.failure_mode),
            ("Process / Module", self.process_module),
            ("Potential Effect", self.potential_effect),
            ("Potential Cause", self.potential_cause),
            ("Prevention Control", self.prevention_control),
            ("Detection Control", self.detection_control),
            ("Recommended Action", self.recommended_action),
            ("Owner", self.owner),
            ("Severity Rationale", self.severity_rationale),
            ("Occurrence Rationale", self.occurrence_rationale),
            ("Detection Rationale", self.detection_rationale),
        ]
    
        for label, value in required_fields:
            if value is None or not str(value).strip():
                errors.append(f"{label} is required.")
    
        if self.action_status not in VALID_ACTION_STATUSES:
            errors.append(
                f"Action Status must be one of: {', '.join(VALID_ACTION_STATUSES)}."
            )
    
        return errors

    @property
    def risk_level(self) -> str:
        """Derives risk level from RPN using project-defined thresholds."""
        return compute_risk_level(self.rpn)

    
    
    @classmethod
    def from_row(cls, row) -> "FMEARecord":
        keys = row.keys()
        return cls(
            fmea_id=row["fmea_id"],
            process_module=row["process_module"],
            failure_mode=row["failure_mode"],
            potential_effect=row["potential_effect"],
            potential_cause=row["potential_cause"],
            prevention_control=row["prevention_control"],
            detection_control=row["detection_control"],
            severity=int(row["severity"]),
            severity_rationale=row["severity_rationale"],
            occurrence=int(row["occurrence"]),
            occurrence_rationale=row["occurrence_rationale"],
            detection=int(row["detection"]),
            detection_rationale=row["detection_rationale"],
            recommended_action=row["recommended_action"],
            action_status=row["action_status"],
            owner=row["owner"],
            created_at=row["created_at"] if "created_at" in keys else None,
            updated_at=row["updated_at"] if "updated_at" in keys else None,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fmea_id":              self.fmea_id,
            "process_module":       self.process_module,
            "failure_mode":         self.failure_mode,
            "potential_effect":     self.potential_effect,
            "potential_cause":      self.potential_cause,
            "prevention_control":   self.prevention_control,
            "detection_control":    self.detection_control,
            "severity":             self.severity,
            "severity_rationale":   self.severity_rationale,
            "occurrence":           self.occurrence,
            "occurrence_rationale": self.occurrence_rationale,
            "detection":            self.detection,
            "detection_rationale":  self.detection_rationale,
            "rpn":                  self.rpn,
            "risk_level":           self.risk_level,
            "recommended_action":   self.recommended_action,
            "action_status":        self.action_status,
            "owner":                self.owner,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def compute_risk_level(rpn: int) -> str:
    """Derives risk level string from RPN using project-defined thresholds."""
    for threshold, level in RISK_THRESHOLDS:
        if rpn >= threshold:
            return level
    return "Low"


def validate_score(value: Any, label: str) -> Tuple[int, str]:
    """
    Validates that value is an integer between 1 and 10.
    Returns (int_value, "") on success, or (-1, error_message) on failure.
    """
    try:
        v = int(value)
        if v != float(value):  # reject decimals passed as strings like "5.5"
            raise ValueError
    except (ValueError, TypeError):
        return -1, f"{label} must be a whole number (integer)."
    if not (1 <= v <= 10):
        return -1, f"{label} must be between 1 and 10 (got {v})."
    return v, ""


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------

class FMEAService:
    """
    Provides full CRUD operations, filtering, sorting, and risk audit
    calculations for FMEA records stored in the fmea_records SQLite table.
    """

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def init_fmea_schema(self) -> None:
        """Creates the fmea_records table and indexes if they do not exist."""
        self.db.execute_script(FMEA_SCHEMA_SQL)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_record(self, rec: FMEARecord) -> Tuple[bool, str]:
        """Inserts a new FMEA record. RPN is computed server-side from S/O/D."""
        errors = rec.validate()
        if errors:
            return False, "; ".join(errors)
        computed_rpn = rec.rpn
        risk = rec.risk_level
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.db.execute(
                """
                INSERT INTO fmea_records (
                    process_module, failure_mode, potential_effect, potential_cause,
                    prevention_control, detection_control,
                    severity, severity_rationale,
                    occurrence, occurrence_rationale,
                    detection, detection_rationale,
                    rpn, risk_level, recommended_action,
                    action_status, owner, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    rec.process_module, rec.failure_mode, rec.potential_effect,
                    rec.potential_cause, rec.prevention_control, rec.detection_control,
                    rec.severity, rec.severity_rationale,
                    rec.occurrence, rec.occurrence_rationale,
                    rec.detection, rec.detection_rationale,
                    computed_rpn, risk, rec.recommended_action,
                    rec.action_status, rec.owner, now, now,
                ),
            )
            return True, "FMEA record added successfully."
        except Exception as e:
            return False, str(e)

    def get_all_records(
        self,
        sort_by: str = "rpn",
        sort_dir: str = "DESC",
    ) -> List[FMEARecord]:
        """Returns all FMEA records ordered by the whitelisted sort column."""
        col = SORT_WHITELIST.get(sort_by.lower(), "rpn")
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
        rows = self.db.fetch_all(
            f"SELECT * FROM fmea_records ORDER BY {col} {direction}"
        )
        return [FMEARecord.from_row(r) for r in rows]

    def get_record_by_id(self, fmea_id: int) -> Optional[FMEARecord]:
        row = self.db.fetch_one(
            "SELECT * FROM fmea_records WHERE fmea_id = ?", (fmea_id,)
        )
        return FMEARecord.from_row(row) if row else None

    def update_record(self, rec: FMEARecord) -> Tuple[bool, str]:
        """Updates an existing FMEA record. RPN is recomputed from S/O/D."""
        if rec.fmea_id is None:
            return False, "FMEA ID required for update."
        errors = rec.validate()
        if errors:
            return False, "; ".join(errors)
        computed_rpn = rec.rpn
        risk = rec.risk_level
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.db.execute(
                """
                UPDATE fmea_records SET
                    process_module=?, failure_mode=?, potential_effect=?,
                    potential_cause=?, prevention_control=?, detection_control=?,
                    severity=?, severity_rationale=?,
                    occurrence=?, occurrence_rationale=?,
                    detection=?, detection_rationale=?,
                    rpn=?, risk_level=?, recommended_action=?,
                    action_status=?, owner=?, updated_at=?
                WHERE fmea_id=?
                """,
                (
                    rec.process_module, rec.failure_mode, rec.potential_effect,
                    rec.potential_cause, rec.prevention_control, rec.detection_control,
                    rec.severity, rec.severity_rationale,
                    rec.occurrence, rec.occurrence_rationale,
                    rec.detection, rec.detection_rationale,
                    computed_rpn, risk, rec.recommended_action,
                    rec.action_status, rec.owner, now,
                    rec.fmea_id,
                ),
            )
            return True, "FMEA record updated successfully."
        except Exception as e:
            return False, str(e)

    def delete_record(self, fmea_id: int) -> Tuple[bool, str]:
        """Deletes an FMEA record by ID."""
        try:
            self.db.execute(
                "DELETE FROM fmea_records WHERE fmea_id = ?", (fmea_id,)
            )
            return True, "FMEA record deleted."
        except Exception as e:
            return False, str(e)

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def filter_records(
        self,
        process_module: Optional[str] = None,
        risk_level: Optional[str] = None,
        action_status: Optional[str] = None,
        min_rpn: Optional[int] = None,
        max_rpn: Optional[int] = None,
        sort_by: str = "rpn",
        sort_dir: str = "DESC",
    ) -> List[FMEARecord]:
        """
        Returns filtered FMEA records. All filter conditions are combined (AND).
        Sort column is whitelisted against SQL injection.
        """
        col = SORT_WHITELIST.get(sort_by.lower(), "rpn")
        direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"

        conditions: List[str] = []
        params: List[Any] = []

        if process_module:
            conditions.append("process_module LIKE ?")
            params.append(f"%{process_module}%")
        if risk_level:
            conditions.append("risk_level = ?")
            params.append(risk_level)
        if action_status:
            conditions.append("action_status = ?")
            params.append(action_status)
        if min_rpn is not None:
            conditions.append("rpn >= ?")
            params.append(min_rpn)
        if max_rpn is not None:
            conditions.append("rpn <= ?")
            params.append(max_rpn)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.db.fetch_all(
            f"SELECT * FROM fmea_records {where} ORDER BY {col} {direction}",
            tuple(params),
        )
        return [FMEARecord.from_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Risk Audit
    # ------------------------------------------------------------------

    def get_risk_audit(self) -> Dict[str, Any]:
        """
        Computes risk audit statistics from all current FMEA records.
        Returns counts per risk level, top-5 risks, open actions, etc.
        """
        records = self.get_all_records(sort_by="rpn", sort_dir="DESC")
        if not records:
            return {
                "total": 0,
                "counts": {"Low": 0, "Medium": 0, "High": 0, "Critical": 0},
                "highest_rpn": 0,
                "highest_risk_record": None,
                "top5": [],
                "open_high_critical": [],
                "completed_count": 0,
            }

        counts = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
        for r in records:
            counts[r.risk_level] = counts.get(r.risk_level, 0) + 1

        top5 = records[:5]
        open_hc = [
            r for r in records
            if r.risk_level in ("High", "Critical") and r.action_status in ("Open", "In Progress")
        ]
        completed = sum(1 for r in records if r.action_status == "Completed")

        return {
            "total": len(records),
            "counts": counts,
            "highest_rpn": records[0].rpn,
            "highest_risk_record": records[0],
            "top5": top5,
            "open_high_critical": open_hc,
            "completed_count": completed,
        }

    def get_distinct_processes(self) -> List[str]:
        rows = self.db.fetch_all(
            "SELECT DISTINCT process_module FROM fmea_records ORDER BY process_module"
        )
        return [r["process_module"] for r in rows]


# ---------------------------------------------------------------------------
# Seed Data
# ---------------------------------------------------------------------------
# Scores are from an "Initial project risk assessment" (qualitative/structured
# academic assessment), NOT measured historical failure rates.

SEED_FMEA_RECORDS = [
    {
        "process_module": "Medicine Inventory",
        "failure_mode": "Expired medicine sold to customer",
        "potential_effect": "Patient safety risk; dispensing ineffective or harmful medication",
        "potential_cause": "Pharmacist overlooks expiry date during manual stock check",
        "prevention_control": "Expiry date validation enforced before medicine is added to cart (Poka-Yoke)",
        "detection_control": "Secondary expiry re-validation executed during final checkout transaction",
        "severity": 9,
        "severity_rationale": "S=9: Serious patient safety impact; regulatory non-compliance; dispensing expired medicine is a critical safety event",
        "occurrence": 2,
        "occurrence_rationale": "O=2: Rare; two layers of expiry validation (cart + checkout) make undetected slip very unlikely",
        "detection": 2,
        "detection_rationale": "D=2: Very likely to detect; system raises a blocking error at both cart-addition and checkout stages",
        "recommended_action": "Maintain mandatory expiry validation at both cart-addition and checkout. Add automated test for expiry boundary cases.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Billing & Sales",
        "failure_mode": "Medicine sold with insufficient stock",
        "potential_effect": "Stock count goes negative; inventory data becomes inaccurate; order fulfilment failure",
        "potential_cause": "Race condition between stock check and actual deduction; stale cache",
        "prevention_control": "Quantity availability check performed before adding to cart",
        "detection_control": "Live stock re-validation inside atomic SQLite transaction before deduction",
        "severity": 7,
        "severity_rationale": "S=7: Major operational impact; inventory inaccuracy causes downstream fulfilment issues and financial discrepancy",
        "occurrence": 3,
        "occurrence_rationale": "O=3: Occasional; single-user SQLite desktop system reduces race conditions but concurrent use scenarios exist",
        "detection": 3,
        "detection_rationale": "D=3: High likelihood of detection; transaction-level re-check catches most cases before commit",
        "recommended_action": "Revalidate current stock inside atomic transaction immediately before deduction. Add integration test for concurrent billing edge case.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Medicine Inventory",
        "failure_mode": "Negative quantity entered for medicine stock",
        "potential_effect": "Stock count becomes negative; corrupted inventory data",
        "potential_cause": "User error during manual data entry in the Add/Edit Medicine form",
        "prevention_control": "Input validation in MedicineService.validate() rejects quantity < 0; UI shows error",
        "detection_control": "SQLite CHECK constraint quantity >= 0 provides a database-level safety net",
        "severity": 6,
        "severity_rationale": "S=6: Moderate; negative stock corrupts reports and impairs billing decisions but no direct patient safety risk",
        "occurrence": 2,
        "occurrence_rationale": "O=2: Rare; Poka-Yoke validation at the service layer intercepts the error before persistence",
        "detection": 2,
        "detection_rationale": "D=2: Very likely to detect; both UI validation and DB constraint reject the invalid value",
        "recommended_action": "Maintain double-layer validation (service + DB constraint). Consider numeric spinner widget to prevent free-text entry.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Medicine Inventory",
        "failure_mode": "Negative price entered for medicine",
        "potential_effect": "Financial calculation errors; incorrect sales totals; negative revenue records",
        "potential_cause": "User enters negative value in price field",
        "prevention_control": "Price validation in MedicineService rejects price < 0; SQLite CHECK price >= 0",
        "detection_control": "UI validation message displayed to user immediately",
        "severity": 5,
        "severity_rationale": "S=5: Moderate; negative price produces incorrect financial calculations but can be corrected",
        "occurrence": 2,
        "occurrence_rationale": "O=2: Rare; validation at both service and DB levels prevents persistence",
        "detection": 2,
        "detection_rationale": "D=2: Very likely to detect; rejected at input stage with clear error message",
        "recommended_action": "Maintain price validation. Add automated unit test for negative price rejection.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Medicine Inventory",
        "failure_mode": "Duplicate medicine code entered",
        "potential_effect": "Two medicines share the same code; search/retrieval returns ambiguous results",
        "potential_cause": "User re-enters a medicine code that already exists in the database",
        "prevention_control": "Service layer checks for existing medicine_code before insert; UNIQUE constraint on medicine_code column",
        "detection_control": "SQLite UNIQUE constraint throws IntegrityError if duplicate slips through; caught and reported to user",
        "severity": 7,
        "severity_rationale": "S=7: Major; duplicate codes undermine reliable Q13 exact-code search and can lead to wrong medicine retrieval",
        "occurrence": 3,
        "occurrence_rationale": "O=3: Occasional; human error probable during high-volume data entry",
        "detection": 2,
        "detection_rationale": "D=2: Very likely to detect; both service validation and DB constraint catch duplicate before commit",
        "recommended_action": "Maintain UNIQUE constraint and pre-insert code uniqueness check. Show duplicate code warning prominently in UI.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Medicine Inventory",
        "failure_mode": "Invalid expiry date format entered",
        "potential_effect": "Expiry date stored incorrectly; expiry validation fails; expired medicine may not be flagged",
        "potential_cause": "User types date in wrong format (DD/MM/YYYY instead of YYYY-MM-DD)",
        "prevention_control": "Expiry date validated with datetime.strptime('%Y-%m-%d') in MedicineService",
        "detection_control": "Validation error displayed before record is saved",
        "severity": 6,
        "severity_rationale": "S=6: Moderate; incorrect expiry date silently allows expired medicine to pass future validation checks",
        "occurrence": 3,
        "occurrence_rationale": "O=3: Occasional; date format confusion is a common user-input error",
        "detection": 3,
        "detection_rationale": "D=3: High likelihood of detection; format validation runs at submission; date picker could further reduce risk",
        "recommended_action": "Replace free-text date entry with a date-picker widget to enforce format at input level (Poka-Yoke).",
        "action_status": "Open",
        "owner": "UI Team",
    },
    {
        "process_module": "Q13 Advanced Search",
        "failure_mode": "Medicine search returns incorrect results",
        "potential_effect": "Wrong medicine dispensed or medicine not found when it exists; Q13 objective not met",
        "potential_cause": "Complex multi-filter combination produces unintended SQL WHERE clause logic",
        "prevention_control": "SearchService builds parameterized SQL dynamically with validated filter conditions; automated search tests",
        "detection_control": "19 automated search tests cover major filter combinations; user reviews visible result list",
        "severity": 6,
        "severity_rationale": "S=6: Moderate; incorrect search could cause dispensing error but pharmacist has final verification responsibility",
        "occurrence": 3,
        "occurrence_rationale": "O=3: Occasional; multi-filter logic bugs are possible in edge cases not covered by existing tests",
        "detection": 4,
        "detection_rationale": "D=4: High likelihood of detection; automated tests catch most regressions; visible result list allows user verification",
        "recommended_action": "Expand search test coverage to include all filter combinations. Add integration test for combined expiry + stock + category filter.",
        "action_status": "In Progress",
        "owner": "QA Team",
    },
    {
        "process_module": "Q13 Advanced Search",
        "failure_mode": "Incorrect search filter applied (category/manufacturer mismatch)",
        "potential_effect": "Filtered results exclude valid medicines or include irrelevant ones",
        "potential_cause": "Filter dropdown value not matching stored data format or case sensitivity issue",
        "prevention_control": "Parameterized queries; exact-match filter on category/manufacturer ensures consistency",
        "detection_control": "Automated tests verify category and manufacturer filter results",
        "severity": 5,
        "severity_rationale": "S=5: Moderate; incorrect filter causes operational inconvenience and delays but not direct safety risk",
        "occurrence": 3,
        "occurrence_rationale": "O=3: Occasional; case sensitivity or whitespace mismatch could occur",
        "detection": 4,
        "detection_rationale": "D=4: High likelihood of detection; visible empty results or unexpected medicines prompt user investigation",
        "recommended_action": "Maintain parameterized exact-match queries. Populate filter dropdowns dynamically from DB to prevent mismatch.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Q13 Advanced Search",
        "failure_mode": "Incorrect sort order returned in search results",
        "potential_effect": "User cannot rely on displayed order; highest-priority medicines not shown first",
        "potential_cause": "Invalid sort field name injected or whitelist bypassed",
        "prevention_control": "Sort-field whitelist in SearchService rejects any non-whitelisted column name",
        "detection_control": "Automated test test_19_allowed_sort_field_whitelist verifies fallback behaviour",
        "severity": 4,
        "severity_rationale": "S=4: Minor operational impact; incorrect sort order is an inconvenience but does not corrupt data",
        "occurrence": 2,
        "occurrence_rationale": "O=2: Rare; whitelist validation prevents unsupported sort fields reaching SQL",
        "detection": 5,
        "detection_rationale": "D=5: Moderate; user may not immediately notice wrong sort order if results are large",
        "recommended_action": "Maintain sort-field whitelist. Add UI label showing active sort column and direction.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Database Layer",
        "failure_mode": "Database query failure (connection error or corrupt DB)",
        "potential_effect": "Application operation unavailable; data cannot be read or written",
        "potential_cause": "Disk space exhaustion; file permissions issue; SQLite file corruption",
        "prevention_control": "Database connection uses context manager; all exceptions are caught and logged",
        "detection_control": "Exception raised and surfaced to UI as error dialog; System audit log records failure",
        "severity": 8,
        "severity_rationale": "S=8: Major; application becomes non-functional; active sales session may be interrupted",
        "occurrence": 2,
        "occurrence_rationale": "O=2: Rare; SQLite is highly stable for desktop single-user workloads",
        "detection": 3,
        "detection_rationale": "D=3: High likelihood of detection; exception is caught and displayed; audit log records event",
        "recommended_action": "Implement database integrity check (PRAGMA integrity_check) at startup. Alert user if disk space is critically low.",
        "action_status": "Open",
        "owner": "Operations Team",
    },
    {
        "process_module": "Billing & Sales",
        "failure_mode": "Partial transaction failure leaves stock inconsistent",
        "potential_effect": "Stock deducted but sale not recorded (or vice versa); inventory data corrupted",
        "potential_cause": "Application crash or power failure mid-transaction",
        "prevention_control": "All billing operations wrapped in a single atomic SQLite transaction (BEGIN/COMMIT)",
        "detection_control": "On failure, SQLite rolls back all changes automatically; transaction failure logged",
        "severity": 9,
        "severity_rationale": "S=9: Very serious; data inconsistency between stock and sales records can cause financial and inventory errors",
        "occurrence": 2,
        "occurrence_rationale": "O=2: Rare; atomic transaction and rollback mechanism prevents partial state persistence",
        "detection": 2,
        "detection_rationale": "D=2: Very likely to detect; rollback is automatic on exception; all-or-nothing atomicity enforced",
        "recommended_action": "Maintain atomic transaction design. Add startup reconciliation check comparing stock levels against sale_items records.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Billing & Sales",
        "failure_mode": "Stock deduction error (wrong quantity deducted)",
        "potential_effect": "Inventory count becomes inaccurate; over-selling or under-selling",
        "potential_cause": "Cart quantity does not match deduction quantity due to race condition or UI bug",
        "prevention_control": "Cart quantity validated before transaction; deduction uses cart-confirmed value",
        "detection_control": "Transaction-level re-check of available stock before deduction inside atomic block",
        "severity": 8,
        "severity_rationale": "S=8: Major; wrong deduction causes immediate inventory inaccuracy affecting all subsequent operations",
        "occurrence": 3,
        "occurrence_rationale": "O=3: Occasional; single-user scenario lowers risk but UI state bugs could occur",
        "detection": 3,
        "detection_rationale": "D=3: High likelihood of detection; atomic transaction re-check and automated billing tests cover this case",
        "recommended_action": "Add post-transaction stock assertion in automated tests. Consider displaying updated stock count on receipt confirmation.",
        "action_status": "In Progress",
        "owner": "Development Team",
    },
    {
        "process_module": "Medicine Inventory",
        "failure_mode": "Unauthorized medicine record deletion",
        "potential_effect": "Medicine data permanently lost; historical billing records may be affected",
        "potential_cause": "Non-Admin user accesses delete functionality or Admin deletes record by mistake",
        "prevention_control": "Delete operation gated by confirmation dialog; role-based access enforced for Admin-only actions",
        "detection_control": "Confirmation dialog displayed before delete executes; System audit log records deletion event",
        "severity": 8,
        "severity_rationale": "S=8: Major; permanent data loss; linked sale_items may reference deleted medicine causing foreign key issues",
        "occurrence": 2,
        "occurrence_rationale": "O=2: Rare; double confirmation (dialog + role check) reduces probability significantly",
        "detection": 3,
        "detection_rationale": "D=3: High likelihood of detection; confirmation dialog intercepts most accidental deletions",
        "recommended_action": "Implement soft-delete (archive flag) instead of hard delete. Maintain audit log of all delete actions.",
        "action_status": "Open",
        "owner": "Development Team",
    },
    {
        "process_module": "Billing & Sales",
        "failure_mode": "Incorrect sales record generated",
        "potential_effect": "Revenue figures inaccurate; incorrect tax/billing reports; customer disputes",
        "potential_cause": "Subtotal or total calculation error; wrong price used at time of sale",
        "prevention_control": "Subtotal = quantity × unit_price computed programmatically at time of transaction; price locked at sale time",
        "detection_control": "Sales reports available for review; unit test test_sales validates calculation accuracy",
        "severity": 7,
        "severity_rationale": "S=7: Major; incorrect financial records affect business decisions and regulatory compliance",
        "occurrence": 3,
        "occurrence_rationale": "O=3: Occasional; programmatic calculation reduces risk but floating-point rounding edge cases exist",
        "detection": 4,
        "detection_rationale": "D=4: High likelihood of detection; sales reports provide audit trail; discrepancies visible on review",
        "recommended_action": "Add floating-point rounding validation in billing tests. Display itemised receipt with per-line totals for user verification.",
        "action_status": "In Progress",
        "owner": "Finance Team",
    },
    {
        "process_module": "Reports & Analytics",
        "failure_mode": "Report displays stale or incorrect inventory data",
        "potential_effect": "Decisions made on outdated stock levels; incorrect low-stock or expiry alerts",
        "potential_cause": "Report loaded with cached data after stock update; refresh not triggered automatically",
        "prevention_control": "Refresh button available in Reports view; data fetched fresh from DB on each report load",
        "detection_control": "User can trigger manual refresh; report timestamp could indicate data currency",
        "severity": 6,
        "severity_rationale": "S=6: Moderate; decisions based on stale data can lead to over-ordering or missed low-stock alerts",
        "occurrence": 4,
        "occurrence_rationale": "O=4: Occasional; report auto-refresh is not triggered on background stock changes in this desktop version",
        "detection": 5,
        "detection_rationale": "D=5: Moderate; no visible data timestamp shown on report; user may not notice staleness without manual refresh",
        "recommended_action": "Display last-refreshed timestamp on all reports. Consider auto-refresh on report view activation. Add staleness warning.",
        "action_status": "Open",
        "owner": "UI Team",
    },
    {
        "process_module": "Q13 Benchmark",
        "failure_mode": "Benchmark database accidentally affecting production data",
        "potential_effect": "Production medicine records contaminated with synthetic benchmark data; pharmacy.db corrupted",
        "potential_cause": "Wrong database path used in BenchmarkEngine; developer error",
        "prevention_control": "BenchmarkEngine uses exclusively data/benchmark.db (separate file path enforced); pharmacy.db path never referenced in benchmark code",
        "detection_control": "Automated test test_16_main_db_unchanged verifies production DB record count after benchmark run",
        "severity": 9,
        "severity_rationale": "S=9: Very serious; contamination of production data would corrupt real medicine records and require full database restoration",
        "occurrence": 1,
        "occurrence_rationale": "O=1: Very rare; hardcoded isolated path and automated safety test provide strong separation",
        "detection": 2,
        "detection_rationale": "D=2: Very likely to detect; automated DB safety test explicitly validates pharmacy.db record count after benchmark operations",
        "recommended_action": "Maintain strict path separation. Add assertion in BenchmarkEngine.__init__ confirming db_path does not contain 'pharmacy'.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Authentication",
        "failure_mode": "Authentication module system failure (cannot log in)",
        "potential_effect": "All users locked out; application inaccessible",
        "potential_cause": "Password hash algorithm failure; database connection unavailable at login",
        "prevention_control": "PBKDF2-SHA256 stable hashing; database initialised before login window launches",
        "detection_control": "Login window displays error message; startup exception propagates to console",
        "severity": 8,
        "severity_rationale": "S=8: Major; complete system unavailability impacts all pharmacy operations",
        "occurrence": 2,
        "occurrence_rationale": "O=2: Rare; PBKDF2 hashing is stable; DB initialisation at startup catches connection issues early",
        "detection": 3,
        "detection_rationale": "D=3: High likelihood of detection; login failure is immediately visible to the user",
        "recommended_action": "Add startup database integrity check. Log authentication failures to System audit log for monitoring.",
        "action_status": "Completed",
        "owner": "Development Team",
    },
    {
        "process_module": "Authentication",
        "failure_mode": "Brute-force / repeated invalid login attempts",
        "potential_effect": "Unauthorized access to pharmacy data; privacy breach; potential data manipulation",
        "potential_cause": "No account lockout or rate-limiting mechanism implemented; attacker scripts login attempts",
        "prevention_control": "Passwords stored as PBKDF2-SHA256 hashes (not plain text); incorrect password does not reveal hash",
        "detection_control": "No automated lockout or attempt counter currently implemented (gap identified)",
        "severity": 8,
        "severity_rationale": "S=8: Major; unauthorized access could expose sensitive medicine and sales data",
        "occurrence": 4,
        "occurrence_rationale": "O=4: Occasional; desktop application with physical access restriction lowers probability but gap remains",
        "detection": 6,
        "detection_rationale": "D=6: Moderate; no automated alert or lockout triggers on repeated failures; only manual log review would detect",
        "recommended_action": "Implement account lockout after N consecutive failed login attempts. Log all failed attempts to System audit log with timestamp.",
        "action_status": "Open",
        "owner": "Security Team",
    },
    {
        "process_module": "Medicine Inventory",
        "failure_mode": "Medicine record accidentally deleted by user",
        "potential_effect": "Medicine permanently removed; cannot be searched, billed, or reported; historical linkage broken",
        "potential_cause": "User selects wrong row and confirms delete dialog without careful review",
        "prevention_control": "Confirmation dialog requires explicit user acknowledgment before delete executes",
        "detection_control": "System audit log records deletion event with username and timestamp",
        "severity": 7,
        "severity_rationale": "S=7: Major; permanent data loss disrupts billing and reporting; recovery requires manual re-entry",
        "occurrence": 3,
        "occurrence_rationale": "O=3: Occasional; confirmation dialog reduces but does not eliminate human error",
        "detection": 3,
        "detection_rationale": "D=3: High likelihood of detection post-event; audit log records the action but does not prevent it",
        "recommended_action": "Implement soft-delete with archive/restore capability. Highlight selected row clearly before showing delete dialog.",
        "action_status": "Open",
        "owner": "Development Team",
    },
    {
        "process_module": "Billing & Sales",
        "failure_mode": "Incorrect quantity entered during billing checkout",
        "potential_effect": "Customer billed for wrong quantity; stock deducted incorrectly; financial error",
        "potential_cause": "User types wrong quantity in cart quantity field without reviewing",
        "prevention_control": "Quantity validated to be a positive integer > 0 and ≤ available stock before cart update",
        "detection_control": "Cart displays running subtotal and total; user reviews cart before confirming checkout",
        "severity": 7,
        "severity_rationale": "S=7: Major; wrong quantity results in incorrect billing amount and inaccurate stock deduction",
        "occurrence": 4,
        "occurrence_rationale": "O=4: Occasional; manual numeric entry is error-prone in busy billing scenarios",
        "detection": 3,
        "detection_rationale": "D=3: High likelihood of detection; cart summary visible for review; automated billing tests cover quantity validation",
        "recommended_action": "Display quantity input with +/- stepper buttons to reduce free-text entry errors (Poka-Yoke). Add cart quantity change confirmation.",
        "action_status": "In Progress",
        "owner": "UI Team",
    },
]


def seed_fmea_data(db: Database) -> None:
    """Seeds initial FMEA records if the table is empty. Idempotent."""
    count_row = db.fetch_one("SELECT COUNT(*) as cnt FROM fmea_records")
    if count_row and count_row["cnt"] > 0:
        return  # Already seeded

    svc = FMEAService(db)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for rec_dict in SEED_FMEA_RECORDS:
        s = rec_dict["severity"]
        o = rec_dict["occurrence"]
        d = rec_dict["detection"]
        rpn = s * o * d
        risk = compute_risk_level(rpn)
        db.execute(
            """
            INSERT INTO fmea_records (
                process_module, failure_mode, potential_effect, potential_cause,
                prevention_control, detection_control,
                severity, severity_rationale,
                occurrence, occurrence_rationale,
                detection, detection_rationale,
                rpn, risk_level, recommended_action,
                action_status, owner, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                rec_dict["process_module"],
                rec_dict["failure_mode"],
                rec_dict["potential_effect"],
                rec_dict["potential_cause"],
                rec_dict["prevention_control"],
                rec_dict["detection_control"],
                s, rec_dict["severity_rationale"],
                o, rec_dict["occurrence_rationale"],
                d, rec_dict["detection_rationale"],
                rpn, risk,
                rec_dict["recommended_action"],
                rec_dict["action_status"],
                rec_dict["owner"],
                now, now,
            ),
        )


def init_fmea_db(db: Optional[Database] = None) -> Database:
    """Creates the fmea_records table, indexes, and seeds initial records."""
    db = db or get_db()
    db.execute_script(FMEA_SCHEMA_SQL)
    seed_fmea_data(db)
    return db
