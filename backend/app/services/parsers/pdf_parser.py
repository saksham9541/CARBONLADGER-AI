"""
CarbonLedger AI — PDF Text Extraction & Scanned Page Detection
==============================================================
Uses PyMuPDF (fitz) to extract document structure, per-page text,
block bounding boxes, and detects whether pages are scanned images
versus selectable text.
"""

from __future__ import annotations

import io
from typing import Any, Dict, List

import fitz  # PyMuPDF

from app.core.logging import get_logger

logger = get_logger(__name__)

# A page with fewer than 50 extracted characters and at least 1 raster image
# is classified as scanned.
SCANNED_PAGE_CHAR_THRESHOLD = 50


def parse_pdf_document(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Parses PDF bytes, extracts per-page text and bounding boxes,
    and identifies scanned pages.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    pages_data: List[Dict[str, Any]] = []
    scanned_pages_count = 0
    full_text_parts: List[str] = []

    for page_idx in range(total_pages):
        page = doc.load_page(page_idx)
        page_num = page_idx + 1

        # Extract text and blocks
        text = page.get_text("text").strip()
        char_count = len(text)
        images = page.get_images()
        image_count = len(images)

        # Scanned page detection heuristic
        # If very low selectable characters and has raster images, it's a scanned/photographed bill
        is_scanned = (char_count < SCANNED_PAGE_CHAR_THRESHOLD and image_count > 0) or (char_count == 0)

        if is_scanned:
            scanned_pages_count += 1

        rect = page.rect
        # Extract structured text blocks with coordinates for auditability
        blocks = page.get_text("blocks")
        text_blocks = []
        for b in blocks:
            # b: (x0, y0, x1, y1, text, block_no, block_type)
            if len(b) >= 5 and b[4].strip():
                text_blocks.append({
                    "bbox": [round(b[0], 2), round(b[1], 2), round(b[2], 2), round(b[3], 2)],
                    "text": b[4].strip(),
                })

        pages_data.append({
            "page_number": page_num,
            "width": round(rect.width, 2),
            "height": round(rect.height, 2),
            "character_count": char_count,
            "image_count": image_count,
            "is_scanned": is_scanned,
            "text": text,
            "blocks": text_blocks[:50],  # Cap to prevent unbounded JSON payloads
        })

        if text:
            full_text_parts.append(f"--- Page {page_num} ---\n{text}")

    doc.close()

    return {
        "parser": "PyMuPDF",
        "total_pages": total_pages,
        "scanned_pages_count": scanned_pages_count,
        "has_scanned_pages": scanned_pages_count > 0,
        "is_entirely_scanned": (scanned_pages_count == total_pages and total_pages > 0),
        "pages": pages_data,
        "full_text": "\n\n".join(full_text_parts),
    }
