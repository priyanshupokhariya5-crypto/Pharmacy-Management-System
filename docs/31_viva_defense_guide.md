# Viva Defense & Technical Architecture Guide
**Pharmacy Management System — Academic Project**
**Student:** Priyanshu Pokhariya | **Enrollment No:** 2410303005 | **Session:** 2026–27  
**University:** Amrapali University, Haldwani

---

## 1. System Architecture & Design Patterns
* **Pattern:** Multi-tier Monolithic Desktop Architecture.
  1. **Presentation Layer:** Built with `CustomTkinter` and `ttk.Treeview`. Single-root window architecture with in-place frame swapping to prevent multiple window instantiations or OS handle leaks.
  2. **Service / Business Logic Layer:** `AuthService`, `MedicineService`, `SearchService`, and `SalesService`. Enforces business rules, Poka-Yoke error prevention, and role-based permissions.
  3. **Data Access Layer:** `Database` (`database/db.py`) managing SQLite3 connection pooling, row factory mapping, and explicit `PRAGMA foreign_keys = ON;`.
  4. **Analytics & Visualization Layer:** `ReportGenerator` utilizing `Pandas` for group-by aggregations and `Matplotlib` for figure rendering embedded in Tkinter canvas.
  5. **Quality Engineering Modules:** `FMEAManager` (RPN risk audit) and `SQCManager` (Pareto 80/20, Ishikawa Fishbone, PDCA Kaizen tracking).

---

## 2. Database Design & B-Tree Indexing Mechanics
* **Database Engine:** SQLite3 relational database (`data/pharmacy.db`).
* **Table Entities:** `users`, `medicines`, `sales`, `sale_items`, `fmea_records`, `sqc_defects`, `pdca_items`.
* **Explicit B-Tree Indexes (17 Indexes):**
  * `idx_medicines_name` on `medicines(medicine_name)`
  * `idx_medicines_category` on `medicines(category)`
  * `idx_medicines_manufacturer` on `medicines(manufacturer)`
  * `idx_medicines_expiry` on `medicines(expiry_date)`
  * `idx_medicines_code` on `medicines(medicine_code)`
  * `idx_sales_invoice` on `sales(invoice_number)`
  * `idx_sales_patient` on `sales(patient_name)`
  * `idx_sales_date` on `sales(sale_date)`
  * Quality indexes on FMEA and SQC status, RPN, severity, and module.
* **Indexing Performance Reality (Viva Defense Point):**
  * **What B-Tree indexes accelerate:** Exact-match lookups (`medicine_code = ?`), category/manufacturer filtering, prefix searches (`LIKE 'Para%'`), and range scans / sorting on expiry date (`expiry_date <= ?`).
  * **What B-Tree indexes DO NOT accelerate:** Arbitrary infix partial searches like `LIKE '%query%'`. SQLite requires a full table scan for infix patterns. However, indexes accelerate composite sorting and page fetching overhead because the indexed columns are evaluated without loading raw data pages.

---

## 3. Atomic POS Transactions & Poka-Yoke Error Prevention
* **Checkout Atomicity:** Cart checkout runs inside `execute_transaction` (`BEGIN TRANSACTION ... COMMIT`).
* **Consistency:** If stock deduction succeeds for item 1 but fails for item 2, SQLite rolls back the entire sale. Stock is never deducted unless the sale record and sale item records are persisted.
* **Poka-Yoke (Mistake Proofing):**
  1. Expired medicine blocking: System prevents adding expired items to cart.
  2. Stock depletion blocking: Quantities exceeding available stock cannot be billed.
  3. Non-negative constraints: Database enforced `CHECK(price >= 0)` and `CHECK(quantity >= 0)`.
  4. Role-based deletion guard: Pharmacist role cannot delete medicine inventory or modify critical risk records.

---

## 4. Quality Tools (TQM / Six Sigma Integration)
* **FMEA (Failure Mode and Effects Analysis):**
  * $\text{RPN} = \text{Severity (1–10)} \times \text{Occurrence (1–10)} \times \text{Detection (1–10)}$.
  * Risk Thresholds:
    * $\text{RPN} \ge 200 \implies$ **Critical** (Immediate mitigation required)
    * $125 \le \text{RPN} < 200 \implies$ **High**
    * $50 \le \text{RPN} < 125 \implies$ **Medium**
    * $\text{RPN} < 50 \implies$ **Low**
* **Pareto Analysis:** Implements the 80/20 rule. Aggregates defect frequencies and plots cumulative percentage curves to identify vital few defect types.
* **Ishikawa Fishbone Diagram:** Categorizes potential root causes into 5 standard dimensions: People, Process, Machine, Material, Environment.
* **PDCA Kaizen:** Tracks continuous improvement lifecycle: $\text{Plan} \rightarrow \text{Do} \rightarrow \text{Check} \rightarrow \text{Act} \rightarrow \text{Closed}$.

---

## 5. Test Suite & Verification Metrics
* **Testing Framework:** Standard Python `unittest`.
* **Total Automated Tests:** 175 tests across 9 suites (100% passing).
* **Test Coverage:**
  * Schema & Database: 8 tests
  * Medicine CRUD: 11 tests
  * Search & Filters: 19 tests
  * Benchmark Latency: 22 tests
  * FMEA Risk Engine: 37 tests
  * SQC & PDCA: 45 tests
  * Sales & Billing: 16 tests
  * Historical Invoices: 2 tests
  * Analytical Reports: 15 tests

---

## 6. Project Limitations & Future Enhancements
* **Local Scope:** Desktop-bound SQLite instance; not intended for concurrent multi-branch WAN deployment.
* **Payment Processing:** Records transaction amounts locally; does not integrate live bank payment gateways.
* **Hardware:** Native barcode scanner integration and thermal printer ESC/POS protocols planned for future cloud releases.
