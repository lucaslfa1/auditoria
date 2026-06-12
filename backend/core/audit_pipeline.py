"""Contexto canônico do pipeline de auditoria pós-classificação.

Papel no fluxo: depois que uma ligação/documento é classificado (setor +
alerta + operador), esses dados de identificação precisam viajar intactos
por transcrição → avaliação → persistência do resultado. Este módulo define
o objeto que carrega esse contexto (`AuditPipelineContext`), os construtores
por origem e o reparo determinístico de setor/alerta antes da auditoria.

Origens suportadas (constantes `AUDIT_ORIGIN_*`):
- `manual_upload`    → upload avulso na UI (`routers/audit.py`);
- `telefonia_manual` → auditoria disparada da tela Telefonia
  (`routers/telefonia.py`);
- `automation`       → esteira automática sobre a fila
  `fila_revisao_classificacao` (`core/automation.py`, `core/automation_cache.py`).

Destino do contexto: `attach_pipeline_context_to_audio_quality` embute o
resultado de `to_audit_metadata()` em `audio_quality["audit_pipeline"]`, que
é gravado junto do artefato por `db.database.persist_audit_artifacts` e lido
de volta por `core/qualification_audit.py` (qualificação/observabilidade).
É assim que a classificação fica rastreável no resultado salvo.

CUSTO DE API: zero — módulo puramente de normalização/metadados, sem chamadas
Azure. A única dependência externa é `repair_queue_audit_context`, que
consulta o catálogo de setores/alertas no Postgres via `core.classification`
(cache TTL). Transcrição (Azure Speech) e avaliação (Azure OpenAI GPT-4o),
que são pagas, acontecem nos consumidores deste contexto.
"""
from __future__ import annotations

import logging
import json
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from db.domain_constants import DEFAULT_SOURCE_TYPE, SOURCE_TYPE_AUDIO, SOURCE_TYPE_PDF, SOURCE_TYPES

logger = logging.getLogger(__name__)

# ── Origens do pipeline e constantes de domínio ──────────────────────────────

# Identificadores de origem gravados em `audio_quality["audit_pipeline"]["origin"]`.
# Fazem parte do artefato persistido (relatórios/UI dependem deles) — não
# renomear sem migração dos dados já salvos.
AUDIT_ORIGIN_MANUAL_UPLOAD = "manual_upload"
AUDIT_ORIGIN_TELEFONIA_MANUAL = "telefonia_manual"
AUDIT_ORIGIN_AUTOMATION = "automation"

# Sentinelas que etapas anteriores (classificação GPT, metadata Huawei) usam
# para "valor ausente/não identificado". A comparação é case-insensitive e
# pós-trim — sempre testar via `is_unknown_value`, nunca por igualdade direta.
UNKNOWN_VALUES = {
    "",
    "desconhecido",
    "nao identificado",
    "não identificado",
    "unknown",
    "erro",
    "none",
    "null",
}

# Whitelist de chaves do metadata da fila de revisão que podem ser copiadas
# para o artefato persistido (campo `source_metadata` de `to_audit_metadata`).
# Filtra o restante para não vazar campos internos/voláteis da triagem para o
# resultado salvo. Inclui a telemetria Huawei (huawei_*) e a identidade real
# do operador resolvida na classificação (operator_*_real).
PIPELINE_METADATA_KEYS = {
    "origem",
    "source_type",
    "classification_status",
    "classification_error",
    "classified_by",
    "huawei_call_id",
    "huawei_begin_time",
    "huawei_duration",
    "huawei_is_call_in",
    "huawei_call_reason",
    "huawei_talk_reason",
    "huawei_talk_remark",
    "huawei_call_reason_code",
    "native_reason_match",
    "native_reason_targets",
    "audio_direction_pre_triage",
    "operator_sector_id",
    "operator_sector_real",
    "operator_name",
    "operator_name_real",
    "operator_id",
    "id_huawei",
    "matricula",
    "operator_matricula",
    "is_manual",
}


# ── Helpers de coerção/normalização (tolerantes, nunca levantam) ─────────────

def _clean_text(value: Any) -> str:
    """Converte para str tratando None e remove espaços nas bordas."""
    return str(value or "").strip()


def _first_text(*values: Any) -> str:
    """Primeiro valor não vazio (após limpeza) na ordem dada, ou ""."""
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


def _coerce_metadata(value: Any) -> dict[str, Any]:
    """Aceita dict ou JSON serializado (coluna `metadata_json` da fila); resto vira {}."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _coerce_float(value: Any) -> Optional[float]:
    """`float(value)` tolerante: None, "" ou valor inválido viram None."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_unknown_value(value: Any) -> bool:
    """True se o valor é uma sentinela de "desconhecido" (ver UNKNOWN_VALUES).

    Usada pelos consumidores (automação, telefonia) para decidir se um campo
    de classificação precisa de reparo/triagem manual antes de auditar.
    """
    return _clean_text(value).lower() in UNKNOWN_VALUES


def normalize_source_type(source_type: Any, filename: str = "") -> str:
    """Normaliza o tipo de fonte para um valor válido de `SOURCE_TYPES`.

    Valor fora do domínio cai no fallback por extensão do arquivo:
    `.pdf` → `pdf` (documento); qualquer outro → `DEFAULT_SOURCE_TYPE`
    (`audio`). O tipo decide a rota de processamento (transcrição de áudio
    versus parser de documento) — ver memória "auditoria áudio vs documento".
    """
    normalized = _clean_text(source_type).lower()
    if normalized in SOURCE_TYPES:
        return normalized
    return SOURCE_TYPE_PDF if _clean_text(filename).lower().endswith(".pdf") else DEFAULT_SOURCE_TYPE


# ── Contexto canônico do pipeline ────────────────────────────────────────────

@dataclass
class AuditPipelineContext:
    """Identificação que acompanha um item da classificação até o artefato salvo.

    Campos principais:
    - `origin`: uma das constantes `AUDIT_ORIGIN_*` (de onde a auditoria partiu);
    - `source_type`: `audio` ou `pdf` (decide a rota transcrição × parser);
    - `sector_id`/`alert_id`/`alert_label`: classificação prevista (ids do
      catálogo oficial; `sector_id` sempre minúsculo);
    - `operator_name`/`operator_id`: operador previsto/resolvido;
    - `queue_input_hash`: hash do item na fila (dedupe/rastreabilidade);
    - `media_path`: caminho da mídia classificada no storage;
    - `metadata`: cópia do metadata da fila (filtrado por
      `PIPELINE_METADATA_KEYS` só na hora de persistir);
    - `classification_confidence`/`review_reasons`: telemetria da classificação;
    - `context_repair_*`: trilha de auditoria dos reparos aplicados por
      `repair_queue_audit_context`/`apply_resolved_operator`.

    Mutável por design: as funções de reparo ajustam os campos in-place e
    registram cada mudança via `mark_repaired`, preservando o histórico.
    """

    origin: str
    source_type: str = DEFAULT_SOURCE_TYPE
    filename: str = ""
    sector_id: str = ""
    alert_id: str = ""
    alert_label: str = ""
    operator_name: str = ""
    operator_id: str = ""
    queue_input_hash: str = ""
    media_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    classification_confidence: Optional[float] = None
    review_reasons: list[str] = field(default_factory=list)
    context_repair_applied: bool = False
    context_repair_reasons: list[str] = field(default_factory=list)

    def mark_repaired(self, reason: str) -> None:
        """Registra um reparo aplicado ao contexto (idempotente por motivo).

        Os motivos acumulados saem em `to_audit_metadata()["context_repair"]`,
        deixando visível no artefato salvo o que foi corrigido e de onde veio.
        """
        reason = _clean_text(reason)
        if not reason:
            return
        self.context_repair_applied = True
        if reason not in self.context_repair_reasons:
            self.context_repair_reasons.append(reason)

    def to_router_context(self) -> dict[str, Any]:
        """Formato esperado pelo roteador de auditoria (kwargs de processamento).

        Inclui o próprio contexto em `pipeline_context` para que a camada de
        avaliação consiga repassá-lo até a persistência sem perder os campos.
        """
        return {
            "sector_id": self.sector_id,
            "alert_id": self.alert_id,
            "operator_name": self.operator_name,
            "operator_id": self.operator_id,
            "source_type": self.source_type,
            "filename": self.filename,
            "media_path": self.media_path,
            "pipeline_context": self,
        }

    def to_audit_metadata(self) -> dict[str, Any]:
        """Serializa o contexto para o bloco `audit_pipeline` do artefato salvo.

        É o contrato de persistência (gravado por `persist_audit_artifacts`
        dentro de `audio_quality`, lido por `qualification_audit` e pela UI):
        alterar chaves aqui exige atualizar `coerce_pipeline_context` e os
        leitores. O metadata da fila entra filtrado por
        `PIPELINE_METADATA_KEYS`, descartando valores vazios.
        """
        source_metadata = {
            key: value
            for key, value in (self.metadata or {}).items()
            if key in PIPELINE_METADATA_KEYS and value not in (None, "")
        }
        return {
            "origin": self.origin,
            "source_type": self.source_type,
            "filename": self.filename,
            "sector_id": self.sector_id,
            "alert_id": self.alert_id,
            "alert_label": self.alert_label,
            "operator_name": self.operator_name,
            "operator_id": self.operator_id,
            "queue_input_hash": self.queue_input_hash,
            "media_path": self.media_path,
            "classification": {
                "confidence": self.classification_confidence,
                "review_reasons": list(self.review_reasons),
            },
            "context_repair": {
                "applied": self.context_repair_applied,
                "reasons": list(self.context_repair_reasons),
            },
            "source_metadata": source_metadata,
        }


def coerce_pipeline_context(value: Any) -> Optional[AuditPipelineContext]:
    """Reconstrói um `AuditPipelineContext` a partir de instância ou dict serializado.

    Operação inversa de `to_audit_metadata`: aceita o próprio objeto (passa
    direto), um Mapping no formato persistido (re-hidrata campo a campo, com
    coerção tolerante) ou qualquer outra coisa → None. Permite que camadas
    que só carregam JSON (fila, rotas HTTP) repassem o contexto sem acoplar
    na dataclass.
    """
    if value is None:
        return None
    if isinstance(value, AuditPipelineContext):
        return value
    if not isinstance(value, Mapping):
        return None

    classification = value.get("classification") if isinstance(value.get("classification"), Mapping) else {}
    context_repair = value.get("context_repair") if isinstance(value.get("context_repair"), Mapping) else {}
    source_metadata = value.get("source_metadata") if isinstance(value.get("source_metadata"), Mapping) else {}
    return AuditPipelineContext(
        origin=_clean_text(value.get("origin")),
        source_type=normalize_source_type(value.get("source_type"), _clean_text(value.get("filename"))),
        filename=_clean_text(value.get("filename")),
        sector_id=_clean_text(value.get("sector_id")),
        alert_id=_clean_text(value.get("alert_id")),
        alert_label=_clean_text(value.get("alert_label")),
        operator_name=_clean_text(value.get("operator_name")),
        operator_id=_clean_text(value.get("operator_id")),
        queue_input_hash=_clean_text(value.get("queue_input_hash")),
        media_path=_clean_text(value.get("media_path")),
        metadata=dict(source_metadata),
        classification_confidence=_coerce_float(classification.get("confidence")),
        review_reasons=[
            _clean_text(reason)
            for reason in classification.get("review_reasons", [])
            if _clean_text(reason)
        ] if isinstance(classification.get("review_reasons"), list) else [],
        context_repair_applied=bool(context_repair.get("applied")),
        context_repair_reasons=[
            _clean_text(reason)
            for reason in context_repair.get("reasons", [])
            if _clean_text(reason)
        ] if isinstance(context_repair.get("reasons"), list) else [],
    )


# ── Construção do contexto por origem ────────────────────────────────────────

def build_manual_upload_context(
    *,
    filename: str,
    source_type: str,
    sector_id: Optional[str],
    alert_id: Optional[str],
    alert_label: Optional[str],
    operator_name: Optional[str],
    operator_id: Optional[str],
) -> AuditPipelineContext:
    """Contexto para upload manual na UI (origin=`manual_upload`).

    Os campos vêm do formulário (o auditor escolheu setor/alerta/operador),
    então não há metadata de fila nem confiança de classificação. Apenas
    normaliza: `sector_id` minúsculo e `source_type` validado contra o
    domínio (com fallback pela extensão do arquivo).
    """
    return AuditPipelineContext(
        origin=AUDIT_ORIGIN_MANUAL_UPLOAD,
        source_type=normalize_source_type(source_type, filename),
        filename=_clean_text(filename),
        sector_id=_clean_text(sector_id).lower(),
        alert_id=_clean_text(alert_id),
        alert_label=_clean_text(alert_label),
        operator_name=_clean_text(operator_name),
        operator_id=_clean_text(operator_id),
    )


def build_queue_audit_context(item: dict, *, origin: str) -> AuditPipelineContext:
    """Contexto a partir de um item da fila `fila_revisao_classificacao`.

    Usado pela automação (origin=`automation`) e pela tela Telefonia
    (origin=`telefonia_manual`). Cada campo tem cadeia de fallback: primeiro
    as colunas do item (`setor_previsto`, `alerta_previsto`,
    `operador_previsto`...), depois as variantes históricas no metadata —
    a ordem das alternativas é contrato com dados antigos já gravados, não
    reordenar. `media_path` prioriza o áudio classificado salvo no storage
    sobre o caminho original do item.
    """
    metadata = _coerce_metadata((item or {}).get("metadata") or (item or {}).get("metadata_json"))
    filename = _first_text((item or {}).get("nome_arquivo"), metadata.get("filename"), "gravacao.wav")
    motivos = (item or {}).get("motivos_revisao") or metadata.get("review_reasons") or []
    if not isinstance(motivos, list):
        motivos = []
    source_type = normalize_source_type(metadata.get("source_type") or (item or {}).get("source_type"), filename)
    media_path = _first_text(
        metadata.get("classified_audio_path"),
        metadata.get("classified_file_path"),
        (item or {}).get("media_path"),
    )

    return AuditPipelineContext(
        origin=origin,
        source_type=source_type,
        filename=filename,
        sector_id=_first_text(
            (item or {}).get("setor_previsto"),
            metadata.get("sector_id"),
            metadata.get("operator_sector_id"),
            metadata.get("setor"),
        ).lower(),
        alert_id=_first_text(
            (item or {}).get("alerta_previsto"),
            metadata.get("alert_id"),
            metadata.get("alerta_previsto"),
        ),
        alert_label=_first_text((item or {}).get("alerta_label"), metadata.get("alert_label")),
        operator_name=_first_text(
            (item or {}).get("operador_previsto"),
            metadata.get("operator_name"),
            metadata.get("operator_name_real"),
            metadata.get("operador_nome"),
        ),
        operator_id=_first_text(
            (item or {}).get("operator_id"),
            metadata.get("operator_id"),
            metadata.get("id_huawei"),
            metadata.get("operator_id_huawei_real"),
            metadata.get("matricula"),
            metadata.get("operator_matricula"),
            metadata.get("operador_id"),
        ),
        queue_input_hash=_clean_text((item or {}).get("input_hash")),
        media_path=media_path,
        metadata=metadata,
        classification_confidence=_coerce_float((item or {}).get("confianca") or metadata.get("confidence")),
        review_reasons=[_clean_text(reason) for reason in motivos if _clean_text(reason)],
    )


# ── Reparo determinístico do contexto antes da auditoria ─────────────────────

def repair_queue_audit_context(context: AuditPipelineContext) -> AuditPipelineContext:
    """Repara setor/alerta usando aliases do catálogo, dicas do nome do arquivo e metadata Huawei.

    Objetivo: evitar auditar (e gastar API) com setor/alerta "desconhecido"
    quando a informação existe em outro lugar do item. Estratégia em camadas:

    1. monta candidatos ignorando sentinelas (`is_unknown_value`) — valor
       atual do contexto, senão variantes do metadata;
    2. alinha os candidatos com o catálogo oficial via
       `align_classification_with_catalog` (resolve aliases/ids canônicos;
       consulta o Postgres com cache — falha vira warning, nunca aborta);
    3. aplica o melhor valor disponível (alinhado > candidato), registrando
       cada mudança em `mark_repaired` para auditoria posterior.

    Muta e retorna o MESMO objeto recebido (in-place). Levanta `ValueError`
    apenas se `context` for None.
    """
    if context is None:
        raise ValueError("context is required")

    metadata = context.metadata or {}
    original_sector = context.sector_id
    original_alert = context.alert_id

    candidate_sector = _first_text(
        context.sector_id if not is_unknown_value(context.sector_id) else "",
        metadata.get("operator_sector_id"),
        metadata.get("sector_id"),
        metadata.get("setor"),
    ).lower()
    candidate_alert = _first_text(
        context.alert_id if not is_unknown_value(context.alert_id) else "",
        metadata.get("alert_id"),
        metadata.get("alerta_previsto"),
    )

    try:
        from core.classification import align_classification_with_catalog

        aligned = align_classification_with_catalog(
            {
                "sector_id": candidate_sector,
                "alert_id": candidate_alert,
                "alert_label": context.alert_label,
                "_filename": context.filename,
            }
        )
    except Exception as exc:
        logger.warning(
            "Falha ao reparar contexto de auditoria via catalogo (origin=%s filename=%s): %s",
            context.origin,
            context.filename,
            exc,
        )
        aligned = {}

    aligned_sector = _clean_text(aligned.get("sector_id")).lower()
    aligned_alert = _clean_text(aligned.get("alert_id"))
    aligned_label = _clean_text(aligned.get("alert_label"))

    # Preferência: valor alinhado ao catálogo > candidato bruto do metadata.
    # Só sobrescreve com valores conhecidos — sentinela nunca substitui dado.
    if aligned_sector and not is_unknown_value(aligned_sector):
        if aligned_sector != context.sector_id:
            context.mark_repaired(f"sector:{context.sector_id or 'empty'}->{aligned_sector}")
        context.sector_id = aligned_sector
    elif candidate_sector and not is_unknown_value(candidate_sector):
        if candidate_sector != context.sector_id:
            context.mark_repaired(f"sector:{context.sector_id or 'empty'}->{candidate_sector}")
        context.sector_id = candidate_sector

    if aligned_alert and not is_unknown_value(aligned_alert):
        if aligned_alert != context.alert_id:
            context.mark_repaired(f"alert:{context.alert_id or 'empty'}->{aligned_alert}")
        context.alert_id = aligned_alert
    elif candidate_alert and not is_unknown_value(candidate_alert):
        if candidate_alert != context.alert_id:
            context.mark_repaired(f"alert:{context.alert_id or 'empty'}->{candidate_alert}")
        context.alert_id = candidate_alert

    if aligned_label and aligned_label != context.alert_label:
        context.alert_label = aligned_label

    # Marca recuperação total (campo era sentinela e agora tem valor real) —
    # sinal distinto do reparo pontual "a->b" registrado acima.
    if is_unknown_value(original_sector) and context.sector_id and not is_unknown_value(context.sector_id):
        context.mark_repaired("sector_recovered")
    if is_unknown_value(original_alert) and context.alert_id and not is_unknown_value(context.alert_id):
        context.mark_repaired("alert_recovered")

    return context


def apply_resolved_operator(
    context: Optional[AuditPipelineContext],
    resolved_operator: Optional[dict],
    *,
    fallback_operator_name: Optional[str] = None,
    fallback_operator_id: Optional[str] = None,
) -> None:
    """Aplica ao contexto o operador resolvido contra o cadastro RH (in-place).

    `resolved_operator` é o dict retornado pela resolução de identidade
    (`core.classification` / repositório de operadores): usa `name` e, para o
    id, prioriza `matricula` > `preferredId` > fallback informado. Troca de
    nome é registrada em `mark_repaired`; troca de id não (id não é exibido
    como reparo). No-op se não houver contexto ou operador resolvido.
    """
    if context is None or not resolved_operator:
        return
    resolved_name = _clean_text(resolved_operator.get("name")) or _clean_text(fallback_operator_name)
    resolved_id = (
        _clean_text(resolved_operator.get("matricula"))
        or _clean_text(resolved_operator.get("preferredId"))
        or _clean_text(fallback_operator_id)
    )
    if resolved_name and resolved_name != context.operator_name:
        context.mark_repaired(f"operator_name:{context.operator_name or 'empty'}->{resolved_name}")
        context.operator_name = resolved_name
    if resolved_id and resolved_id != context.operator_id:
        context.operator_id = resolved_id


# ── Anexação do contexto ao artefato persistido ──────────────────────────────

def attach_pipeline_context_to_audio_quality(
    audio_quality: Optional[dict],
    pipeline_context: Any,
    *,
    transcription_metadata: Optional[dict[str, Any]] = None,
) -> Optional[dict]:
    """Embute o contexto do pipeline no dict `audio_quality` antes de persistir.

    Ponto de junção entre classificação e resultado salvo: o bloco
    `audio_quality["audit_pipeline"]` (gerado por `to_audit_metadata`) é o que
    `persist_audit_artifacts` grava e o que a qualificação lê depois. Se
    `transcription_metadata` for informado, anexa também um resumo da
    estratégia de transcrição vencedora (selector de candidatos).

    Não muta o dict recebido (retorna cópia rasa). Se o contexto não puder
    ser coerido, devolve `audio_quality` inalterado.
    """
    context = coerce_pipeline_context(pipeline_context)
    if context is None:
        return audio_quality

    merged = dict(audio_quality or {})
    audit_pipeline = context.to_audit_metadata()
    if transcription_metadata:
        audit_pipeline["transcription_strategy"] = {
            "selected_strategy": transcription_metadata.get("selected_strategy"),
            "selected_provider": transcription_metadata.get("selected_provider"),
            "selected_reason": transcription_metadata.get("selected_reason"),
        }
    merged["audit_pipeline"] = audit_pipeline
    return merged
