"""
Search Performance Benchmarking Engine for Q13 – Faster Search & Retrieval.

Measures REAL SQLite execution times on an isolated benchmark database.
All values are empirically measured; NOTHING is fabricated or hard-coded.

Academic Accuracy Notice:
- B-Tree indexes CAN accelerate: exact-match (=), prefix LIKE 'X%', range (<=, >=).
- B-Tree indexes generally CANNOT accelerate arbitrary substring search LIKE '%X%'
  because the leading wildcard prevents index traversal.
  EXPLAIN QUERY PLAN will confirm actual SQLite planner behaviour at runtime.
"""
import csv
import os
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from database.benchmark_db import BenchmarkDatabase, init_benchmark_db, DEFAULT_BENCHMARK_DB_PATH

# Indexes expected to exist on the medicines_indexed table inside benchmark.db
EXPECTED_INDEXES = [
    "idx_bm_code",
    "idx_bm_name",
    "idx_bm_category",
    "idx_bm_mfr",
    "idx_bm_expiry",
]

# Warm-up runs before actual measurement (not included in statistics)
WARMUP_RUNS = 5

# Default benchmark queries (indexed table)
QUERY_DEFINITIONS = {
    "Medicine Code": {
        "label": "Medicine Code Exact Match",
        "sql_indexed": (
            "SELECT medicine_id, medicine_code, medicine_name "
            "FROM medicines_indexed WHERE medicine_code = ?"
        ),
        "sql_scan": (
            "SELECT medicine_id, medicine_code, medicine_name "
            "FROM medicines_scan WHERE medicine_code = ?"
        ),
        "param_fn": lambda bm_db: _pick_sample_code(bm_db),
        "index_expected": True,
        "note": "Exact match on medicine_code. SQLite can use B-Tree index (idx_bm_code).",
    },
    "Category": {
        "label": "Category Exact Match",
        "sql_indexed": (
            "SELECT medicine_id, medicine_code, medicine_name, category "
            "FROM medicines_indexed WHERE category = ?"
        ),
        "sql_scan": (
            "SELECT medicine_id, medicine_code, medicine_name, category "
            "FROM medicines_scan WHERE category = ?"
        ),
        "param_fn": lambda bm_db: _pick_sample_category(bm_db),
        "index_expected": True,
        "note": "Exact match on category. SQLite can use B-Tree index (idx_bm_category).",
    },
    "Manufacturer": {
        "label": "Manufacturer Exact Match",
        "sql_indexed": (
            "SELECT medicine_id, medicine_code, medicine_name, manufacturer "
            "FROM medicines_indexed WHERE manufacturer = ?"
        ),
        "sql_scan": (
            "SELECT medicine_id, medicine_code, medicine_name, manufacturer "
            "FROM medicines_scan WHERE manufacturer = ?"
        ),
        "param_fn": lambda bm_db: _pick_sample_manufacturer(bm_db),
        "index_expected": True,
        "note": "Exact match on manufacturer. SQLite can use B-Tree index (idx_bm_mfr).",
    },
    "Expiry Date": {
        "label": "Expiry Date Range Filter",
        "sql_indexed": (
            "SELECT medicine_id, medicine_code, medicine_name, expiry_date "
            "FROM medicines_indexed WHERE expiry_date <= ?"
        ),
        "sql_scan": (
            "SELECT medicine_id, medicine_code, medicine_name, expiry_date "
            "FROM medicines_scan WHERE expiry_date <= ?"
        ),
        "param_fn": lambda bm_db: _pick_sample_expiry(bm_db),
        "index_expected": True,
        "note": "Range filter on expiry_date. SQLite can use B-Tree index (idx_bm_expiry).",
    },
    "Partial Text": {
        "label": "Partial Text Search – Substring",
        "sql_indexed": (
            "SELECT medicine_id, medicine_code, medicine_name "
            "FROM medicines_indexed WHERE medicine_name LIKE ?"
        ),
        "sql_scan": None,  # No meaningful indexed vs scan comparison for LIKE '%X%'
        "param_fn": lambda bm_db: ("%a%",),
        "index_expected": False,
        "note": (
            "Substring search LIKE '%term%'. The leading wildcard prevents B-Tree index traversal. "
            "SQLite performs a sequential scan of indexed rows. "
            "EXPLAIN QUERY PLAN will confirm actual planner behaviour."
        ),
    },
}


# ---------------------------------------------------------------------------
# Parameter helper functions
# ---------------------------------------------------------------------------

def _pick_sample_code(bm_db: BenchmarkDatabase) -> Tuple[str, ...]:
    row = bm_db.fetch_one(
        "SELECT medicine_code FROM medicines_indexed ORDER BY RANDOM() LIMIT 1"
    )
    return (row["medicine_code"] if row else "BM000001",)


def _pick_sample_category(bm_db: BenchmarkDatabase) -> Tuple[str, ...]:
    row = bm_db.fetch_one(
        "SELECT category FROM medicines_indexed ORDER BY RANDOM() LIMIT 1"
    )
    return (row["category"] if row else "Analgesic",)


def _pick_sample_manufacturer(bm_db: BenchmarkDatabase) -> Tuple[str, ...]:
    row = bm_db.fetch_one(
        "SELECT manufacturer FROM medicines_indexed ORDER BY RANDOM() LIMIT 1"
    )
    return (row["manufacturer"] if row else "Cipla Ltd",)


def _pick_sample_expiry(bm_db: BenchmarkDatabase) -> Tuple[str, ...]:
    """Return the median expiry date so the range returns meaningful results."""
    row = bm_db.fetch_one(
        "SELECT expiry_date FROM medicines_indexed "
        "ORDER BY expiry_date LIMIT 1 OFFSET "
        "(SELECT COUNT(*)/2 FROM medicines_indexed)"
    )
    return (row["expiry_date"] if row else "2026-12-31",)


# ---------------------------------------------------------------------------
# Core benchmark engine
# ---------------------------------------------------------------------------

class BenchmarkEngine:
    """
    Measures actual SQLite query execution times on the isolated benchmark database.
    Uses time.perf_counter() for high-resolution sub-millisecond timing.
    UI rendering time is NEVER included in SQL timing measurements.
    """

    def __init__(self, db_path: Optional[str] = None, record_count: int = 5000):
        self.db_path = db_path or DEFAULT_BENCHMARK_DB_PATH
        self.record_count = record_count
        self.bm_db: Optional[BenchmarkDatabase] = None

    def initialize(self) -> BenchmarkDatabase:
        """Ensures benchmark.db exists and is populated. Returns BenchmarkDatabase handle."""
        self.bm_db = init_benchmark_db(self.db_path, self.record_count)
        return self.bm_db

    def get_record_count(self) -> int:
        """Returns the number of records in the indexed benchmark table."""
        if self.bm_db is None:
            self.initialize()
        row = self.bm_db.fetch_one("SELECT COUNT(*) as cnt FROM medicines_indexed")
        return row["cnt"] if row else 0

    def verify_indexes(self) -> Dict[str, bool]:
        """Checks that all expected indexes exist. Returns {index_name: exists}."""
        if self.bm_db is None:
            self.initialize()
        rows = self.bm_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        existing = {r["name"] for r in rows}
        return {idx: (idx in existing) for idx in EXPECTED_INDEXES}

    def get_query_plan(self, sql: str, params: Tuple[Any, ...]) -> str:
        """Runs EXPLAIN QUERY PLAN and returns a formatted string of the actual plan."""
        if self.bm_db is None:
            self.initialize()
        explain_sql = f"EXPLAIN QUERY PLAN {sql}"
        try:
            rows = self.bm_db.fetch_all(explain_sql, params)
            lines = []
            for r in rows:
                keys = r.keys()
                if "detail" in keys:
                    lines.append(r["detail"])
                else:
                    lines.append(" | ".join(str(r[k]) for k in keys))
            return "\n".join(lines) if lines else "(No plan returned)"
        except Exception as e:
            return f"(EXPLAIN QUERY PLAN error: {e})"

    def run_timed_query(
        self,
        sql: str,
        params: Tuple[Any, ...],
        iterations: int = 100,
        warmup: int = WARMUP_RUNS,
    ) -> Dict[str, Any]:
        """
        Executes a parameterized SQL query N times on the benchmark database,
        measuring pure SQL execution time via time.perf_counter().

        Warm-up runs are discarded. Only iteration timings are used for statistics.
        Returns avg, min, max, and individual timings.
        """
        if self.bm_db is None:
            self.initialize()

        conn = self.bm_db.get_connection()
        try:
            cursor = conn.cursor()

            # Warm-up: discard these timings
            for _ in range(warmup):
                cursor.execute(sql, params)
                cursor.fetchall()

            # Measured iterations
            timings: List[float] = []
            result_count = 0
            for _ in range(iterations):
                t0 = time.perf_counter()
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                timings.append(elapsed_ms)
                result_count = len(rows)

            avg_ms = sum(timings) / len(timings)
            min_ms = min(timings)
            max_ms = max(timings)
            median_ms = _median(timings)

            return {
                "avg_ms": round(avg_ms, 4),
                "min_ms": round(min_ms, 4),
                "max_ms": round(max_ms, 4),
                "median_ms": round(median_ms, 4),
                "result_count": result_count,
                "iterations": iterations,
                "warmup": warmup,
                "timings": timings,
            }
        finally:
            conn.close()

    def benchmark_query_type(
        self,
        query_key: str,
        iterations: int = 100,
        run_scan_comparison: bool = True,
    ) -> Dict[str, Any]:
        """
        Runs a full benchmark for the given query type (key from QUERY_DEFINITIONS).
        Returns empirical indexed stats, optional scan stats, speedup, and query plans.
        """
        if self.bm_db is None:
            self.initialize()

        defn = QUERY_DEFINITIONS[query_key]
        params = defn["param_fn"](self.bm_db)

        # --- Indexed query ---
        indexed_stats = self.run_timed_query(
            defn["sql_indexed"], params, iterations=iterations
        )
        indexed_plan = self.get_query_plan(defn["sql_indexed"], params)

        result: Dict[str, Any] = {
            "query_key": query_key,
            "label": defn["label"],
            "note": defn["note"],
            "sql_indexed": defn["sql_indexed"],
            "params": params,
            "indexed": indexed_stats,
            "indexed_plan": indexed_plan,
            "scan": None,
            "scan_plan": None,
            "speedup": None,
            "timestamp": datetime.now().isoformat(),
        }

        # --- Scan comparison (only for queries that support it) ---
        if run_scan_comparison and defn["sql_scan"]:
            scan_stats = self.run_timed_query(
                defn["sql_scan"], params, iterations=iterations
            )
            scan_plan = self.get_query_plan(defn["sql_scan"], params)
            result["scan"] = scan_stats
            result["scan_plan"] = scan_plan

            # Speedup = scan_avg / indexed_avg (honest; don't hide if indexed is slower)
            if indexed_stats["avg_ms"] > 0:
                result["speedup"] = round(
                    scan_stats["avg_ms"] / indexed_stats["avg_ms"], 3
                )

        return result


# ---------------------------------------------------------------------------
# Statistics helper
# ---------------------------------------------------------------------------

def _median(values: List[float]) -> float:
    sorted_v = sorted(values)
    n = len(sorted_v)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 0:
        return (sorted_v[mid - 1] + sorted_v[mid]) / 2.0
    return sorted_v[mid]


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

def export_results_to_csv(results: List[Dict[str, Any]], csv_path: str) -> str:
    """
    Exports benchmark results to a CSV file.
    All values come from actual measured benchmark execution – nothing is fabricated.
    Returns the absolute path of the written file.
    """
    fieldnames = [
        "timestamp",
        "query_type",
        "mode",
        "dataset_size",
        "iterations",
        "average_ms",
        "minimum_ms",
        "maximum_ms",
        "median_ms",
        "result_count",
        "speedup",
        "query_plan",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results:
            # Indexed row
            writer.writerow({
                "timestamp": r.get("timestamp", ""),
                "query_type": r.get("label", ""),
                "mode": "Indexed",
                "dataset_size": r.get("indexed", {}).get("result_count", ""),
                "iterations": r.get("indexed", {}).get("iterations", ""),
                "average_ms": r.get("indexed", {}).get("avg_ms", ""),
                "minimum_ms": r.get("indexed", {}).get("min_ms", ""),
                "maximum_ms": r.get("indexed", {}).get("max_ms", ""),
                "median_ms": r.get("indexed", {}).get("median_ms", ""),
                "result_count": r.get("indexed", {}).get("result_count", ""),
                "speedup": r.get("speedup", "N/A"),
                "query_plan": r.get("indexed_plan", ""),
            })

            # Scan row (if available)
            if r.get("scan"):
                writer.writerow({
                    "timestamp": r.get("timestamp", ""),
                    "query_type": r.get("label", ""),
                    "mode": "Full Scan (No Index)",
                    "dataset_size": r.get("scan", {}).get("result_count", ""),
                    "iterations": r.get("scan", {}).get("iterations", ""),
                    "average_ms": r.get("scan", {}).get("avg_ms", ""),
                    "minimum_ms": r.get("scan", {}).get("min_ms", ""),
                    "maximum_ms": r.get("scan", {}).get("max_ms", ""),
                    "median_ms": r.get("scan", {}).get("median_ms", ""),
                    "result_count": r.get("scan", {}).get("result_count", ""),
                    "speedup": r.get("speedup", "N/A"),
                    "query_plan": r.get("scan_plan", ""),
                })

    return os.path.abspath(csv_path)


# ---------------------------------------------------------------------------
# Speedup calculation (standalone helper for tests / UI)
# ---------------------------------------------------------------------------

def calculate_speedup(scan_avg_ms: float, indexed_avg_ms: float) -> Optional[float]:
    """
    Calculates speedup = scan_avg / indexed_avg.
    Returns None if either value is non-positive (undefined / division-by-zero guard).
    Result is honest – if indexed is slower, speedup < 1.0 is returned as-is.
    """
    if indexed_avg_ms <= 0 or scan_avg_ms <= 0:
        return None
    return round(scan_avg_ms / indexed_avg_ms, 3)


# ---------------------------------------------------------------------------
# Legacy compatibility shim (for existing code that imports SearchBenchmark)
# ---------------------------------------------------------------------------

class SearchBenchmark:
    """
    Thin wrapper kept for backward-compatibility with existing imports.
    New code should use BenchmarkEngine directly.
    """

    def __init__(self, db=None):
        from database.db import get_db
        self.db = db or get_db()

    def explain_query_plan(self, query: str, params: Tuple[Any, ...] = ()) -> str:
        explain_sql = f"EXPLAIN QUERY PLAN {query}"
        rows = self.db.fetch_all(explain_sql, params)
        lines = []
        for r in rows:
            detail = r["detail"] if "detail" in r.keys() else str(dict(r))
            lines.append(detail)
        return " | ".join(lines)

    def benchmark_query(self, query: str, params: Tuple[Any, ...] = (),
                        iterations: int = 50) -> Dict[str, Any]:
        timings = []
        results_count = 0
        for _ in range(iterations):
            start = time.perf_counter()
            rows = self.db.fetch_all(query, params)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            timings.append(elapsed_ms)
            results_count = len(rows)

        avg_time = sum(timings) / len(timings)
        plan = self.explain_query_plan(query, params)
        return {
            "query": query,
            "params": str(params),
            "iterations": iterations,
            "results_count": results_count,
            "avg_time_ms": round(avg_time, 4),
            "min_time_ms": round(min(timings), 4),
            "max_time_ms": round(max(timings), 4),
            "query_plan": plan,
            "uses_index": "USING INDEX" in plan or "USING COVERING INDEX" in plan,
        }

    def run_q13_benchmark_suite(self) -> List[Dict[str, Any]]:
        suite = [
            (
                "Exact Code Lookup (Indexed)",
                "SELECT medicine_id, medicine_name, price FROM medicines WHERE medicine_code = ?",
                ("MED1001",),
            ),
            (
                "Category Filtering (Indexed)",
                "SELECT medicine_id, medicine_name, price, quantity FROM medicines WHERE category = ?",
                ("Antibiotic",),
            ),
            (
                "Expiry Date Range & Sorting (Indexed)",
                "SELECT medicine_id, medicine_name, expiry_date FROM medicines "
                "WHERE expiry_date >= ? ORDER BY expiry_date ASC",
                ("2026-01-01",),
            ),
            (
                "Prefix Text Search (Indexed Candidate)",
                "SELECT medicine_id, medicine_name FROM medicines "
                "WHERE medicine_name LIKE ? ORDER BY medicine_name ASC",
                ("Para%",),
            ),
            (
                "Infix Substring Partial Search (Table Scan)",
                "SELECT medicine_id, medicine_name FROM medicines WHERE medicine_name LIKE ?",
                ("%cillin%",),
            ),
        ]
        results = []
        for name, query, params in suite:
            res = self.benchmark_query(query, params, iterations=30)
            res["test_name"] = name
            results.append(res)
        return results
