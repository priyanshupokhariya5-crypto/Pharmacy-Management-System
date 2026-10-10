import unittest
import os
import tempfile
from services.sales_service import SalesService
from database.db import Database
from database.schema import init_db
from utils.pdf_generator import generate_invoice_pdf

class TestInvoices(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.db = init_db(self.db_path)
        self.sales_service = SalesService(self.db)
        
    def tearDown(self):
        try:
            self.db.get_connection().close()
        except:
            pass
        try:
            os.remove(self.db_path)
        except:
            pass

    def test_pdf_generation_new_sale(self):
        success, msg, sale_id, inv_num = self.sales_service.process_sale(1, [(1, 2)], "Test Patient PDF", "9999999999", 40)
        self.assertTrue(success)
        self.assertIsNotNone(sale_id)
        self.assertIsNotNone(inv_num)
        
        details = self.sales_service.get_sale_details(sale_id)
        self.assertEqual(details['patient_name'], "Test Patient PDF")
        
        pdf_path = os.path.join(tempfile.gettempdir(), f"Test_Invoice_{inv_num}.pdf")
        if os.path.exists(pdf_path): os.remove(pdf_path)
            
        res = generate_invoice_pdf(details, pdf_path)
        self.assertTrue(res)
        self.assertTrue(os.path.exists(pdf_path))
        self.assertGreater(os.path.getsize(pdf_path), 1000)
        os.remove(pdf_path)

    def test_legacy_invoice_retrieval(self):
        self.db.execute("INSERT INTO sales (sale_date, total_amount, user_id) VALUES ('2023-01-01 10:00:00', 500.0, 1)")
        legacy_sale_id = self.db.fetch_one("SELECT MAX(sale_id) as id FROM sales")['id']
        
        legacy_inv = f"INV-LEGACY-{legacy_sale_id:06d}"
        self.db.execute("UPDATE sales SET invoice_number = ?, patient_name = 'Walk-in Patient' WHERE sale_id = ?", (legacy_inv, legacy_sale_id))
        
        details2 = self.sales_service.get_sale_details(legacy_sale_id)
        self.assertIsNotNone(details2)
        self.assertEqual(details2['patient_name'], 'Walk-in Patient')
        self.assertEqual(details2['invoice_number'], legacy_inv)
        
        pdf_path = os.path.join(tempfile.gettempdir(), f"Test_Invoice_Legacy_{legacy_sale_id}.pdf")
        res = generate_invoice_pdf(details2, pdf_path)
        self.assertTrue(res)
        self.assertTrue(os.path.exists(pdf_path))
        os.remove(pdf_path)

if __name__ == '__main__':
    unittest.main()
