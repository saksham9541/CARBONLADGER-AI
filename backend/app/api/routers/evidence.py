"""
CarbonLedger AI — Multimodal Evidence Intake Router
===================================================
Endpoints for uploading, listing, retrieving, previewing, downloading,
and reprocessing evidence files with strict organization isolation.
"""

from __future__ import annotations

import uuid
from typing import List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.auth import require_analyst_or_admin, require_any_member
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.enums import UserRole
from app.models.evidence import EvidenceFile, ExtractionJob
from app.models.organization import Facility, OrganizationMembership
from app.models.reporting_period import ReportingPeriod
from app.schemas.evidence import (
    EvidenceDetailResponse,
    EvidenceFileListResponse,
    EvidenceFileResponse,
    ExtractionJobResponse,
)
from app.services.file_validator import (
    FileValidationError,
    UnsupportedMediaTypeError,
    validate_file_upload,
)
from app.services.intake_service import run_intake_processing
from app.services.storage import StorageBackend, get_storage_service

router = APIRouter(prefix="/organizations/{org_id}/evidence", tags=["Evidence Intake"])
logger = get_logger(__name__)


def _get_evidence_or_404(
    db: Session,
    org_id: UUID,
    file_id: UUID,
    allow_deleted: bool = False,
) -> EvidenceFile:
    query = select(EvidenceFile).where(
        EvidenceFile.id == file_id,
        EvidenceFile.org_id == org_id,
    )
    if not allow_deleted:
        query = query.where(EvidenceFile.is_deleted == False)

    file_rec = db.execute(query).scalar_one_or_none()
    if not file_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evidence file '{file_id}' not found in this organization",
        )
    return file_rec


def _get_latest_job(db: Session, file_id: UUID) -> Optional[ExtractionJob]:
    return db.execute(
        select(ExtractionJob)
        .where(ExtractionJob.file_id == file_id)
        .order_by(desc(ExtractionJob.created_at))
    ).scalars().first()


@router.post(
    "/upload",
    response_model=EvidenceDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest evidence document",
    description="Accepts PDF, JPG/PNG, XLSX/CSV, and WAV/MP3/M4A. Requires Analyst or Admin role.",
)
async def upload_evidence_file(
    org_id: UUID,
    file: UploadFile = File(..., description="Binary evidence document"),
    period_id: Optional[UUID] = Form(None, description="Optional reporting period UUID"),
    facility_id: Optional[UUID] = Form(None, description="Optional facility UUID"),
    membership: OrganizationMembership = Depends(require_analyst_or_admin),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_service),
) -> EvidenceDetailResponse:
    # 1. Validate reporting period belongs to this org if specified
    if period_id:
        period = db.execute(
            select(ReportingPeriod).where(
                ReportingPeriod.id == period_id,
                ReportingPeriod.org_id == org_id,
            )
        ).scalar_one_or_none()
        if not period:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reporting period '{period_id}' does not exist in this organization",
            )

    # 2. Validate facility belongs to this org if specified
    if facility_id:
        facility = db.execute(
            select(Facility).where(
                Facility.id == facility_id,
                Facility.org_id == org_id,
            )
        ).scalar_one_or_none()
        if not facility:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Facility '{facility_id}' does not exist in this organization",
            )

    # 3. Read uploaded binary contents
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    # 4. Content signature and MIME validation
    try:
        validated_meta = validate_file_upload(
            content=content,
            original_filename=file.filename or "uploaded_file",
        )
    except UnsupportedMediaTypeError as err:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=err.message,
        )
    except FileValidationError as err:
        raise HTTPException(
            status_code=err.status_code,
            detail=err.message,
        )

    # 5. Save to private storage
    file_id = uuid.uuid4()
    storage_path = storage.save(
        org_id=org_id,
        file_id=file_id,
        filename=validated_meta.sanitized_filename,
        content=content,
    )

    # 6. Insert EvidenceFile row
    evidence_file = EvidenceFile(
        id=file_id,
        org_id=org_id,
        period_id=period_id,
        facility_id=facility_id,
        original_name=file.filename or validated_meta.sanitized_filename,
        storage_path=storage_path,
        file_hash=validated_meta.file_hash,
        file_type=validated_meta.file_type.value,
        mime_type=validated_meta.mime_type,
        size_bytes=validated_meta.size_bytes,
        uploaded_by=membership.user_id,
    )
    db.add(evidence_file)
    db.commit()
    db.refresh(evidence_file)

    # 7. Execute intake processing (modality parsing & scanned page detection)
    job = run_intake_processing(db=db, evidence_file=evidence_file, file_bytes=content)

    file_resp = EvidenceFileResponse.model_validate(evidence_file)
    file_resp.latest_job_status = job.status
    job_resp = ExtractionJobResponse.model_validate(job)

    return EvidenceDetailResponse(file=file_resp, latest_job=job_resp)


@router.get(
    "",
    response_model=EvidenceFileListResponse,
    summary="List evidence files for organization",
    description="Accessible by all active organization members (Admin, Analyst, Auditor).",
)
def list_evidence_files(
    org_id: UUID,
    period_id: Optional[UUID] = None,
    file_type: Optional[str] = None,
    include_deleted: bool = False,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
) -> EvidenceFileListResponse:
    query = select(EvidenceFile).where(EvidenceFile.org_id == org_id)

    if not include_deleted:
        query = query.where(EvidenceFile.is_deleted == False)
    if period_id:
        query = query.where(EvidenceFile.period_id == period_id)
    if file_type:
        query = query.where(EvidenceFile.file_type == file_type)

    query = query.order_by(desc(EvidenceFile.uploaded_at))
    files = db.execute(query).scalars().all()

    items: List[EvidenceFileResponse] = []
    for f in files:
        f_resp = EvidenceFileResponse.model_validate(f)
        latest_job = _get_latest_job(db, f.id)
        f_resp.latest_job_status = latest_job.status if latest_job else None
        items.append(f_resp)

    return EvidenceFileListResponse(items=items, total=len(items))


@router.get(
    "/{file_id}",
    response_model=EvidenceDetailResponse,
    summary="Get evidence file details and extraction status",
)
def get_evidence_file(
    org_id: UUID,
    file_id: UUID,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
) -> EvidenceDetailResponse:
    file_rec = _get_evidence_or_404(db, org_id, file_id)
    latest_job = _get_latest_job(db, file_id)

    file_resp = EvidenceFileResponse.model_validate(file_rec)
    file_resp.latest_job_status = latest_job.status if latest_job else None
    job_resp = ExtractionJobResponse.model_validate(latest_job) if latest_job else None

    return EvidenceDetailResponse(file=file_resp, latest_job=job_resp)


@router.get(
    "/{file_id}/download",
    summary="Download original evidence file",
    description="Streams binary file with attachment disposition.",
)
def download_evidence_file(
    org_id: UUID,
    file_id: UUID,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_service),
) -> Response:
    file_rec = _get_evidence_or_404(db, org_id, file_id)
    try:
        content = storage.get(file_rec.storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File content not found in storage.",
        )

    headers = {
        "Content-Disposition": f'attachment; filename="{file_rec.original_name}"',
        "Content-Length": str(len(content)),
    }
    return Response(content=content, media_type=file_rec.mime_type, headers=headers)


@router.get(
    "/{file_id}/preview",
    summary="Preview evidence file",
    description="Streams binary file with inline disposition.",
)
def preview_evidence_file(
    org_id: UUID,
    file_id: UUID,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_service),
) -> Response:
    file_rec = _get_evidence_or_404(db, org_id, file_id)
    try:
        content = storage.get(file_rec.storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File content not found in storage.",
        )

    headers = {
        "Content-Disposition": f'inline; filename="{file_rec.original_name}"',
        "Content-Length": str(len(content)),
    }
    return Response(content=content, media_type=file_rec.mime_type, headers=headers)


@router.get(
    "/{file_id}/jobs",
    response_model=List[ExtractionJobResponse],
    summary="Get all extraction and processing jobs for evidence file",
)
def get_evidence_jobs(
    org_id: UUID,
    file_id: UUID,
    _membership: OrganizationMembership = Depends(require_any_member),
    db: Session = Depends(get_db),
) -> List[ExtractionJobResponse]:
    _get_evidence_or_404(db, org_id, file_id)
    jobs = db.execute(
        select(ExtractionJob)
        .where(ExtractionJob.file_id == file_id, ExtractionJob.org_id == org_id)
        .order_by(desc(ExtractionJob.created_at))
    ).scalars().all()
    return [ExtractionJobResponse.model_validate(j) for j in jobs]


@router.post(
    "/{file_id}/reprocess",
    response_model=EvidenceDetailResponse,
    summary="Reprocess evidence file",
    description="Re-triggers extraction and intake parsing. Requires Analyst or Admin role.",
)
def reprocess_evidence_file(
    org_id: UUID,
    file_id: UUID,
    _membership: OrganizationMembership = Depends(require_analyst_or_admin),
    db: Session = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_service),
) -> EvidenceDetailResponse:
    file_rec = _get_evidence_or_404(db, org_id, file_id)
    try:
        content = storage.get(file_rec.storage_path)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File content not found in storage.",
        )

    job = run_intake_processing(db=db, evidence_file=file_rec, file_bytes=content)

    file_resp = EvidenceFileResponse.model_validate(file_rec)
    file_resp.latest_job_status = job.status
    job_resp = ExtractionJobResponse.model_validate(job)

    return EvidenceDetailResponse(file=file_resp, latest_job=job_resp)


@router.delete(
    "/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft delete evidence file",
    description="Marks file as deleted to preserve audit ledger history. Requires Analyst or Admin role.",
)
def delete_evidence_file(
    org_id: UUID,
    file_id: UUID,
    _membership: OrganizationMembership = Depends(require_analyst_or_admin),
    db: Session = Depends(get_db),
) -> Response:
    file_rec = _get_evidence_or_404(db, org_id, file_id)
    file_rec.is_deleted = True
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
