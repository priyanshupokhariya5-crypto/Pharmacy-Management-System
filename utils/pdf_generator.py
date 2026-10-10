import os
from fpdf import FPDF
from typing import Dict, Any

def generate_invoice_pdf(sale_details: Dict[str, Any], filepath: str) -> bool:
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        
        # Header
        pdf.cell(190, 10, "PHARMACY MANAGEMENT SYSTEM", ln=True, align="C")
        pdf.set_font("Arial", "", 12)
        pdf.cell(190, 10, "Official Sales & Transaction Invoice", ln=True, align="C")
        pdf.ln(10)
        
        # Meta Info
        pdf.set_font("Arial", "B", 12)
        pdf.cell(95, 8, f"Invoice #: {sale_details.get('invoice_number', 'N/A')}", ln=False)
        pdf.cell(95, 8, f"Date: {sale_details.get('sale_date', 'N/A')}", ln=True)
        
        pdf.set_font("Arial", "", 12)
        pdf.cell(95, 8, f"Patient Name: {sale_details.get('patient_name', 'N/A')}", ln=False)
        cashier = sale_details.get("username") or "System User"
        pdf.cell(95, 8, f"Billed By: {cashier}", ln=True)
        
        patient_phone = sale_details.get('patient_phone') or ""
        patient_age = sale_details.get('patient_age') or ""
        if patient_phone or patient_age:
            p_extra = f"Phone: {patient_phone}" if patient_phone else ""
            a_extra = f"Age: {patient_age}" if patient_age else ""
            combined = " | ".join(filter(None, [p_extra, a_extra]))
            pdf.cell(190, 8, f"Patient Details: {combined}", ln=True)
            
        pdf.ln(5)
        
        # Table Header
        pdf.set_font("Arial", "B", 10)
        pdf.set_fill_color(200, 200, 200)
        pdf.cell(30, 8, "Code", border=1, fill=True)
        pdf.cell(80, 8, "Medicine Name", border=1, fill=True)
        pdf.cell(20, 8, "Qty", border=1, fill=True, align="C")
        pdf.cell(30, 8, "Price (Rs)", border=1, fill=True, align="R")
        pdf.cell(30, 8, "Subtotal (Rs)", border=1, fill=True, align="R")
        pdf.ln()
        
        # Table Rows
        pdf.set_font("Arial", "", 10)
        items = sale_details.get("items", [])
        total_qty = 0
        for item in items:
            total_qty += item["quantity"]
            code = item.get("medicine_code", "")
            name = item.get("medicine_name", "")[:35]
            qty = str(item["quantity"])
            price = f"{item['price']:.2f}"
            sub = f"{item['subtotal']:.2f}"
            
            pdf.cell(30, 8, code, border=1)
            pdf.cell(80, 8, name, border=1)
            pdf.cell(20, 8, qty, border=1, align="C")
            pdf.cell(30, 8, price, border=1, align="R")
            pdf.cell(30, 8, sub, border=1, align="R")
            pdf.ln()
            
        pdf.ln(5)
        
        # Summary
        pdf.set_font("Arial", "B", 12)
        pdf.cell(130, 8, f"Total Items: {total_qty}", border=0, align="R")
        total_amount = sale_details.get("total_amount", 0.0)
        pdf.cell(60, 8, f"GRAND TOTAL: Rs {total_amount:.2f}", border=0, align="R")
        pdf.ln(15)
        
        pdf.set_font("Arial", "I", 10)
        pdf.cell(190, 10, "Thank you for your visit!", ln=True, align="C")
        
        pdf.output(filepath)
        return True
    except Exception as e:
        print(f"PDF Error: {e}")
        return False
