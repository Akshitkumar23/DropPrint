"""
Office Document to PDF Conversion Service for DropPrint.
Converts Word (.doc, .docx), Excel (.xls, .xlsx), and PowerPoint (.ppt, .pptx)
documents directly to standard PDF format using Windows COM automation (win32com)
with fallback to LibreOffice when available.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OFFICE_WORD_EXTENSIONS = {".doc", ".docx"}
OFFICE_EXCEL_EXTENSIONS = {".xls", ".xlsx"}
OFFICE_PPT_EXTENSIONS = {".ppt", ".pptx"}
OFFICE_EXTENSIONS = OFFICE_WORD_EXTENSIONS | OFFICE_EXCEL_EXTENSIONS | OFFICE_PPT_EXTENSIONS

# MS Office Export Formats
WD_FORMAT_PDF = 17
XL_TYPE_PDF = 0
PP_SAVE_AS_PDF = 32


def _convert_word(input_path: Path, output_pdf_path: Path) -> bool:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = False
        doc = word.Documents.Open(str(input_path.resolve()), ReadOnly=True, Visible=False)
        doc.SaveAs2(str(output_pdf_path.resolve()), FileFormat=WD_FORMAT_PDF)
        return output_pdf_path.exists() and output_pdf_path.stat().st_size > 0
    except Exception as exc:
        logger.warning("Word COM conversion failed for %s: %s", input_path.name, exc)
        return False
    finally:
        try:
            if doc is not None:
                doc.Close(False)
        except Exception:
            pass
        try:
            if word is not None:
                word.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def _convert_excel(input_path: Path, output_pdf_path: Path) -> bool:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    excel = None
    wb = None
    try:
        excel = win32com.client.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        wb = excel.Workbooks.Open(str(input_path.resolve()), ReadOnly=True)
        wb.ExportAsFixedFormat(XL_TYPE_PDF, str(output_pdf_path.resolve()))
        return output_pdf_path.exists() and output_pdf_path.stat().st_size > 0
    except Exception as exc:
        logger.warning("Excel COM conversion failed for %s: %s", input_path.name, exc)
        return False
    finally:
        try:
            if wb is not None:
                wb.Close(False)
        except Exception:
            pass
        try:
            if excel is not None:
                excel.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def _convert_powerpoint(input_path: Path, output_pdf_path: Path) -> bool:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    ppt = None
    pres = None
    try:
        ppt = win32com.client.DispatchEx("PowerPoint.Application")
        pres = ppt.Presentations.Open(str(input_path.resolve()), ReadOnly=True, WithWindow=False)
        pres.SaveAs(str(output_pdf_path.resolve()), PP_SAVE_AS_PDF)
        return output_pdf_path.exists() and output_pdf_path.stat().st_size > 0
    except Exception as exc:
        logger.warning("PowerPoint COM conversion failed for %s: %s", input_path.name, exc)
        return False
    finally:
        try:
            if pres is not None:
                pres.Close()
        except Exception:
            pass
        try:
            if ppt is not None:
                ppt.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def _convert_libreoffice_fallback(input_path: Path, output_pdf_path: Path) -> bool:
    try:
        from app.printing.convert import to_pdf

        pdf_candidate = to_pdf(input_path)
        if pdf_candidate and pdf_candidate.exists() and pdf_candidate.stat().st_size > 0:
            shutil.copy2(pdf_candidate, output_pdf_path)
            return True
    except Exception as exc:
        logger.debug("LibreOffice fallback conversion failed: %s", exc)
    return False


def convert_office_to_pdf(input_path: Path, output_pdf_path: Path) -> bool:
    """Converts a Word, Excel, or PowerPoint document to PDF.

    Tries native Windows COM automation first (Word/Excel/PowerPoint),
    falling back to LibreOffice if available.
    Returns True if conversion succeeded and output_pdf_path exists and is non-empty.
    """
    if not input_path.exists() or input_path.stat().st_size == 0:
        logger.warning("Office converter: input file missing or empty: %s", input_path)
        return False

    suffix = input_path.suffix.lower()
    if suffix not in OFFICE_EXTENSIONS:
        logger.warning("Office converter: unsupported extension %s", suffix)
        return False

    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Try Windows COM automation based on file type
    success = False
    if suffix in OFFICE_WORD_EXTENSIONS:
        success = _convert_word(input_path, output_pdf_path)
    elif suffix in OFFICE_EXCEL_EXTENSIONS:
        success = _convert_excel(input_path, output_pdf_path)
    elif suffix in OFFICE_PPT_EXTENSIONS:
        success = _convert_powerpoint(input_path, output_pdf_path)

    if success and output_pdf_path.exists() and output_pdf_path.stat().st_size > 0:
        return True

    # 2. Try LibreOffice fallback
    if _convert_libreoffice_fallback(input_path, output_pdf_path):
        return True

    return False
