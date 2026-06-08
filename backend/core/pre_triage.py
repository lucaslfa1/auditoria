import asyncio
import io
import json
import logging
import os
import unicodedata
from typing import Any, Optional

from pydub import AudioSegment

logger = logging.getLogger(__name__)

_OPERATOR_LABELS = {"operador", "atendente"}
_EXTERNAL_LABELS = {
    "cliente",
    "condutor",
    "interlocutor",
    "motorista",
    "policia",
    "ponto de apoio",
    "supervisor",
    "transportadora",
}
_TELEPHONY_LABELS = {"telefonia", "sistema", "ura"}

_OUTBOUND_TELEPHONY_MARKERS = (
    "caixa postal",
    "chamada esta sendo encaminhada",
    "deixe seu recado",
    "telefone tocando",
    "tuu",
)
_OUTBOUND_CONTACT_MARKERS = (
    "conseguiria falar com",
    "estou falando com",
    "eu falo com",
    "falo com a senhora",
    "falo com o senhor",
    "gostaria de falar com",
    "queria falar com",
    "to falando com",
)
_OUTBOUND_REASON_MARKERS = (
    "alerta de temperatura",
    "estou com um alerta",
    "estou entrando em contato",
    "meu contato e referente",
    "nao conseguimos contato",
    "perdeu posicao",
    "posicao em atraso",
    "referente a sua viagem",
    "referente ao veiculo",
    "suspeita de sinistro",
    "tentativa de contato",
    "queria falar sobre uma placa",
)
_INBOUND_STRONG_MARKERS = (
    "como posso ajudar",
    "em que posso ajudar",
    "em que posso ser util",
    "no que posso ajudar",
    "no que posso ser util",
    "posso ajuda la",
    "posso ajuda lo",
    "posso ajudar",
    "pois nao",
)
_INBOUND_GREETING_MARKERS = (
    "alo opentech bom dia",
    "alo opentech boa noite",
    "alo opentech boa tarde",
    "central de atendimento",
    "central de monitoramento",
    "obrigada por ligar",
    "obrigado por ligar",
    "opentech bom dia",
    "opentech boa noite",
    "opentech boa tarde",
)


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)
    return " ".join(text.split())


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _split_speaker_text(raw_text: Any) -> tuple[str, str]:
    text = str(raw_text or "").strip()
    prefix, separator, body = text.partition(":")
    if separator and len(prefix) <= 40:
        return _normalize_text(prefix), body.strip()
    return "", text


def _speaker_role(speaker: str) -> str:
    normalized = _normalize_text(speaker)
    if any(label in normalized for label in _TELEPHONY_LABELS):
        return "telephony"
    if any(label in normalized for label in _OPERATOR_LABELS):
        return "operator"
    if any(label in normalized for label in _EXTERNAL_LABELS):
        return "external"
    return ""


def _first_utterances(segments: list[dict[str, Any]], limit: int = 6) -> list[dict[str, str]]:
    utterances: list[dict[str, str]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        raw_text = segment.get("text") or ""
        prefixed_speaker, body = _split_speaker_text(raw_text)
        explicit_speaker = _normalize_text(segment.get("speaker") or "")
        speaker = explicit_speaker or prefixed_speaker
        normalized_body = _normalize_text(body)
        if not normalized_body:
            continue
        utterances.append(
            {
                "speaker": speaker,
                "role": _speaker_role(speaker),
                "text": str(body or "").strip(),
                "normalized": normalized_body,
            }
        )
        if len(utterances) >= limit:
            break
    return utterances


def _infer_direction_from_segments(segments: list[dict[str, Any]]) -> Optional[bool]:
    """Return True for inbound, False for outbound, None when ambiguous."""

    utterances = _first_utterances(segments)
    if not utterances:
        return None

    first = utterances[0]
    first_role = first["role"]
    first_text = first["normalized"]
    early_text = " ".join(item["normalized"] for item in utterances[:4])

    if first_role == "telephony" or _contains_any(early_text, _OUTBOUND_TELEPHONY_MARKERS):
        return False

    inbound_score = 0
    outbound_score = 0

    if first_role == "external":
        outbound_score += 4
    elif first_role == "operator":
        inbound_score += 1

    if _contains_any(early_text, _OUTBOUND_CONTACT_MARKERS):
        outbound_score += 3
    if first_role == "operator" and _contains_any(early_text, _OUTBOUND_REASON_MARKERS):
        outbound_score += 2

    if _contains_any(first_text, _INBOUND_STRONG_MARKERS):
        inbound_score += 4
    elif _contains_any(early_text, _INBOUND_STRONG_MARKERS):
        inbound_score += 2

    if first_role == "operator" and _contains_any(first_text, _INBOUND_GREETING_MARKERS):
        inbound_score += 2

    if outbound_score >= 3 and outbound_score > inbound_score:
        return False
    if inbound_score >= 3 and inbound_score > outbound_score:
        return True
    return None


def _detect_service_greeting(utterances: list[dict[str, Any]]) -> bool:
    """True quando, nas primeiras falas, aparece uma frase de atendimento de quem
    RECEBE a ligacao (oferta de ajuda / saudacao de central pelo operador),
    indicando receptiva.

    Usado como sinal DETERMINISTICO antes da IA: setores de risco so auditam
    ligacoes ativas, entao uma frase de atendimento clara basta para classificar
    receptiva, sem depender do desempate da IA (que pode responder 'AMBIGUOUS' e
    deixar a receptiva vazar)."""
    if not utterances:
        return False
    early = utterances[:4]
    early_text = " ".join(item["normalized"] for item in early)
    # Sinais outbound claros afastam a hipotese de receptiva (evita falso positivo):
    # telefonia (caixa postal/URA), abertura de contato e MOTIVO de quem ligou.
    if (
        _contains_any(early_text, _OUTBOUND_TELEPHONY_MARKERS)
        or _contains_any(early_text, _OUTBOUND_CONTACT_MARKERS)
        or _contains_any(early_text, _OUTBOUND_REASON_MARKERS)
    ):
        return False
    # Frase de atendimento forte ("em que posso ajudar", "pois nao", ...).
    if _contains_any(early_text, _INBOUND_STRONG_MARKERS):
        return True
    # Saudacao de central dita pelo operador.
    for item in early:
        if item["role"] == "operator" and _contains_any(item["normalized"], _INBOUND_GREETING_MARKERS):
            return True
    return False


def _load_few_shot_examples() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(base_dir, "instrucoes", "telefonia", "exemplos_direcao.json")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        lines = []
        for i, ex in enumerate(data):
            lines.append(f"Exemplo {i+1} ({ex.get('direcao', 'UNKNOWN')}):\n{ex.get('text') or ex.get('exemplo')}\n")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning(f"Erro ao carregar exemplos few-shot: {exc}")
        return ""


def _slice_audio_to_wav(audio_bytes: bytes, duration_ms: int) -> bytes:
    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
    sliced = audio[: max(1000, int(duration_ms or 0))]
    out = io.BytesIO()
    sliced.export(out, format="wav")
    return out.getvalue()


def _transcribe_diarized_excerpt(audio_bytes: bytes) -> list[dict[str, Any]]:
    from core.transcription import transcribe_audio_gpt4o_diarize

    return transcribe_audio_gpt4o_diarize(
        audio_bytes,
        "audio/wav",
        "Operador",
        "Motorista",
    )


async def analyze_call_direction(audio_bytes: bytes, duration_ms: int = 30000) -> Optional[bool]:
    """
    Analisa o inicio da ligacao por GPT-4o diarize e classifica a direcao (INBOUND/OUTBOUND)
    com GPT-4o e Few-Shot JSON, substituindo regras fixas por Raciocinio Semantico.

    Retorna True para RECEPTIVA/INBOUND, False para ATIVA/OUTBOUND e None
    quando a transcricao ou as evidencias ficarem ambiguas.
    """
    if not audio_bytes:
        logger.warning("Pre-triage direction skipped: empty audio")
        return None

    try:
        sliced_bytes = await asyncio.to_thread(_slice_audio_to_wav, audio_bytes, duration_ms)
        segments = await asyncio.to_thread(_transcribe_diarized_excerpt, sliced_bytes)
    except Exception as exc:
        logger.exception("Erro na pre-triagem (transcricao): %s", exc)
        return None

    if not segments:
        return None
        
    utterances = _first_utterances(segments)
    if not utterances:
        return None

    dialogue = "\n".join(f"[{u['speaker']}]: {u['text']}" for u in utterances)
    
    first = utterances[0]
    early_text = " ".join(item["normalized"] for item in utterances[:4])
    if first["role"] == "telephony" or _contains_any(early_text, _OUTBOUND_TELEPHONY_MARKERS):
        logger.info("Pre-triage direction: OUTBOUND detected by telephony markers")
        return False

    # Sinal DETERMINISTICO: frase de atendimento do operador => receptiva (INBOUND),
    # com precedencia sobre a IA (que poderia responder AMBIGUOUS e deixar vazar).
    if _detect_service_greeting(utterances):
        logger.info("Pre-triage direction: INBOUND por frase de atendimento (deterministico)")
        return True

    examples = await asyncio.to_thread(_load_few_shot_examples)
    
    sys_prompt = (
        "Você é um classificador especializado em chamadas de Gerenciamento de Risco. "
        "Analise os primeiros segundos da transcrição fornecida e determine se a chamada foi "
        "EFETUADA pelo operador (OUTBOUND) ou RECEBIDA pelo operador (INBOUND).\n\n"
        "Se não for possível determinar com segurança, responda AMBIGUOUS.\n\n"
        "Retorne EXATAMENTE um JSON no formato:\n"
        '{"analise": "sua justificativa breve", "direcao": "INBOUND" | "OUTBOUND" | "AMBIGUOUS"}\n\n'
    )
    if examples:
        sys_prompt += f"EXEMPLOS DE REFERÊNCIA (Few-Shot):\n{examples}\n"

    try:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        key = os.getenv("AZURE_OPENAI_KEY")
        if not endpoint or not key:
            raise ValueError("Azure OpenAI credentials not set")
            
        from openai import AsyncAzureOpenAI
        client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=key,
            api_version="2025-01-01-preview"
        )
        resp = await client.chat.completions.create(
            model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": f"Transcrição:\n{dialogue}"}
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "PreTriageDirection",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "analise": {"type": "string"},
                            "direcao": {
                                "type": "string",
                                "enum": ["INBOUND", "OUTBOUND", "AMBIGUOUS"]
                            }
                        },
                        "required": ["analise", "direcao"],
                        "additionalProperties": False
                    },
                    "strict": True
                }
            },
            temperature=0.1,
            max_tokens=150
        )
        content = resp.choices[0].message.content or ""
        parsed = json.loads(content)
        direcao = str(parsed.get("direcao", "")).strip().upper()
        
        if direcao == "INBOUND":
            logger.info(f"Pre-triage direction: INBOUND detected by AI (Analise: {parsed.get('analise')})")
            return True
        elif direcao == "OUTBOUND":
            logger.info(f"Pre-triage direction: OUTBOUND detected by AI (Analise: {parsed.get('analise')})")
            return False
        else:
            logger.warning(f"Pre-triage direction ambiguous by AI (Analise: {parsed.get('analise')})")
            return None
    except Exception as e:
        logger.exception("Erro ao usar IA para classificar direção: %s. Fallback para regras antigas.", e)
        # Fallback to old rules
        decision = _infer_direction_from_segments(segments)
        if decision is True:
            logger.info("Pre-triage direction: INBOUND detected by fallback rules")
        elif decision is False:
            logger.info("Pre-triage direction: OUTBOUND detected by fallback rules")
        else:
            logger.warning("Pre-triage direction ambiguous by fallback rules")
        return decision
