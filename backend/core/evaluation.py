"""Avaliação de auditoria: ponte para a IA e montagem do resultado final.

Este módulo é a fachada de avaliação consumida pelo restante do backend. Ele tem
dois papéis:

1. **Repassar** as chamadas de avaliação por IA para o cluster
   ``core.audit_evaluator`` (que foi extraído daqui), injetando as dependências
   resolvidas de configuração/banco via ``_get_audit_evaluation_dependencies``. As
   funções ``evaluate_transcription`` / ``evaluate_with_azure`` /
   ``evaluate_with_ai_priority`` e ``get_audit_system_prompt`` são wrappers finos
   sobre esse cluster.
2. **Transformar** o JSON cru devolvido pela IA em um ``AuditResult`` tipado
   (``result_from_raw``): normaliza status por critério, calcula a nota ponderada
   pela lógica da planilha BD (peso/deflator), aplica as redes de segurança
   (``safety_nets`` de ``prompts.json``) e a zeragem por critério fatal em 3 camadas
   (criterionId determinístico → ``fatal_flags`` da IA → fallback por substring),
   respeitando o fallback legítimo de CPF quando o motorista confirma não ter senha.

CUSTO DE API: as funções ``evaluate_*`` e ``get_audit_system_prompt`` disparam, por
baixo, chamadas pagas ao Azure OpenAI / provedor de IA (via ``core.audit_evaluator``).
Já ``result_from_raw``, ``validate_evaluation`` e os helpers de scoring são puros
(CPU/memória) — não fazem rede nem chamam IA; o reparo de JSON foi extraído para
``core.json_repair`` e é só reexportado aqui por compatibilidade de import.
"""
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
    AI_PROVIDER_PRIORITY,
    AUDIT_DETAIL_SEVERITY,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    PROMPTS_CONFIG,
    ai_client,
)

# Reexport de compat: o cluster de reparo de JSON foi extraído para core.json_repair.
# Importadores antigos (`from core.evaluation import parse_json_with_repair`) seguem OK.
from core.json_repair import parse_json_with_repair  # noqa: F401

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
    """Reduz o status de um critério ao binário ``pass``/``fail`` do sistema.

    Mapeia status legados/ambíguos da IA: ``na``/``pending_manual`` viram ``pass``
    (não penaliza), ``partial`` vira ``fail``, qualquer valor fora de
    ``{pass, fail}`` cai em ``fail`` por segurança (default conservador).
    """
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


def _segment_is_operator(normalized_text: str) -> bool:
    """True se o trecho (ja normalizado) e fala do OPERADOR.

    A transcricao vem diarizada com prefixo de locutor no proprio texto
    ('Operador:' / 'Operador BAS:' / 'Motorista:' / nome do condutor). O
    operador e sempre rotulado 'Operador...'. Sem prefixo (transcricao nao
    diarizada), assume-se que NAO e o operador — mantem o comportamento
    leniente para audios sem diarizacao.
    """
    if ":" not in normalized_text:
        return False
    speaker = normalized_text.split(":", 1)[0].strip()
    return speaker.startswith("operador")


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
    """True quando o MOTORISTA confirma que nao tem senha antes do CPF.

    Regra de auditoria (Fatima, 2026-06-12): se o motorista confirma que nao
    tem/nao recebeu/nao lembra/nao consegue acessar a senha, ele pode validar
    por CPF — fallback legitimo, nao zera. O que NAO pode acontecer e o
    operador pedir ou aceitar o CPF SEM essa confirmacao do motorista.

    Por isso a negativa so conta quando vem do MOTORISTA: o operador nao pode
    presumir ('o senhor nao tem a senha, ne? entao passa o CPF') nem colocar a
    negativa na boca do condutor. O pedido de CPF em si pode ser do operador,
    desde que ja exista a confirmacao previa do motorista.
    """
    if not isinstance(transcription_data, list):
        return False

    password_requested = False
    password_unavailable = False

    for segment in transcription_data:
        text = _segment_password_flow_text(segment)
        if not text:
            continue
        is_operator = _segment_is_operator(text)
        if _is_password_request_text(text):
            password_requested = True
        # A confirmacao de "nao tem senha" PRECISA ser do motorista.
        if not is_operator and _is_password_unavailable_text(text, password_requested):
            password_unavailable = True
        # O CPF pode aparecer na fala do motorista (ele dita) ou no pedido do
        # operador — mas so vale apos a confirmacao do motorista acima.
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


def validate_evaluation(data: Any) -> bool:
    """Valida o shape mínimo do JSON de avaliação devolvido pela IA.

    Exige um dict com ``summary`` e ``details`` (lista), e que cada item de
    ``details`` seja um dict com ``criterionId``, ``status`` e ``comment``, com
    ``status`` em ``{"pass", "fail"}``. Retorna ``True``/``False``; não levanta nem
    altera ``data``. Função pura (sem efeitos colaterais).
    """
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
    """Monta o pacote de dependências injetadas no cluster ``core.audit_evaluator``.

    Resolve, no momento da chamada, os valores de configuração (prompts, modelo,
    chaves/endpoint Azure, prioridade de provedores, flag de IA habilitada) e os
    callables de acesso a banco (``get_config_value``, ``get_colaboradores_para_prompt``)
    e de reparo de JSON. Não dispara IA por si só — apenas empacota o que as funções
    de avaliação vão usar.
    """
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
    """Constrói o system prompt de auditoria para a IA (wrapper de ``core.audit_evaluator``).

    Concatena contexto do alerta, texto dos critérios, qualidade de áudio, setor,
    operador e (quando fornecido) embedding de consulta de feedback para incorporar
    instruções/feedback relevantes ao prompt. Retorna o prompt pronto como string.

    Efeitos colaterais: a montagem do prompt pode consultar banco (config, colaboradores
    do setor) e, dependendo do feedback por embedding, buscar instruções relacionadas;
    a chamada paga à IA ocorre só quando o prompt é efetivamente enviado pelas funções
    ``evaluate_*``.
    """
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
    """Avalia a transcrição contra os critérios usando a IA (wrapper assíncrono).

    Repassa para ``core.audit_evaluator.evaluate_transcription`` com as dependências
    resolvidas. Recebe a transcrição diarizada, o alerta e a lista de critérios, e o
    contexto de operador/motorista/qualidade/setor; devolve o dict de avaliação cru
    (``summary``, ``details``, eventuais ``fatal_flags``) que depois alimenta
    ``result_from_raw``.

    CUSTO DE API: dispara chamada paga ao Azure OpenAI / provedor de IA.
    """
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
    """Avalia a transcrição forçando o provedor Azure OpenAI (wrapper assíncrono).

    Variante de ``evaluate_transcription`` que ignora a prioridade de provedores e
    usa o Azure diretamente. Devolve o mesmo dict de avaliação cru.

    CUSTO DE API: dispara chamada paga ao Azure OpenAI.
    """
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
    """Avalia a transcrição respeitando a ordem de prioridade de provedores de IA.

    Wrapper assíncrono que segue ``AI_PROVIDER_PRIORITY`` (fallback entre provedores)
    via ``core.audit_evaluator``. Devolve o mesmo dict de avaliação cru.

    CUSTO DE API: dispara chamada(s) paga(s) ao provedor de IA selecionado.
    """
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
    """Converte o JSON cru da IA em um ``AuditResult`` tipado, com nota e zeragem.

    É o coração do scoring. Passos principais:

    - Monta a transcrição de saída a partir de ``transcription_data`` (ou de
      ``raw['transcription']`` como fallback), deduplicando segmentos e removendo
      emojis.
    - Para cada critério em ``criteria_list``, casa o detalhe correspondente da IA
      (por ``criterionId``), normaliza o status, escolhe o mais severo em caso de
      duplicata e calcula ``obtainedScore``/``maxPossibleScore`` pela lógica de
      peso/deflator (ver ``_resolve_audit_detail_scores``). Critério ausente na
      resposta vira ``fail`` para manter a auditoria completa.
    - Anota ``evidence_quality`` (se a IA enviou) e pode forçar
      ``review_recommended``/``review_priority`` em ``audio_quality``.
    - Aplica as ``safety_nets`` (de ``prompts.json``): em setores configurados, se não
      houve comportamento hostil e a razão da nota caiu abaixo do limiar, eleva a nota
      para o ``boost_ratio``.
    - Aplica a ZERAGEM por critério fatal em 3 camadas (criterionId de senha em setores
      de rastreamento → ``fatal_flags`` da IA por setor → fallback por substring em
      label/comentário), respeitando o fallback legítimo de CPF
      (``_has_legitimate_cpf_password_fallback``). Quando zera, anexa a explicação ao
      ``summary`` e zera ``score``.

    Parâmetros relevantes: ``raw`` é o dict da IA; ``criteria_list`` define os
    critérios oficiais e seus pesos/deflators; ``source_type`` (``"audio"`` ou doc)
    deriva o ``audit_scope``; ``sector_id`` determina quais regras fatais valem.

    Retorno: ``AuditResult`` com ``score``, ``maxPossibleScore``, ``summary``,
    ``details``, ``transcription``, ``fatal_flags`` e ``audio_quality`` enriquecido.
    Função pura quanto a I/O: não faz rede nem banco (só CPU/memória).
    """
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
