"""Fachada de exportação de relatórios de auditoria (DOCX/PDF/Excel).

Camada fina e estável de compatibilidade: a implementação real foi extraída para
``core.report_exports`` e este módulo apenas reexporta/encaminha as funções públicas
(``generate_*``) e o utilitário ``format_timestamp`` (vindo de ``audio.audio_utils``),
para que imports antigos como ``from core.export import generate_docx_report`` sigam
funcionando.

Cada função recebe um ``AuditResult`` e devolve os bytes/stream do arquivo gerado.
Sem custo de API (geração local de documento — só CPU/memória).
"""
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
    """Gera o relatório de auditoria em Excel (.xlsx) a partir do ``AuditResult``.

    Encaminha para ``core.report_exports``. Sem custo de API.
    """
    return build_excel_report(result)

def generate_docx_report(result: AuditResult):
    """Gera o relatório de auditoria em Word (.docx) a partir do ``AuditResult``.

    Encaminha para ``core.report_exports``. Sem custo de API.
    """
    return build_docx_report(result)

def generate_docx_transcription(result: AuditResult):
    """Gera um documento Word (.docx) só com a transcrição do ``AuditResult``.

    Encaminha para ``core.report_exports``. Sem custo de API.
    """
    return build_docx_transcription(result)

def generate_pdf_report(result: AuditResult):
    """Gera o relatório de auditoria em PDF a partir do ``AuditResult``.

    Encaminha para ``core.report_exports``. Sem custo de API.
    """
    return build_pdf_report(result)

def generate_pdf_transcription(result: AuditResult):
    """Gera um PDF só com a transcrição do ``AuditResult``.

    Encaminha para ``core.report_exports``. Sem custo de API.
    """
    return build_pdf_transcription(result)
