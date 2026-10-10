"""
Search Service for Q13 - Faster Search & Retrieval.
Implements optimized multi-filter queries, dynamic whitelisted sorting, partial text search,
and query execution time benchmarking hooks.
"""
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from database.db import Database, get_db
from models.medicine import Medicine, LOW_STOCK_THRESHOLD, EXPIRING_SOON_DAYS


class SearchService:
    """Provides high-performance search and retrieval operations across inventory records."""

    # Whitelist of allowed column names for SQL ORDER BY clause (Security & Injection Defense)
    ALLOWED_SORT_FIELDS = {
        "medicine_name": "medicine_name",
        "price": "price",
        "quantity": "quantity",
        "expiry_date": "expiry_date",
        "medicine_code": "medicine_code",
        "category": "category",
        "manufacturer": "manufacturer"
    }

    ALLOWED_SORT_ORDERS = {"ASC", "DESC"}

    # Map preset sort choice names to SQL ORDER BY clauses
    SORT_OPTIONS = {
        "Name A-Z": "medicine_name ASC",
        "Name Z-A": "medicine_name DESC",
        "Price Low-High": "price ASC",
        "Price High-Low": "price DESC",
        "Quantity Low-High": "quantity ASC",
        "Quantity High-Low": "quantity DESC",
        "Expiry Nearest": "expiry_date ASC",
        "Expiry Latest": "expiry_date DESC"
    }

    def __init__(self, db: Optional[Database] = None):
        self.db = db or get_db()

    def search_medicines(
        self,
        query_text: Optional[str] = None,
        category: Optional[str] = None,
        manufacturer: Optional[str] = None,
        stock_status: Optional[str] = None,   # 'All', 'Available', 'Low Stock', 'Out of Stock'
        price_min: Optional[float] = None,
        price_max: Optional[float] = None,
        expiry_status: Optional[str] = None,  # 'All', 'Valid', 'Expiring Soon', 'Expired'
        sort_by: Optional[str] = "Name A-Z",
        sort_field: Optional[str] = None,
        sort_order: Optional[str] = "ASC",
        limit: int = 200
    ) -> Tuple[List[Medicine], float]:
        """
        Executes a dynamic, parameterized search with filters and whitelisted sorting.
        Returns a tuple of (List[Medicine], execution_time_ms).
        """
        start_time = time.perf_counter()

        # Explicit column projection instead of SELECT *
        sql_base = """
        SELECT medicine_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines
        """

        where_clauses: List[str] = []
        params: List[Any] = []

        # 1. Text Search (Partial match across name, code, batch_no, manufacturer)
        if query_text and query_text.strip():
            clean_text = f"%{query_text.strip()}%"
            where_clauses.append(
                "(medicine_name LIKE ? OR medicine_code LIKE ? OR batch_no LIKE ? OR manufacturer LIKE ? OR category LIKE ?)"
            )
            params.extend([clean_text, clean_text, clean_text, clean_text, clean_text])

        # 2. Category Filter
        if category and category.strip() and category != "All":
            where_clauses.append("category = ?")
            params.append(category.strip())

        # 3. Manufacturer Filter
        if manufacturer and manufacturer.strip() and manufacturer != "All":
            where_clauses.append("manufacturer = ?")
            params.append(manufacturer.strip())

        # 4. Stock Status Filter
        if stock_status and stock_status != "All":
            if stock_status == "Available":
                where_clauses.append("quantity > 10")
            elif stock_status == "Low Stock":
                where_clauses.append("quantity > 0 AND quantity <= ?")
                params.append(LOW_STOCK_THRESHOLD)
            elif stock_status == "Out of Stock":
                where_clauses.append("quantity = 0")

        # 5. Price Minimum
        if price_min is not None and price_min >= 0:
            where_clauses.append("price >= ?")
            params.append(price_min)

        # 6. Price Maximum
        if price_max is not None and price_max >= 0:
            where_clauses.append("price <= ?")
            params.append(price_max)

        # 7. Expiry Status Filter
        if expiry_status and expiry_status != "All":
            today_str = datetime.now().strftime("%Y-%m-%d")
            expiring_threshold = (datetime.now() + timedelta(days=EXPIRING_SOON_DAYS)).strftime("%Y-%m-%d")

            if expiry_status == "Valid":
                where_clauses.append("expiry_date > ?")
                params.append(expiring_threshold)
            elif expiry_status == "Expiring Soon":
                where_clauses.append("expiry_date >= ? AND expiry_date <= ?")
                params.extend([today_str, expiring_threshold])
            elif expiry_status == "Expired":
                where_clauses.append("expiry_date < ?")
                params.append(today_str)

        # Assemble WHERE clause
        if where_clauses:
            sql_base += " WHERE " + " AND ".join(where_clauses)

        # Determine Whitelisted Sorting Clause
        order_clause = "medicine_name ASC"
        if sort_field:
            clean_field = self.ALLOWED_SORT_FIELDS.get(sort_field.lower().strip(), "medicine_name")
            clean_order = sort_order.upper().strip() if sort_order and sort_order.upper().strip() in self.ALLOWED_SORT_ORDERS else "ASC"
            order_clause = f"{clean_field} {clean_order}"
        elif sort_by in self.SORT_OPTIONS:
            order_clause = self.SORT_OPTIONS[sort_by]

        sql_base += f" ORDER BY {order_clause}"

        # Apply Limit
        if limit > 0:
            sql_base += " LIMIT ?"
            params.append(limit)

        # Execute query
        rows = self.db.fetch_all(sql_base, params)
        medicines = [Medicine.from_row(r) for r in rows]

        execution_time_ms = (time.perf_counter() - start_time) * 1000.0
        return medicines, round(execution_time_ms, 3)

    def quick_search(self, keyword: str, limit: int = 8) -> List[Medicine]:
        """
        Dashboard quick search helper for instant auto-complete popups.
        Optimized for sub-millisecond response on typed input.
        """
        if not keyword or not keyword.strip():
            return []

        search_pattern = f"%{keyword.strip()}%"
        query = """
        SELECT medicine_id, medicine_code, medicine_name, category, manufacturer,
               batch_no, price, quantity, expiry_date, created_at, updated_at
        FROM medicines
        WHERE medicine_name LIKE ? OR medicine_code LIKE ? OR category LIKE ? OR manufacturer LIKE ?
        ORDER BY medicine_name ASC
        LIMIT ?
        """
        rows = self.db.fetch_all(query, (search_pattern, search_pattern, search_pattern, search_pattern, limit))
        return [Medicine.from_row(r) for r in rows]
