"""
Stage 4 Unit Tests for Q13 Advanced Search & Retrieval Engine.
Tests partial text matching, multi-criteria filtering, price bounds, expiry status,
whitelisted SQL sorting, and parameterized query security.
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from database.db import Database
from database.schema import init_db
from services.search_service import SearchService


class TestAdvancedSearchEngine(unittest.TestCase):
    """Test suite for Q13 Search Service multi-filter engine and security whitelists."""

    def setUp(self):
        """Creates an isolated temporary database for test execution."""
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)

        self.db = init_db(self.temp_db_path)
        self.search_service = SearchService(self.db)

    def tearDown(self):
        """Cleans up temporary database file."""
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except PermissionError:
                pass

    def test_1_search_by_medicine_name(self):
        """Verifies exact/case-insensitive medicine name search."""
        results, latency = self.search_service.search_medicines(query_text="Paracetamol 500mg")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0].medicine_name, "Paracetamol 500mg")

    def test_2_search_by_partial_medicine_name(self):
        """Verifies partial text substring matching (e.g. 'para', 'amox')."""
        results_para, _ = self.search_service.search_medicines(query_text="para")
        self.assertGreaterEqual(len(results_para), 2)
        for m in results_para:
            self.assertIn("paracetamol", m.medicine_name.lower())

        results_amox, _ = self.search_service.search_medicines(query_text="amox")
        self.assertGreaterEqual(len(results_amox), 2)
        for m in results_amox:
            self.assertIn("amoxicillin", m.medicine_name.lower())

    def test_3_search_by_medicine_code(self):
        """Verifies search by unique medicine code."""
        results, _ = self.search_service.search_medicines(query_text="MED1001")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].medicine_code, "MED1001")

    def test_4_search_by_category(self):
        """Verifies category filtering."""
        results, _ = self.search_service.search_medicines(category="Antibiotic")
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertEqual(m.category, "Antibiotic")

    def test_5_search_by_manufacturer(self):
        """Verifies manufacturer filtering."""
        results, _ = self.search_service.search_medicines(manufacturer="Cipla Ltd")
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertEqual(m.manufacturer, "Cipla Ltd")

    def test_6_filter_by_available_stock(self):
        """Verifies stock status filtering for Available items (quantity > 10)."""
        results, _ = self.search_service.search_medicines(stock_status="Available")
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertGreater(m.quantity, 10)

    def test_7_filter_by_low_stock(self):
        """Verifies stock status filtering for Low Stock items (0 < quantity <= 10)."""
        results, _ = self.search_service.search_medicines(stock_status="Low Stock")
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertTrue(0 < m.quantity <= 10)

    def test_8_filter_by_out_of_stock(self):
        """Verifies stock status filtering for Out of Stock items (quantity == 0)."""
        results, _ = self.search_service.search_medicines(stock_status="Out of Stock")
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertEqual(m.quantity, 0)

    def test_9_filter_by_minimum_price(self):
        """Verifies minimum price filtering (price >= 50.0)."""
        results, _ = self.search_service.search_medicines(price_min=50.0)
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertGreaterEqual(m.price, 50.0)

    def test_10_filter_by_maximum_price(self):
        """Verifies maximum price filtering (price <= 20.0)."""
        results, _ = self.search_service.search_medicines(price_max=20.0)
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertLessEqual(m.price, 20.0)

    def test_11_filter_by_price_range(self):
        """Verifies price range filtering (15.0 <= price <= 50.0)."""
        results, _ = self.search_service.search_medicines(price_min=15.0, price_max=50.0)
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertTrue(15.0 <= m.price <= 50.0)

    def test_12_filter_by_expiry_status(self):
        """Verifies expiry status filtering (Expired, Expiring Soon, Valid)."""
        results_exp, _ = self.search_service.search_medicines(expiry_status="Expired")
        self.assertGreater(len(results_exp), 0)
        for m in results_exp:
            self.assertTrue(m.is_expired)

        results_soon, _ = self.search_service.search_medicines(expiry_status="Expiring Soon")
        self.assertGreater(len(results_soon), 0)
        for m in results_soon:
            self.assertTrue(m.is_expiring_soon)

    def test_13_combined_filters(self):
        """Verifies multi-condition combined filtering (Text + Category + Stock + Price)."""
        results, _ = self.search_service.search_medicines(
            query_text="para",
            category="Analgesic",
            stock_status="Available",
            price_min=10.0,
            price_max=30.0
        )
        self.assertGreater(len(results), 0)
        for m in results:
            self.assertIn("para", m.medicine_name.lower())
            self.assertEqual(m.category, "Analgesic")
            self.assertGreater(m.quantity, 10)
            self.assertTrue(10.0 <= m.price <= 30.0)

    def test_14_sort_ascending(self):
        """Verifies whitelisted sorting in Ascending order (price ASC)."""
        results, _ = self.search_service.search_medicines(sort_field="price", sort_order="ASC")
        prices = [m.price for m in results]
        self.assertEqual(prices, sorted(prices))

    def test_15_sort_descending(self):
        """Verifies whitelisted sorting in Descending order (price DESC)."""
        results, _ = self.search_service.search_medicines(sort_field="price", sort_order="DESC")
        prices = [m.price for m in results]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_16_empty_result(self):
        """Verifies query returning zero results when no records match."""
        results, _ = self.search_service.search_medicines(query_text="NonExistentMedicine9999")
        self.assertEqual(len(results), 0)

    def test_17_parameterized_search(self):
        """Verifies parameterized SQL query defense against SQL injection attempts."""
        injection_str = "' OR '1'='1"
        results, _ = self.search_service.search_medicines(query_text=injection_str)
        self.assertEqual(len(results), 0)

    def test_18_invalid_price_range_handling(self):
        """Verifies price bounds logic when min_price > max_price."""
        # Querying min_price 100 and max_price 10 should return 0 rows gracefully
        results, _ = self.search_service.search_medicines(price_min=100.0, price_max=10.0)
        self.assertEqual(len(results), 0)

    def test_19_allowed_sort_field_whitelist(self):
        """Verifies security whitelist for sort columns (falls back to medicine_name if invalid)."""
        # Passing invalid sort field 'secret_column; DROP TABLE users;'
        results, _ = self.search_service.search_medicines(sort_field="secret_column; DROP TABLE users;")
        self.assertGreater(len(results), 0)
        # Should not throw exception and should return sorted records safely
        names = [m.medicine_name for m in results]
        self.assertEqual(names, sorted(names))


if __name__ == "__main__":
    unittest.main()
