import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

from schemas import AuditAlert, AuditCriterion, AuditResult, AuditResultDetail
import db.database as database
from repositories import operators
from utils.text_processing import (
    deduplicate_transcription_segments,
    remove_emojis,
)
from core.audit_evaluator import (
    AuditEvaluationDependencies,
    build_audit_evaluation_dependencies,
    evaluate_transcription as run_ai_audit_evaluation,
    evaluate_with_ai_priority as run_prioritized_audit_evaluation,
    evaluate_with_azure as run_azure_audit_evaluation,
    get_audit_system_prompt as build_audit_system_prompt,
)
from repositories.common import derive_audit_scope
from core.audit_rules import (
    get_fatal_flag_reason_text,
    get_fatal_flag_sectors,
    get_fatal_keywords_for_sector,
    get_password_criterion_keys,
    get_rastreamento_sectors,
)

from core.config import (
    AI_AUDIT_MODEL,
    AI_ENABLED,
    AI_MODEL,
    AI_PROVIDER_PRIORITY,
    AUDIT_DETAIL_SEVERITY,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    PROMPTS_CONFIG,
    ai_client,
)

__all__ = [
    # Funções públicas de avaliação
    "evaluate_transcription", "evaluate_with_azure", "evaluate_with_ai_priority",
    "result_from_raw",
    "validate_evaluation", "get_audit_system_prompt",
    "parse_json_with_repair",
    # Funções internas (usadas por testes)
    "_normalize_audit_detail_status", "_resolve_audit_detail_scores",
    "_pick_stricter_audit_detail", "_get_audit_evaluation_dependencies",
]


def _get_default_generation_config():
    """Lazy fetch do GENERATION_CONFIG para evitar google.genai no boot."""
    from core.config import GENERATION_CONFIG
    return GENERATION_CONFIG


def _normalize_audit_detail_status(raw_status: Any) -> str:
    status = str(raw_status or "").strip().lower()
    if status in {"na", "pending_manual"}:
        return "pass"
    if status == "partial":
        return "fail"
    return status if status in {"pass", "fail"} else "fail"

def _resolve_audit_detail_scores(weight: float, status: str, deflator: Optional[float] = None) -> tuple[float, float]:
    """Calcula (score_obtido, score_maximo) para um critério seguindo a lógica da planilha BD.
    
    A nota final é: 10.0 - sum(Peso + abs(Deflator) para cada falha).
    Isso significa que para cada critério, o score_obtido é:
    - PASS: Peso
    - FAIL: Peso - (Peso + abs(Deflator)) = -abs(Deflator)
    - Status legados PARTIAL/NA/PENDING_MANUAL sao normalizados antes desta funcao.
    """
    # Se não houver deflator, assume 0.0 (perde apenas o peso)
    d = abs(deflator) if deflator is not None else 0.0
    
    if status == "pass":
        return weight, weight
    if status == "fail":
        # Perde o peso inteiro MAIS o valor do deflator
        return -d, weight
        
    return -d, weight # Default fail fallback


_CPF_FALLBACK_COMPATIBLE_FATAL_FLAGS = {
    "senha_nao_solicitada",
    "solicitar_senha_ou_cpf",
    "senha_incorreta_aceita",
}


def _normalize_password_flow_text(value: Any) -> str:
    text = remove_emojis(str(value or "")).lower()
    replacements = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return re.sub(r"\s+", " ", text).strip()


def _segment_password_flow_text(segment: Any) -> str:
    if isinstance(segment, dict):
        return _normalize_password_flow_text(segment.get("text") or segment.get("content") or "")
    return _normalize_password_flow_text(getattr(segment, "text", segment))


def _is_password_request_text(text: str) -> bool:
    return "senha" in text and any(
        cue in text
        for cue in (
            "confirma",
            "confirmar",
            "informa",
            "informar",
            "me passa",
            "pode passar",
            "qual",
            "solicito",
            "senha de seguranca",
        )
    )


def _is_password_unavailable_text(text: str, password_was_requested: bool) -> bool:
    explicit_password_denial = "senha" in text and any(
        cue in text
        for cue in (
            "nao tenho",
            "nao tem",
            "nao recebi",
            "nao chegou",
            "sem senha",
            "nao sei",
            "nao lembro",
            "esqueci",
            "nao consigo",
            "nao estou com",
            "nao to com",
            "nao tenho acesso",
        )
    )
    if explicit_password_denial:
        return True

    # Depois que a senha foi solicitada, a negativa pode vir curta ("nao tenho",
    # "estou dirigindo") sem repetir a palavra senha na transcricao.
    return password_was_requested and any(
        cue in text
        for cue in (
            "nao tenho",
            "nao recebi",
            "nao sei",
            "nao lembro",
            "esqueci",
            "estou dirigindo",
            "to dirigindo",
            "estou em movimento",
            "to em movimento",
            "nao consigo ver",
            "nao consigo pegar",
            "sem acesso",
        )
    )


def _has_cpf_signal(text: str) -> bool:
    digits = re.sub(r"\D+", "", text)
    return "cpf" in text or len(digits) >= 11


def _has_legitimate_cpf_password_fallback(transcription_data: Any) -> bool:
    """True quando a conversa mostra senha solicitada/negada antes do CPF.

    Essa guarda corrige falso positivo de zeragem: motorista diz que nao tem
    ou nao recebeu a senha, entao o operador pode validar por CPF. Sem uma
    negativa antes do CPF, a regra segue zerando por senha/CPF direto.
    """
    if not isinstance(transcription_data, list):
        return False

    password_requested = False
    password_unavailable = False

    for segment in transcription_data:
        text = _segment_password_flow_text(segment)
        if not text:
            continue
        if _is_password_request_text(text):
            password_requested = True
        if _is_password_unavailable_text(text, password_requested):
            password_unavailable = True
        if password_unavailable and _has_cpf_signal(text):
            return True

    return False


def _pick_stricter_audit_detail(existing: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    existing_rank = AUDIT_DETAIL_SEVERITY[existing["status"]]
    candidate_rank = AUDIT_DETAIL_SEVERITY[candidate["status"]]
    if candidate_rank < existing_rank:
        return candidate
    if candidate_rank > existing_rank:
        return existing

    existing_comment = str(existing.get("comment", "")).strip()
    candidate_comment = str(candidate.get("comment", "")).strip()
    return candidate if len(candidate_comment) > len(existing_comment) else existing


def _log_json_repair_event(
    *,
    event: str,
    attempt: int,
    provider: str,
    schema_hint: str,
    text,
    error=None,
) -> None:
    payload = {
        "event": event,
        "attempt": attempt,
        "provider": provider,
        "schema_hint": str(schema_hint or "")[:160],
        "text_length": len(text or ""),
    }
    if error is not None:
        payload["error_type"] = error.__class__.__name__
        payload["error_message"] = str(error)[:240]
    logger.info(
        "[evaluation-json-repair] %s",
        json.dumps(payload, ensure_ascii=False, sort_keys=True),
    )


def _iter_local_json_candidates(raw_text: str):
    text = str(raw_text or "").strip()
    if not text:
        return

    seen: set[str] = set()

    def emit(candidate: str):
        candidate = str(candidate or "").strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            yield candidate

    yield from emit(text)

    if text.startswith("```"):
        stripped = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```\s*$", "", stripped)
        yield from emit(stripped)

    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            _, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        yield from emit(text[index : index + end])
        break


def _try_parse_json_locally(raw_text: str) -> tuple[bool, Any]:
    last_error: Optional[Exception] = None
    for candidate in _iter_local_json_candidates(raw_text):
        try:
            return True, json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
    if last_error is not None:
        _log_json_repair_event(
            event="local_repair_failed",
            attempt=0,
            provider="local",
            schema_hint="",
            text=raw_text,
            error=last_error,
        )
    return False, None


def _build_azure_json_repair_client(endpoint: str, api_key: str) -> Any:
    from openai import AzureOpenAI

    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2025-01-01-preview",
        timeout=180.0,
    )


def parse_json_with_repair(
    raw_text: str,
    schema_hint: str,
    max_attempts: int = 2,
    *,
    azure_client: Any = None,
    primary_ai_client: Any = None,
    ai_provider_priority: Optional[str] = None,
    azure_openai_key: Optional[str] = None,
    azure_openai_endpoint: Optional[str] = None,
    azure_openai_deployment: Optional[str] = None,
    ai_model: Optional[str] = None,
    generation_config: Any = None,
) -> Any:
    provider_priority = ai_provider_priority or AI_PROVIDER_PRIORITY
    azure_key = AZURE_OPENAI_KEY if azure_openai_key is None else azure_openai_key
    azure_endpoint = AZURE_OPENAI_ENDPOINT if azure_openai_endpoint is None else azure_openai_endpoint
    azure_deployment = azure_openai_deployment or AZURE_OPENAI_DEPLOYMENT
    model_name = ai_model or AI_MODEL
    model_client = primary_ai_client or ai_client
    if generation_config is None:
        from core.config import GENERATION_CONFIG  # lazy: evita google.genai no boot
        effective_generation_config = GENERATION_CONFIG
    else:
        effective_generation_config = generation_config

    attempt = 0
    text = raw_text
    while True:
        try:
            if not text:
                raise ValueError("JSON input is empty or None")
            return json.loads(text)
        except Exception as exc:
            local_ok, parsed = _try_parse_json_locally(text)
            if local_ok:
                _log_json_repair_event(
                    event="local_repair_applied",
                    attempt=attempt,
                    provider="local",
                    schema_hint=schema_hint,
                    text=text,
                    error=exc,
                )
                return parsed

            if attempt >= max_attempts:
                _log_json_repair_event(
                    event="exhausted",
                    attempt=attempt,
                    provider="none",
                    schema_hint=schema_hint,
                    text=text,
                    error=exc,
                )
                raise
            attempt += 1
            use_azure_repair = bool(provider_priority == "azure" and azure_key and azure_endpoint)
            repair_provider = (
                "azure_openai"
                if use_azure_repair
                else "primary_ai"
            )
            _log_json_repair_event(
                event="invalid_json_detected",
                attempt=attempt,
                provider=repair_provider,
                schema_hint=schema_hint,
                text=text,
                error=exc,
            )

            fix_prompt = f"""
            Corrija o JSON para ficar valido e obedecer ao esquema abaixo.
            Responda somente com JSON, sem explicacoes.
            ESQUEMA:
            {schema_hint}
            TEXTO:
            {text}
            """
            # Use Azure OpenAI when the Azure route is selected
            if use_azure_repair:
                from core import cost_guard
                cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "json_repair")
                client = azure_client or _build_azure_json_repair_client(azure_endpoint, azure_key)
                completion = client.chat.completions.create(
                    model=azure_deployment,
                    messages=[{"role": "user", "content": fix_prompt}],
                    temperature=0,
                    response_format={"type": "json_object"}
                )
                text = completion.choices[0].message.content
            else:
                if model_client is None:
                    raise RuntimeError("AI client not configured for JSON repair")
                repaired = model_client.models.generate_content(
                    model=model_name,
                    contents=[fix_prompt],
                    config=effective_generation_config
                )
                text = repaired.text

            _log_json_repair_event(
                event="repair_generated",
                attempt=attempt,
                provider=repair_provider,
                schema_hint=schema_hint,
                text=text,
            )
            # Loop volta ao while True -> json.loads(text) para tentar novamente


def validate_evaluation(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if "summary" not in data or "details" not in data:
        return False
    if not isinstance(data["details"], list):
        return False
    allowed = {"pass", "fail"}
    for item in data["details"]:
        if not isinstance(item, dict):
            return False
        if "criterionId" not in item or "status" not in item or "comment" not in item:
            return False
        if item["status"] not in allowed:
            return False
    return True
def _get_audit_evaluation_dependencies() -> AuditEvaluationDependencies:
    return build_audit_evaluation_dependencies(
        prompts_config=PROMPTS_CONFIG,
        get_config_value=database.get_config_value,
        get_colaboradores_para_prompt=lambda sector_id="", supervisor="", escala="": operators.get_colaboradores_para_prompt(database.get_connection, supervisor, escala, sector_id),
        parse_json_with_repair=parse_json_with_repair,
        ai_client=ai_client,
        ai_audit_model=AI_AUDIT_MODEL,
        generation_config=_get_default_generation_config(),
        azure_openai_key=AZURE_OPENAI_KEY,
        azure_openai_endpoint=AZURE_OPENAI_ENDPOINT,
        azure_openai_deployment=AZURE_OPENAI_DEPLOYMENT,
        ai_priority=AI_PROVIDER_PRIORITY,
        ai_enabled=AI_ENABLED,
    )
def get_audit_system_prompt(
    alert_context: str,
    criteria_text: str,
    audio_quality: Optional[dict] = None,
    sector_id: Optional[str] = None,
    operator_name: Optional[str] = None,
    alert_id: Optional[str] = None,
    alert_label: Optional[str] = None,
    feedback_query_embedding: Optional[list[float]] = None,
) -> str:
    return build_audit_system_prompt(
        alert_context,
        criteria_text,
        audio_quality,
        sector_id,
        alert_id=alert_id,
        alert_label=alert_label,
        dependencies=_get_audit_evaluation_dependencies(),
        operator_name=operator_name,
        feedback_query_embedding=feedback_query_embedding,
    )
async def evaluate_transcription(transcription: list[dict], alert: AuditAlert, criteria_list: list[AuditCriterion], operator_name: Optional[str], driver_name: Optional[str], audio_quality: Optional[dict] = None, sector_id: Optional[str] = None) -> dict:
    return await run_ai_audit_evaluation(
        transcription,
        alert,
        criteria_list,
        operator_name,
        driver_name,
        audio_quality,
        sector_id,
        dependencies=_get_audit_evaluation_dependencies(),
    )
async def evaluate_with_azure(transcription: list[dict], alert: AuditAlert, criteria_list: list[AuditCriterion], operator_name: Optional[str], audio_quality: Optional[dict] = None, sector_id: Optional[str] = None) -> dict:
    return await run_azure_audit_evaluation(
        transcription,
        alert,
        criteria_list,
        operator_name,
        audio_quality,
        sector_id,
        dependencies=_get_audit_evaluation_dependencies(),
    )
async def evaluate_with_ai_priority(transcription: list[dict], alert: AuditAlert, criteria_list: list[AuditCriterion], operator_name: Optional[str], audio_quality: Optional[dict] = None, sector_id: Optional[str] = None) -> dict:
    return await run_prioritized_audit_evaluation(
        transcription,
        alert,
        criteria_list,
        operator_name,
        audio_quality,
        sector_id,
        dependencies=_get_audit_evaluation_dependencies(),
    )
def result_from_raw(raw: dict, criteria_list: list[AuditCriterion], transcription_data: Optional[list[dict]] = None, operator_name: Optional[str] = None, operator_id: Optional[str] = None, source_type: str = "audio", audio_quality: Optional[dict] = None, sector_id: Optional[str] = None) -> AuditResult:
    from schemas import TranscriptionSegment
    total_score, max_score, details, transcription = 0.0, 0.0, [], []
    
    audit_scope = derive_audit_scope(source_type, audio_quality)
    
    # Transcription source handling
    t_source = transcription_data if transcription_data is not None else []
    if not t_source and isinstance(raw, dict):
        t_source = raw.get("transcription", [])
    
    if isinstance(t_source, list):
        t_source = deduplicate_transcription_segments(t_source)
        for t in t_source:
            if isinstance(t, dict):
                text = remove_emojis(str(t.get("text", ""))).strip()
                transcription.append(TranscriptionSegment(
                    start=str(t.get("start", "00:00")),
                    end=str(t.get("end", "00:00")),
                    text=text
                ))
    
    # Details handling
    details_source = raw.get("details", []) if isinstance(raw, dict) else []
    criteria_by_id = {criterion.id: criterion for criterion in criteria_list}
    normalized_details_by_id: dict[str, dict[str, Any]] = {}
    if isinstance(details_source, list):
        for item in details_source:
            if not isinstance(item, dict):
                continue
            crit_id = str(item.get("criterionId", "")).strip()
            if not criteria_by_id.get(crit_id):
                continue

            normalized_item = {
                "status": _normalize_audit_detail_status(item.get("status")),
                "comment": remove_emojis(str(item.get("comment", ""))),
            }
            timestamp_ref = str(item.get("timestamp") or "").strip()
            evidence_text = str(item.get("evidence_text") or "").strip()
            evidence_validation = item.get("evidence_validation")
            if timestamp_ref:
                normalized_item["timestamp"] = timestamp_ref
            if evidence_text:
                normalized_item["evidence_text"] = evidence_text
            if isinstance(evidence_validation, dict):
                normalized_item["evidence_validation"] = evidence_validation
            existing = normalized_details_by_id.get(crit_id)
            normalized_details_by_id[crit_id] = (
                _pick_stricter_audit_detail(existing, normalized_item) if existing else normalized_item
            )

    for crit in criteria_list:
        normalized_item = normalized_details_by_id.get(crit.id)
        if normalized_item is None:
            status = "fail"
            comment = "Critério ausente na resposta da IA. Tratado como fail para manter a auditoria completa."
            timestamp_ref = None
            evidence_text = None
            evidence_validation = None
        else:
            status = normalized_item["status"]
            comment = normalized_item["comment"]
            timestamp_ref = normalized_item.get("timestamp") or None
            evidence_text = normalized_item.get("evidence_text") or None
            evidence_validation = normalized_item.get("evidence_validation")

        obtained, max_increment = _resolve_audit_detail_scores(crit.weight, status, crit.deflator)
        obtained = round(obtained, 2)
        max_increment = round(max_increment, 2)
        max_score += max_increment
        details.append(AuditResultDetail(
            criterionId=crit.id,
            label=crit.label,
            status=status,
            weight=crit.weight,
            deflator=crit.deflator,
            obtainedScore=obtained,
            comment=comment,
            timestamp=timestamp_ref,
            evidence_text=evidence_text,
            evidence_validation=evidence_validation if isinstance(evidence_validation, dict) else None,
        ))
        total_score += obtained

    summary_text = ""
    ai_feedback_text = None
    if isinstance(raw, dict):
        summary_text = remove_emojis(str(raw.get("summary", "")))
        ai_feedback_text = remove_emojis(str(raw.get("ai_feedback", ""))) if raw.get("ai_feedback") else None

    evidence_quality = raw.get("evidence_quality") if isinstance(raw, dict) else None
    if isinstance(evidence_quality, dict):
        if audio_quality is None:
            audio_quality = {}
        else:
            audio_quality = dict(audio_quality)
        audio_quality["evidence_quality"] = evidence_quality
        if evidence_quality.get("review_recommended"):
            reasons = list(audio_quality.get("review_reasons") or [])
            reason = str(evidence_quality.get("reason") or "evidencia_insuficiente").strip()
            evidence_reason = f"evidencia:{reason}"
            if evidence_reason not in reasons:
                reasons.append(evidence_reason)
            audio_quality["review_reasons"] = reasons
            audio_quality["review_recommended"] = True
            priority_rank = {"low": 0, "medium": 1, "high": 2}
            current_priority = str(audio_quality.get("review_priority") or "low").strip().lower()
            audio_quality["review_priority"] = "high" if priority_rank.get(current_priority, 0) < 2 else current_priority

    # SAFETY NETS (Configured in prompts.json)
    # Automatically boost scores for specific sectors when audio quality/transcription fails
    # but the operator maintains a professional flow (no hostile behavior).
    safety_nets = PROMPTS_CONFIG.get("safety_nets", {})
    
    for sector_key, net_config in safety_nets.items():
        trigger = net_config.get("trigger_keyword", "")
        if not trigger:
            continue
            
        is_triggered = any(trigger.lower() in (c.label or "").lower() for c in criteria_list)
        if is_triggered:
            hostile_words = net_config.get("hostile_keywords", ["grosseiro", "hostil", "desligou", "abandonou"])
            is_hostile = any(word in summary_text.lower() for word in hostile_words)
            
            if not is_hostile and max_score > 0:
                current_ratio = total_score / max_score
                threshold = net_config.get("threshold_ratio", 0.70)
                boost = net_config.get("boost_ratio", 0.82)
                
                if current_ratio < threshold:
                    total_score = max_score * boost
            
            # Aplica apenas o primeiro safety net que der match
            break

    # FATAL CRITERIA (CRITERIOS QUE ZERAM A NOTA - NAO NEGOCIAVEIS) POR SETOR
    sec = (sector_id or "").lower().strip()
    zeroed = False
    zero_reason = ""
    has_legitimate_cpf_fallback = _has_legitimate_cpf_password_fallback(transcription_data)

    # === CAMADA 1: Deteccao deterministica por criterionId ===
    RASTREAMENTO_SECTORS = get_rastreamento_sectors()
    PASSWORD_CRITERION_KEYS = get_password_criterion_keys()

    if sec in RASTREAMENTO_SECTORS:
        # Criterio de "senha" com fail -> zera (cobre todas as violacoes de senha)
        for item in details:
            criterion = criteria_by_id.get(item.criterionId)
            criterion_key = str(
                getattr(criterion, "chave", None)
                or getattr(criterion, "id", None)
                or item.criterionId
                or ""
            ).strip().lower()
            label = str(item.label or "").lower()
            is_password_criterion = (
                criterion_key in PASSWORD_CRITERION_KEYS
                or "senha" in criterion_key
                or "senha" in label
            )
            if is_password_criterion and item.status == "fail" and not has_legitimate_cpf_fallback:
                zeroed = True
                zero_reason = f"falha no critério de senha ('{item.label}')"
                break

    # === CAMADA 2: Deteccao por fatal_flags da IA ===
    if not zeroed:
        fatal_flags = raw.get("fatal_flags", []) if isinstance(raw, dict) else []

        for flag in fatal_flags:
            normalized_flag = str(flag or "").strip()
            if (
                has_legitimate_cpf_fallback
                and normalized_flag in _CPF_FALLBACK_COMPATIBLE_FATAL_FLAGS
            ):
                continue
            if isinstance(flag, str) and sec in get_fatal_flag_sectors(flag):
                zeroed = True
                zero_reason = f"flag não-negociável '{flag}'"
                break

    # === CAMADA 3: Fallback por substring (rede de seguranca) ===
    if not zeroed:
        fatal_keywords = get_fatal_keywords_for_sector(sec)

        if fatal_keywords:
            for item in details:
                if item.status == "fail":
                    item_text = f"{item.label} {item.comment}".lower()
                    if has_legitimate_cpf_fallback and (
                        "senha" in item_text or "cpf" in item_text
                    ):
                        continue
                    if any(fk in item_text for fk in fatal_keywords):
                        zeroed = True
                        zero_reason = f"criterio '{item.label}'"
                        break

    if zeroed:
        total_score = 0.0
        summary_text += f"\n\n[ATENÇÃO: A nota foi zerada (0) devido à violação não-negociável no setor '{sec.upper() or 'N/A'}': {zero_reason}.]"
        zero_reason_lower = zero_reason.lower()
        if "flag" in zero_reason_lower:
            fatal_flags = raw.get("fatal_flags", []) if isinstance(raw, dict) else []
            for flag in fatal_flags:
                if isinstance(flag, str) and flag in zero_reason:
                    reason_text = get_fatal_flag_reason_text(flag)
                    if reason_text:
                        zero_reason = reason_text
                    break
        elif "senha" in zero_reason_lower and "falha" in zero_reason_lower:
            zero_reason = "o critério de senha foi reprovado"
        elif "crit" in zero_reason_lower and "motivo grave" not in zero_reason_lower:
            zero_reason = zero_reason.replace("criterio", "o critério")

        if zero_reason.lower().startswith("o critério") and "reprovado" not in zero_reason.lower():
            zero_reason += " foi reprovado por motivo grave"

        zero_message = f"Nota zerada porque {zero_reason}."
        if sec:
            zero_message += f" Setor: {sec.upper()}."
        summary_core = summary_text.rsplit("\n\n[", 1)[0].strip() if "\n\n[" in summary_text else summary_text.strip()
        summary_text = f"{summary_core}\n\n[{zero_message}]".strip() if summary_core else zero_message



    result_fatal_flags = [
        str(flag).strip()
        for flag in (raw.get("fatal_flags", []) if isinstance(raw, dict) else [])
        if str(flag).strip()
    ]
    if has_legitimate_cpf_fallback:
        result_fatal_flags = [
            flag
            for flag in result_fatal_flags
            if flag not in _CPF_FALLBACK_COMPATIBLE_FATAL_FLAGS
        ]

    return AuditResult(
        score=round(total_score, 2),
        maxPossibleScore=round(max_score, 2),
        summary=summary_text,
        ai_feedback=ai_feedback_text,
        details=details,
        transcription=transcription,
        operatorName=remove_emojis(operator_name or "Não identificado"),
        operatorId=operator_id or "",
        timestamp=datetime.now().isoformat(),
        source_type=source_type,
        audit_scope=audit_scope,
        audio_quality=audio_quality,
        fatal_flags=result_fatal_flags,
    )
