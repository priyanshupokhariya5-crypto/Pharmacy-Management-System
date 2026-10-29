"""
Safe Database Synchronization and Migration Utility.
Allows non-destructive migration of stores, users, inventory, and sales
between the source development database and the packaged portable EXE database.
"""
import os
import sys
import sqlite3
from typing import Dict, Any, Optional

from database.db import Database


def get_source_db_candidate() -> Optional[str]:
    """
    Locates the source project database if available on the current filesystem.
    Returns None if the application is running in an isolated or deployed environment.
    """
    # 1. Environment variable override
    env_source = os.environ.get("PHARMACY_SOURCE_DB")
    if env_source and os.path.isfile(env_source):
        return os.path.abspath(env_source)

    # 2. Frozen mode: check if running from within the project's dist folder
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        # Structure: <project_root>/dist/PharmacyApp/PharmacyApp.exe -> <project_root>/data/pharmacy.db
        project_root_candidate = os.path.dirname(os.path.dirname(exe_dir))
        candidate_db = os.path.join(project_root_candidate, "data", "pharmacy.db")
        if os.path.isfile(candidate_db):
            return os.path.abspath(candidate_db)
        return None

    # 3. Source mode: project root data folder
    from utils.paths import get_project_root
    src_db = os.path.join(get_project_root(), "data", "pharmacy.db")
    if os.path.isfile(src_db):
        return os.path.abspath(src_db)

    return None


def sync_databases(source_db_path: str, target_db_path: str) -> Dict[str, int]:
    """
    Safely migrates missing stores, users, medicines, and sales records
    from source_db_path into target_db_path without overwriting existing data.
    Preserves all password hashes, salts, and foreign key relationships.
    """
    source_db_path = os.path.abspath(source_db_path)
    target_db_path = os.path.abspath(target_db_path)

    if source_db_path == target_db_path:
        return {"status": "skipped_identical_paths"}

    if not os.path.isfile(source_db_path):
        raise FileNotFoundError(f"Source database not found at: {source_db_path}")

    # Ensure target directory exists
    os.makedirs(os.path.dirname(target_db_path), exist_ok=True)

    src_conn = sqlite3.connect(source_db_path)
    src_conn.row_factory = sqlite3.Row
    dst_conn = sqlite3.connect(target_db_path)
    dst_conn.row_factory = sqlite3.Row

    summary = {
        "stores": 0,
        "users": 0,
        "medicines": 0,
        "sales": 0,
        "sale_items": 0,
        "fmea_records": 0,
        "sqc_defects": 0,
        "pdca_items": 0
    }

    try:
        dst_cursor = dst_conn.cursor()
        dst_cursor.execute("PRAGMA foreign_keys = ON;")

        # Helper to check table existence
        def _table_exists(conn, name: str) -> bool:
            r = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
            return bool(r)

        # ------------------------------------------------------------------
        # 1. Stores
        # ------------------------------------------------------------------
        if _table_exists(src_conn, "stores") and _table_exists(dst_conn, "stores"):
            src_stores = src_conn.execute("SELECT * FROM stores").fetchall()
            dst_store_ids = {r["store_id"] for r in dst_conn.execute("SELECT store_id FROM stores").fetchall()}
            for s in src_stores:
                if s["store_id"] not in dst_store_ids:
                    dst_cursor.execute(
                        "INSERT INTO stores (store_id, store_name, owner_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (s["store_id"], s["store_name"], s["owner_name"], s["created_at"], s["updated_at"])
                    )
                    dst_store_ids.add(s["store_id"])
                    summary["stores"] += 1

        # ------------------------------------------------------------------
        # 2. Users (preserve exact password hashes and salts)
        # ------------------------------------------------------------------
        if _table_exists(src_conn, "users") and _table_exists(dst_conn, "users"):
            src_users = src_conn.execute("SELECT * FROM users").fetchall()
            dst_users = dst_conn.execute("SELECT user_id, username FROM users").fetchall()
            dst_user_map = {r["username"]: r["user_id"] for r in dst_users}
            user_id_map = {}

            for u in src_users:
                uname = u["username"]
                if uname in dst_user_map:
                    user_id_map[u["user_id"]] = dst_user_map[uname]
                    # Safely sync updated password hash if modified in source
                    dst_cursor.execute(
                        "UPDATE users SET password_hash = ? WHERE username = ? AND password_hash != ?",
                        (u["password_hash"], uname, u["password_hash"])
                    )
                else:
                    dst_cursor.execute(
                        "INSERT INTO users (username, password_hash, role, store_id, full_name, email) VALUES (?, ?, ?, ?, ?, ?)",
                        (uname, u["password_hash"], u["role"], u["store_id"], u["full_name"], u["email"])
                    )
                    new_uid = dst_cursor.lastrowid
                    dst_user_map[uname] = new_uid
                    user_id_map[u["user_id"]] = new_uid
                    summary["users"] += 1

        # ------------------------------------------------------------------
        # 3. Medicines
        # ------------------------------------------------------------------
        if _table_exists(src_conn, "medicines") and _table_exists(dst_conn, "medicines"):
            src_meds = src_conn.execute("SELECT * FROM medicines").fetchall()
            dst_meds = dst_conn.execute("SELECT medicine_id, store_id, medicine_code FROM medicines").fetchall()
            dst_med_map = {(r["store_id"], r["medicine_code"]): r["medicine_id"] for r in dst_meds}
            med_id_map = {}

            for m in src_meds:
                key = (m["store_id"], m["medicine_code"])
                if key in dst_med_map:
                    med_id_map[m["medicine_id"]] = dst_med_map[key]
                else:
                    dst_cursor.execute(
                        "INSERT INTO medicines (store_id, medicine_code, medicine_name, category, manufacturer, batch_no, price, quantity, expiry_date, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (m["store_id"], m["medicine_code"], m["medicine_name"], m["category"], m["manufacturer"],
                         m["batch_no"], m["price"], m["quantity"], m["expiry_date"], m["created_at"], m["updated_at"])
                    )
                    new_mid = dst_cursor.lastrowid
                    dst_med_map[key] = new_mid
                    med_id_map[m["medicine_id"]] = new_mid
                    summary["medicines"] += 1

        # ------------------------------------------------------------------
        # 4. Sales
        # ------------------------------------------------------------------
        if _table_exists(src_conn, "sales") and _table_exists(dst_conn, "sales"):
            src_sales = src_conn.execute("SELECT * FROM sales").fetchall()
            dst_sales = dst_conn.execute("SELECT sale_id, invoice_number FROM sales").fetchall()
            dst_sale_map = {r["invoice_number"]: r["sale_id"] for r in dst_sales if r["invoice_number"]}
            sale_id_map = {}
            new_sales_old_ids = set()

            for s in src_sales:
                inv = s["invoice_number"]
                if inv and inv in dst_sale_map:
                    sale_id_map[s["sale_id"]] = dst_sale_map[inv]
                else:
                    mapped_uid = user_id_map.get(s["user_id"], s["user_id"])
                    dst_cursor.execute(
                        "INSERT INTO sales (store_id, invoice_number, patient_name, patient_phone, patient_age, sale_date, total_amount, user_id) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (s["store_id"], inv, s["patient_name"], s["patient_phone"], s["patient_age"], s["sale_date"], s["total_amount"], mapped_uid)
                    )
                    new_sid = dst_cursor.lastrowid
                    if inv:
                        dst_sale_map[inv] = new_sid
                    sale_id_map[s["sale_id"]] = new_sid
                    new_sales_old_ids.add(s["sale_id"])
                    summary["sales"] += 1

        # ------------------------------------------------------------------
        # 5. Sale Items
        # ------------------------------------------------------------------
        if _table_exists(src_conn, "sale_items") and _table_exists(dst_conn, "sale_items"):
            src_items = src_conn.execute("SELECT * FROM sale_items").fetchall()
            for item in src_items:
                if item["sale_id"] in new_sales_old_ids:
                    mapped_sid = sale_id_map.get(item["sale_id"])
                    mapped_mid = med_id_map.get(item["medicine_id"])
                    if mapped_sid and mapped_mid:
                        dst_cursor.execute(
                            "INSERT INTO sale_items (store_id, sale_id, medicine_id, quantity, price, subtotal) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (item["store_id"], mapped_sid, mapped_mid, item["quantity"], item["price"], item["subtotal"])
                        )
                        summary["sale_items"] += 1

        # ------------------------------------------------------------------
        # 6. FMEA, SQC, PDCA Quality Records
        # ------------------------------------------------------------------
        if _table_exists(src_conn, "fmea_records") and _table_exists(dst_conn, "fmea_records"):
            src_fmea = src_conn.execute("SELECT * FROM fmea_records").fetchall()
            for r in src_fmea:
                exists = dst_conn.execute(
                    "SELECT 1 FROM fmea_records WHERE store_id = ? AND process_module = ? AND failure_mode = ?",
                    (r["store_id"], r["process_module"], r["failure_mode"])
                ).fetchone()
                if not exists:
                    cols = [k for k in r.keys() if k != "fmea_id"]
                    placeholders = ", ".join(["?"] * len(cols))
                    col_names = ", ".join(cols)
                    values = [r[k] for k in cols]
                    dst_cursor.execute(
                        f"INSERT INTO fmea_records ({col_names}) VALUES ({placeholders})",
                        values
                    )
                    summary["fmea_records"] += 1

        if _table_exists(src_conn, "sqc_defects") and _table_exists(dst_conn, "sqc_defects"):
            src_sqc = src_conn.execute("SELECT * FROM sqc_defects").fetchall()
            for r in src_sqc:
                exists = dst_conn.execute(
                    "SELECT 1 FROM sqc_defects WHERE store_id = ? AND module = ? AND defect_type = ?",
                    (r["store_id"], r["module"], r["defect_type"])
                ).fetchone()
                if not exists:
                    cols = [k for k in r.keys() if k != "defect_id"]
                    placeholders = ", ".join(["?"] * len(cols))
                    col_names = ", ".join(cols)
                    values = [r[k] for k in cols]
                    dst_cursor.execute(
                        f"INSERT INTO sqc_defects ({col_names}) VALUES ({placeholders})",
                        values
                    )
                    summary["sqc_defects"] += 1

        if _table_exists(src_conn, "pdca_items") and _table_exists(dst_conn, "pdca_items"):
            src_pdca = src_conn.execute("SELECT * FROM pdca_items").fetchall()
            for r in src_pdca:
                exists = dst_conn.execute(
                    "SELECT 1 FROM pdca_items WHERE store_id = ? AND improvement_id = ?",
                    (r["store_id"], r["improvement_id"])
                ).fetchone()
                if not exists:
                    cols = [k for k in r.keys() if k != "pdca_id"]
                    placeholders = ", ".join(["?"] * len(cols))
                    col_names = ", ".join(cols)
                    values = [r[k] for k in cols]
                    dst_cursor.execute(
                        f"INSERT INTO pdca_items ({col_names}) VALUES ({placeholders})",
                        values
                    )
                    summary["pdca_items"] += 1

        # Foreign Key check
        fk_errors = dst_cursor.execute("PRAGMA foreign_key_check;").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign key violations detected after sync: {fk_errors}")

        dst_conn.commit()
        return summary
    except Exception as e:
        dst_conn.rollback()
        raise e
    finally:
        src_conn.close()
        dst_conn.close()


def auto_sync_from_source_if_needed(target_db: Database) -> Optional[Dict[str, int]]:
    """
    Checks if the target database is missing custom stores present in the source database,
    and runs a safe non-destructive migration.
    Only runs in frozen mode (compiled EXE) to preserve unit test isolation in source mode.
    """
    # Auto-sync is only applicable when running as a compiled executable (frozen mode).
    # In source mode, the application already uses the source database directly,
    # and unit tests require completely isolated temporary databases.
    if not getattr(sys, "frozen", False):
        return None

    source_path = get_source_db_candidate()
    if not source_path:
        return None

    target_path = os.path.abspath(target_db.db_path)
    if os.path.abspath(source_path) == target_path:
        return None

    try:
        src_conn = sqlite3.connect(source_path)
        src_stores = {
            r[0] for r in src_conn.execute(
                "SELECT store_id FROM stores WHERE store_id != 'STORE-LEGACY-001'"
            ).fetchall()
        }
        src_conn.close()

        if not src_stores:
            return None

        # Check existing custom stores in target database
        dst_stores = {
            r["store_id"] for r in target_db.fetch_all(
                "SELECT store_id FROM stores WHERE store_id != 'STORE-LEGACY-001'"
            )
        }

        # If any custom store from source is missing in target, synchronize
        missing = src_stores - dst_stores
        if missing:
            return sync_databases(source_path, target_path)

        return None
    except Exception as e:
        sys.stderr.write(f"[SYNC-WARNING] Auto-sync check failed: {e}\n")
        return None
