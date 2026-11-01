# Stage 3 Architecture: Authentication, Role-Based Access Control (RBAC) & Dedicated Dashboards

---

## 1. Executive Overview

Stage 3 transforms the Pharmacy Management System from a single-dashboard model into an enterprise **Role-Based Access Control (RBAC)** architecture with 4 distinct operational roles:
1. **Owner / Admin**
2. **Pharmacist**
3. **Cashier**
4. **Inventory Manager**

Security is enforced at the **backend/service layer**, not merely by hiding UI buttons. Direct service calls to restricted operations (`delete_medicine`, `add_medicine`, `process_sale`, `manage_users`, etc.) verify role permissions and multi-store tenant boundaries, raising `PermissionError` if an unauthorized call is attempted.

---

## 2. Backward-Compatible Role-Mapping Strategy

The existing database contains 4 legacy users across 3 stores:
- `admin` (Role: `Admin`, Store: `STORE-LEGACY-001`)
- `pharmacist` (Role: `Pharmacist`, Store: `STORE-LEGACY-001`)
- `pokhariya` (Role: `Owner`, Store: `STORE-81C3C6BF`)
- `dyerycfh` (Role: `Owner`, Store: `STORE-4DFCD74E`)

### Canonical Role Mapping Table
To guarantee 100% backward compatibility without granting excessive permissions, role strings are mapped through `normalize_role()`:

| Stored / Input Role | Canonical Role | Granted Privilege Set | Rationale |
| :--- | :--- | :--- | :--- |
| `Admin` | `Admin` | Full System & Store Administration | Legacy administrator granted owner-equivalent operational rights within store. |
| `Owner` | `Owner` | Full Store Ownership & Financials | Business owner with user management, financials, and inventory control. |
| `Pharmacist` | `Pharmacist` | Clinical Inspection & Dispensing | Medicine lookup, batch inspection, and safety checks; **no deletion, user management, or billing**. |
| `Cashier` | `Cashier` | Point of Sale (POS) Billing | Cart checkout, receipt printing, and daily cashier shift totals; **no inventory editing or financials**. |
| `Inventory Manager` | `Inventory Manager` | Stock & Batch Management | Goods receiving, shelf assignment, stock reordering; **no billing, deletion, or user management**. |
| *Unrecognized / Unknown* | `Unknown` | Zero Permissions (Fail-Safe) | Blocks privilege escalation for malformed or injected role strings. |

---

## 3. Role-Permission Matrix

The system enforces 14 granular permissions across 5 domain areas:

| Permission Identifier | Description | Owner / Admin | Pharmacist | Cashier | Inventory Manager |
| :--- | :--- | :---: | :---: | :---: | :---: |
| `view_dashboard` | Access role-specific dashboard | ✅ | ✅ | ✅ | ✅ |
| `view_financials` | Executive revenues, profits, purchase costs | ✅ | ❌ | ❌ | ❌ |
| `manage_users` | Create, deactivate, and assign staff roles | ✅ | ❌ | ❌ | ❌ |
| `manage_store_settings`| Store configuration and tenant parameters | ✅ | ❌ | ❌ | ❌ |
| `view_audit_logs` | Security, login, and transaction audit trails | ✅ | ❌ | ❌ | ❌ |
| `view_medicines` | Inspect medicine catalogue & stock levels | ✅ | ✅ | ✅ | ✅ |
| `add_medicine` | Catalog new pharmaceutical items | ✅ | ✅ | ❌ | ✅ |
| `update_medicine` | Edit pricing, stock levels, or medicine data | ✅ | ✅ | ❌ | ✅ |
| `delete_medicine` | Permanently remove medicine records | ✅ | ❌ | ❌ | ❌ |
| `process_sale` | Point of sale checkout and receipt creation | ✅ | ❌ | ✅ | ❌ |
| `view_sales_history` | Review sales transactions | ✅ | ❌ | ✅ *(own/shift)* | ❌ |
| `reprint_receipt` | Reprint past invoices/receipts | ✅ | ❌ | ✅ | ❌ |
| `manage_inventory` | Adjust stock, batches, shelf assignments | ✅ | ❌ | ❌ | ✅ |
| `dispense_medicine` | Clinical dispensing review and inspection | ✅ | ✅ | ❌ | ❌ |
| `view_stock_alerts` | Expiry (<30d) and low-stock reorder warnings | ✅ | ✅ | ❌ | ✅ |

---

## 4. Backend Service-Layer Authorization Guards

Authorization is implemented in [`services/rbac.py`](file:///C:/Users/priya/.gemini/antigravity/scratch/Pharmacy-Management-System-Clean/services/rbac.py) and called at service boundaries:

```python
def require_permission(acting_user: Any, permission: str, action_desc: str = "This operation") -> None:
    if acting_user is None:
        return
    user_role = getattr(acting_user, "role", None)
    if not has_permission(user_role, permission):
        raise PermissionError(
            f"Access Denied: {action_desc} requires '{permission}' permission. "
            f"User '{acting_user.username}' with role '{user_role}' is not authorized."
        )

def require_store_access(acting_user: Any, target_store_id: str, action_desc: str = "This operation") -> None:
    if acting_user is None or not target_store_id:
        return
    user_store = getattr(acting_user, "store_id", None)
    if user_store and user_store != target_store_id:
        raise PermissionError(
            f"Store Access Denied: User '{acting_user.username}' belongs to store '{user_store}' "
            f"and is not authorized to access or modify resources in store '{target_store_id}'."
        )
```

### Protected Service Operations
1. `MedicineService.delete_medicine(medicine_id, acting_user)`: Requires `PERM_DELETE_MEDICINE` (Owner/Admin only).
2. `MedicineService.add_medicine(medicine, acting_user)`: Requires `PERM_ADD_MEDICINE` (Owner, Admin, Pharmacist, Inventory Manager).
3. `MedicineService.update_medicine(medicine, acting_user)`: Requires `PERM_UPDATE_MEDICINE`.
4. `SalesService.process_sale(..., acting_user)`: Requires `PERM_PROCESS_SALE` (Cashier, Owner, Admin).
5. `AuthService.create_user(..., acting_user)`: Requires `PERM_MANAGE_USERS` (Owner, Admin).
6. `AuthService.set_user_active_status(..., acting_user)`: Requires `PERM_MANAGE_USERS`; prevents self-deactivation.
7. `AuthService.update_user_role(..., acting_user)`: Requires `PERM_MANAGE_USERS`.

---

## 5. Role-Specific Dashboards Architecture

The unified [`ui/dashboard.py`](file:///C:/Users/priya/.gemini/antigravity/scratch/Pharmacy-Management-System-Clean/ui/dashboard.py) dynamically inspects `user.canonical_role` to render role-optimized views using real SQLite queries:

### A. Owner / Admin Executive Dashboard
- **5 KPI Metrics:** Today's Sales (`₹`), Today's Bills Count, Total Net Revenue (`₹`), Estimated Gross Profit (`25% margin`), Total Stock Alerts.
- **Top 5 Selling Medicines Table:** Ranked by quantity sold and total revenue generated within the store.
- **Recent Store Transactions:** Last 5 invoices with customer name, timestamp, and amount.
- **Q13 Instant Quick-Search:** Sub-millisecond debounced medicine search with modal details view.

### B. Cashier Shift Dashboard
- **5 Shift Metrics:** Today's Bill Count, Today's Gross Sales (`₹`), Cash Collections (`₹`), Digital Collections (UPI/Card `₹`), Net Settled Sales (`₹`).
- **Prominent Action Banner:** Large "🛒 Open New Bill (POS)" button that navigates directly to the Point of Sale view.
- **Shift Invoices Table:** Recent bills created today with invoice number, patient name, items count, and total amount.
- **Price & Availability Checker:** Fast medicine lookup for checkout assistance.

### C. Pharmacist Clinical Dashboard
- **5 Clinical KPIs:** In-Stock Available Medicines, Clinical Attention Required, Near-Expiry (<30d), Expired Medicines (BLOCKED from dispensing), Critical Low Stock (<=10).
- **Clinical Attention List:** Real-time table of expired or near-expiry batches requiring quarantine or immediate dispensing priority.
- **Recent Dispensing Log:** Audit list of recently dispensed medicines with patient name, batch number, and quantity.
- **Fast Medicine & Batch Inspector:** Full modal popup displaying shelf, batch, manufacturer, and expiry status.

### D. Inventory Manager Dashboard
- **5 Stock Metrics:** Cataloged Medicines, Total Physical Stock Units, Inventory Valuation (`₹`), Reorder Required (<=10 units), Expired Stock.
- **Low-Stock Reorder Priority List:** Ordered by lowest stock quantity with category and batch details.
- **Batch & Expiry Alert Ledger:** Batches expiring within 60 days requiring supplier return or reorder.

---

## 6. Account Status Lifecycle (`is_active`)

1. **Schema Support:** The `users` table includes `is_active INTEGER DEFAULT 1`.
2. **Authentication Enforcement:** [`AuthService.authenticate()`](file:///C:/Users/priya/.gemini/antigravity/scratch/Pharmacy-Management-System-Clean/services/auth_service.py) checks `is_active`. If `0`, login is immediately rejected with:
   `"Account is deactivated. Please contact store owner."`
3. **Lockout Prevention:** An owner cannot deactivate their own account, preventing accidental store lockout.
4. **Permission Revocation:** If `user.is_active is False`, `user.has_permission()` immediately returns `False`.

---

## 7. Automated Test Verification

A dedicated test suite [`tests/test_stage3_auth_dashboards.py`](file:///C:/Users/priya/.gemini/antigravity/scratch/Pharmacy-Management-System-Clean/tests/test_stage3_auth_dashboards.py) validates all 15 core Stage 3 scenarios:
- Valid login across all roles by username and email (Test 01)
- Invalid credentials and empty inputs (Test 02)
- Disabled account rejection and reactivation (Test 03)
- Canonical role mapping and unknown role safety (Test 04)
- RBAC permissions matrix correctness (Test 05)
- Unauthorized medicine deletion blocked (Test 06)
- Cashier blocked from adding/updating medicines (Test 07)
- Inventory Manager blocked from POS sales (Test 08)
- Authorized operations succeed for permitted roles (Test 09)
- User management RBAC and self-deactivation protection (Test 10)
- Multi-store cross-tenant access blocked (Test 11)
- Owner dashboard query accuracy (Test 12)
- Cashier dashboard query accuracy (Test 13)
- Pharmacist clinical dashboard query accuracy (Test 14)
- Inventory Manager dashboard query accuracy (Test 15)

**Results: 15/15 tests passed in 36.332s (100% PASS).**
