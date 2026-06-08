import logging
from typing import Optional

from schemas import AuditResult
from core.report_exports import (
    generate_docx_report as build_docx_report,
    generate_docx_transcription as build_docx_transcription,
    generate_excel_report as build_excel_report,
    generate_pdf_report as build_pdf_report,
    generate_pdf_transcription as build_pdf_transcription,
)
from audio.audio_utils import format_timestamp  # re-exportado para services/testes

logger = logging.getLogger(__name__)

__all__ = [
    "generate_excel_report",
    "generate_docx_report",
    "generate_docx_transcription",
    "generate_pdf_report",
    "generate_pdf_transcription",
    "format_timestamp",
]


def generate_excel_report(result: AuditResult):
    return build_excel_report(result)

def generate_docx_report(result: AuditResult):
    return build_docx_report(result)

def generate_docx_transcription(result: AuditResult):
    return build_docx_transcription(result)

def generate_pdf_report(result: AuditResult):
    return build_pdf_report(result)

def generate_pdf_transcription(result: AuditResult):
    return build_pdf_transcription(result)
