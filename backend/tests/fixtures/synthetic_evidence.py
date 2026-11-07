"""
CarbonLedger AI — Synthetic Evidence Generator
==============================================
Creates synthetically generated multimodal evidence files for testing:
1. Text-based PDF electricity bill (multi-page, selectable text, PyMuPDF)
2. Scanned PDF electricity bill (raster image only, low/zero selectable text)
3. Photographed invoice JPG (Pillow with EXIF orientation metadata)
4. Photographed invoice PNG (Pillow)
5. XLSX supplier declaration (openpyxl with multiple sheets, coordinates, units)
6. CSV supplier declaration (commas, coordinates, units)
7. Audio voice note WAV (Python standard wave module, PCM frames)
8. Audio voice note MP3 (ID3v2 header)
"""

from __future__ import annotations

import csv
import io
import struct
import wave
from typing import Dict

import fitz  # PyMuPDF
import openpyxl
from PIL import Image


def generate_synthetic_text_pdf() -> bytes:
    """Creates a 2-page text-based PDF electricity bill."""
    doc = fitz.open()

    # Page 1
    page1 = doc.new_page(width=595, height=842)  # A4
    page1.insert_text(
        fitz.Point(50, 70),
        "TATA POWER ELECTRICITY DISTRIBUTION LIMITED\nTAX INVOICE / ELECTRICITY BILL\n"
        "Account Number: 9948210042\nBilling Month: January 2026\n"
        "Tariff Category: HT Industrial\nContract Demand: 500 kVA\n\n"
        "METER READING DETAILS:\n"
        "Previous Reading: 120,400 kWh\n"
        "Current Reading: 124,900 kWh\n"
        "Total Energy Consumption: 4,500 kWh\n"
        "Billed Amount: INR 42,750.00\n",
        fontsize=12,
    )

    # Page 2
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text(
        fitz.Point(50, 70),
        "PAYMENT DETAILS AND HISTORICAL CONSUMPTION\n"
        "November 2025: 4,100 kWh\nDecember 2025: 4,350 kWh\nJanuary 2026: 4,500 kWh\n"
        "Power Factor: 0.98\nGrid Baseline Factor Reference: CEA v22.0\n",
        fontsize=11,
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def generate_synthetic_scanned_pdf() -> bytes:
    """
    Creates a 1-page scanned PDF bill.
    Contains an embedded raster image and zero selectable text.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Generate a dummy raster image (e.g. 200x200 pixel grayscale noise/bill)
    img = Image.new("RGB", (300, 400), color=(240, 240, 240))
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format="PNG")
    img_bytes = img_byte_arr.getvalue()

    # Insert image into page covering most of the page
    rect = fitz.Rect(50, 50, 545, 750)
    page.insert_image(rect, stream=img_bytes)

    # Note: NO text is inserted, so selectable text count will be 0!
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def generate_synthetic_invoice_jpg() -> bytes:
    """
    Creates a photographed diesel invoice in JPG format
    with EXIF orientation tag (tag 274 = 6: rotate 90 CW).
    """
    img = Image.new("RGB", (800, 600), color=(255, 255, 255))
    # Add EXIF orientation tag (6 = rotated 90 deg)
    exif = img.getexif()
    exif[274] = 6  # EXIF orientation

    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif, quality=85)
    return buf.getvalue()


def generate_synthetic_invoice_png() -> bytes:
    """Creates a photographed invoice in PNG format."""
    img = Image.new("RGBA", (900, 700), color=(245, 245, 250, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_synthetic_supplier_xlsx() -> bytes:
    """
    Creates an XLSX spreadsheet with 2 sheets, explicit cell coordinates,
    headers, and unit mentions.
    """
    wb = openpyxl.Workbook()

    # Sheet 1: Scope 3 Supplier Declarations
    ws1 = wb.active
    ws1.title = "Supplier Declarations"
    ws1.append(["Invoice No", "Supplier Name", "Delivery Date", "Fuel Quantity", "Unit", "Facility"])
    ws1.append(["INV-2026-001", "Bharat Petroleum", "2026-01-15", 1500, "Litres", "Plant A - Pune"])
    ws1.append(["INV-2026-002", "Indian Oil Corp", "2026-01-28", 2.5, "kL", "Plant B - Mumbai"])
    ws1.append(["INV-2026-003", "Hindustan Petroleum", "2026-02-05", 850, "Litres", "Plant A - Pune"])

    # Sheet 2: Electricity Sub-metering
    ws2 = wb.create_sheet(title="Submeter Readings")
    ws2.append(["Meter ID", "Location", "Consumption", "Unit"])
    ws2.append(["MTR-01", "Boiler House", 12500, "kWh"])
    ws2.append(["MTR-02", "Cooling Tower", 8400, "kWh"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def generate_synthetic_supplier_csv() -> bytes:
    """Creates a tabular CSV declaration with coordinates and units."""
    rows = [
        ["Invoice Number", "Supplier Name", "Activity Type", "Quantity", "Unit", "Date"],
        ["DSL-098", "Shell Energy", "Diesel Generator", "3200", "Litres", "2026-01-20"],
        ["GAS-104", "GAIL India", "Natural Gas", "450", "m3", "2026-01-25"],
        ["ELE-552", "State Grid", "Purchased Electricity", "28000", "kWh", "2026-01-31"],
    ]
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def generate_synthetic_wav_audio() -> bytes:
    """Creates a valid 2-second PCM RIFF WAV audio file."""
    buf = io.BytesIO()
    sample_rate = 16000
    num_channels = 1
    sample_width = 2  # 16-bit
    duration_sec = 2
    num_frames = sample_rate * duration_sec

    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        # 2 seconds of silence/tone
        data = struct.pack(f"<{num_frames}h", *([0] * num_frames))
        wf.writeframes(data)

    return buf.getvalue()


def generate_synthetic_mp3_audio() -> bytes:
    """Creates an MP3 byte stream with valid ID3v2 header and sync frame."""
    id3_header = b"ID3\x03\x00\x00\x00\x00\x00\x00"
    # MPEG-1 Audio Layer III frame sync header (0xFF 0xFB)
    mpeg_frame = b"\xff\xfb\x90\x64" + (b"\x00" * 414)
    return id3_header + (mpeg_frame * 10)
