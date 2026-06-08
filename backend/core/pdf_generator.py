from __future__ import annotations
"""Gera PDF corporativo a partir do transcript JSON de chat (WhatsApp).

Substitui o processo manual de "salvar HTML e imprimir como PDF" que a equipe
de auditoria faz hoje. A saida e binario PDF pronto para `process_pdf_audit`.
"""


import io
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def gerar_pdf_chat(
    mensagens: Iterable[Dict[str, Any]],
    operador: str,
    metadados: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Monta um PDF com as mensagens de um chat multimidia.

    Args:
        mensagens: iteravel de dicts com chaves `sender` (OPERATOR|CLIENT),
            `text`, `timestamp` (ISO ou epoch ms).
        operador: nome do operador auditado (cabecalho).
        metadados: opcional. Chaves suportadas: `setor`, `protocolo`,
            `data_inicio`, `data_fim`.
    Returns:
        Bytes do PDF gerado.
    """
    meta = metadados or {}
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"Auditoria - {operador}",
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#555555"),
        spaceAfter=12,
    )
    operator_style = ParagraphStyle(
        "OperatorMsg",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#0b3d91"),
    )
    client_style = ParagraphStyle(
        "ClientMsg",
        parent=styles["Normal"],
        fontSize=10,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#222222"),
    )

    story: List[Any] = []
    story.append(Paragraph("Transcricao de Atendimento Multimidia", title_style))
    subtitle_parts = [f"<b>Operador:</b> {operador}"]
    if meta.get("setor"):
        subtitle_parts.append(f"<b>Setor:</b> {meta['setor']}")
    if meta.get("protocolo"):
        subtitle_parts.append(f"<b>Protocolo:</b> {meta['protocolo']}")
    if meta.get("data_inicio"):
        subtitle_parts.append(f"<b>Inicio:</b> {meta['data_inicio']}")
    if meta.get("data_fim"):
        subtitle_parts.append(f"<b>Fim:</b> {meta['data_fim']}")
    subtitle_parts.append(
        f"<b>Gerado em:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    )
    story.append(Paragraph(" &nbsp;|&nbsp; ".join(subtitle_parts), subtitle_style))
    story.append(Spacer(1, 0.3 * cm))

    rows: List[List[Any]] = []
    for msg in mensagens:
        sender = str(msg.get("sender") or msg.get("from") or "").upper()
        text = str(msg.get("text") or msg.get("content") or "").strip()
        if not text:
            continue
        ts = _format_timestamp(msg.get("timestamp") or msg.get("time"))
        if sender in ("OPERATOR", "AGENT", "OPERADOR"):
            paragraph = Paragraph(
                f"<b>{ts} - Operador</b><br/>{_escape_html(text)}",
                operator_style,
            )
            rows.append(["", paragraph])
        else:
            paragraph = Paragraph(
                f"<b>{ts} - Cliente</b><br/>{_escape_html(text)}",
                client_style,
            )
            rows.append([paragraph, ""])

    if not rows:
        story.append(Paragraph("(Conversa sem mensagens)", styles["Italic"]))
    else:
        table = Table(rows, colWidths=[8 * cm, 8 * cm])
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(table)

    doc.build(story)
    return buffer.getvalue()


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("\n", "<br/>")
    )


def _format_timestamp(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)):
        # epoch ms ou s
        seconds = value / 1000 if value > 1e12 else value
        try:
            return datetime.fromtimestamp(seconds).strftime("%d/%m %H:%M")
        except (ValueError, OSError):
            return str(value)
    text = str(value)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(text[: len(fmt.replace("%Y", "2000"))], fmt).strftime("%d/%m %H:%M")
        except ValueError:
            continue
    return text
