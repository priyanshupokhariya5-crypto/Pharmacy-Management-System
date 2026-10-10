"""
Stage 8 Unit Tests – FMEA & Risk Audit.

Tests cover all 20 required areas:
 1. FMEA record creation
 2. FMEA record retrieval
 3. FMEA record update
 4. FMEA record deletion
 5. Severity validation (1–10 integer only)
 6. Occurrence validation (1–10 integer only)
 7. Detection validation (1–10 integer only)
 8. RPN calculation (S × O × D)
 9. Risk-level calculation (thresholds)
10. RPN sorting (DESC order)
11. Risk-level filtering
12. Action-status filtering
13. Combined filters (risk + status)
14. Highest-risk calculation
15. Top-5 risk calculation
16. Invalid score prevention (0, negatives, >10, decimals, strings)
17. RPN cannot be manually overridden (always recomputed)
18. FMEA persistence (survives reconnect)
19. Seed records load correctly (count and fields)
20. RPN recalculation after score update
"""
import os
import tempfile
import unittest
from typing import Optional

from database.db import Database
from database.schema import init_db
from utils.fmea import (
    FMEA_SCHEMA_SQL,
    RISK_THRESHOLDS,
    SEED_FMEA_RECORDS,
    SORT_WHITELIST,
    VALID_ACTION_STATUSES,
    FMEARecord,
    FMEAService,
    compute_risk_level,
    init_fmea_db,
    seed_fmea_data,
    validate_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_record(
    failure_mode: str = "Test Failure Mode",
    severity: int = 5,
    occurrence: int = 4,
    detection: int = 3,
    action_status: str = "Open",
    process_module: str = "Medicine Inventory",
) -> FMEARecord:
    """Creates a valid FMEARecord for testing. RPN = S × O × D."""
    return FMEARecord(
        fmea_id=None,
        process_module=process_module,
        failure_mode=failure_mode,
        potential_effect="Test potential effect",
        potential_cause="Test potential cause",
        prevention_control="Parameterized queries and validation",
        detection_control="Automated tests and exception handling",
        severity=severity,
        severity_rationale=f"S={severity}: Test rationale for severity",
        occurrence=occurrence,
        occurrence_rationale=f"O={occurrence}: Test rationale for occurrence",
        detection=detection,
        detection_rationale=f"D={detection}: Test rationale for detection",
        recommended_action="Maintain existing controls and add regression tests.",
        action_status=action_status,
        owner="Development Team",
    )


class TestFMEA(unittest.TestCase):
    """Comprehensive test suite for Stage 8 FMEA & Risk Audit module."""

    def setUp(self):
        """Creates an isolated temporary database for each test."""
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix="_fmea_test.db")
        os.close(self.temp_fd)
        self.db = init_db(self.temp_path)          # creates all tables incl. fmea_records
        self.svc = FMEAService(self.db)

    def tearDown(self):
        """Removes the temporary database after each test."""
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except PermissionError:
                pass

    # -----------------------------------------------------------------------
    # 1. FMEA record creation
    # -----------------------------------------------------------------------
    def test_01_fmea_record_creation(self):
        """Adding a valid FMEA record must succeed and persist the record."""
        rec = _make_valid_record(failure_mode="Creation Test", severity=6, occurrence=3, detection=4)
        ok, msg = self.svc.add_record(rec)
        self.assertTrue(ok, f"add_record failed: {msg}")
        all_records = self.svc.get_all_records()
        failure_modes = [r.failure_mode for r in all_records]
        self.assertIn("Creation Test", failure_modes)

    # -----------------------------------------------------------------------
    # 2. FMEA record retrieval
    # -----------------------------------------------------------------------
    def test_02_fmea_record_retrieval_by_id(self):
        """A record inserted must be retrievable by its auto-assigned fmea_id."""
        rec = _make_valid_record(failure_mode="Retrieval Test", severity=4, occurrence=3, detection=5)
        ok, _ = self.svc.add_record(rec)
        self.assertTrue(ok)
        all_records = self.svc.get_all_records()
        inserted = next((r for r in all_records if r.failure_mode == "Retrieval Test"), None)
        self.assertIsNotNone(inserted)
        fetched = self.svc.get_record_by_id(inserted.fmea_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.failure_mode, "Retrieval Test")
        self.assertEqual(fetched.severity, 4)

    # -----------------------------------------------------------------------
    # 3. FMEA record update
    # -----------------------------------------------------------------------
    def test_03_fmea_record_update(self):
        """Updating S/O/D must persist new values and recompute RPN."""
        rec = _make_valid_record(failure_mode="Update Test Rec", severity=3, occurrence=3, detection=3)
        self.svc.add_record(rec)
        all_records = self.svc.get_all_records()
        inserted = next((r for r in all_records if r.failure_mode == "Update Test Rec"), None)
        self.assertIsNotNone(inserted)
        self.assertEqual(inserted.rpn, 3 * 3 * 3)

        inserted.severity = 7
        inserted.severity_rationale = "Updated: S=7 major impact"
        inserted.occurrence = 5
        inserted.occurrence_rationale = "Updated: O=5 moderate frequency"
        inserted.detection = 6
        inserted.detection_rationale = "Updated: D=6 moderate detectability"
        inserted.action_status = "In Progress"

        ok, msg = self.svc.update_record(inserted)
        self.assertTrue(ok, f"update_record failed: {msg}")

        updated = self.svc.get_record_by_id(inserted.fmea_id)
        self.assertEqual(updated.severity, 7)
        self.assertEqual(updated.occurrence, 5)
        self.assertEqual(updated.detection, 6)
        self.assertEqual(updated.rpn, 7 * 5 * 6)
        self.assertEqual(updated.action_status, "In Progress")


    # -----------------------------------------------------------------------
    # 4. FMEA record deletion
    # -----------------------------------------------------------------------
    def test_04_fmea_record_deletion(self):
        """A deleted record must no longer appear in get_all_records."""
        rec = _make_valid_record(failure_mode="Delete Me")
        self.svc.add_record(rec)
        all_records = self.svc.get_all_records()
        to_delete = next((r for r in all_records if r.failure_mode == "Delete Me"), None)
        self.assertIsNotNone(to_delete)

        ok, msg = self.svc.delete_record(to_delete.fmea_id)
        self.assertTrue(ok, f"delete_record failed: {msg}")

        fetched = self.svc.get_record_by_id(to_delete.fmea_id)
        self.assertIsNone(fetched)

    # -----------------------------------------------------------------------
    # 5. Severity validation
    # -----------------------------------------------------------------------
    def test_05_severity_validation_valid(self):
        """Severity values 1 and 10 (boundary) must be accepted."""
        for s in [1, 5, 10]:
            with self.subTest(severity=s):
                rec = _make_valid_record(severity=s)
                errors = rec.validate()
                sev_errors = [e for e in errors if "Severity" in e]
                self.assertEqual(sev_errors, [], f"Unexpected severity error for S={s}: {sev_errors}")

    def test_05b_severity_validation_invalid(self):
        """Severity 0 and 11 must fail validation."""
        for bad_s in [0, 11, -1]:
            with self.subTest(severity=bad_s):
                rec = _make_valid_record()
                rec.severity = bad_s
                errors = rec.validate()
                self.assertTrue(any("Severity" in e for e in errors),
                                f"Expected severity error for S={bad_s}")

    # -----------------------------------------------------------------------
    # 6. Occurrence validation
    # -----------------------------------------------------------------------
    def test_06_occurrence_validation_valid(self):
        """Occurrence boundary values 1 and 10 must be accepted."""
        for o in [1, 5, 10]:
            with self.subTest(occurrence=o):
                rec = _make_valid_record(occurrence=o)
                errors = rec.validate()
                occ_errors = [e for e in errors if "Occurrence" in e]
                self.assertEqual(occ_errors, [])

    def test_06b_occurrence_validation_invalid(self):
        """Occurrence 0 and 11 must fail validation."""
        for bad_o in [0, 11, -3]:
            with self.subTest(occurrence=bad_o):
                rec = _make_valid_record()
                rec.occurrence = bad_o
                errors = rec.validate()
                self.assertTrue(any("Occurrence" in e for e in errors),
                                f"Expected occurrence error for O={bad_o}")

    # -----------------------------------------------------------------------
    # 7. Detection validation
    # -----------------------------------------------------------------------
    def test_07_detection_validation_valid(self):
        """Detection boundary values 1 and 10 must be accepted."""
        for d in [1, 5, 10]:
            with self.subTest(detection=d):
                rec = _make_valid_record(detection=d)
                errors = rec.validate()
                det_errors = [e for e in errors if "Detection" in e]
                self.assertEqual(det_errors, [])

    def test_07b_detection_validation_invalid(self):
        """Detection 0 and 11 must fail validation."""
        for bad_d in [0, 11, -2]:
            with self.subTest(detection=bad_d):
                rec = _make_valid_record()
                rec.detection = bad_d
                errors = rec.validate()
                self.assertTrue(any("Detection" in e for e in errors),
                                f"Expected detection error for D={bad_d}")

    # -----------------------------------------------------------------------
    # 8. RPN calculation
    # -----------------------------------------------------------------------
    def test_08_rpn_calculation(self):
        """RPN property must equal S × O × D for various combinations."""
        cases = [
            (1, 1, 1, 1),
            (10, 10, 10, 1000),
            (5, 4, 3, 60),
            (9, 2, 2, 36),
            (8, 4, 6, 192),
        ]
        for s, o, d, expected_rpn in cases:
            with self.subTest(s=s, o=o, d=d):
                rec = _make_valid_record(severity=s, occurrence=o, detection=d)
                self.assertEqual(rec.rpn, expected_rpn)

    # -----------------------------------------------------------------------
    # 9. Risk-level calculation
    # -----------------------------------------------------------------------
    def test_09_risk_level_calculation(self):
        """compute_risk_level must map RPN values to correct risk buckets."""
        cases = [
            (1,   "Low"),
            (39,  "Low"),
            (40,  "Medium"),
            (79,  "Medium"),
            (80,  "High"),
            (124, "High"),
            (125, "Critical"),
            (1000, "Critical"),
        ]
        for rpn, expected_level in cases:
            with self.subTest(rpn=rpn):
                self.assertEqual(compute_risk_level(rpn), expected_level,
                                 f"RPN={rpn} expected {expected_level}")

    def test_09b_risk_level_via_property(self):
        """FMEARecord.risk_level property must match compute_risk_level(rpn)."""
        rec = _make_valid_record(severity=8, occurrence=4, detection=6)  # RPN=192 → Critical
        self.assertEqual(rec.risk_level, "Critical")
        self.assertEqual(rec.rpn, 192)

    # -----------------------------------------------------------------------
    # 10. RPN sorting (DESC order)
    # -----------------------------------------------------------------------
    def test_10_rpn_sorting_descending(self):
        """get_all_records with sort_by='rpn' DESC must return highest RPN first."""
        rpn_configs = [(2, 2, 2), (9, 4, 6), (5, 5, 5), (1, 1, 1)]
        for s, o, d in rpn_configs:
            self.svc.add_record(_make_valid_record(severity=s, occurrence=o, detection=d))

        records = self.svc.get_all_records(sort_by="rpn", sort_dir="DESC")
        rpn_values = [r.rpn for r in records]
        self.assertEqual(rpn_values, sorted(rpn_values, reverse=True),
                         "Records not sorted by RPN descending")

    def test_10b_rpn_sorting_ascending(self):
        """get_all_records with sort_dir='ASC' must return lowest RPN first."""
        for s, o, d in [(3, 3, 3), (7, 7, 7), (2, 2, 2)]:
            self.svc.add_record(_make_valid_record(severity=s, occurrence=o, detection=d))

        records = self.svc.get_all_records(sort_by="rpn", sort_dir="ASC")
        rpn_values = [r.rpn for r in records]
        self.assertEqual(rpn_values, sorted(rpn_values),
                         "Records not sorted by RPN ascending")

    # -----------------------------------------------------------------------
    # 11. Risk-level filtering
    # -----------------------------------------------------------------------
    def test_11_risk_level_filtering(self):
        """filter_records with risk_level='Critical' must return only Critical records."""
        # S=9, O=4, D=6 → RPN=216 (Critical)
        self.svc.add_record(_make_valid_record(failure_mode="Critical Item", severity=9, occurrence=4, detection=6))
        # S=2, O=2, D=2 → RPN=8 (Low)
        self.svc.add_record(_make_valid_record(failure_mode="Low Item", severity=2, occurrence=2, detection=2))

        critical_records = self.svc.filter_records(risk_level="Critical")
        for r in critical_records:
            self.assertEqual(r.risk_level, "Critical",
                             f"Expected Critical but got {r.risk_level} for '{r.failure_mode}'")

        low_records = self.svc.filter_records(risk_level="Low")
        for r in low_records:
            self.assertEqual(r.risk_level, "Low")

    # -----------------------------------------------------------------------
    # 12. Action-status filtering
    # -----------------------------------------------------------------------
    def test_12_action_status_filtering(self):
        """filter_records with action_status must return only matching status records."""
        self.svc.add_record(_make_valid_record(failure_mode="Open Item", action_status="Open"))
        self.svc.add_record(_make_valid_record(failure_mode="Done Item", action_status="Completed"))

        open_records = self.svc.filter_records(action_status="Open")
        for r in open_records:
            self.assertEqual(r.action_status, "Open",
                             f"Expected Open but got {r.action_status} for '{r.failure_mode}'")

        completed_records = self.svc.filter_records(action_status="Completed")
        for r in completed_records:
            self.assertEqual(r.action_status, "Completed")

    # -----------------------------------------------------------------------
    # 13. Combined filters (risk + status)
    # -----------------------------------------------------------------------
    def test_13_combined_filters(self):
        """filter_records with both risk_level and action_status must AND the conditions."""
        # High risk Open
        self.svc.add_record(_make_valid_record(
            failure_mode="High+Open", severity=8, occurrence=4, detection=3,  # RPN=96 High
            action_status="Open"
        ))
        # High risk Completed
        self.svc.add_record(_make_valid_record(
            failure_mode="High+Completed", severity=8, occurrence=4, detection=3,
            action_status="Completed"
        ))
        # Low risk Open
        self.svc.add_record(_make_valid_record(
            failure_mode="Low+Open", severity=2, occurrence=2, detection=2,  # RPN=8 Low
            action_status="Open"
        ))

        results = self.svc.filter_records(risk_level="High", action_status="Open")
        for r in results:
            self.assertEqual(r.risk_level, "High")
            self.assertEqual(r.action_status, "Open")

        high_open_modes = [r.failure_mode for r in results]
        self.assertIn("High+Open", high_open_modes)
        self.assertNotIn("High+Completed", high_open_modes)
        self.assertNotIn("Low+Open", high_open_modes)

    # -----------------------------------------------------------------------
    # 14. Highest-risk calculation
    # -----------------------------------------------------------------------
    def test_14_highest_risk_calculation(self):
        """get_risk_audit must identify the record with the highest RPN."""
        self.svc.add_record(_make_valid_record(severity=3, occurrence=3, detection=3))  # RPN=27
        self.svc.add_record(_make_valid_record(severity=9, occurrence=5, detection=7))  # RPN=315
        self.svc.add_record(_make_valid_record(severity=5, occurrence=5, detection=5))  # RPN=125

        audit = self.svc.get_risk_audit()
        self.assertEqual(audit["highest_rpn"], 315)
        self.assertIsNotNone(audit["highest_risk_record"])
        self.assertEqual(audit["highest_risk_record"].rpn, 315)

    # -----------------------------------------------------------------------
    # 15. Top-5 risk calculation
    # -----------------------------------------------------------------------
    def test_15_top5_risk_calculation(self):
        """get_risk_audit top5 must contain up to 5 records sorted by RPN DESC."""
        for i in range(8):
            s = (i % 9) + 2  # vary scores for distinct RPNs
            o = (i % 5) + 1
            d = (i % 4) + 1
            self.svc.add_record(_make_valid_record(severity=s, occurrence=o, detection=d))

        audit = self.svc.get_risk_audit()
        top5 = audit["top5"]
        self.assertLessEqual(len(top5), 5)
        self.assertGreater(len(top5), 0)

        # Must be sorted descending by RPN
        rpn_values = [r.rpn for r in top5]
        self.assertEqual(rpn_values, sorted(rpn_values, reverse=True))

    # -----------------------------------------------------------------------
    # 16. Invalid score prevention
    # -----------------------------------------------------------------------
    def test_16_invalid_scores_blocked_from_db(self):
        """Records with out-of-range S/O/D must be rejected by add_record."""
        invalid_cases = [
            {"severity": 0},
            {"severity": 11},
            {"occurrence": 0},
            {"occurrence": 11},
            {"detection": 0},
            {"detection": 11},
        ]
        for override in invalid_cases:
            with self.subTest(**override):
                rec = _make_valid_record()
                for attr, val in override.items():
                    setattr(rec, attr, val)
                ok, msg = self.svc.add_record(rec)
                self.assertFalse(ok, f"Expected failure for {override} but got ok=True: {msg}")

    def test_16b_validate_score_helper_rejects_invalid_values(self):
        """validate_score helper must reject 0, negatives, >10, and non-numeric strings."""
        invalid_inputs = [0, -1, 11, 100, "abc", "", None, 5.5, "5.5"]
        for val in invalid_inputs:
            with self.subTest(value=val):
                result_val, err = validate_score(val, "Severity")
                self.assertEqual(result_val, -1, f"Expected rejection for value={val!r}")
                self.assertTrue(len(err) > 0)

    def test_16c_validate_score_helper_accepts_valid_values(self):
        """validate_score helper must accept integers 1 through 10."""
        for v in range(1, 11):
            with self.subTest(value=v):
                result_val, err = validate_score(v, "Severity")
                self.assertEqual(result_val, v)
                self.assertEqual(err, "")

    # -----------------------------------------------------------------------
    # 17. RPN cannot be manually overridden
    # -----------------------------------------------------------------------
    def test_17_rpn_cannot_be_overridden_via_property(self):
        """FMEARecord.rpn is a computed property; setting S/O/D updates it automatically."""
        rec = _make_valid_record(severity=5, occurrence=5, detection=5)  # RPN=125
        self.assertEqual(rec.rpn, 125)

        # Changing scores changes RPN — no manual override path
        rec.severity = 2
        rec.occurrence = 2
        rec.detection = 2
        self.assertEqual(rec.rpn, 8,
                         "RPN must recompute from updated S/O/D, not retain stale value")

    def test_17b_rpn_stored_in_db_always_matches_sod(self):
        """RPN stored in DB after update must match S×O×D of the updated record."""
        rec = _make_valid_record(failure_mode="RPN DB Match Test", severity=4, occurrence=4, detection=4)
        self.svc.add_record(rec)
        all_records = self.svc.get_all_records()
        stored = next((r for r in all_records if r.failure_mode == "RPN DB Match Test"), None)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.rpn, 4 * 4 * 4)

        stored.severity = 9
        stored.occurrence = 3
        stored.detection = 5  # New RPN = 135
        stored.severity_rationale = "Updated rationale"
        stored.occurrence_rationale = "Updated rationale"
        stored.detection_rationale = "Updated rationale"
        self.svc.update_record(stored)

        refreshed = self.svc.get_record_by_id(stored.fmea_id)
        self.assertEqual(refreshed.rpn, 9 * 3 * 5,
                         "DB-stored RPN must equal newly computed S×O×D")
        self.assertEqual(refreshed.risk_level, compute_risk_level(9 * 3 * 5))


    # -----------------------------------------------------------------------
    # 18. FMEA persistence
    # -----------------------------------------------------------------------
    def test_18_fmea_persistence_across_reconnect(self):
        """Records must survive a fresh Database connection to the same file."""
        rec = _make_valid_record(failure_mode="Persistence Test", severity=6, occurrence=5, detection=4)
        self.svc.add_record(rec)

        # Open a new connection to same file
        new_db = Database(self.temp_path)
        new_svc = FMEAService(new_db)
        all_records = new_svc.get_all_records()
        failure_modes = [r.failure_mode for r in all_records]
        self.assertIn("Persistence Test", failure_modes,
                      "FMEA record not found after reconnect to same DB file")

    # -----------------------------------------------------------------------
    # 19. Seed records load correctly
    # -----------------------------------------------------------------------
    def test_19_seed_records_loaded(self):
        """init_db must seed exactly len(SEED_FMEA_RECORDS) FMEA records."""
        row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM fmea_records")
        self.assertEqual(row["cnt"], len(SEED_FMEA_RECORDS),
                         f"Expected {len(SEED_FMEA_RECORDS)} seed records but found {row['cnt']}")

    def test_19b_seed_records_have_valid_rpn(self):
        """Every seeded record must have RPN = S × O × D as stored."""
        rows = self.db.fetch_all("SELECT severity, occurrence, detection, rpn FROM fmea_records")
        for row in rows:
            expected = row["severity"] * row["occurrence"] * row["detection"]
            self.assertEqual(row["rpn"], expected,
                             f"Stored RPN {row['rpn']} != computed {expected}")

    def test_19c_seed_records_have_non_empty_rationales(self):
        """Every seeded record must have non-empty severity/occurrence/detection rationale."""
        rows = self.db.fetch_all(
            "SELECT fmea_id, severity_rationale, occurrence_rationale, detection_rationale "
            "FROM fmea_records"
        )
        for row in rows:
            self.assertTrue(row["severity_rationale"].strip(),
                            f"Empty severity_rationale for fmea_id={row['fmea_id']}")
            self.assertTrue(row["occurrence_rationale"].strip(),
                            f"Empty occurrence_rationale for fmea_id={row['fmea_id']}")
            self.assertTrue(row["detection_rationale"].strip(),
                            f"Empty detection_rationale for fmea_id={row['fmea_id']}")

    def test_19d_seed_records_cover_all_required_failure_modes(self):
        """Seeded records must cover key failure mode topics required by the spec."""
        rows = self.db.fetch_all("SELECT failure_mode FROM fmea_records")
        all_modes = " ".join(r["failure_mode"].lower() for r in rows)

        required_keywords = [
            "expir",         # expired medicine
            "stock",         # insufficient stock / stock deduction
            "negative",      # negative quantity / price
            "duplicate",     # duplicate medicine code
            "search",        # incorrect search
            "sort",          # incorrect sorting
            "transaction",   # partial transaction
            "benchmark",     # benchmark DB contamination
            "login",         # authentication / login
            "billing",       # billing quantity
        ]
        for keyword in required_keywords:
            with self.subTest(keyword=keyword):
                self.assertIn(keyword, all_modes,
                              f"No seed record covers failure mode topic '{keyword}'")

    # -----------------------------------------------------------------------
    # 20. RPN recalculation after score update
    # -----------------------------------------------------------------------
    def test_20_rpn_recalculation_after_update(self):
        """Updating S/O/D must recalculate and store the new RPN in the database."""
        rec = _make_valid_record(severity=2, occurrence=2, detection=2)  # RPN=8, Low
        self.svc.add_record(rec)
        inserted = self.svc.get_all_records()[-1]
        self.assertEqual(inserted.rpn, 8)
        self.assertEqual(inserted.risk_level, "Low")

        # Update to high-risk scores
        inserted.severity = 9
        inserted.severity_rationale = "Recalculation test: high severity"
        inserted.occurrence = 5
        inserted.occurrence_rationale = "Recalculation test: moderate occurrence"
        inserted.detection = 7
        inserted.detection_rationale = "Recalculation test: low detectability"

        ok, _ = self.svc.update_record(inserted)
        self.assertTrue(ok)

        refreshed = self.svc.get_record_by_id(inserted.fmea_id)
        self.assertEqual(refreshed.rpn, 9 * 5 * 7)          # 315
        self.assertEqual(refreshed.risk_level, "Critical")   # 315 >= 125

    # -----------------------------------------------------------------------
    # Additional: Sort whitelist security
    # -----------------------------------------------------------------------
    def test_21_sort_whitelist_prevents_sql_injection(self):
        """Invalid sort column must fall back to 'rpn', not use the injected string."""
        # Add a record so the query has data to sort
        self.svc.add_record(_make_valid_record())
        # Should not raise; falls back to 'rpn'
        records = self.svc.get_all_records(sort_by="'; DROP TABLE fmea_records; --")
        self.assertIsInstance(records, list)
        # Table must still exist
        row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM fmea_records")
        self.assertIsNotNone(row)

    # -----------------------------------------------------------------------
    # Additional: Risk audit counts
    # -----------------------------------------------------------------------
    def test_22_risk_audit_counts(self):
        """get_risk_audit counts must correctly tally records per risk level."""
        # Insert one of each risk level on top of seeds
        configs = [
            (2, 2, 2, "Low"),    # RPN=8 → Low
            (5, 4, 3, "Medium"), # RPN=60 → Medium
            (8, 4, 3, "High"),   # RPN=96 → High
            (9, 4, 6, "Critical"),  # RPN=216 → Critical
        ]
        for s, o, d, expected_level in configs:
            rec = _make_valid_record(severity=s, occurrence=o, detection=d)
            self.svc.add_record(rec)

        audit = self.svc.get_risk_audit()
        # Just verify each level has at least 1
        for level in ("Low", "Medium", "High", "Critical"):
            with self.subTest(level=level):
                self.assertGreater(audit["counts"].get(level, 0), 0,
                                   f"Expected at least 1 {level} record in audit")

    # -----------------------------------------------------------------------
    # Additional: fmea_records table exists with correct indexes
    # -----------------------------------------------------------------------
    def test_23_fmea_table_and_indexes_exist(self):
        """fmea_records table and its 4 indexes must exist in the database."""
        rows = self.db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='fmea_records'"
        )
        self.assertEqual(len(rows), 1, "fmea_records table missing")

        idx_rows = self.db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_fmea_%'"
        )
        idx_names = {r["name"] for r in idx_rows}
        for expected in ("idx_fmea_risk_level", "idx_fmea_rpn",
                         "idx_fmea_process", "idx_fmea_status"):
            with self.subTest(index=expected):
                self.assertIn(expected, idx_names, f"Index '{expected}' missing")

    # -----------------------------------------------------------------------
    # Additional: Action status validation
    # -----------------------------------------------------------------------
    def test_24_invalid_action_status_rejected(self):
        """add_record must reject records with an invalid action_status."""
        rec = _make_valid_record()
        rec.action_status = "Unknown"
        ok, msg = self.svc.add_record(rec)
        self.assertFalse(ok, "Expected failure for invalid action_status")
        self.assertIn("Action Status", msg)

    def test_24b_all_valid_action_statuses_accepted(self):
        """Each of the 4 valid action statuses must be accepted by add_record."""
        for status in VALID_ACTION_STATUSES:
            with self.subTest(status=status):
                rec = _make_valid_record(action_status=status)
                ok, msg = self.svc.add_record(rec)
                self.assertTrue(ok, f"add_record rejected valid status '{status}': {msg}")

    # -----------------------------------------------------------------------
    # Additional: filter_records min/max RPN
    # -----------------------------------------------------------------------
    def test_25_filter_by_rpn_range(self):
        """filter_records with min_rpn/max_rpn must return only records within range."""
        # Seed provides varied RPN values; just add known ones
        self.svc.add_record(_make_valid_record(severity=2, occurrence=2, detection=2))  # 8
        self.svc.add_record(_make_valid_record(severity=5, occurrence=5, detection=5))  # 125
        self.svc.add_record(_make_valid_record(severity=9, occurrence=5, detection=7))  # 315

        results = self.svc.filter_records(min_rpn=100, max_rpn=200)
        for r in results:
            self.assertGreaterEqual(r.rpn, 100)
            self.assertLessEqual(r.rpn, 200)


if __name__ == "__main__":
    unittest.main()

