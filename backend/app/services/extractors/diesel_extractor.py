"""
CarbonLedger AI — Diesel Fuel Invoice Extraction Engine
=======================================================
Extracts diesel delivery quantities from invoice images/text:
- Fuel volume (Litres / kL).
- Supplier name (e.g. Bharat Petroleum, Indian Oil, Shell).
- Delivery/invoice date and invoice number.
- Evidence reference location.
- Strict density rule: rejects automatic mass-to-volume conversion without documented density.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.core.logging import get_logger
from app.schemas.extraction import (
    EvidenceReferenceLocation,
    ExtractedActivityItem,
    ReviewFlagType,
)
from app.services.nexus_client import NexusClient

logger = get_logger(__name__)

DIESEL_PROMPT = """You are a carbon accounting auditor extracting activity data from a diesel fuel invoice.
CRITICAL RULES:
1. Extract the diesel quantity and unit explicitly stated on the invoice.
2. NEVER guess or invent missing numbers.
3. If quantity or date is missing, return null.

Invoice context:
\"\"\"{context_text}\"\"\"

Return a valid JSON object matching this schema:
{{
  "supplier_name": string or null,
  "invoice_or_account_number": string or null,
  "invoice_date": "YYYY-MM-DD" or null,
  "quantity": number or null,
  "unit": string or null,
  "confidence": number between 0.0 and 1.0,
  "evidence_snippet": string or null
}}"""


def extract_diesel_from_invoice(
    invoice_parsed_data: Dict[str, Any],
    nexus_client: NexusClient,
    ocr_text: Optional[str] = None,
) -> List[ExtractedActivityItem]:
    """
    Extracts diesel invoice activity using Nexus AI with unit normalization
    and strict dimensional verification.
    """
    context = ocr_text or invoice_parsed_data.get("ocr_text") or (
        f"Photographed fuel invoice. Format: {invoice_parsed_data.get('format', 'JPEG')}. "
        f"Dimensions: {invoice_parsed_data.get('normalized_dimensions', {})}. "
        "Delivery receipt for commercial diesel supply."
    )

    prompt = DIESEL_PROMPT.format(context_text=context)
    messages = [
        {"role": "system", "content": "You are a meticulous auditor. Always output pure valid JSON."},
        {"role": "user", "content": prompt},
    ]

    res = nexus_client.chat_completion(messages=messages, temperature=0.0)
    data = res.get("data", {})

    raw_qty = data.get("quantity")
    raw_unit = data.get("unit")
    conf_val = Decimal(str(data.get("confidence", 0.7)))

    review_flags: List[str] = []
    review_reasons: List[str] = []
    needs_review = False

    dec_qty: Optional[Decimal] = None
    if raw_qty is not None:
        try:
            dec_qty = Decimal(str(raw_qty))
        except Exception:
            needs_review = True
            review_flags.append(ReviewFlagType.MISSING_VALUE.value)
            review_reasons.append(f"Invalid numerical diesel quantity: '{raw_qty}'")
    else:
        needs_review = True
        review_flags.append(ReviewFlagType.MISSING_VALUE.value)
        review_reasons.append("Missing diesel volume quantity in invoice.")

    if conf_val < Decimal("0.80"):
        needs_review = True
        review_flags.append(ReviewFlagType.UNCERTAIN_EXTRACTION.value)
        review_reasons.append(f"Confidence score ({conf_val}) is below verification threshold 0.80.")

    # Unit normalization and strict dimensional check
    norm_val: Optional[Decimal] = None
    norm_unit: Optional[str] = None

    if dec_qty is not None and raw_unit:
        u_lower = raw_unit.lower().strip()
        if u_lower in ("l", "litre", "litres", "liter", "liters"):
            norm_val = dec_qty
            norm_unit = "litres"
        elif u_lower in ("kl", "kilolitre", "kilolitres"):
            # 1.5 kL * 1000 = 1500 litres
            norm_val = dec_qty * Decimal("1000")
            norm_unit = "litres"
        elif u_lower in ("m3", "cubic meter", "cubic metres"):
            # 1 m3 = 1000 litres
            norm_val = dec_qty * Decimal("1000")
            norm_unit = "litres"
        elif u_lower in ("kg", "kilogram", "tonne", "tonnes", "mt"):
            # CRITICAL RULE: A fuel invoice in kilograms cannot automatically be converted to litres without a documented density
            needs_review = True
            review_flags.append(ReviewFlagType.AMBIGUOUS_UNIT.value)
            review_reasons.append(
                f"Fuel quantity stated in mass ({raw_unit}) cannot automatically be converted to litres without a documented fuel density."
            )
            norm_val = dec_qty
            norm_unit = raw_unit
        else:
            needs_review = True
            review_flags.append(ReviewFlagType.AMBIGUOUS_UNIT.value)
            review_reasons.append(f"Unknown or non-standard fuel unit: '{raw_unit}'")
    elif dec_qty is not None:
        needs_review = True
        review_flags.append(ReviewFlagType.AMBIGUOUS_UNIT.value)
        review_reasons.append("Diesel invoice quantity extracted without a specified unit.")

    item = ExtractedActivityItem(
        evidence_type="diesel",
        supplier_name=data.get("supplier_name"),
        invoice_or_account_number=data.get("invoice_or_account_number"),
        period_start=data.get("invoice_date"),
        period_end=data.get("invoice_date"),
        raw_value=dec_qty,
        raw_unit=raw_unit,
        normalised_value=norm_val,
        normalised_unit=norm_unit,
        confidence=conf_val,
        location=EvidenceReferenceLocation(
            raw_text_snippet=data.get("evidence_snippet") or "Photographed fuel delivery invoice",
        ),
        needs_human_review=needs_review,
        review_flags=review_flags,
        review_reasons=review_reasons,
    )
    return [item]
