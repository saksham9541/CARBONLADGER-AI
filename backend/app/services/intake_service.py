"""
CarbonLedger AI — Multimodal Evidence Intake Pipeline Orchestrator
==================================================================
Processes uploaded evidence documents:
- Dispatches to modality-specific parsers.
- Manages ExtractionJob lifecycle (PENDING -> RUNNING -> COMPLETED / FAILED).
- Saves parsed structured data without performing carbon arithmetic (reserved for Phase 4/5).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.enums import EvidenceFileType, ExtractionJobStatus
from app.models.evidence import EvidenceFile, ExtractionJob
from app.services.parsers import (
    parse_audio_document,
    parse_and_preprocess_image,
    parse_csv_document,
    parse_pdf_document,
    parse_xlsx_document,
)

logger = get_logger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_intake_processing(
    db: Session,
    evidence_file: EvidenceFile,
    file_bytes: bytes,
    job: Optional[ExtractionJob] = None,
) -> ExtractionJob:
    """
    Executes intake parsing pipeline for the given evidence file.
    Updates or creates an ExtractionJob and persists extraction results.
    """
    if job is None:
        job = ExtractionJob(
            org_id=evidence_file.org_id,
            file_id=evidence_file.id,
            status=ExtractionJobStatus.PENDING.value,
            model_name="deterministic-intake-parser",
            model_version="1.0.0",
        )
        db.add(job)
        db.flush()

    job.status = ExtractionJobStatus.RUNNING.value
    job.started_at = utc_now()
    db.commit()

    try:
        parsed_result: Dict[str, Any] = {}
        file_type = evidence_file.file_type

        if file_type == EvidenceFileType.PDF.value or file_type == EvidenceFileType.PDF:
            parsed_result = parse_pdf_document(file_bytes)
            job.model_name = f"PyMuPDF-{parsed_result.get('parser', 'fitz')}"

        elif file_type == EvidenceFileType.EXCEL.value or file_type == EvidenceFileType.EXCEL:
            parsed_result = parse_xlsx_document(file_bytes)
            job.model_name = "openpyxl-parser"

        elif file_type == EvidenceFileType.CSV.value or file_type == EvidenceFileType.CSV:
            parsed_result = parse_csv_document(file_bytes)
            job.model_name = "csv-parser"

        elif file_type == EvidenceFileType.IMAGE.value or file_type == EvidenceFileType.IMAGE:
            parsed_result = parse_and_preprocess_image(file_bytes)
            job.model_name = "pillow-image-preprocessor"

        elif file_type == EvidenceFileType.AUDIO.value or file_type == EvidenceFileType.AUDIO:
            parsed_result = parse_audio_document(
                file_bytes,
                evidence_file.original_name,
                evidence_file.mime_type,
            )
            job.model_name = parsed_result.get("parser", "audio-adapter")

        else:
            raise ValueError(f"Unrecognized evidence file type for intake: {file_type}")

        # Store extraction results
        job.extracted_data = {
            "file_id": str(evidence_file.id),
            "original_name": evidence_file.original_name,
            "file_type": str(file_type),
            "file_hash": evidence_file.file_hash,
            "size_bytes": evidence_file.size_bytes,
            "processed_at": utc_now().isoformat(),
            "data": parsed_result,
        }
        job.status = ExtractionJobStatus.COMPLETED.value
        job.completed_at = utc_now()
        job.error_message = None

        logger.info(
            "Intake processing completed successfully",
            file_id=str(evidence_file.id),
            file_type=str(file_type),
            job_id=str(job.id),
        )

    except Exception as exc:
        logger.error(
            "Intake processing failed",
            file_id=str(evidence_file.id),
            error=str(exc),
        )
        job.status = ExtractionJobStatus.FAILED.value
        job.completed_at = utc_now()
        job.error_message = str(exc)

    db.commit()
    db.refresh(job)
    return job
