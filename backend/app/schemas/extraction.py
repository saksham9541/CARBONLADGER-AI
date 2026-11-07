"""
CarbonLedger AI — Structured Extraction Output Schemas
======================================================
Strict Pydantic models for multimodal extraction output.
Enforces:
- Exact typing, Decimal precision, ISO dates.
- Evidence references (page #, cell coordinates, timestamps).
- Human-review flags for missing, uncertain, or conflicting values.
- AI NEVER computes emissions or invents missing quantities.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewFlagType(str, enum.Enum):
    MISSING_VALUE = "FLAG_MISSING_VALUE"
    UNCERTAIN_EXTRACTION = "FLAG_UNCERTAIN_EXTRACTION"
    AMBIGUOUS_UNIT = "FLAG_AMBIGUOUS_UNIT"
    CONFLICTING_VALUES = "FLAG_CONFLICTING_VALUES"
    UNSUPPORTED_DECLARATION = "FLAG_UNSUPPORTED_SUPPLIER_DECLARATION"


class EvidenceReferenceLocation(BaseModel):
    page_number: Optional[int] = Field(None, description="Source PDF page number (1-based)")
    bounding_box: Optional[List[float]] = Field(None, description="Bounding coordinates [x0, y0, x1, y1]")
    cell_coordinate: Optional[str] = Field(None, description="Spreadsheet cell coordinate, e.g. 'Sheet1!C14'")
    timestamp_range: Optional[str] = Field(None, description="Audio timestamp range, e.g. '00:00 - 00:02'")
    raw_text_snippet: Optional[str] = Field(None, description="Exact text verbatim from source")

    model_config = ConfigDict(protected_namespaces=())


class ExtractedActivityItem(BaseModel):
    evidence_type: str = Field(..., description="electricity | diesel | supplier_declaration | voice_note_explanation")
    supplier_name: Optional[str] = Field(None, description="Utility provider, vendor, or supplier name")
    invoice_or_account_number: Optional[str] = Field(None, description="Identifier for cross-referencing")
    period_start: Optional[date] = Field(None, description="Billing/delivery start date")
    period_end: Optional[date] = Field(None, description="Billing/delivery end date")

    # Raw extracted figures from document
    raw_value: Optional[Decimal] = Field(None, description="Extracted numerical quantity")
    raw_unit: Optional[str] = Field(None, description="Verbatim unit from document, e.g. kWh, Litres, kL")

    # Controlled normalised values (determined by backend rules, not invented by AI)
    normalised_value: Optional[Decimal] = Field(None, description="Standardised unit value (e.g. 1.5 kL -> 1500 L)")
    normalised_unit: Optional[str] = Field(None, description="Standardised unit: kWh, litres, etc.")

    confidence: Decimal = Field(..., ge=Decimal("0.0"), le=Decimal("1.0"), description="Extraction confidence score (0.0 to 1.0)")
    location: EvidenceReferenceLocation = Field(default_factory=EvidenceReferenceLocation)

    # Human review enforcement
    needs_human_review: bool = Field(default=False, description="Flagged for mandatory human auditor review")
    review_flags: List[str] = Field(default_factory=list, description="Machine-readable review codes")
    review_reasons: List[str] = Field(default_factory=list, description="Human-readable justification for review")

    model_config = ConfigDict(protected_namespaces=())

    @field_validator("confidence")
    @classmethod
    def round_confidence(cls, v: Decimal) -> Decimal:
        return round(v, 4)


class ExtractionResultResponse(BaseModel):
    job_id: UUID
    file_id: UUID
    status: str
    document_type: str
    provider: str
    model_used: str
    items: List[ExtractedActivityItem]
    unresolved_gaps: List[str] = Field(default_factory=list)
    needs_human_review: bool
    execution_latency_ms: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
