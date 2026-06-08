from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

OUTPUT_PATH = Path("export/plano_gerencial_auditoria.pdf")

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
    
    styles.add(ParagraphStyle(
        name="TitleCenter", parent=styles["Title"], alignment=TA_CENTER,
        fontSize=20, leading=26, textColor=colors.HexColor("#16324f"), spaceAfter=10
    ))
    styles.add(ParagraphStyle(
        name="Section", parent=styles["Heading2"], fontSize=14, leading=18,
        textColor=colors.HexColor("#0f4c81"), spaceBefore=12, spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name="Body", parent=styles["BodyText"], fontSize=11, leading=15, spaceAfter=6, alignment=TA_JUSTIFY
    ))

    doc = SimpleDocTemplate(
        str(OUTPUT_PATH), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm, bottomMargin=18*mm,
        title="Relatório Executivo de Status - Auditoria NSTECH", author="Equipe Técnica"
    )

    story = [
        Paragraph("Sistema de Auditoria NSTECH", styles["TitleCenter"]),
        Paragraph("Relatório Executivo de Status e Próximas Etapas", styles["Heading2"]),
        Paragraph("Introdução", styles["Section"]),
        Paragraph(
            "Este documento apresenta de forma resumida o status de desenvolvimento e "
            "as etapas de evolução para o sistema de Auditoria NSTECH. Nele, consolidamos as melhorias já atingidas e "
            "as frentes nas quais estamos trabalhando neste momento visando estabilidade, automação e usabilidade ideal.", styles["Body"]
        ),
        
        Spacer(1, 10),
        Paragraph("1. O que já foi entregue e está em revisão", styles["Section"]),
        build_bullet_list([
            "<b>Aprimoramento do Motor de Inteligência Artificial:</b> Refinamos a precisão das avaliações realizadas pela IA, incluindo regras estritas de zeramento automático de nota para faltas graves (ex: problemas no fornecimento de senhas ou recusa de acesso).",
            "<b>Melhorias na Interface do Supervisor:</b> Atualização das telas internas da gestão. Adição de um player de áudio direto no portal, botões simplificados de exportação de dados e permissão para que supervisores realizem descarte de auditorias que preenchem a cota de limite dos operadores incorretamente.",
            "<b>Fluxo Funcional e Nuvem:</b> O sistema está no ar de forma estável na nuvem, sendo capaz de transcrever e avaliar áudios complexos na velocidade da máquina, entregando resultados consolidados em um painel único.",
            "<b>Data Correta em Auditoria:</b> As validações e contagens de ocorrências processadas migraram da data em que os áudios foram inseridos para a data de fato em que o telefonema ocorreu, organizando relatórios."
        ], styles["Body"]),

        Spacer(1, 10),
        Paragraph("2. Próximos Passos (O que falta construir)", styles["Section"]),
        build_bullet_list([
            "<b>Integração Direta com a Telefonia (Huawei):</b> Esse é o maior desafio atual. Construir a captura totalmente automatizada para receber dezenas de gravações diretamente da central telefônica Huawei (seja na nuvem ou fixa) sem necessitar que alguém as baixe e adicione na plataforma.",
            "<b>Modo Planilha de Exportação:</b> Criação e formatação visual de uma planilha de exportação. Esta planilha terá uma estrutura final com dados validados a serem exportados para o dashboard de quartil, logo após passarem pela fase de contestação das lideranças.",
            "<b>Refinamento da Segurança Corporativa:</b> Elevação dos parâmetros internos de segurança dos servidores aos mais rígidos protocolos exigidos, introduzindo o sistema de Cofres Digitais contra vazamento de senhas.",
            "<b>Polimento Final e UX do Usuário (Frontend):</b> Lapidação das ações onde múltiplos carregamentos ocorrem ao mesmo tempo na plataforma, para garantir que nunca causem congelamento ou problemas visuais no caso de excesso de informações assíncronas simultâneas.",
            "<b>Monitoramento de Negócio e Telemetria de Logs:</b> Criação de uma matriz de acompanhamento interna para registrar a estabilidade contínua e prevenir possíveis picos de consumo causados pelo motor de Inteligência Artificial."
        ], styles["Body"]),
        
        Spacer(1, 20),
        Paragraph("Conclusão", styles["Section"]),
        Paragraph(
            "Nosso panorama atual apresenta a plataforma madura e robusta para avaliar operadores com alta assertividade. "
            "Os investimentos técnicos a partir de agora seguem predominantemente voltados à diminuição da carga de trabalho humana das lideranças, "
            "focando em automatizar totalmente não apenas as notas lidas, mas também a importação regular dos volumes telefônicos (Fase Huawei).",
            styles["Body"]
        ),
    ]

    doc.build(story)
    print(f"PDF executivo gerado com sucesso em: {OUTPUT_PATH.absolute()}")

if __name__ == "__main__":
    main()
