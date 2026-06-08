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
    """Sends an email notification when a new AI feedback is created."""
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
