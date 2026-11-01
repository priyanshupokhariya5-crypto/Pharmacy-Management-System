# Advanced Pharmacy Management System (PMS)

[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![GUI-CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-087F5B.svg)](https://github.com/TomSchimansky/CustomTkinter)
[![Database-SQLite3](https://img.shields.io/badge/Database-SQLite3-003B57.svg)](https://www.sqlite.org/)
[![Tests-270_Passing](https://img.shields.io/badge/Tests-270%20Passing-237A4B.svg)](tests/)
[![Architecture-Multi--Store_RBAC](https://img.shields.io/badge/Architecture-Multi--Store%20RBAC-142B3B.svg)](docs/architecture/)

An enterprise-grade, desktop Pharmacy Management and Point of Sale (POS) system engineered for high-throughput retail pharmacies and hospital dispensaries. Features **Multi-Store Isolation**, **Role-Based Access Control (RBAC)**, **Deterministic FEFO (First-Expiry, First-Out) Inventory**, **Multi-Batch Purchasing & Goods Receiving**, **Shelf Allocation Rules**, **Poka-Yoke Error Prevention**, and **Industrial Quality Engineering** (FMEA, SQC, PDCA Kaizen).

---

## 1. System Highlights

- **Point of Sale (POS) & Billing**:
  - Live medicine search with stock and expiry warnings.
  - Multi-item cart management with quantity controls and real-time subtotal, discount, tax, and standard commercial half-up rounding (`Decimal.ROUND_HALF_UP`).
  - **Mandatory Customer Mobile Validation**: Enforces 10-digit Indian phone format (`[6-9]\d{9}`) with dual UI and backend validation.
  - Multiple payment methods (**Cash**, **UPI**, **Card**) with transaction/auth reference recording.
  - Receipt generation, printing modal, and reprint history.
  - Duplicate checkout submission prevention.
- **FEFO Batch Inventory & Checkout**:
  - Full batch tracking: batch number, manufacturing date, expiry date, purchase cost, selling price, and storage location.
  - Deterministic FEFO allocation across multiple batches by earliest expiry date during checkout.
  - Atomic stock deductions and complete movement auditing via `stock_movements` ledger.
  - Automatic exclusion of expired, recalled, quarantined, and unverified batches.
- **Shelf Allocation Rules**:
  - Batches of the same medicine with different expiry dates must use separate shelves.
  - Batches of the same medicine with identical expiry dates may share a shelf.
  - Different medicines may share a shelf.
- **Authorized Returns & Refunds**:
  - Multi-item returns linked to original sales with over-return protection.
  - Non-sellable stock protection: damaged or expired returned medicines are never returned to sellable stock.
- **Cashier Shift Reconciliation**:
  - Live cashier metrics: Today's bill count, gross sales, cash collections, UPI collections, card collections, discounts, refunds, and net settled sales.
- **Multi-Store Architecture**:
  - Strict physical and logical data isolation across individual stores (`store_id`).
  - Store-scoped user permissions, inventory, purchases, sales, and analytics.
- **5 Canonical Roles (RBAC)**:
  - **Owner**: Full cross-store analytics and administration.
  - **Admin**: Store-level administrative oversight, settings, and user management.
  - **Pharmacist**: Medicine dispensing, expiry inspections, and batch quality control.
  - **Cashier**: POS billing, shift reconciliation, receipt reprinting, and authorized returns.
  - **Inventory Manager**: Purchasing, supplier management, batch receiving, and shelf allocation.
- **Quality Engineering & Kaizen**:
  - Failure Mode and Effects Analysis (FMEA) with automated Risk Priority Number (RPN) ranking.
  - Statistical Quality Control (SQC) with Pareto defect analysis and Ishikawa Fishbone diagrams.
  - Plan-Do-Check-Act (PDCA) Kaizen cycle tracking.
- **High-Performance Database Engine**:
  - Explicit column projections and SQLite B-Tree indexing on critical lookup paths.
  - Sub-millisecond query execution benchmarked against 5,000+ records.

---

## 2. Technology Stack

| Layer | Technology | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.13 (64-bit) | Modern Python runtime |
| **GUI Framework** | CustomTkinter 5.2+ | Hardware-accelerated, modern desktop UI |
| **Styling & Theme** | Custom Design System | Emerald Green (`#087F5B`) + Deep Navy (`#142B3B`) + Soft Off-White (`#F4F7F8`) + Teal (`#20A39E`) |
| **Database Engine** | SQLite 3 | Atomic transactions, foreign keys enabled, B-Tree indexes |
| **Analytics** | Pandas 2.2+ | High-performance data aggregation & CSV export |
| **Data Visualization**| Matplotlib 3.8+ | Pareto charts, SQC defect trends, Fishbone diagrams |
| **Document Engine** | ReportLab / FPDF | Invoice generation & receipt formatting |
| **Testing** | Python `unittest` | 270 automated unit, integration, and regression tests |
| **Packaging** | PyInstaller 6.x | Standalone Windows onedir executable packaging |

---

## 3. Project Structure

```
Pharmacy-Management-System/
├── main.py                     # Main application entry point & runtime initialization
├── requirements.txt            # Python dependencies
├── PharmacyApp.spec            # PyInstaller build specification
├── README.md                   # System documentation
│
├── database/                   # Database engine & migrations
│   ├── db.py                   # Thread-safe SQLite connection wrapper & transaction execution
│   ├── schema.py               # Base schema DDL, indexes, and initial data seeding
│   ├── migration_stage2.py     # Safe idempotent schema migrations (Stores, Batches, POs, Returns)
│   ├── sync.py                 # Multi-database synchronization engine
│   └── benchmark_db.py         # Dedicated benchmark database utility
│
├── models/                     # Domain entity data classes
│   ├── user.py                 # User model and canonical roles (Owner, Admin, Pharmacist, Cashier, InvMgr)
│   ├── medicine.py             # Medicine catalog entity with expiry property
│   ├── batch.py                # Inventory batch model with verification & quarantine flags
│   ├── location.py             # Storage location (shelf, rack, bin) model
│   ├── supplier.py             # Supplier directory model
│   ├── purchase.py             # Purchase order & item models
│   ├── sale.py                 # Sale, SaleItem, SaleReturn, and SaleReturnItem models
│   └── stock_movement.py       # Stock movement audit ledger model
│
├── services/                   # Business logic & transaction processing
│   ├── auth_service.py         # Authentication, PBKDF2 hashing, and store-scoped user management
│   ├── rbac.py                 # Role-based access control and permission enforcement
│   ├── medicine_service.py     # Medicine catalog CRUD and low-stock alerts
│   ├── search_service.py       # Optimized B-Tree search with multi-parameter filtering
│   ├── sales_service.py        # POS billing, FEFO batch deductions, returns, and shift reconciliation
│   ├── inventory_service.py    # Batch lifecycle, quarantine flags, and stock adjustments
│   ├── shelf_service.py        # Shelf allocation rules and capacity verification
│   ├── purchase_service.py     # Purchase orders, multi-batch goods receipt, and atomic ledger entries
│   ├── supplier_service.py     # Supplier directory CRUD and status transitions
│   ├── audit_service.py        # Structured audit logging for sensitive system events
│   └── report_service.py       # Comprehensive analytics reports and CSV data exports
│
├── ui/                         # CustomTkinter modern UI views
│   ├── theme.py                # Modern Emerald Green & Deep Navy color tokens and typography
│   ├── main_window.py          # Unified application shell with role-aware sidebar navigation
│   ├── dashboard.py            # Role-tailored dashboards with live KPI summary cards
│   ├── billing.py              # Point of Sale (POS) view with live cart, totals, and return modals
│   ├── batch_inventory.py      # Batch-wise inventory management and shelf assignment view
│   ├── purchase_entry.py       # Purchase order management and multi-batch goods receiving view
│   ├── supplier_management.py  # Supplier directory management view
│   ├── benchmark_view.py       # Search performance benchmarking view
│   └── ...                     # Medicine CRUD, Reports, FMEA, SQC, and PDCA views
│
├── utils/                      # Helper utilities and validators
│   ├── validators.py           # Mandatory 10-digit Indian phone validation & bill total calculations
│   ├── logger.py               # Structured application and Poka-Yoke logger
│   ├── benchmark.py            # Sub-millisecond performance timing framework
│   └── quality_tools.py        # FMEA, SQC Pareto, Fishbone, and PDCA calculation engines
│
├── tests/                      # Automated test suite (270 Passing Tests)
│   ├── test_sales.py           # POS cart rules, subtotal calculations, and stock deduction tests
│   ├── test_stage2_migration.py# Schema migration, foreign key integrity, and table rebuild tests
│   ├── test_stage3_auth_dashboards.py # RBAC permission gating, multi-store isolation tests
│   ├── test_stage4_purchasing_fefo.py # Purchasing, batch receiving, and shelf rule tests
│   ├── test_stage5_billing_pos_returns.py # Phone validation, Cash/UPI/Card, FEFO checkout, returns tests
│   └── ...                     # Comprehensive regression, search, benchmarking, and quality tests
│
└── docs/                       # Complete academic and technical documentation
    ├── architecture/           # Architecture specifications and 13 Mermaid diagrams
    ├── database/               # Complete database schema design and migration logs
    └── SRS_Pharmacy_Management_System.md # Software Requirements Specification
```

---

## 4. Key Architectural Workflows & Diagrams

Detailed diagrams with editable Mermaid source code are available in [docs/architecture/system_architecture_and_diagrams.md](docs/architecture/system_architecture_and_diagrams.md).

### 4.1 FEFO (First-Expiry, First-Out) Algorithm
When a sale is processed:
1. Loads all eligible active batches for the medicine in the cashier's store (`expiry_date >= current_date`, `current_quantity > 0`, `status = 'Active'`, `verification_flag = 0`).
2. Sorts deterministically: `expiry_date ASC`, `created_at ASC`, `batch_id ASC`.
3. Verifies that cumulative eligible stock $\ge$ requested quantity.
4. Allocates quantity across batches, deducting `current_quantity` conditionally (`WHERE current_quantity >= allocated_qty`).
5. Updates legacy `medicines.quantity` synchronously.
6. Writes immutable audit rows to `stock_movements` (`SALE_DISPENSE`, -delta) and `sale_batch_allocations`.
7. Commits all changes within a single atomic SQLite transaction; rolls back completely on any failure.

### 4.2 Shelf Allocation Rule
- **Rule 1**: The same medicine with different expiry dates **must** be stored on different shelves.
- **Rule 2**: The same medicine with identical expiry dates may share a shelf.
- **Rule 3**: Different medicines may share a shelf, subject to shelf physical capacity.

### 4.3 Mandatory Customer Phone Validation
- Enforces exactly 10 digits.
- First digit must be between 6 and 9 (`6`, `7`, `8`, or `9`).
- Empty values, alphabetic characters, symbols, and incorrect digit lengths are strictly rejected with an inline warning.
- Enforced at both the CustomTkinter UI level and in the backend `SalesService`.

---

## 5. Demo Credentials

The system seeds sample demonstration accounts:

| Username | Password | Role | Store ID | Scope |
| :--- | :--- | :--- | :--- | :--- |
| `admin` | `admin123` | **Admin** | `STORE-LEGACY-001` | Full administrative control of store |
| `pharmacist` | `pharma123` | **Pharmacist** | `STORE-LEGACY-001` | Dispensing, batch inspection, and quality |
| `owner` | `owner123` | **Owner** | `STORE-LEGACY-001` | Multi-store financial and business analytics |
| `cashier` | `cashier123` | **Cashier** | `STORE-LEGACY-001` | POS billing, shift reconciliation, returns |
| `inventory` | `inv123` | **Inventory Manager**| `STORE-LEGACY-001` | Purchasing, batch receiving, shelf mapping |

---

## 6. Installation & Execution

### Prerequisites
- Python 3.13 (or 3.11+) 64-bit
- Windows 10/11 (or Linux/macOS with Tkinter installed)

### Setup Instructions
1. Clone the repository:
   ```bash
   git clone https://github.com/priyanshupokhariya5-crypto/Pharmacy-Management-System.git
   cd Pharmacy-Management-System
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the desktop application:
   ```bash
   python main.py
   ```

---

## 7. Automated Testing & Verification

The project includes an automated test suite verifying every component from database transactions to GUI flows.

### Run All 270 Tests
```bash
python -W ignore -m unittest discover -s tests -p "test_*.py"
```

**Verification Results**:
- **Total Tests Executed**: 270
- **Passed**: 270
- **Failures**: 0
- **Errors**: 0
- **Execution Time**: ~236 seconds

### Run GUI Workflow Verification
```bash
python test_gui_workflow.py
```
*Validates login, registration, multi-store creation, medicine cataloging, logout, and cross-store data isolation across 11 automated GUI steps.*

### Run Multi-Store Isolation Scenario
```bash
python verify_multistore_scenario.py
```
*Simulates two separate pharmacies operating concurrently, proving complete separation of inventory, customers, invoices, and sales.*

---

## 8. PyInstaller Packaging

A pre-configured PyInstaller specification (`PharmacyApp.spec`) produces a standalone Windows executable:
```bash
pyinstaller PharmacyApp.spec --clean
```
Output executable is generated in `dist/PharmacyApp/PharmacyApp.exe`.

---

## 9. Academic Review Milestones

- **Review 1 Commit**: `fcfe5d4c4ca9cd04e7ae0a834e3ed995b6d4d356` (System Architecture & Project Scope)
- **Review 2 Commit**: `cce94dba300f2eb7d116075b3cfe2838286f15b6` (Schema Architecture, Authentication & Search)
- **Review 3**: Multi-Store Isolation, RBAC & Role Dashboards
- **Review 4**: Purchasing, Batch Inventory, Shelf Allocation & FEFO Preview
- **Final Review**: Complete POS Billing, Mandatory Phone Validation, Real FEFO Checkout, Returns/Refunds, Cashier Reconciliation, Theme Redesign, and Full Regression Suite (270/270 tests).
