"""
Database Schema Definition, Migration, and Initializer.
Defines DDL for stores, users, medicines, sales, and sale_items tables along with
B-Tree indexes for Q13 search optimization and multi-store tenant isolation.
"""
import hashlib
import hmac
import os
import sys
import secrets
from datetime import datetime, timedelta
from typing import Optional
from .db import Database, get_db

SCHEMA_SQL = """
-- 0. Stores Table (Multi-Store Pharmacy Management)
CREATE TABLE IF NOT EXISTS stores (
    store_id TEXT PRIMARY KEY,
    store_name TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('Admin', 'Pharmacist', 'Owner')),
    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
    full_name TEXT,
    email TEXT UNIQUE
);

-- 2. Medicines Table
CREATE TABLE IF NOT EXISTS medicines (
    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
    medicine_code TEXT NOT NULL,
    medicine_name TEXT NOT NULL,
    category TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    batch_no TEXT NOT NULL,
    price REAL NOT NULL CHECK(price >= 0),
    quantity INTEGER NOT NULL CHECK(quantity >= 0),
    expiry_date TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, medicine_code)
);

-- 3. Sales Table
CREATE TABLE IF NOT EXISTS sales (
    sale_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
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
    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
    sale_id INTEGER NOT NULL,
    medicine_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    price REAL NOT NULL CHECK(price >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0),
    FOREIGN KEY(sale_id) REFERENCES sales(sale_id) ON DELETE CASCADE,
    FOREIGN KEY(medicine_id) REFERENCES medicines(medicine_id) ON DELETE RESTRICT
);



-- Q13 INDEXES FOR FASTER SEARCH & RETRIEVAL
CREATE INDEX IF NOT EXISTS idx_medicines_name ON medicines(medicine_name);
CREATE INDEX IF NOT EXISTS idx_medicines_category ON medicines(category);
CREATE INDEX IF NOT EXISTS idx_medicines_manufacturer ON medicines(manufacturer);
CREATE INDEX IF NOT EXISTS idx_medicines_expiry ON medicines(expiry_date);
CREATE INDEX IF NOT EXISTS idx_medicines_code ON medicines(medicine_code);
"""


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """
    Computes secure PBKDF2 HMAC SHA-256 hash for user password storage.
    Generates a unique random per-user salt if none is provided and uses 200,000 iterations.
    Format returned: '{salt}${key_hex}'
    """
    if salt is None:
        salt = secrets.token_hex(16)
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            200000
        )
        return f"{salt}${key.hex()}"
    else:
        # Backward compatibility for fixed-salt legacy callers/tests
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return key.hex()


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verifies a plain-text password against a stored PBKDF2 hash using constant-time comparison.
    Supports both modern '{salt}${key}' (200k iterations) and legacy fixed-salt format (100k iterations).
    """
    if not password or not stored_hash:
        return False

    if "$" in stored_hash:
        try:
            salt, hash_val = stored_hash.split("$", 1)
            key = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                200000
            )
            return hmac.compare_digest(key.hex(), hash_val)
        except Exception:
            return False
    else:
        # Legacy fallback verification for pre-existing seed hashes
        legacy_key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            b"tqm_pharmacy_salt_2026",
            100000
        )
        return hmac.compare_digest(legacy_key.hex(), stored_hash)


def migrate_database(db: Database) -> None:
    """
    Executes safe, non-destructive schema migrations:
    - Creates stores table and default legacy store.
    - Adds store_id, email, and full_name to users.
    - Adds store_id to medicines, sales, sale_items, fmea_records, sqc_defects, pdca_items.
    - Backfills legacy records to 'STORE-LEGACY-001' so existing data is preserved.
    - Adds compound indexes for fast store-isolated queries.
    """
    # 1. Create stores table
    db.execute("""
    CREATE TABLE IF NOT EXISTS stores (
        store_id TEXT PRIMARY KEY,
        store_name TEXT NOT NULL,
        owner_name TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 2. Default legacy store record
    db.execute("""
    INSERT OR IGNORE INTO stores (store_id, store_name, owner_name)
    VALUES ('STORE-LEGACY-001', 'Default Pharmacy Store', 'Priyanshu Pokhariya')
    """)

    # Helper to check if a table exists
    def _table_exists(name: str) -> bool:
        row = db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (name,))
        return bool(row)

    # 3. Migrate users table
    if _table_exists("users"):
        user_sql_row = db.fetch_one("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
        user_sql = user_sql_row["sql"] if user_sql_row else ""

        # If existing users table has old CHECK constraint without 'Owner', rebuild table transactionally
        if "Owner" not in user_sql:
            user_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(users)")]
            store_expr = "store_id" if "store_id" in user_cols else "'STORE-LEGACY-001'"
            fname_expr = "full_name" if "full_name" in user_cols else "''"
            email_expr = "email" if "email" in user_cols else "(username || '@pharmacy.local')"

            conn = db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys = OFF;")
                cursor.execute("""
                CREATE TABLE users_new (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('Admin', 'Pharmacist', 'Owner')),
                    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
                    full_name TEXT,
                    email TEXT UNIQUE
                );
                """)
                cursor.execute(f"""
                INSERT INTO users_new (user_id, username, password_hash, role, store_id, full_name, email)
                SELECT user_id, username, password_hash, role,
                       COALESCE({store_expr}, 'STORE-LEGACY-001'),
                       COALESCE({fname_expr}, ''),
                       COALESCE({email_expr}, username || '@pharmacy.local')
                FROM users;
                """)
                cursor.execute("DROP TABLE users;")
                cursor.execute("ALTER TABLE users_new RENAME TO users;")
                cursor.execute("PRAGMA foreign_keys = ON;")
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        else:
            # Table already allows 'Owner', ensure any missing columns exist
            user_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(users)")]
            if "store_id" not in user_cols:
                db.execute("ALTER TABLE users ADD COLUMN store_id TEXT REFERENCES stores(store_id)")
            if "full_name" not in user_cols:
                db.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
            if "email" not in user_cols:
                db.execute("ALTER TABLE users ADD COLUMN email TEXT")

        db.execute("UPDATE users SET store_id = 'STORE-LEGACY-001' WHERE store_id IS NULL OR store_id = ''")
        db.execute("UPDATE users SET email = username || '@pharmacy.local' WHERE email IS NULL OR email = ''")
        db.execute("""
        UPDATE users SET full_name = CASE
            WHEN role = 'Admin' THEN 'Store Administrator'
            WHEN role = 'Pharmacist' THEN 'Staff Pharmacist'
            ELSE 'Store Owner' END
        WHERE full_name IS NULL OR full_name = ''
        """)

        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_users_store ON users(store_id)")

    # 4. Migrate medicines table
    if _table_exists("medicines"):
        # Check if table requires migration to support multi-store composite unique(store_id, medicine_code)
        # 1. Any unique index or constraint strictly on medicine_code alone must be removed.
        # 2. Composite unique constraint UNIQUE(store_id, medicine_code) must be enforced.
        rebuild_medicines = False

        for idx in db.fetch_all("PRAGMA index_list('medicines')"):
            if idx["unique"] == 1:
                cols = [info["name"] for info in db.fetch_all(f"PRAGMA index_info('{idx['name']}')")]
                if cols == ["medicine_code"]:
                    rebuild_medicines = True
                    break

        has_composite_unique = False
        for idx in db.fetch_all("PRAGMA index_list('medicines')"):
            if idx["unique"] == 1:
                cols = [info["name"] for info in db.fetch_all(f"PRAGMA index_info('{idx['name']}')")]
                if set(cols) == {"store_id", "medicine_code"}:
                    has_composite_unique = True
                    break

        if not has_composite_unique:
            rebuild_medicines = True

        if rebuild_medicines:
            med_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(medicines)")]
            store_expr = "store_id" if "store_id" in med_cols else "'STORE-LEGACY-001'"
            created_expr = "created_at" if "created_at" in med_cols else "CURRENT_TIMESTAMP"
            updated_expr = "updated_at" if "updated_at" in med_cols else "CURRENT_TIMESTAMP"

            conn = db.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("PRAGMA foreign_keys = OFF;")
                cursor.execute("""
                CREATE TABLE medicines_new (
                    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    store_id TEXT DEFAULT 'STORE-LEGACY-001' REFERENCES stores(store_id),
                    medicine_code TEXT NOT NULL,
                    medicine_name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    manufacturer TEXT NOT NULL,
                    batch_no TEXT NOT NULL,
                    price REAL NOT NULL CHECK(price >= 0),
                    quantity INTEGER NOT NULL CHECK(quantity >= 0),
                    expiry_date TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(store_id, medicine_code)
                );
                """)
                cursor.execute(f"""
                INSERT INTO medicines_new (
                    medicine_id, store_id, medicine_code, medicine_name, category,
                    manufacturer, batch_no, price, quantity, expiry_date,
                    created_at, updated_at
                )
                SELECT medicine_id,
                       COALESCE({store_expr}, 'STORE-LEGACY-001'),
                       medicine_code,
                       medicine_name,
                       category,
                       manufacturer,
                       batch_no,
                       price,
                       quantity,
                       expiry_date,
                       COALESCE({created_expr}, CURRENT_TIMESTAMP),
                       COALESCE({updated_expr}, CURRENT_TIMESTAMP)
                FROM medicines;
                """)
                cursor.execute("DROP TABLE medicines;")
                cursor.execute("ALTER TABLE medicines_new RENAME TO medicines;")
                cursor.execute("PRAGMA foreign_keys = ON;")
                fk_violations = cursor.execute("PRAGMA foreign_key_check;").fetchall()
                if fk_violations:
                    raise RuntimeError(f"Foreign key violations detected after medicines migration: {fk_violations}")
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally:
                conn.close()
        else:
            med_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(medicines)")]
            if "store_id" not in med_cols:
                db.execute("ALTER TABLE medicines ADD COLUMN store_id TEXT REFERENCES stores(store_id)")

        db.execute("UPDATE medicines SET store_id = 'STORE-LEGACY-001' WHERE store_id IS NULL OR store_id = ''")

        # Standard Q13 and store isolation indexes
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_name ON medicines(medicine_name)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_category ON medicines(category)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_manufacturer ON medicines(manufacturer)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_expiry ON medicines(expiry_date)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_code ON medicines(medicine_code)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_store ON medicines(store_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_store_name ON medicines(store_id, medicine_name)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_store_category ON medicines(store_id, category)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_store_code ON medicines(store_id, medicine_code)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_medicines_store_expiry ON medicines(store_id, expiry_date)")

    # 5. Migrate sales table
    if _table_exists("sales"):
        sales_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(sales)")]
        if "invoice_number" not in sales_cols:
            db.execute("ALTER TABLE sales ADD COLUMN invoice_number TEXT")
            legacy_sales = db.fetch_all("SELECT sale_id FROM sales WHERE invoice_number IS NULL")
            for row in legacy_sales:
                legacy_inv = f"INV-LEGACY-{row['sale_id']:06d}"
                db.execute("UPDATE sales SET invoice_number = ? WHERE sale_id = ?", (legacy_inv, row['sale_id']))

        if "patient_name" not in sales_cols:
            db.execute("ALTER TABLE sales ADD COLUMN patient_name TEXT")
            db.execute("UPDATE sales SET patient_name = 'Walk-in Patient' WHERE patient_name IS NULL")

        if "patient_phone" not in sales_cols:
            db.execute("ALTER TABLE sales ADD COLUMN patient_phone TEXT")

        if "patient_age" not in sales_cols:
            db.execute("ALTER TABLE sales ADD COLUMN patient_age INTEGER")

        if "store_id" not in sales_cols:
            db.execute("ALTER TABLE sales ADD COLUMN store_id TEXT REFERENCES stores(store_id)")
        db.execute("UPDATE sales SET store_id = 'STORE-LEGACY-001' WHERE store_id IS NULL")

        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sales_invoice ON sales(invoice_number)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sales_patient ON sales(patient_name)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sales_date ON sales(sale_date)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sales_store ON sales(store_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sales_store_date ON sales(store_id, sale_date)")

    # 6. Migrate sale_items table
    if _table_exists("sale_items"):
        item_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(sale_items)")]
        if "store_id" not in item_cols:
            db.execute("ALTER TABLE sale_items ADD COLUMN store_id TEXT REFERENCES stores(store_id)")
        db.execute("""
        UPDATE sale_items
        SET store_id = (SELECT s.store_id FROM sales s WHERE s.sale_id = sale_items.sale_id)
        WHERE store_id IS NULL AND EXISTS (SELECT 1 FROM sales s WHERE s.sale_id = sale_items.sale_id)
        """)
        db.execute("UPDATE sale_items SET store_id = 'STORE-LEGACY-001' WHERE store_id IS NULL")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sale_items_store ON sale_items(store_id)")

    # 7. Migrate fmea_records table
    fmea_tables = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name='fmea_records'")
    if fmea_tables:
        fmea_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(fmea_records)")]
        if "store_id" not in fmea_cols:
            db.execute("ALTER TABLE fmea_records ADD COLUMN store_id TEXT REFERENCES stores(store_id)")
        db.execute("UPDATE fmea_records SET store_id = 'STORE-LEGACY-001' WHERE store_id IS NULL")
        db.execute("CREATE INDEX IF NOT EXISTS idx_fmea_store ON fmea_records(store_id)")

    # 8. Migrate sqc_defects & pdca_items tables
    sqc_tables = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name='sqc_defects'")
    if sqc_tables:
        sqc_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(sqc_defects)")]
        if "store_id" not in sqc_cols:
            db.execute("ALTER TABLE sqc_defects ADD COLUMN store_id TEXT REFERENCES stores(store_id)")
        db.execute("UPDATE sqc_defects SET store_id = 'STORE-LEGACY-001' WHERE store_id IS NULL")
        db.execute("CREATE INDEX IF NOT EXISTS idx_sqc_store ON sqc_defects(store_id)")

    pdca_tables = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' AND name='pdca_items'")
    if pdca_tables:
        pdca_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(pdca_items)")]
        if "store_id" not in pdca_cols:
            db.execute("ALTER TABLE pdca_items ADD COLUMN store_id TEXT REFERENCES stores(store_id)")
        db.execute("UPDATE pdca_items SET store_id = 'STORE-LEGACY-001' WHERE store_id IS NULL")
        db.execute("CREATE INDEX IF NOT EXISTS idx_pdca_store ON pdca_items(store_id)")


def seed_initial_data(db: Database) -> None:
    """Populates initial default store and sample medicines for legacy compatibility."""
    # Ensure default store exists
    db.execute("""
    INSERT OR IGNORE INTO stores (store_id, store_name, owner_name)
    VALUES ('STORE-LEGACY-001', 'Default Pharmacy Store', 'Priyanshu Pokhariya')
    """)

    # Seed Users
    user_count = db.fetch_one("SELECT COUNT(*) as cnt FROM users")
    if user_count and user_count['cnt'] == 0:
        admin_hash = hash_password("admin123")
        pharma_hash = hash_password("pharma123")
        db.execute(
            "INSERT INTO users (username, password_hash, role, store_id, full_name, email) VALUES (?, ?, ?, ?, ?, ?)",
            ("admin", admin_hash, "Admin", "STORE-LEGACY-001", "Administrator", "admin@pharmacy.local")
        )
        db.execute(
            "INSERT INTO users (username, password_hash, role, store_id, full_name, email) VALUES (?, ?, ?, ?, ?, ?)",
            ("pharmacist", pharma_hash, "Pharmacist", "STORE-LEGACY-001", "Staff Pharmacist", "pharmacist@pharmacy.local")
        )

    # Seed Medicines for legacy store
    med_count = db.fetch_one("SELECT COUNT(*) as cnt FROM medicines")
    if med_count and med_count['cnt'] == 0:
        today = datetime.now()
        
        valid_date_1 = (today + timedelta(days=365)).strftime("%Y-%m-%d")
        valid_date_2 = (today + timedelta(days=180)).strftime("%Y-%m-%d")
        expiring_soon_date = (today + timedelta(days=15)).strftime("%Y-%m-%d")
        expired_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")

        sample_medicines = [
            ("STORE-LEGACY-001", "MED1001", "Paracetamol 500mg", "Analgesic", "Cipla Ltd", "B202601", 15.50, 150, valid_date_1),
            ("STORE-LEGACY-001", "MED1002", "Paracetamol 650mg", "Analgesic", "Cipla Ltd", "B202602", 22.00, 120, valid_date_1),
            ("STORE-LEGACY-001", "MED1003", "Amoxicillin 500mg", "Antibiotic", "Sun Pharma", "B202603", 85.00, 80, valid_date_1),
            ("STORE-LEGACY-001", "MED1004", "Amoxicillin 250mg", "Antibiotic", "Sun Pharma", "B202604", 45.00, 60, valid_date_2),
            ("STORE-LEGACY-001", "MED1005", "Cetirizine 10mg", "Antihistamine", "Dr. Reddy's", "B202605", 12.00, 200, valid_date_1),
            ("STORE-LEGACY-001", "MED1006", "Metformin 500mg", "Antidiabetic", "Lupin Pharma", "B202606", 35.00, 90, valid_date_2),
            ("STORE-LEGACY-001", "MED1007", "Pantoprazole 40mg", "Gastroenterology", "Zydus Cadila", "B202607", 55.00, 110, valid_date_1),
            ("STORE-LEGACY-001", "MED1008", "Azithromycin 500mg", "Antibiotic", "Sun Pharma", "B202608", 120.00, 5, valid_date_1),
            ("STORE-LEGACY-001", "MED1009", "Ibuprofen 400mg", "Analgesic", "Cipla Ltd", "B202609", 25.00, 8, valid_date_2),
            ("STORE-LEGACY-001", "MED1010", "ORS Sachet 21.8g", "Rehydration", "FDC Ltd", "B202610", 18.00, 3, valid_date_1),
            ("STORE-LEGACY-001", "MED1011", "Dextromethorphan Syrup", "Cough & Cold", "Dabur India", "B202611", 65.00, 0, valid_date_1),
            ("STORE-LEGACY-001", "MED1012", "Vitamin C 500mg", "Supplements", "Abbott Healthcare", "B202612", 40.00, 0, valid_date_2),
            ("STORE-LEGACY-001", "MED1013", "Insulin Glargine 100IU", "Diabetes", "Biocon", "B202599", 450.00, 25, expiring_soon_date),
            ("STORE-LEGACY-001", "MED1014", "Cough Syrup Batch B", "Cough & Cold", "Dabur India", "B202598", 70.00, 15, expiring_soon_date),
            ("STORE-LEGACY-001", "MED1015", "Aspirin 75mg", "Cardiovascular", "Bayer India", "B202410", 10.00, 40, expired_date),
            ("STORE-LEGACY-001", "MED1016", "Tetracycline 250mg", "Antibiotic", "Pfizer India", "B202411", 50.00, 20, expired_date)
        ]

        query = """
        INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        for med in sample_medicines:
            db.execute(query, med)


def init_db(db_path: Optional[str] = None) -> Database:
    """Initializes the database schema, indexes, safe migrations, and seeds initial data."""
    db = get_db(db_path)
    db.execute_script(SCHEMA_SQL)
    
    # Run safe, non-destructive migration
    try:
        migrate_database(db)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Database migration failed: {e}")

    seed_initial_data(db)

    # Initialize FMEA table and seed records
    from utils.fmea import init_fmea_db
    init_fmea_db(db)

    # Initialize SQC / PDCA tables and seed records
    from utils.sqc import init_sqc_db
    init_sqc_db(db)

    # Re-run migration after FMEA/SQC init to ensure their store_id columns are created and backfilled
    try:
        migrate_database(db)
    except Exception:
        pass

    # Safe, non-destructive import of custom stores from source DB if running in a new/clean environment
    try:
        from database.sync import auto_sync_from_source_if_needed
        auto_sync_from_source_if_needed(db)
    except Exception as e:
        sys.stderr.write(f"[SYNC-INFO] auto_sync_from_source skipped: {e}\n")

    return db
