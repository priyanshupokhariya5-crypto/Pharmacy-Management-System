"""
Authentication service handling user login, store registration, and secure credentials verification.
Enforces multi-store tenancy, salted PBKDF2 password hashing, and unique username/email constraints.
"""
import re
import uuid
from typing import Optional, Tuple, List
from database.db import Database, get_db
from database.schema import hash_password, verify_password
from models.user import User
from services.rbac import (
    require_permission,
    require_store_access,
    PERM_MANAGE_USERS,
    ALL_ROLES,
    normalize_role,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_INVENTORY_MANAGER,
)


class AuthService:
    """Manages authentication and store registration operations."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_db()

    def authenticate(self, identity: str, password: str) -> Tuple[Optional[User], str]:
        """
        Authenticates a user by username OR email and password.
        Returns (User instance, message string). If failed, User is None.
        Rejects login if the account is deactivated (is_active == 0).
        """
        if not identity or not identity.strip():
            return None, "Username or email cannot be empty."

        if not password or not password.strip():
            return None, "Password cannot be empty."

        clean_identity = identity.strip()
        query = """
        SELECT u.*, s.store_name
        FROM users u
        LEFT JOIN stores s ON u.store_id = s.store_id
        WHERE LOWER(u.username) = LOWER(?) OR LOWER(u.email) = LOWER(?)
        """
        row = self.db.fetch_one(query, (clean_identity, clean_identity))

        if not row:
            return None, "Invalid username/email or password."

        if not verify_password(password, row["password_hash"]):
            return None, "Invalid username/email or password."

        # Check account activation status
        keys = row.keys() if hasattr(row, "keys") else []
        if "is_active" in keys and row["is_active"] is not None and int(row["is_active"]) == 0:
            return None, "Account is deactivated. Please contact store owner."

        user = User.from_row(row)
        return user, "Login successful."

    def register_store(
        self,
        store_name: str,
        owner_name: str,
        username: str,
        email: str,
        password: str,
        confirm_password: str
    ) -> Tuple[bool, str, Optional[User]]:
        """
        Registers a new pharmacy store and its primary owner account.
        Validates all inputs, enforces unique constraints, hashes password with PBKDF2,
        and creates a persistent store record with a unique Store ID.
        Returns (success_bool, message, Optional[User]).
        """
        # 1. Required field checks
        if not store_name or not store_name.strip():
            return False, "Pharmacy / Store Name is required.", None
        if not owner_name or not owner_name.strip():
            return False, "Owner's Full Name is required.", None
        if not username or not username.strip():
            return False, "Username is required.", None
        if not email or not email.strip():
            return False, "Email Address is required.", None
        if not password or not password.strip():
            return False, "Password is required.", None
        if not confirm_password or not confirm_password.strip():
            return False, "Please confirm your password.", None

        clean_store = store_name.strip()
        clean_owner = owner_name.strip()
        clean_user = username.strip()
        clean_email = email.strip().lower()

        # 2. Username format validation
        if len(clean_user) < 3:
            return False, "Username must be at least 3 characters long.", None
        if not re.match(r"^[a-zA-Z0-9_.-]+$", clean_user):
            return False, "Username can only contain letters, numbers, underscores, dots, or dashes.", None

        # 3. Email format validation
        email_pattern = r"^[\w\.-]+@[\w\.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, clean_email):
            return False, "Please enter a valid email address.", None

        # 4. Password validation
        if len(password) < 6:
            return False, "Password must be at least 6 characters long.", None
        if password != confirm_password:
            return False, "Password and Confirm Password do not match.", None

        # 5. Unique username check
        existing_user = self.db.fetch_one(
            "SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)",
            (clean_user,)
        )
        if existing_user:
            return False, f"Username '{clean_user}' is already registered.", None

        # 6. Unique email check
        existing_email = self.db.fetch_one(
            "SELECT user_id FROM users WHERE LOWER(email) = LOWER(?)",
            (clean_email,)
        )
        if existing_email:
            return False, f"Email address '{clean_email}' is already registered.", None

        # 7. Generate unique Store ID
        store_id = f"STORE-{uuid.uuid4().hex[:8].upper()}"

        # 8. Hash password using salted PBKDF2
        pwd_hash = hash_password(password)

        conn = self.db.get_connection()
        try:
            cursor = conn.cursor()
            # Insert Store
            cursor.execute(
                "INSERT INTO stores (store_id, store_name, owner_name) VALUES (?, ?, ?)",
                (store_id, clean_store, clean_owner)
            )
            # Insert Owner User
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, store_id, full_name, email) "
                "VALUES (?, ?, 'Owner', ?, ?, ?)",
                (clean_user, pwd_hash, store_id, clean_owner, clean_email)
            )
            user_id = cursor.lastrowid

            # Seed standard storage locations for new store if storage_locations exists
            loc_table = cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='storage_locations'").fetchone()
            if loc_table:
                standard_shelves = [
                    ("SHELF-A01", "Rack A", "Bin 1", "Main Prescription Shelf (Tablets & Capsules)"),
                    ("SHELF-A02", "Rack A", "Bin 2", "Secondary Shelf (Tablets - Later Expiry)"),
                    ("SHELF-B01", "Rack B", "Bin 1", "General Liquids & Syrups"),
                    ("SHELF-B02", "Rack B", "Bin 2", "Secondary Shelf (Liquids - Later Expiry)"),
                    ("SHELF-COLD", "Cold Unit", "Fridge 1", "Cold Chain Storage (Insulin & Biologicals)"),
                    ("SHELF-QUAR", "Quarantine", "Bin Q", "Segregated Quarantine / Expired Stock")
                ]
                for code, rack, bin_c, desc in standard_shelves:
                    cursor.execute(
                        "INSERT OR IGNORE INTO storage_locations (store_id, shelf_code, rack, bin, description, is_active) VALUES (?, ?, ?, ?, ?, 1)",
                        (store_id, code, rack, bin_c, desc)
                    )

            conn.commit()

            created_user = User(
                user_id=user_id,
                username=clean_user,
                role="Owner",
                store_id=store_id,
                store_name=clean_store,
                full_name=clean_owner,
                email=clean_email
            )
            return True, f"Pharmacy store '{clean_store}' registered successfully! (Store ID: {store_id})", created_user
        except Exception as e:
            conn.rollback()
            return False, f"Registration failed due to database error: {str(e)}", None
        finally:
            conn.close()

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        store_id: Optional[str] = "STORE-LEGACY-001",
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        is_active: bool = True,
        acting_user: Optional[User] = None
    ) -> Tuple[bool, str]:
        """
        Creates a new user account with hashed password.
        Supports all 4 roles: Owner/Admin, Pharmacist, Cashier, and Inventory Manager.
        Enforces backend RBAC: requires PERM_MANAGE_USERS and store isolation if acting_user is provided.
        """
        clean_store = store_id or "STORE-LEGACY-001"

        # Backend Authorization Guards
        if acting_user is not None:
            require_permission(acting_user, PERM_MANAGE_USERS, "Creating user accounts")
            require_store_access(acting_user, clean_store, "Creating user accounts")

        if not username or not username.strip():
            return False, "Username is required."
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters long."

        canonical = normalize_role(role)
        if canonical not in ALL_ROLES:
            return False, f"Invalid role '{role}'. Must be one of: {', '.join(ALL_ROLES)}"

        # Use canonical role casing ('Owner', 'Admin', 'Pharmacist', 'Cashier', 'Inventory Manager')
        clean_role = canonical

        clean_user = username.strip()
        existing = self.db.fetch_one("SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)", (clean_user,))
        if existing:
            return False, f"Username '{clean_user}' already exists."

        clean_email = email.strip() if email else f"{clean_user}@pharmacy.local"
        clean_name = full_name.strip() if full_name else clean_user.capitalize()

        pwd_hash = hash_password(password)

        # Check if users table has is_active column
        user_cols = [c['name'] for c in self.db.fetch_all("PRAGMA table_info(users)")]
        if "is_active" in user_cols:
            query = """
            INSERT INTO users (username, password_hash, role, store_id, full_name, email, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params = (clean_user, pwd_hash, clean_role, clean_store, clean_name, clean_email, 1 if is_active else 0)
        else:
            query = """
            INSERT INTO users (username, password_hash, role, store_id, full_name, email)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            params = (clean_user, pwd_hash, clean_role, clean_store, clean_name, clean_email)

        try:
            self.db.execute(query, params)
            return True, f"User '{clean_user}' ({clean_role}) created successfully."
        except Exception as e:
            return False, f"Database error: {str(e)}"

    def get_store_users(self, store_id: str, acting_user: Optional[User] = None) -> List[User]:
        """
        Retrieves all user accounts for a given store.
        Guarded by store access and management permissions if acting_user is provided.
        """
        if acting_user is not None:
            require_permission(acting_user, PERM_MANAGE_USERS, "Viewing store users")
            require_store_access(acting_user, store_id, "Viewing store users")

        query = """
        SELECT u.*, s.store_name
        FROM users u
        LEFT JOIN stores s ON u.store_id = s.store_id
        WHERE u.store_id = ?
        ORDER BY u.user_id ASC
        """
        rows = self.db.fetch_all(query, (store_id,))
        return [User.from_row(r) for r in rows]

    def set_user_active_status(
        self,
        user_id: int,
        is_active: bool,
        acting_user: Optional[User] = None
    ) -> Tuple[bool, str]:
        """
        Activates or deactivates a user account.
        Enforces RBAC: requires PERM_MANAGE_USERS and prevents self-deactivation.
        """
        user_row = self.db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if not user_row:
            return False, "User not found."

        target_user = User.from_row(user_row)

        if acting_user is not None:
            require_permission(acting_user, PERM_MANAGE_USERS, "Modifying user status")
            require_store_access(acting_user, target_user.store_id, "Modifying user status")
            if acting_user.user_id == user_id and not is_active:
                return False, "You cannot deactivate your own account."

        user_cols = [c['name'] for c in self.db.fetch_all("PRAGMA table_info(users)")]
        if "is_active" not in user_cols:
            self.db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")

        self.db.execute("UPDATE users SET is_active = ? WHERE user_id = ?", (1 if is_active else 0, user_id))
        status_str = "activated" if is_active else "deactivated"
        return True, f"User '{target_user.username}' has been {status_str}."

    def reset_password(
        self,
        user_id: int,
        new_password: str,
        acting_user: Optional[User] = None
    ) -> Tuple[bool, str]:
        """
        Securely resets password for a user account.
        Enforces RBAC: requires PERM_MANAGE_USERS and store boundary matching.
        Hashes password with PBKDF2 salt. Never stores plaintext or logs hash.
        """
        if not new_password or len(new_password.strip()) < 6:
            return False, "Password must be at least 6 characters long."

        user_row = self.db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if not user_row:
            return False, "User not found."

        target_user = User.from_row(user_row)

        if acting_user is not None:
            require_permission(acting_user, PERM_MANAGE_USERS, "Resetting user password")
            require_store_access(acting_user, target_user.store_id, "Resetting user password")
            # Owners cannot have password reset by non-owners
            if target_user.canonical_role == ROLE_OWNER and acting_user.canonical_role != ROLE_OWNER:
                return False, "Only a Store Owner can reset an Owner's password."

        new_hash = hash_password(new_password.strip())
        self.db.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (new_hash, user_id))
        return True, f"Password for '{target_user.username}' has been successfully reset."

    def update_user_role(
        self,
        user_id: int,
        new_role: str,
        acting_user: Optional[User] = None
    ) -> Tuple[bool, str]:
        """
        Updates the role for a user account.
        Enforces RBAC: requires PERM_MANAGE_USERS.
        """
        user_row = self.db.fetch_one("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if not user_row:
            return False, "User not found."

        target_user = User.from_row(user_row)

        if acting_user is not None:
            require_permission(acting_user, PERM_MANAGE_USERS, "Updating user role")
            require_store_access(acting_user, target_user.store_id, "Updating user role")

        canonical = normalize_role(new_role)
        if canonical not in ALL_ROLES:
            return False, f"Invalid role '{new_role}'. Must be one of: {', '.join(ALL_ROLES)}"

        self.db.execute("UPDATE users SET role = ? WHERE user_id = ?", (canonical, user_id))
        return True, f"Role for '{target_user.username}' updated to '{canonical}'."

    def get_available_stores(self, include_test: bool = False) -> List[dict]:
        """
        Retrieves list of all registered pharmacy stores.
        Excludes QA test stores when include_test is False.
        Returns empty list if no stores exist (never returns a fake legacy store).
        """
        table_check = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='stores'")
        if not table_check:
            return []

        rows = self.db.fetch_all("SELECT store_id, store_name, owner_name FROM stores ORDER BY store_name ASC")
        if not rows:
            return []

        stores = [dict(r) for r in rows]
        if not include_test:
            stores = [
                s for s in stores
                if not s["store_id"].startswith("TEST-")
                and "[QA]" not in s["store_name"]
                and "[TEST]" not in s["store_name"]
                and s["store_id"] != "STORE-LEGACY-001"
            ]
        return stores

    def count_role_accounts(self, store_id: str, role: str) -> int:
        """Returns number of active accounts for a given role in a store."""
        if not store_id:
            return 0
        canonical = normalize_role(role)
        row = self.db.fetch_one(
            "SELECT COUNT(*) as cnt FROM users WHERE store_id = ? AND role = ? AND is_active = 1",
            (store_id, canonical)
        )
        return row["cnt"] if row else 0

    def get_roles_for_store(self, store_id: str) -> List[str]:
        """Returns distinct roles with active accounts in the store."""
        if not store_id:
            return []
        rows = self.db.fetch_all(
            "SELECT DISTINCT role FROM users WHERE store_id = ? AND is_active = 1",
            (store_id,)
        )
        return [r["role"] for r in rows]

    def authenticate_with_store_and_role(
        self,
        store_id: str,
        role: str,
        username: str,
        password: str
    ) -> Tuple[Optional[User], str]:
        """
        Authenticates a user against Store ID, Assigned Role, Username, and Password.
        Strictly verifies:
        - Store existence
        - Active account presence for selected role in store
        - User existence by username
        - Password hash verification (PBKDF2)
        - Store ID match (rejects cross-store login attempts)
        - Role match (rejects role mismatch attempts)
        - Active account status (rejects deactivated accounts)
        """
        if not store_id or not store_id.strip():
            return None, "Please select a registered pharmacy store."

        if not role or not role.strip():
            return None, "Please select an assigned role."

        if not username or not username.strip():
            return None, "Username cannot be empty."

        if not password or not password.strip():
            return None, "Password cannot be empty."

        clean_user = username.strip()
        canonical_role = normalize_role(role)

        # 1. Verify store exists
        store_row = self.db.fetch_one("SELECT store_id, store_name FROM stores WHERE store_id = ?", (store_id,))
        if not store_row:
            return None, "Selected pharmacy store does not exist."

        # 2. Check if this store has any account for the selected role
        role_count = self.count_role_accounts(store_id, canonical_role)
        if role_count == 0:
            return None, f"No active accounts found for role '{canonical_role}' in this store."

        # 3. Query the user account by username
        user_row = self.db.fetch_one(
            """
            SELECT u.*, s.store_name
            FROM users u
            LEFT JOIN stores s ON u.store_id = s.store_id
            WHERE LOWER(u.username) = LOWER(?)
            """,
            (clean_user,)
        )
        if not user_row:
            return None, "Invalid username or password."

        # 4. Verify password hash using PBKDF2
        if not verify_password(password, user_row["password_hash"]):
            return None, "Invalid username or password."

        # 5. Verify Store ID match
        user_store_id = user_row["store_id"]
        if str(user_store_id) != str(store_id):
            return None, f"User '{clean_user}' is not registered under store '{store_row['store_name']}'."

        # 6. Verify Role match
        user_actual_role = normalize_role(user_row["role"])
        if user_actual_role != canonical_role:
            return None, f"User '{clean_user}' does not have the '{canonical_role}' role (registered role is '{user_row['role']}')."

        # 7. Verify Active status
        keys = user_row.keys() if hasattr(user_row, "keys") else []
        if "is_active" in keys and user_row["is_active"] is not None and int(user_row["is_active"]) == 0:
            return None, f"Account '{clean_user}' is deactivated. Please contact store owner."

        # 8. All checks passed
        user = User.from_row(user_row)
        return user, "Login successful."

    def get_login_users(self, store_id: Optional[str] = None) -> List[dict]:
        """
        Retrieves sanitized user directory for the login user selection panel.
        Strictly strips password_hash and security tokens to prevent leakage.
        Filtered by store_id if provided.
        """
        table_check = self.db.fetch_one("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not table_check:
            return []

        user_cols = [c['name'] for c in self.db.fetch_all("PRAGMA table_info(users)")]
        store_expr = "u.store_id" if "store_id" in user_cols else "'STORE-LEGACY-001'"
        active_expr = "u.is_active" if "is_active" in user_cols else "1"
        fname_expr = "u.full_name" if "full_name" in user_cols else "''"
        email_expr = "u.email" if "email" in user_cols else "''"

        query = f"""
        SELECT u.user_id, u.username, u.role, {store_expr} as store_id,
               COALESCE(s.store_name, 'Default Pharmacy Store') as store_name,
               COALESCE({fname_expr}, '') as full_name,
               COALESCE({email_expr}, '') as email,
               COALESCE({active_expr}, 1) as is_active
        FROM users u
        LEFT JOIN stores s ON {store_expr} = s.store_id
        """
        params: List[object] = []
        if store_id and "store_id" in user_cols:
            query += f" WHERE ({store_expr} = ? OR {store_expr} IS NULL)"
            params.append(store_id)

        query += " ORDER BY u.user_id ASC"
        rows = self.db.fetch_all(query, tuple(params))

        sanitized = []
        for r in rows:
            sanitized.append({
                "user_id": r["user_id"],
                "username": r["username"],
                "full_name": r["full_name"] or r["username"].capitalize(),
                "role": r["role"],
                "canonical_role": normalize_role(r["role"]),
                "store_id": r["store_id"] or "STORE-LEGACY-001",
                "store_name": r["store_name"] or "Default Pharmacy Store",
                "is_active": bool(r["is_active"]),
                "email": r["email"]
            })
        return sanitized
