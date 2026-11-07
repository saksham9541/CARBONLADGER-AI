"""
CarbonLedger AI — Image Preprocessing and Metadata Subsystem
============================================================
Inspects photographed invoices (JPG, PNG), corrects EXIF orientation,
computes image dimensions and visual characteristics, and generates
preprocessed preview representations.
"""

from __future__ import annotations

import io
from typing import Any, Dict

from PIL import Image, ImageOps

from app.core.logging import get_logger

logger = get_logger(__name__)


def parse_and_preprocess_image(image_bytes: bytes) -> Dict[str, Any]:
    """
    Validates, corrects EXIF orientation, and analyzes image characteristics.
    """
    # Open image from stream
    img = Image.open(io.BytesIO(image_bytes))

    orig_format = img.format or "UNKNOWN"
    orig_mode = img.mode
    orig_width, orig_height = img.size

    # Check for EXIF orientation tag
    orientation_corrected = False
    try:
        exif = img.getexif()
        # Tag 274 is orientation
        orientation_val = exif.get(274) if exif else None
        if orientation_val and orientation_val > 1:
            img = ImageOps.exif_transpose(img)
            orientation_corrected = True
    except Exception as exc:
        logger.warning("Could not read or apply EXIF orientation", error=str(exc))

    curr_width, curr_height = img.size

    # Image quality / OCR readiness heuristics
    is_low_res = curr_width < 600 or curr_height < 600
    aspect_ratio = round(curr_width / max(curr_height, 1), 3)

    return {
        "parser": "Pillow",
        "format": orig_format,
        "color_mode": orig_mode,
        "original_dimensions": {"width": orig_width, "height": orig_height},
        "normalized_dimensions": {"width": curr_width, "height": curr_height},
        "orientation_corrected": orientation_corrected,
        "aspect_ratio": aspect_ratio,
        "is_low_resolution": is_low_res,
        "ocr_readiness": "low_resolution" if is_low_res else "suitable",
    }
