"""
Regression test suite for UI navigation switching performance and view initialization.
Verifies idle pre-warming, tab switching across all views, and smart report refresh.
"""
import unittest
import customtkinter as ctk
from models.user import User
from ui.main_window import MainWindowContent
from ui.reports_view import ReportsView


class TestNavigationPerformance(unittest.TestCase):
    """Test suite validating fast navigation switching and pre-warming."""

    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()
        cls.user = User(1, "admin", "Admin")

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def test_navigation_switching_and_prewarm(self):
        win = MainWindowContent(self.root, self.user)
        # Drain prewarm queue to simulate background completion
        while win._prewarm_queue:
            win._prewarm_step()

        # Check all views exist
        self.assertIsNotNone(win.dashboard_view)
        self.assertIsNotNone(win.medicines_view)
        self.assertIsNotNone(win.search_view)
        self.assertIsNotNone(win.billing_view)
        self.assertIsNotNone(win.benchmark_view)
        self.assertIsNotNone(win.fmea_view)
        self.assertIsNotNone(win.sqc_view)
        self.assertIsNotNone(win.reports_view)

        # Test switching across all tabs
        for nav in ["Medicines", "Search", "Billing", "Reports", "Benchmark", "FMEA", "SQC", "Dashboard"]:
            win._on_nav_click(nav)
            self.assertEqual(win.current_nav, nav)

    def test_reports_smart_refresh(self):
        reports = ReportsView(self.root, self.user)
        initial_sig = reports._last_chart_sig
        self.assertIsNotNone(initial_sig)

        # Second refresh with same data should preserve _last_chart_sig and skip redraw
        reports.refresh_reports(force_charts=False)
        self.assertEqual(reports._last_chart_sig, initial_sig)


if __name__ == "__main__":
    unittest.main()
