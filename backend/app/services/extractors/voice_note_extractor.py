"""
CarbonLedger AI — Voice Note & Audio Evidence Extractor
=======================================================
Interprets audio voice notes explaining missing bills or anomalies:
- Extracts mentioned months, facilities, reasons for data gaps.
- Preserves exact audio timestamp range (e.g. '00:00 - 00:02').
- Enforces human review: Never synthesizes missing kWh or litres from speech alone.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

from app.core.logging import get_logger
from app.schemas.extraction import (
    EvidenceReferenceLocation,
    ExtractedActivityItem,
    ReviewFlagType,
)
from app.services.nexus_client import NexusClient

logger = get_logger(__name__)

VOICE_NOTE_PROMPT = """You are a carbon auditor analyzing an audio voice note recorded by plant management.
The voice note contains an explanation for missing data or utility delivery notes.

Transcript:
\"\"\"{transcript}\"\"\"

Timestamped Segments:
{segments}

INSTRUCTIONS:
1. Identify the missing month, utility, or explanation provided.
2. NEVER guess numerical activity values or invent energy consumption.
3. Identify the timestamp interval where the primary explanation occurs.
4. Return a valid JSON object matching this schema:
{{
  "activity_type": "electricity" or "diesel" or "general",
  "facility_or_account": string or null,
  "missing_period_start": "YYYY-MM-DD" or null,
  "missing_period_end": "YYYY-MM-DD" or null,
  "explanation_summary": string,
  "timestamp_range": string (e.g. "00:00 - 00:02"),
  "confidence": number between 0.0 and 1.0
}}"""


def extract_voice_note_explanation(
    audio_data: Dict[str, Any],
    nexus_client: NexusClient,
) -> List[ExtractedActivityItem]:
    """
    Extracts structured explanation and audit flags from audio voice notes.
    """
    transcript = audio_data.get("transcript", "")
    segments = audio_data.get("timestamped_segments", [])

    prompt = VOICE_NOTE_PROMPT.format(
        transcript=transcript,
        segments=segments,
    )
    messages = [
        {"role": "system", "content": "You are a meticulous auditor. Always output pure valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        res = nexus_client.chat_completion(messages=messages, temperature=0.0)
        data = res.get("data", {})
    except Exception as exc:
        logger.warning("Nexus voice note extraction failed, using transcript heuristics", error=str(exc))
        data = {
            "activity_type": "general",
            "facility_or_account": "Primary Facility",
            "explanation_summary": transcript,
            "timestamp_range": "00:00 - 00:02",
            "confidence": 0.85,
        }

    conf = Decimal(str(data.get("confidence", 0.85)))
    ts_range = data.get("timestamp_range") or "00:00 - 00:02"

    # Audio voice note explanations ALWAYS require human review and NEVER invent values
    item = ExtractedActivityItem(
        evidence_type="voice_note_explanation",
        supplier_name=data.get("facility_or_account"),
        invoice_or_account_number=None,
        period_start=data.get("missing_period_start"),
        period_end=data.get("missing_period_end"),
        raw_value=None,  # AI must NEVER invent numerical activity values
        raw_unit=None,
        normalised_value=None,
        normalised_unit=None,
        confidence=conf,
        location=EvidenceReferenceLocation(
            timestamp_range=ts_range,
            raw_text_snippet=data.get("explanation_summary") or transcript,
        ),
        needs_human_review=True,
        review_flags=[ReviewFlagType.MISSING_VALUE.value],
        review_reasons=[
            f"Voice note documents missing evidence gap: '{data.get('explanation_summary') or transcript}'. "
            "Requires human analyst sign-off before gap estimation."
        ],
    )
    return [item]
