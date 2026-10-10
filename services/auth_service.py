"""
Authentication service handling user login, registration, and password hashing.
"""
from typing import Optional, Tuple
from database.db import Database, get_db
from database.schema import hash_password
from models.user import User


class AuthService:
    """Manages authentication operations against the users database table."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_db()

    def authenticate(self, username: str, password: str) -> Tuple[Optional[User], str]:
        """
        Authenticates username and password against database records.
        Returns (User instance, message string). If failed, User is None.
        """
        if not username or not username.strip():
            return None, "Username cannot be empty."

        if not password or not password.strip():
            return None, "Password cannot be empty."

        query = "SELECT user_id, username, password_hash, role FROM users WHERE username = ?"
        row = self.db.fetch_one(query, (username.strip(),))

        if not row:
            return None, "Invalid username or password."

        input_hash = hash_password(password)
        if row["password_hash"] != input_hash:
            return None, "Invalid username or password."

        user = User.from_row(row)
        return user, "Login successful."

    def create_user(self, username: str, password: str, role: str) -> Tuple[bool, str]:
        """Creates a new user account with hashed password."""
        if not username or not username.strip():
            return False, "Username is required."
        if not password or len(password) < 4:
            return False, "Password must be at least 4 characters long."
        if role not in ("Admin", "Pharmacist"):
            return False, "Role must be 'Admin' or 'Pharmacist'."

        existing = self.db.fetch_one("SELECT user_id FROM users WHERE username = ?", (username.strip(),))
        if existing:
            return False, f"Username '{username}' already exists."

        pwd_hash = hash_password(password)
        query = "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)"
        try:
            self.db.execute(query, (username.strip(), pwd_hash, role))
            return True, f"User '{username}' created successfully."
        except Exception as e:
            return False, f"Database error: {str(e)}"
