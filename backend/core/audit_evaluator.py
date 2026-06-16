"""Avaliação GPT-4o da auditoria: prompt com critérios oficiais e parsing robusto.

Papel no fluxo: depois da transcrição (Azure Speech), este módulo recebe a
transcrição diarizada + o alerta classificado (com os critérios oficiais
carregados do catálogo no banco — módulo IA > Critérios) e devolve o payload
de avaliação normalizado: `summary`, `ai_feedback`, `details[]` (um item por
critério, com evidência literal e timestamp), `fatal_flags[]` e
`evidence_quality`. Consumido pela fachada `core/evaluation.py` (que injeta
as dependências reais via `build_audit_evaluation_dependencies`) e, através
dela, por `core/audit.py` no fluxo manual e na automação.

Zeragem: este módulo NÃO zera score — apenas transporta os `fatal_flags`
apontados pela IA; a zeragem 3-camadas (Camada 2 = fatal_flags) é aplicada
no scoring downstream, em `core/evaluation.py`.

CUSTO DE API (Azure OpenAI, pago):
- caminho principal `evaluate_with_azure`: 1 chamada GPT-4o por avaliação
  (registrada no `cost_guard` como categoria `avaliacao`) e, quando o payload
  vem inválido ou com evidência fraca (< `AUDIT_MIN_MATCHED_EVIDENCE_RATIO`),
  +1 chamada de retry (categoria `avaliacao_retry`). O retry de evidência
  fraca é a alavanca de custo `AUDIT_WEAK_EVIDENCE_RETRY` (default ON);
  o retry de payload INVÁLIDO independe dessa flag;
- +1 chamada de embedding por avaliação (`rag_triagem.gerar_embedding`,
  categoria `embedding`) para ranquear o feedback da auditora no prompt
  (fail-open: sem embedding, usa fallback cronológico);
- fallback `evaluate_transcription` usa o provedor alternativo (`ai_client`,
  ex.: Gemini) — fora da contagem do cost_guard.

Anti-alucinação: `response_format` JSON Schema estrito com enum dos
`criterionId` válidos + validação da evidência literal contra a transcrição
(`core/evidence_validation.py`).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import logging
import os
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

from core import cost_guard
from core.procedimentos_rag import get_procedimento_prompt_block
from core.audit_rules import (
    get_sector_prompt_rules,
    password_rule_applies_to_sector,
)
from schemas import AuditAlert, AuditCriterion
# Normalização/validação/scoring do payload extraída para audit_evaluation_payload;
# reexportada p/ compat (usada por evaluate_*, test_qualification_audit e
# test_audit_evaluator_payloads).
from core.audit_evaluation_payload import (  # noqa: F401
    _normalize_evaluation_payload,
    _is_valid_evaluation_payload,
    _normalize_validate_and_score_evaluation,
    _evidence_coverage_is_acceptable,
)

# Construção do prompt de avaliação (system/user + response_format) e a hint de
# schema: extraídos para audit_evaluation_prompt (v1.3.168); reexportados p/ compat
# (evaluate_*, fachada evaluation/services e testes usam audit_evaluator.<nome>).
from core.audit_evaluation_prompt import (  # noqa: E402,F401
    AUDIT_EVALUATION_SCHEMA_HINT,
    _build_criteria_text,
    _build_audit_evaluation_response_format,
    _build_strict_evidence_retry_prompt,
    _build_default_evaluation_user_prompt,
    _ensure_evidence_contract_in_user_prompt,
    _should_apply_password_rule,
    _build_diarization_prompt_block,
    _get_golden_dataset_prompt_block,
    get_audit_system_prompt,
)


# ── Knobs de ambiente (timeout, qualidade de evidência, custo) ──────────────

def _get_azure_openai_timeout_seconds() -> float:
    """Timeout (s) das chamadas Azure OpenAI — `AZURE_OPENAI_AUDIT_TIMEOUT_SECONDS`, clamp 30–600 (default 180)."""
    raw = os.getenv("AZURE_OPENAI_AUDIT_TIMEOUT_SECONDS", "180")
    try:
        parsed = float(str(raw).strip().replace(",", "."))
    except (TypeError, ValueError):
        parsed = 180.0
    return max(30.0, min(parsed, 600.0))


def _weak_evidence_retry_enabled() -> bool:
    """Retry da avaliacao quando a evidencia ficou fraca (< ratio acima).

    Default ON (1 retry, comportamento historico). `AUDIT_WEAK_EVIDENCE_RETRY=0`
    desliga: a avaliacao VALIDA porem com evidencia fraca e aceita com warning,
    cortando a segunda chamada GPT-4o (alavanca de custo). Payload INVALIDO
    continua tendo retry independente desta flag — sem ele nao ha resultado.
    """
    raw = os.getenv("AUDIT_WEAK_EVIDENCE_RETRY")
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


# ── Injeção de dependências (montada pela fachada core/evaluation.py) ───────

@dataclass(frozen=True)
class AuditEvaluationDependencies:
    """Dependências injetadas na avaliação (evita import circular com a fachada).

    A fachada `core/evaluation.py` monta esta struct com os singletons reais
    do serviço; os testes injetam dublês. Imutável (frozen).
    """

    prompts_config: dict  # Conteúdo de backend/config/prompts.json (audit_system, evaluation_user_prompt...).
    get_config_value: Callable[[str, str], str]  # Lê chave da tabela `configuracoes` no banco (com default).
    get_colaboradores_para_prompt: Callable[..., list[str]]  # Nomes oficiais do setor (ajuda a IA a identificar o operador).
    parse_json_with_repair: Callable[[str, str], Any]  # Parser tolerante: repara JSON malformado guiado pelo schema_hint.
    ai_client: Any  # Cliente do provedor ALTERNATIVO (Gemini) — usado só no fallback.
    ai_audit_model: Optional[str]  # Modelo do provedor alternativo.
    generation_config: Any  # Config de geração do provedor alternativo.
    azure_openai_key: Optional[str]  # Credenciais do caminho PRINCIPAL (GPT-4o); ausentes => cai no fallback.
    azure_openai_endpoint: str
    azure_openai_deployment: str
    ai_priority: str  # "azure" = tentar GPT-4o primeiro; outro valor pula direto para o fallback.
    ai_enabled: bool  # Habilita o fallback Gemini quando o Azure falha ou não está configurado.



def build_audit_evaluation_dependencies(
    *,
    prompts_config: dict,
    get_config_value: Callable[[str, str], str],
    get_colaboradores_para_prompt: Callable[..., list[str]],
    parse_json_with_repair: Callable[[str, str], Any],
    ai_client: Any = None,
    ai_audit_model: Optional[str] = None,
    generation_config: Any = None,
    azure_openai_key: Optional[str] = None,
    azure_openai_endpoint: str = "",
    azure_openai_deployment: str = "",
    ai_priority: str = "azure",
    ai_enabled: bool = False,
) -> AuditEvaluationDependencies:
    """Fábrica de `AuditEvaluationDependencies` com defaults seguros (IA desligada).

    Sem efeitos colaterais: apenas empacota as referências para injeção.
    """
    return AuditEvaluationDependencies(
        prompts_config=prompts_config,
        get_config_value=get_config_value,
        get_colaboradores_para_prompt=get_colaboradores_para_prompt,
        parse_json_with_repair=parse_json_with_repair,
        ai_client=ai_client,
        ai_audit_model=ai_audit_model,
        generation_config=generation_config,
        azure_openai_key=azure_openai_key,
        azure_openai_endpoint=azure_openai_endpoint,
        azure_openai_deployment=azure_openai_deployment,
        ai_priority=ai_priority,
        ai_enabled=ai_enabled,
    )


# ── Avaliação: chamadas aos provedores de IA ────────────────────────────────

async def _build_feedback_query_embedding(transcription: list[dict]) -> Optional[list[float]]:
    """Embedding da transcrição para ranquear o feedback da auditora no prompt.

    CUSTO: 1 chamada paga de embedding ao Azure OpenAI
    (`rag_triagem.gerar_embedding`, categoria `embedding` no cost_guard).
    Fail-open: transcrição vazia ou erro retorna None e o feedback usa o
    fallback cronológico. Texto truncado em 32k chars antes do embedding.
    """
    transcription_text = " ".join(
        str(segment.get("text") or "").strip()
        for segment in transcription
        if isinstance(segment, dict) and str(segment.get("text") or "").strip()
    )
    if not transcription_text:
        return None
    try:
        from core.rag_triagem import gerar_embedding

        return await asyncio.to_thread(gerar_embedding, transcription_text[:32000])
    except Exception as exc:
        logger.warning("Evaluation RAG embedding unavailable; using chronological feedback fallback: %s", exc)
        return None


async def evaluate_transcription(
    transcription: list[dict],
    alert: AuditAlert,
    criteria_list: list[AuditCriterion],
    operator_name: Optional[str],
    driver_name: Optional[str],
    audio_quality: Optional[dict] = None,
    sector_id: Optional[str] = None,
    *,
    dependencies: AuditEvaluationDependencies,
) -> dict:
    """Avalia a transcrição no provedor ALTERNATIVO (`ai_client`, ex.: Gemini).

    Caminho de fallback — o principal é `evaluate_with_azure`. Monta os
    mesmos system/user prompts do caminho Azure, faz 1 chamada ao modelo,
    parseia com reparo e normaliza. Diferenças: sem retry de evidência fraca
    e sem registro no cost_guard (o teto cobre só o consumo Azure).

    `driver_name` é ignorado (mantido por compatibilidade de assinatura).

    Retorna o payload normalizado; levanta RuntimeError quando o resultado
    não cumpre o contrato mínimo de `_is_valid_evaluation_payload`.

    CUSTO: 1 chamada ao provedor alternativo + 1 embedding Azure (feedback RAG).
    """
    _ = driver_name
    criteria_text = _build_criteria_text(criteria_list)
    transcription_json = json.dumps(transcription, ensure_ascii=True, separators=(",", ":"))
    feedback_query_embedding = await _build_feedback_query_embedding(transcription)
    system_prompt = get_audit_system_prompt(
        alert.context,
        criteria_text,
        audio_quality,
        sector_id,
        alert_id=alert.id,
        alert_label=alert.label,
        dependencies=dependencies,
        operator_name=operator_name,
        feedback_query_embedding=feedback_query_embedding,
    )

    schema_hint = AUDIT_EVALUATION_SCHEMA_HINT
    user_prompt = dependencies.prompts_config.get("evaluation_user_prompt", "")
    if user_prompt:
        user_prompt = user_prompt.replace("{transcription_json}", transcription_json)
    else:
        user_prompt = ""
    if not user_prompt:
        user_prompt = _build_default_evaluation_user_prompt(transcription_json, schema_hint)
    user_prompt = _ensure_evidence_contract_in_user_prompt(user_prompt)
    response = await asyncio.to_thread(
        dependencies.ai_client.models.generate_content,
        model=dependencies.ai_audit_model,
        contents=[system_prompt, user_prompt],
        config=dependencies.generation_config,
    )
    logger.debug("AI audit raw response: %s", response.text)
    parsed = await asyncio.to_thread(dependencies.parse_json_with_repair, response.text, schema_hint)
    normalized_payload = _normalize_validate_and_score_evaluation(
        parsed,
        criteria_list,
        transcription,
        alert=alert,
        audio_quality=audio_quality,
        sector_id=sector_id,
    )
    if not _is_valid_evaluation_payload(normalized_payload, criteria_list):
        raise RuntimeError("AI audit evaluation returned invalid payload.")
    return normalized_payload


async def evaluate_with_azure(
    transcription: list[dict],
    alert: AuditAlert,
    criteria_list: list[AuditCriterion],
    operator_name: Optional[str],
    audio_quality: Optional[dict] = None,
    sector_id: Optional[str] = None,
    *,
    dependencies: AuditEvaluationDependencies,
) -> dict:
    """Caminho principal: avaliação GPT-4o no Azure OpenAI, com retry de evidência.

    Sem credenciais Azure, delega direto para `evaluate_transcription`.

    Fluxo: monta prompts → 1ª chamada GPT-4o (temperature=0 e seed=42 para
    reprodutibilidade; JSON Schema estrito com enum de criterionId) →
    normaliza/valida. Aceita de imediato se válido E com evidência aceitável.
    Se válido porém com evidência fraca e `AUDIT_WEAK_EVIDENCE_RETRY=0`,
    aceita com warning (alavanca de custo). Caso contrário, 2ª chamada com
    instruções estritas de evidência; payload ainda inválido → RuntimeError
    (evidência ainda fraca após retry é aceita com warning).

    CUSTO: 1–2 chamadas GPT-4o (cost_guard `avaliacao`/`avaliacao_retry`)
    + 1 embedding por avaliação. Qualquer exceção é re-embrulhada em
    RuntimeError("Azure OpenAI evaluation failed: ...").
    """
    if not dependencies.azure_openai_key or not dependencies.azure_openai_endpoint:
        return await evaluate_transcription(
            transcription,
            alert,
            criteria_list,
            operator_name,
            None,
            audio_quality,
            sector_id,
            dependencies=dependencies,
        )

    from openai import AzureOpenAI

    client = AzureOpenAI(
        azure_endpoint=dependencies.azure_openai_endpoint,
        api_key=dependencies.azure_openai_key,
        api_version="2025-01-01-preview",
        timeout=_get_azure_openai_timeout_seconds(),
    )
    criteria_text = _build_criteria_text(criteria_list)
    transcription_json = json.dumps(transcription, ensure_ascii=True, separators=(",", ":"))
    feedback_query_embedding = await _build_feedback_query_embedding(transcription)
    system_prompt = get_audit_system_prompt(
        alert.context,
        criteria_text,
        audio_quality,
        sector_id,
        alert_id=alert.id,
        alert_label=alert.label,
        dependencies=dependencies,
        operator_name=operator_name,
        feedback_query_embedding=feedback_query_embedding,
    )
    user_prompt = dependencies.prompts_config.get("evaluation_user_prompt", "")
    if user_prompt:
        user_prompt = user_prompt.replace("{transcription_json}", transcription_json)
    else:
        user_prompt = ""
    if not user_prompt:
        user_prompt = _build_default_evaluation_user_prompt(transcription_json, schema_hint=AUDIT_EVALUATION_SCHEMA_HINT)
    user_prompt = _ensure_evidence_contract_in_user_prompt(user_prompt)
    try:
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "avaliacao")
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model=dependencies.azure_openai_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0,
            seed=42,
            response_format=_build_audit_evaluation_response_format(criteria_list),
        )
        schema_hint = AUDIT_EVALUATION_SCHEMA_HINT
        parsed = await asyncio.to_thread(dependencies.parse_json_with_repair, completion.choices[0].message.content, schema_hint)
        normalized_payload = _normalize_validate_and_score_evaluation(
            parsed,
            criteria_list,
            transcription,
            alert=alert,
            audio_quality=audio_quality,
            sector_id=sector_id,
        )
        if _is_valid_evaluation_payload(normalized_payload, criteria_list) and _evidence_coverage_is_acceptable(normalized_payload):
            return normalized_payload

        # Alavanca de custo: payload VALIDO com evidencia fraca pode ser aceito
        # sem a segunda chamada GPT-4o quando AUDIT_WEAK_EVIDENCE_RETRY=0.
        if (
            _is_valid_evaluation_payload(normalized_payload, criteria_list)
            and not _weak_evidence_retry_enabled()
        ):
            logger.warning(
                "Azure audit evaluation com evidencia fraca aceita sem retry "
                "(AUDIT_WEAK_EVIDENCE_RETRY=0). evidence=%s",
                normalized_payload.get("evidence_quality"),
            )
            return normalized_payload

        logger.warning(
            "Azure audit evaluation returned invalid or weak-evidence payload. Retrying with stricter schema instructions. evidence=%s",
            normalized_payload.get("evidence_quality"),
        )
        retry_user_prompt = _build_strict_evidence_retry_prompt(user_prompt, criteria_list)
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "avaliacao_retry")
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model=dependencies.azure_openai_deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": retry_user_prompt},
            ],
            temperature=0,
            seed=42,
            response_format=_build_audit_evaluation_response_format(criteria_list),
        )
        parsed = await asyncio.to_thread(dependencies.parse_json_with_repair, completion.choices[0].message.content, schema_hint)
        normalized_payload = _normalize_validate_and_score_evaluation(
            parsed,
            criteria_list,
            transcription,
            alert=alert,
            audio_quality=audio_quality,
            sector_id=sector_id,
        )
        if not _is_valid_evaluation_payload(normalized_payload, criteria_list):
            raise RuntimeError("Azure OpenAI returned invalid audit evaluation payload.")
        if not _evidence_coverage_is_acceptable(normalized_payload):
            logger.warning(
                "Azure audit evaluation completed with weak evidence coverage after retry: %s",
                normalized_payload.get("evidence_quality"),
            )
        return normalized_payload
    except Exception as exc:
        logger.error("Azure OpenAI Error: %s", exc)
        raise RuntimeError(f"Azure OpenAI evaluation failed: {exc}")


async def evaluate_with_ai_priority(
    transcription: list[dict],
    alert: AuditAlert,
    criteria_list: list[AuditCriterion],
    operator_name: Optional[str],
    audio_quality: Optional[dict] = None,
    sector_id: Optional[str] = None,
    *,
    dependencies: AuditEvaluationDependencies,
) -> dict:
    """Orquestrador de provedores: Azure primeiro (se prioritário), Gemini de fallback.

    Regras: `ai_priority == "azure"` + key presente → tenta
    `evaluate_with_azure`; em falha, propaga RuntimeError se não houver
    fallback (`ai_enabled=False`) ou cai para `evaluate_transcription`.
    Nenhum provedor configurado → RuntimeError.

    É o ponto de entrada usado por `core/audit.py` (via fachada
    `core/evaluation.py`) tanto no fluxo manual quanto na automação.
    """
    if dependencies.ai_priority == "azure" and dependencies.azure_openai_key:
        try:
            return await evaluate_with_azure(
                transcription,
                alert,
                criteria_list,
                operator_name,
                audio_quality,
                sector_id,
                dependencies=dependencies,
            )
        except Exception as exc:
            logger.error("Falha na Azure OpenAI: %s.", exc)
            if not dependencies.ai_enabled:
                raise RuntimeError("Falha no serviço Azure.")
            # Como falhou, o fluxo continuará para baixo batendo na condição do ai_enabled (Gemini)
    if dependencies.ai_enabled:
        return await evaluate_transcription(
            transcription,
            alert,
            criteria_list,
            operator_name,
            None,
            audio_quality,
            sector_id,
            dependencies=dependencies,
        )
    raise RuntimeError("Nenhum provedor de IA configurado. Forneca AZURE_OPENAI_KEY ou AI_API_KEY.")
