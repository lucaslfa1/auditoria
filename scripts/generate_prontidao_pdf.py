from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


OUTPUT_PATH = Path("export/prontidao_apresentacao_nstech_2026-03-02.pdf")


def build_bullet_list(items: list[str], style: ParagraphStyle) -> ListFlowable:
    return ListFlowable(
        [ListItem(Paragraph(item, style)) for item in items],
        bulletType="bullet",
        start="circle",
        leftIndent=16,
    )


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleCenter",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#16324f"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#0f4c81"),
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body",
            parent=styles["BodyText"],
            fontSize=10.5,
            leading=15,
            spaceAfter=4,
        )
    )

    doc = SimpleDocTemplate(
        str(OUTPUT_PATH),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Prontidao para Apresentacao - nstech",
        author="nstech",
    )

    story = [
        Paragraph("Sistema de Auditoria nstech", styles["TitleCenter"]),
        Paragraph("Relatorio executivo de prontidao para apresentacao", styles["Heading2"]),
        Paragraph("Data: 2 de marco de 2026", styles["Body"]),
        Spacer(1, 10),
        Table(
            [[
                Paragraph("<b>Status recomendado</b><br/>Pronto para apresentacao controlada", styles["Body"]),
                Paragraph("<b>Escopo validado</b><br/>Arquitetura, testes, build, lint e smoke local", styles["Body"]),
            ]],
            colWidths=[82 * mm, 82 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4fb")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#b8cde2")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#b8cde2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]),
        ),
        Spacer(1, 12),
        Paragraph("Resumo executivo", styles["Section"]),
        Paragraph(
            "A revisao tecnica confirmou que os bloqueadores principais da apresentacao foram removidos. "
            "O sistema agora suporta demonstracao local com autenticacao funcional, nao injeta dados ficticios no dashboard "
            "e possui validacoes automatizadas estaveis para o fluxo principal.",
            styles["Body"],
        ),
        Paragraph("Correcoes aplicadas", styles["Section"]),
        build_bullet_list(
            [
                "Login local ajustado para funcionar em HTTP no modo empacotado.",
                "Remocao dos mocks automaticos do dashboard quando a base esta vazia.",
                "Configuracao de autenticacao endurecida, com suporte a arquivo de usuarios e segredo de sessao efemero quando ausente.",
                "Escopo do lint corrigido para analisar apenas o app principal.",
                "Testes de autenticacao estabilizados para nao depender do ambiente local.",
            ],
            styles["Body"],
        ),
        Paragraph("Validacoes executadas", styles["Section"]),
        build_bullet_list(
            [
                "npm run test: OK, com frontend e backend aprovados.",
                "npm run lint: OK.",
                "npm run build: OK.",
                "Smoke test local: backend sobe, frontend carrega, login funciona, sessao persiste e logout responde corretamente.",
            ],
            styles["Body"],
        ),
        Paragraph("Ressalvas remanescentes", styles["Section"]),
        build_bullet_list(
            [
                "Recomenda-se um ensaio final com arquivos reais antes da apresentacao ao cliente.",
                "As integracoes externas de IA continuam dependentes das credenciais e do ambiente final.",
                "A operacao pode se beneficiar de um roteiro curto de demonstracao e checklist pre-apresentacao.",
            ],
            styles["Body"],
        ),
        Paragraph("Conclusao", styles["Section"]),
        Paragraph(
            "Na data de 2 de marco de 2026, a recomendacao e apresentar o sistema em formato controlado, "
            "com ambiente previamente ensaiado e dados reais ja separados para demonstracao.",
            styles["Body"],
        ),
    ]

    doc.build(story)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
