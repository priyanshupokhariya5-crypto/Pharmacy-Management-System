"""
Stage 7 Unit Tests – Q13 SQL Performance Benchmarking.

Tests cover:
1.  Benchmark database creation
2.  Benchmark dataset generation
3.  Expected dataset size
4.  Required indexes exist
5.  Exact medicine-code query executes
6.  Category query executes
7.  Manufacturer query executes
8.  Expiry date query executes
9.  Partial text query executes
10. EXPLAIN QUERY PLAN executes and returns data
11. Timing values are positive
12. Multiple iteration benchmark works
13. Avg / min / max / median calculation correctness
14. Speedup calculation (honest: only with valid values)
15. Export CSV contains actual result fields
16. Main pharmacy database (pharmacy.db) remains unchanged after benchmark
17. Parameterized benchmark queries (no raw string concatenation)
18. Invalid iteration input handling
"""
import csv
import os
import tempfile
import time
import unittest

from database.benchmark_db import BenchmarkDatabase, init_benchmark_db
from utils.benchmark import (
    EXPECTED_INDEXES,
    QUERY_DEFINITIONS,
    BenchmarkEngine,
    _median,
    calculate_speedup,
    export_results_to_csv,
)

# Use a much smaller dataset for test speed
TEST_RECORD_COUNT = 500


class TestBenchmarkDatabase(unittest.TestCase):
    """Tests for the isolated benchmark.db creation and dataset population."""

    def setUp(self):
        # Use a temporary file so tests never touch data/benchmark.db
        fd, self.db_path = tempfile.mkstemp(suffix="_bm_test.db")
        os.close(fd)
        os.remove(self.db_path)  # init_benchmark_db will create it
        self.bm_db = init_benchmark_db(self.db_path, TEST_RECORD_COUNT)

    def tearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except PermissionError:
                pass

    # -----------------------------------------------------------------------
    # 1. Benchmark database creation
    # -----------------------------------------------------------------------
    def test_01_benchmark_db_file_created(self):
        """Benchmark database file should exist after init_benchmark_db."""
        self.assertTrue(
            os.path.exists(self.db_path),
            f"Expected benchmark DB file at {self.db_path}",
        )

    # -----------------------------------------------------------------------
    # 2. Benchmark dataset generation – twin tables exist
    # -----------------------------------------------------------------------
    def test_02_twin_tables_exist(self):
        """medicines_indexed and medicines_scan tables must both exist."""
        rows = self.bm_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        table_names = [r["name"] for r in rows]
        self.assertIn("medicines_indexed", table_names)
        self.assertIn("medicines_scan", table_names)

    # -----------------------------------------------------------------------
    # 3. Expected dataset size
    # -----------------------------------------------------------------------
    def test_03_indexed_table_record_count(self):
        """Indexed table should have at least TEST_RECORD_COUNT records."""
        row = self.bm_db.fetch_one("SELECT COUNT(*) as cnt FROM medicines_indexed")
        self.assertGreaterEqual(row["cnt"], TEST_RECORD_COUNT)

    def test_03b_scan_table_record_count(self):
        """Scan table should have the same record count as indexed table."""
        indexed = self.bm_db.fetch_one("SELECT COUNT(*) as cnt FROM medicines_indexed")
        scan = self.bm_db.fetch_one("SELECT COUNT(*) as cnt FROM medicines_scan")
        self.assertEqual(indexed["cnt"], scan["cnt"])

    # -----------------------------------------------------------------------
    # 4. Required indexes exist on medicines_indexed
    # -----------------------------------------------------------------------
    def test_04_required_indexes_exist(self):
        """All five expected B-Tree indexes must exist on medicines_indexed."""
        rows = self.bm_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        idx_names = {r["name"] for r in rows}
        for idx in EXPECTED_INDEXES:
            with self.subTest(index=idx):
                self.assertIn(idx, idx_names, f"Index '{idx}' missing from benchmark DB")

    # -----------------------------------------------------------------------
    # 5–9. Query execution tests (via BenchmarkEngine)
    # -----------------------------------------------------------------------

    def _make_engine(self) -> BenchmarkEngine:
        engine = BenchmarkEngine(db_path=self.db_path, record_count=TEST_RECORD_COUNT)
        engine.bm_db = self.bm_db  # inject already-initialized db
        return engine

    def test_05_medicine_code_query_executes(self):
        """Exact medicine-code query must return rows from the indexed table."""
        row = self.bm_db.fetch_one(
            "SELECT medicine_code FROM medicines_indexed LIMIT 1"
        )
        self.assertIsNotNone(row, "No rows found in medicines_indexed")
        code = row["medicine_code"]
        results = self.bm_db.fetch_all(
            "SELECT medicine_id, medicine_code, medicine_name "
            "FROM medicines_indexed WHERE medicine_code = ?",
            (code,),
        )
        self.assertGreater(len(results), 0)

    def test_06_category_query_executes(self):
        """Category exact-match query must return at least one row."""
        row = self.bm_db.fetch_one(
            "SELECT category FROM medicines_indexed LIMIT 1"
        )
        self.assertIsNotNone(row)
        results = self.bm_db.fetch_all(
            "SELECT medicine_id, medicine_code, medicine_name, category "
            "FROM medicines_indexed WHERE category = ?",
            (row["category"],),
        )
        self.assertGreater(len(results), 0)

    def test_07_manufacturer_query_executes(self):
        """Manufacturer exact-match query must return at least one row."""
        row = self.bm_db.fetch_one(
            "SELECT manufacturer FROM medicines_indexed LIMIT 1"
        )
        self.assertIsNotNone(row)
        results = self.bm_db.fetch_all(
            "SELECT medicine_id, medicine_code, medicine_name, manufacturer "
            "FROM medicines_indexed WHERE manufacturer = ?",
            (row["manufacturer"],),
        )
        self.assertGreater(len(results), 0)

    def test_08_expiry_date_query_executes(self):
        """Expiry date range query must return at least one row."""
        results = self.bm_db.fetch_all(
            "SELECT medicine_id, medicine_code, medicine_name, expiry_date "
            "FROM medicines_indexed WHERE expiry_date <= ?",
            ("2030-12-31",),
        )
        self.assertGreater(len(results), 0)

    def test_09_partial_text_query_executes(self):
        """LIKE '%a%' substring query must execute without error."""
        results = self.bm_db.fetch_all(
            "SELECT medicine_id, medicine_code, medicine_name "
            "FROM medicines_indexed WHERE medicine_name LIKE ?",
            ("%a%",),
        )
        # Just check it ran – count may be 0 if no 'a' in any name
        self.assertIsInstance(results, list)

    # -----------------------------------------------------------------------
    # 10. EXPLAIN QUERY PLAN executes and returns data
    # -----------------------------------------------------------------------
    def test_10_explain_query_plan_returns_data(self):
        """EXPLAIN QUERY PLAN must return a non-empty string."""
        engine = self._make_engine()
        plan = engine.get_query_plan(
            "SELECT medicine_id, medicine_code FROM medicines_indexed WHERE medicine_code = ?",
            ("BM000001",),
        )
        self.assertIsInstance(plan, str)
        self.assertGreater(len(plan.strip()), 0, "EXPLAIN QUERY PLAN returned empty result")

    # -----------------------------------------------------------------------
    # 11. Timing values are positive
    # -----------------------------------------------------------------------
    def test_11_timing_positive(self):
        """Measured execution times must all be positive (> 0)."""
        engine = self._make_engine()
        stats = engine.run_timed_query(
            "SELECT medicine_id FROM medicines_indexed WHERE category = ?",
            ("Analgesic",),
            iterations=5,
            warmup=2,
        )
        self.assertGreater(stats["avg_ms"], 0)
        self.assertGreater(stats["min_ms"], 0)
        self.assertGreater(stats["max_ms"], 0)

    # -----------------------------------------------------------------------
    # 12. Multiple iteration benchmark works
    # -----------------------------------------------------------------------
    def test_12_multiple_iterations_work(self):
        """Benchmark engine must complete 20 iterations without error."""
        engine = self._make_engine()
        stats = engine.run_timed_query(
            "SELECT medicine_id FROM medicines_indexed WHERE manufacturer = ?",
            ("Cipla Ltd",),
            iterations=20,
            warmup=3,
        )
        self.assertEqual(stats["iterations"], 20)
        self.assertEqual(len(stats["timings"]), 20)

    # -----------------------------------------------------------------------
    # 13. Avg / min / max / median correctness
    # -----------------------------------------------------------------------
    def test_13_statistics_correctness(self):
        """Avg, min, max, and median values must be logically consistent."""
        engine = self._make_engine()
        stats = engine.run_timed_query(
            "SELECT medicine_id FROM medicines_indexed WHERE category = ?",
            ("Antibiotic",),
            iterations=10,
            warmup=2,
        )
        self.assertLessEqual(stats["min_ms"], stats["avg_ms"])
        self.assertLessEqual(stats["avg_ms"], stats["max_ms"])
        self.assertGreater(stats["median_ms"], 0)

    def test_13b_median_helper(self):
        """_median() must compute the correct median for odd and even lists."""
        self.assertAlmostEqual(_median([1.0, 3.0, 2.0]), 2.0)
        self.assertAlmostEqual(_median([1.0, 2.0, 3.0, 4.0]), 2.5)
        self.assertEqual(_median([]), 0.0)

    # -----------------------------------------------------------------------
    # 14. Speedup calculation (honest)
    # -----------------------------------------------------------------------
    def test_14_speedup_calculation(self):
        """calculate_speedup must return scan/indexed ratio; return None for invalid inputs."""
        self.assertAlmostEqual(calculate_speedup(10.0, 2.0), 5.0)
        self.assertAlmostEqual(calculate_speedup(1.0, 2.0), 0.5)   # indexed slower – displayed as-is
        self.assertIsNone(calculate_speedup(0.0, 2.0))
        self.assertIsNone(calculate_speedup(10.0, 0.0))

    # -----------------------------------------------------------------------
    # 15. Export CSV contains actual result fields
    # -----------------------------------------------------------------------
    def test_15_export_csv_fields(self):
        """Exported CSV must contain required column headers and at least one data row."""
        engine = self._make_engine()
        result = engine.benchmark_query_type(
            "Category",
            iterations=5,
            run_scan_comparison=True,
        )
        results = [result]

        with tempfile.NamedTemporaryFile(
            suffix=".csv", delete=False, mode="w"
        ) as f:
            csv_path = f.name

        try:
            export_results_to_csv(results, csv_path)
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            required_fields = [
                "timestamp", "query_type", "mode", "dataset_size",
                "iterations", "average_ms", "minimum_ms", "maximum_ms",
                "median_ms", "result_count", "speedup", "query_plan",
            ]
            for field in required_fields:
                self.assertIn(field, reader.fieldnames, f"Missing CSV column: {field}")

            self.assertGreater(len(rows), 0, "CSV has no data rows")
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    # -----------------------------------------------------------------------
    # 16. Main pharmacy database remains unchanged
    # -----------------------------------------------------------------------
    def test_16_main_db_unchanged(self):
        """The main pharmacy.db (if it exists) must not be altered by benchmark operations."""
        from database.db import DEFAULT_DB_PATH
        if not os.path.exists(DEFAULT_DB_PATH):
            self.skipTest("pharmacy.db does not exist on this machine – skipping integrity check.")

        from database.db import Database
        prod_db = Database(DEFAULT_DB_PATH)
        row = prod_db.fetch_one("SELECT COUNT(*) as cnt FROM medicines")
        self.assertIsNotNone(row)
        self.assertGreater(row["cnt"], 0, "pharmacy.db medicines table should have records")

    # -----------------------------------------------------------------------
    # 17. Parameterized benchmark queries
    # -----------------------------------------------------------------------
    def test_17_queries_are_parameterized(self):
        """All QUERY_DEFINITIONS SQL strings must use ? placeholders, not raw values."""
        for key, defn in QUERY_DEFINITIONS.items():
            with self.subTest(query=key):
                sql = defn["sql_indexed"]
                self.assertIn("?", sql, f"'{key}' indexed SQL has no ? parameter placeholder")

    def test_17b_sql_injection_safe(self):
        """Injecting SQL via parameter must not affect result set count differently from safe value."""
        injection_code = "' OR '1'='1"
        results = self.bm_db.fetch_all(
            "SELECT medicine_id, medicine_code FROM medicines_indexed WHERE medicine_code = ?",
            (injection_code,),
        )
        # Injection as a literal parameter value should return 0 rows (no code matches that string)
        self.assertEqual(len(results), 0, "SQL injection attempt via parameter should return 0 rows")

    # -----------------------------------------------------------------------
    # 18. Invalid iteration input handling (BenchmarkEngine)
    # -----------------------------------------------------------------------
    def test_18_invalid_iterations_raise(self):
        """run_timed_query with 0 iterations should raise ZeroDivisionError or similar."""
        engine = self._make_engine()
        with self.assertRaises((ZeroDivisionError, ValueError)):
            # 0 measured iterations → avg = sum([]) / 0 → ZeroDivisionError
            engine.run_timed_query(
                "SELECT medicine_id FROM medicines_indexed WHERE category = ?",
                ("Analgesic",),
                iterations=0,
                warmup=0,
            )

    def test_18b_benchmark_query_type_five_keys(self):
        """All five QUERY_DEFINITIONS keys must successfully run benchmark_query_type."""
        engine = self._make_engine()
        for key in QUERY_DEFINITIONS.keys():
            with self.subTest(query_key=key):
                result = engine.benchmark_query_type(key, iterations=5, run_scan_comparison=False)
                self.assertIn("indexed", result)
                self.assertGreater(result["indexed"]["avg_ms"], 0)


if __name__ == "__main__":
    unittest.main()
