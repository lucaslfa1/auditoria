import asyncio
import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

from schemas import AuditAlert, AuditResultDetail, TranscriptionSegment
from core.evaluation import parse_json_with_repair
from core.config import (
    AI_ENABLED,
    AI_MODEL,
    AI_PROVIDER_PRIORITY,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    PROMPTS_CONFIG,
    ai_client,
)

# Limite seguro de caracteres para a transcrição enviada à IA.
# Evita estouro de contexto (token limit) e OOM em transcrições longas.
_MAX_TRANSCRIPTION_CHARS = 150_000

async def regenerate_summary_and_feedback(
    transcription: list[TranscriptionSegment],
    alert: AuditAlert,
    details: list[AuditResultDetail],
    operator_name: Optional[str] = None
) -> dict[str, str]:
    """
    Calls the AI to regenerate only the summary and AI feedback given the manually edited criteria details.
    """
    
    # Montar o prompt apenas para os textos
    transcription_text = []
    for i, seg in enumerate(transcription):
        transcription_text.append(f"[{i:04d}] [{seg.start} -> {seg.end}] {seg.text}")
    transcription_str = "\n".join(transcription_text)[:_MAX_TRANSCRIPTION_CHARS]
    
    alert_context = alert.context or "N/A"
    alert_label = alert.label or "N/A"
    
    # Format the current evaluated details
    criteria_results_text = []
    for d in details:
        criteria_results_text.append(
            f"Critério: {d.label}\nStatus Manual: {d.status.upper()}\nComentário: {d.comment}\n"
        )
    criteria_str = "\n".join(criteria_results_text)
    
    schema_hint = '''{
  "summary": "Resumo da auditoria atualizado...",
  "ai_feedback": "Feedback para o operador atualizado..."
}'''

    system_prompt = f"""
Voce é uma IA Especialista em Qualidade de Atendimento (QA).
Sua tarefa NÃO é avaliar a ligação. A avaliação JÁ FOI FEITA MANUALMENTE pelo auditor humano.
Sua tarefa é EXCLUSIVAMENTE redigir o 'Resumo da Auditoria' e o 'Feedback para o operador' com base nas NOTAS que o auditor humano acabou de dar.

ALERTA DE CONTEXTO: {alert_label} - {alert_context}
OPERADOR(A): {operator_name or "Desconhecido"}

Abaixo, os critérios e suas respectivas NOTAS MANUAIS (PASS, FAIL, PARTIAL, NA):
{criteria_str}

DIRETRIZES PARA O RESUMO:
- Seja simples, claro e direto ao ponto (3-4 linhas). Use linguagem natural, humana e técnica, sem tentar enfeitar ou soar excessivamente corporativo.
- Documente o que as notas refletem. Se o auditor zerou ou reprovou a Senha da Viagem, mencione claramente no resumo que a senha foi reprovada ou teve falha.
- Se o operador cometeu erros críticos, explique de forma objetiva o que ocorreu.
- Não use termos em inglês como "resultou em um FAIL nesse critério", prefira sempre termos em português simples como "resultou em uma falha no critério".

DIRETRIZES PARA O FEEDBACK:
- Redija de forma direta, técnica e construtiva, sem jargões corporativos vazios. Dirija-se ao operador em terceira pessoa ou diretamente.
- Reflita fielmente os pontos de falha que o auditor deixou nos comentários.
- Dê orientações simples baseadas apenas nas regras que falharam (FAIL ou PARTIAL).
- Se tudo foi aprovado (PASS), dê um feedback positivo, curto e natural.

Devolva APENAS um JSON válido.
SCHEMA:
{schema_hint}
"""

    if AI_PROVIDER_PRIORITY == "azure" and AZURE_OPENAI_KEY and AZURE_OPENAI_ENDPOINT:
        # Cloud Run: instanciar o cliente localmente em vez de singleton global.
        # Conexões TCP ociosas sofrem drop silencioso quando a CPU congela a 0%.
        from openai import AsyncAzureOpenAI
        client = AsyncAzureOpenAI(
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_KEY,
            api_version="2025-01-01-preview",
            timeout=60.0,
        )
        completion = await client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"TRANSCRICAO:\n{transcription_str}"}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )
        response_text = completion.choices[0].message.content
    else:
        # Fallback Gemini: generate_content é síncrono, precisa de to_thread
        from core.config import GENERATION_CONFIG  # lazy: evita google.genai no boot
        resp = await asyncio.to_thread(
            ai_client.models.generate_content,
            model=AI_MODEL,
            contents=[system_prompt, f"TRANSCRICAO:\n{transcription_str}"],
            config=GENERATION_CONFIG
        )
        response_text = resp.text
        
    # parse_json_with_repair pode fazer chamadas HTTP bloqueantes se o JSON
    # vier malformado; isolamos em thread para não travar o Event Loop.
    parsed = await asyncio.to_thread(parse_json_with_repair, response_text or "{}", schema_hint)
    return {
        "summary": parsed.get("summary", ""),
        "ai_feedback": parsed.get("ai_feedback", "")
    }
