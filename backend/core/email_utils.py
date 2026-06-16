"""Notificações por e-mail (SMTP) para eventos do sistema de auditoria.

Hoje cobre apenas a notificação de cadastro de novas instruções/feedback para a IA.
O envio usa SMTP direto (default ``smtp.gmail.com:587`` com STARTTLS); credenciais e
servidor vêm de variáveis de ambiente (``SMTP_SERVER``, ``SMTP_PORT``, ``SMTP_USER``,
``SMTP_PASSWORD``). Sem essas credenciais o envio é silenciosamente pulado.

Sem custo de API paga (Azure OpenAI/Speech); efeito colateral é apenas rede (SMTP).
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
DESTINATION_EMAIL = "lucas.lfa.sc@gmail.com"

def send_new_feedback_email(feedback: Dict[str, Any]):
    """Envia e-mail de notificação quando uma nova instrução/feedback para a IA é cadastrada.

    O destinatário é fixo (``DESTINATION_EMAIL``). O corpo é montado a partir das
    chaves do dict ``feedback`` (``tipo``, ``setor``, ``criterio_id``, ``criado_por``,
    ``situacao``, ``correcao``, ``justificativa`` e o opcional ``exemplo_transcricao``).

    Efeitos colaterais: abre conexão SMTP e envia o e-mail (rede). Não lança em caso
    de falha — se as credenciais SMTP não estiverem configuradas, apenas registra um
    warning e retorna; qualquer erro de envio é capturado e logado como erro, sem
    propagar (o cadastro do feedback não deve falhar por causa do e-mail).
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning(
            "SMTP credentials (SMTP_USER/SMTP_PASSWORD) not configured. "
            "Skipping email notification for AI Feedback."
        )
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = DESTINATION_EMAIL
        msg["Subject"] = f"Nova Instrução para IA Cadastrada: {feedback.get('tipo', 'Global')}"

        body = f"""
Nova instrução para a IA cadastrada no sistema:

- Tipo: {feedback.get('tipo')}
- Setor: {feedback.get('setor') or 'Global'}
- Critério: {feedback.get('criterio_id') or 'N/A'}
- Criado por: {feedback.get('criado_por')}

SITUAÇÃO (O que aconteceu):
{feedback.get('situacao')}

CORREÇÃO (O que deveria ter feito):
{feedback.get('correcao')}

JUSTIFICATIVA:
{feedback.get('justificativa')}
"""
        
        exemplo = feedback.get('exemplo_transcricao')
        if exemplo:
            body += f"\nEXEMPLO DE TRANSCRIÇÃO:\n{exemplo}\n"

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            
        logger.info(f"Email de notificação de feedback enviado com sucesso para {DESTINATION_EMAIL}")
    except Exception as e:
        logger.error(f"Failed to send feedback email: {e}")
