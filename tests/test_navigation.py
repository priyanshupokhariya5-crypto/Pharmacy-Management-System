"""
Regression test suite for UI navigation switching performance and view initialization.
Verifies idle pre-warming, tab switching across all views, and smart report refresh.
"""
import os
import tempfile
import unittest
import customtkinter as ctk
import database.db as db_module
from database.schema import init_db, migrate_database
from models.user import User
from ui.main_window import MainWindowContent
from ui.reports_view import ReportsView


class TestNavigationPerformance(unittest.TestCase):
    """Test suite validating fast navigation switching and pre-warming."""

    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()
        cls.temp_db_fd, cls.temp_db_path = tempfile.mkstemp(suffix="_test_nav.db")
        os.close(cls.temp_db_fd)
        cls.db = init_db(cls.temp_db_path)
        migrate_database(cls.db)
        cls.user = User(1, "admin", "Admin", store_id="STORE-NAV-001")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass
        db_module._db_instance = None
        if hasattr(cls, "temp_db_path") and os.path.exists(cls.temp_db_path):
            try:
                os.remove(cls.temp_db_path)
            except Exception:
                pass

    def test_navigation_switching_and_prewarm(self):
        import ui.main_window as mw
        orig = mw.ENABLE_REVIEW3_4_FEATURES
        mw.ENABLE_REVIEW3_4_FEATURES = True
        try:
            self._run_prewarm_test()
        finally:
            mw.ENABLE_REVIEW3_4_FEATURES = orig

    def _run_prewarm_test(self):
        win = MainWindowContent(self.root, self.user)
        # Drain prewarm queue to simulate background completion
        while win._prewarm_queue:
            win._prewarm_step()

        # Check all views exist
        self.assertIsNotNone(win.dashboard_view)
        self.assertIsNotNone(win.medicines_view)
        self.assertIsNotNone(win.batches_view)
        self.assertIsNotNone(win.purchases_view)
        self.assertIsNotNone(win.suppliers_view)
        self.assertIsNotNone(win.search_view)
        self.assertIsNotNone(win.billing_view)
        self.assertFalse(hasattr(win, "benchmark_view") and win.benchmark_view is not None)
        self.assertIsNotNone(win.fmea_view)
        self.assertIsNotNone(win.sqc_view)
        self.assertIsNotNone(win.reports_view)

        # Test switching across all tabs
        for nav in ["Medicines", "Batches", "Purchases", "Suppliers", "Search", "Billing", "Reports", "FMEA", "SQC", "Dashboard"]:
            win._on_nav_click(nav)
            self.assertEqual(win.current_nav, nav)

    def test_navigation_review1_and_2_restricted_mode(self):
        """Verifies that Review 3 (FMEA), Review 4 (SQC), and removed Benchmark are not present."""
        import ui.main_window as mw
        orig = mw.ENABLE_REVIEW3_4_FEATURES
        try:
            mw.ENABLE_REVIEW3_4_FEATURES = False
            win = MainWindowContent(self.root, self.user)
            self.assertNotIn("FMEA", win.allowed_nav_keys)
            self.assertNotIn("SQC", win.allowed_nav_keys)
            self.assertNotIn("Benchmark", win.allowed_nav_keys)
            self.assertNotIn("FMEA", win.nav_buttons)
            self.assertNotIn("SQC", win.nav_buttons)
            self.assertNotIn("Benchmark", win.nav_buttons)

            # Clicking hidden/removed nav should fallback safely to Dashboard
            win._on_nav_click("FMEA")
            self.assertEqual(win.current_nav, "Dashboard")
            win._on_nav_click("SQC")
            self.assertEqual(win.current_nav, "Dashboard")
            win._on_nav_click("Benchmark")
            self.assertEqual(win.current_nav, "Dashboard")

            # Retained Review 1 & 2 features must be present
            for key in ["Dashboard", "Medicines", "Batches", "Purchases", "Suppliers", "Search", "Billing", "Staff", "Reports"]:
                self.assertIn(key, win.allowed_nav_keys)
        finally:
            mw.ENABLE_REVIEW3_4_FEATURES = orig

    def test_reports_smart_refresh(self):
        reports = ReportsView(self.root, self.user)
        initial_sig = reports._last_chart_sig
        self.assertIsNotNone(initial_sig)

        # Second refresh with same data should preserve _last_chart_sig and skip redraw
        reports.refresh_reports(force_charts=False)
        self.assertEqual(reports._last_chart_sig, initial_sig)


if __name__ == "__main__":
    unittest.main()
