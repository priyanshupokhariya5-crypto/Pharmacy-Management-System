"""
Isolated Benchmark Database Manager for Stage 7 Q13 Performance Testing.
Populates a dedicated SQLite database (data/benchmark.db) with 5,000 synthetic medicine records
and provides twin tables (indexed vs non-indexed) for safe, empirical query performance comparison.
NEVER alters production pharmacy.db.
"""
import os
import random
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

DEFAULT_BENCHMARK_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "benchmark.db"
)

CATEGORIES = [
    "Analgesic", "Antibiotic", "Antihistamine", "Antidiabetic",
    "Gastroenterology", "Cardiovascular", "Rehydration", "Cough & Cold",
    "Supplements", "Dermatology", "Neurology", "Ophthalmology"
]

MANUFACTURERS = [
    "Cipla Ltd", "Sun Pharma", "Dr. Reddy's", "Lupin Pharma",
    "Zydus Cadila", "FDC Ltd", "Dabur India", "Abbott Healthcare",
    "Biocon", "Bayer India", "Pfizer India", "Torrent Pharma"
]

MEDICINE_PREFIXES = [
    "Para", "Amox", "Ceti", "Metf", "Panto", "Azith", "Ibup", "Dext",
    "Vita", "Insu", "Aspi", "Tetra", "Clavi", "Omep", "Ator", "Losi",
    "Amlod", "Glim", "Telmi", "Rant", "Mont", "Levoc", "Cipro", "Oflox"
]

MEDICINE_SUFFIXES = [
    "500mg Tablet", "650mg Tablet", "250mg Capsule", "10mg Tablet",
    "40mg Tablet", "20mg Tablet", "Syrup 100ml", "Injection 10ml",
    "Gel 30g", "Drops 15ml", "Sachet 21.8g", "Suspension 60ml"
]


class BenchmarkDatabase:
    """Manager for isolated benchmark.db database file."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_BENCHMARK_DB_PATH
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[sqlite3.Row]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

    def execute_script(self, script: str) -> None:
        with self.get_connection() as conn:
            conn.executescript(script)
            conn.commit()


def init_benchmark_db(db_path: Optional[str] = None, record_count: int = 5000) -> BenchmarkDatabase:
    """Initializes benchmark.db, creates indexed & non-indexed twin tables, and seeds synthetic records."""
    bm_db = BenchmarkDatabase(db_path)

    schema_sql = """
    -- Table 1: Indexed Medicines Table
    CREATE TABLE IF NOT EXISTS medicines_indexed (
        medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_code TEXT UNIQUE NOT NULL,
        medicine_name TEXT NOT NULL,
        category TEXT NOT NULL,
        manufacturer TEXT NOT NULL,
        batch_no TEXT NOT NULL,
        price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        expiry_date TEXT NOT NULL
    );

    -- Table 2: Non-Indexed Medicines Table (Identical data for fair Full Table Scan benchmark)
    CREATE TABLE IF NOT EXISTS medicines_scan (
        medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_code TEXT NOT NULL,
        medicine_name TEXT NOT NULL,
        category TEXT NOT NULL,
        manufacturer TEXT NOT NULL,
        batch_no TEXT NOT NULL,
        price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        expiry_date TEXT NOT NULL
    );

    -- Indexes on medicines_indexed
    CREATE INDEX IF NOT EXISTS idx_bm_code ON medicines_indexed(medicine_code);
    CREATE INDEX IF NOT EXISTS idx_bm_name ON medicines_indexed(medicine_name);
    CREATE INDEX IF NOT EXISTS idx_bm_category ON medicines_indexed(category);
    CREATE INDEX IF NOT EXISTS idx_bm_mfr ON medicines_indexed(manufacturer);
    CREATE INDEX IF NOT EXISTS idx_bm_expiry ON medicines_indexed(expiry_date);
    """
    bm_db.execute_script(schema_sql)

    # Check if dataset is already seeded
    count_row = bm_db.fetch_one("SELECT COUNT(*) as cnt FROM medicines_indexed")
    if count_row and count_row["cnt"] >= record_count:
        return bm_db

    # Seed synthetic benchmark dataset deterministically
    random.seed(2026)
    today = datetime.now()

    records = []
    for i in range(1, record_count + 1):
        code = f"BM{i:06d}"
        prefix = random.choice(MEDICINE_PREFIXES)
        suffix = random.choice(MEDICINE_SUFFIXES)
        name = f"{prefix} {suffix}"
        cat = random.choice(CATEGORIES)
        mfr = random.choice(MANUFACTURERS)
        batch = f"BM{random.randint(1000, 9999)}"
        price = round(random.uniform(5.0, 500.0), 2)
        qty = random.randint(0, 500)
        days_offset = random.randint(-180, 500)
        exp_date = (today + timedelta(days=days_offset)).strftime("%Y-%m-%d")

        records.append((code, name, cat, mfr, batch, price, qty, exp_date))

    # Insert into twin tables within an atomic transaction
    conn = bm_db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM medicines_indexed;")
        cursor.execute("DELETE FROM medicines_scan;")

        ins_sql = """
        INSERT INTO medicines_indexed (medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        cursor.executemany(ins_sql, records)

        ins_scan_sql = """
        INSERT INTO medicines_scan (medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
        """
        cursor.executemany(ins_scan_sql, records)

        conn.commit()
    finally:
        conn.close()

    return bm_db
