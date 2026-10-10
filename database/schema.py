"""
Database Schema Definition and Initializer.
Defines DDL for users, medicines, sales, and sale_items tables along with
B-Tree indexes for Q13 search optimization and initial seed data.
"""
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional
from .db import Database, get_db

SCHEMA_SQL = """
-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('Admin', 'Pharmacist'))
);

-- 2. Medicines Table
CREATE TABLE IF NOT EXISTS medicines (
    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_code TEXT UNIQUE NOT NULL,
    medicine_name TEXT NOT NULL,
    category TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    batch_no TEXT NOT NULL,
    price REAL NOT NULL CHECK(price >= 0),
    quantity INTEGER NOT NULL CHECK(quantity >= 0),
    expiry_date TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 3. Sales Table
CREATE TABLE IF NOT EXISTS sales (
    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT UNIQUE,
    patient_name TEXT,
    patient_phone TEXT,
    patient_age INTEGER,
    sale_date TEXT NOT NULL,
    total_amount REAL NOT NULL CHECK(total_amount >= 0),
    user_id INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL
);

-- 4. Sale Items Table
CREATE TABLE IF NOT EXISTS sale_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_id INTEGER NOT NULL,
    medicine_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    price REAL NOT NULL CHECK(price >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0),
    FOREIGN KEY(sale_id) REFERENCES sales(sale_id) ON DELETE CASCADE,
    FOREIGN KEY(medicine_id) REFERENCES medicines(medicine_id) ON DELETE RESTRICT
);

-- Q13 INDEXES FOR FASTER SEARCH & RETRIEVAL
-- Note on B-Tree Indexes:
-- 1. Accelerates exact lookups (e.g. medicine_code = 'MED1001')
-- 2. Accelerates category & manufacturer filtering (e.g. category = 'Antibiotic')
-- 3. Accelerates range queries & sorting on expiry date (e.g. expiry_date <= '2026-10-01')
-- 4. Accelerates prefix searches (e.g. medicine_name LIKE 'Para%')
-- 5. Note: Arbitrary infix partial searches like '%para%' perform full scan, but indexing speeds up overall table scans by reducing memory page fetch overhead for composite sorting.

CREATE INDEX IF NOT EXISTS idx_medicines_name ON medicines(medicine_name);
CREATE INDEX IF NOT EXISTS idx_medicines_category ON medicines(category);
CREATE INDEX IF NOT EXISTS idx_medicines_manufacturer ON medicines(manufacturer);
CREATE INDEX IF NOT EXISTS idx_medicines_expiry ON medicines(expiry_date);
CREATE INDEX IF NOT EXISTS idx_medicines_code ON medicines(medicine_code);
"""


def hash_password(password: str, salt: str = "tqm_pharmacy_salt_2026") -> str:
    """Computes SHA-256 PBKDF2 hash for user password storage."""
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return key.hex()


def seed_initial_data(db: Database) -> None:
    """Populates initial demo accounts and realistic sample medicines if empty."""
    # Seed Users
    user_count = db.fetch_one("SELECT COUNT(*) as cnt FROM users")
    if user_count and user_count['cnt'] == 0:
        admin_hash = hash_password("admin123")
        pharma_hash = hash_password("pharma123")
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", admin_hash, "Admin")
        )
        db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("pharmacist", pharma_hash, "Pharmacist")
        )

    # Seed Medicines
    med_count = db.fetch_one("SELECT COUNT(*) as cnt FROM medicines")
    if med_count and med_count['cnt'] == 0:
        today = datetime.now()
        
        # Datetime calculations for realistic test scenarios
        valid_date_1 = (today + timedelta(days=365)).strftime("%Y-%m-%d")
        valid_date_2 = (today + timedelta(days=180)).strftime("%Y-%m-%d")
        expiring_soon_date = (today + timedelta(days=15)).strftime("%Y-%m-%d")
        expired_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")

        sample_medicines = [
            # Normal Stock
            ("MED1001", "Paracetamol 500mg", "Analgesic", "Cipla Ltd", "B202601", 15.50, 150, valid_date_1),
            ("MED1002", "Paracetamol 650mg", "Analgesic", "Cipla Ltd", "B202602", 22.00, 120, valid_date_1),
            ("MED1003", "Amoxicillin 500mg", "Antibiotic", "Sun Pharma", "B202603", 85.00, 80, valid_date_1),
            ("MED1004", "Amoxicillin 250mg", "Antibiotic", "Sun Pharma", "B202604", 45.00, 60, valid_date_2),
            ("MED1005", "Cetirizine 10mg", "Antihistamine", "Dr. Reddy's", "B202605", 12.00, 200, valid_date_1),
            ("MED1006", "Metformin 500mg", "Antidiabetic", "Lupin Pharma", "B202606", 35.00, 90, valid_date_2),
            ("MED1007", "Pantoprazole 40mg", "Gastroenterology", "Zydus Cadila", "B202607", 55.00, 110, valid_date_1),

            # Low Stock (<= 10)
            ("MED1008", "Azithromycin 500mg", "Antibiotic", "Sun Pharma", "B202608", 120.00, 5, valid_date_1),
            ("MED1009", "Ibuprofen 400mg", "Analgesic", "Cipla Ltd", "B202609", 25.00, 8, valid_date_2),
            ("MED1010", "ORS Sachet 21.8g", "Rehydration", "FDC Ltd", "B202610", 18.00, 3, valid_date_1),

            # Out of Stock (0)
            ("MED1011", "Dextromethorphan Syrup", "Cough & Cold", "Dabur India", "B202611", 65.00, 0, valid_date_1),
            ("MED1012", "Vitamin C 500mg", "Supplements", "Abbott Healthcare", "B202612", 40.00, 0, valid_date_2),

            # Expiring Soon (within 30 days)
            ("MED1013", "Insulin Glargine 100IU", "Diabetes", "Biocon", "B202599", 450.00, 25, expiring_soon_date),
            ("MED1014", "Cough Syrup Batch B", "Cough & Cold", "Dabur India", "B202598", 70.00, 15, expiring_soon_date),

            # Expired Medicine
            ("MED1015", "Aspirin 75mg", "Cardiovascular", "Bayer India", "B202410", 10.00, 40, expired_date),
            ("MED1016", "Tetracycline 250mg", "Antibiotic", "Pfizer India", "B202411", 50.00, 20, expired_date)
        ]

        query = """
        INSERT INTO medicines (medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        for med in sample_medicines:
            db.execute(query, med)


def init_db(db_path: Optional[str] = None) -> Database:
    """Initializes the database schema, indexes, and seeds initial data (including FMEA and SQC)."""
    db = get_db(db_path)
    db.execute_script(SCHEMA_SQL)
    
    # Safe migration for new billing fields
    try:
        columns = [col['name'] for col in db.fetch_all("PRAGMA table_info(sales)")]
        if "invoice_number" not in columns:
            db.execute("ALTER TABLE sales ADD COLUMN invoice_number TEXT")
            # Backfill legacy records
            legacy_sales = db.fetch_all("SELECT sale_id FROM sales WHERE invoice_number IS NULL")
            for row in legacy_sales:
                legacy_inv = f"INV-LEGACY-{row['sale_id']:06d}"
                db.execute("UPDATE sales SET invoice_number = ? WHERE sale_id = ?", (legacy_inv, row['sale_id']))
                
        if "patient_name" not in columns:
            db.execute("ALTER TABLE sales ADD COLUMN patient_name TEXT")
            db.execute("UPDATE sales SET patient_name = 'Walk-in Patient' WHERE patient_name IS NULL")
            
        if "patient_phone" not in columns:
            db.execute("ALTER TABLE sales ADD COLUMN patient_phone TEXT")
            
        if "patient_age" not in columns:
            db.execute("ALTER TABLE sales ADD COLUMN patient_age INTEGER")
            
        # Create indexes after columns are guaranteed to exist
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_invoice ON sales(invoice_number)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sales_patient ON sales(patient_name)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Database migration failed: {e}")

    seed_initial_data(db)
    # Stage 8: Initialize FMEA table and seed records (import here to avoid circular import)
    from utils.fmea import init_fmea_db
    init_fmea_db(db)
    # Stage 9: Initialize SQC / PDCA tables and seed records
    from utils.sqc import init_sqc_db
    init_sqc_db(db)
    return db

