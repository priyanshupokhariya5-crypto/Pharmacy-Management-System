"""
Dedicated Automated Test-Data Seeding and Safe Cleanup Utility.
Provides realistic, normalized test datasets for:
  - Multi-store isolation (Alpha and Beta test stores)
  - 5 Canonical user roles (Owner, Admin, Pharmacist, Cashier, Inventory Manager) + Inactive user
  - Medicines across multiple therapeutic categories, prices, and stock states
  - Batch-wise inventory with storage locations (shelves, racks, cold storage, quarantine)
  - Shelf allocation rules:
      * Batches of same medicine with different expiry dates cannot share a shelf
      * Batches of same medicine with identical expiry dates may share a shelf
      * Different medicines can share shelves where permitted
  - Suppliers, purchase orders, goods receipts, and stock ledger movements
  - Completed POS sales with Cash, UPI, and Card payment methods
  - Mandatory 10-digit Indian customer phone validation (starting with 6-9)
  - FEFO batch deduction, sale batch allocations, and stock movements
  - Partial and full returns (sellable restocked vs damaged/expired quarantined)
  - Expired, quarantined, unverified, and sellable batch states
  - Critical low-stock (<=10) and out-of-stock (0) inventory states
  - Quality engineering records (FMEA clinical risk, SQC defects, PDCA cycles)
  - Repeatable, idempotent seeding and clean removal utility

CRITICAL SAFETY:
  Must NEVER run against the original production database (data/pharmacy.db).
  Guarded by strict runtime assertions.
"""
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from database.db import Database
from database.schema import SCHEMA_SQL, hash_password, migrate_database
from database.migration_stage2 import apply_stage2_migration, is_migration_applied


def assert_isolated_test_database(db: Database) -> None:
    """
    CRITICAL SAFETY GUARD:
    Prevents test seeding from ever running against the production database file.
    """
    path_str = str(getattr(db, "db_path", "") or "").lower().replace("\\", "/")
    # Block if explicitly data/pharmacy.db or production backup
    if (path_str.endswith("data/pharmacy.db") or path_str == "pharmacy.db") and "test" not in path_str:
        raise RuntimeError(
            f"SAFETY VIOLATION: Test seeder must NEVER run against production database '{path_str}'! "
            "Execute only on isolated test databases (e.g. data/test_*.db or :memory:)."
        )


def cleanup_test_data(db: Database, test_tag: str = "TEST") -> int:
    """
    Safely removes only test records created with the specified test_tag.
    Leaves production and pre-existing legacy records completely intact.
    Deletes child records first to respect SQLite foreign keys.
    """
    assert_isolated_test_database(db)

    tag_pattern = f"%{test_tag}%"
    store_pattern = f"STORE-{test_tag}-%"
    user_pattern = f"test_%_{test_tag.lower()}%"
    deleted_count = 0

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = OFF;")

        # Helper to safely delete from table if it exists
        def _delete_where(table: str, condition: str, params: Tuple[Any, ...]) -> int:
            row = cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name = ?", (table,)).fetchone()
            if not row:
                return 0
            cur = cursor.execute(f"DELETE FROM {table} WHERE {condition}", params)
            return cur.rowcount

        # 1. Sale returns and items
        deleted_count += _delete_where("sale_return_items", "return_id IN (SELECT return_id FROM sale_returns WHERE store_id LIKE ?)", (store_pattern,))
        deleted_count += _delete_where("sale_returns", "store_id LIKE ? OR invoice_number LIKE ?", (store_pattern, tag_pattern))

        # 2. Sale batch allocations
        deleted_count += _delete_where("sale_batch_allocations", "batch_id IN (SELECT batch_id FROM inventory_batches WHERE store_id LIKE ?)", (store_pattern,))

        # 3. Sale items & Sales
        deleted_count += _delete_where("sale_items", "store_id LIKE ?", (store_pattern,))
        deleted_count += _delete_where("sales", "store_id LIKE ? OR invoice_number LIKE ?", (store_pattern, tag_pattern))

        # 4. Stock movements
        deleted_count += _delete_where("stock_movements", "store_id LIKE ? OR reference_id LIKE ?", (store_pattern, tag_pattern))

        # 5. Purchase items & Purchases
        deleted_count += _delete_where("purchase_items", "purchase_id IN (SELECT purchase_id FROM purchases WHERE store_id LIKE ?)", (store_pattern,))
        deleted_count += _delete_where("purchases", "store_id LIKE ? OR invoice_number LIKE ?", (store_pattern, tag_pattern))

        # 6. Inventory batches & Storage locations
        deleted_count += _delete_where("inventory_batches", "store_id LIKE ? OR batch_number LIKE ?", (store_pattern, tag_pattern))
        deleted_count += _delete_where("storage_locations", "store_id LIKE ? OR shelf_code LIKE ?", (store_pattern, tag_pattern))

        # 7. Suppliers
        deleted_count += _delete_where("suppliers", "store_id LIKE ? OR supplier_code LIKE ?", (store_pattern, tag_pattern))

        # 8. Quality engineering tables
        deleted_count += _delete_where("fmea_records", "store_id LIKE ? OR process_module LIKE ?", (store_pattern, tag_pattern))
        deleted_count += _delete_where("sqc_defects", "store_id LIKE ? OR defect_type LIKE ?", (store_pattern, tag_pattern))
        deleted_count += _delete_where("pdca_items", "store_id LIKE ? OR improvement_id LIKE ?", (store_pattern, tag_pattern))

        # 9. Audit logs
        deleted_count += _delete_where("audit_logs", "store_id LIKE ? OR details LIKE ?", (store_pattern, tag_pattern))

        # 10. Medicines
        deleted_count += _delete_where("medicines", "store_id LIKE ? OR medicine_code LIKE ?", (store_pattern, tag_pattern))

        # 11. Users
        deleted_count += _delete_where("users", "store_id LIKE ? OR username LIKE 'test_%'", (store_pattern,))

        # 12. Stores
        deleted_count += _delete_where("stores", "store_id LIKE ?", (store_pattern,))

        cursor.execute("PRAGMA foreign_keys = ON;")
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return deleted_count


def seed_test_dataset(db: Database, test_tag: str = "TEST", reference_date: Optional[str] = None) -> Dict[str, Any]:
    """
    Populates an isolated test database with realistic test records.
    Idempotent and repeatable: purges existing test records matching test_tag before seeding.
    """
    assert_isolated_test_database(db)

    # Ensure baseline schema DDL and Stage 1 & Stage 2 schema is applied
    db.execute_script(SCHEMA_SQL)
    migrate_database(db)
    if not is_migration_applied(db):
        apply_stage2_migration(db, reference_date=reference_date)

    # Initialize quality tables if available
    try:
        from utils.fmea import init_fmea_db
        init_fmea_db(db)
    except Exception:
        pass

    try:
        from utils.sqc import init_sqc_db
        init_sqc_db(db)
    except Exception:
        pass

    # Clean any previous run
    cleanup_test_data(db, test_tag=test_tag)

    ref_dt = datetime.strptime(reference_date, "%Y-%m-%d") if reference_date else datetime.now()
    today_str = ref_dt.strftime("%Y-%m-%d")
    now_time_str = ref_dt.strftime("%Y-%m-%d %H:%M:%S")

    store_alpha_id = f"STORE-{test_tag}-ALPHA"
    store_beta_id = f"STORE-{test_tag}-BETA"

    seeded_summary = {
        "stores": [],
        "users": [],
        "locations": [],
        "suppliers": [],
        "medicines": [],
        "batches": [],
        "purchases": [],
        "sales": [],
        "returns": [],
        "fmea": [],
        "sqc": [],
        "pdca": []
    }

    # =========================================================================
    # 1. STORES
    # =========================================================================
    stores = [
        (store_alpha_id, "Apollo Care Pharmacy (Test Alpha)", "Dr. Alok Verma"),
        (store_beta_id, "MedPlus Express (Test Beta)", "Dr. Bhavna Sharma")
    ]
    for s_id, s_name, s_owner in stores:
        db.execute(
            "INSERT INTO stores (store_id, store_name, owner_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (s_id, s_name, s_owner, now_time_str, now_time_str)
        )
        seeded_summary["stores"].append({"store_id": s_id, "store_name": s_name})

    # =========================================================================
    # 2. USERS (5 Canonical Roles + Inactive Account)
    # =========================================================================
    default_test_pwd = "TestPassword@2026"
    test_pwd_hash = hash_password(default_test_pwd)

    users_data = [
        # Store Alpha Users
        ("test_owner_alpha", test_pwd_hash, "Owner", store_alpha_id, "Dr. Alok Verma", "alok.owner@testpharm.local", 1),
        ("test_admin_alpha", test_pwd_hash, "Admin", store_alpha_id, "Ananya Roy", "ananya.admin@testpharm.local", 1),
        ("test_pharma_alpha", test_pwd_hash, "Pharmacist", store_alpha_id, "Pooja Sharma", "pooja.pharma@testpharm.local", 1),
        ("test_cashier_alpha", test_pwd_hash, "Cashier", store_alpha_id, "Rohan Gupta", "rohan.cashier@testpharm.local", 1),
        ("test_inv_alpha", test_pwd_hash, "Inventory Manager", store_alpha_id, "Vikram Singh", "vikram.inv@testpharm.local", 1),
        ("test_inactive_alpha", test_pwd_hash, "Cashier", store_alpha_id, "Inactive Staff", "inactive@testpharm.local", 0),
        # Store Beta Users
        ("test_owner_beta", test_pwd_hash, "Owner", store_beta_id, "Dr. Bhavna Sharma", "bhavna.owner@testpharm.local", 1),
        ("test_cashier_beta", test_pwd_hash, "Cashier", store_beta_id, "Siddharth Rao", "sid.cashier@testpharm.local", 1),
    ]

    user_id_map = {}
    for uname, phash, role, sid, fname, email, active in users_data:
        db.execute(
            """
            INSERT INTO users (username, password_hash, role, store_id, full_name, email, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (uname, phash, role, sid, fname, email, active)
        )
        row = db.fetch_one("SELECT user_id FROM users WHERE username = ?", (uname,))
        uid = row["user_id"] if row else None
        user_id_map[uname] = uid
        seeded_summary["users"].append({"user_id": uid, "username": uname, "role": role, "store_id": sid, "is_active": active})

    # =========================================================================
    # 3. STORAGE LOCATIONS (Shelves)
    # =========================================================================
    locations_data = [
        (store_alpha_id, "SHELF-TEST-A1", "Rack A", "Bin 1", "Room Temperature Solid Dosage"),
        (store_alpha_id, "SHELF-TEST-A2", "Rack A", "Bin 2", "Secondary Solid Dosage Shelf"),
        (store_alpha_id, "SHELF-TEST-B1", "Rack B", "Bin 1", "General Antibiotics and Syrups"),
        (store_alpha_id, "SHELF-TEST-B2", "Rack B", "Bin 2", "Fast Moving OTC Shelf"),
        (store_alpha_id, "SHELF-TEST-COLD", "Cold Unit 1", "Bin C1", "Insulin & Biologicals 2-8°C"),
        (store_alpha_id, "SHELF-TEST-QUARANTINE", "Quarantine Rack Q", "Bin Q1", "Defective & Expired Holding"),
        (store_beta_id, "SHELF-TEST-BETA-01", "Rack Main", "Bin 1", "Beta Store Primary Storage"),
    ]

    loc_id_map = {}
    for sid, scode, rack, bin_no, desc in locations_data:
        db.execute(
            """
            INSERT INTO storage_locations (store_id, shelf_code, rack, bin, description, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (sid, scode, rack, bin_no, desc)
        )
        row = db.fetch_one("SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?", (sid, scode))
        lid = row["location_id"] if row else None
        loc_id_map[(sid, scode)] = lid
        seeded_summary["locations"].append({"location_id": lid, "shelf_code": scode, "store_id": sid})

    # =========================================================================
    # 4. SUPPLIERS
    # =========================================================================
    suppliers_data = [
        (store_alpha_id, "SUP-TEST-001", "Cipla Distribution Hub", "Rajesh Patel", "9811223344", "sales@cipla-dist.test", "27AAAAA0000A1Z5"),
        (store_alpha_id, "SUP-TEST-002", "Sun Pharma Supply Co", "Amit Saxena", "9822334455", "orders@sun-supply.test", "27BBBBB1111B1Z6"),
        (store_beta_id, "SUP-TEST-003", "Zydus Healthcare Dist", "Karan Mehta", "9833445566", "karan@zydus-dist.test", "27CCCCC2222C1Z7"),
    ]

    sup_id_map = {}
    for sid, scode, sname, cpers, phone, email, gst in suppliers_data:
        db.execute(
            """
            INSERT INTO suppliers (store_id, supplier_code, supplier_name, contact_person, phone, email, gst_number, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (sid, scode, sname, cpers, phone, email, gst)
        )
        row = db.fetch_one("SELECT supplier_id FROM suppliers WHERE store_id = ? AND supplier_code = ?", (sid, scode))
        sup_id = row["supplier_id"] if row else None
        sup_id_map[scode] = sup_id
        seeded_summary["suppliers"].append({"supplier_id": sup_id, "supplier_code": scode, "store_id": sid})

    # =========================================================================
    # 5. MEDICINES & BATCH INVENTORY
    # =========================================================================
    # Dates
    exp_far = (ref_dt + timedelta(days=365)).strftime("%Y-%m-%d")
    exp_mid = (ref_dt + timedelta(days=180)).strftime("%Y-%m-%d")
    exp_near = (ref_dt + timedelta(days=20)).strftime("%Y-%m-%d")
    exp_past = (ref_dt - timedelta(days=30)).strftime("%Y-%m-%d")
    mfg_past = (ref_dt - timedelta(days=180)).strftime("%Y-%m-%d")

    # Medicines Catalog for Store Alpha
    medicines_alpha = [
        # code, name, category, mfr, legacy_batch, price, total_qty, exp
        ("TEST-MED-01", "Paracetamol 650mg Dolo", "Analgesic", "Cipla Ltd", "B2026-A1", 30.00, 205, exp_far),
        ("TEST-MED-02", "Amoxicillin 500mg Trihydrate", "Antibiotic", "Sun Pharma", "B2026-B1", 95.00, 135, exp_mid),
        ("TEST-MED-03", "Cetirizine 10mg Relief", "Antihistamine", "Dr. Reddy's", "B2026-C1", 15.00, 120, exp_far),
        ("TEST-MED-04", "Azithromycin 500mg (Low Stock)", "Antibiotic", "Sun Pharma", "B2026-D1", 130.00, 5, exp_mid),
        ("TEST-MED-05", "Insulin Glargine 100IU (OOS)", "Diabetes", "Biocon", "B2026-E1", 500.00, 0, exp_near),
        ("TEST-MED-06", "Pantoprazole 40mg Gastro", "Gastroenterology", "Zydus", "B2026-F1", 60.00, 80, exp_far),
    ]

    med_id_map = {}
    for mcode, mname, cat, mfr, lbatch, price, qty, exp in medicines_alpha:
        db.execute(
            """
            INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (store_alpha_id, mcode, mname, cat, mfr, lbatch, price, qty, exp)
        )
        row = db.fetch_one("SELECT medicine_id FROM medicines WHERE store_id = ? AND medicine_code = ?", (store_alpha_id, mcode))
        mid = row["medicine_id"] if row else None
        med_id_map[mcode] = mid
        seeded_summary["medicines"].append({"medicine_id": mid, "code": mcode, "name": mname, "store_id": store_alpha_id})

    # Medicine for Store Beta (Tenant Isolation)
    db.execute(
        """
        INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
        VALUES (?, 'TEST-MED-BETA-01', 'Beta Amoxicillin 500mg', 'Antibiotic', 'Sun Pharma', 'BETA-B1', 90.00, 50, ?)
        """,
        (store_beta_id, exp_far)
    )
    bmed_row = db.fetch_one("SELECT medicine_id FROM medicines WHERE store_id = ? AND medicine_code = ?", (store_beta_id, "TEST-MED-BETA-01"))
    bmed_id = bmed_row["medicine_id"] if bmed_row else None
    med_id_map["TEST-MED-BETA-01"] = bmed_id

    # Normalized Batches for Store Alpha
    # Tests shelf allocation rules:
    #   - BATCH-TEST-DOLO-01 & 02: Same medicine, same expiry -> permitted on SHELF-TEST-A1
    #   - BATCH-TEST-DOLO-03: Same medicine, different expiry -> required on SHELF-TEST-A2
    #   - BATCH-TEST-CET-01: Different medicine on SHELF-TEST-B1 -> permitted
    #   - BATCH-TEST-DOLO-EXP: Expired -> on SHELF-TEST-QUARANTINE, status='Expired'
    #   - BATCH-TEST-AMOX-QUA: Quarantined -> status='Quarantined'
    #   - BATCH-TEST-AMOX-UNV: Unverified -> verification_flag=1
    shelf_a1 = loc_id_map[(store_alpha_id, "SHELF-TEST-A1")]
    shelf_a2 = loc_id_map[(store_alpha_id, "SHELF-TEST-A2")]
    shelf_b1 = loc_id_map[(store_alpha_id, "SHELF-TEST-B1")]
    shelf_b2 = loc_id_map[(store_alpha_id, "SHELF-TEST-B2")]
    shelf_cold = loc_id_map[(store_alpha_id, "SHELF-TEST-COLD")]
    shelf_quarantine = loc_id_map[(store_alpha_id, "SHELF-TEST-QUARANTINE")]
    sup1 = sup_id_map["SUP-TEST-001"]
    sup2 = sup_id_map["SUP-TEST-002"]

    batches_data = [
        # Paracetamol batches (Same expiry shared shelf, different expiry separate shelf, expired)
        (store_alpha_id, med_id_map["TEST-MED-01"], "BATCH-TEST-DOLO-01", sup1, mfg_past, exp_far, today_str, 100, 100, 20.00, 30.00, shelf_a1, "Active", 0, "Primary bulk batch"),
        (store_alpha_id, med_id_map["TEST-MED-01"], "BATCH-TEST-DOLO-02", sup1, mfg_past, exp_far, today_str, 50, 50, 20.00, 30.00, shelf_a1, "Active", 0, "Shared shelf same expiry"),
        (store_alpha_id, med_id_map["TEST-MED-01"], "BATCH-TEST-DOLO-03", sup1, mfg_past, exp_mid, today_str, 40, 40, 18.00, 30.00, shelf_a2, "Active", 0, "Separate shelf earlier expiry"),
        (store_alpha_id, med_id_map["TEST-MED-01"], "BATCH-TEST-DOLO-EXP", sup1, mfg_past, exp_past, today_str, 15, 15, 18.00, 30.00, shelf_quarantine, "Expired", 0, "Expired batch"),
        # Amoxicillin batches (Active, Quarantined, Unverified)
        (store_alpha_id, med_id_map["TEST-MED-02"], "BATCH-TEST-AMOX-01", sup2, mfg_past, exp_mid, today_str, 80, 80, 60.00, 95.00, shelf_b1, "Active", 0, "Sellable active batch"),
        (store_alpha_id, med_id_map["TEST-MED-02"], "BATCH-TEST-AMOX-QUA", sup2, mfg_past, exp_mid, today_str, 25, 25, 60.00, 95.00, shelf_quarantine, "Quarantined", 0, "Quarantined for lab check"),
        (store_alpha_id, med_id_map["TEST-MED-02"], "BATCH-TEST-AMOX-UNV", sup2, mfg_past, exp_far, today_str, 30, 30, 60.00, 95.00, shelf_b2, "Active", 1, "Unverified receiving flag"),
        # Cetirizine (Shared shelf with Amoxicillin where policy allows)
        (store_alpha_id, med_id_map["TEST-MED-03"], "BATCH-TEST-CET-01", sup1, mfg_past, exp_far, today_str, 120, 120, 8.00, 15.00, shelf_b1, "Active", 0, "Standard OTC stock"),
        # Azithromycin (Critical Low Stock)
        (store_alpha_id, med_id_map["TEST-MED-04"], "BATCH-TEST-AZI-01", sup2, mfg_past, exp_mid, today_str, 5, 5, 80.00, 130.00, shelf_a2, "Active", 0, "Reorder threshold reached"),
        # Insulin (Out of Stock)
        (store_alpha_id, med_id_map["TEST-MED-05"], "BATCH-TEST-INS-01", sup2, mfg_past, exp_near, today_str, 0, 0, 350.00, 500.00, shelf_cold, "Active", 0, "Zero units remaining"),
        # Pantoprazole
        (store_alpha_id, med_id_map["TEST-MED-06"], "BATCH-TEST-PAN-01", sup1, mfg_past, exp_far, today_str, 80, 80, 35.00, 60.00, shelf_a1, "Active", 0, "Active gastro stock"),
    ]

    batch_id_map = {}
    for sid, mid, bnum, spid, mfg, exp, rec, init_q, cur_q, pcost, sprice, lid, stat, vflag, notes in batches_data:
        db.execute(
            """
            INSERT INTO inventory_batches (
                store_id, medicine_id, batch_number, supplier_id, mfg_date, expiry_date,
                received_date, initial_quantity, current_quantity, purchase_cost, selling_price,
                location_id, status, verification_flag, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sid, mid, bnum, spid, mfg, exp, rec, init_q, cur_q, pcost, sprice, lid, stat, vflag, notes)
        )
        row = db.fetch_one("SELECT batch_id FROM inventory_batches WHERE store_id = ? AND batch_number = ?", (sid, bnum))
        bid = row["batch_id"] if row else None
        batch_id_map[bnum] = bid
        seeded_summary["batches"].append({"batch_id": bid, "batch_number": bnum, "status": stat})

        # Record initial stock movements
        db.execute(
            """
            INSERT INTO stock_movements (
                store_id, medicine_id, batch_id, movement_type, quantity_delta,
                reference_type, reference_id, notes, created_by, created_at
            ) VALUES (?, ?, ?, 'PURCHASE_RECEIPT', ?, 'PO_INIT', 'PO-TEST-INIT', 'Initial test seed goods receipt', ?, ?)
            """,
            (sid, mid, bid, init_q, user_id_map["test_inv_alpha"], now_time_str)
        )

    # =========================================================================
    # 6. PURCHASES & GOODS RECEIPTS
    # =========================================================================
    db.execute(
        """
        INSERT INTO purchases (
            store_id, supplier_id, invoice_number, purchase_date, total_amount,
            payment_status, status, received_by, notes, created_at, updated_at
        ) VALUES (?, ?, 'PO-TEST-ALPHA-001', ?, 3200.00, 'PAID', 'RECEIVED', ?, 'Procurement order for Paracetamol and Amox', ?, ?)
        """,
        (store_alpha_id, sup1, today_str, user_id_map["test_inv_alpha"], now_time_str, now_time_str)
    )
    po_row = db.fetch_one("SELECT purchase_id FROM purchases WHERE store_id = ? AND invoice_number = 'PO-TEST-ALPHA-001'", (store_alpha_id,))
    po_id = po_row["purchase_id"] if po_row else 1

    db.execute(
        """
        INSERT INTO purchase_items (purchase_id, medicine_id, batch_id, quantity, unit_cost, subtotal)
        VALUES (?, ?, ?, 100, 20.00, 2000.00),
               (?, ?, ?, 20, 60.00, 1200.00)
        """,
        (po_id, med_id_map["TEST-MED-01"], batch_id_map["BATCH-TEST-DOLO-01"],
         po_id, med_id_map["TEST-MED-02"], batch_id_map["BATCH-TEST-AMOX-01"])
    )
    seeded_summary["purchases"].append({"purchase_id": po_id, "invoice_number": "PO-TEST-ALPHA-001"})

    # =========================================================================
    # 7. SALES TRANSACTIONS (Cash, UPI, Card + 10-digit Indian Mobile Numbers)
    # =========================================================================
    # Sale 1: Cash payment, Patient Ramesh Kumar (9876543210), 10 units Dolo
    # FEFO should allocate from BATCH-TEST-DOLO-03 (Earliest expiry!)
    db.execute(
        """
        INSERT INTO sales (
            store_id, invoice_number, patient_name, patient_phone, patient_age,
            sale_date, subtotal, discount_amount, tax_amount, rounding_amount,
            total_amount, payment_method, payment_reference, status, user_id
        ) VALUES (
            ?, 'INV-TEST-CASH-001', 'Ramesh Kumar', '9876543210', 42,
            ?, 300.00, 0.0, 0.0, 0.0, 300.00, 'Cash', 'CASH-REC-01', 'COMPLETED', ?
        )
        """,
        (store_alpha_id, now_time_str, user_id_map["test_cashier_alpha"])
    )
    sale1_row = db.fetch_one("SELECT sale_id FROM sales WHERE invoice_number = 'INV-TEST-CASH-001'")
    sale1_id = sale1_row["sale_id"] if sale1_row else None

    db.execute(
        """
        INSERT INTO sale_items (store_id, sale_id, medicine_id, quantity, price, subtotal)
        VALUES (?, ?, ?, 10, 30.00, 300.00)
        """,
        (store_alpha_id, sale1_id, med_id_map["TEST-MED-01"])
    )
    s1_item_row = db.fetch_one("SELECT item_id FROM sale_items WHERE sale_id = ?", (sale1_id,))
    s1_item_id = s1_item_row["item_id"] if s1_item_row else None

    # Allocation & FEFO deduction from Batch 3
    dolo_b3_id = batch_id_map["BATCH-TEST-DOLO-03"]
    db.execute(
        """
        INSERT INTO sale_batch_allocations (sale_item_id, batch_id, quantity, unit_price, subtotal)
        VALUES (?, ?, 10, 30.00, 300.00)
        """,
        (s1_item_id, dolo_b3_id)
    )
    db.execute("UPDATE inventory_batches SET current_quantity = current_quantity - 10 WHERE batch_id = ?", (dolo_b3_id,))
    db.execute("UPDATE medicines SET quantity = quantity - 10 WHERE medicine_id = ?", (med_id_map["TEST-MED-01"],))
    db.execute(
        """
        INSERT INTO stock_movements (
            store_id, medicine_id, batch_id, movement_type, quantity_delta,
            reference_type, reference_id, notes, created_by, created_at
        ) VALUES (?, ?, ?, 'SALE_DISPENSE', -10, 'SALE', 'INV-TEST-CASH-001', 'Sale dispense 10 units', ?, ?)
        """,
        (store_alpha_id, med_id_map["TEST-MED-01"], dolo_b3_id, user_id_map["test_cashier_alpha"], now_time_str)
    )
    seeded_summary["sales"].append({"sale_id": sale1_id, "invoice_number": "INV-TEST-CASH-001", "payment_method": "Cash"})

    # Sale 2: UPI payment, Patient Suman Lata (8765432109), Amoxicillin 5 units + Cetirizine 10 units
    db.execute(
        """
        INSERT INTO sales (
            store_id, invoice_number, patient_name, patient_phone, patient_age,
            sale_date, subtotal, discount_amount, tax_amount, rounding_amount,
            total_amount, payment_method, payment_reference, status, user_id
        ) VALUES (
            ?, 'INV-TEST-UPI-002', 'Suman Lata', '8765432109', 35,
            ?, 625.00, 0.0, 0.0, 0.0, 625.00, 'UPI', 'UPI/TEST/998877', 'COMPLETED', ?
        )
        """,
        (store_alpha_id, now_time_str, user_id_map["test_cashier_alpha"])
    )
    sale2_row = db.fetch_one("SELECT sale_id FROM sales WHERE invoice_number = 'INV-TEST-UPI-002'")
    sale2_id = sale2_row["sale_id"] if sale2_row else None

    # Items for sale 2
    amox_b1_id = batch_id_map["BATCH-TEST-AMOX-01"]
    cet_b1_id = batch_id_map["BATCH-TEST-CET-01"]

    db.execute(
        """
        INSERT INTO sale_items (store_id, sale_id, medicine_id, quantity, price, subtotal)
        VALUES (?, ?, ?, 5, 95.00, 475.00)
        """,
        (store_alpha_id, sale2_id, med_id_map["TEST-MED-02"])
    )
    s2_item1_row = db.fetch_one("SELECT item_id FROM sale_items WHERE sale_id = ? AND medicine_id = ?", (sale2_id, med_id_map["TEST-MED-02"]))
    s2_item1_id = s2_item1_row["item_id"] if s2_item1_row else None

    db.execute(
        """
        INSERT INTO sale_batch_allocations (sale_item_id, batch_id, quantity, unit_price, subtotal)
        VALUES (?, ?, 5, 95.00, 475.00)
        """,
        (s2_item1_id, amox_b1_id)
    )
    db.execute("UPDATE inventory_batches SET current_quantity = current_quantity - 5 WHERE batch_id = ?", (amox_b1_id,))
    db.execute("UPDATE medicines SET quantity = quantity - 5 WHERE medicine_id = ?", (med_id_map["TEST-MED-02"],))
    db.execute(
        """
        INSERT INTO stock_movements (store_id, medicine_id, batch_id, movement_type, quantity_delta, reference_type, reference_id, notes, created_by, created_at)
        VALUES (?, ?, ?, 'SALE_DISPENSE', -5, 'SALE', 'INV-TEST-UPI-002', 'Sale dispense 5 units', ?, ?)
        """,
        (store_alpha_id, med_id_map["TEST-MED-02"], amox_b1_id, user_id_map["test_cashier_alpha"], now_time_str)
    )

    db.execute(
        """
        INSERT INTO sale_items (store_id, sale_id, medicine_id, quantity, price, subtotal)
        VALUES (?, ?, ?, 10, 15.00, 150.00)
        """,
        (store_alpha_id, sale2_id, med_id_map["TEST-MED-03"])
    )
    s2_item2_row = db.fetch_one("SELECT item_id FROM sale_items WHERE sale_id = ? AND medicine_id = ?", (sale2_id, med_id_map["TEST-MED-03"]))
    s2_item2_id = s2_item2_row["item_id"] if s2_item2_row else None

    db.execute(
        """
        INSERT INTO sale_batch_allocations (sale_item_id, batch_id, quantity, unit_price, subtotal)
        VALUES (?, ?, 10, 15.00, 150.00)
        """,
        (s2_item2_id, cet_b1_id)
    )
    db.execute("UPDATE inventory_batches SET current_quantity = current_quantity - 10 WHERE batch_id = ?", (cet_b1_id,))
    db.execute("UPDATE medicines SET quantity = quantity - 10 WHERE medicine_id = ?", (med_id_map["TEST-MED-03"],))
    db.execute(
        """
        INSERT INTO stock_movements (store_id, medicine_id, batch_id, movement_type, quantity_delta, reference_type, reference_id, notes, created_by, created_at)
        VALUES (?, ?, ?, 'SALE_DISPENSE', -10, 'SALE', 'INV-TEST-UPI-002', 'Sale dispense 10 units', ?, ?)
        """,
        (store_alpha_id, med_id_map["TEST-MED-03"], cet_b1_id, user_id_map["test_cashier_alpha"], now_time_str)
    )
    seeded_summary["sales"].append({"sale_id": sale2_id, "invoice_number": "INV-TEST-UPI-002", "payment_method": "UPI"})

    # Sale 3: Card payment, Patient Vikas Mehra (7654321098), 5 units Dolo
    db.execute(
        """
        INSERT INTO sales (
            store_id, invoice_number, patient_name, patient_phone, patient_age,
            sale_date, subtotal, discount_amount, tax_amount, rounding_amount,
            total_amount, payment_method, payment_reference, status, user_id
        ) VALUES (
            ?, 'INV-TEST-CARD-003', 'Vikas Mehra', '7654321098', 29,
            ?, 150.00, 0.0, 0.0, 0.0, 150.00, 'Card', 'TXN-CARD-443322', 'COMPLETED', ?
        )
        """,
        (store_alpha_id, now_time_str, user_id_map["test_cashier_alpha"])
    )
    sale3_row = db.fetch_one("SELECT sale_id FROM sales WHERE invoice_number = 'INV-TEST-CARD-003'")
    sale3_id = sale3_row["sale_id"] if sale3_row else None

    db.execute(
        """
        INSERT INTO sale_items (store_id, sale_id, medicine_id, quantity, price, subtotal)
        VALUES (?, ?, ?, 5, 30.00, 150.00)
        """,
        (store_alpha_id, sale3_id, med_id_map["TEST-MED-01"])
    )
    s3_item_row = db.fetch_one("SELECT item_id FROM sale_items WHERE sale_id = ?", (sale3_id,))
    s3_item_id = s3_item_row["item_id"] if s3_item_row else None

    db.execute(
        """
        INSERT INTO sale_batch_allocations (sale_item_id, batch_id, quantity, unit_price, subtotal)
        VALUES (?, ?, 5, 30.00, 150.00)
        """,
        (s3_item_id, dolo_b3_id)
    )
    db.execute("UPDATE inventory_batches SET current_quantity = current_quantity - 5 WHERE batch_id = ?", (dolo_b3_id,))
    db.execute("UPDATE medicines SET quantity = quantity - 5 WHERE medicine_id = ?", (med_id_map["TEST-MED-01"],))
    db.execute(
        """
        INSERT INTO stock_movements (store_id, medicine_id, batch_id, movement_type, quantity_delta, reference_type, reference_id, notes, created_by, created_at)
        VALUES (?, ?, ?, 'SALE_DISPENSE', -5, 'SALE', 'INV-TEST-CARD-003', 'Sale dispense 5 units', ?, ?)
        """,
        (store_alpha_id, med_id_map["TEST-MED-01"], dolo_b3_id, user_id_map["test_cashier_alpha"], now_time_str)
    )
    seeded_summary["sales"].append({"sale_id": sale3_id, "invoice_number": "INV-TEST-CARD-003", "payment_method": "Card"})

    # Sale 4: For testing full return (2 units Cetirizine)
    db.execute(
        """
        INSERT INTO sales (
            store_id, invoice_number, patient_name, patient_phone, patient_age,
            sale_date, subtotal, discount_amount, tax_amount, rounding_amount,
            total_amount, payment_method, payment_reference, status, user_id
        ) VALUES (
            ?, 'INV-TEST-RET-004', 'Anita Desai', '9123456789', 51,
            ?, 30.00, 0.0, 0.0, 0.0, 30.00, 'Cash', 'CASH-REC-04', 'COMPLETED', ?
        )
        """,
        (store_alpha_id, now_time_str, user_id_map["test_cashier_alpha"])
    )
    sale4_row = db.fetch_one("SELECT sale_id FROM sales WHERE invoice_number = 'INV-TEST-RET-004'")
    sale4_id = sale4_row["sale_id"] if sale4_row else None

    db.execute(
        """
        INSERT INTO sale_items (store_id, sale_id, medicine_id, quantity, price, subtotal)
        VALUES (?, ?, ?, 2, 15.00, 30.00)
        """,
        (store_alpha_id, sale4_id, med_id_map["TEST-MED-03"])
    )
    s4_item_row = db.fetch_one("SELECT item_id FROM sale_items WHERE sale_id = ?", (sale4_id,))
    s4_item_id = s4_item_row["item_id"] if s4_item_row else None

    db.execute(
        """
        INSERT INTO sale_batch_allocations (sale_item_id, batch_id, quantity, unit_price, subtotal)
        VALUES (?, ?, 2, 15.00, 30.00)
        """,
        (s4_item_id, cet_b1_id)
    )
    db.execute("UPDATE inventory_batches SET current_quantity = current_quantity - 2 WHERE batch_id = ?", (cet_b1_id,))
    db.execute("UPDATE medicines SET quantity = quantity - 2 WHERE medicine_id = ?", (med_id_map["TEST-MED-03"],))

    # =========================================================================
    # 8. RETURNS (Partial Return Sellable Restocked vs Damaged Excluded)
    # =========================================================================
    # Return 1: Partial return of 2 units Dolo from Sale 1 (Condition: SELLABLE -> Stock Restored)
    db.execute(
        """
        INSERT INTO sale_returns (
            store_id, sale_id, invoice_number, return_date, total_refund, refund_method, reason, created_by, created_at
        ) VALUES (?, ?, 'INV-TEST-CASH-001', ?, 60.00, 'Cash', 'Customer prescribed dosage reduction', ?, ?)
        """,
        (store_alpha_id, sale1_id, today_str, user_id_map["test_cashier_alpha"], now_time_str)
    )
    ret1_row = db.fetch_one("SELECT return_id FROM sale_returns WHERE invoice_number = 'INV-TEST-CASH-001'")
    ret1_id = ret1_row["return_id"] if ret1_row else None

    db.execute(
        """
        INSERT INTO sale_return_items (
            return_id, sale_item_id, medicine_id, batch_id, quantity, unit_price, refund_amount, restocked, restock_condition
        ) VALUES (?, ?, ?, ?, 2, 30.00, 60.00, 1, 'SELLABLE')
        """,
        (ret1_id, s1_item_id, med_id_map["TEST-MED-01"], dolo_b3_id)
    )
    # Restock 2 units into batch and medicine
    db.execute("UPDATE inventory_batches SET current_quantity = current_quantity + 2 WHERE batch_id = ?", (dolo_b3_id,))
    db.execute("UPDATE medicines SET quantity = quantity + 2 WHERE medicine_id = ?", (med_id_map["TEST-MED-01"],))
    db.execute(
        """
        INSERT INTO stock_movements (store_id, medicine_id, batch_id, movement_type, quantity_delta, reference_type, reference_id, notes, created_by, created_at)
        VALUES (?, ?, ?, 'CUSTOMER_RETURN', 2, 'RETURN', 'RET-01', 'Partial customer return restocked', ?, ?)
        """,
        (store_alpha_id, med_id_map["TEST-MED-01"], dolo_b3_id, user_id_map["test_cashier_alpha"], now_time_str)
    )
    seeded_summary["returns"].append({"return_id": ret1_id, "condition": "SELLABLE", "refund": 60.00})

    # Return 2: Full return of 2 units Cetirizine from Sale 4 (Condition: DAMAGED -> NOT restocked to sellable)
    db.execute(
        """
        INSERT INTO sale_returns (
            store_id, sale_id, invoice_number, return_date, total_refund, refund_method, reason, created_by, created_at
        ) VALUES (?, ?, 'INV-TEST-RET-004', ?, 30.00, 'Cash', 'Packaging crushed by customer', ?, ?)
        """,
        (store_alpha_id, sale4_id, today_str, user_id_map["test_cashier_alpha"], now_time_str)
    )
    ret2_row = db.fetch_one("SELECT return_id FROM sale_returns WHERE invoice_number = 'INV-TEST-RET-004'")
    ret2_id = ret2_row["return_id"] if ret2_row else None

    db.execute(
        """
        INSERT INTO sale_return_items (
            return_id, sale_item_id, medicine_id, batch_id, quantity, unit_price, refund_amount, restocked, restock_condition
        ) VALUES (?, ?, ?, ?, 2, 15.00, 30.00, 0, 'DAMAGED')
        """,
        (ret2_id, s4_item_id, med_id_map["TEST-MED-03"], cet_b1_id)
    )
    # Critical: Do NOT restore quantity for damaged return; log quarantine movement
    db.execute(
        """
        INSERT INTO stock_movements (store_id, medicine_id, batch_id, movement_type, quantity_delta, reference_type, reference_id, notes, created_by, created_at)
        VALUES (?, ?, ?, 'RECALL_QUARANTINE', 0, 'RETURN_DAMAGED', 'RET-02', 'Damaged return sent to quarantine; sellable stock untouched', ?, ?)
        """,
        (store_alpha_id, med_id_map["TEST-MED-03"], cet_b1_id, user_id_map["test_cashier_alpha"], now_time_str)
    )
    seeded_summary["returns"].append({"return_id": ret2_id, "condition": "DAMAGED", "refund": 30.00})

    # =========================================================================
    # 9. QUALITY ENGINEERING (FMEA, SQC, PDCA)
    # =========================================================================
    # FMEA
    fmea_data = [
        (store_alpha_id, "Dispensing LASA Medicines", "Dispensing wrong strength", "Adverse patient reaction", "Look-alike packaging", "Barcode check", "Visual double check", 8, "High clinical impact", 3, "Rare occurrence", 4, "Manual inspection", 96, "High", "Barcode scanner enforcement", "Completed", "Dr. Alok Verma"),
        (store_alpha_id, "Cold Chain Storage", "Temperature excursion > 8C", "Loss of vaccine/insulin potency", "Thermostat drift", "Temperature alarm", "Daily manual log", 9, "Biological damage", 2, "Backup generator present", 3, "IoT alert", 54, "Medium", "Automated temperature alarm", "In Progress", "Vikram Singh"),
        (store_alpha_id, "Prescription Validation", "Dispensing Schedule H1 without Rx", "Regulatory penalty and patient hazard", "Rush hour oversight", "Mandatory Rx lock", "Pharmacist sign-off", 7, "Regulatory violation", 2, "Low frequency", 2, "Register audit", 28, "Low", "Mandatory prescription upload", "Completed", "Pooja Sharma"),
    ]
    for row in fmea_data:
        try:
            db.execute(
                """
                INSERT INTO fmea_records (
                    store_id, process_module, failure_mode, potential_effect, potential_cause,
                    prevention_control, detection_control, severity, severity_rationale,
                    occurrence, occurrence_rationale, detection, detection_rationale,
                    rpn, risk_level, recommended_action, action_status, owner
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row
            )
            seeded_summary["fmea"].append({"process_module": row[1], "rpn": row[13]})
        except Exception:
            pass

    # SQC Defects
    sqc_data = [
        (store_alpha_id, today_str, "Inventory", "Packaging Damage", "Box crushed during transit", "High", 8, "Open", "Transit handling", "Supplier packaging feedback", "QA Team"),
        (store_alpha_id, today_str, "Billing", "Label Printing Blur", "Barcode scanner unreadable", "Medium", 4, "Closed", "Printer toner low", "Replaced thermal ribbon", "Rohan Gupta"),
        (store_alpha_id, today_str, "Procurement", "Near Expiry Stock", "Supplier delivered < 6 month expiry", "Critical", 2, "Open", "Vendor Cipla Direct", "Return batch to supplier", "Vikram Singh"),
    ]
    for row in sqc_data:
        try:
            db.execute(
                """
                INSERT INTO sqc_defects (
                    store_id, date_reported, module, defect_type, description,
                    severity, frequency, status, root_cause, corrective_action, reported_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row
            )
            seeded_summary["sqc"].append({"defect_type": row[3], "module": row[2]})
        except Exception:
            pass

    # PDCA Items
    pdca_data = [
        (store_alpha_id, "TEST-PDCA-01", "Reduce Near-Expiry Inventory Write-offs", "Implement 60-day proactive supplier return window", "Active monitoring of batches expiring in 60 days", "Evaluate returned batch credit", "Adopt policy store-wide", "Vikram Singh", "Do", today_str, "Write-off reduction by 40%", "Active monitoring"),
        (store_alpha_id, "TEST-PDCA-02", "Eliminate Prescription Dispensing Errors", "Mandatory double-read barcode scanning", "Roll out scanners across all counters", "Audit past 1,000 bills", "Standardize workflow SOP", "Pooja Sharma", "Check", today_str, "Zero mis-dispenses recorded", "Audit complete"),
    ]
    for row in pdca_data:
        try:
            db.execute(
                """
                INSERT INTO pdca_items (
                    store_id, improvement_id, problem, plan_action, do_action,
                    check_action, act_action, owner, status, date_created, result_metric, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                row
            )
            seeded_summary["pdca"].append({"improvement_id": row[1], "status": row[8]})
        except Exception:
            pass

    return seeded_summary
