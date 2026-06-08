"""
Módulo de exportação PDF no formato dos Gestores.
Gera um relatório visual estilizado com os dados da auditoria.
"""

import io
import json
from datetime import datetime
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)


# ── Paleta NSTECH ──
NSTECH_BLUE = HexColor("#2563EB")
NSTECH_DARK = HexColor("#0F172A")
HEADER_BG = HexColor("#1E293B")
ROW_ALT = HexColor("#F8FAFC")
GREEN = HexColor("#16A34A")
GREEN_BG = HexColor("#DCFCE7")
RED = HexColor("#DC2626")
RED_BG = HexColor("#FEE2E2")
YELLOW = HexColor("#CA8A04")
YELLOW_BG = HexColor("#FEF9C3")
GRAY = HexColor("#64748B")
LIGHT_GRAY = HexColor("#E2E8F0")
WHITE = HexColor("#FFFFFF")
BLACK = HexColor("#1E293B")


def _normalize_binary_detail_status(value: object) -> str:
    status = str(value or "").strip().lower()
    if status in {"pass", "na", "n/a", "pending_manual"}:
        return "pass"
    if status in {"fail", "partial"}:
        return "fail"
    return "fail"


def _build_styles():
    """Estilos personalizados para o PDF."""
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="NSTechTitle",
        fontName="Helvetica-Bold",
        fontSize=18,
        textColor=NSTECH_BLUE,
        spaceAfter=4,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="NSTechSubtitle",
        fontName="Helvetica",
        fontSize=10,
        textColor=GRAY,
        spaceAfter=12,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle",
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=BLACK,
        spaceBefore=16,
        spaceAfter=6,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="BodyText2",
        fontName="Helvetica",
        fontSize=9,
        textColor=BLACK,
        leading=13,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="SmallGray",
        fontName="Helvetica",
        fontSize=8,
        textColor=GRAY,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="CriterionPass",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=GREEN,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="CriterionFail",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=RED,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="TranscriptionSpeaker",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=NSTECH_BLUE,
        leading=12,
        spaceBefore=4,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="TranscriptionText",
        fontName="Helvetica",
        fontSize=8,
        textColor=BLACK,
        leading=11,
        leftIndent=10,
        spaceAfter=2,
        wordWrap="CJK",
    ))
    return styles


def generate_gestores_pdf(audit_data: dict) -> io.BytesIO:
    """
    Gera um PDF estilizado com os dados da auditoria para os gestores.

    audit_data: dict com campos: timestamp, operator_name, operator_id,
                score, max_score, summary, details (JSON string ou list),
                alert_label, sector_id, transcription (list of dicts com start/end/text)
    Retorna BytesIO com o PDF.
    """
    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )
    styles = _build_styles()
    story = []

    # ── Parse dados ──
    details = audit_data.get("details", [])
    if isinstance(details, str):
        try:
            details = json.loads(details)
        except (json.JSONDecodeError, TypeError):
            details = []

    timestamp = audit_data.get("timestamp", "")
    try:
        dt = datetime.fromisoformat(timestamp) if timestamp else datetime.now()
    except (ValueError, TypeError):
        dt = datetime.now()

    operator_name = audit_data.get("operator_name", "") or "Não identificado"
    operator_id = audit_data.get("operator_id", "") or "—"
    score = audit_data.get("score", 0)
    max_score = audit_data.get("max_score", 0)
    summary = audit_data.get("summary", "") or ""
    alert_label = audit_data.get("alert_label", "") or "—"
    sector_id = audit_data.get("sector_id", "") or "—"
    transcription_segments = audit_data.get("transcription", []) or []

    pct = (score / max_score * 100) if max_score > 0 else 0

    # ══════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════
    story.append(Paragraph("NSTECH — Relatório de Auditoria", styles["NSTechTitle"]))
    story.append(Paragraph(
        f"Gerado em {dt.strftime('%d/%m/%Y às %H:%M')} • Formato Gestores",
        styles["NSTechSubtitle"]
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=LIGHT_GRAY, spaceAfter=12))

    # ══════════════════════════════════════════════
    # INFO CARD
    # ══════════════════════════════════════════════
    score_color = GREEN if pct >= 70 else (YELLOW if pct >= 50 else RED)
    info_data = [
        ["Operador", operator_name, "Nota Final", f"{score:.2f} / {max_score:.2f} ({pct:.0f}%)"],
        ["ID Operador", operator_id, "Setor", sector_id.upper()],
        ["Alerta", alert_label, "Data", dt.strftime("%d/%m/%Y %H:%M")],
    ]
    info_table = Table(info_data, colWidths=[3.2 * cm, 5.5 * cm, 3.2 * cm, 5.5 * cm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
        ("TEXTCOLOR", (2, 0), (2, -1), GRAY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (3, 0), (3, 0), score_color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, -1), ROW_ALT),
        ("GRID", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════
    # RESUMO DA IA
    # ══════════════════════════════════════════════
    if summary:
        story.append(Paragraph("Análise da IA", styles["SectionTitle"]))
        story.append(Paragraph(summary, styles["BodyText2"]))
        story.append(Spacer(1, 4))

    # ══════════════════════════════════════════════
    # TABELA DE CRITÉRIOS
    # ══════════════════════════════════════════════
    if details:
        story.append(Paragraph("Critérios de Avaliação", styles["SectionTitle"]))

        header = ["#", "Critério", "Resultado", "Comentário"]
        table_data = [header]

        for i, detail in enumerate(details):
            status = _normalize_binary_detail_status(detail.get("status"))
            label = detail.get("label", f"Critério {i + 1}")
            comment = detail.get("comment", "")

            if status == "pass":
                result_text = "SIM"
            else:
                result_text = "NÃO"

            table_data.append([
                str(i + 1),
                Paragraph(label, styles["BodyText2"]),
                result_text,
                Paragraph(comment, styles["SmallGray"]),
            ])

        col_widths = [1 * cm, 5.5 * cm, 2 * cm, 8.9 * cm]
        criteria_table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Estilos base
        table_style_cmds = [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 0), (2, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ]

        # Cores condicionais por status
        for row_idx, detail in enumerate(details, 1):
            status = _normalize_binary_detail_status(detail.get("status"))
            if status == "pass":
                table_style_cmds.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), GREEN))
                table_style_cmds.append(("BACKGROUND", (2, row_idx), (2, row_idx), GREEN_BG))
            elif status == "fail":
                table_style_cmds.append(("TEXTCOLOR", (2, row_idx), (2, row_idx), RED))
                table_style_cmds.append(("BACKGROUND", (2, row_idx), (2, row_idx), RED_BG))

            # Zebra striping
            if row_idx % 2 == 0:
                table_style_cmds.append(("BACKGROUND", (0, row_idx), (1, row_idx), ROW_ALT))
                table_style_cmds.append(("BACKGROUND", (3, row_idx), (-1, row_idx), ROW_ALT))

        criteria_table.setStyle(TableStyle(table_style_cmds))
        story.append(criteria_table)
        story.append(Spacer(1, 8))

    # ══════════════════════════════════════════════
    # TRANSCRIÇÃO
    # ══════════════════════════════════════════════
    if transcription_segments:
        story.append(Paragraph("Transcrição da Ligação", styles["SectionTitle"]))

        MAX_SEGS = 80
        for seg in transcription_segments[:MAX_SEGS]:
            start = seg.get("start", "") or ""
            end = seg.get("end", "") or ""
            text = seg.get("text", "") or ""

            # Separar "Speaker: fala" do text
            speaker = ""
            speech = text
            if ": " in text:
                parts = text.split(": ", 1)
                speaker = parts[0].strip()
                speech = parts[1].strip()

            def _esc(s):
                return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            # Timestamp em cinza
            ts_label = f"[{_esc(start)}]" if not end or end == start else f"[{_esc(start)} – {_esc(end)}]"

            if speaker:
                header_line = f'<font color="#64748B" size="7">{ts_label}</font>  <b><font color="#2563EB">{_esc(speaker)}</font></b>'
                story.append(Paragraph(header_line, styles["TranscriptionSpeaker"]))
            else:
                story.append(Paragraph(f'<font color="#64748B" size="7">{ts_label}</font>', styles["SmallGray"]))

            if speech:
                story.append(Paragraph(_esc(speech), styles["TranscriptionText"]))

        if len(transcription_segments) > MAX_SEGS:
            story.append(Paragraph(
                f"... (+{len(transcription_segments) - MAX_SEGS} segmentos omitidos)",
                styles["SmallGray"]
            ))

    # ══════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════
    story.append(Spacer(1, 20))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=6))
    story.append(Paragraph(
        f"NSTECH Audit • Documento gerado automaticamente em {datetime.now().strftime('%d/%m/%Y %H:%M')} • Confidencial",
        styles["SmallGray"]
    ))

    doc.build(story)
    output.seek(0)
    return output
