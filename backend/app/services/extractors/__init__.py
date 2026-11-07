"""
CarbonLedger AI — Modality Extractors Registry
"""

from app.services.extractors.diesel_extractor import extract_diesel_from_invoice
from app.services.extractors.electricity_extractor import extract_electricity_from_pdf
from app.services.extractors.spreadsheet_extractor import extract_supplier_spreadsheet
from app.services.extractors.voice_note_extractor import extract_voice_note_explanation

__all__ = [
    "extract_electricity_from_pdf",
    "extract_diesel_from_invoice",
    "extract_supplier_spreadsheet",
    "extract_voice_note_explanation",
]
