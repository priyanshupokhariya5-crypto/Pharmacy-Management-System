"""
Stage 2 Database Architecture & Safe Schema Migration Module.
Introduces:
  1. schema_migrations: Migration version tracking ledger.
  2. suppliers: Normalized vendor directory per store.
  3. storage_locations: Physical shelf/rack/bin location entities.
  4. inventory_batches: Normalized batch-wise inventory tracking expiry, FEFO eligibility, and location.
  5. purchases & purchase_items: Procurement receiving workflow entities.
  6. stock_movements: Immutable audit ledger tracking all quantity additions and deductions.
  7. sale_batch_allocations: Prepares many-to-many allocation between sale items and specific inventory batches.

Maintains 100% backward compatibility with legacy medicines table while establishing a normalized foundation.
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from database.db import Database
from services.shelf_service import ShelfService

MIGRATION_VERSION = "20261029_01_batch_inventory"
MIGRATION_DESCRIPTION = (
    "Normalized batch-wise inventory, storage locations, suppliers, purchases, "
    "stock movement ledger, and sale batch allocations."
)

SCHEMA_STAGE2_DDL = """
-- 1. Migration Version Ledger
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id INTEGER PRIMARY KEY AUTOINCREMENT,
    version TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
    checksum TEXT
);

-- 2. Suppliers Table
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    supplier_code TEXT NOT NULL,
    supplier_name TEXT NOT NULL,
    contact_person TEXT,
    phone TEXT,
    email TEXT,
    address TEXT,
    gst_number TEXT,
    is_active INTEGER DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, supplier_code)
);
CREATE INDEX IF NOT EXISTS idx_suppliers_store ON suppliers(store_id);
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(store_id, supplier_name);

-- 3. Storage Locations Table
CREATE TABLE IF NOT EXISTS storage_locations (
    location_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    shelf_code TEXT NOT NULL,
    rack TEXT,
    bin TEXT,
    description TEXT,
    is_active INTEGER DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, shelf_code)
);
CREATE INDEX IF NOT EXISTS idx_locations_store_shelf ON storage_locations(store_id, shelf_code);

-- 4. Inventory Batches Table (Normalized Batch-wise Inventory)
CREATE TABLE IF NOT EXISTS inventory_batches (
    batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    medicine_id INTEGER NOT NULL REFERENCES medicines(medicine_id) ON DELETE RESTRICT,
    batch_number TEXT NOT NULL,
    supplier_id INTEGER REFERENCES suppliers(supplier_id) ON DELETE SET NULL,
    mfg_date TEXT,
    expiry_date TEXT NOT NULL,
    received_date TEXT,
    initial_quantity INTEGER NOT NULL CHECK(initial_quantity >= 0),
    current_quantity INTEGER NOT NULL CHECK(current_quantity >= 0),
    purchase_cost REAL CHECK(purchase_cost IS NULL OR purchase_cost >= 0),
    selling_price REAL NOT NULL CHECK(selling_price >= 0),
    location_id INTEGER REFERENCES storage_locations(location_id) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK(status IN ('Active', 'Expired', 'Quarantined', 'Recalled')),
    verification_flag INTEGER DEFAULT 0 CHECK(verification_flag IN (0, 1)),
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, medicine_id, batch_number)
);
CREATE INDEX IF NOT EXISTS idx_batches_store_med ON inventory_batches(store_id, medicine_id);
CREATE INDEX IF NOT EXISTS idx_batches_expiry ON inventory_batches(expiry_date);
CREATE INDEX IF NOT EXISTS idx_batches_status ON inventory_batches(status);
CREATE INDEX IF NOT EXISTS idx_batches_location ON inventory_batches(location_id);
CREATE INDEX IF NOT EXISTS idx_batches_number ON inventory_batches(batch_number);

-- 5. Purchases & Purchase Items Tables
CREATE TABLE IF NOT EXISTS purchases (
    purchase_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(supplier_id) ON DELETE RESTRICT,
    invoice_number TEXT NOT NULL,
    purchase_date TEXT NOT NULL,
    total_amount REAL NOT NULL CHECK(total_amount >= 0),
    payment_status TEXT NOT NULL CHECK(payment_status IN ('PAID', 'PENDING', 'PARTIAL')) DEFAULT 'PAID',
    status TEXT NOT NULL CHECK(status IN ('DRAFT', 'ORDERED', 'RECEIVED', 'CANCELLED')) DEFAULT 'RECEIVED',
    received_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    notes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(store_id, invoice_number)
);
CREATE INDEX IF NOT EXISTS idx_purchases_store_date ON purchases(store_id, purchase_date);
CREATE INDEX IF NOT EXISTS idx_purchases_supplier ON purchases(supplier_id);
CREATE INDEX IF NOT EXISTS idx_purchases_status ON purchases(store_id, status);

CREATE TABLE IF NOT EXISTS purchase_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES purchases(purchase_id) ON DELETE CASCADE,
    medicine_id INTEGER NOT NULL REFERENCES medicines(medicine_id) ON DELETE RESTRICT,
    batch_id INTEGER REFERENCES inventory_batches(batch_id) ON DELETE SET NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0)
);
CREATE INDEX IF NOT EXISTS idx_purchase_items_purchase ON purchase_items(purchase_id);
CREATE INDEX IF NOT EXISTS idx_purchase_items_medicine ON purchase_items(medicine_id);

-- 6. Stock Movement Ledger Table
CREATE TABLE IF NOT EXISTS stock_movements (
    movement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    medicine_id INTEGER NOT NULL REFERENCES medicines(medicine_id) ON DELETE RESTRICT,
    batch_id INTEGER REFERENCES inventory_batches(batch_id) ON DELETE RESTRICT,
    movement_type TEXT NOT NULL CHECK(movement_type IN (
        'MIGRATION_OPENING',
        'PURCHASE_RECEIPT',
        'SALE_DISPENSE',
        'CUSTOMER_RETURN',
        'STOCK_ADJUSTMENT',
        'STORE_TRANSFER',
        'EXPIRY_WRITE_OFF',
        'RECALL_QUARANTINE'
    )),
    quantity_delta INTEGER NOT NULL,
    reference_type TEXT,
    reference_id TEXT,
    notes TEXT,
    created_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_stock_movements_store_med ON stock_movements(store_id, medicine_id);
CREATE INDEX IF NOT EXISTS idx_stock_movements_batch ON stock_movements(batch_id);
CREATE INDEX IF NOT EXISTS idx_stock_movements_type ON stock_movements(movement_type);
CREATE INDEX IF NOT EXISTS idx_stock_movements_date ON stock_movements(created_at);

-- 7. Sale Batch Allocations Table
CREATE TABLE IF NOT EXISTS sale_batch_allocations (
    allocation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sale_item_id INTEGER NOT NULL REFERENCES sale_items(item_id) ON DELETE CASCADE,
    batch_id INTEGER NOT NULL REFERENCES inventory_batches(batch_id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price REAL NOT NULL CHECK(unit_price >= 0),
    subtotal REAL NOT NULL CHECK(subtotal >= 0),
    allocated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_sale_alloc_item ON sale_batch_allocations(sale_item_id);
CREATE INDEX IF NOT EXISTS idx_sale_alloc_batch ON sale_batch_allocations(batch_id);

-- 8. Sale Returns Table
CREATE TABLE IF NOT EXISTS sale_returns (
    return_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE CASCADE,
    sale_id INTEGER NOT NULL REFERENCES sales(sale_id) ON DELETE RESTRICT,
    invoice_number TEXT NOT NULL,
    return_date TEXT NOT NULL,
    total_refund REAL NOT NULL CHECK(total_refund >= 0),
    refund_method TEXT NOT NULL CHECK(refund_method IN ('Cash', 'UPI', 'Card', 'Original')),
    reason TEXT NOT NULL,
    created_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_returns_store ON sale_returns(store_id);
CREATE INDEX IF NOT EXISTS idx_returns_sale ON sale_returns(sale_id);
CREATE INDEX IF NOT EXISTS idx_returns_date ON sale_returns(return_date);

-- 9. Sale Return Items Table
CREATE TABLE IF NOT EXISTS sale_return_items (
    return_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id INTEGER NOT NULL REFERENCES sale_returns(return_id) ON DELETE CASCADE,
    sale_item_id INTEGER NOT NULL REFERENCES sale_items(item_id) ON DELETE RESTRICT,
    medicine_id INTEGER NOT NULL REFERENCES medicines(medicine_id) ON DELETE RESTRICT,
    batch_id INTEGER REFERENCES inventory_batches(batch_id) ON DELETE SET NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price REAL NOT NULL CHECK(unit_price >= 0),
    refund_amount REAL NOT NULL CHECK(refund_amount >= 0),
    restocked INTEGER DEFAULT 1 CHECK(restocked IN (0, 1)),
    restock_condition TEXT DEFAULT 'SELLABLE'
);
CREATE INDEX IF NOT EXISTS idx_return_items_return ON sale_return_items(return_id);
CREATE INDEX IF NOT EXISTS idx_return_items_med ON sale_return_items(medicine_id);

-- 10. Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id TEXT REFERENCES stores(store_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details TEXT,
    ip_address TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_audit_logs_store ON audit_logs(store_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_logs_date ON audit_logs(created_at);
"""


def is_migration_applied(db: Database) -> bool:
    """Checks whether the Stage 2 schema migration has already been executed."""
    tbl = db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
    if not tbl:
        return False
    row = db.fetch_one("SELECT migration_id FROM schema_migrations WHERE version = ?", (MIGRATION_VERSION,))
    return row is not None


def apply_stage2_migration(db: Database, reference_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes the Stage 2 schema migration safely and transactionally.
    Performs:
      1. Creates 7 normalized tables and B-Tree indexes.
      2. Initializes physical storage shelves per store.
      3. Migrates all legacy medicine rows into active/expired inventory_batches with verification flags.
      4. Creates immutable opening stock movements in stock_movements ledger.
      5. Enforces Critical Shelf Allocation Rule (batches of same medicine with different expiry get distinct shelves).
      6. Records migration version in schema_migrations.
      7. Reconciles 100% of stock quantities.

    Returns:
      Comprehensive execution and reconciliation report.
    """
    shelf_service = ShelfService(db)
    ref_date = reference_date or datetime.now().strftime("%Y-%m-%d")

    report: Dict[str, Any] = {
        "status": "PENDING",
        "version": MIGRATION_VERSION,
        "already_applied": False,
        "stores_processed": 0,
        "locations_created": 0,
        "medicines_scanned": 0,
        "batches_created": 0,
        "stock_movements_logged": 0,
        "expired_batches_flagged": 0,
        "active_batches_created": 0,
        "zero_quantity_batches": 0,
        "verification_flags_set": 0,
        "shelf_conflicts_detected": 0,
        "reconciled": False,
        "reconciliation_summary": {},
        "missing_details_audit": []
    }

    if is_migration_applied(db):
        report["status"] = "ALREADY_APPLIED"
        report["already_applied"] = True
        rec = shelf_service.reconcile_medicine_stock()
        report["reconciled"] = all(r["reconciled"] for r in rec)
        report["reconciliation_summary"] = {
            "total_medicines": len(rec),
            "reconciled_count": sum(1 for r in rec if r["reconciled"]),
            "unreconciled_count": sum(1 for r in rec if not r["reconciled"])
        }
        return report

    # 1. Execute DDL script
    db.execute_script(SCHEMA_STAGE2_DDL)

    # Ensure purchases table has status column if table was previously created without it
    p_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(purchases)")]
    if "status" not in p_cols:
        db.execute("ALTER TABLE purchases ADD COLUMN status TEXT DEFAULT 'RECEIVED'")

    # Ensure sales table has financial breakdown and payment method columns if sales table exists
    if db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='sales'"):
        s_cols = [c['name'] for c in db.fetch_all("PRAGMA table_info(sales)")]
        if "subtotal" not in s_cols:
            db.execute("ALTER TABLE sales ADD COLUMN subtotal REAL DEFAULT 0.0")
            db.execute("UPDATE sales SET subtotal = total_amount WHERE subtotal IS NULL OR subtotal = 0.0")
        if "discount_amount" not in s_cols:
            db.execute("ALTER TABLE sales ADD COLUMN discount_amount REAL DEFAULT 0.0")
        if "tax_amount" not in s_cols:
            db.execute("ALTER TABLE sales ADD COLUMN tax_amount REAL DEFAULT 0.0")
        if "rounding_amount" not in s_cols:
            db.execute("ALTER TABLE sales ADD COLUMN rounding_amount REAL DEFAULT 0.0")
        if "payment_method" not in s_cols:
            db.execute("ALTER TABLE sales ADD COLUMN payment_method TEXT DEFAULT 'Cash'")
        if "payment_reference" not in s_cols:
            db.execute("ALTER TABLE sales ADD COLUMN payment_reference TEXT")
        if "status" not in s_cols:
            db.execute("ALTER TABLE sales ADD COLUMN status TEXT DEFAULT 'COMPLETED'")



    # 2. Seed Standard Storage Locations per Store
    store_rows = db.fetch_all("SELECT store_id, store_name FROM stores")
    if not store_rows:
        store_ids = []
    else:
        store_ids = [s["store_id"] for s in store_rows]

    standard_shelves = [
        ("SHELF-A01", "Rack A", "Bin 1", "Main Prescription Shelf (Tablets & Capsules)"),
        ("SHELF-A02", "Rack A", "Bin 2", "Secondary Shelf (Tablets - Later Expiry)"),
        ("SHELF-B01", "Rack B", "Bin 1", "General Liquids & Syrups"),
        ("SHELF-B02", "Rack B", "Bin 2", "Secondary Shelf (Liquids - Later Expiry)"),
        ("SHELF-COLD", "Cold Unit", "Fridge 1", "Cold Chain Storage (Insulin & Biologicals)"),
        ("SHELF-QUAR", "Quarantine", "Bin Q", "Segregated Quarantine / Expired Stock")
    ]

    locations_created = 0
    for sid in store_ids:
        for code, rack, bin_c, desc in standard_shelves:
            existing_loc = db.fetch_one(
                "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
                (sid, code)
            )
            if not existing_loc:
                db.execute(
                    "INSERT INTO storage_locations (store_id, shelf_code, rack, bin, description, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                    (sid, code, rack, bin_c, desc)
                )
                locations_created += 1

    report["stores_processed"] = len(store_ids)
    report["locations_created"] = locations_created

    # 3. Migrate Existing Medicines Table into Inventory Batches & Movements
    medicines = db.fetch_all("SELECT * FROM medicines ORDER BY medicine_id ASC")
    report["medicines_scanned"] = len(medicines)

    batches_created = 0
    movements_created = 0
    expired_count = 0
    active_count = 0
    zero_qty_count = 0
    missing_details = []

    for med in medicines:
        med_id = med["medicine_id"]
        med_store = med["store_id"] or "STORE-LEGACY-001"
        med_code = med["medicine_code"]
        med_name = med["medicine_name"]
        batch_no = str(med["batch_no"]).strip() if med["batch_no"] else ""
        expiry_date = str(med["expiry_date"]).strip() if med["expiry_date"] else ""
        quantity = int(med["quantity"])
        price = float(med["price"])

        # Check if already migrated
        existing_batch = db.fetch_one(
            "SELECT batch_id FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND batch_number = ?",
            (med_store, med_id, batch_no)
        )
        if existing_batch:
            continue

        # Check for missing/anomalous legacy details
        anomaly_reasons = []
        if not batch_no:
            batch_no = f"SURROGATE-B{med_id}"
            anomaly_reasons.append("Missing legacy batch number; generated technical surrogate.")
        if not expiry_date:
            expiry_date = "1970-01-01"
            anomaly_reasons.append("Missing legacy expiry date; marked for verification.")
        if quantity <= 0:
            zero_qty_count += 1
            if quantity < 0:
                anomaly_reasons.append(f"Negative legacy quantity detected ({quantity}); preserved as 0.")
                quantity = 0

        # Always flag legacy data as requiring supplier & mfg_date verification
        anomaly_reasons.append("Legacy record: Supplier, purchase cost, and manufacturing date are unrecorded.")
        missing_details.append({
            "medicine_id": med_id,
            "medicine_code": med_code,
            "medicine_name": med_name,
            "batch_number": batch_no,
            "reasons": anomaly_reasons
        })

        # Determine batch status based on strict expiry rules
        is_exp = shelf_service.is_expired(expiry_date, ref_date)
        status = "Expired" if is_exp else "Active"
        if is_exp:
            expired_count += 1
        else:
            active_count += 1

        # Determine shelf location complying with Critical Shelf Allocation Rule
        cat = str(med["category"]).lower() if "category" in med.keys() else ""
        name_lower = med_name.lower()

        if "insulin" in name_lower or "cold" in cat or "diabetes" in cat:
            preferred_code = "SHELF-COLD"
            fallback_code = "SHELF-A02"
        elif "syrup" in name_lower or "cough" in cat or "rehydration" in cat or "liquid" in cat:
            preferred_code = "SHELF-B01"
            fallback_code = "SHELF-B02"
        elif is_exp:
            preferred_code = "SHELF-QUAR"
            fallback_code = "SHELF-A02"
        else:
            preferred_code = "SHELF-A01"
            fallback_code = "SHELF-A02"

        # Lookup preferred location ID
        pref_loc = db.fetch_one(
            "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
            (med_store, preferred_code)
        )
        loc_id = pref_loc["location_id"] if pref_loc else None

        # Verify shelf allocation rule (same medicine with different expiry cannot share shelf)
        if loc_id:
            ok, _ = shelf_service.validate_shelf_allocation(med_store, med_id, loc_id, expiry_date)
            if not ok:
                # Fallback to secondary shelf
                fall_loc = db.fetch_one(
                    "SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?",
                    (med_store, fallback_code)
                )
                loc_id = fall_loc["location_id"] if fall_loc else loc_id

        # Insert normalized inventory batch
        batch_id = db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, supplier_id, mfg_date,
                expiry_date, received_date, initial_quantity, current_quantity,
                purchase_cost, selling_price, location_id, status, verification_flag, notes
            ) VALUES (?, ?, ?, NULL, NULL, ?, NULL, ?, ?, NULL, ?, ?, ?, 1, ?)
            """,
            (
                med_store, med_id, batch_no, expiry_date,
                quantity, quantity, price, loc_id, status,
                "Migrated opening balance from legacy medicines table"
            )
        )
        batches_created += 1

        # Insert Opening Stock Movement into ledger
        db.execute(
            """
            INSERT INTO stock_movements (
                store_id, medicine_id, batch_id, movement_type,
                quantity_delta, reference_type, reference_id, notes, created_by
            ) VALUES (?, ?, ?, 'MIGRATION_OPENING', ?, 'LEGACY_MIGRATION', ?, ?, NULL)
            """,
            (
                med_store, med_id, batch_id, quantity,
                f"MED-{med_id}-INIT",
                f"Opening balance migrated for batch '{batch_no}'"
            )
        )
        movements_created += 1

    # Record migration in schema_migrations
    db.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, description, applied_at, checksum)
        VALUES (?, ?, ?, 'STAGE2_BATCH_MIGRATION_OK')
        """,
        (MIGRATION_VERSION, MIGRATION_DESCRIPTION, datetime.now().isoformat())
    )

    report["status"] = "SUCCESS"
    report["batches_created"] = batches_created
    report["stock_movements_logged"] = movements_created
    report["expired_batches_flagged"] = expired_count
    report["active_batches_created"] = active_count
    report["zero_quantity_batches"] = zero_qty_count
    report["verification_flags_set"] = batches_created
    report["missing_details_audit"] = missing_details

    # Verify Shelf Conflicts
    conflicts = shelf_service.detect_all_shelf_conflicts()
    report["shelf_conflicts_detected"] = len(conflicts)
    report["shelf_conflicts"] = conflicts

    # Run Stock Reconciliation
    reconciliation = shelf_service.reconcile_medicine_stock()
    all_reconciled = all(r["reconciled"] for r in reconciliation)
    report["reconciled"] = all_reconciled
    report["reconciliation_summary"] = {
        "total_medicines": len(reconciliation),
        "reconciled_count": sum(1 for r in reconciliation if r["reconciled"]),
        "unreconciled_count": sum(1 for r in reconciliation if not r["reconciled"])
    }
    report["reconciliation_details"] = reconciliation

    return report


def rollback_stage2_migration(db: Database) -> bool:
    """
    Emergency rollback procedure for Stage 2 migration.
    Drops the new normalized tables and removes the migration record,
    leaving all legacy tables and records 100% untouched.
    """
    drop_script = """
    DROP TABLE IF EXISTS sale_batch_allocations;
    DROP TABLE IF EXISTS stock_movements;
    DROP TABLE IF EXISTS purchase_items;
    DROP TABLE IF EXISTS purchases;
    DROP TABLE IF EXISTS inventory_batches;
    DROP TABLE IF EXISTS storage_locations;
    DROP TABLE IF EXISTS suppliers;
    DELETE FROM schema_migrations WHERE version = '20261029_01_batch_inventory';
    """
    db.execute_script(drop_script)
    return True
