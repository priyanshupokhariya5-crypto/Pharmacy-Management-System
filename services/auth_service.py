"""
Authentication service handling user login, store registration, and secure credentials verification.
Enforces multi-store tenancy, salted PBKDF2 password hashing, and unique username/email constraints.
"""
import re
import uuid
from typing import Optional, Tuple
from database.db import Database, get_db
from database.schema import hash_password, verify_password
from models.user import User


class AuthService:
    """Manages authentication and store registration operations."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_db()

    def authenticate(self, identity: str, password: str) -> Tuple[Optional[User], str]:
        """
        Authenticates a user by username OR email and password.
        Returns (User instance, message string). If failed, User is None.
        """
        if not identity or not identity.strip():
            return None, "Username or email cannot be empty."

        if not password or not password.strip():
            return None, "Password cannot be empty."

        clean_identity = identity.strip()
        query = """
        SELECT u.user_id, u.username, u.password_hash, u.role, u.store_id, u.full_name, u.email,
               s.store_name
        FROM users u
        LEFT JOIN stores s ON u.store_id = s.store_id
        WHERE LOWER(u.username) = LOWER(?) OR LOWER(u.email) = LOWER(?)
        """
        row = self.db.fetch_one(query, (clean_identity, clean_identity))

        if not row:
            return None, "Invalid username/email or password."

        if not verify_password(password, row["password_hash"]):
            return None, "Invalid username/email or password."

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
        full_name: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Creates a new user account with hashed password (for backwards compatibility / administrative use)."""
        if not username or not username.strip():
            return False, "Username is required."
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters long."
        if role not in ("Admin", "Pharmacist", "Owner"):
            return False, "Role must be 'Admin', 'Pharmacist', or 'Owner'."

        clean_user = username.strip()
        existing = self.db.fetch_one("SELECT user_id FROM users WHERE LOWER(username) = LOWER(?)", (clean_user,))
        if existing:
            return False, f"Username '{clean_user}' already exists."

        clean_store = store_id or "STORE-LEGACY-001"
        clean_email = email.strip() if email else f"{clean_user}@pharmacy.local"
        clean_name = full_name.strip() if full_name else clean_user.capitalize()

        pwd_hash = hash_password(password)
        query = """
        INSERT INTO users (username, password_hash, role, store_id, full_name, email)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        try:
            self.db.execute(query, (clean_user, pwd_hash, role, clean_store, clean_name, clean_email))
            return True, f"User '{clean_user}' created successfully."
        except Exception as e:
            return False, f"Database error: {str(e)}"
