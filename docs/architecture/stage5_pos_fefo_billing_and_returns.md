# Stage 5 Architecture Specification: POS Billing, FEFO Checkout, Returns & Shift Reconciliation

## 1. Executive Summary
Stage 5 completes the end-to-end integration of the Pharmacy Management System. Building upon Stage 1 (Quality & Benchmarking), Stage 2 (Multi-Store & Schema), Stage 3 (RBAC & Dashboards), and Stage 4 (Purchasing, Batches, Locations & FEFO Preview), Stage 5 integrates:
1. **Full Point of Sale (POS) Workflow**: Multi-item cart management, quantity steppers, live subtotal/discount/tax/rounding calculations, and unique invoice generation (`INV-YYYYMMDDHHMMSS-HEX`).
2. **Mandatory 10-Digit Indian Mobile Number Validation**: Poka-Yoke input normalization, rejecting empty, non-digit, malformed length, or invalid starting digits (< 6) at both UI and service layer.
3. **Multi-Method Payments**: Cash, UPI, and Card selection with transaction reference tracking and cashier shift reconciliation.
4. **Active FEFO Checkout Integration**: Atomic deduction from `inventory_batches`, updating legacy `medicines.quantity`, recording `sale_batch_allocations`, and generating audit ledger rows in `stock_movements` (`SALE_DISPENSE`, -delta).
5. **Authorized Returns & Refunds**: Multi-item returns against historical sales, over-return validation, non-sellable return safety (preventing damaged/expired goods from returning to active stock), and refund auditing.
6. **Cashier Shift Reconciliation**: Real-time KPI cards for bills count, gross sales, payment breakdown (Cash, UPI, Card), discounts, refunds, and net settled sales.
7. **Comprehensive Audit Logging**: Structured logging of sensitive actions (`SALE_CHECKOUT`, `SALE_RETURN`, `PURCHASE_RECEIPT`, `STOCK_ADJUSTMENT`, etc.) with user, store, timestamp, and audit trail.
8. **Modern Visual Redesign**: Professional Emerald Green (`#087F5B`) + Deep Navy (`#142B3B`) + Soft Off-White (`#F4F7F8`) + Teal (`#20A39E`) theme.

---

## 2. Point of Sale (POS) Architecture

### 2.1 Workflow Pipeline
```
[Cashier POS View]
       │
       ▼ (Search & Select Medicine)
[Cart Management (add, update qty, remove)]
       │
       ▼ (Enter Customer Name & Phone)
[Poka-Yoke Validation (10-Digit Indian Mobile: [6-9]\d{9})]
       │
       ▼ (Calculate Subtotal, Discount, Tax, Rounding)
[Select Payment Method: Cash / UPI / Card (+ Auth Ref)]
       │
       ▼ (Submit Sale Request)
[SalesService.process_sale(store_id, cashier_id, cart, phone, pm)]
       │
       ├── 1. Store Authorization & Role Verification
       ├── 2. Cart Item Existence & Non-Expired Verification
       ├── 3. FEFO Eligible Batch Query (Expiry ASC, Created ASC, ID ASC)
       ├── 4. Stock Sufficiency Check (Available vs Requested)
       ├── 5. BEGIN TRANSACTION (SQLite)
       │      ├── Deduct from inventory_batches.current_quantity
       │      ├── Update medicines.quantity (legacy sync)
       │      ├── Insert sale_batch_allocations
       │      ├── Insert stock_movements (SALE_DISPENSE, -qty)
       │      ├── Insert sales & sale_items
       │      └── Insert audit_logs (SALE_CHECKOUT)
       └── 6. COMMIT TRANSACTION (Rollback on any conflict)
              │
              ▼
       [Invoice Receipt Modal & Reprint]
```

---

## 3. Mandatory Phone Validation Policy

Customer phone validation enforces standard Indian mobile numbering:
- **Format**: Exactly 10 numeric digits.
- **Leading Digit**: Must be between 6 and 9 (`6`, `7`, `8`, or `9`).
- **Input Normalization**:
  - Strips leading `+91`, `91`, or `0` prefix if present.
  - Strips whitespace, hyphens, parentheses, and period separators.
- **Error Handling**:
  - Empty input: `Enter a valid 10-digit Indian mobile number.`
  - Invalid character: `Enter a valid 10-digit Indian mobile number.`
  - Invalid length (< 10 or > 10): `Enter a valid 10-digit Indian mobile number.`
  - Invalid start digit (< 6): `Enter a valid 10-digit Indian mobile number.`
- **Dual Enforcement**: Enforced both in CustomTkinter UI (live inline warning banner) and in `SalesService` backend before transaction initiation.

---

## 4. FEFO Checkout & Stock Deduction Rules

When checkout occurs:
1. **Batch Eligibility**:
   - Must belong to the cashier's active `store_id`.
   - `status = 'Active'`.
   - `verification_flag = 0` (unquarantined, verified).
   - `current_quantity > 0`.
   - `expiry_date >= current_local_date` (expired batches strictly excluded).
2. **Sorting Order (Deterministic FEFO)**:
   - Primary: `expiry_date ASC` (earliest expiry first).
   - Tie-breaker 1: `created_at ASC` (oldest received batch first).
   - Tie-breaker 2: `batch_id ASC` (deterministic monotonic ID).
3. **Multi-Batch Allocation**:
   - If requested quantity exceeds the first eligible batch's stock, allocation cascades to the next batch until the entire quantity is fulfilled.
   - If total eligible stock across all batches is less than requested quantity, the entire transaction is aborted and rolled back.
4. **Ledger Consistency**:
   - For every allocated batch, an entry in `stock_movements` is recorded with `movement_type = 'SALE_DISPENSE'`, `quantity_delta = -allocated_qty`, and reference `INV-...`.
   - Legacy `medicines.quantity` is updated synchronously inside the same database transaction.

---

## 5. Payment Methods & Shift Reconciliation

### 5.1 Supported Payment Methods
- **Cash**: Standard cash payment.
- **UPI**: Unified Payments Interface (supports transaction ID / UTR reference).
- **Card**: Debit/Credit card (supports last 4 digits / auth reference).

### 5.2 Financial Calculation Formula
- `Subtotal` = $\sum (\text{item\_price} \times \text{item\_quantity})$
- `Taxable Amount` = $\max(0, \text{Subtotal} - \text{Discount})$
- `Tax Amount` = $\text{round}(\text{Taxable Amount} \times \frac{\text{Tax Rate}}{100}, 2)$
- `Unrounded Total` = $\text{Taxable Amount} + \text{Tax Amount}$
- `Grand Total` = $\text{quantize}(\text{Unrounded Total}, \text{ROUND\_HALF\_UP})$
- `Rounding Amount` = $\text{Grand Total} - \text{Unrounded Total}$

### 5.3 Cashier Reconciliation Metrics
- **Today's Bill Count**: Total completed sales for the active store and cashier.
- **Gross Sales**: $\sum \text{total\_amount}$ for all completed sales.
- **Cash Collections**: $\sum \text{total\_amount}$ where `payment_method = 'Cash'`.
- **UPI Collections**: $\sum \text{total\_amount}$ where `payment_method = 'UPI'`.
- **Card Collections**: $\sum \text{total\_amount}$ where `payment_method = 'Card'`.
- **Total Discounts**: $\sum \text{discount\_amount}$.
- **Total Refunds**: $\sum \text{total\_refund}$ from `sale_returns`.
- **Net Settled Sales**: $\text{Gross Sales} - \text{Total Refunds}$.

---

## 6. Returns & Refunds Architecture

### 6.1 Return Constraints & Safety Rules
1. **Original Sale Reference**: Return must reference a valid `sale_id` and specific `sale_item_id`.
2. **Over-Return Prevention**: Total returned quantity across all returns for a line item cannot exceed the original quantity sold:
   $$\sum \text{earlier\_returns} + \text{requested\_return} \le \text{original\_quantity}$$
3. **Non-Sellable Stock Protection**:
   - If medicine condition is marked `DAMAGED`, `EXPIRED`, or `RECALLED`:
     - Stock is **NOT** added back to sellable batch quantity.
     - Batch quantity remains untouched or batch is flagged quarantined.
     - Reason is permanently logged in `sale_returns` and `audit_logs`.
   - If medicine condition is marked `SELLABLE`:
     - Returned quantity is added back to the original batch (`current_quantity = current_quantity + returned_qty`).
     - A positive movement ledger entry is written (`movement_type = 'CUSTOMER_RETURN'`).
     - Legacy `medicines.quantity` is incremented.

---

## 7. Audit Logging Specification

Structured table `audit_logs` captures sensitive events:
- `log_id`: Monotonic primary key.
- `store_id`: Multi-store isolation key.
- `user_id`: Acting user identifier.
- `action_type`: Standardized action code (`SALE_CHECKOUT`, `SALE_RETURN`, `PURCHASE_RECEIPT`, `STOCK_ADJUSTMENT`, `USER_ROLE_CHANGE`, `USER_STATUS_CHANGE`).
- `entity_type`: Target entity (`sale`, `sale_return`, `purchase`, `inventory_batch`, `user`).
- `entity_id`: Primary key of modified entity.
- `details`: Human-readable summary or JSON details (never passwords or private keys).
- `ip_address`: Client IP / workstation identifier.
- `created_at`: UTC timestamp.

---

## 8. Verification & Test Metrics
- **Unit and Integration Tests**: 270 passed out of 270 tests (0 failures, 0 errors).
- **Execution Time**: 236 seconds across full test suite.
- **GUI Automation Workflow**: `test_gui_workflow.py` 11/11 steps passed.
- **Multi-Store Isolation Scenario**: `verify_multistore_scenario.py` 11/11 steps passed.
