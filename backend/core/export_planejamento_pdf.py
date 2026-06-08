"""Export consolidado mensal em PDF para o setor de Planejamento.

Gera um relatório visual estilizado com dados consolidados por operador,
no mesmo formato de dados do export_planejamento.py (Excel), porém em PDF.
"""

import io
from datetime import datetime
from typing import Optional

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak,
)

from db.domain_constants import AUDIT_STATUS_APPROVED

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
GRAY = HexColor("#64748B")
LIGHT_GRAY = HexColor("#E2E8F0")
WHITE = HexColor("#FFFFFF")
BLACK = HexColor("#1E293B")

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _build_styles():
    """Estilos personalizados para o PDF consolidado."""
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
        name="TableCell",
        fontName="Helvetica",
        fontSize=8,
        textColor=BLACK,
        leading=10,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="TableCellBold",
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=BLACK,
        leading=10,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="SmallGray",
        fontName="Helvetica",
        fontSize=7,
        textColor=GRAY,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="KPIValue",
        fontName="Helvetica-Bold",
        fontSize=20,
        textColor=BLACK,
        alignment=TA_CENTER,
        wordWrap="CJK",
    ))
    styles.add(ParagraphStyle(
        name="KPILabel",
        fontName="Helvetica",
        fontSize=8,
        textColor=GRAY,
        alignment=TA_CENTER,
        wordWrap="CJK",
    ))
    return styles


def _fetch_operator_data(get_connection, month: int, year: int) -> dict[str, dict]:
    """Busca nota média por operador + dados do colaboradores."""
    date_start = f"{year:04d}-{month:02d}-01"
    date_end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"
    conn = get_connection()
    try:
        c = conn.cursor()

        sql = """
            WITH audit_stats AS (
                SELECT
                    operator_name,
                    AVG(score) AS media_nota,
                    MAX(max_score) AS max_score,
                    COUNT(*) AS total_ligacoes,
                    ROUND(AVG(CASE WHEN max_score > 0 THEN (score * 1.0 / max_score) * 100 ELSE 0 END), 2) AS media_percentual
                FROM audits
                WHERE status = %s
                  AND COALESCE(audit_date, timestamp)::TIMESTAMP >= %s
                  AND COALESCE(audit_date, timestamp)::TIMESTAMP < %s
                GROUP BY operator_name
            )
            SELECT
                ast.*,
                COALESCE(col.matricula, '') AS matricula,
                COALESCE(col.supervisor, '') AS supervisor,
                COALESCE(col.setor, '') AS setor,
                COALESCE(col.escala, '') AS escala,
                COALESCE(col.status, 'ATIVO') AS status,
                COALESCE(col.id_huawei, '') AS id_huawei,
                COALESCE(col.id_weon, '') AS id_weon
            FROM audit_stats ast
            LEFT JOIN colaboradores col ON col.id = (
                SELECT id FROM colaboradores c
                WHERE c.nome = ast.operator_name LIMIT 1
            )
            ORDER BY ast.operator_name
        """
        c.execute(sql, [AUDIT_STATUS_APPROVED, date_start, date_end])
        results = {}
        for row in c.fetchall():
            results[row["operator_name"]] = dict(row)
        return results
    finally:
        conn.close()


def generate_planejamento_pdf(
    get_connection,
    month: int,
    year: int,
    sector_id: Optional[str] = None,
) -> io.BytesIO:
    """Gera PDF consolidado mensal com os dados de auditoria por operador."""
    operators = _fetch_operator_data(get_connection, month, year)

    # Filtrar por setor se especificado
    if sector_id:
        operators = {
            k: v for k, v in operators.items()
            if v.get("setor", "").lower() == sector_id.lower()
        }

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = _build_styles()
    story = []

    mes_nome = MESES_PT.get(month, str(month))
    now = datetime.now()

    # ══════════════════════════════════════════════
    # HEADER
    # ══════════════════════════════════════════════
    story.append(Paragraph(
        "NSTECH — Fechamento Mensal de Auditoria",
        styles["NSTechTitle"]
    ))
    story.append(Paragraph(
        f"Período: {mes_nome} / {year}  •  "
        f"Gerado em {now.strftime('%d/%m/%Y às %H:%M')}  •  "
        f"Setor: {sector_id.upper() if sector_id else 'TODOS'}",
        styles["NSTechSubtitle"]
    ))
    story.append(HRFlowable(
        width="100%", thickness=1, color=NSTECH_BLUE, spaceAfter=12
    ))

    # ══════════════════════════════════════════════
    # KPIs
    # ══════════════════════════════════════════════
    total_ops = len(operators)
    if total_ops > 0:
        total_ligacoes = sum(op.get("total_ligacoes", 0) for op in operators.values())
        notas = []
        for op in operators.values():
            notas.append(op.get("media_percentual", 0))
        nota_media = sum(notas) / len(notas) if notas else 0
        aprovados = sum(1 for n in notas if n >= 80)
        taxa_aprov = (aprovados / total_ops * 100) if total_ops > 0 else 0
    else:
        total_ligacoes = 0
        nota_media = 0
        aprovados = 0
        taxa_aprov = 0

    kpi_data = [
        [
            Paragraph(str(total_ops), styles["KPIValue"]),
            Paragraph(str(total_ligacoes), styles["KPIValue"]),
            Paragraph(f"{nota_media:.1f}%", styles["KPIValue"]),
            Paragraph(f"{taxa_aprov:.0f}%", styles["KPIValue"]),
        ],
        [
            Paragraph("Operadores", styles["KPILabel"]),
            Paragraph("Ligações auditadas", styles["KPILabel"]),
            Paragraph("Nota média", styles["KPILabel"]),
            Paragraph("Taxa de aprovação", styles["KPILabel"]),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[6.5 * cm] * 4)
    kpi_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("BACKGROUND", (0, 0), (-1, -1), ROW_ALT),
        ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
        ("LINEBEFORE", (1, 0), (1, -1), 0.5, LIGHT_GRAY),
        ("LINEBEFORE", (2, 0), (2, -1), 0.5, LIGHT_GRAY),
        ("LINEBEFORE", (3, 0), (3, -1), 0.5, LIGHT_GRAY),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 14))

    # ══════════════════════════════════════════════
    # TABELA DE OPERADORES
    # ══════════════════════════════════════════════
    story.append(Paragraph("Desempenho por Operador", styles["SectionTitle"]))

    HEADERS = ["#", "Matrícula", "Colaborador", "Nota Telefônica",
               "Ligações", "Status", "Turno / Escala",
               "Supervisor", "Setor"]

    header_cells = [
        Paragraph(f'<b><font color="#FFFFFF">{h}</font></b>', styles["TableCell"])
        for h in HEADERS
    ]
    table_data = [header_cells]

    col_widths = [
        1 * cm,     # #
        2.3 * cm,   # Matrícula
        5.5 * cm,   # Colaborador
        2.8 * cm,   # Nota
        2 * cm,     # Ligações
        2 * cm,     # Status
        3.5 * cm,   # Turno
        4 * cm,     # Supervisor
        3 * cm,     # Setor
    ]

    seq = 1
    for name in sorted(operators.keys()):
        op = operators[name]

        media = op.get("media_nota", 0)
        pct = op.get("media_percentual", 0)

        if pct >= 80:
            nota_color = "#16A34A"  # green
        elif pct >= 60:
            nota_color = "#CA8A04"  # yellow
        else:
            nota_color = "#DC2626"  # red

        status = op.get("status", "ATIVO")
        status_color = "#16A34A" if status == "ATIVO" else "#64748B"

        row = [
            Paragraph(str(seq), styles["TableCell"]),
            Paragraph(op.get("matricula", ""), styles["TableCell"]),
            Paragraph(f"<b>{_esc(name)}</b>", styles["TableCellBold"]),
            Paragraph(
                f'<font color="{nota_color}"><b>{media:.2f}</b></font>'
                f'  <font color="#64748B" size="7">({pct:.0f}%)</font>',
                styles["TableCell"]
            ),
            Paragraph(str(op.get("total_ligacoes", 0)), styles["TableCell"]),
            Paragraph(
                f'<font color="{status_color}">{status}</font>',
                styles["TableCell"]
            ),
            Paragraph(op.get("escala", ""), styles["TableCell"]),
            Paragraph(op.get("supervisor", ""), styles["TableCell"]),
            Paragraph(op.get("setor", ""), styles["TableCell"]),
        ]
        table_data.append(row)
        seq += 1

    if total_ops == 0:
        table_data.append([
            Paragraph(
                '<font color="#64748B">Nenhuma auditoria aprovada neste período.</font>',
                styles["TableCell"]
            ),
            "", "", "", "", "", "", "", ""
        ])

    op_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    table_style_cmds = [
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        # Body
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),   # #
        ("ALIGN", (3, 1), (4, -1), "CENTER"),    # Nota e Ligações
        ("ALIGN", (5, 1), (5, -1), "CENTER"),    # Status
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.5, LIGHT_GRAY),
    ]

    # Zebra striping
    for row_idx in range(1, len(table_data)):
        if row_idx % 2 == 0:
            table_style_cmds.append(
                ("BACKGROUND", (0, row_idx), (-1, row_idx), ROW_ALT)
            )

    op_table.setStyle(TableStyle(table_style_cmds))
    story.append(op_table)

    # ══════════════════════════════════════════════
    # FOOTER
    # ══════════════════════════════════════════════
    story.append(Spacer(1, 20))
    story.append(HRFlowable(
        width="100%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=6
    ))
    story.append(Paragraph(
        f"NSTECH Auditoria de Qualidade  •  "
        f"Relatório gerado automaticamente em {now.strftime('%d/%m/%Y %H:%M')}  •  "
        f"Confidencial",
        styles["SmallGray"]
    ))

    doc.build(story)
    output.seek(0)
    return output


def _esc(s: str) -> str:
    """Escapa caracteres especiais para reportlab Paragraph."""
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
