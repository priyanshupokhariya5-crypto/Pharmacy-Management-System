# Advanced Pharmacy Management System: Comprehensive Architecture & Diagrams

This document provides the complete technical architecture and all 13 core architectural diagrams for the Pharmacy Management System, reflecting the fully integrated Stage 1 through Stage 5 implementations.

---

## 1. System Architecture Diagram

```mermaid
graph TB
    subgraph Client_Presentation_Layer ["Desktop Presentation Layer (CustomTkinter)"]
        UI_Login["Login & Store Selector View"]
        UI_Dash["Role-Specific Dashboards (Owner/Admin/Cashier/Inv)"]
        UI_POS["POS Billing & Invoice Modal (Cash/UPI/Card)"]
        UI_Med["Medicine CRUD & Search View (B-Tree Optimized)"]
        UI_Batch["Batch Inventory & Shelf Allocation View"]
        UI_Purch["Purchase Order & Goods Receiving View"]
        UI_Supp["Supplier Directory & Management View"]
        UI_Ret["Returns & Refund Management View"]
        UI_Rep["Reporting & Analytics View (Tabular & CSV)"]
        UI_Qual["Quality Control (FMEA / SQC / PDCA / Fishbone)"]
    end

    subgraph Business_Service_Layer ["Service Layer (Business Logic & Authorization)"]
        AuthSvc["AuthService & RBAC Enforcer"]
        MedSvc["MedicineService"]
        SearchSvc["SearchService (B-Tree + Filter Cache)"]
        SalesSvc["SalesService (FEFO Checkout & Returns)"]
        InvSvc["InventoryService (Batch Lifecycle)"]
        ShelfSvc["ShelfService (Shelf Expiry Rules)"]
        PurchSvc["PurchaseService (PO & Goods Receipt)"]
        SuppSvc["SupplierService"]
        AuditSvc["AuditService (Security Logging)"]
        RepSvc["ReportService (Aggregations & Exports)"]
    end

    subgraph Data_Access_Layer ["Data Access & SQLite Engine"]
        DBHandler["Database Manager (db.py / Connection Pool)"]
        SchemaMgr["Schema Migration & Compatibility Engine"]
        SyncMgr["Cross-Database Sync Engine"]
        SQLiteDB[("SQLite 3 Database (pharmacy.db)")]
    end

    UI_Login --> AuthSvc
    UI_Dash --> RepSvc
    UI_Dash --> AuditSvc
    UI_POS --> SalesSvc
    UI_Med --> MedSvc
    UI_Med --> SearchSvc
    UI_Batch --> InvSvc
    UI_Batch --> ShelfSvc
    UI_Purch --> PurchSvc
    UI_Supp --> SuppSvc
    UI_Ret --> SalesSvc
    UI_Rep --> RepSvc

    AuthSvc --> DBHandler
    MedSvc --> DBHandler
    SearchSvc --> DBHandler
    SalesSvc --> DBHandler
    InvSvc --> DBHandler
    ShelfSvc --> DBHandler
    PurchSvc --> DBHandler
    SuppSvc --> DBHandler
    AuditSvc --> DBHandler
    RepSvc --> DBHandler

    DBHandler --> SchemaMgr
    DBHandler --> SQLiteDB
```

---

## 2. Complete Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    STORES ||--o{ USERS : "employs"
    STORES ||--o{ MEDICINES : "stocks"
    STORES ||--o{ INVENTORY_BATCHES : "holds"
    STORES ||--o{ STORAGE_LOCATIONS : "organizes"
    STORES ||--o{ SUPPLIERS : "contracts"
    STORES ||--o{ PURCHASE_ORDERS : "issues"
    STORES ||--o{ SALES : "processes"
    STORES ||--o{ SALE_RETURNS : "authorizes"
    STORES ||--o{ STOCK_MOVEMENTS : "tracks"
    STORES ||--o{ AUDIT_LOGS : "logs"

    MEDICINES ||--o{ INVENTORY_BATCHES : "has_batches"
    MEDICINES ||--o{ SALE_ITEMS : "sold_in"
    MEDICINES ||--o{ PURCHASE_ITEMS : "ordered_in"
    MEDICINES ||--o{ STOCK_MOVEMENTS : "moved_in"

    STORAGE_LOCATIONS ||--o{ INVENTORY_BATCHES : "stores"

    SUPPLIERS ||--o{ PURCHASE_ORDERS : "supplies"

    PURCHASE_ORDERS ||--o{ PURCHASE_ITEMS : "contains"
    PURCHASE_ITEMS ||--o{ PURCHASE_ITEM_BATCHES : "received_as"
    PURCHASE_ITEM_BATCHES ||--o| INVENTORY_BATCHES : "creates"

    USERS ||--o{ SALES : "cashier"
    USERS ||--o{ SALE_RETURNS : "approves"
    USERS ||--o{ PURCHASE_ORDERS : "creates"
    USERS ||--o{ AUDIT_LOGS : "acts"

    SALES ||--o{ SALE_ITEMS : "has"
    SALE_ITEMS ||--o{ SALE_BATCH_ALLOCATIONS : "allocates_from"
    INVENTORY_BATCHES ||--o{ SALE_BATCH_ALLOCATIONS : "dispensed_in"

    SALES ||--o{ SALE_RETURNS : "returned_against"
    SALE_RETURNS ||--o{ SALE_RETURN_ITEMS : "includes"
    SALE_ITEMS ||--o{ SALE_RETURN_ITEMS : "returns_item"
    INVENTORY_BATCHES ||--o{ SALE_RETURN_ITEMS : "restocks_batch"

    INVENTORY_BATCHES ||--o{ STOCK_MOVEMENTS : "records_movement"

    STORES {
        string store_id PK
        string store_name
        string owner_name
        timestamp created_at
    }

    USERS {
        int user_id PK
        string username
        string password_hash
        string role
        string store_id FK
        string full_name
        string email
        int is_active
    }

    MEDICINES {
        int medicine_id PK
        string store_id FK
        string medicine_code
        string medicine_name
        string category
        string manufacturer
        float price
        int quantity
        date expiry_date
    }

    INVENTORY_BATCHES {
        int batch_id PK
        string store_id FK
        int medicine_id FK
        string batch_number
        date expiry_date
        date mfg_date
        int initial_quantity
        int current_quantity
        float purchase_cost
        float selling_price
        int location_id FK
        int supplier_id FK
        string status
        int verification_flag
    }

    STORAGE_LOCATIONS {
        int location_id PK
        string store_id FK
        string shelf_name
        string rack_number
        string bin_number
        int capacity
        int is_active
    }

    SUPPLIERS {
        int supplier_id PK
        string store_id FK
        string supplier_name
        string contact_person
        string phone
        string email
        string status
    }

    PURCHASE_ORDERS {
        int purchase_id PK
        string store_id FK
        int supplier_id FK
        string invoice_number
        date purchase_date
        float total_amount
        string status
        int created_by FK
    }

    PURCHASE_ITEMS {
        int item_id PK
        int purchase_id FK
        int medicine_id FK
        int quantity
        float unit_cost
        float subtotal
    }

    PURCHASE_ITEM_BATCHES {
        int batch_receipt_id PK
        int item_id FK
        int batch_id FK
        string batch_number
        date expiry_date
        int quantity
    }

    SALES {
        int sale_id PK
        string store_id FK
        string invoice_number
        string patient_name
        string patient_phone
        float subtotal
        float discount_amount
        float tax_amount
        float rounding_amount
        float total_amount
        string payment_method
        string payment_reference
        string status
        int user_id FK
        timestamp sale_date
    }

    SALE_ITEMS {
        int item_id PK
        string store_id FK
        int sale_id FK
        int medicine_id FK
        int quantity
        float price
        float subtotal
    }

    SALE_BATCH_ALLOCATIONS {
        int allocation_id PK
        int sale_item_id FK
        int batch_id FK
        int quantity
        float unit_price
        float subtotal
    }

    SALE_RETURNS {
        int return_id PK
        string store_id FK
        int sale_id FK
        string invoice_number
        timestamp return_date
        float total_refund
        string refund_method
        string reason
        int created_by FK
    }

    SALE_RETURN_ITEMS {
        int return_item_id PK
        int return_id FK
        int sale_item_id FK
        int medicine_id FK
        int batch_id FK
        int quantity
        float refund_amount
        string restock_condition
    }

    STOCK_MOVEMENTS {
        int movement_id PK
        string store_id FK
        int medicine_id FK
        int batch_id FK
        string movement_type
        int quantity_delta
        int resulting_quantity
        string reference_type
        string reference_id
        timestamp created_at
    }

    AUDIT_LOGS {
        int log_id PK
        string store_id FK
        int user_id FK
        string action_type
        string entity_type
        int entity_id
        string details
        timestamp created_at
    }
```

---

## 3. Use-Case Diagram

```mermaid
graph LR
    OwnerAdmin((Owner / Admin))
    Pharmacist((Pharmacist))
    Cashier((Cashier))
    InvMgr((Inventory Manager))

    subgraph Pharmacy_Management_System ["Pharmacy Management System (POS & ERP)"]
        UC_Auth["Login / Switch Store / Logout"]
        UC_Store["Store Settings & Configuration"]
        UC_User["User & Role Management"]
        UC_POS["POS Billing (Cash/UPI/Card & Phone Validation)"]
        UC_Receipt["Reprint Receipts & Invoices"]
        UC_Reconcile["Cashier Shift Reconciliation"]
        UC_Return["Process Sale Returns & Refunds"]
        UC_MedCRUD["Medicine Catalog & Search CRUD"]
        UC_Dispense["Inspect Batch Expiry & Dispensing"]
        UC_Supp["Supplier Onboarding & Oversight"]
        UC_PO["Create PO & Receive Multi-Batch Goods"]
        UC_Shelf["Shelf & Bin Allocation Management"]
        UC_StockMove["Stock Adjustments & Expiry Write-Offs"]
        UC_Rep["Sales, Inventory & Valuation Reports (CSV)"]
        UC_Audit["Audit Trail Inspection"]
        UC_Quality["Quality Engineering (FMEA / SQC / PDCA)"]
    end

    OwnerAdmin --> UC_Auth
    OwnerAdmin --> UC_Store
    OwnerAdmin --> UC_User
    OwnerAdmin --> UC_Supp
    OwnerAdmin --> UC_PO
    OwnerAdmin --> UC_Rep
    OwnerAdmin --> UC_Audit
    OwnerAdmin --> UC_Quality

    Pharmacist --> UC_Auth
    Pharmacist --> UC_MedCRUD
    Pharmacist --> UC_Dispense
    Pharmacist --> UC_Quality

    Cashier --> UC_Auth
    Cashier --> UC_POS
    Cashier --> UC_Receipt
    Cashier --> UC_Reconcile
    Cashier --> UC_Return

    InvMgr --> UC_Auth
    InvMgr --> UC_Supp
    InvMgr --> UC_PO
    InvMgr --> UC_Shelf
    InvMgr --> UC_StockMove
    InvMgr --> UC_Rep
```

---

## 4. Role-Permission Matrix

```mermaid
graph TD
    subgraph Roles ["Canonical Application Roles"]
        R_Owner["Owner (Full Cross-Store Scope)"]
        R_Admin["Admin (Full Store Administration)"]
        R_Pharma["Pharmacist (Clinical & Dispensing Scope)"]
        R_Cashier["Cashier (POS Billing & Shift Scope)"]
        R_Inv["Inventory Manager (Purchasing & Warehouse Scope)"]
    end

    subgraph Permission_Gates ["Backend Permission Gates (services/rbac.py)"]
        P_USER["MANAGE_USERS"]
        P_STORE["MANAGE_STORE_SETTINGS"]
        P_AUDIT["VIEW_AUDIT_LOGS"]
        P_REP["VIEW_REPORTS / EXPORT_CSV"]
        P_POS["PROCESS_SALE / BILLING"]
        P_RET["PROCESS_RETURNS"]
        P_RECON["VIEW_CASHIER_RECONCILIATION"]
        P_MED["MANAGE_MEDICINES"]
        P_BATCH["MANAGE_BATCHES / SHELVES"]
        P_PURCH["MANAGE_PURCHASING / RECEIVE_GOODS"]
    end

    R_Owner --> P_USER
    R_Owner --> P_STORE
    R_Owner --> P_AUDIT
    R_Owner --> P_REP
    R_Owner --> P_POS
    R_Owner --> P_RET
    R_Owner --> P_MED
    R_Owner --> P_BATCH
    R_Owner --> P_PURCH

    R_Admin --> P_USER
    R_Admin --> P_STORE
    R_Admin --> P_AUDIT
    R_Admin --> P_REP
    R_Admin --> P_POS
    R_Admin --> P_RET
    R_Admin --> P_MED
    R_Admin --> P_BATCH
    R_Admin --> P_PURCH

    R_Pharma --> P_MED
    R_Pharma --> P_BATCH

    R_Cashier --> P_POS
    R_Cashier --> P_RET
    R_Cashier --> P_RECON

    R_Inv --> P_BATCH
    R_Inv --> P_PURCH
    R_Inv --> P_REP
```

---

## 5. Authentication & Authorization Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as User (Cashier / Admin)
    participant UI as LoginPanel / MainWindow
    participant Auth as AuthService
    participant RBAC as rbac.py
    participant DB as SQLite DB

    User->>UI: Enter Username & Password
    UI->>Auth: login(username, password)
    Auth->>DB: SELECT * FROM users WHERE username = ?
    DB-->>Auth: User Record (PBKDF2 Hash, Role, StoreID, is_active)
    
    alt Account Inactive
        Auth-->>UI: Error: "Account deactivated"
    else Invalid Password
        Auth->>Auth: Constant-time PBKDF2 hash verification
        Auth-->>UI: Error: "Invalid credentials"
    else Authentication Succeeded
        Auth->>DB: INSERT INTO audit_logs (USER_LOGIN)
        Auth-->>UI: Authenticated User Object (Role, StoreID)
        UI->>UI: Render Theme & Role Sidebar
    end

    User->>UI: Trigger Service Action (e.g., process_sale)
    UI->>RBAC: require_permission(acting_user, PERM_PROCESS_SALE)
    alt Permission Denied
        RBAC-->>UI: Raise PermissionError (403 Forbidden)
    else Store Mismatch
        RBAC->>RBAC: require_store_access(acting_user, target_store)
        RBAC-->>UI: Raise PermissionError ("Cross-store access denied")
    else Access Granted
        RBAC-->>UI: Proceed with Service Execution
    end
```

---

## 6. Purchase & Goods-Receiving Workflow

```mermaid
sequenceDiagram
    autonumber
    actor InvMgr as Inventory Manager
    participant UI as PurchaseEntryView
    participant PSvc as PurchaseService
    participant SSvc as ShelfService
    participant DB as SQLite DB

    InvMgr->>UI: Select Supplier & Enter Invoice No
    InvMgr->>UI: Add Medicines, Quantities & Purchase Costs
    UI->>PSvc: create_purchase_order(supplier_id, items)
    PSvc->>DB: INSERT INTO purchase_orders (status='Pending')
    DB-->>PSvc: purchase_id

    InvMgr->>UI: Receive Goods & Enter Batches (BatchNo, Expiry, Location)
    UI->>SSvc: validate_shelf_assignment(store_id, medicine_id, expiry_date, location_id)
    alt Shelf Expiry Conflict Detected
        SSvc-->>UI: Error: "Same medicine with different expiry cannot share shelf"
    else Shelf Validated
        UI->>PSvc: receive_goods(purchase_id, received_batches)
        PSvc->>DB: BEGIN TRANSACTION
        loop For Each Batch
            PSvc->>DB: INSERT INTO inventory_batches (current_qty, cost, price, loc)
            PSvc->>DB: INSERT INTO purchase_item_batches
            PSvc->>DB: INSERT INTO stock_movements (GOODS_RECEIPT, +qty)
            PSvc->>DB: UPDATE medicines SET quantity = quantity + ?
        end
        PSvc->>DB: UPDATE purchase_orders SET status = 'Received'
        PSvc->>DB: INSERT INTO audit_logs (PURCHASE_RECEIPT)
        PSvc->>DB: COMMIT TRANSACTION
        PSvc-->>UI: Success: Goods received and stock updated atomically
    end
```

---

## 7. Batch & Shelf Allocation Workflow

```mermaid
flowchart TD
    Start([Receive Medicine Batch]) --> CheckShelf{Assign Shelf Location}
    CheckShelf --> QueryExisting[Query existing batches on chosen shelf]
    QueryExisting --> AnyBatch{Are batches present on shelf?}
    
    AnyBatch -- No --> AllowAssignment[Assign Shelf Location Successfully]
    AnyBatch -- Yes --> CheckMed{Is same medicine present on shelf?}
    
    CheckMed -- No (Different Medicine) --> AllowShare[Allowed: Different medicines can share shelf]
    CheckMed -- Yes (Same Medicine) --> CheckExpiry{Does new batch have identical expiry date?}
    
    CheckExpiry -- Yes (Same Expiry) --> AllowSameExpiry[Allowed: Same medicine with identical expiry shares shelf]
    CheckExpiry -- No (Different Expiry) --> RejectConflict[BLOCKED: Same medicine with different expiry must use distinct shelf]
    
    AllowAssignment --> SaveDB[(Update inventory_batches location_id)]
    AllowShare --> SaveDB
    AllowSameExpiry --> SaveDB
    RejectConflict --> AlertUser[Display Shelf Conflict Warning & Prompt New Shelf]
```

---

## 8. FEFO Allocation Algorithm

```mermaid
flowchart TD
    Start([Checkout Request: Med ID, Requested Qty]) --> LoadBatches[Query Eligible Batches for Store & Medicine]
    LoadBatches --> FilterRules{Filter Active Batches}
    
    FilterRules --> ExcludeExpired[Exclude expiry_date < today]
    FilterRules --> ExcludeZero[Exclude current_quantity <= 0]
    FilterRules --> ExcludeQuarantine[Exclude verification_flag != 0]
    FilterRules --> ExcludeInactive[Exclude status != 'Active']
    
    ExcludeExpired & ExcludeZero & ExcludeQuarantine & ExcludeInactive --> SortFEFO[Sort by Expiry ASC, Created ASC, BatchID ASC]
    SortFEFO --> SumStock{Total Eligible Stock >= Requested Qty?}
    
    SumStock -- No --> RollbackAbort[ABORT & ROLLBACK: Insufficient Stock Error]
    SumStock -- Yes --> InitLoop[Remaining Qty = Requested Qty]
    
    InitLoop --> ForEachBatch[Iterate Through Sorted Batches]
    ForEachBatch --> DeductCalc[Deduct Qty = min(Remaining Qty, Batch Current Qty)]
    DeductCalc --> DeductBatch[Deduct from Batch: current_quantity -= Deduct Qty]
    DeductBatch --> RecordAlloc[Insert sale_batch_allocations Record]
    DeductBatch --> RecordLedger[Insert stock_movements SALE_DISPENSE -Deduct Qty]
    DeductBatch --> UpdateRemaining[Remaining Qty -= Deduct Qty]
    
    UpdateRemaining --> MoreNeeded{Remaining Qty > 0?}
    MoreNeeded -- Yes --> ForEachBatch
    MoreNeeded -- No --> CompleteFEFO[FEFO Allocation Complete & Verified]
```

---

## 9. POS Billing & Payment Workflow

```mermaid
sequenceDiagram
    autonumber
    actor Cashier as Cashier
    participant UI as POS Billing View
    participant Val as validators.py
    participant SalesSvc as SalesService
    participant DB as SQLite DB

    Cashier->>UI: Search & Add Medicines to Cart
    Cashier->>UI: Enter Customer Name & Phone Number
    UI->>Val: validate_indian_phone(phone)
    alt Phone Invalid
        Val-->>UI: False ("Enter a valid 10-digit Indian mobile number.")
        UI->>UI: Show red inline alert & block checkout
    else Phone Valid
        Val-->>UI: True, normalized_phone
        UI->>Val: calculate_bill_totals(subtotal, discount, tax_rate)
        Val-->>UI: Subtotal, Discount, Tax, Rounding (ROUND_HALF_UP), Grand Total
    end

    Cashier->>UI: Select Payment: Cash / UPI / Card (+ Auth Ref)
    Cashier->>UI: Click Complete Sale
    UI->>SalesSvc: process_sale(cart, phone, payment_method, ref, discount, tax)
    SalesSvc->>SalesSvc: Execute FEFO Algorithm & Stock Checks
    SalesSvc->>DB: BEGIN TRANSACTION
    SalesSvc->>DB: INSERT INTO sales (invoice_num, patient_phone, totals, payment_method)
    SalesSvc->>DB: INSERT INTO sale_items & sale_batch_allocations
    SalesSvc->>DB: UPDATE inventory_batches & medicines
    SalesSvc->>DB: INSERT INTO stock_movements (SALE_DISPENSE, -qty)
    SalesSvc->>DB: INSERT INTO audit_logs (SALE_CHECKOUT)
    SalesSvc->>DB: COMMIT TRANSACTION
    SalesSvc-->>UI: Return Success, sale_id, invoice_number
    UI->>UI: Display InvoiceReceiptModal (Print / Reprint Ready)
```

---

## 10. Stock Movement Lifecycle

```mermaid
stateDiagram-v2
    [*] --> GoodsReceiving : Purchase Order Received
    GoodsReceiving --> ActiveInventory : Movement: GOODS_RECEIPT (+qty)
    
    ActiveInventory --> Dispensed : POS Checkout: SALE_DISPENSE (-qty)
    Dispensed --> [*] : Consumed by Patient

    Dispensed --> CustomerReturn : Authorized Return
    CustomerReturn --> ActiveInventory : Condition SELLABLE: CUSTOMER_RETURN (+qty)
    CustomerReturn --> Quarantined : Condition DAMAGED / EXPIRED: RETURN_QUARANTINE

    ActiveInventory --> ShelfRelocation : Warehouse Move: RELOCATION (loc_a -> loc_b)
    ShelfRelocation --> ActiveInventory

    ActiveInventory --> Quarantined : Quality Audit Flag: QUARANTINE
    Quarantined --> ActiveInventory : Re-verified: UNQUARANTINE
    Quarantined --> WrittenOff : Expiry Disposal: EXPIRY_WRITEOFF (-qty)
    ActiveInventory --> WrittenOff : Stock Damage: DAMAGE_WRITEOFF (-qty)
    WrittenOff --> [*]
```

---

## 11. Returns and Refunds Workflow

```mermaid
sequenceDiagram
    autonumber
    actor Cashier as Cashier / Pharmacist
    participant UI as Returns Management Modal
    participant SalesSvc as SalesService
    participant DB as SQLite DB

    Cashier->>UI: Search Original Invoice / Sale ID
    UI->>SalesSvc: get_sale_details(sale_id)
    SalesSvc->>DB: SELECT s.*, si.*, sba.* FROM sales ...
    DB-->>SalesSvc: Sale Header, Items, Allocated Batches
    SalesSvc-->>UI: Display Sale Details & Returnable Quantities

    Cashier->>UI: Select Item, Return Qty, Restock Condition & Reason
    UI->>SalesSvc: process_sale_return(sale_id, return_items, reason)
    SalesSvc->>SalesSvc: Validate: previously_returned + requested <= original_qty
    alt Over-Return Attempted
        SalesSvc-->>UI: Error: "Cannot return more than originally purchased quantity"
    else Return Validated
        SalesSvc->>DB: BEGIN TRANSACTION
        SalesSvc->>DB: INSERT INTO sale_returns (total_refund, refund_method, reason)
        loop For Each Returned Item
            SalesSvc->>DB: INSERT INTO sale_return_items (condition, refund_amt)
            alt Condition is SELLABLE and Batch Not Expired
                SalesSvc->>DB: UPDATE inventory_batches SET current_qty = current_qty + ?
                SalesSvc->>DB: UPDATE medicines SET quantity = quantity + ?
                SalesSvc->>DB: INSERT INTO stock_movements (CUSTOMER_RETURN, +qty)
            else Condition is DAMAGED or EXPIRED
                SalesSvc->>DB: INSERT INTO stock_movements (RETURN_DAMAGED_EXCLUDED, 0)
            end
        end
        SalesSvc->>DB: INSERT INTO audit_logs (SALE_RETURN)
        SalesSvc->>DB: COMMIT TRANSACTION
        SalesSvc-->>UI: Success: Refund processed & inventory adjusted safely
    end
```

---

## 12. Database Transaction and Rollback Flow

```mermaid
sequenceDiagram
    autonumber
    participant App as SalesService / PurchaseService
    participant DB as SQLite Connection
    participant Ledger as Stock Movements & Batches

    App->>DB: BEGIN IMMEDIATE TRANSACTION
    
    App->>DB: Step 1: Update Header (Sales / Purchase)
    alt Step 1 Database Error (e.g., UNIQUE constraint violation)
        DB-->>App: Database Exception
        App->>DB: ROLLBACK TRANSACTION
        App-->>App: Restore In-Memory State & Return Error to User
    end

    App->>Ledger: Step 2: Atomic Batch Stock Deduction (WHERE current_qty >= requested)
    alt Step 2 Conflict (Concurrent modification or insufficient stock)
        Ledger-->>App: rowcount == 0 (Poka-Yoke Stock Conflict)
        App->>DB: ROLLBACK TRANSACTION
        App-->>App: Stock Untouched, Zero Partial Changes Written
    end

    App->>DB: Step 3: Record Movement Ledger & Audit Logs
    alt Step 3 Failure (Disk full or table lock)
        DB-->>App: Exception
        App->>DB: ROLLBACK TRANSACTION
        App-->>App: Completely Discard Transaction
    end

    App->>DB: Step 4: All Validations & Operations Succeeded
    App->>DB: COMMIT TRANSACTION
    DB-->>App: Commit Acknowledged (Atomic Durability)
```

---

## 13. Report Generation and Data Flow

```mermaid
flowchart TD
    Trigger([User Triggers Report: Sales / Inventory / Cashier / Valuation]) --> Gate{Role & Store Authorization Check}
    Gate -- Unauthorized --> Deny[Raise PermissionError / Block UI]
    Gate -- Authorized --> QueryParams[Bind Active StoreID & Date Filters]

    QueryParams --> RunQuery[Execute Optimized SQL Aggregations on SQLite]
    RunQuery --> RawData[Raw Database Records & Financial Metrics]

    RawData --> DataProcessor{Report Type}
    
    DataProcessor -- Sales Summary --> ProcessSales[Aggregate Gross, Cash, UPI, Card, Net Sales]
    DataProcessor -- Cashier Performance --> ProcessCashier[Compute Bills Count, Revenue & Returns per Cashier]
    DataProcessor -- Inventory Valuation --> ProcessInv[Partition: Physical, Sellable, Expired & Quarantined]
    DataProcessor -- Medicine Performance --> ProcessMeds[Compute Units Sold & Revenue per Drug]

    ProcessSales & ProcessCashier & ProcessInv & ProcessMeds --> ViewAdapter[Format Formatted Data Objects]
    
    ViewAdapter --> UI_Table[Render Interactive CustomTkinter Table]
    ViewAdapter --> ExportHandler{User Clicks Export CSV}
    
    ExportHandler -- Yes --> CSVWriter[Write UTF-8 Parameterized CSV File to Disk]
    CSVWriter --> NotifyUser[Show File Saved Toast Notification]
```
