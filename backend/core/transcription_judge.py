"""Juiz LLM de desempate entre dois candidatos de transcricao.

Papel no fluxo: o selector deterministico (`core/transcription_selector.py`)
escolhe o melhor candidato por regras; quando dois candidatos ficam num "empate"
(scores muito proximos), este modulo aciona um juiz GPT-4o que le os dois textos
e decide qual e mais fiel ao audio, marcando tambem possiveis alucinacoes.

CUSTO DE API: SIM. `judge_tie_break` faz UMA chamada paga a Azure OpenAI
(chat.completions GPT-4o, deployment `AZURE_OPENAI_DEPLOYMENT`, registrada via
`core.cost_guard`). So e chamado no caso de empate, nao em toda transcricao.

Contrato de robustez: qualquer falha (prompt ausente em PROMPTS_CONFIG, cliente
sem credencial, JSON invalido na resposta, excecao na chamada) faz a funcao
retornar None silenciosamente — o caller trata None como "juiz nao resolveu" e
cai no fallback deterministico ja existente. Nunca propaga excecao.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.transcription_candidates import TranscriptionCandidate

logger = logging.getLogger(__name__)


_MAX_TEXT_CHARS_PER_CANDIDATE = 8000


@dataclass(frozen=True)
class JudgeOutcome:
    """Resultado estruturado da decisao do juiz LLM.

    Campos:
    - winner_label: "A", "B" ou "tie" (empate, juiz nao escolheu vencedor).
    - winner_candidate_id: candidate_id do vencedor (None quando "tie").
    - confidence: confianca do juiz no intervalo [0.0, 1.0].
    - reason: justificativa textual curta da decisao.
    - scores: notas por candidato (mapa candidate_id/label -> [0.0, 1.0]).
    - hallucinations: trechos suspeitos de alucinacao por candidate_id.
    - raw_response: payload JSON bruto retornado pelo modelo.
    """

    winner_label: str
    winner_candidate_id: Optional[str]
    confidence: float
    reason: str
    scores: dict[str, float] = field(default_factory=dict)
    hallucinations: dict[str, list[str]] = field(default_factory=dict)
    raw_response: Any = None

    @property
    def resolved(self) -> bool:
        """True quando o juiz escolheu um vencedor concreto (A ou B com id)."""
        return self.winner_label in {"A", "B"} and bool(self.winner_candidate_id)


def _serialize_segments(candidate: TranscriptionCandidate) -> str:
    """Achata os segmentos do candidato em texto "speaker: fala" por linha.

    Trunca em `_MAX_TEXT_CHARS_PER_CANDIDATE` (8000 chars) para limitar o tamanho
    do prompt enviado ao modelo. Ignora segmentos sem texto.
    """
    parts: list[str] = []
    total = 0
    for segment in candidate.segments or []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        speaker = str(segment.get("speaker") or "").strip()
        line = f"{speaker}: {text}" if speaker and not text.lower().startswith(speaker.lower() + ":") else text
        if total + len(line) > _MAX_TEXT_CHARS_PER_CANDIDATE:
            parts.append("[...truncado...]")
            break
        parts.append(line)
        total += len(line) + 1
    return "\n".join(parts).strip()


def _build_default_client():
    from core.config import AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY

    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_KEY:
        return None
    from openai import AzureOpenAI

    return AzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version="2025-01-01-preview",
        timeout=180.0,
    )


def _load_prompt_templates() -> Optional[dict[str, str]]:
    from core.config import PROMPTS_CONFIG

    block = PROMPTS_CONFIG.get("transcription_judge") if PROMPTS_CONFIG else None
    if not isinstance(block, dict):
        return None
    system = str(block.get("system") or "").strip()
    user = str(block.get("user") or "").strip()
    if not system or not user:
        return None
    return {"system": system, "user": user}


def _parse_judge_response(
    raw_text: str,
    *,
    candidate_a: TranscriptionCandidate,
    candidate_b: TranscriptionCandidate,
) -> Optional[JudgeOutcome]:
    """Converte a resposta JSON do juiz em JudgeOutcome, validando o conteudo.

    Retorna None quando o texto nao e JSON valido, nao e objeto, ou traz um
    `winner` fora de {A, B, TIE}. Faz coercao defensiva de confianca/scores para
    [0.0, 1.0] e resolve `winner_candidate_id` a partir do label quando omitido.
    """
    try:
        payload = json.loads(raw_text)
    except (TypeError, ValueError) as exc:
        logger.warning("[judge] resposta nao e JSON valido: %s", exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("[judge] payload nao e objeto: %r", type(payload).__name__)
        return None

    winner_label = str(payload.get("winner") or "").strip().upper()
    if winner_label not in {"A", "B", "TIE"}:
        logger.warning("[judge] winner invalido: %r", payload.get("winner"))
        return None

    winner_candidate_id = str(payload.get("winner_candidate_id") or "").strip() or None
    if winner_label == "A":
        winner_candidate_id = winner_candidate_id or candidate_a.candidate_id
    elif winner_label == "B":
        winner_candidate_id = winner_candidate_id or candidate_b.candidate_id
    else:
        winner_candidate_id = None

    confidence_raw = payload.get("confidence")
    try:
        confidence = float(confidence_raw) if confidence_raw is not None else 0.5
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    scores_raw = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    scores: dict[str, float] = {}
    for key, value in scores_raw.items():
        try:
            scores[str(key)] = max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            continue

    hallucinations = {
        candidate_a.candidate_id: [str(item) for item in (payload.get("hallucinations_a") or []) if item],
        candidate_b.candidate_id: [str(item) for item in (payload.get("hallucinations_b") or []) if item],
    }

    return JudgeOutcome(
        winner_label="tie" if winner_label == "TIE" else winner_label,
        winner_candidate_id=winner_candidate_id,
        confidence=confidence,
        reason=str(payload.get("reason") or "").strip(),
        scores=scores,
        hallucinations=hallucinations,
        raw_response=payload,
    )


def judge_tie_break(
    candidate_a: TranscriptionCandidate,
    candidate_b: TranscriptionCandidate,
    *,
    alert_id: str = "",
    alert_label: str = "",
    sector_id: str = "",
    operator_label: str = "Operador",
    driver_label: str = "Motorista",
    client: Any = None,
    deployment: Optional[str] = None,
) -> Optional[JudgeOutcome]:
    """Decide qual de dois candidatos de transcricao e mais fiel via LLM judge.

    CUSTO DE API: faz uma chamada paga a Azure OpenAI (GPT-4o) quando todas as
    pre-condicoes sao atendidas (prompt configurado, textos utilizaveis, cliente
    com credencial). A chamada e registrada em `core.cost_guard`.

    Params:
    - candidate_a / candidate_b: os dois candidatos a comparar.
    - alert_id / alert_label / sector_id: contexto do alerta, injetados no prompt.
    - operator_label / driver_label: rotulos de falante para o prompt.
    - client: cliente AzureOpenAI ja construido (opcional); se None, monta um
      default a partir das credenciais em `core.config`.
    - deployment: nome do deployment a usar (opcional); default
      `AZURE_OPENAI_DEPLOYMENT` ou "gpt-4o".

    Retorna None silenciosamente em qualquer falha (config ausente, cliente sem
    credencial, resposta invalida). Caller deve tratar None como "judge nao
    resolveu" e cair no fallback deterministico ja existente.
    """

    if candidate_a is None or candidate_b is None:
        return None
    if candidate_a.candidate_id == candidate_b.candidate_id:
        return None

    templates = _load_prompt_templates()
    if not templates:
        logger.info("[judge] prompt transcription_judge ausente em PROMPTS_CONFIG; pulando")
        return None

    text_a = _serialize_segments(candidate_a)
    text_b = _serialize_segments(candidate_b)
    if not text_a or not text_b:
        logger.info("[judge] candidato sem texto utilizavel; pulando")
        return None

    active_client = client or _build_default_client()
    if active_client is None:
        logger.info("[judge] cliente AzureOpenAI indisponivel; pulando")
        return None

    from core.config import AZURE_OPENAI_DEPLOYMENT

    deployment_name = deployment or AZURE_OPENAI_DEPLOYMENT or "gpt-4o"

    try:
        user_prompt = templates["user"].format(
            alert_id=alert_id or "",
            alert_label=alert_label or "",
            sector_id=sector_id or "",
            operator_label=operator_label or "Operador",
            driver_label=driver_label or "Motorista",
            provider_a=candidate_a.provider,
            candidate_id_a=candidate_a.candidate_id,
            score_a=f"{float(candidate_a.deterministic_score or 0.0):.2f}",
            text_a=text_a,
            provider_b=candidate_b.provider,
            candidate_id_b=candidate_b.candidate_id,
            score_b=f"{float(candidate_b.deterministic_score or 0.0):.2f}",
            text_b=text_b,
        )
    except KeyError as exc:
        logger.warning("[judge] template user com placeholder desconhecido: %s", exc)
        return None

    try:
        from core import cost_guard
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "judge_transcricao")
        response = active_client.chat.completions.create(
            model=deployment_name,
            messages=[
                {"role": "system", "content": templates["system"]},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            top_p=1,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        logger.warning("[judge] falha na chamada AzureOpenAI: %s", exc)
        return None

    try:
        raw_text = response.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError) as exc:
        logger.warning("[judge] resposta malformada do AzureOpenAI: %s", exc)
        return None

    outcome = _parse_judge_response(raw_text, candidate_a=candidate_a, candidate_b=candidate_b)
    if outcome is None:
        logger.warning("[judge] nao foi possivel interpretar JSON do juiz; raw=%r", raw_text[:200])
    else:
        logger.info(
            "[judge] resultado: winner=%s candidate_id=%s confidence=%.2f reason=%r",
            outcome.winner_label,
            outcome.winner_candidate_id,
            outcome.confidence,
            outcome.reason[:120],
        )
    return outcome


__all__ = ["JudgeOutcome", "judge_tie_break"]
