# Pharmacy Management System - User Manual

## 1. Installation
1. Ensure Python 3.x is installed on your system.
2. Clone or download the repository.
3. Open a terminal in the project directory and run: `pip install -r requirements.txt`.

## 2. Login
1. Run the application using `python main.py`.
2. The login screen will appear.
3. Enter your credentials. For demonstration:
   - **Admin:** `admin` / `admin123`
   - **Pharmacist:** `pharmacist` / `pharma123`
4. Click "Login" to access the system.

## 3. Dashboard
The Dashboard is the central hub displaying:
- Total Medicines in stock.
- Low Stock Alerts (medicines with quantity <= 10).
- Out of Stock Alerts (medicines with quantity 0).
- A quick search bar for immediate inventory lookup.

## 4. Medicine Inventory
Navigate to the "Medicines" tab on the left sidebar to manage stock.
- **Add:** Click "Add Medicine", fill in the details, and save.
- **Update:** Select a medicine from the list, modify details, and click "Update".
- **Delete:** Select a medicine and click "Delete" (Admin only).

## 5. Search & Filters
In the Medicine Inventory tab, use the search bar to find medicines by name or code.
- Use the **Category** dropdown to filter by specific medicine categories.
- Use the **Manufacturer** dropdown to filter by specific manufacturers.
- Click "Clear" to reset all filters.

## 6. Sorting
Click on any column header in the Medicine Inventory table (e.g., Price, Quantity, Expiry Date) to sort the data in ascending or descending order.

## 7. Quick Search
From the main Dashboard, use the Quick Search bar. Type a partial medicine name, code, category, or manufacturer. The system will auto-suggest matching entries and allow you to quickly transition to the inventory view.

## 8. Billing
Navigate to the "Sales / Billing" tab.
1. Enter the mandatory **Patient Name**. Age and Phone are optional.
2. Search for a medicine in the cart search bar.
3. Enter the quantity and click "Add to Cart".
4. Review the cart items and total amount.
5. Click "Complete Sale" to process the transaction.

## 9. Invoice
Upon completing a sale, an Invoice Receipt modal will automatically appear, displaying the unique Invoice Number, Patient details, and a breakdown of purchased items.

## 10. PDF Download
In the Invoice Receipt modal, click the "Download PDF" button to save a digital copy of the invoice to your local disk.

## 11. Printing
In the Invoice Receipt modal, click the "Print" button to open the standard system print dialog and print a physical receipt.

## 12. Billing History
Navigate to the "Reports & Analytics" tab and scroll down to the **Complete Sales Transaction History** table. This displays a chronological list of all processed bills.

## 13. Reports
The "Reports & Analytics" tab provides:
- Visual charts (Pie charts for category distribution, Bar charts for sales).
- Expiry Alerts (medicines expiring within 30 days).
- Inventory Summaries.

## 14. Benchmark
Navigate to the "Benchmark" tab (Admin only). Click "Run Benchmark" to execute performance tests on database search queries and view the average response latency in milliseconds.

## 15. FMEA
Failure Mode and Effects Analysis (FMEA) is accessible via the "FMEA Risk Audit" tab. 
- Log potential failure modes in pharmacy operations.
- The system automatically calculates the Risk Priority Number (RPN) based on Severity, Occurrence, and Detection.

## 16. SQC
Statistical Quality Control (SQC) is accessible via the "SQC Quality Tracking" tab.
- Log operational defects or quality issues.
- View real-time defect frequency data.

## 17. Pareto
In the SQC tab, the Pareto Chart automatically renders to show the 80/20 rule, highlighting the most frequent defects contributing to quality issues.

## 18. Fishbone
The SQC tab includes a digital Fishbone (Ishikawa) diagram to help identify root causes of specific defects across categories like Methods, Machines, Materials, and People.

## 19. PDCA
The Plan-Do-Check-Act (PDCA) Kaizen tracker allows you to log continuous improvement cycles and monitor their current status (Plan, Do, Check, or Act).

## 20. Logout / Exit
To safely exit the application, click the "Logout" button at the bottom of the left sidebar. This securely ends your session and returns you to the login screen.