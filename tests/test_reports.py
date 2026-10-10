"""
Stage 6 Unit Tests for Inventory & Sales Analytical Reports & Pandas Aggregations.
Tests DataFrames, stock totals, value calculations, low stock, out of stock, expiry reports,
sales history, category groupbys, empty states, and live sale update consistency.
"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta
import pandas as pd

from database.db import Database
from database.schema import init_db
from reports.report_generator import ReportGenerator
from services.medicine_service import MedicineService
from services.sales_service import SalesService
from models.medicine import Medicine


class TestAnalyticalReports(unittest.TestCase):
    """Test suite for ReportGenerator, Pandas DataFrames, and live DB data consistency."""

    def setUp(self):
        """Creates an isolated temporary database for test execution."""
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.temp_db_fd)

        self.db = init_db(self.temp_db_path)
        self.report_gen = ReportGenerator(self.db)
        self.med_service = MedicineService(self.db)
        self.sales_service = SalesService(self.db)

    def tearDown(self):
        """Cleans up temporary database file."""
        if os.path.exists(self.temp_db_path):
            try:
                os.remove(self.temp_db_path)
            except PermissionError:
                pass

    def test_1_inventory_dataframe_generation(self):
        """Verifies generation of Pandas DataFrame for full inventory."""
        df = self.report_gen.get_inventory_dataframe()
        self.assertIsInstance(df, pd.DataFrame)
        self.assertFalse(df.empty)
        self.assertIn("total_value", df.columns)
        self.assertIn("medicine_code", df.columns)

    def test_2_total_medicine_count(self):
        """Verifies medicine count from inventory DataFrame."""
        df = self.report_gen.get_inventory_dataframe()
        self.assertEqual(len(df), 16)  # 16 seed medicines

    def test_3_total_stock_calculation(self):
        """Verifies sum of stock quantity calculation."""
        df = self.report_gen.get_inventory_dataframe()
        total_qty = df["quantity"].sum()
        self.assertEqual(total_qty, 926)

    def test_4_inventory_value_calculation(self):
        """Verifies calculation of total inventory value (quantity * price)."""
        df = self.report_gen.get_inventory_dataframe()
        computed_val = round(df["total_value"].sum(), 2)
        self.assertEqual(computed_val, 40619.00)

    def test_5_low_stock_report(self):
        """Verifies low stock report DataFrame filtering (0 < quantity <= 10)."""
        df_low = self.report_gen.get_low_stock_dataframe()
        self.assertFalse(df_low.empty)
        self.assertEqual(len(df_low), 3)
        for qty in df_low["quantity"]:
            self.assertTrue(0 < qty <= 10)

    def test_6_out_of_stock_report(self):
        """Verifies out-of-stock report DataFrame filtering (quantity == 0)."""
        df_out = self.report_gen.get_out_of_stock_dataframe()
        self.assertFalse(df_out.empty)
        self.assertEqual(len(df_out), 2)
        for qty in df_out["quantity"]:
            self.assertEqual(qty, 0)

    def test_7_expiry_classification_report(self):
        """Verifies expiry status classification column in Pandas DataFrame."""
        df_exp = self.report_gen.get_expiry_report_dataframe()
        self.assertIn("expiry_status", df_exp.columns)
        statuses = set(df_exp["expiry_status"].unique())
        self.assertIn("Expired", statuses)
        self.assertIn("Valid", statuses)

    def test_8_sales_history_retrieval(self):
        """Verifies sales history DataFrame structure."""
        # Initial empty state check
        df_sales = self.report_gen.get_sales_history_dataframe()
        self.assertIsInstance(df_sales, pd.DataFrame)

    def test_9_total_sales_calculation(self):
        """Verifies calculation of total sales revenue in ₹."""
        # Perform a sale
        med = self.med_service.get_medicine_by_code("MED1001") # Price: 15.50
        self.sales_service.process_sale(1, [(med.medicine_id, 2)], 'Test Patient')

        metrics = self.report_gen.get_sales_summary_metrics()
        self.assertEqual(metrics["total_sales_value"], 31.00)

    def test_10_total_items_sold(self):
        """Verifies total items sold units count."""
        med1 = self.med_service.get_medicine_by_code("MED1001")
        med2 = self.med_service.get_medicine_by_code("MED1002")
        self.sales_service.process_sale(1, [(med1.medicine_id, 2), (med2.medicine_id, 3)], 'Test Patient')

        metrics = self.report_gen.get_sales_summary_metrics()
        self.assertEqual(metrics["total_items_sold"], 5)

    def test_11_average_sale_calculation(self):
        """Verifies average transaction sale value computation."""
        med1 = self.med_service.get_medicine_by_code("MED1001") # 15.50 * 2 = 31.00
        med2 = self.med_service.get_medicine_by_code("MED1002") # 22.00 * 1 = 22.00
        self.sales_service.process_sale(1, [(med1.medicine_id, 2)], 'Test Patient')
        self.sales_service.process_sale(1, [(med2.medicine_id, 1)], 'Test Patient')

        metrics = self.report_gen.get_sales_summary_metrics()
        self.assertEqual(metrics["total_transactions"], 2)
        expected_avg = round((31.00 + 22.00) / 2, 2)
        self.assertEqual(metrics["avg_sale_value"], expected_avg)

    def test_12_category_wise_stock_aggregation(self):
        """Verifies Pandas category groupby aggregation DataFrame."""
        df_cat = self.report_gen.get_category_analysis_dataframe()
        self.assertFalse(df_cat.empty)
        self.assertIn("category", df_cat.columns)
        self.assertIn("total_quantity", df_cat.columns)
        self.assertIn("total_inventory_value", df_cat.columns)

    def test_13_stock_status_aggregation(self):
        """Verifies calculation of stock status counts for Matplotlib figure."""
        fig = self.report_gen.generate_stock_status_chart()
        self.assertIsNotNone(fig)

    def test_14_empty_sales_state(self):
        """Verifies graceful handling when zero sales exist in database."""
        metrics = self.report_gen.get_sales_summary_metrics()
        self.assertEqual(metrics["total_transactions"], 0)
        self.assertEqual(metrics["total_sales_value"], 0.0)

    def test_15_live_data_consistency_sale_impact(self):
        """
        CRITICAL TEST: Proves live data consistency between checkout and reports.
        1. Adds a medicine with stock = 10.
        2. Verifies report generator shows quantity = 10.
        3. Performs a sale of 2 units.
        4. Re-queries report generator.
        5. Proves quantity decreases to 8 and sales history records the new sale!
        """
        exp_date = (datetime.now() + timedelta(days=180)).strftime("%Y-%m-%d")
        med = Medicine(
            medicine_id=None,
            medicine_code="MED_TEST_REP",
            medicine_name="Report Consistency Med",
            category="Testing",
            manufacturer="Report Lab",
            batch_no="B_REP",
            price=20.00,
            quantity=10,
            expiry_date=exp_date
        )
        self.med_service.add_medicine(med)
        inserted = self.med_service.get_medicine_by_code("MED_TEST_REP")

        # 1. Initial report check
        df_init = self.report_gen.get_inventory_dataframe()
        row_init = df_init[df_init["medicine_code"] == "MED_TEST_REP"].iloc[0]
        self.assertEqual(row_init["quantity"], 10)

        # 2. Perform sale of 2 units
        ok, msg, sale_id, inv = self.sales_service.process_sale(1, [(inserted.medicine_id, 2)], 'Test Patient')
        self.assertTrue(ok)

        # 3. Re-query report generator to verify live update
        df_after = self.report_gen.get_inventory_dataframe()
        row_after = df_after[df_after["medicine_code"] == "MED_TEST_REP"].iloc[0]
        self.assertEqual(row_after["quantity"], 8, "Report stock did not decrease live after sale!")

        # 4. Verify sales history updated live
        df_sales = self.report_gen.get_sales_history_dataframe()
        self.assertFalse(df_sales.empty)
        self.assertIn(sale_id, df_sales["sale_id"].values)


if __name__ == "__main__":
    unittest.main()
