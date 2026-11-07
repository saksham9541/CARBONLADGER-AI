"""
CarbonLedger AI — Spreadsheet Parser (XLSX & CSV)
=================================================
Parses supplier declarations, fuel receipts, and activity spreadsheets.
Preserves:
- Sheet names.
- Row and column coordinates (1-based row index and cell labels like A1, C14).
- Detected unit mentions in headers or values (kWh, litres, kL, MT, kg, etc.).
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Optional, Set

import openpyxl
from openpyxl.utils import get_column_letter

from app.core.logging import get_logger

logger = get_logger(__name__)

# Controlled unit patterns for carbon & energy activity discovery
KNOWN_UNIT_PATTERNS = [
    r"\b(kwh|mwh|gwh)\b",
    r"\b(l|litre|litres|liter|liters|kl|kilolitre|kilolitres)\b",
    r"\b(kg|kilogram|kilograms|tonne|tonnes|mt|metric\s+tonnes?)\b",
    r"\b(m3|cubic\s+meters?|cubic\s+metres?)\b",
    r"\b(km|kilometres?|kilometers?|miles?)\b",
    r"\b(gj|mj|btu|mmbtu)\b",
    r"\b(kg\s*co2e?|tco2e?|mtco2e?)\b",
]
UNIT_REGEX = re.compile("|".join(KNOWN_UNIT_PATTERNS), re.IGNORECASE)


def extract_potential_units(text: str) -> List[str]:
    """Find recognized unit substrings in text."""
    if not text:
        return []
    matches = UNIT_REGEX.findall(text)
    # findall with capture groups returns tuples of strings
    units: Set[str] = set()
    for m in matches:
        if isinstance(m, tuple):
            for part in m:
                if part:
                    units.add(part.lower().strip())
        elif isinstance(m, str) and m:
            units.add(m.lower().strip())
    return sorted(list(units))


def parse_xlsx_document(file_bytes: bytes, max_rows_per_sheet: int = 500) -> Dict[str, Any]:
    """
    Parses XLSX spreadsheet preserving sheet names, cell coordinates,
    headers, rows, and unit metadata.
    """
    wb = openpyxl.load_workbook(filename=io.BytesIO(file_bytes), data_only=True, read_only=True)
    sheets_data: List[Dict[str, Any]] = []
    all_detected_units: Set[str] = set()

    for sheet_name in wb.sheetnames:
        sheet = wb[sheet_name]
        headers: List[Dict[str, Any]] = []
        rows: List[List[Dict[str, Any]]] = []

        is_header = True
        row_idx = 0

        for raw_row in sheet.iter_rows(values_only=False):
            row_idx += 1
            if row_idx > max_rows_per_sheet:
                break

            # Check if entire row is empty
            row_values = [cell.value for cell in raw_row]
            if not any(v is not None for v in row_values):
                continue

            current_row_cells: List[Dict[str, Any]] = []
            for col_idx, cell in enumerate(raw_row, start=1):
                col_letter = get_column_letter(col_idx)
                coord = f"{col_letter}{row_idx}"
                val = cell.value

                cell_str = str(val) if val is not None else ""
                units = extract_potential_units(cell_str)
                all_detected_units.update(units)

                cell_info = {
                    "coordinate": coord,
                    "row": row_idx,
                    "col": col_idx,
                    "col_letter": col_letter,
                    "value": val,
                    "detected_units": units,
                }
                current_row_cells.append(cell_info)

            if is_header:
                headers = current_row_cells
                is_header = False
            else:
                rows.append(current_row_cells)

        sheets_data.append({
            "sheet_name": sheet_name,
            "total_rows_inspected": row_idx,
            "header_columns": [h["value"] for h in headers if h["value"] is not None],
            "headers": headers,
            "sample_rows": rows[:50],  # Return up to 50 sample rows in JSON payload
            "row_count": len(rows),
        })

    wb.close()

    return {
        "parser": "openpyxl",
        "format": "xlsx",
        "sheet_names": [s["sheet_name"] for s in sheets_data],
        "total_sheets": len(sheets_data),
        "detected_units": sorted(list(all_detected_units)),
        "sheets": sheets_data,
    }


def parse_csv_document(file_bytes: bytes, max_rows: int = 500) -> Dict[str, Any]:
    """
    Parses CSV text preserving row/col coordinates and detected units.
    """
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    # Detect delimiter
    sample = text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delimiter = dialect.delimiter
    except Exception:
        delimiter = ","

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    headers: List[Dict[str, Any]] = []
    rows: List[List[Dict[str, Any]]] = []
    all_detected_units: Set[str] = set()

    row_idx = 0
    for raw_row in reader:
        row_idx += 1
        if row_idx > max_rows:
            break

        if not any(cell.strip() for cell in raw_row):
            continue

        current_row_cells: List[Dict[str, Any]] = []
        for col_idx, val in enumerate(raw_row, start=1):
            col_letter = get_column_letter(col_idx)
            coord = f"{col_letter}{row_idx}"
            clean_val = val.strip()

            units = extract_potential_units(clean_val)
            all_detected_units.update(units)

            cell_info = {
                "coordinate": coord,
                "row": row_idx,
                "col": col_idx,
                "col_letter": col_letter,
                "value": clean_val,
                "detected_units": units,
            }
            current_row_cells.append(cell_info)

        if row_idx == 1:
            headers = current_row_cells
        else:
            rows.append(current_row_cells)

    return {
        "parser": "csv",
        "format": "csv",
        "delimiter": delimiter,
        "total_rows_inspected": row_idx,
        "header_columns": [h["value"] for h in headers],
        "headers": headers,
        "sample_rows": rows[:50],
        "row_count": len(rows),
        "detected_units": sorted(list(all_detected_units)),
    }
