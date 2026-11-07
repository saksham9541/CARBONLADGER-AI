"""
CarbonLedger AI — Nexus Multimodal Extraction Service
=====================================================
Orchestrates AI extraction for evidence files, enforces Pydantic schemas,
populates ActivityRecord rows in the database, and flags anomalies for human review.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import ActivityRecordStatus, EvidenceFileType, ExtractionJobStatus
from app.models.evidence import ActivityRecord, EvidenceFile, ExtractionJob
from app.schemas.extraction import (
    ExtractedActivityItem,
    ExtractionResultResponse,
)
from app.services.extractors import (
    extract_diesel_from_invoice,
    extract_electricity_from_pdf,
    extract_supplier_spreadsheet,
    extract_voice_note_explanation,
)
from app.services.nexus_client import NexusClient, get_nexus_client
from app.services.storage import StorageBackend, get_storage_service

logger = get_logger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_nexus_extraction(
    db: Session,
    evidence_file: EvidenceFile,
    nexus_client: Optional[NexusClient] = None,
    storage: Optional[StorageBackend] = None,
) -> ExtractionResultResponse:
    """
    Executes multimodal structured extraction on an ingested evidence document
    using Nexus AI.
    """
    client = nexus_client or get_nexus_client()
    storage_svc = storage or get_storage_service()

    start_time = time.time()

    # Find the latest intake job to retrieve parsed content
    intake_job = db.execute(
        select(ExtractionJob)
        .where(ExtractionJob.file_id == evidence_file.id)
        .order_by(desc(ExtractionJob.created_at))
    ).scalars().first()

    raw_parsed_data: Dict[str, Any] = {}
    if intake_job and intake_job.extracted_data:
        raw_parsed_data = intake_job.extracted_data.get("data", {})

    # Create new extraction job specifically for Nexus AI execution
    ai_job = ExtractionJob(
        id=uuid.uuid4(),
        org_id=evidence_file.org_id,
        file_id=evidence_file.id,
        status=ExtractionJobStatus.RUNNING.value,
        model_name=f"nexus:{client.extraction_model}",
        model_version="1.0.0",
        started_at=utc_now(),
    )
    db.add(ai_job)
    db.commit()
    db.refresh(ai_job)

    try:
        extracted_items: List[ExtractedActivityItem] = []
        file_type = evidence_file.file_type

        if file_type == EvidenceFileType.PDF.value or file_type == EvidenceFileType.PDF:
            extracted_items = extract_electricity_from_pdf(raw_parsed_data, client)

        elif file_type == EvidenceFileType.IMAGE.value or file_type == EvidenceFileType.IMAGE:
            extracted_items = extract_diesel_from_invoice(raw_parsed_data, client)

        elif file_type in (EvidenceFileType.EXCEL.value, EvidenceFileType.CSV.value, EvidenceFileType.EXCEL, EvidenceFileType.CSV):
            extracted_items = extract_supplier_spreadsheet(raw_parsed_data, client)

        elif file_type == EvidenceFileType.AUDIO.value or file_type == EvidenceFileType.AUDIO:
            extracted_items = extract_voice_note_explanation(raw_parsed_data, client)

        else:
            raise ValueError(f"Unsupported evidence file type for Nexus extraction: {file_type}")

        # Check if any items need human review
        overall_needs_review = any(item.needs_human_review for item in extracted_items)

        # Collect unresolved gaps
        gaps: List[str] = []
        for item in extracted_items:
            if item.needs_human_review:
                gaps.extend(item.review_reasons)

        latency_ms = round((time.time() - start_time) * 1000, 2)

        # Persist structured output in ai_job
        items_dump = [item.model_dump(mode="json") for item in extracted_items]
        ai_job.extracted_data = {
            "file_id": str(evidence_file.id),
            "file_type": str(file_type),
            "provider": "nexus-ai",
            "model_used": client.extraction_model,
            "latency_ms": latency_ms,
            "items": items_dump,
            "unresolved_gaps": gaps,
            "needs_human_review": overall_needs_review,
        }
        ai_job.status = ExtractionJobStatus.COMPLETED.value
        ai_job.completed_at = utc_now()
        ai_job.error_message = None

        # Insert ActivityRecord rows into DB
        for item in extracted_items:
            evidence_ref = (
                item.location.cell_coordinate
                or (f"Page {item.location.page_number}" if item.location.page_number else None)
                or item.location.timestamp_range
                or item.location.raw_text_snippet
                or "Document evidence"
            )

            rec_status = (
                ActivityRecordStatus.REVIEW.value
                if item.needs_human_review
                else ActivityRecordStatus.PENDING.value
            )

            activity_rec = ActivityRecord(
                id=uuid.uuid4(),
                org_id=evidence_file.org_id,
                period_id=evidence_file.period_id or evidence_file.org_id,  # fallback to org if period not assigned yet
                file_id=evidence_file.id,
                facility_id=evidence_file.facility_id,
                job_id=ai_job.id,
                evidence_reference=evidence_ref[:255] if evidence_ref else None,
                evidence_type=item.evidence_type,
                raw_value=item.raw_value,
                raw_unit=item.raw_unit,
                raw_date_start=item.period_start,
                raw_date_end=item.period_end,
                confidence=item.confidence,
                normalised_value=item.normalised_value,
                normalised_unit=item.normalised_unit,
                status=rec_status,
            )
            db.add(activity_rec)

        db.commit()
        db.refresh(ai_job)

        return ExtractionResultResponse(
            job_id=ai_job.id,
            file_id=evidence_file.id,
            status=ai_job.status,
            document_type=str(file_type),
            provider="nexus-ai",
            model_used=client.extraction_model,
            items=extracted_items,
            unresolved_gaps=gaps,
            needs_human_review=overall_needs_review,
            execution_latency_ms=latency_ms,
            created_at=ai_job.created_at,
        )

    except Exception as exc:
        logger.error("Nexus extraction engine failed", file_id=str(evidence_file.id), error=str(exc))
        ai_job.status = ExtractionJobStatus.FAILED.value
        ai_job.completed_at = utc_now()
        ai_job.error_message = str(exc)
        db.commit()
        raise
