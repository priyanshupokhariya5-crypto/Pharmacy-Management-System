# Pharmacy Management System — Architecture & Workflow Diagrams (Version 2.0)

**Project:** Pharmacy Management System  
**Course:** BBAT104 – Fundamentals of Total Quality Management  
**Quality Goal:** Q13 – Faster Search & Retrieval  
**Student:** Priyanshu Pokhariya | **Enrollment No.:** 2410303005  
**Institution:** Amrapali University, Haldwani, Uttarakhand  

This directory contains the individual, authoritative Mermaid (`.mmd`) diagram source files referenced throughout the **Software Requirements Specification (SRS Version 2.0)**. Each diagram represents a verified architectural, behavioral, or quality engineering dimension of the Pharmacy Management System implemented on branch `release/v2-clean`.

---

## Diagram Index & Purpose

| Diagram File | Figure Title | Type | Architectural Purpose |
| :--- | :--- | :--- | :--- |
| [`01_system_context.mmd`](01_system_context.mmd) | Figure 1: System Context Diagram | Context Graph | Depicts system boundaries, external human actors (5 user roles, suppliers, customers), local SQLite database, file system, and hardware interfaces. |
| [`02_high_level_architecture.mmd`](02_high_level_architecture.mmd) | Figure 2: High-Level System Architecture | Layered Architecture | Models 4-tier separation: Presentation Layer (CustomTkinter GUI), Business Service Layer, Cross-Cutting Utilities, and Data Access Layer. |
| [`03_use_case_model.mmd`](03_use_case_model.mmd) | Figure 3: Complete Use Case Diagram | Use Case Model | Details the interactions and functional privileges of all 5 user roles (Owner, Admin, Pharmacist, Cashier, Inventory Manager) across core operational use cases. |
| [`04_level_0_dfd.mmd`](04_level_0_dfd.mmd) | Figure 4: Level 0 Context Data Flow Diagram | DFD Level 0 | Illustrates top-level data inflows (credentials, orders, stock, phone numbers) and outflows (receipts, reports, RPNs) between entities and core process 0.0. |
| [`05_level_1_dfd.mmd`](05_level_1_dfd.mmd) | Figure 5: Level 1 Subsystem Data Flow Diagram | DFD Level 1 | Decomposes system into 7 primary subsystems: Authentication, Medicine Master, Q13 Search, Procurement, POS Billing, Reports, and TQM Quality. |
| [`06_level_2_dfd_pos_fefo.mmd`](06_level_2_dfd_pos_fefo.mmd) | Figure 6: Level 2 DFD for POS Billing & FEFO | DFD Level 2 | Details the critical data flow inside process 5.0 (POS Billing) covering phone validation, item scanning, FEFO deduction, financial calculation, and invoice creation. |
| [`07_erd_complete.mmd`](07_erd_complete.mmd) | Figure 7: Complete Entity Relationship Diagram | ERD | Authoritative Crow's Foot ERD mapping all 19 relational entities, primary keys, foreign keys, cardinality, and multi-store compound uniqueness constraints. |
| [`08_login_rbac_activity.mmd`](08_login_rbac_activity.mmd) | Figure 8: Login & RBAC Activity Diagram | Activity Flowchart | Decision flow for multi-store user authentication, active status checks, role consistency verification, PBKDF2 hash evaluation, and dynamic nav filtering. |
| [`09_medicine_inventory_workflow.mmd`](09_medicine_inventory_workflow.mmd) | Figure 9: Medicine Master Management Workflow | Activity Flowchart | Full lifecycle of medicine catalogue entries: Permission checks, modal validation, shelf allocation checks, updates, and dependency-checked soft/hard deletion. |
| [`10_batch_receiving_shelf_allocation.mmd`](10_batch_receiving_shelf_allocation.mmd) | Figure 10: Batch Inward & Shelf Allocation | Activity Flowchart | Enforces the Critical Shelf Rule: Same medicine with different expiry dates cannot share a shelf; identical expiry dates may share a shelf. |
| [`11_purchase_order_workflow.mmd`](11_purchase_order_workflow.mmd) | Figure 11: Purchase Order & Goods Receiving | Activity Flowchart | Inward procurement lifecycle: Supplier selection, line items entry, shelf rule verification, and atomic commit across purchases, batches, and stock ledger. |
| [`12_advanced_search_activity.mmd`](12_advanced_search_activity.mmd) | Figure 12: Q13 Advanced Search Activity Flow | Activity Flowchart | Fast search execution path: B-Tree index scan for exact codes, prefix index ranges for names, compound queries for shelf/category, and instant POS cart transfer. |
| [`13_pos_billing_sequence.mmd`](13_pos_billing_sequence.mmd) | Figure 13: POS Billing Sequence Diagram | Sequence Diagram | Interaction sequence between Cashier, POS UI, Validator, SalesService, ShelfService, and SQLite DB during checkout and receipt generation. |
| [`14_fefo_allocation_flowchart.mmd`](14_fefo_allocation_flowchart.mmd) | Figure 14: Automated FEFO Stock Allocation | Flowchart Algorithm | Step-by-step logic of the First Expiry, First Out algorithm: Query unexpired active stock, sort by `expiry_date ASC`, allocate across batches, atomic deduction. |
| [`15_sales_transaction_sequence.mmd`](15_sales_transaction_sequence.mmd) | Figure 15: Sales ACID Transaction Sequence | Sequence Diagram | Details database transaction isolation: `BEGIN TRANSACTION`, batch row locks, stock deduction, allocations insert, audit log write, and automatic `ROLLBACK` on error. |
| [`16_returns_stock_adjustment.mmd`](16_returns_stock_adjustment.mmd) | Figure 16: Sales Return & Stock Adjustment | Flowchart | Customer return workflow: Invoice verification, return quantity boundary check, condition grading (Sellable vs Damaged), restocking, and refund voucher issuance. |
| [`17_fmea_workflow.mmd`](17_fmea_workflow.mmd) | Figure 17: FMEA Risk Audit Workflow | Activity Flowchart | Risk evaluation lifecycle: Failure mode identification, Severity (S), Occurrence (O), Detection (D) scoring, RPN computation ($S \times O \times D$), and CAPA tracking. |
| [`18_sqc_pareto_fishbone_workflow.mmd`](18_sqc_pareto_fishbone_workflow.mmd) | Figure 18: SQC Defect Tracking & Fishbone | Quality Workflow | Defect logging, Pareto 80/20 vital few analysis, cumulative defect distribution, and 6M Ishikawa root cause analysis (Methods, Machines, Materials, Manpower, Measurement, Milieu). |
| [`19_pdca_cycle.mmd`](19_pdca_cycle.mmd) | Figure 19: Deming PDCA Continuous Improvement | Cycle Diagram | The 4 iterative stages of continuous quality engineering: Plan (Root Cause & Target), Do (Poka-Yoke Controls), Check (Metric Verification), and Act (Standardization). |
| [`20_end_to_end_pharmacy_workflow.mmd`](20_end_to_end_pharmacy_workflow.mmd) | Figure 20: Overall End-to-End Pharmacy Operations | Master Flowchart | High-level synthesis connecting daily store opening, procurement inward, customer dispensing, returns, quality audits, analytics, and shift closing. |

---

## Viewing & Rendering Instructions

1. **In Markdown Preview / GitHub**: Mermaid blocks are natively rendered in GitHub markdown viewers and modern IDEs (Antigravity, VS Code with Markdown Preview Mermaid Support).
2. **In Word Document (`docs/SRS_Pharmacy_Management_System.docx`)**: These diagrams have been rendered into high-resolution graphic assets located in `docs/diagrams/images/` and embedded directly into the document.
3. **CLI Rendering**: Use `@mermaid-js/mermaid-cli` (`mmdc -i <file.mmd> -o <file.png> -s 2 -b white`) to export vector or raster images if desired.

