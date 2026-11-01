"""
PDF Invoice Generator for Pharmacy Management System.
Generates compliant, formatted customer tax and sales invoices with batch allocations.
"""
import os
import re
from fpdf import FPDF
from typing import Dict, Any, Optional


def _clean_str(val: Any) -> str:
    """Sanitizes strings for FPDF standard latin-1 encoding."""
    if val is None:
        return ""
    text = str(val)
    text = text.replace("₹", "Rs. ")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("'", "'").replace("'", "'").replace('"', '"').replace('"', '"')
    # Filter out characters outside latin-1
    return text.encode("latin-1", "replace").decode("latin-1")


def generate_invoice_pdf(sale_details: Dict[str, Any], filepath: Optional[str] = None) -> str:
    """
    Generates a PDF invoice document for a completed sale transaction.
    Returns the absolute path to the generated PDF file.
    """
    if not filepath:
        out_dir = os.path.abspath("invoices")
        os.makedirs(out_dir, exist_ok=True)
        raw_inv = sale_details.get("invoice_number") or f"INV_{sale_details.get('sale_id', '0')}"
        safe_inv = re.sub(r"[^A-Za-z0-9_-]", "_", str(raw_inv))
        filepath = os.path.join(out_dir, f"{safe_inv}.pdf")
    else:
        out_dir = os.path.dirname(os.path.abspath(filepath))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 8, _clean_str("PHARMACY MANAGEMENT SYSTEM"), ln=True, align="C")
    pdf.set_font("Arial", "", 11)
    pdf.cell(190, 6, _clean_str("Official Sales & Transaction Invoice Receipt"), ln=True, align="C")
    pdf.ln(6)

    # Horizontal Line
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # Meta Info
    pdf.set_font("Arial", "B", 10)
    inv_no = _clean_str(sale_details.get("invoice_number", f"INV-{sale_details.get('sale_id', 'N/A')}"))
    sale_dt = _clean_str(sale_details.get("sale_date", "N/A"))
    pdf.cell(95, 6, f"Invoice No: {inv_no}", ln=False)
    pdf.cell(95, 6, f"Date: {sale_dt}", ln=True, align="R")

    pdf.set_font("Arial", "", 10)
    pat_name = _clean_str(sale_details.get("patient_name") or "Walk-in Customer")
    cashier = _clean_str(sale_details.get("username") or "System User")
    pdf.cell(95, 6, f"Customer: {pat_name}", ln=False)
    pdf.cell(95, 6, f"Billed By: {cashier}", ln=True, align="R")

    pat_phone = _clean_str(sale_details.get("patient_phone") or "")
    pat_age = _clean_str(sale_details.get("patient_age") or "")
    status = _clean_str(sale_details.get("status") or "COMPLETED")
    p_info = []
    if pat_phone:
        p_info.append(f"Phone: {pat_phone}")
    if pat_age:
        p_info.append(f"Age: {pat_age}")
    if p_info:
        pdf.cell(95, 6, " | ".join(p_info), ln=False)
    else:
        pdf.cell(95, 6, "", ln=False)
    pdf.cell(95, 6, f"Status: {status}", ln=True, align="R")

    pdf.ln(4)

    # Table Header
    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(220, 230, 242)
    pdf.cell(25, 7, "Code", border=1, fill=True)
    pdf.cell(80, 7, "Medicine / Batch Allocation", border=1, fill=True)
    pdf.cell(20, 7, "Qty", border=1, fill=True, align="C")
    pdf.cell(32, 7, "Unit Price", border=1, fill=True, align="R")
    pdf.cell(33, 7, "Subtotal", border=1, fill=True, align="R")
    pdf.ln()

    # Table Items
    pdf.set_font("Arial", "", 9)
    items = sale_details.get("items", [])
    total_qty = 0
    for idx, item in enumerate(items):
        qty = int(item.get("quantity", 0))
        total_qty += qty
        code = _clean_str(item.get("medicine_code", ""))[:12]
        med_name = _clean_str(item.get("medicine_name", ""))
        batch_info = _clean_str(item.get("batch_details", ""))
        display_name = f"{med_name} [{batch_info}]" if batch_info else med_name
        display_name = display_name[:42]

        price = float(item.get("price", 0.0))
        subtotal = float(item.get("subtotal", 0.0))

        pdf.cell(25, 6, code, border=1)
        pdf.cell(80, 6, display_name, border=1)
        pdf.cell(20, 6, str(qty), border=1, align="C")
        pdf.cell(32, 6, f"Rs. {price:.2f}", border=1, align="R")
        pdf.cell(33, 6, f"Rs. {subtotal:.2f}", border=1, align="R")
        pdf.ln()

    pdf.ln(3)

    # Financial Summary
    subtotal_val = float(sale_details.get("subtotal", sale_details.get("total_amount", 0.0)))
    discount_val = float(sale_details.get("discount_amount", 0.0))
    grand_total_val = float(sale_details.get("total_amount", 0.0))
    pm = _clean_str(sale_details.get("payment_method", "Cash"))
    pref = _clean_str(sale_details.get("payment_reference") or "")

    pdf.set_font("Arial", "", 10)
    pdf.cell(125, 6, f"Total Items: {total_qty}", border=0)
    pdf.cell(65, 6, f"Subtotal: Rs. {subtotal_val:.2f}", border=0, align="R")
    pdf.ln()

    if discount_val > 0:
        pdf.cell(125, 6, "", border=0)
        pdf.cell(65, 6, f"Discount: -Rs. {discount_val:.2f}", border=0, align="R")
        pdf.ln()

    pdf.set_font("Arial", "B", 12)
    pay_note = f"Paid via {pm}" + (f" (Ref: {pref})" if pref else "")
    pdf.cell(110, 8, pay_note, border=0)
    pdf.cell(80, 8, f"GRAND TOTAL: Rs. {grand_total_val:.2f}", border=0, align="R")
    pdf.ln(12)

    # Footer Note
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(190, 6, _clean_str("Thank you for choosing us! Please retain this receipt for return/refund reference."), ln=True, align="C")
    pdf.cell(190, 5, _clean_str("Regulated under Indian Drug & Cosmetics Act - Standard Pharmacy Management System"), ln=True, align="C")

    pdf.output(filepath)
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        raise IOError(f"PDF creation failed: target file '{filepath}' is missing or empty.")

    return os.path.abspath(filepath)


def print_pdf(filepath: str) -> bool:
    """Sends the PDF file to the default printer or opens it for printing."""
    try:
        abs_path = os.path.abspath(filepath)
        if not os.path.exists(abs_path):
            return False
        if os.name == "nt":
            os.startfile(abs_path, "print")
        return True
    except Exception as e:
        print(f"Print PDF exception: {e}")
        return False


def generate_purchase_order_pdf(purchase_details: Dict[str, Any], filepath: Optional[str] = None) -> str:
    """
    Generates a PDF Purchase Order and Goods Receiving invoice document.
    Returns the absolute path to the generated PDF file.
    """
    if not filepath:
        out_dir = os.path.abspath("invoices")
        os.makedirs(out_dir, exist_ok=True)
        raw_inv = purchase_details.get("invoice_number") or f"PO_{purchase_details.get('purchase_id', '0')}"
        safe_inv = re.sub(r"[^A-Za-z0-9_-]", "_", str(raw_inv))
        filepath = os.path.join(out_dir, f"PO_{safe_inv}.pdf")
    else:
        out_dir = os.path.dirname(os.path.abspath(filepath))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(190, 8, _clean_str("PHARMACY MANAGEMENT SYSTEM"), ln=True, align="C")
    pdf.set_font("Arial", "", 11)
    pdf.cell(190, 6, _clean_str("Official Purchase Order & Supplier Procurement Invoice"), ln=True, align="C")
    pdf.ln(6)

    # Horizontal Line
    pdf.set_draw_color(180, 180, 180)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(4)

    # Meta Info
    pdf.set_font("Arial", "B", 10)
    po_no = _clean_str(purchase_details.get("invoice_number", f"PO-{purchase_details.get('purchase_id', 'N/A')}"))
    po_dt = _clean_str(purchase_details.get("purchase_date", "N/A"))
    pdf.cell(95, 6, f"PO / Invoice No: {po_no}", ln=False)
    pdf.cell(95, 6, f"Date: {po_dt}", ln=True, align="R")

    pdf.set_font("Arial", "", 10)
    supp_name = _clean_str(purchase_details.get("supplier_name") or f"Supplier ID {purchase_details.get('supplier_id', '')}")
    status = _clean_str(purchase_details.get("status") or "DRAFT")
    pdf.cell(95, 6, f"Supplier: {supp_name}", ln=False)
    pdf.cell(95, 6, f"Status: {status}", ln=True, align="R")

    store_id = _clean_str(purchase_details.get("store_id") or "")
    if store_id:
        pdf.cell(95, 6, f"Store ID: {store_id}", ln=False)
        pdf.cell(95, 6, f"Payment Status: {_clean_str(purchase_details.get('payment_status', 'PAID'))}", ln=True, align="R")

    pdf.ln(4)

    # Table Header
    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(220, 230, 242)
    pdf.cell(20, 7, "Item #", border=1, fill=True)
    pdf.cell(75, 7, "Medicine Description", border=1, fill=True)
    pdf.cell(30, 7, "Batch Number", border=1, fill=True, align="C")
    pdf.cell(20, 7, "Qty", border=1, fill=True, align="C")
    pdf.cell(22, 7, "Rate (Rs.)", border=1, fill=True, align="R")
    pdf.cell(23, 7, "Subtotal", border=1, fill=True, align="R")
    pdf.ln()

    # Table Items
    pdf.set_font("Arial", "", 9)
    items = purchase_details.get("items", [])
    total_qty = 0
    total_val = 0.0

    for idx, item in enumerate(items, start=1):
        if hasattr(item, "to_dict"):
            item_dict = item.to_dict()
        elif isinstance(item, dict):
            item_dict = item
        else:
            item_dict = vars(item)

        med_name = _clean_str(item_dict.get("medicine_name") or f"Medicine #{item_dict.get('medicine_id', '')}")
        batch_no = _clean_str(item_dict.get("batch_number") or item_dict.get("batch_no") or "-")
        qty = int(item_dict.get("quantity", 0))
        rate = float(item_dict.get("purchase_price", item_dict.get("price", 0.0)))
        subtotal = float(item_dict.get("subtotal", qty * rate))

        total_qty += qty
        total_val += subtotal

        pdf.cell(20, 6, str(idx), border=1)
        pdf.cell(75, 6, med_name[:38], border=1)
        pdf.cell(30, 6, batch_no[:15], border=1, align="C")
        pdf.cell(20, 6, str(qty), border=1, align="C")
        pdf.cell(22, 6, f"{rate:.2f}", border=1, align="R")
        pdf.cell(23, 6, f"{subtotal:.2f}", border=1, align="R")
        pdf.ln()

    pdf.ln(3)

    # Totals
    grand_total_val = float(purchase_details.get("total_amount", total_val))
    pdf.set_font("Arial", "", 10)
    pdf.cell(125, 6, f"Total Quantity: {total_qty} units across {len(items)} line item(s)", border=0)
    pdf.cell(65, 6, f"Items Total: Rs. {total_val:.2f}", border=0, align="R")
    pdf.ln()

    pdf.set_font("Arial", "B", 12)
    pdf.cell(110, 8, f"Procurement Status: {status}", border=0)
    pdf.cell(80, 8, f"TOTAL VALUE: Rs. {grand_total_val:.2f}", border=0, align="R")
    pdf.ln(12)

    # Footer
    pdf.set_font("Arial", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(190, 6, _clean_str("Authorized Purchase Order Document - Retain for vendor ledger reconciliation."), ln=True, align="C")
    pdf.cell(190, 5, _clean_str("Regulated under Good Distribution Practices (GDP) - Pharmacy Management System"), ln=True, align="C")

    pdf.output(filepath)
    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        raise IOError(f"PDF creation failed: target file '{filepath}' is missing or empty.")

    return os.path.abspath(filepath)
