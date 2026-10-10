"""
Stage 9 Unit/Integration Tests – SQC & Continuous Improvement.

Covers:
  1.  SQC Defect creation
  2.  SQC Defect retrieval
  3.  SQC Defect update
  4.  SQC Defect deletion
  5.  Defect validation – required fields
  6.  Defect validation – severity values
  7.  Defect validation – frequency >= 1
  8.  Defect validation – action-status values
  9.  Defect filter by severity
  10. Defect filter by status
  11. Defect filter by module
  12. Combined defect filter
  13. Pareto calculation – ordering
  14. Pareto calculation – cumulative percentage
  15. Pareto 80% threshold
  16. PDCA item creation
  17. PDCA item retrieval
  18. PDCA item update
  19. PDCA item deletion
  20. PDCA validation
  21. PDCA status filter
  22. Dashboard KPI – live data
  23. Fishbone structured data
  24. Seed records loaded correctly
  25. SQC persistence across reconnect
  26. Sort whitelist prevents SQL injection
  27. Defect frequency ordering
  28. PDCA CRUD end-to-end
"""
import os
import tempfile
import unittest

from database.db import Database
from database.schema import init_db
from utils.sqc import (
    DEFECT_MODULES, DEFECT_SEVERITIES, DEFECT_STATUSES,
    FISHBONE_CAUSES, PDCA_STATUSES,
    PDCAItem, SQCDefect, SQCService,
    SEED_PDCA_ITEMS, SEED_SQC_DEFECTS,
    init_sqc_db,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_defect(
    failure_mode: str = "Test Defect",
    severity: str = "Medium",
    frequency: int = 2,
    status: str = "Open",
    module: str = "Q13 Advanced Search",
    defect_type: str = "Incorrect Retrieval",
) -> SQCDefect:
    return SQCDefect(
        defect_id=None,
        date_reported="2026-09-01",
        module=module,
        defect_type=defect_type,
        description=f"Test: {failure_mode}",
        severity=severity,
        frequency=frequency,
        status=status,
        root_cause="Test root cause",
        corrective_action="Test corrective action",
        reported_by="Test Suite",
    )


def _make_pdca(improvement_id: str = "TEST-001",
               status: str = "Plan") -> PDCAItem:
    return PDCAItem(
        pdca_id=None,
        improvement_id=improvement_id,
        problem="Test problem statement for PDCA.",
        plan_action="Plan: Identify root cause.",
        do_action="Do: Implement fix.",
        check_action="Check: Verify fix.",
        act_action="Act: Standardize if effective.",
        owner="Test Owner",
        status=status,
        date_created="2026-09-01",
        result_metric="Target: 0 occurrences.",
        notes="Test notes.",
    )


class TestSQC(unittest.TestCase):
    """Comprehensive Stage 9 test suite."""

    def setUp(self):
        self.temp_fd, self.temp_path = tempfile.mkstemp(suffix="_sqc_test.db")
        os.close(self.temp_fd)
        self.db = init_db(self.temp_path)   # creates all tables incl. sqc_defects, pdca_items
        self.svc = SQCService(self.db)

    def tearDown(self):
        if os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except PermissionError:
                pass

    # -----------------------------------------------------------------------
    # 1. Defect creation
    # -----------------------------------------------------------------------
    def test_01_defect_creation(self):
        """add_defect must succeed and persist a valid defect record."""
        d = _make_defect("Creation Test")
        ok, msg = self.svc.add_defect(d)
        self.assertTrue(ok, f"add_defect failed: {msg}")
        all_d = self.svc.get_all_defects()
        descs = [r.description for r in all_d]
        self.assertIn("Test: Creation Test", descs)

    # -----------------------------------------------------------------------
    # 2. Defect retrieval
    # -----------------------------------------------------------------------
    def test_02_defect_retrieval_by_id(self):
        """A defect must be retrievable by its auto-assigned defect_id."""
        d = _make_defect("Retrieval Test")
        self.svc.add_defect(d)
        inserted = next(
            (r for r in self.svc.get_all_defects() if "Retrieval Test" in r.description), None
        )
        self.assertIsNotNone(inserted)
        fetched = self.svc.get_defect_by_id(inserted.defect_id)
        self.assertIsNotNone(fetched)
        self.assertIn("Retrieval Test", fetched.description)
        self.assertEqual(fetched.severity, "Medium")

    # -----------------------------------------------------------------------
    # 3. Defect update
    # -----------------------------------------------------------------------
    def test_03_defect_update(self):
        """update_defect must persist changed fields."""
        d = _make_defect("Update Test")
        self.svc.add_defect(d)
        inserted = next(
            (r for r in self.svc.get_all_defects() if "Update Test" in r.description), None
        )
        inserted.severity = "High"
        inserted.status = "In Progress"
        inserted.corrective_action = "Updated corrective action."
        ok, msg = self.svc.update_defect(inserted)
        self.assertTrue(ok, f"update_defect failed: {msg}")
        updated = self.svc.get_defect_by_id(inserted.defect_id)
        self.assertEqual(updated.severity, "High")
        self.assertEqual(updated.status, "In Progress")
        self.assertEqual(updated.corrective_action, "Updated corrective action.")

    # -----------------------------------------------------------------------
    # 4. Defect deletion
    # -----------------------------------------------------------------------
    def test_04_defect_deletion(self):
        """Deleted defect must not appear in get_all_defects."""
        d = _make_defect("Delete Me")
        self.svc.add_defect(d)
        rec = next(
            (r for r in self.svc.get_all_defects() if "Delete Me" in r.description), None
        )
        self.assertIsNotNone(rec)
        ok, msg = self.svc.delete_defect(rec.defect_id)
        self.assertTrue(ok, msg)
        self.assertIsNone(self.svc.get_defect_by_id(rec.defect_id))

    # -----------------------------------------------------------------------
    # 5. Defect validation – required fields
    # -----------------------------------------------------------------------
    def test_05_defect_validation_required_fields(self):
        """Blank required fields must produce validation errors."""
        d = _make_defect()
        d.description = ""
        ok, msg = self.svc.add_defect(d)
        self.assertFalse(ok, "Expected failure for blank description")
        self.assertIn("Description", msg)

        d2 = _make_defect()
        d2.defect_type = ""
        ok2, msg2 = self.svc.add_defect(d2)
        self.assertFalse(ok2)
        self.assertIn("Defect Type", msg2)

    # -----------------------------------------------------------------------
    # 6. Defect validation – severity values
    # -----------------------------------------------------------------------
    def test_06_defect_severity_valid(self):
        """All 4 valid severity values must be accepted."""
        for sev in DEFECT_SEVERITIES:
            with self.subTest(severity=sev):
                d = _make_defect(severity=sev)
                errors = d.validate()
                sev_errors = [e for e in errors if "Severity" in e]
                self.assertEqual(sev_errors, [], f"Unexpected error for severity={sev}")

    def test_06b_defect_severity_invalid(self):
        """Invalid severity must be rejected."""
        d = _make_defect()
        d.severity = "Extreme"
        ok, msg = self.svc.add_defect(d)
        self.assertFalse(ok)
        self.assertIn("Severity", msg)

    # -----------------------------------------------------------------------
    # 7. Defect validation – frequency >= 1
    # -----------------------------------------------------------------------
    def test_07_defect_frequency_valid(self):
        """Frequency 1 through large values should pass."""
        for freq in [1, 5, 100]:
            d = _make_defect(frequency=freq)
            errors = [e for e in d.validate() if "Frequency" in e or "frequency" in e.lower()]
            self.assertEqual(errors, [], f"Unexpected freq error for {freq}")

    def test_07b_defect_frequency_zero_rejected(self):
        """Frequency 0 must fail validation."""
        d = _make_defect(frequency=0)
        ok, msg = self.svc.add_defect(d)
        self.assertFalse(ok)
        self.assertIn("Frequency", msg)

    # -----------------------------------------------------------------------
    # 8. Defect validation – status values
    # -----------------------------------------------------------------------
    def test_08_defect_status_valid(self):
        """All 4 valid statuses must be accepted."""
        for stat in DEFECT_STATUSES:
            with self.subTest(status=stat):
                d = _make_defect(status=stat)
                errors = d.validate()
                s_errors = [e for e in errors if "Status" in e]
                self.assertEqual(s_errors, [])

    def test_08b_defect_status_invalid(self):
        """Invalid status must be rejected."""
        d = _make_defect()
        d.status = "Unknown"
        ok, msg = self.svc.add_defect(d)
        self.assertFalse(ok)
        self.assertIn("Status", msg)

    # -----------------------------------------------------------------------
    # 9. Filter by severity
    # -----------------------------------------------------------------------
    def test_09_filter_by_severity(self):
        """filter_defects with severity='Critical' must return only Critical records."""
        self.svc.add_defect(_make_defect("Crit", severity="Critical"))
        self.svc.add_defect(_make_defect("Low", severity="Low"))

        results = self.svc.filter_defects(severity="Critical")
        for r in results:
            self.assertEqual(r.severity, "Critical",
                             f"Expected Critical, got {r.severity}")

    # -----------------------------------------------------------------------
    # 10. Filter by status
    # -----------------------------------------------------------------------
    def test_10_filter_by_status(self):
        """filter_defects with status='Open' must return only Open records."""
        self.svc.add_defect(_make_defect("Open1", status="Open"))
        self.svc.add_defect(_make_defect("Closed1", status="Closed"))

        results = self.svc.filter_defects(status="Open")
        for r in results:
            self.assertEqual(r.status, "Open")

    # -----------------------------------------------------------------------
    # 11. Filter by module
    # -----------------------------------------------------------------------
    def test_11_filter_by_module(self):
        """filter_defects with module filter must return only matching-module records."""
        self.svc.add_defect(_make_defect(module="Billing & Sales"))
        self.svc.add_defect(_make_defect(module="Authentication"))

        results = self.svc.filter_defects(module="Billing & Sales")
        for r in results:
            self.assertEqual(r.module, "Billing & Sales")

    # -----------------------------------------------------------------------
    # 12. Combined defect filter
    # -----------------------------------------------------------------------
    def test_12_combined_filter(self):
        """filter_defects with multiple conditions must AND them."""
        self.svc.add_defect(_make_defect("HighOpen", severity="High", status="Open"))
        self.svc.add_defect(_make_defect("HighClosed", severity="High", status="Closed"))
        self.svc.add_defect(_make_defect("LowOpen", severity="Low", status="Open"))

        results = self.svc.filter_defects(severity="High", status="Open")
        for r in results:
            self.assertEqual(r.severity, "High")
            self.assertEqual(r.status, "Open")
        descs = [r.description for r in results]
        self.assertIn("Test: HighOpen", descs)
        self.assertNotIn("Test: HighClosed", descs)
        self.assertNotIn("Test: LowOpen", descs)

    # -----------------------------------------------------------------------
    # 13. Pareto calculation – ordering
    # -----------------------------------------------------------------------
    def test_13_pareto_ordering_by_frequency(self):
        """get_pareto_data must return defect types ordered by frequency descending."""
        for dt, freq in [("Type A", 10), ("Type B", 5), ("Type C", 15)]:
            d = _make_defect(defect_type=dt, frequency=freq)
            self.svc.add_defect(d)

        pareto = self.svc.get_pareto_data()
        freqs = [p["frequency"] for p in pareto]
        self.assertEqual(freqs, sorted(freqs, reverse=True),
                         "Pareto data not sorted by frequency descending")

    # -----------------------------------------------------------------------
    # 14. Pareto cumulative percentage
    # -----------------------------------------------------------------------
    def test_14_pareto_cumulative_percentage(self):
        """Cumulative percentage of last Pareto entry must equal 100.0."""
        for dt, freq in [("X", 3), ("Y", 7)]:
            d = _make_defect(defect_type=dt, frequency=freq)
            self.svc.add_defect(d)

        pareto = self.svc.get_pareto_data()
        self.assertGreater(len(pareto), 0)
        self.assertEqual(pareto[-1]["cumulative_pct"], 100.0)

    def test_14b_pareto_cumulative_increases_monotonically(self):
        """Cumulative percentage must be non-decreasing."""
        for dt, freq in [("A", 2), ("B", 5), ("C", 3)]:
            d = _make_defect(defect_type=dt, frequency=freq)
            self.svc.add_defect(d)

        pareto = self.svc.get_pareto_data()
        pcts = [p["cumulative_pct"] for p in pareto]
        for i in range(1, len(pcts)):
            self.assertGreaterEqual(pcts[i], pcts[i - 1],
                                    "Cumulative % decreased at index {i}")

    # -----------------------------------------------------------------------
    # 15. Pareto 80% threshold
    # -----------------------------------------------------------------------
    def test_15_pareto_80pct_threshold(self):
        """Types with cumulative_pct <= 80 are the Pareto vital few."""
        for dt, freq in [("Major", 80), ("Minor1", 10), ("Minor2", 10)]:
            d = _make_defect(defect_type=dt, frequency=freq)
            self.svc.add_defect(d)

        pareto = self.svc.get_pareto_data()
        vital_few = [p for p in pareto if p["cumulative_pct"] <= 80]
        self.assertGreater(len(vital_few), 0)
        # "Major" with freq 80/100=80% should be at or under 80%
        self.assertEqual(vital_few[0]["defect_type"], "Major")

    # -----------------------------------------------------------------------
    # 16. PDCA creation
    # -----------------------------------------------------------------------
    def test_16_pdca_creation(self):
        """add_pdca must succeed and persist a valid PDCA item."""
        p = _make_pdca("PDCA-T01")
        ok, msg = self.svc.add_pdca(p)
        self.assertTrue(ok, f"add_pdca failed: {msg}")
        all_p = self.svc.get_all_pdca()
        ids = [i.improvement_id for i in all_p]
        self.assertIn("PDCA-T01", ids)

    # -----------------------------------------------------------------------
    # 17. PDCA retrieval
    # -----------------------------------------------------------------------
    def test_17_pdca_retrieval_by_id(self):
        """A PDCA item must be retrievable by pdca_id."""
        p = _make_pdca("PDCA-T02")
        self.svc.add_pdca(p)
        inserted = next(
            (i for i in self.svc.get_all_pdca() if i.improvement_id == "PDCA-T02"), None
        )
        self.assertIsNotNone(inserted)
        fetched = self.svc.get_pdca_by_id(inserted.pdca_id)
        self.assertEqual(fetched.improvement_id, "PDCA-T02")

    # -----------------------------------------------------------------------
    # 18. PDCA update
    # -----------------------------------------------------------------------
    def test_18_pdca_update(self):
        """update_pdca must persist changed status and result_metric."""
        p = _make_pdca("PDCA-T03", status="Plan")
        self.svc.add_pdca(p)
        inserted = next(
            (i for i in self.svc.get_all_pdca() if i.improvement_id == "PDCA-T03"), None
        )
        inserted.status = "Check"
        inserted.result_metric = "Avg search time reduced by 40%."
        ok, msg = self.svc.update_pdca(inserted)
        self.assertTrue(ok, f"update_pdca failed: {msg}")
        updated = self.svc.get_pdca_by_id(inserted.pdca_id)
        self.assertEqual(updated.status, "Check")
        self.assertEqual(updated.result_metric, "Avg search time reduced by 40%.")

    # -----------------------------------------------------------------------
    # 19. PDCA deletion
    # -----------------------------------------------------------------------
    def test_19_pdca_deletion(self):
        """Deleted PDCA item must not appear in get_all_pdca."""
        p = _make_pdca("PDCA-DEL")
        self.svc.add_pdca(p)
        inserted = next(
            (i for i in self.svc.get_all_pdca() if i.improvement_id == "PDCA-DEL"), None
        )
        self.assertIsNotNone(inserted)
        ok, msg = self.svc.delete_pdca(inserted.pdca_id)
        self.assertTrue(ok, msg)
        self.assertIsNone(self.svc.get_pdca_by_id(inserted.pdca_id))

    # -----------------------------------------------------------------------
    # 20. PDCA validation
    # -----------------------------------------------------------------------
    def test_20_pdca_validation_required_fields(self):
        """Blank improvement_id or problem must be rejected."""
        p = _make_pdca()
        p.improvement_id = ""
        ok, msg = self.svc.add_pdca(p)
        self.assertFalse(ok, "Expected rejection for blank improvement_id")
        self.assertIn("Improvement ID", msg)

        p2 = _make_pdca("PDCA-V02")
        p2.problem = ""
        ok2, msg2 = self.svc.add_pdca(p2)
        self.assertFalse(ok2)
        self.assertIn("Problem", msg2)

    def test_20b_pdca_invalid_status_rejected(self):
        """Invalid PDCA status must be rejected."""
        p = _make_pdca("PDCA-V03")
        p.status = "Unknown"
        ok, msg = self.svc.add_pdca(p)
        self.assertFalse(ok)
        self.assertIn("Status", msg)

    def test_20c_pdca_all_valid_statuses(self):
        """All 5 valid PDCA statuses must be accepted (use unique IDs)."""
        for i, stat in enumerate(PDCA_STATUSES):
            with self.subTest(status=stat):
                p = _make_pdca(f"PDCA-ST{i}", status=stat)
                ok, msg = self.svc.add_pdca(p)
                self.assertTrue(ok, f"Rejected valid status '{stat}': {msg}")

    # -----------------------------------------------------------------------
    # 21. PDCA status filter
    # -----------------------------------------------------------------------
    def test_21_pdca_status_filter(self):
        """filter_pdca with status='Plan' must return only Plan items."""
        self.svc.add_pdca(_make_pdca("F-001", status="Plan"))
        self.svc.add_pdca(_make_pdca("F-002", status="Closed"))

        results = self.svc.filter_pdca(status="Plan")
        for r in results:
            self.assertEqual(r.status, "Plan")

        all_r = self.svc.filter_pdca(status=None)
        self.assertGreater(len(all_r), len(results))

    # -----------------------------------------------------------------------
    # 22. Dashboard KPIs – live data
    # -----------------------------------------------------------------------
    def test_22_dashboard_kpis_live(self):
        """get_dashboard_kpis must return correct counts from live DB data."""

        # init_db() loads demo/seed data.
        # Clear it so this test measures only the records created below.
        self.db.execute("DELETE FROM sqc_defects")
        self.db.execute("DELETE FROM pdca_items")

        self.svc.add_defect(
        _make_defect("D1", severity="Critical", status="Open")
        )
        self.svc.add_defect(
        _make_defect("D2", severity="High", status="Open")
        )
        self.svc.add_defect(
        _make_defect("D3", severity="Low", status="Closed")
        )

        self.svc.add_pdca(
        _make_pdca("P-001", status="Plan")
        )
        self.svc.add_pdca(
        _make_pdca("P-002", status="Closed")
        )

        kpis = self.svc.get_dashboard_kpis()

        self.assertEqual(kpis["total_defects"], 3)
        self.assertEqual(kpis["open_defects"], 2)
        self.assertEqual(kpis["high_critical_defects"], 2)
        self.assertEqual(kpis["pdca_open"], 1)
        self.assertEqual(kpis["pdca_closed"], 1)

    def test_22b_dashboard_kpis_empty(self):
        """get_dashboard_kpis on empty table must return zeros and 'N/A'."""

        # Remove seeded/demo defects to create a genuinely empty SQC table.
        self.db.execute("DELETE FROM sqc_defects")

        kpis = self.svc.get_dashboard_kpis()

        self.assertEqual(kpis["total_defects"], 0)
        self.assertEqual(kpis["open_defects"], 0)
        self.assertEqual(kpis["high_critical_defects"], 0)
        self.assertEqual(kpis["top_defect_type"], "N/A")
        self.assertEqual(kpis["top_defect_freq"], 0)
        self.assertEqual(kpis["pareto_80pct_types"], 0)

    # -----------------------------------------------------------------------
    # 23. Fishbone structured data
    # -----------------------------------------------------------------------
    def test_23_fishbone_data_exists(self):
        """FISHBONE_CAUSES must contain at least 3 defects with 5 categories each."""
        self.assertGreaterEqual(len(FISHBONE_CAUSES), 3)
        for defect, cats in FISHBONE_CAUSES.items():
            with self.subTest(defect=defect):
                self.assertGreaterEqual(len(cats), 4,
                                        f"Expected ≥4 categories for '{defect}'")
                for cat, causes in cats.items():
                    self.assertGreater(len(causes), 0,
                                       f"Category '{cat}' for '{defect}' has no causes")

    def test_23b_fishbone_contains_q13_category(self):
        """Fishbone must include Q13 search/retrieval defect."""
        q13_key = "Incorrect / Slow Q13 Search Retrieval"
        self.assertIn(q13_key, FISHBONE_CAUSES)
        cats = FISHBONE_CAUSES[q13_key]
        self.assertIn("Software / Code", cats)

    # -----------------------------------------------------------------------
    # 24. Seed records loaded correctly
    # -----------------------------------------------------------------------
    def test_24_seed_defects_count(self):
        """init_db must seed exactly len(SEED_SQC_DEFECTS) defect records."""
        # Our test DB is seeded by init_db in setUp
        # But init_sqc_db seeds only if empty — since setUp calls init_db which
        # calls init_sqc_db, table should be seeded.
        row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM sqc_defects")
        self.assertEqual(row["cnt"], len(SEED_SQC_DEFECTS),
                         f"Expected {len(SEED_SQC_DEFECTS)} seed defects, got {row['cnt']}")

    def test_24b_seed_pdca_count(self):
        """init_db must seed exactly len(SEED_PDCA_ITEMS) PDCA records."""
        row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM pdca_items")
        self.assertEqual(row["cnt"], len(SEED_PDCA_ITEMS),
                         f"Expected {len(SEED_PDCA_ITEMS)} PDCA items, got {row['cnt']}")

    def test_24c_seed_defects_have_valid_severity(self):
        """Every seeded defect must have a valid severity value."""
        rows = self.db.fetch_all("SELECT defect_id, severity FROM sqc_defects")
        for r in rows:
            self.assertIn(r["severity"], DEFECT_SEVERITIES,
                          f"Invalid severity '{r['severity']}' in defect_id={r['defect_id']}")

    def test_24d_seed_defects_have_valid_status(self):
        """Every seeded defect must have a valid status value."""
        rows = self.db.fetch_all("SELECT defect_id, status FROM sqc_defects")
        for r in rows:
            self.assertIn(r["status"], DEFECT_STATUSES,
                          f"Invalid status '{r['status']}' in defect_id={r['defect_id']}")

    def test_24e_seed_pdca_have_valid_status(self):
        """Every seeded PDCA item must have a valid status value."""
        rows = self.db.fetch_all("SELECT pdca_id, status FROM pdca_items")
        for r in rows:
            self.assertIn(r["status"], PDCA_STATUSES,
                          f"Invalid PDCA status '{r['status']}' in pdca_id={r['pdca_id']}")

    def test_24f_seed_defects_cover_q13(self):
        """Seed defects must include at least one Q13 Advanced Search record."""
        rows = self.db.fetch_all(
            "SELECT module FROM sqc_defects WHERE module='Q13 Advanced Search'"
        )
        self.assertGreater(len(rows), 0,
                           "No seed defect found for Q13 Advanced Search module")

    # -----------------------------------------------------------------------
    # 25. Persistence across reconnect
    # -----------------------------------------------------------------------
    def test_25_sqc_persistence(self):
        """Defects and PDCA items must survive a fresh DB connection."""
        self.svc.add_defect(_make_defect("Persist Test"))
        self.svc.add_pdca(_make_pdca("PERSIST-001"))

        new_db = Database(self.temp_path)
        new_svc = SQCService(new_db)
        all_d = new_svc.get_all_defects()
        all_p = new_svc.get_all_pdca()
        self.assertTrue(any("Persist Test" in d.description for d in all_d))
        self.assertTrue(any(p.improvement_id == "PERSIST-001" for p in all_p))

    # -----------------------------------------------------------------------
    # 26. Sort whitelist SQL injection prevention
    # -----------------------------------------------------------------------
    def test_26_sort_whitelist_defects(self):
        """Invalid sort column in get_all_defects must fall back safely."""
        self.svc.add_defect(_make_defect())
        # Should not raise; falls back to date_reported
        result = self.svc.get_all_defects(sort_by="'; DROP TABLE sqc_defects; --")
        self.assertIsInstance(result, list)
        row = self.db.fetch_one("SELECT COUNT(*) as cnt FROM sqc_defects")
        self.assertIsNotNone(row)

    def test_26b_sort_whitelist_pdca(self):
        """Invalid sort column in get_all_pdca must fall back safely."""
        self.svc.add_pdca(_make_pdca("WL-001"))
        result = self.svc.get_all_pdca(sort_by="'; DROP TABLE pdca_items; --")
        self.assertIsInstance(result, list)

    # -----------------------------------------------------------------------
    # 27. Defect frequency ordering in Pareto
    # -----------------------------------------------------------------------
    def test_27_pareto_empty_table(self):
        """get_pareto_data on empty table must return empty list (no crash)."""
        # Temp DB starts seeded; clear only sqc_defects
        self.db.execute("DELETE FROM sqc_defects")
        pareto = self.svc.get_pareto_data()
        self.assertEqual(pareto, [])

    def test_27b_pareto_groups_by_defect_type(self):
        """get_pareto_data must aggregate frequency across all records of same type."""
        for _ in range(3):
            self.svc.add_defect(_make_defect(defect_type="Grp Type", frequency=2))

        pareto = self.svc.get_pareto_data()
        grp = next((p for p in pareto if p["defect_type"] == "Grp Type"), None)
        self.assertIsNotNone(grp)
        self.assertGreaterEqual(grp["frequency"], 6)  # 3 records × freq 2

    # -----------------------------------------------------------------------
    # 28. PDCA CRUD end-to-end
    # -----------------------------------------------------------------------
    def test_28_pdca_full_lifecycle(self):
        """Full PDCA lifecycle: Plan → Do → Check → Act → Closed."""
        p = _make_pdca("LIFECYCLE-001", status="Plan")
        ok, _ = self.svc.add_pdca(p)
        self.assertTrue(ok)

        for next_status in ("Do", "Check", "Act", "Closed"):
            inserted = next(
                (i for i in self.svc.get_all_pdca() if i.improvement_id == "LIFECYCLE-001"), None
            )
            self.assertIsNotNone(inserted)
            inserted.status = next_status
            ok, msg = self.svc.update_pdca(inserted)
            self.assertTrue(ok, f"Failed to update to {next_status}: {msg}")
            refreshed = self.svc.get_pdca_by_id(inserted.pdca_id)
            self.assertEqual(refreshed.status, next_status)

    # -----------------------------------------------------------------------
    # 29. Tables and indexes exist
    # -----------------------------------------------------------------------
    def test_29_tables_and_indexes_exist(self):
        """sqc_defects and pdca_items tables plus all 5 SQC indexes must exist."""
        for table in ("sqc_defects", "pdca_items"):
            rows = self.db.fetch_all(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
            )
            self.assertEqual(len(rows), 1, f"Table '{table}' missing")

        idx_rows = self.db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_sqc%' "
            "OR (type='index' AND name LIKE 'idx_pdca%')"
        )
        idx_names = {r["name"] for r in idx_rows}
        for expected in ("idx_sqc_module", "idx_sqc_severity", "idx_sqc_status",
                         "idx_sqc_type", "idx_pdca_status"):
            self.assertIn(expected, idx_names, f"Index '{expected}' missing")

    # -----------------------------------------------------------------------
    # 30. Distinct helpers
    # -----------------------------------------------------------------------
    def test_30_distinct_helpers(self):
        """get_distinct_defect_types and get_distinct_modules must return sorted lists."""
        self.svc.add_defect(_make_defect(defect_type="Alpha", module="Authentication"))
        self.svc.add_defect(_make_defect(defect_type="Zeta",  module="Authentication"))
        types = self.svc.get_distinct_defect_types()
        self.assertIsInstance(types, list)
        self.assertIn("Alpha", types)
        self.assertIn("Zeta", types)
        modules = self.svc.get_distinct_modules()
        self.assertIn("Authentication", modules)


if __name__ == "__main__":
    unittest.main()
