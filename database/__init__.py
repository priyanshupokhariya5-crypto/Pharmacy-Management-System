"""
Database module for Pharmacy Management System.
Handles SQLite connection, schema initialization, and B-Tree indexing.
"""
from .db import Database, get_db
from .schema import init_db

__all__ = ["Database", "get_db", "init_db"]
