"""
Active Store Inventory & Purchasing Seeder for Pharmacy Management System.
Idempotently populates 12-15 realistic medicines, multi-batch records adhering to
the Critical Shelf Allocation Rule, suppliers, and purchase orders for the active store.
Operates strictly on data/pharmacy_app.db (or passed db_path). Never touches data/pharmacy.db.
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional, Dict, Any, List


def seed_active_store_inventory(db_path: str = "data/pharmacy_app.db", target_store_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Seeds rich, realistic inventory, batches, shelves, suppliers, and purchases
    for the active registered pharmacy store. Idempotent and crash-safe.
    """
    if "pharmacy.db" == os.path.basename(db_path):
        raise ValueError("SAFETY VIOLATION: Seeder must NEVER run against production pharmacy.db")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Ensure stage 2 tables exist
    has_table = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='storage_locations'").fetchone()
    if not has_table:
        conn.close()
        from database.db import Database
        from database.migration_stage2 import apply_stage2_migration
        apply_stage2_migration(Database(db_path))
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

    # 1. Determine active store
    if not target_store_id:
        store_row = c.execute("SELECT store_id, store_name, owner_name FROM stores ORDER BY rowid DESC LIMIT 1").fetchone()
        if not store_row:
            conn.close()
            return {"success": False, "message": "No registered store found to seed."}
        store_id = store_row["store_id"]
        store_name = store_row["store_name"]
    else:
        store_id = target_store_id
        store_row = c.execute("SELECT store_id, store_name, owner_name FROM stores WHERE store_id = ?", (store_id,)).fetchone()
        store_name = store_row["store_name"] if store_row else store_id

    # Find owner user_id
    owner_row = c.execute("SELECT user_id, username FROM users WHERE store_id = ? AND role = 'Owner' LIMIT 1", (store_id,)).fetchone()
    owner_id = owner_row["user_id"] if owner_row else 1

    # 2. Ensure Shelves exist for this store
    shelves_def = [
        ("SHELF-A01", "Rack A", "Bin 1", "Main Prescription Shelf (Tablets & Capsules)"),
        ("SHELF-A02", "Rack A", "Bin 2", "Secondary Shelf (Tablets - Later Expiry)"),
        ("SHELF-B01", "Rack B", "Bin 1", "General Liquids & Syrups"),
        ("SHELF-B02", "Rack B", "Bin 2", "Secondary Shelf (Liquids - Later Expiry)"),
        ("SHELF-COLD", "Cold Unit", "Fridge 1", "Cold Chain Storage (Insulin & Biologicals)"),
        ("SHELF-QUAR", "Quarantine", "Bin Q", "Segregated Quarantine / Expired Stock")
    ]
    shelf_id_map: Dict[str, int] = {}
    for code, rack, bin_code, desc in shelves_def:
        row = c.execute("SELECT location_id FROM storage_locations WHERE store_id = ? AND shelf_code = ?", (store_id, code)).fetchone()
        if row:
            shelf_id_map[code] = row["location_id"]
        else:
            c.execute(
                "INSERT INTO storage_locations (store_id, shelf_code, rack, bin, description, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                (store_id, code, rack, bin_code, desc)
            )
            shelf_id_map[code] = c.lastrowid

    # 3. Ensure Suppliers exist
    suppliers_def = [
        ("SUP-001", "Apex Healthcare Distributors", "Ramesh Gupta", "9876543210", "ramesh@apexmed.in", "Plot 44, Okhla Ind Area, New Delhi", "07AAAAA0000A1Z5"),
        ("SUP-002", "Cipla Pharmaceuticals Distribution", "Anita Desai", "9822334455", "orders@cipladist.in", "B-12, MIDC Industrial Area, Mumbai", "27BBBBB1111B2Z6"),
        ("SUP-003", "Sun Pharma Supply Logistics", "Vikram Patel", "9811223344", "supply@sunpharma.in", "GIDC Estate, Vadodara, Gujarat", "24CCCCC2222C3Z7"),
    ]
    supplier_id_map: Dict[str, int] = {}
    for scode, sname, cpers, phone, email, addr, gst in suppliers_def:
        srow = c.execute("SELECT supplier_id FROM suppliers WHERE store_id = ? AND supplier_code = ?", (store_id, scode)).fetchone()
        if srow:
            supplier_id_map[scode] = srow["supplier_id"]
        else:
            c.execute(
                """
                INSERT INTO suppliers (store_id, supplier_code, supplier_name, contact_person, phone, email, address, gst_number, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (store_id, scode, sname, cpers, phone, email, addr, gst)
            )
            supplier_id_map[scode] = c.lastrowid

    # 4. Catalog Medicines (Preserving any existing, e.g. MED 102)
    medicines_def = [
        ("MED 101", "Paracetamol 650mg", "Analgesic", "Micro Labs", 30.00),
        ("MED 102", "Vicks action 500", "Antibiotic", "Micro labs", 10.00), # Existing to preserve
        ("MED 103", "Amoxicillin 500mg", "Antibiotic", "Cipla Ltd", 75.50),
        ("MED 104", "Azithromycin 500mg", "Antibiotic", "Sun Pharma", 110.00),
        ("MED 105", "Cetirizine 10mg", "Antihistamine", "Dr. Reddy's", 20.00),
        ("MED 106", "Metformin 500mg", "Antidiabetic", "USV Ltd", 45.00),
        ("MED 107", "Pantoprazole 40mg", "Antacid", "Alkem Labs", 85.00),
        ("MED 108", "Insulin Glargine 100IU", "Cold Chain", "Sanofi", 650.00),
        ("MED 109", "Cough Syrup 100ml", "Respiratory", "Dabur India", 95.00),
        ("MED 110", "ORS Electrolyte Sachet", "Nutritional", "FDC Ltd", 22.00),
        ("MED 111", "Ibuprofen 400mg", "Analgesic", "Abbott India", 35.00),
        ("MED 112", "Atorvastatin 10mg", "Cardiovascular", "Zydus Cadila", 120.00),
        ("MED 113", "Telmisartan 40mg", "Cardiovascular", "Glenmark", 90.00),
        ("MED 114", "Vitamin C 500mg Chewable", "Nutritional", "Piramal", 25.00),
    ]

    med_id_map: Dict[str, int] = {}
    for mcode, mname, mcat, mmfg, mprice in medicines_def:
        mrow = c.execute("SELECT medicine_id FROM medicines WHERE store_id = ? AND medicine_code = ?", (store_id, mcode)).fetchone()
        if mrow:
            med_id_map[mcode] = mrow["medicine_id"]
        else:
            c.execute(
                """
                INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date)
                VALUES (?, ?, ?, ?, ?, 'INITIAL', ?, 0, '2027-12-31')
                """,
                (store_id, mcode, mname, mcat, mmfg, mprice)
            )
            med_id_map[mcode] = c.lastrowid

    # 5. Batches adhering to Critical Shelf Allocation Rules:
    # Rule 1: Different expiries of same med on separate shelves.
    # Rule 2: Same expiry can share shelf.
    # Rule 3: Different meds can share shelf.
    # Rule 4: Expired/quarantined in SHELF-QUAR with status Expired.
    # Rule 5: Cold chain in SHELF-COLD.
    # (med_code, batch_num, supplier_code, mfg_date, expiry_date, qty, cost, price, shelf_code, status)
    batches_def = [
        # Paracetamol (MED 101): 2 batches with different expiries -> SHELF-A01 and SHELF-A02
        ("MED 101", "PCM-2611", "SUP-001", "2024-11-01", "2026-11-30", 40, 18.00, 30.00, "SHELF-A01", "Active"),
        ("MED 101", "PCM-2708", "SUP-001", "2025-08-01", "2027-08-15", 60, 18.50, 30.00, "SHELF-A02", "Active"),

        # Vicks action 500 (MED 102): Single active batch
        ("MED 102", "b20456", "SUP-001", "2024-12-01", "2026-12-10", 50, 6.50, 10.00, "SHELF-A01", "Active"),

        # Amoxicillin (MED 103): 2 batches with different expiries -> SHELF-A01 and SHELF-A02
        ("MED 103", "AMX-2612", "SUP-002", "2024-12-15", "2026-12-31", 30, 48.00, 75.50, "SHELF-A01", "Active"),
        ("MED 103", "AMX-2706", "SUP-002", "2025-06-15", "2027-06-30", 50, 49.00, 75.50, "SHELF-A02", "Active"),

        # Azithromycin (MED 104)
        ("MED 104", "AZI-2704", "SUP-003", "2025-04-01", "2027-04-30", 25, 72.00, 110.00, "SHELF-A01", "Active"),

        # Cetirizine (MED 105): 2 batches with EXACT SAME expiry -> CAN share SHELF-A01
        ("MED 105", "CET-2703A", "SUP-001", "2025-03-01", "2027-03-31", 100, 11.00, 20.00, "SHELF-A01", "Active"),
        ("MED 105", "CET-2703B", "SUP-001", "2025-03-01", "2027-03-31", 50, 11.00, 20.00, "SHELF-A01", "Active"),

        # Metformin (MED 106): 2 batches with different expiries -> SHELF-A01 and SHELF-A02
        ("MED 106", "MET-2612", "SUP-002", "2024-12-01", "2026-12-15", 80, 28.00, 45.00, "SHELF-A01", "Active"),
        ("MED 106", "MET-2710", "SUP-002", "2025-10-01", "2027-10-31", 120, 29.00, 45.00, "SHELF-A02", "Active"),

        # Pantoprazole (MED 107)
        ("MED 107", "PAN-2705", "SUP-003", "2025-05-01", "2027-05-31", 60, 52.00, 85.00, "SHELF-A01", "Active"),

        # Insulin Glargine (MED 108): Cold Chain storage -> SHELF-COLD
        ("MED 108", "INS-2702", "SUP-002", "2025-02-01", "2027-02-28", 15, 420.00, 650.00, "SHELF-COLD", "Active"),

        # Cough Syrup 100ml (MED 109): Liquids -> SHELF-B01 and SHELF-B02
        ("MED 109", "CS-2611", "SUP-001", "2024-11-10", "2026-11-20", 25, 58.00, 95.00, "SHELF-B01", "Active"),
        ("MED 109", "CS-2707", "SUP-001", "2025-07-10", "2027-07-31", 40, 60.00, 95.00, "SHELF-B02", "Active"),

        # ORS Electrolyte (MED 110): Liquids/Powder shelf -> SHELF-B01
        ("MED 110", "ORS-2709", "SUP-001", "2025-09-01", "2027-09-30", 150, 12.00, 22.00, "SHELF-B01", "Active"),

        # Ibuprofen 400mg (MED 111)
        ("MED 111", "IBU-2701", "SUP-003", "2025-01-10", "2027-01-31", 50, 21.00, 35.00, "SHELF-A01", "Active"),

        # Atorvastatin 10mg (MED 112)
        ("MED 112", "ATV-2708", "SUP-002", "2025-08-01", "2027-08-31", 45, 75.00, 120.00, "SHELF-A01", "Active"),

        # Telmisartan 40mg (MED 113)
        ("MED 113", "TEL-2705", "SUP-003", "2025-05-01", "2027-05-15", 40, 55.00, 90.00, "SHELF-A01", "Active"),

        # Vitamin C (MED 114): Expired batch in SHELF-QUAR + Active batch in SHELF-A01
        ("MED 114", "VIT-2610", "SUP-001", "2024-10-01", "2026-10-01", 10, 14.00, 25.00, "SHELF-QUAR", "Expired"),
        ("MED 114", "VIT-2712", "SUP-001", "2025-12-01", "2027-12-31", 80, 15.00, 25.00, "SHELF-A01", "Active"),
    ]

    batch_id_map: Dict[str, int] = {}
    for mcode, bnum, scode, mfg, exp, qty, cost, price, shelf_code, status in batches_def:
        med_id = med_id_map[mcode]
        supp_id = supplier_id_map[scode]
        loc_id = shelf_id_map[shelf_code]

        brow = c.execute(
            "SELECT batch_id FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND batch_number = ?",
            (store_id, med_id, bnum)
        ).fetchone()

        if brow:
            batch_id_map[bnum] = brow["batch_id"]
        else:
            c.execute(
                """
                INSERT INTO inventory_batches (
                    store_id, medicine_id, batch_number, supplier_id, mfg_date, expiry_date,
                    received_date, initial_quantity, current_quantity, purchase_cost, selling_price,
                    location_id, status, verification_flag, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    store_id, med_id, bnum, supp_id, mfg, exp,
                    datetime.now().strftime("%Y-%m-%d"), qty, qty, cost, price,
                    loc_id, status, 0, f"Initial stock batch on {shelf_code}"
                )
            )
            batch_id = c.lastrowid
            batch_id_map[bnum] = batch_id

            # Stock movement log
            c.execute(
                """
                INSERT INTO stock_movements (
                    store_id, medicine_id, batch_id, movement_type, quantity_delta,
                    reference_type, reference_id, notes, created_by
                ) VALUES (?, ?, ?, 'PURCHASE_RECEIPT', ?, 'INITIAL_SEED', NULL, ?, ?)
                """,
                (store_id, med_id, batch_id, qty, f"Initial inventory batch receipt on {shelf_code}", owner_id)
            )

    # 6. Synchronize Medicines total quantity from active batches (excluding expired)
    for mcode, med_id in med_id_map.items():
        total_active_qty = c.execute(
            "SELECT COALESCE(SUM(current_quantity), 0) FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND status = 'Active'",
            (store_id, med_id)
        ).fetchone()[0]

        # Get earliest expiry of active batches
        earliest_exp = c.execute(
            "SELECT MIN(expiry_date) FROM inventory_batches WHERE store_id = ? AND medicine_id = ? AND status = 'Active'",
            (store_id, med_id)
        ).fetchone()[0] or "2027-12-31"

        c.execute(
            "UPDATE medicines SET quantity = ?, expiry_date = ? WHERE medicine_id = ?",
            (total_active_qty, earliest_exp, med_id)
        )

    # 7. Create Purchase Orders in purchases & purchase_items
    purchases_def = [
        ("PO-2026-001", "SUP-001", "2026-10-25", "RECEIVED", [
            ("MED 101", "PCM-2611", 40, 18.00),
            ("MED 102", "b20456", 50, 6.50),
            ("MED 105", "CET-2703A", 100, 11.00),
            ("MED 109", "CS-2611", 25, 58.00),
            ("MED 110", "ORS-2709", 150, 12.00),
        ]),
        ("PO-2026-002", "SUP-002", "2026-10-28", "RECEIVED", [
            ("MED 103", "AMX-2612", 30, 48.00),
            ("MED 106", "MET-2612", 80, 28.00),
            ("MED 108", "INS-2702", 15, 420.00),
            ("MED 112", "ATV-2708", 45, 75.00),
        ]),
        ("PO-2026-003", "SUP-003", "2026-10-30", "ORDERED", [
            ("MED 104", "AZI-2704", 25, 72.00),
            ("MED 107", "PAN-2705", 60, 52.00),
            ("MED 111", "IBU-2701", 50, 21.00),
            ("MED 113", "TEL-2705", 40, 55.00),
        ])
    ]

    for inv_num, scode, p_date, p_status, p_items in purchases_def:
        p_row = c.execute("SELECT purchase_id FROM purchases WHERE store_id = ? AND invoice_number = ?", (store_id, inv_num)).fetchone()
        if not p_row:
            supp_id = supplier_id_map[scode]
            total_amt = sum(item[2] * item[3] for item in p_items)
            c.execute(
                """
                INSERT INTO purchases (store_id, supplier_id, invoice_number, purchase_date, total_amount, payment_status, status, received_by, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (store_id, supp_id, inv_num, p_date, total_amt, "PAID" if p_status == "RECEIVED" else "PENDING", p_status, owner_id if p_status == "RECEIVED" else None, "Standard vendor replenishment order")
            )
            purchase_id = c.lastrowid

            for mcode, bnum, qty, unit_cost in p_items:
                med_id = med_id_map[mcode]
                batch_id = batch_id_map.get(bnum)
                c.execute(
                    """
                    INSERT INTO purchase_items (purchase_id, medicine_id, batch_id, quantity, unit_cost, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (purchase_id, med_id, batch_id, qty, unit_cost, qty * unit_cost)
                )

    conn.commit()
    conn.close()

    return {
        "success": True,
        "store_id": store_id,
        "store_name": store_name,
        "medicines_count": len(medicines_def),
        "batches_count": len(batches_def),
        "shelves_count": len(shelves_def),
        "suppliers_count": len(suppliers_def),
        "purchases_count": len(purchases_def)
    }


if __name__ == "__main__":
    result = seed_active_store_inventory()
    print("Seed result:", result)
