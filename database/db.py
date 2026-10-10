"""
Database connection manager for SQLite3.
Provides thread-safe connections, foreign key enforcement, parameterized query execution,
and transaction context management.
"""
import os
import sqlite3
from typing import Any, List, Optional, Tuple, Dict, Union

# Default DB Path relative to project root
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "pharmacy.db"
)


class Database:
    """SQLite Database manager providing robust connection handling and helper methods."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensures that the target directory for the SQLite database file exists."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """
        Creates and returns a new sqlite3 connection with Row factory enabled
        and foreign key constraints enforced.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def execute(self, query: str, params: Union[Tuple[Any, ...], List[Any], Dict[str, Any]] = ()) -> int:
        """
        Executes a write/update query using parameterized inputs and commits changes.
        Returns the last inserted row id.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid or 0

    def execute_script(self, script: str) -> None:
        """Executes a multi-statement SQL DDL script."""
        with self.get_connection() as conn:
            conn.executescript(script)
            conn.commit()

    def fetch_all(self, query: str, params: Union[Tuple[Any, ...], List[Any], Dict[str, Any]] = ()) -> List[sqlite3.Row]:
        """Executes a SELECT query with parameters and returns all resulting rows."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def fetch_one(self, query: str, params: Union[Tuple[Any, ...], List[Any], Dict[str, Any]] = ()) -> Optional[sqlite3.Row]:
        """Executes a SELECT query with parameters and returns a single row or None."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchone()

    def execute_transaction(self, queries_and_params: List[Tuple[str, Union[Tuple[Any, ...], List[Any]]]]) -> bool:
        """
        Executes multiple queries within a single transaction block.
        Rolls back changes if any query fails.
        """
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            for query, params in queries_and_params:
                cursor.execute(query, params)
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()


# Singleton instance helper
_db_instance: Optional[Database] = None


def get_db(db_path: Optional[str] = None) -> Database:
    """Returns a Database manager instance."""
    global _db_instance
    if db_path or _db_instance is None:
        _db_instance = Database(db_path)
    return _db_instance
