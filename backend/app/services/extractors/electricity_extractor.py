"""
CarbonLedger AI — Electricity PDF Extraction Engine
===================================================
Extracts structured billing data from PyMuPDF-parsed PDF text:
- Billing start & end dates.
- Energy consumption (kWh / MWh).
- Utility supplier name & account/invoice identifier.
- Exact source page numbers and verbatim text snippet citations.
- Enforces human-review flags for missing data or low confidence.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.core.logging import get_logger
from app.schemas.extraction import (
    EvidenceReferenceLocation,
    ExtractedActivityItem,
    ReviewFlagType,
)
from app.services.nexus_client import NexusClient

logger = get_logger(__name__)

ELECTRICITY_PROMPT = """You are a rigorous carbon accounting auditor inspecting an electricity utility bill.
Extract all relevant activity data.
CRITICAL AUDIT RULES:
1. NEVER invent, estimate, or assume numbers, dates, or units.
2. If a value is not explicitly present in the text, return null.
3. Denominator must match electricity consumption (kWh or MWh).
4. Identify the exact page number where the consumption figure appears.

Extracted PDF text:
\"\"\"{pdf_text}\"\"\"

Return a valid JSON object matching this schema:
{{
  "supplier_name": string or null,
  "account_or_invoice_number": string or null,
  "billing_period_start": "YYYY-MM-DD" or null,
  "billing_period_end": "YYYY-MM-DD" or null,
  "quantity": number or null,
  "unit": string or null,
  "confidence": number between 0.0 and 1.0,
  "source_page": integer (1-based) or null,
  "evidence_snippet": string or null
}}"""


def extract_electricity_from_pdf(
    pdf_parsed_data: Dict[str, Any],
    nexus_client: NexusClient,
) -> List[ExtractedActivityItem]:
    """
    Executes electricity bill extraction using Nexus AI.
    Applies deterministic review flags and normalization.
    """
    full_text = pdf_parsed_data.get("full_text", "")
    if not full_text.strip():
        # Scanned page with zero text -> requires human review / OCR
        return [
            ExtractedActivityItem(
                evidence_type="electricity",
                confidence=Decimal("0.20"),
                needs_human_review=True,
                review_flags=[ReviewFlagType.MISSING_VALUE.value, ReviewFlagType.UNCERTAIN_EXTRACTION.value],
                review_reasons=["Document is a scanned image with no selectable text layer. Manual verification required."],
                location=EvidenceReferenceLocation(page_number=1, raw_text_snippet="Scanned raster image"),
            )
        ]

    prompt = ELECTRICITY_PROMPT.format(pdf_text=full_text[:4000])
    messages = [
        {"role": "system", "content": "You are a specialized carbon data extractor. Always return pure JSON."},
        {"role": "user", "content": prompt},
    ]

    res = nexus_client.chat_completion(messages=messages, temperature=0.0)
    data = res.get("data", {})

    raw_qty = data.get("quantity")
    raw_unit = data.get("unit")
    conf_val = Decimal(str(data.get("confidence", 0.5)))
    page_num = data.get("source_page") or 1

    review_flags: List[str] = []
    review_reasons: List[str] = []
    needs_review = False

    # Check for missing quantity
    dec_qty: Optional[Decimal] = None
    if raw_qty is not None:
        try:
            dec_qty = Decimal(str(raw_qty))
        except Exception:
            needs_review = True
            review_flags.append(ReviewFlagType.MISSING_VALUE.value)
            review_reasons.append(f"Invalid numerical quantity parsed: '{raw_qty}'")
    else:
        needs_review = True
        review_flags.append(ReviewFlagType.MISSING_VALUE.value)
        review_reasons.append("Missing electricity consumption quantity in bill text.")

    # Check confidence
    if conf_val < Decimal("0.80"):
        needs_review = True
        review_flags.append(ReviewFlagType.UNCERTAIN_EXTRACTION.value)
        review_reasons.append(f"Extraction confidence is below threshold ({conf_val} < 0.80).")

    # Unit normalization (kWh)
    norm_val: Optional[Decimal] = None
    norm_unit: Optional[str] = None
    if dec_qty is not None and raw_unit:
        u_lower = raw_unit.lower().strip()
        if u_lower == "kwh":
            norm_val = dec_qty
            norm_unit = "kWh"
        elif u_lower == "mwh":
            # 1 MWh = 1000 kWh
            norm_val = dec_qty * Decimal("1000")
            norm_unit = "kWh"
        elif u_lower == "gwh":
            norm_val = dec_qty * Decimal("1000000")
            norm_unit = "kWh"
        else:
            needs_review = True
            review_flags.append(ReviewFlagType.AMBIGUOUS_UNIT.value)
            review_reasons.append(f"Non-standard electricity unit '{raw_unit}'.")
    elif dec_qty is not None and not raw_unit:
        needs_review = True
        review_flags.append(ReviewFlagType.AMBIGUOUS_UNIT.value)
        review_reasons.append("Electricity quantity extracted without a specified unit.")

    item = ExtractedActivityItem(
        evidence_type="electricity",
        supplier_name=data.get("supplier_name"),
        invoice_or_account_number=data.get("account_or_invoice_number"),
        period_start=data.get("billing_period_start"),
        period_end=data.get("billing_period_end"),
        raw_value=dec_qty,
        raw_unit=raw_unit,
        normalised_value=norm_val,
        normalised_unit=norm_unit,
        confidence=conf_val,
        location=EvidenceReferenceLocation(
            page_number=page_num,
            raw_text_snippet=data.get("evidence_snippet"),
        ),
        needs_human_review=needs_review,
        review_flags=review_flags,
        review_reasons=review_reasons,
    )
    return [item]
