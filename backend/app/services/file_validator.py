"""
CarbonLedger AI — File Validation and Classification Subsystem
=============================================================
Enforces:
- Content-based magic byte inspection (preventing extension spoofing).
- Size limit verification.
- Filename sanitization and path traversal prevention.
- Content SHA-256 hash calculation.
- EvidenceFileType classification.
- Never silently discard unsupported files.
"""

from __future__ import annotations

import hashlib
import re
import zipfile
import io
from dataclasses import dataclass
from typing import Optional, Tuple

from app.core.config import get_settings
from app.core.exceptions import CarbonLedgerError
from app.models.enums import EvidenceFileType


class FileValidationError(CarbonLedgerError):
    """Raised when file validation fails (size, corrupt, spoofed)."""
    def __init__(self, message: str, status_code: int = 400, code: str = "FILE_VALIDATION_ERROR"):
        super().__init__(message=message, code=code, status_code=status_code)


class UnsupportedMediaTypeError(FileValidationError):
    """Raised when media format is unsupported."""
    def __init__(self, message: str):
        super().__init__(message=message, status_code=415, code="UNSUPPORTED_MEDIA_TYPE")


@dataclass
class ValidatedFileMetadata:
    sanitized_filename: str
    file_hash: str  # SHA-256
    file_type: EvidenceFileType
    mime_type: str
    size_bytes: int


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename against path traversal, control characters, and excess length.
    """
    if not filename or not filename.strip():
        return "unnamed_document"

    # Strip directory components (Windows and Unix)
    cleaned = filename.replace("\\", "/").split("/")[-1].strip()

    # Remove null bytes and control chars
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)

    # Replace spaces and tricky characters with underscore or dash
    cleaned = re.sub(r"[^\w\.\-\_]", "_", cleaned)

    # Collapse repeated dots or underscores
    cleaned = re.sub(r"\.{2,}", ".", cleaned)
    cleaned = re.sub(r"_{2,}", "_", cleaned)

    if not cleaned or cleaned.startswith("."):
        cleaned = f"file{cleaned}"

    # Truncate to maximum 200 characters while preserving extension
    if len(cleaned) > 200:
        parts = cleaned.rsplit(".", 1)
        if len(parts) == 2:
            stem, ext = parts
            cleaned = f"{stem[:190]}.{ext[:9]}"
        else:
            cleaned = cleaned[:200]

    return cleaned


def detect_file_type_and_mime(content: bytes, filename: str) -> Tuple[EvidenceFileType, str]:
    """
    Inspect magic bytes and filename extension to determine type and MIME.
    Throws UnsupportedMediaTypeError or FileValidationError on mismatch/unsupported.
    """
    if not content:
        raise FileValidationError("File is empty (0 bytes).")

    ext = filename.lower().split(".")[-1] if "." in filename else ""

    # 1. PDF: %PDF-
    if content.startswith(b"%PDF-"):
        return EvidenceFileType.PDF, "application/pdf"

    # 2. PNG: \x89PNG\r\n\x1a\n
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return EvidenceFileType.IMAGE, "image/png"

    # 3. JPEG: \xff\xd8\xff
    if content.startswith(b"\xff\xd8\xff"):
        return EvidenceFileType.IMAGE, "image/jpeg"

    # 4. XLSX / Office Open XML: PK\x03\x04 (ZIP)
    if content.startswith(b"PK\x03\x04"):
        # Check if it's an Excel spreadsheet
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()
                if any("xl/" in n or "workbook.xml" in n for n in names):
                    return EvidenceFileType.EXCEL, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except zipfile.BadZipFile:
            raise FileValidationError("Corrupted or invalid Excel file archive.")

    # 5. Audio WAV: RIFF....WAVE
    if len(content) > 12 and content[:4] == b"RIFF" and content[8:12] == b"WAVE":
        return EvidenceFileType.AUDIO, "audio/wav"

    # 6. Audio MP3: ID3 or frame sync 0xFF 0xFB/F3/F2
    if content.startswith(b"ID3") or (
        len(content) > 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0
    ):
        return EvidenceFileType.AUDIO, "audio/mpeg"

    # 7. Audio M4A: ISO BMFF with ftyp box
    if len(content) > 12 and content[4:8] == b"ftyp":
        major_brand = content[8:12]
        if major_brand in (b"M4A ", b"isom", b"mp42", b"mp41"):
            return EvidenceFileType.AUDIO, "audio/mp4"

    # 8. CSV / Tabular Text
    if ext == "csv" or ext == "txt":
        # Verify it can be decoded as text and has line/column format
        try:
            text_sample = content[:4096].decode("utf-8")
        except UnicodeDecodeError:
            try:
                text_sample = content[:4096].decode("latin-1")
            except Exception:
                raise UnsupportedMediaTypeError("Unable to decode text file as UTF-8 or Latin-1.")

        # Check for tabular structure
        lines = [line.strip() for line in text_sample.splitlines() if line.strip()]
        if len(lines) >= 1:
            return EvidenceFileType.CSV, "text/csv"

    # If extension claims to be a supported format but magic bytes do not match:
    if ext in ("pdf", "png", "jpg", "jpeg", "xlsx", "wav", "mp3", "m4a", "csv"):
        raise FileValidationError(
            f"File extension '.{ext}' does not match actual binary file content header."
        )

    # Unsupported file type
    raise UnsupportedMediaTypeError(
        f"Unsupported file format '{ext or 'unknown'}'. "
        "CarbonLedger accepts PDF bills, JPG/PNG invoices, XLSX/CSV declarations, and WAV/MP3/M4A voice notes."
    )


def validate_file_upload(
    content: bytes,
    original_filename: str,
    max_size_mb: Optional[int] = None,
) -> ValidatedFileMetadata:
    """
    Comprehensive upload validation:
    - Enforces size limit.
    - Computes content SHA-256 hash.
    - Sanitizes filename.
    - Validates magic bytes and classifies evidence type.
    """
    settings = get_settings()
    max_mb = max_size_mb or settings.max_file_size_mb
    max_bytes = max_mb * 1024 * 1024

    size_bytes = len(content)
    if size_bytes > max_bytes:
        raise FileValidationError(
            f"File size ({size_bytes / (1024 * 1024):.2f} MB) exceeds maximum limit of {max_mb} MB.",
            status_code=413,
        )

    sanitized = sanitize_filename(original_filename)
    file_type, mime_type = detect_file_type_and_mime(content, sanitized)
    file_hash = hashlib.sha256(content).hexdigest()

    return ValidatedFileMetadata(
        sanitized_filename=sanitized,
        file_hash=file_hash,
        file_type=file_type,
        mime_type=mime_type,
        size_bytes=size_bytes,
    )
