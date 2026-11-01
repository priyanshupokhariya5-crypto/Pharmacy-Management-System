"""
Validation and Financial Utilities for Pharmacy POS and Management System.
Implements strict Indian mobile phone number validation, financial calculations,
and Poka-Yoke error prevention rules.
"""
import re
from typing import Tuple, Dict, Any, Optional


def validate_indian_phone(phone: Optional[str]) -> Tuple[bool, str, str]:
    """
    Validates customer phone number according to strict Indian mobile number rules:
    - Mandatory (cannot be empty or whitespace)
    - Exactly 10 digits
    - First digit must be between 6 and 9
    - No letters, signs, or special characters (after whitespace/hyphen normalization)
    - Stored as text string
    
    Returns:
        (is_valid: bool, error_message: str, cleaned_phone: str)
    """
    if phone is None:
        return False, "Customer mobile number is required.", ""

    # Normalization: strip leading/trailing whitespace
    raw_str = str(phone).strip()
    if not raw_str:
        return False, "Customer mobile number is required.", ""

    # Check for country code prefix '+91' or '91' if length is 12-13, but normalize
    # Standard format: exactly 10 digits starting with 6, 7, 8, or 9
    # If customer entered spaces or hyphens like "98765-43210" or "98765 43210", normalize:
    normalized = re.sub(r"[\s\-\(\)]", "", raw_str)

    # If it starts with +91, remove it
    if normalized.startswith("+91"):
        normalized = normalized[3:]
    elif normalized.startswith("91") and len(normalized) == 12:
        normalized = normalized[2:]
    elif normalized.startswith("0") and len(normalized) == 11:
        normalized = normalized[1:]

    # Check if purely digits
    if not normalized.isdigit():
        return False, "Enter a valid 10-digit Indian mobile number.", normalized

    # Check length
    if len(normalized) != 10:
        return False, "Enter a valid 10-digit Indian mobile number.", normalized

    # Check first digit (must be 6, 7, 8, or 9)
    if normalized[0] not in ("6", "7", "8", "9"):
        return False, "Enter a valid 10-digit Indian mobile number.", normalized

    return True, "", normalized


def calculate_bill_totals(
    subtotal: float,
    discount_amount: float = 0.0,
    tax_rate: float = 0.0,
    enable_rounding: bool = True
) -> Dict[str, float]:
    """
    Calculates validated bill financials with Poka-Yoke boundaries:
    - subtotal >= 0
    - 0 <= discount_amount <= subtotal
    - tax_amount = round((subtotal - discount_amount) * (tax_rate / 100), 2)
    - rounding_amount adjusts final total to nearest whole integer if enabled
    - grand_total = subtotal - discount_amount + tax_amount + rounding_amount
    """
    subtotal = round(max(0.0, float(subtotal)), 2)
    discount_amount = round(max(0.0, min(float(discount_amount), subtotal)), 2)
    taxable_amount = max(0.0, subtotal - discount_amount)
    
    tax_rate = max(0.0, float(tax_rate))
    tax_amount = round(taxable_amount * (tax_rate / 100.0), 2)
    
    unrounded_total = taxable_amount + tax_amount
    
    if enable_rounding:
        from decimal import Decimal, ROUND_HALF_UP
        d_unrounded = Decimal(str(unrounded_total))
        d_rounded = d_unrounded.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        rounded_total = float(d_rounded)
        rounding_amount = round(rounded_total - unrounded_total, 2)
        grand_total = rounded_total
    else:
        rounding_amount = 0.0
        grand_total = round(unrounded_total, 2)

    return {
        "subtotal": subtotal,
        "discount_amount": discount_amount,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "rounding_amount": rounding_amount,
        "grand_total": grand_total
    }
