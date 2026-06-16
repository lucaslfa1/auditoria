"""Classificação de ligações (triagem): setor + alerta + operador + direção.

Papel no fluxo: sync Huawei D-1 → **este módulo** (transcrição leve + GPT
classifica cada ligação) → fila de triagem (`fila_revisao_classificacao`) →
automação audita os itens prontos → Arquivos Salvos → aprovação → fechamento.

Pipeline de `classify_audio` (entrada principal):
1. transcrição LEVE (áudio truncado a ~90s — só o tópico importa na triagem);
2. classificação via GPT-4o com prompt dinâmico (catálogo + pistas do nome do
   arquivo + lista de operadores + feedback RAG);
3. alinhamento com o catálogo oficial (`align_classification_with_catalog`)
   — valores não reconhecidos viram 'desconhecido', nunca chute silencioso;
4. guardrails determinísticos (temperatura, hierarquia de alertas,
   parada×desvio, manutenção-como-contexto, setor oficial do operador no RH,
   direção efetivada×receptiva).

CUSTO DE API: cada ligação classificada gasta 1 transcrição (Whisper →
GPT-4o-diarize → Azure Fast, em fallback) + 1 chamada GPT-4o (registrada no
`cost_guard`). O catálogo é cacheado (TTL 5 min) para não bater no banco a
cada item.

Fonte de verdade do catálogo: tabelas `audit_sectors`/`audit_alerts` no Neon
(fallback de emergência p/ YAML via env `CRITERIA_CATALOG_SOURCE=yaml`).
"""

import asyncio
import json
import logging
import os
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Import credentials and settings from services.py
from services import (
    AZURE_SPEECH_KEY, 
    AZURE_SPEECH_REGION,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    AZURE_OPENAI_DEPLOYMENT,
    ai_client,
    AI_MODEL,
    AI_PROVIDER_PRIORITY
)

from core import cost_guard
from db.database import get_connection

# Blocos extraídos para módulos próprios (sem mudança de comportamento).
# Reimport explícito mantém `core.classification.<nome>` válido p/ terceiros.
from core.classification_audio import (
    MAX_AUDIO_DURATION_SECONDS,
    _trim_leading_silence_enabled,
    get_mime_type,
    truncate_audio,
)
from core.classification_lexicon import (
    TEMPERATURE_KEYWORDS,
    TEMPERATURE_OFF_KEYWORDS,
    DRIVER_CUES,
    CLIENT_CUES,
    TEMPERATURE_ALERTS_BY_CONTEXT,
    TEMPERATURE_ALERT_IDS,
    PARADA_DESVIO_ALERT_IDS,
    POSITION_SIGNAL_WEIGHTS,
    PRIORITY_SIGNAL_WEIGHTS,
    POLICE_SIGNAL_WEIGHTS,
    PARADA_SIGNAL_WEIGHTS,
    DESVIO_SIGNAL_WEIGHTS,
    MAINTENANCE_CONTEXT_KEYWORDS,
    NON_AUDITABLE_OUTPUT_KEYWORDS,
    STADIA_CONTEXT_KEYWORDS,
)
from core.classification_alert_equivalence import (
    _OPERATIONAL_SECTORS,
    _OPERATIONAL_ALERT_PREFIXES,
    _LOGISTICA_KIND_ALERTS,
    _get_catalog_alert,
    _apply_alert_match,
    _normalize_alert_token,
    _infer_alert_actor_suffix,
    _extract_operational_alert_kind,
    _operational_alert_suffix,
    _get_equivalent_alert_for_sector,
)
# Pré-parser determinístico de nome de arquivo extraído (v1.3.148); reexportado
# para compat (callers internos + huawei/sync_classification + anotação
# FilenameParsed em resolve_operator_identity).
from core.classification_filename import (  # noqa: F401
    FilenameParsed,
    parse_filename,
)


def get_operators_summary_for_prompt() -> str:
    """Lista colaboradores ativos auditaveis para o prompt de classificacao.

    Restaurado apos a migracao para repositories.operators (commit a6a72aa)
    deixar a referencia orfa em classification.py — todo triage retornava
    NameError -> alert_id='erro'.
    """
    try:
        from repositories import operators

        names = operators.get_colaboradores_para_prompt(get_connection)
    except Exception:
        logger.exception("Falha ao carregar colaboradores para o prompt; seguindo sem lista.")
        return ""
    if not names:
        return ""
    return "OPERADORES CADASTRADOS (use para confirmar o nome reconhecido):\n" + "\n".join(f"- {name}" for name in names)


# ── Configurações e constantes da classificação ─────────────────────────────
MAX_FILES_PER_REQUEST = 50
LOW_CONFIDENCE_REVIEW_THRESHOLD = float(os.getenv("LOW_CONFIDENCE_REVIEW_THRESHOLD", "0.8"))
VERY_LOW_CONFIDENCE_REVIEW_THRESHOLD = 0.5
# D' (hora extra detection): se IA classifica setor diferente do cadastro com
# confianca >= este threshold, confia na IA (provavel hora extra). Senao,
# forca setor do cadastro mas preserva alerta da IA pra auditor revisar.
SECTOR_TRUST_CONFIDENCE = float(os.getenv("SECTOR_TRUST_CONFIDENCE", "0.9"))
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

_ALERT_ID_ALIASES = {
    "BAS-POLICIAL": "BAS-PRIORITARIO-POLICIA",
    # Migracao BBM -> Distribuicao em 2026-05-18 (v1.3.74) - manter por
    # defense-in-depth caso IA ou fonte externa devolva alert_id antigo.
    "BBM-PARADA-MOT": "DISTRIBUICAO-PARADA-MOT",
    "BBM-PARADA-CLI": "DISTRIBUICAO-PARADA-CLI",
    "BBM-DESVIO-MOT": "DISTRIBUICAO-DESVIO-MOT",
    "BBM-DESVIO-CLI": "DISTRIBUICAO-DESVIO-CLI",
    "BBM-POSICAO-MOT": "DISTRIBUICAO-POSICAO-MOT",
    "BBM-POSICAO-CLI": "DISTRIBUICAO-POSICAO-CLI",
    "BBM-PRIORITARIO-MOT": "DISTRIBUICAO-PRIORITARIO-MOT",
    "BBM-PRIORITARIO-CLI": "DISTRIBUICAO-PRIORITARIO-CLI",
    "BBM-PRIORITARIO-POLICIA": "DISTRIBUICAO-PRIORITARIO-POLICIA",
    "BBM-PONTO-APOIO": "DISTRIBUICAO-PONTO-APOIO",
}

# ── Direção da ligação (guardrail EFETUADA × RECEPTIVA) ──────────────────────

def _normalize_direction_value(value: str | None) -> str | None:
    """Normaliza texto livre de direção para 'receptiva'/'efetivada' (ou None se ambíguo)."""
    normalized = _normalize_operator_identity_text(value)
    if not normalized:
        return None
    if any(token in normalized for token in ("receptiva", "recebida", "inbound")):
        return "receptiva"
    if any(token in normalized for token in ("efetivada", "ativa", "outbound", "realizada")):
        return "efetivada"
    return None


def _expected_direction_for_sector(sector_id: str | None) -> str | None:
    """Mantido por compatibilidade. A regra de direcao agora e per-alert."""
    _ = sector_id
    return None


# Guardrail EFETUADA vs RECEPTIVA por keyword no alert_id (decisao A.1).
# Quando expected != classified, marca needs_review com motivo 'direction_mismatch',
# mas NAO bloqueia a auditoria. Para desligar: DIRECTION_GUARDRAIL_ENABLED=false.
_DIRECTION_KEYWORDS_EFETIVADA = (
    "PRIORITARIO-POLICIA",
    "POLICIAL",
    "PARADA-MOT",
    "PARADA-CLI",
    "DESVIO",
    "ABANDONO",
    "PONTO-APOIO",
    "POSICAO-MOT",
    "POSICAO-CLI",
)
_DIRECTION_KEYWORDS_RECEPTIVA = (
    "RECEPTIVA",
    "RECEBIDA",
    "INBOUND",
    "ATENDIMENTO-INBOUND",
)


def _expected_direction_for_alert(alert_id: str | None) -> str | None:
    """Infere direcao esperada (efetivada/receptiva) por keyword no alert_id.

    Retorna None quando o alert_id nao bate com nenhuma keyword conhecida —
    nesse caso o guardrail nao dispara.
    """
    if not alert_id:
        return None
    if os.getenv("DIRECTION_GUARDRAIL_ENABLED", "true").strip().lower() in ("0", "false", "no", "off"):
        return None
    normalized = _normalize_alert_token(alert_id)
    if not normalized:
        return None
    for keyword in _DIRECTION_KEYWORDS_RECEPTIVA:
        if keyword in normalized:
            return "receptiva"
    for keyword in _DIRECTION_KEYWORDS_EFETIVADA:
        if keyword in normalized:
            return "efetivada"
    return None


def _append_review_reason(classification: dict, reason: str) -> None:
    """Acrescenta um motivo de revisão humana ao dict (sem duplicar)."""
    reasons = classification.get("review_reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    if reason not in reasons:
        reasons.append(reason)
    classification["review_reasons"] = reasons



@dataclass
class ClassificationResult:
    """Resultado da classificação de um áudio (contrato com a fila de triagem).

    `sector_id`/`alert_id` em {'desconhecido','erro'} sinalizam falha de
    identificação; `needs_review`/`review_reasons`/`review_priority` são
    derivados em `finalize_classification_result` e decidem se o item vai
    direto para a automação ou para triagem manual.
    """
    filename: str
    sector_id: str
    sector_label: str
    alert_id: str
    alert_label: str
    confidence: float
    operator_name: Optional[str] = None
    direction: Optional[str] = None
    id_huawei: Optional[str] = None
    matricula: Optional[str] = None
    error: Optional[str] = None
    direction_mismatch: bool = False
    needs_review: bool = False
    review_reasons: list[str] = field(default_factory=list)
    review_priority: str = "low"
    # D' (guardrail D'): campos auxiliares propagados para metadata da fila
    # pra que o auditor veja sugestoes da IA quando guardrail interveio.
    # Devem ser populados pelo guardrail (enforce_operator_and_direction_guardrails).
    metadata_extras: dict = field(default_factory=dict)


def finalize_classification_result(result: ClassificationResult) -> ClassificationResult:
    """Deriva `needs_review`, `review_reasons` e `review_priority` do resultado.

    Regras: erro de classificação, confiança < LOW/VERY_LOW thresholds,
    setor/alerta não identificados e direction_mismatch geram motivos;
    motivos "graves" elevam a prioridade para 'high'. SEMPRE passar o
    resultado por aqui antes de devolver ao caller (muta e retorna o mesmo objeto).
    """
    review_reasons: list[str] = list(result.review_reasons) if result.review_reasons else []
    try:
        confidence = float(result.confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if result.error:
        review_reasons.append("erro_classificacao")

    if confidence < LOW_CONFIDENCE_REVIEW_THRESHOLD:
        review_reasons.append("baixa_confianca")
    if confidence < VERY_LOW_CONFIDENCE_REVIEW_THRESHOLD:
        review_reasons.append("confianca_muito_baixa")

    if result.sector_id in {"desconhecido", "erro"}:
        review_reasons.append("setor_nao_identificado")
    if result.alert_id in {"desconhecido", "erro"}:
        review_reasons.append("alerta_nao_identificado")
        
    if result.direction_mismatch:
        review_reasons.append("direction_mismatch")

    result.review_reasons = list(dict.fromkeys(review_reasons))
    result.needs_review = bool(result.review_reasons)

    high_priority_reasons = {
        "erro_classificacao",
        "setor_nao_identificado",
        "alerta_nao_identificado",
        "confianca_muito_baixa",
    }

    if not result.needs_review:
        result.review_priority = "low"
    elif any(reason in high_priority_reasons for reason in result.review_reasons):
        result.review_priority = "high"
    else:
        result.review_priority = "medium"

    return result


import time

# ── Catálogo de setores/alertas (DB-first, cache TTL 5 min) ──────────────────

def ttl_cache(maxsize: int = 1, ttl: int = 300):
    """Cache simples com expiração por tempo (evita lru_cache eterno p/ dados do banco).

    Ao atingir `maxsize` o cache inteiro é limpo (sem LRU real — suficiente
    para os poucos getters de catálogo). Expõe `cache_clear()` p/ hot-reload.
    """
    def decorator(func):
        cache = {}
        def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            now = time.monotonic()
            if key in cache:
                value, timestamp = cache[key]
                if now - timestamp < ttl:
                    return value
            value = func(*args, **kwargs)
            if len(cache) >= maxsize:
                cache.clear()
            cache[key] = (value, now)
            return value
        wrapper.cache_clear = cache.clear
        return wrapper
    return decorator

@ttl_cache(ttl=300)
def load_audit_criteria_catalog() -> dict[str, dict[str, object]]:
    """Carrega o catálogo de classificação do banco (Fase 1.1 do plano DB-first).

    Lê de `audit_sectors` + `audit_alerts` (com `pop_ref`) e reaplica a
    replicação BAS→setores irmãos em memória, mantendo o mesmo contrato da
    versão YAML. Retorno: {sector_id: {"label": ..., "alerts": [{id,label,pop_ref}]}}.

    Fonte da verdade transitiva: o seed em `database._seed_audit_criteria`
    ainda faz UPSERT do YAML em todo deploy, então na prática DB ↔ YAML
    continuam paritários. Edição via UI gera trail em `audit_*_audit_log` mas
    é sobrescrita no próximo deploy até a Fase 1.2 (parar seed destrutivo).

    Fallback de segurança: env `CRITERIA_CATALOG_SOURCE=yaml` reverte para a
    leitura YAML (sem deploy), útil em caso de incidente. Cache TTL de 5 min.
    """
    source = os.getenv("CRITERIA_CATALOG_SOURCE", "db").strip().lower()
    if source == "yaml":
        return _load_catalog_from_yaml()
    try:
        return _load_catalog_from_db()
    except Exception:
        logger.exception("load_audit_criteria_catalog DB-first falhou — fallback para YAML")
        return _load_catalog_from_yaml()


def _load_catalog_from_yaml() -> dict[str, dict[str, object]]:
    """Versao legada do catalogo (le scoring_rules.yaml + replica BAS→siblings)."""
    from db.scoring_loader import load_scoring_rules

    rules = load_scoring_rules()
    catalog: dict[str, dict[str, object]] = {}

    sector_labels = {s["id"]: s["label"] for s in rules.get("sectors", [])}

    for alert in rules.get("alerts", []):
        sector_id = alert["sector"]
        alert_id = alert["id"]
        alert_label = alert["label"]
        pop_ref = alert.get("pop_ref", "")

        if sector_id not in catalog:
            catalog[sector_id] = {
                "label": sector_labels.get(sector_id, sector_id),
                "alerts": [],
            }
        catalog[sector_id]["alerts"].append({
            "id": alert_id,
            "label": alert_label,
            "pop_ref": pop_ref,
        })

    if not catalog:
        raise ValueError("Empty classification catalog from scoring_rules.yaml")

    return _apply_operational_siblings(catalog, sector_labels)


def _load_catalog_from_db() -> dict[str, dict[str, object]]:
    """Le o catalogo direto de audit_sectors + audit_alerts."""
    import db.database as database

    catalog: dict[str, dict[str, object]] = {}
    sector_labels: dict[str, str] = {}

    conn = database.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, label FROM audit_sectors")
        for row in cursor.fetchall():
            sector_labels[row[0]] = row[1]

        cursor.execute(
            "SELECT id, sector_id, label, COALESCE(pop_ref, '') FROM audit_alerts ORDER BY sector_id, id"
        )
        for alert_id, sector_id, label, pop_ref in cursor.fetchall():
            if sector_id not in catalog:
                catalog[sector_id] = {
                    "label": sector_labels.get(sector_id, sector_id),
                    "alerts": [],
                }
            catalog[sector_id]["alerts"].append({
                "id": alert_id,
                "label": label,
                "pop_ref": pop_ref,
            })
    finally:
        conn.close()

    if not catalog:
        raise ValueError("Empty classification catalog from database")

    return _apply_operational_siblings(catalog, sector_labels)


def _apply_operational_siblings(
    catalog: dict[str, dict[str, object]],
    sector_labels: dict[str, str],
) -> dict[str, dict[str, object]]:
    """Replica os alertas do setor BAS para os setores operacionais irmãos.

    Setores operacionais (transferencia, distribuicao, fenix, uti, ...)
    compartilham os mesmos alertas 4.1.x do BAS; em vez de duplicar no banco,
    a réplica vive em memória por enquanto — será movida para o DB na Fase 1.3.
    """
    _OPERATIONAL_SIBLINGS = {"transferencia", "distribuicao", "fenix", "uti", "rastreamento", "grs", "sinistros"}
    bas_alerts = catalog.get("bas", {}).get("alerts", [])
    if bas_alerts:
        for sibling in _OPERATIONAL_SIBLINGS:
            if sibling in sector_labels and sibling not in catalog:
                catalog[sibling] = {
                    "label": sector_labels[sibling],
                    "alerts": list(bas_alerts),
                }
            elif sibling in catalog:
                existing_alert_ids = {a["id"] for a in catalog[sibling].get("alerts", [])}
                for bas_alert in bas_alerts:
                    if bas_alert["id"] not in existing_alert_ids:
                        catalog[sibling].setdefault("alerts", []).append(bas_alert)
    return catalog


@ttl_cache(ttl=300)
def build_sectors_and_alerts_prompt() -> str:
    """Monta o bloco dinâmico do prompt listando todos os setores e alertas.

    Inclui tanto o id do catálogo (ex.: UTI-PARADA-MOT) quanto a referência de
    POP (ex.: 4.1.5), para que a IA possa devolver qualquer um dos formatos.
    Cacheado (TTL 5 min) — é texto grande montado a partir do catálogo.
    """
    lines = ["SETORES E ALERTAS DISPONIVEIS:", ""]

    for index, (sector_id, sector_data) in enumerate(load_audit_criteria_catalog().items(), start=1):
        sector_label = str(sector_data["label"])
        alerts = sector_data["alerts"]
        alert_parts = []
        for alert in alerts:
            pop = alert.get("pop_ref", "")
            if pop:
                alert_parts.append(f"{alert['id']} [POP {pop}] ({alert['label']})")
            else:
                alert_parts.append(f"{alert['id']} ({alert['label']})")

        if not alert_parts:
            continue

        lines.append(f"{index}. {sector_id} ({sector_label})")
        lines.append(f"   Alertas: {', '.join(alert_parts)}")
        lines.append("")

    return "\n".join(lines).strip()


@ttl_cache(ttl=300)
def get_alert_lookup_by_id() -> dict[str, tuple[str, str, str]]:
    """Lookup: alert_id → (sector_id, sector_label, alert_label).

    Indexa o id do catálogo (UTI-PARADA-MOT), os aliases legados
    (`_ALERT_ID_ALIASES`, ex.: BBM-*) E o pop_ref (4.1.5), para resolver
    classificações em qualquer um dos formatos. Cacheado (TTL 5 min).
    """
    lookup: dict[str, tuple[str, str, str]] = {}
    for sector_id, sector_data in load_audit_criteria_catalog().items():
        sector_label = str(sector_data["label"])
        for alert in sector_data["alerts"]:
            yaml_id = str(alert["id"])
            pop_ref = str(alert.get("pop_ref", ""))
            entry = (sector_id, sector_label, str(alert["label"]))
            # Primary key: YAML id
            lookup[yaml_id] = entry
            for alias, canonical_id in _ALERT_ID_ALIASES.items():
                if canonical_id == yaml_id:
                    lookup[alias] = entry
            # Secondary key: POP reference (e.g. "4.1.5")
            if pop_ref and pop_ref not in lookup:
                lookup[pop_ref] = entry
    return lookup


def _canonicalize_alert_id(alert_id: str) -> str:
    return _ALERT_ID_ALIASES.get(alert_id, alert_id)


def canonicalize_alert_id(alert_id: str) -> str:
    """API publica para resolver aliases (ex.: BAS-POLICIAL -> BAS-PRIORITARIO-POLICIA)."""
    return _canonicalize_alert_id(alert_id)


# ── Equivalência de alertas entre setores operacionais ──────────────────────
# Helpers e constantes em core/classification_alert_equivalence.py (reexportados
# acima). Esta variante fica aqui porque os testes a monkeypatcham diretamente.
def _get_equivalent_alert_from_context(
    sector_id: str,
    alert_id: str,
    *,
    alert_hint: str | None = None,
    filename: str | None = None,
) -> tuple[str, str, str] | None:
    """Variante de `_get_equivalent_alert_for_sector` que infere o ator (MOT/CLI)
    a partir do contexto (alert_id + hint + nome do arquivo)."""
    actor = _infer_alert_actor_suffix(alert_id, alert_hint, filename)
    for candidate in (alert_id, alert_hint):
        match = _get_equivalent_alert_for_sector(sector_id, candidate or "", actor=actor)
        if match:
            return match
    return None


# ── Alinhamento da classificação com o catálogo oficial ─────────────────────
# Substitui a versão legada acima: valores não reconhecidos PERMANECEM
# 'desconhecido' (sem fallback silencioso) para a triagem revisar.
def align_classification_with_catalog(classification: dict) -> dict:
    """Garante que sector_id e alert_id da classificação existam no catálogo.

    Cadeia de fallback, na ordem:
      1. match exato do alert_id dentro do setor classificado;
      1b. alerta equivalente do mesmo tipo no setor (ex.: id de outro setor);
      2. lookup cross-setor do alert_id (alerta existe, setor estava errado);
      3. pistas determinísticas do nome do arquivo (`parse_filename`);
      4. fuzzy match do alert_label dentro do setor;
      5. nada casou → marca setor/alerta como "desconhecido" (revisão manual).

    Muta e retorna o mesmo dict. Usa a chave interna `_filename` (removida
    pelo caller depois). Invariante: NUNCA inventa um alerta que não existe
    no catálogo — 'desconhecido' é preferível a chute.
    """
    sector_id = str(classification.get("sector_id", "")).strip().lower()
    alert_id = _canonicalize_alert_id(str(classification.get("alert_id", "")).strip())
    alert_label = str(classification.get("alert_label", "")).strip()
    
    catalog = load_audit_criteria_catalog()

    if sector_id in catalog:
        for alert in catalog[sector_id]["alerts"]:
            if alert["id"] == alert_id:
                classification["sector_id"] = sector_id
                classification["sector_label"] = str(catalog[sector_id]["label"])
                classification["alert_id"] = alert_id
                classification["alert_label"] = alert["label"]
                return classification

        parsed = parse_filename(str(classification.get("_filename", "") or "")) if classification.get("_filename") else None
        equivalent = _get_equivalent_alert_from_context(
            sector_id,
            alert_id,
            alert_hint=parsed.alert_hint if parsed else None,
            filename=str(classification.get("_filename") or ""),
        )
        if equivalent:
            logger.info(
                "align_catalog: remapped alert_id '%s' to sector-specific '%s' for sector '%s'",
                alert_id,
                equivalent[1],
                sector_id,
            )
            return _apply_alert_match(classification, equivalent)

    matched_alert = get_alert_lookup_by_id().get(alert_id)
    if matched_alert:
        matched_sector_id, matched_sector_label, matched_alert_label = matched_alert
        classification["sector_id"] = matched_sector_id
        classification["sector_label"] = matched_sector_label
        classification["alert_id"] = alert_id
        classification["alert_label"] = matched_alert_label
        return classification

    filename = classification.get("_filename", "")
    if filename:
        parsed = parse_filename(filename)
        hint_sector_id = parsed.sector_hint or sector_id
        if parsed.alert_id_hint and hint_sector_id in catalog:
            hint_sector = catalog[hint_sector_id]
            for alert in hint_sector["alerts"]:
                if alert["id"] == parsed.alert_id_hint:
                    classification["sector_id"] = hint_sector_id
                    classification["sector_label"] = str(hint_sector["label"])
                    classification["alert_id"] = parsed.alert_id_hint
                    classification["alert_label"] = alert["label"]
                    logger.info(
                        "align_catalog: recovered alert_id '%s' -> '%s' via filename hint (sector=%s)",
                        alert_id, parsed.alert_id_hint, hint_sector_id,
                    )
                    return classification

    if sector_id in catalog and alert_label:
        normalized_req = normalize_classification_text(alert_label)
        best_match = None
        best_score = 0
        for alert in catalog[sector_id]["alerts"]:
            normalized_cat = normalize_classification_text(alert["label"])
            if not normalized_req or not normalized_cat:
                continue
            score = 0
            if normalized_req in normalized_cat or normalized_cat in normalized_req:
                score = min(len(normalized_req), len(normalized_cat))
            if score > best_score:
                best_score = score
                best_match = alert
        if best_match and best_score >= 4:
            classification["sector_id"] = sector_id
            classification["sector_label"] = str(catalog[sector_id]["label"])
            classification["alert_id"] = best_match["id"]
            classification["alert_label"] = best_match["label"]
            logger.info(
                "align_catalog: fuzzy-matched alert_label '%s' -> '%s' (%s)",
                alert_label, best_match["label"], best_match["id"],
            )
            return classification

    if sector_id in catalog:
        classification["sector_id"] = sector_id
        classification["sector_label"] = str(catalog[sector_id]["label"])
        classification["alert_id"] = "desconhecido"
        classification["alert_label"] = "Nao Identificado"
        logger.warning(
            "align_catalog: alert_id '%s' not found in sector '%s' -> marking alert as desconhecido",
            alert_id, sector_id,
        )
        return classification

    classification["sector_id"] = "desconhecido"
    classification["sector_label"] = "Nao Identificado"
    classification["alert_id"] = "desconhecido"
    classification["alert_label"] = "Nao Identificado"
    logger.warning(
        "align_catalog: nothing matched (sector='%s', alert='%s') -> marking sector and alert as desconhecido",
        sector_id, alert_id,
    )
    return classification
# ── Prompt de classificação (enviado ao GPT-4o — chamada paga) ──────────────
# Prompt ativo, mantido ASCII-safe. Placeholders são preenchidos em
# classify_with_gpt/classify_with_ai: catálogo, transcrição, pistas do nome do
# arquivo, lista de operadores e feedback de calibração (RAG).
CLASSIFICATION_PROMPT = """Voce e um classificador de ligacoes telefonicas de uma central de monitoramento logistico e de frotas.

Classifique: SETOR, ALERTA, OPERADOR e DIRECAO.

{sectors_and_alerts}

ARQUIVO: {filename}
{filename_hints}

TRANSCRICAO:
{transcription}

REGRAS:
1. PARADA/DESVIO COM POLICIA ou roubo -> setor operacional correspondente e alerta PRIORITARIO-POLICIA desse setor. Exemplos: DISTRIBUICAO-PRIORITARIO-POLICIA, TRANSFERENCIA-PRIORITARIO-POLICIA, FENIX-PRIORITARIO-POLICIA, UTI-PRIORITARIO-POLICIA; BAS usa BAS-PRIORITARIO-POLICIA.
2. PARADA/DESVIO LOGISTICO (cobranca branda, foco em entrega) -> logistica, alertas LOGISTICA-PARADA ou LOGISTICA-DESVIO
3. PARADA EXCESSIVA = veiculo ficou parado por tempo excessivo antes de reiniciar viagem -> LOGISTICA-PARADA-EXCESSIVA-MOT/CLI
4. VIAGEM SEM ESPELHAMENTO / PERDA DE POSICAO com cliente -> LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI ou LOGISTICA-PERDA-POSICAO-CLI
5. ATRASO = descumprimento de horario de CHEGADA ao cliente -> LOGISTICA-ATRASO. Parada no caminho = LOGISTICA-PARADA, nao LOGISTICA-ATRASO
6. ESTADIA = motorista parado na DOCA/CLIENTE para carga/descarga -> LOGISTICA-ESTADIA
7. TEMPERATURA (setpoint, bau refrigerado, termografo) -> logistica, alertas LOGISTICA-TEMPERATURA-MOT/CLI ou LOGISTICA-DESLIG-TEMP-MOT/CLI
8. CADASTRO = somente consulta de antecedentes -> CADASTRO-ANTECEDENTES. Nunca usar para logistica
7. sector_id e alert_id devem ser exatamente os listados acima na secao SETORES E ALERTAS
8. Priorize setor/alerta do nome do arquivo se disponivel
9. SETORES OPERACIONAIS usam IDs setoriais do catalogo atual. Nao troque distribuicao/transferencia/fenix para "uti" apenas pelo tipo do alerta; preserve o setor do operador e escolha o alert_id equivalente daquele setor. UTI refere-se a GRS (Gerenciamento de Risco e Sinistro) ou Tratativa de Incidentes. BAS e a base de monitoramento principal.
10. "Rastreamento" e pista operacional, nao decisao final por si so. Se o operador identificado existir no cadastro, o setor cadastrado tem prioridade sobre autodeclaracoes genericas como "rastreamento". Operadores de distribuicao podem se apresentar como "rastreamento" sem pertencer ao setor "transferencia"
11. MULTIPLAS VIOLACOES na mesma ligacao (ex: parada indevida + violacao de bateria + comportamento inadequado) -> classificar como UTI-PRIORITARIO-MOT no setor operacional correspondente
12. ALERTAS CRITICOS tem prioridade sobre alertas menores. Se a fala enfatizar perda de sinal, sem posicao ou posicao em atraso, priorize POSICAO. Se enfatizar painel violado, violacao, botao de panico, sensor de desengate ou bau violado, priorize ALERTA PRIORITARIO, mesmo que tambem exista parada ou desvio na conversa.
13. CONTATO COM POLICIA ou acionamento policial -> classificar como PRIORITARIO-POLICIA no setor operacional correspondente, usando exatamente o ID listado no catalogo para esse setor
14. DIRECAO DA LIGACAO: "receptiva" se o motorista/cliente ligou para a central; "efetivada" se o operador da central ligou para fora
15. Quando a duvida for entre PARADA e DESVIO, use a enfase da fala. Se a ligacao repete mais "parada", "parado", "parada indevida", classifique como PARADA. Se repete mais "desvio", "rota", "fora da rota", classifique como DESVIO.
16. Se houver duvida real entre dois setores ou alertas e a evidencia nao favorecer claramente um deles, nao chute. Use "desconhecido" no campo incerto.
17. So use confidence >= 0.90 quando houver evidencia clara e consistente na transcricao, no nome do arquivo ou em ambos.
18. Se o nome do operador nao estiver claramente identificavel, retorne null.
19. Se a direcao da ligacao nao estiver clara, retorne a melhor hipotese com confidence menor. Nao invente certeza.
20. Quando houver conflito entre sinais fracos da transcricao e pista forte do nome do arquivo, prefira o nome do arquivo apenas se ele for um padrao confiavel.
21. Para atendimentos de texto/multimidia via WhatsApp (frequentemente com Rastreamento_Whatsapp no nome), prefira classificar no setor "receptivo" (celula de atendimento) ou conforme as pistas do arquivo.
22. MANUTENCAO/OFICINA/REPARO/DOCA/CARGA/DESCARGA sao apenas contexto operacional da ligacao. Nunca retorne "INFORMATIVO", "Nao Auditavel" ou "Manutencao" como alerta final por esse motivo. Identifique o alerta que gerou o contato: parada, desvio, posicao/perda de sinal, prioritario, policia, violacao, temperatura, estadia ou outro alerta do catalogo. Se nao houver evidencia suficiente para escolher o alerta, use "desconhecido" para revisao manual.

OPERADOR:
- E a pessoa da CENTRAL (nao o motorista/cliente)
- Procure: "aqui e o/a [Nome]", "meu nome e [Nome]", ou nome no arquivo
- Padrao de arquivo: ALERTA-TIPO-DATA_Nome_Sobrenome_Setor_Voz.wav
- Se o operador identificado estiver na lista oficial, priorize o setor cadastrado desse operador sobre autodeclaracoes amplas como "rastreamento"

{known_operators}

{feedback_calibration}

JSON (sem emoji, sem texto extra):
{{
  "raciocinio_situacao": "Descreva em 1 frase curta o problema relatado no audio",
  "raciocinio_regras": "Com base nas regras, explique qual se aplica aqui e por que",
  "sector_id": "id_exato",
  "sector_label": "Nome do Setor",
  "alert_id": "id_exato",
  "alert_label": "Nome do Alerta",
  "operator_name": "Nome ou null",
  "direction": "efetivada ou receptiva",
  "confidence": "Numero decimal entre 0.00 e 1.00 baseando-se na clareza do audio e certeza da classificacao"
}}"""

import re as _re

@dataclass
class ResolvedOperatorIdentity:
    """Identidade do operador resolvida contra o cadastro (`colaboradores`).

    `db_sector` é o setor OFICIAL do cadastro (usado pelo guardrail de setor);
    `source` indica como a identidade foi resolvida: 'matricula', 'id_huawei',
    'filename' ou 'ai'.
    """
    operator_name: str | None = None
    id_huawei: str | None = None
    matricula: str | None = None
    db_sector: str | None = None
    source: str | None = None


# ── Identidade do operador (resolução contra o cadastro RH) ─────────────────

def _normalize_operator_identity_text(value: str | None) -> str:
    """Normaliza nome p/ comparação: minúsculo, sem acento, só [a-z0-9 ]."""
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    normalized = _re.sub(r"[^a-z0-9\s]", " ", normalized)
    return " ".join(part for part in normalized.split() if part)


def _operator_identity_tokens(value: str | None) -> list[str]:
    return [part for part in _normalize_operator_identity_text(value).split() if len(part) >= 2]


def _is_strong_operator_name(value: str | None) -> bool:
    """Nome "forte" = pelo menos nome + sobrenome (evita match por 1 token só)."""
    return len(_operator_identity_tokens(value)) >= 2


def _operator_name_matches_record(requested_name: str | None, canonical_name: str | None) -> bool:
    """Confere se o nome pedido bate com o nome canônico do cadastro.

    Exige primeiro nome idêntico e todos os tokens pedidos presentes no
    canônico — protege contra homônimos parciais (ex.: 'Maria' sozinho não casa).
    """
    requested_tokens = _operator_identity_tokens(requested_name)
    canonical_tokens = _operator_identity_tokens(canonical_name)
    if not requested_tokens or not canonical_tokens:
        return False
    if requested_tokens == canonical_tokens:
        return True
    if len(requested_tokens) < 2:
        return False
    if requested_tokens[0] != canonical_tokens[0]:
        return False
    return all(token in canonical_tokens for token in requested_tokens)


def _resolve_db_sector_alias(db_sector: str | None) -> str | None:
    """Resolve um setor cru -> canonico. Fase 2: le do DB via
    repositories.sector_aliases (setor_exact). Fallback: catalog hit + normalize.
    """
    if not db_sector:
        return None

    raw_id = str(db_sector).strip().lower()
    try:
        from repositories import sector_aliases as _sector_aliases_repo
        alias_map = _sector_aliases_repo.get_setor_exact_aliases(get_connection)
    except Exception:
        logger.warning("Falha ao carregar sector_aliases do DB; usando dict vazio.")
        alias_map = {}

    if raw_id in alias_map:
        return alias_map[raw_id]

    try:
        catalog = load_audit_criteria_catalog()
        if raw_id in catalog:
            return raw_id
    except Exception:
        pass

    normalized_db_sector = _normalize_operator_identity_text(db_sector)
    return alias_map.get(normalized_db_sector, normalized_db_sector or None)


def _buscar_colaborador_por_nome_confiavel(operator_name: str | None) -> dict | None:
    """Busca o colaborador no cadastro SÓ quando o nome é forte e o match é estrito.

    Retorna o registro RH ou None (nome fraco, não encontrado ou match ambíguo).
    """
    if not _is_strong_operator_name(operator_name):
        return None

    try:
        from repositories import operators
        rh = operators.buscar_colaborador_por_nome(get_connection, operator_name)
    except Exception as exc:
        logger.warning("Trusted operator lookup error: %s", exc)
        return None

    if not rh:
        return None

    canonical_name = rh.get("name") or operator_name
    if not _operator_name_matches_record(operator_name, canonical_name):
        logger.info(
            "Ignoring weak operator match '%s' -> '%s'",
            operator_name,
            canonical_name,
        )
        return None

    return rh


def _get_effective_db_sector(rh: dict | None) -> str | None:
    """Setor EFETIVO do colaborador: mapeia setor/escala/supervisor do RH para o
    setor de classificação (ex.: escala FÊNIX → 'fenix'; CENTRAL-* → 'transferencia')."""
    if not rh:
        return None
    try:
        from repositories import operators
        mapped = operators.map_db_sector_to_classification_sector(
            rh.get("setor") or rh.get("sector") or "",
            rh.get("escala") or "",
            rh.get("supervisor") or ""
        )
        return mapped or rh.get("setor") or rh.get("sector") or None
    except Exception as exc:
        logger.debug("Effective sector mapping error: %s", exc)
        return rh.get("setor") or rh.get("sector") or None


def resolve_operator_identity(
    ai_operator_name: str | None,
    parsed_operator_name: str | None,
    parsed_id_huawei: str | None,
    parsed_matricula: str | None = None,
) -> ResolvedOperatorIdentity:
    """Resolve a identidade do operador combinando IA + nome do arquivo + cadastro.

    Ordem de confiança: matrícula explícita > id_huawei (que pode ser uma
    matrícula disfarçada) > nome do arquivo > nome dado pela IA. Quando acha o
    colaborador no cadastro, usa o nome canônico e o setor oficial
    (`db_sector`); senão devolve só o nome "forte" disponível, sem setor.
    Só lê o banco — sem efeitos colaterais.
    """
    resolved = ResolvedOperatorIdentity(id_huawei=parsed_id_huawei, matricula=parsed_matricula)
    
    # Try looking up by matricula first if it's explicitly provided
    if parsed_matricula:
        try:
            from db.database import buscar_colaborador_por_matricula
            rh = buscar_colaborador_por_matricula(parsed_matricula)
        except Exception as exc:
            logger.warning("Trusted operator lookup by matricula error: %s", exc)
            rh = None
        if rh:
            return ResolvedOperatorIdentity(
                operator_name=rh.get("name") or None,
                id_huawei=parsed_id_huawei or rh.get("idHuawei") or rh.get("idTelefonia") or None,
                matricula=parsed_matricula or rh.get("matricula") or None,
                db_sector=_get_effective_db_sector(rh),
                source="matricula",
            )

    # Then try looking up by id_huawei (which could be the real id_huawei or a matricula in disguise)
    if parsed_id_huawei:
        try:
            from repositories import operators
            rh = operators.buscar_colaborador_por_id_huawei(get_connection, parsed_id_huawei)
            # If not found by id_huawei, try treating the huawei ID as a matricula
            if not rh:
                rh = operators.buscar_colaborador_por_matricula(get_connection, parsed_id_huawei)
        except Exception as exc:
            logger.warning("Trusted operator lookup by id_huawei/matricula fallback error: %s", exc)
            rh = None
        if rh:
            return ResolvedOperatorIdentity(
                operator_name=rh.get("name") or None,
                id_huawei=parsed_id_huawei or rh.get("idHuawei") or rh.get("idTelefonia") or None,
                matricula=rh.get("matricula") or parsed_matricula or None,
                db_sector=_get_effective_db_sector(rh),
                source="id_huawei",
            )

    candidates = (
        ("filename", parsed_operator_name),
        ("ai", ai_operator_name),
    )
    for source, candidate in candidates:
        rh = _buscar_colaborador_por_nome_confiavel(candidate)
        if not rh:
            continue
        return ResolvedOperatorIdentity(
            operator_name=rh.get("name") or candidate,
            id_huawei=resolved.id_huawei or rh.get("idHuawei") or rh.get("idTelefonia") or None,
            matricula=rh.get("matricula") or None,
            db_sector=_get_effective_db_sector(rh),
            source=source,
        )

    if _is_strong_operator_name(parsed_operator_name):
        resolved.operator_name = parsed_operator_name
        resolved.source = "filename"
    elif _is_strong_operator_name(ai_operator_name):
        resolved.operator_name = ai_operator_name
        resolved.source = "ai"

    return resolved


# ── Guardrails pós-classificação (correções determinísticas sobre a IA) ─────

def _strict_rh_sector_enforcement_enabled() -> bool:
    """Regra rígida de setor (default ON): força SEMPRE o setor oficial do
    operador no RH/matrícula, removendo a margem 'hora extra' (Guardrail D').
    Rollback: STRICT_RH_SECTOR_ENFORCEMENT=false volta ao comportamento D'.
    """
    raw = os.getenv("STRICT_RH_SECTOR_ENFORCEMENT")
    if raw is None:
        return True
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def enforce_operator_and_direction_guardrails(
    classification: dict,
    operator_name: str | None,
    *,
    db_sector: str | None = None,
    parsed_filename: Optional[FilenameParsed] = None,
) -> dict:
    """Guardrail de setor do operador (RH) + direção da ligação.

    Setor: se o operador identificado tem setor oficial no cadastro diferente
    do classificado, força o setor do RH (modo rígido, default) e tenta mapear
    o alerta para o equivalente do setor; sem equivalente, zera o alerta para
    'desconhecido' preservando `_ai_original_*` como contexto p/ o auditor.
    No modo D' (STRICT_RH_SECTOR_ENFORCEMENT=false), IA confiante
    (>= SECTOR_TRUST_CONFIDENCE) vence o cadastro (possível hora extra).

    Direção: compara a direção esperada do alerta (keyword no alert_id) com a
    classificada; divergência marca `_direction_mismatch` + motivo de revisão
    (NÃO bloqueia a auditoria). Muta e retorna o mesmo dict.
    """
    if not db_sector and operator_name:
        rh = _buscar_colaborador_por_nome_confiavel(operator_name)
        if rh:
            db_sector = rh.get("setor") or None

    sector_id = str(classification.get("sector_id", "")).strip().lower()
    resolved_db_sector = _resolve_db_sector_alias(db_sector)

    # ========================================================================
    # Estrategia D' (Hybrid + preservacao total):
    # - Caso 2 (IA confianca >= SECTOR_TRUST_CONFIDENCE): possivel hora extra
    #   do operador em outro setor. Confia na IA (sector + alerta), salva o
    #   cadastro em _operator_cadastro_sector pra auditor verificar rapido.
    # - Caso 4 (IA confianca < SECTOR_TRUST_CONFIDENCE): IA insegura, mais
    #   provavel chute. Forca setor = cadastro, tenta heuristicas pra mapear
    #   alerta; se falham, KEEP o alerta da IA original (nao zera para
    #   "desconhecido") e salva _ai_original_* pra metadata.
    # Esta abordagem nunca destroi informacao da IA — auditor sempre tem
    # contexto pra decidir.
    # ========================================================================
    try:
        confidence = float(classification.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    # Regra rigida (default): remove a margem 'hora extra' do D' — sempre forca o
    # setor oficial do RH. STRICT_RH_SECTOR_ENFORCEMENT=false volta ao D'.
    strict = _strict_rh_sector_enforcement_enabled()

    if (not strict) and resolved_db_sector and resolved_db_sector != sector_id and confidence >= SECTOR_TRUST_CONFIDENCE:
        # Caso 2 (so no modo D', strict OFF): IA confiante em setor diferente — provavel hora extra
        logger.info(
            "Guardrail: IA confiante (%.2f) classificou setor '%s' diferente do cadastro '%s' (operador '%s') — possivel hora extra. Preservando IA.",
            confidence,
            sector_id,
            resolved_db_sector,
            operator_name,
        )
        classification["_operator_cadastro_sector"] = resolved_db_sector
        _append_review_reason(
            classification,
            "setor_classificado_diferente_do_cadastro_possivel_hora_extra",
        )
        # NAO mexe em sector_id/alert_id — preserva IA
    elif resolved_db_sector and resolved_db_sector != sector_id:
        catalog = load_audit_criteria_catalog()
        sector_data = catalog.get(resolved_db_sector)
        if sector_data:
            logger.info(
                "Guardrail: forcando setor '%s' -> '%s' (operador '%s' pertence ao setor oficial %s; modo=%s, confianca IA %.2f)",
                sector_id,
                resolved_db_sector,
                operator_name,
                resolved_db_sector,
                "rigido" if strict else "D'",
                confidence,
            )
            ai_original_sector_id = sector_id
            ai_original_alert_id = classification.get("alert_id")
            ai_original_alert_label = classification.get("alert_label")

            classification["sector_id"] = resolved_db_sector
            classification["sector_label"] = str(sector_data["label"])
            _append_review_reason(classification, "verificar_setor")

            # Also fix alert_id if current alert doesn't belong to the correct sector
            current_alert = classification.get("alert_id", "")
            valid_alert_ids = {a["id"] for a in sector_data["alerts"]}

            # Apenas marcar review se o alerta original era incompativel com o
            # setor ajustado pelo RH. Se o alerta ja era compativel, a correcao
            # de setor e silenciosa (reduz volume de falsos needs_review).
            if current_alert not in valid_alert_ids:
                _append_review_reason(classification, "setor_alterado_pelo_rh")

            if current_alert not in valid_alert_ids:
                matched_new_alert = False

                # 1. Try to find matching alert by keyword from the alert hint
                if parsed_filename and parsed_filename.alert_id_hint and parsed_filename.alert_id_hint in valid_alert_ids:
                    for alert in sector_data["alerts"]:
                        if alert["id"] == parsed_filename.alert_id_hint:
                            classification["alert_id"] = parsed_filename.alert_id_hint
                            classification["alert_label"] = alert["label"]
                            matched_new_alert = True
                            break

                # 2. Preserve alert type and MOT/CLI/POLICIA suffix when the
                # operator sector changes. Example: UTI-POSICAO-MOT +
                # Distribuicao operator -> DISTRIBUICAO-POSICAO-MOT.
                if not matched_new_alert:
                    equivalent = _get_equivalent_alert_from_context(
                        resolved_db_sector,
                        current_alert,
                        alert_hint=parsed_filename.alert_hint if parsed_filename else None,
                    )
                    if equivalent:
                        _apply_alert_match(classification, equivalent)
                        matched_new_alert = True

                # 3. Try to match by alert keyword (e.g., "PARADA", "DESVIO")
                if not matched_new_alert and sector_data["alerts"]:
                    alert_hint_lower = ""
                    if parsed_filename and parsed_filename.alert_hint:
                        alert_hint_lower = parsed_filename.alert_hint.split("-")[0].lower()

                    if not alert_hint_lower and current_alert:
                        parts = current_alert.split("-")
                        if len(parts) > 1:
                            alert_hint_lower = parts[1].lower()

                    if alert_hint_lower:
                        for alert in sector_data["alerts"]:
                            if alert_hint_lower in alert["label"].lower() or alert_hint_lower in alert["id"].lower():
                                classification["alert_id"] = alert["id"]
                                classification["alert_label"] = alert["label"]
                                matched_new_alert = True
                                break

                # 4. Sem equivalente no setor oficial. Salva _ai_original_* como
                # contexto pro auditor. No modo rigido (default) zera o alerta para
                # 'desconhecido' (triagem manual) — nao mantem alerta de outro setor.
                # No modo D' (strict OFF) preserva o alerta da IA.
                if not matched_new_alert:
                    classification["_ai_original_sector_id"] = ai_original_sector_id
                    classification["_ai_original_alert_id"] = ai_original_alert_id
                    classification["_ai_original_alert_label"] = ai_original_alert_label
                    if strict:
                        classification["alert_id"] = "desconhecido"
                        classification["alert_label"] = "Sem alerta no setor oficial do operador"
                        _append_review_reason(classification, "alerta_fora_do_setor_oficial")
                    else:
                        _append_review_reason(classification, "alerta_pode_estar_no_setor_diferente")

    final_sector_id = str(classification.get("sector_id") or "").strip().lower()
    final_alert_id = str(classification.get("alert_id") or "").strip()
    expected_direction = _expected_direction_for_alert(final_alert_id)
    classified_direction = _normalize_direction_value(classification.get("direction"))

    if expected_direction and classified_direction and expected_direction != classified_direction:
        logger.info(
            "Guardrail: direction mismatch for operador '%s' (sector=%s, alert=%s, expected=%s, classified=%s)",
            operator_name,
            final_sector_id,
            final_alert_id,
            expected_direction,
            classified_direction,
        )
        classification["_direction_mismatch"] = True
        _append_review_reason(classification, "direction_mismatch")

    return classification

def normalize_classification_text(text: str) -> str:
    """Normaliza texto p/ busca de keywords: minúsculo, sem acento, espaços colapsados."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return " ".join(normalized.split())


def contains_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    """True se o texto (já normalizado) contém qualquer uma das keywords."""
    return any(keyword in text for keyword in keywords)


def infer_temperature_alert(normalized_text: str) -> tuple[str, str]:
    """Escolhe o alerta de temperatura (MOT/CLI × controle/desligamento) pelo contexto da fala."""
    is_temperature_off = contains_any_keyword(normalized_text, TEMPERATURE_OFF_KEYWORDS)
    driver_score = sum(1 for cue in DRIVER_CUES if cue in normalized_text)
    client_score = sum(1 for cue in CLIENT_CUES if cue in normalized_text)
    is_driver_context = driver_score >= client_score

    if is_driver_context and is_temperature_off:
        return TEMPERATURE_ALERTS_BY_CONTEXT["driver_shutdown"]
    if is_driver_context:
        return TEMPERATURE_ALERTS_BY_CONTEXT["driver_control"]
    if is_temperature_off:
        return TEMPERATURE_ALERTS_BY_CONTEXT["client_shutdown"]
    return TEMPERATURE_ALERTS_BY_CONTEXT["client_control"]


def _score_weighted_signals(text: str, weights: dict[str, int]) -> int:
    """Score = soma de (ocorrências do termo x peso) — base dos guardrails por keyword."""
    return sum(text.count(term) * weight for term, weight in weights.items())


def _classification_has_catalog_alert(classification: dict) -> bool:
    """True se a classificação aponta para um alerta REAL do catálogo (não desconhecido/erro)."""
    alert_id = _canonicalize_alert_id(str(classification.get("alert_id") or "").strip())
    if not alert_id or alert_id in {"INFORMATIVO", "DESCONHECIDO", "ERRO"}:
        return False
    sector_id = str(classification.get("sector_id") or "").strip().lower()
    if _get_catalog_alert(sector_id, alert_id):
        return True
    return bool(get_alert_lookup_by_id().get(alert_id))


def _is_non_auditable_like_output(classification: dict) -> bool:
    """Detecta saídas proibidas da IA tipo 'INFORMATIVO'/'Não Auditável'/'Manutenção'."""
    alert_id = _canonicalize_alert_id(str(classification.get("alert_id") or "").strip())
    alert_label = normalize_classification_text(str(classification.get("alert_label") or ""))
    combined = normalize_classification_text(f"{alert_id} {alert_label}")
    return alert_id == "INFORMATIVO" or contains_any_keyword(combined, NON_AUDITABLE_OUTPUT_KEYWORDS)


def _get_sector_alert(sector_id: str, alert_id: str) -> tuple[str, str] | None:
    """Variante de `_get_catalog_alert` que retorna só (alert_id, label)."""
    for alert in load_audit_criteria_catalog().get(sector_id, {}).get("alerts", []):
        if alert["id"] == alert_id:
            return alert_id, str(alert["label"])
    return None


def _infer_logistica_specific_alert(
    normalized_transcription: str,
    normalized_filename: str,
    actor: str,
) -> tuple[str, str] | None:
    """Detecta alertas ESPECÍFICOS de logística (espelhamento, perda de posição
    CLI, parada excessiva) por keywords — eles vencem os genéricos PARADA/DESVIO."""
    combined = f"{normalized_transcription} {normalized_filename}"
    actor = "CLI" if str(actor or "").upper() == "CLI" else "MOT"

    if "espelhamento" in combined:
        return _get_sector_alert("logistica", "LOGISTICA-VIAGEM-SEM-ESPELHAMENTO-CLI")

    position_terms = (
        "perda de posicao",
        "perdeu posicao",
        "perdeu o sinal",
        "perda de sinal",
        "sem sinal",
    )
    if actor == "CLI" and any(term in combined for term in position_terms):
        return _get_sector_alert("logistica", "LOGISTICA-PERDA-POSICAO-CLI")

    parada_excessiva_terms = (
        "parada excessiva",
        "parado a tanto tempo",
        "parado ha tanto tempo",
        "parado por muito tempo",
        "previsao de reiniciar",
        "reinicio da viagem",
        "reiniciar a viagem",
    )
    if any(term in combined for term in parada_excessiva_terms):
        target = (
            "LOGISTICA-PARADA-EXCESSIVA-CLI"
            if actor == "CLI"
            else "LOGISTICA-PARADA-EXCESSIVA-MOT"
        )
        return _get_sector_alert("logistica", target)

    return None


def enforce_alert_hierarchy_guardrail(classification: dict, transcription: str, filename: str) -> dict:
    """Guardrail de hierarquia: alertas críticos vencem alertas menores.

    Pontua sinais de POLÍCIA > PRIORITÁRIO (violação/pânico) > POSIÇÃO na
    transcrição (nome do arquivo só como apoio fraco) e força o alerta
    equivalente do setor quando o score passa do limiar. Muta e retorna o dict.
    """
    sector_id = str(classification.get("sector_id", "")).strip().lower()
    current_alert_id = _canonicalize_alert_id(str(classification.get("alert_id", "")).strip())
    normalized_transcription = normalize_classification_text(transcription)
    normalized_filename = normalize_classification_text(filename)
    actor = _infer_alert_actor_suffix(current_alert_id, filename, transcription)

    position_score = _score_weighted_signals(normalized_transcription, POSITION_SIGNAL_WEIGHTS)
    priority_score = _score_weighted_signals(normalized_transcription, PRIORITY_SIGNAL_WEIGHTS)
    police_score = _score_weighted_signals(normalized_transcription, POLICE_SIGNAL_WEIGHTS)

    # The spoken content has precedence. Filename acts only as a weak support signal.
    position_score += _score_weighted_signals(normalized_filename, {"posicao": 1, "sinal": 1})
    priority_score += _score_weighted_signals(normalized_filename, {"prioritario": 1, "violacao": 1})
    police_score += _score_weighted_signals(normalized_filename, {"policia": 2, "policial": 2})

    forced_alert: tuple[str, str] | None = None
    forced_sector_id = sector_id
    if sector_id in _OPERATIONAL_SECTORS:
        if police_score >= 5:
            forced_match = _get_equivalent_alert_for_sector(sector_id, "PRIORITARIO-POLICIA", actor=actor)
        elif priority_score >= 5:
            forced_match = _get_equivalent_alert_for_sector(sector_id, "PRIORITARIO", actor=actor)
        elif position_score >= 4:
            forced_match = _get_equivalent_alert_for_sector(sector_id, "POSICAO", actor=actor)
        else:
            forced_match = None
        if forced_match:
            forced_sector_id, forced_alert_id, forced_alert_label = forced_match
            forced_alert = (forced_alert_id, forced_alert_label)
    elif sector_id == "logistica":
        forced_alert = _infer_logistica_specific_alert(
            normalized_transcription,
            normalized_filename,
            actor,
        )
        if not forced_alert and position_score >= 4:
            forced_alert = _get_sector_alert(
                sector_id,
                "LOGISTICA-PERDA-POSICAO-CLI" if actor == "CLI" else "LOGISTICA-POSICAO",
            )

    if not forced_alert:
        return classification

    forced_alert_id, forced_alert_label = forced_alert
    if current_alert_id == forced_alert_id:
        return classification

    if forced_sector_id != sector_id:
        catalog = load_audit_criteria_catalog()
        classification["sector_id"] = forced_sector_id
        classification["sector_label"] = str(catalog.get(forced_sector_id, {}).get("label") or forced_sector_id)

    classification["alert_id"] = forced_alert_id
    classification["alert_label"] = forced_alert_label
    return classification


def enforce_parada_desvio_guardrail(classification: dict, transcription: str, filename: str) -> dict:
    """Desempata PARADA × DESVIO pela ênfase da fala (regra 15 do prompt).

    Só age com evidência forte (score >= 4) e diferença clara (gap >= 2);
    se o alerta atual nem é de parada/desvio, exige score ainda maior (>= 6)
    para sobrescrever. Muta e retorna o dict.
    """
    sector_id = str(classification.get("sector_id", "")).strip().lower()
    current_alert_id = str(classification.get("alert_id", "")).strip()
    if sector_id not in {"logistica", *_OPERATIONAL_SECTORS}:
        return classification

    normalized_transcription = normalize_classification_text(transcription)
    normalized_filename = normalize_classification_text(filename)
    actor = _infer_alert_actor_suffix(current_alert_id, filename, transcription)

    parada_score = _score_weighted_signals(normalized_transcription, PARADA_SIGNAL_WEIGHTS)
    desvio_score = _score_weighted_signals(normalized_transcription, DESVIO_SIGNAL_WEIGHTS)

    parada_score += _score_weighted_signals(normalized_filename, {"parada": 1})
    desvio_score += _score_weighted_signals(normalized_filename, {"desvio": 1, "rota": 1})

    strongest_score = max(parada_score, desvio_score)
    score_gap = abs(parada_score - desvio_score)
    if strongest_score < 4 or score_gap < 2:
        return classification

    if sector_id == "logistica":
        forced_alert = None
        if parada_score > desvio_score:
            forced_alert = _infer_logistica_specific_alert(
                normalized_transcription,
                normalized_filename,
                actor,
            )
            if forced_alert and not forced_alert[0].startswith("LOGISTICA-PARADA-EXCESSIVA"):
                forced_alert = None
        if not forced_alert:
            forced_alert = _get_sector_alert(sector_id, "LOGISTICA-PARADA" if parada_score > desvio_score else "LOGISTICA-DESVIO")
    else:
        forced_match = _get_equivalent_alert_for_sector(
            sector_id,
            "PARADA" if parada_score > desvio_score else "DESVIO",
            actor=actor,
        )
        forced_alert = (forced_match[1], forced_match[2]) if forced_match else None
    
    if not forced_alert:
        return classification

    forced_alert_id, forced_alert_label = forced_alert
    if current_alert_id == forced_alert_id:
        return classification

    if current_alert_id not in PARADA_DESVIO_ALERT_IDS and strongest_score < 6:
        return classification

    classification["alert_id"] = forced_alert_id
    classification["alert_label"] = forced_alert_label
    return classification


def enforce_context_not_non_auditable_guardrail(classification: dict, transcription: str, filename: str) -> dict:
    """Manutenção/oficina é CONTEXTO da ligação, nunca alerta final não-auditável.

    Quando a IA devolve 'INFORMATIVO'/'Manutenção' (saída proibida) ou há
    contexto de manutenção/estadia sem alerta de catálogo, tenta inferir o
    alerta real pelos scores de keywords; se nada casa, marca 'desconhecido'
    com confiança <= 0.49 (vai para triagem manual). Muta e retorna o dict.
    """

    if _classification_has_catalog_alert(classification) and not _is_non_auditable_like_output(classification):
        return classification

    normalized_transcription = normalize_classification_text(transcription)
    normalized_filename = normalize_classification_text(filename)
    combined = f"{normalized_filename} {normalized_transcription}"
    has_maintenance_context = contains_any_keyword(combined, MAINTENANCE_CONTEXT_KEYWORDS)
    has_stadia_context = contains_any_keyword(combined, STADIA_CONTEXT_KEYWORDS)
    non_auditable_like = _is_non_auditable_like_output(classification)

    if not has_maintenance_context and not has_stadia_context and not non_auditable_like:
        return classification

    catalog = load_audit_criteria_catalog()
    sector_id = str(classification.get("sector_id") or "").strip().lower()
    if sector_id not in catalog:
        parsed = parse_filename(filename) if filename else None
        if parsed and parsed.sector_hint in catalog:
            sector_id = parsed.sector_hint
            classification["sector_id"] = sector_id
            classification["sector_label"] = str(catalog[sector_id]["label"])
            _append_review_reason(classification, "setor_inferido_pelo_filename")

    actor = _infer_alert_actor_suffix(classification.get("alert_id"), filename, transcription)
    police_score = _score_weighted_signals(normalized_transcription, POLICE_SIGNAL_WEIGHTS)
    priority_score = _score_weighted_signals(normalized_transcription, PRIORITY_SIGNAL_WEIGHTS)
    position_score = _score_weighted_signals(normalized_transcription, POSITION_SIGNAL_WEIGHTS)
    parada_score = _score_weighted_signals(normalized_transcription, PARADA_SIGNAL_WEIGHTS)
    desvio_score = _score_weighted_signals(normalized_transcription, DESVIO_SIGNAL_WEIGHTS)

    forced_match: tuple[str, str, str] | None = None
    if sector_id in catalog:
        if police_score >= 3:
            forced_match = _get_equivalent_alert_for_sector(sector_id, "PRIORITARIO-POLICIA", actor=actor)
        elif priority_score >= 3:
            forced_match = _get_equivalent_alert_for_sector(sector_id, "PRIORITARIO", actor=actor)
        elif position_score >= 4:
            forced_match = _get_equivalent_alert_for_sector(sector_id, "POSICAO", actor=actor)
        elif sector_id == "logistica" and has_stadia_context:
            forced_match = _get_catalog_alert("logistica", "LOGISTICA-ESTADIA")
        elif parada_score >= 2 and parada_score >= desvio_score:
            forced_match = _get_equivalent_alert_for_sector(sector_id, "PARADA", actor=actor)
        elif desvio_score >= 3:
            forced_match = _get_equivalent_alert_for_sector(sector_id, "DESVIO", actor=actor)

    if forced_match:
        classification = _apply_alert_match(classification, forced_match)
        try:
            confidence = float(classification.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        classification["confidence"] = max(confidence, 0.82)
        return classification

    if non_auditable_like or has_maintenance_context:
        classification["alert_id"] = "desconhecido"
        classification["alert_label"] = "Nao Identificado"
        _append_review_reason(classification, "contexto_operacional_sem_alerta_identificado")
        try:
            confidence = float(classification.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        classification["confidence"] = min(confidence, 0.49)
    return classification


def enforce_temperature_guardrail(classification: dict, transcription: str, filename: str) -> dict:
    """Contexto de temperatura (setpoint, baú refrigerado...) força setor
    logística + alerta de temperatura adequado (MOT/CLI × controle/desligamento)."""
    normalized_text = normalize_classification_text(f"{filename} {transcription}")
    has_temperature_context = contains_any_keyword(normalized_text, TEMPERATURE_KEYWORDS)
    if not has_temperature_context:
        return classification

    sector_id = str(classification.get("sector_id", "")).strip().lower()
    alert_id = _canonicalize_alert_id(str(classification.get("alert_id", "")).strip())
    forced_alert_id, forced_alert_label = infer_temperature_alert(normalized_text)
    has_valid_temperature_classification = sector_id == "logistica" and alert_id in TEMPERATURE_ALERT_IDS
    if has_valid_temperature_classification and alert_id == forced_alert_id:
        return classification
    classification["sector_id"] = "logistica"
    classification["sector_label"] = "Logística Opentech"
    classification["alert_id"] = forced_alert_id
    classification["alert_label"] = forced_alert_label

    try:
        confidence = float(classification.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    classification["confidence"] = max(confidence, 0.82)
    return classification

# ── Transcrição leve para triagem (custo reduzido por design) ───────────────
TRIAGE_MAX_AUDIO_SECONDS = 90


async def transcribe_for_classification(audio_bytes: bytes, mime_type: str) -> str:
    """Transcrição leve dedicada à triagem (NÃO é a transcrição da auditoria).

    Por quê: triagem só precisa do tópico (setor/alerta), não de diarização
    perfeita. Usar o pipeline completo (hybrid_dual + merge GPT-4o — legado)
    levava 4-5 min por ligação, estourava o timeout do front e gerava
    'alert=erro'. Trunca para ~90s para passar a URA inicial.

    CUSTO: 1 chamada paga por tentativa, em cascata de fallback:
    Whisper → GPT-4o-diarize → Azure Fast Transcription. Levanta exceção se
    os três motores falharem.
    """
    from core.transcription import transcribe_audio_azure, transcribe_audio_gpt4o_diarize
    from core.config import _resolve_azure_whisper_config, _resolve_azure_gpt4o_diarize_config

    truncated = await asyncio.to_thread(truncate_audio, audio_bytes, TRIAGE_MAX_AUDIO_SECONDS)
    triage_mime = "audio/wav" if truncated.startswith(b"RIFF") else mime_type

    last_error: Exception | None = None

    whisper_endpoint, whisper_key = _resolve_azure_whisper_config()
    if whisper_endpoint and whisper_key:
        try:
            logger.info("[Triagem] Transcrevendo via Whisper (truncado a %ss)", TRIAGE_MAX_AUDIO_SECONDS)
            segments = await asyncio.to_thread(
                transcribe_audio_azure,
                truncated,
                "Operador",
                "Motorista",
                None,
                None,
                triage_mime,
                endpoint_override=whisper_endpoint,
                api_key_override=whisper_key,
            )
            return " ".join(seg.get("text", "") for seg in segments).strip()
        except Exception as exc:
            last_error = exc
            logger.warning("[Triagem] Whisper falhou, tentando GPT-4o-diarize: %s", exc)

    diarize_endpoint, diarize_key = _resolve_azure_gpt4o_diarize_config()
    if diarize_endpoint and diarize_key:
        try:
            logger.info("[Triagem] Transcrevendo via GPT-4o-diarize (fallback)")
            segments = await asyncio.to_thread(
                transcribe_audio_gpt4o_diarize,
                truncated,
                triage_mime,
                "Operador",
                "Motorista",
                endpoint_override=diarize_endpoint,
                api_key_override=diarize_key,
            )
            return " ".join(seg.get("text", "") for seg in segments).strip()
        except Exception as exc:
            last_error = exc
            logger.warning("[Triagem] GPT-4o-diarize falhou, tentando Azure Fast: %s", exc)

    try:
        logger.info("[Triagem] Transcrevendo via Azure Fast Transcription (ultimo recurso)")
        segments = await asyncio.to_thread(
            transcribe_audio_azure,
            truncated,
            "Operador",
            "Motorista",
            None,
            None,
            triage_mime,
        )
        return " ".join(seg.get("text", "") for seg in segments).strip()
    except Exception as exc:
        last_error = exc
        logger.error("[Triagem] Azure Fast tambem falhou: %s", exc)

    raise Exception(f"Todos os motores de triagem falharam: {last_error}")

async def transcribe_for_classification_ai(audio_bytes: bytes, mime_type: str) -> str:
    """Transcrição de triagem via provedor de IA alternativo (`ai_client`, ex.: Gemini).

    Só usada quando `AI_PROVIDER_PRIORITY` não é 'azure'. CUSTO: 1 chamada paga
    ao provedor alternativo com o áudio truncado.
    """
    try:
        truncated_audio = await asyncio.to_thread(truncate_audio, audio_bytes, MAX_AUDIO_DURATION_SECONDS)
        final_mime = mime_type
        if truncated_audio.startswith(b'RIFF'): final_mime = "audio/wav"
        prompt = "Transcreva este áudio para fins de classificação. Responda apenas com o texto da transcrição. Transcreva exatamente o que foi falado. Se houver repetições na fala, transcreva as repetições também, mas NÃO invente ou alucine texto que não existe. Se não conseguir identificar alguma palavra ou trecho, escreva exclusivamente '[Inaudível]'."
        from google.genai import types  # lazy: evita google.genai no boot do servidor
        response = await asyncio.to_thread(ai_client.models.generate_content, model=AI_MODEL, contents=[prompt, types.Part.from_bytes(data=truncated_audio, mime_type=final_mime)])
        return response.text
    except Exception as e: logger.exception("AI transcription error: %s", e); raise

def _build_filename_hints(filename: str) -> str:
    """Build a structured hint block from deterministic filename parsing."""
    parsed = parse_filename(filename)
    lines: list[str] = []
    if parsed.operator_name:
        lines.append(f"OPERADOR DETECTADO NO ARQUIVO: {parsed.operator_name}")
    if parsed.sector_hint:
        catalog = load_audit_criteria_catalog()
        sector_data = catalog.get(parsed.sector_hint)
        label = str(sector_data["label"]) if sector_data else parsed.sector_hint
        lines.append(f"SETOR DETECTADO NO ARQUIVO: {parsed.sector_hint} ({label})")
    if parsed.alert_id_hint:
        alert_info = get_alert_lookup_by_id().get(parsed.alert_id_hint)
        if alert_info:
            lines.append(f"ALERTA SUGERIDO: {parsed.alert_id_hint} ({alert_info[2]})")
    if parsed.alert_hint:
        lines.append(f"TIPO DE ALERTA NO ARQUIVO: {parsed.alert_hint}")
    if lines:
        return "PISTAS EXTRAÍDAS DO NOME DO ARQUIVO (use como referência forte):\n" + "\n".join(lines)
    return ""


# ── Entrada principal: transcrição de triagem → classificação IA → guardrails ──
# classify_audio é a porta de entrada; classify_with_gpt/classify_with_ai são as
# rotas de provedor de IA (Azure é o caminho de produção, ver AI_PROVIDER_PRIORITY).
async def classify_with_gpt(transcription: str, filename: str = "") -> dict:
    """Classifica a transcrição de triagem via Azure OpenAI (rota de produção).

    Produz o dict de classificação (setor/alerta/operador/confiança). Cada chamada
    é paga (GPT-4o) e registrada no cost_guard. `classify_with_ai` é a rota gêmea
    para o provedor alternativo — mesmo formato de dict de saída.
    """
    if not AZURE_OPENAI_KEY: raise ValueError("Azure OpenAI key not configured")
    from openai import AsyncAzureOpenAI
    client = AsyncAzureOpenAI(
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_KEY,
        api_version="2025-01-01-preview"
    )
    # Get classification feedback (com RAG semântico quando possível)
    feedback_calibration = ""
    try:
        from core.ai_feedback import get_feedback_for_prompt
        # Gerar embedding da transcrição para busca semântica
        query_embedding = None
        try:
            from core.rag_triagem import gerar_embedding
            query_embedding = await asyncio.to_thread(gerar_embedding, transcription)
        except Exception as emb_exc:
            logger.debug("RAG embedding skip: %s", emb_exc)
        feedback_calibration = await asyncio.to_thread(
            get_feedback_for_prompt,
            tipos={"classificacao", "regra_geral"},
            query_embedding=query_embedding,
        )
    except Exception as exc:
        logger.warning("Failed to load classification feedback: %s", exc)

    prompt = CLASSIFICATION_PROMPT.format(
        sectors_and_alerts=build_sectors_and_alerts_prompt(),
        transcription=transcription,
        filename=filename,
        filename_hints=_build_filename_hints(filename),
        known_operators=get_operators_summary_for_prompt(),
        feedback_calibration=feedback_calibration,
    )
    try:
        cost_guard.record_call(cost_guard.PROVIDER_AZURE_OPENAI, "classificacao")
        response = await client.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "Você é um classificador de ligações. Responda apenas com JSON válido."},
                {"role": "user", "content": prompt}
            ],
            temperature=0,
            max_tokens=500,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        classification = json.loads(content)
        # Logar e remover campos de Chain of Thought
        for key in ("raciocinio_situacao", "raciocinio_regras"):
            value = classification.pop(key, None)
            if value:
                logger.info("CoT [%s]: %s", key, value)
        # Normalizar confidence para float
        conf = classification.get("confidence")
        if isinstance(conf, str):
            try:
                classification["confidence"] = float(conf)
            except ValueError:
                classification["confidence"] = 0.0
        return classification
    except Exception as e:
        import openai
        if isinstance(e, openai.APIError):
            logger.error("Azure OpenAI API Error: %s", e)
            raise Exception(f"Azure API error: {e}")
        raise Exception(f"Azure API error: {e}")

async def classify_with_ai(transcription: str, filename: str = "") -> dict:
    """Classifica via provedor de IA alternativo (ex.: Gemini), espelhando classify_with_gpt.

    Mesmo prompt + feedback RAG e mesmo formato de dict de saída; a rota é escolhida
    por AI_PROVIDER_PRIORITY (produção usa Azure via classify_with_gpt). A diferença
    real é o client e o parsing do JSON (Azure usa response_format json_object; aqui
    há fallback por regex).
    """
    try:
        # Get classification feedback (com RAG semântico quando possível)
        feedback_calibration = ""
        try:
            from core.ai_feedback import get_feedback_for_prompt
            # Gerar embedding da transcrição para busca semântica
            query_embedding = None
            try:
                from core.rag_triagem import gerar_embedding
                query_embedding = await asyncio.to_thread(gerar_embedding, transcription)
            except Exception as emb_exc:
                logger.debug("RAG embedding skip: %s", emb_exc)
            feedback_calibration = await asyncio.to_thread(
                get_feedback_for_prompt,
                tipos={"classificacao", "regra_geral"},
                query_embedding=query_embedding,
            )
        except Exception as exc:
            logger.warning("Failed to load classification feedback: %s", exc)

        prompt = CLASSIFICATION_PROMPT.format(
            sectors_and_alerts=build_sectors_and_alerts_prompt(),
            transcription=transcription,
            filename=filename,
            filename_hints=_build_filename_hints(filename),
            known_operators=get_operators_summary_for_prompt(),
            feedback_calibration=feedback_calibration,
        )
        response = await asyncio.to_thread(ai_client.models.generate_content, model=AI_MODEL, contents=[prompt])
        text = response.text
        try:
            clean_text = text.replace("```json", "").replace("```", "").strip()
            classification = json.loads(clean_text)
        except Exception:
            match = _re.search(r'\{[^{}]*\}', text, _re.DOTALL)
            if match:
                classification = json.loads(match.group())
            else:
                raise ValueError(f"Could not parse classification: {text}")
        # Logar e remover campos de Chain of Thought
        for key in ("raciocinio_situacao", "raciocinio_regras"):
            value = classification.pop(key, None)
            if value:
                logger.info("CoT [%s]: %s", key, value)
        # Normalizar confidence para float
        conf = classification.get("confidence")
        if isinstance(conf, str):
            try:
                classification["confidence"] = float(conf)
            except ValueError:
                classification["confidence"] = 0.0
        return classification
    except Exception as e: logger.exception("AI classification error: %s", e); raise

async def classify_audio(audio_bytes: bytes, filename: str) -> ClassificationResult:
    """Entrada principal da triagem: do áudio ao ClassificationResult finalizado.

    Etapas: (1) transcreve para triagem (provider priority); (2) classifica via IA
    (classify_with_gpt); (3) alinha com o catálogo oficial; (4) aplica a cadeia de
    guardrails (conteúdo → identidade do operador → fallback por nome do arquivo) e
    finaliza. NÃO levanta para o caller normal: erros viram um ClassificationResult
    com sector_id='erro' (via finalize_classification_result).
    """
    transcription = ""; mime_type = get_mime_type(filename)

    # 1. Transcription with provider priority
    if AI_PROVIDER_PRIORITY == "azure" and AZURE_SPEECH_KEY:
        transcription = await transcribe_for_classification(audio_bytes, mime_type)
        if not transcription:
            raise Exception("Azure transcription returned empty")
    elif AI_PROVIDER_PRIORITY == "azure":
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id="erro",
                sector_label="Erro",
                alert_id="erro",
                alert_label="Azure Speech não configurado",
                confidence=0.0,
                error="AZURE_SPEECH_KEY missing",
            )
        )
    else:
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id="erro",
                sector_label="Erro",
                alert_id="erro",
                alert_label="IA desativada",
                confidence=0.0,
                error="User disabled AI provider",
            )
        )

    if not transcription or len(transcription.strip()) < 10:
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id="desconhecido",
                sector_label="Não Identificado",
                alert_id="desconhecido",
                alert_label="Áudio curto/sem fala",
                confidence=0.0,
                error="Short transcription",
            )
        )

    # 2. Classification with provider priority
    if AI_PROVIDER_PRIORITY == "azure" and AZURE_OPENAI_KEY:
        classification = await classify_with_gpt(transcription, filename)
    elif AI_PROVIDER_PRIORITY == "azure":
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id="erro",
                sector_label="Erro",
                alert_id="erro",
                alert_label="Azure OpenAI não configurado",
                confidence=0.0,
                error="AZURE_OPENAI_KEY missing",
            )
        )
    else:
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id="erro",
                sector_label="Erro",
                alert_id="erro",
                alert_label="IA desativada",
                confidence=0.0,
                error="User disabled AI provider",
            )
        )

    classification["_filename"] = filename
    classification = align_classification_with_catalog(classification)
    classification.pop("_filename", None)  # clean up internal key
    # A ORDEM desta cadeia é load-bearing (não reordenar sem revalidar):
    # 1) guardrails de CONTEÚDO — temperatura (força logística) → hierarquia de
    #    alerta crítico → parada/desvio → contexto-não-auditável; em seguida
    # 2) IDENTIDADE do operador, que resolve o cadastro e pode FORÇAR o setor
    #    oficial do RH (remapeando o alerta); por fim
    # 3) FALLBACK por sector_hint do nome do arquivo, só se o setor permaneceu
    #    'desconhecido' depois de tudo.
    classification = enforce_temperature_guardrail(classification, transcription, filename)
    classification = enforce_alert_hierarchy_guardrail(classification, transcription, filename)
    classification = enforce_parada_desvio_guardrail(classification, transcription, filename)
    classification = enforce_context_not_non_auditable_guardrail(classification, transcription, filename)

    # Operator sector guardrail: fix BAS/UTI/transferência confusion
    parsed = parse_filename(filename)
    resolved_operator = await asyncio.to_thread(
        resolve_operator_identity,
        classification.get("operator_name"),
        parsed.operator_name,
        parsed.id_huawei,
    )
    final_operator = resolved_operator.operator_name
    final_id_huawei = resolved_operator.id_huawei
    final_matricula = resolved_operator.matricula
    db_sector = resolved_operator.db_sector
    classification["operator_name"] = final_operator
    if final_operator or db_sector:
        classification = await asyncio.to_thread(
            enforce_operator_and_direction_guardrails,
            classification,
            final_operator,
            db_sector=db_sector,
            parsed_filename=parsed,
        )

    if classification.get("sector_id") in {"desconhecido", "erro", "", None} and parsed.sector_hint:
        catalog = load_audit_criteria_catalog()
        sector_data = catalog.get(parsed.sector_hint)
        if sector_data:
            classification["sector_id"] = parsed.sector_hint
            classification["sector_label"] = str(sector_data["label"])
            if parsed.alert_id_hint:
                for alert in sector_data["alerts"]:
                    if alert["id"] == parsed.alert_id_hint:
                        classification["alert_id"] = parsed.alert_id_hint
                        classification["alert_label"] = alert["label"]
                        break

    return finalize_classification_result(
        ClassificationResult(
            filename=filename,
            sector_id=classification.get("sector_id", "desconhecido"),
            sector_label=classification.get("sector_label", "Não Identificado"),
            alert_id=classification.get("alert_id", "desconhecido"),
            alert_label=classification.get("alert_label", "Não Identificado"),
            confidence=float(classification.get("confidence", 0.0)),
            operator_name=final_operator,
            direction=classification.get("direction"),
            id_huawei=final_id_huawei,
            matricula=final_matricula,
            direction_mismatch=classification.get("_direction_mismatch", False),
            review_reasons=classification.get("review_reasons", [])
        )
    )

async def _safe_classify_audio(audio_bytes: bytes, filename: str) -> ClassificationResult:
    try:
        return await classify_audio(audio_bytes, filename)
    except Exception as exc:
        logger.exception("AI classification error for %s: %s", filename, exc)
        return finalize_classification_result(
            ClassificationResult(
                filename=filename,
                sector_id="erro",
                sector_label="Erro",
                alert_id="erro",
                alert_label=f"Falha na IA ({type(exc).__name__})",
                confidence=0.0,
                error=str(exc),
            )
        )

async def classify_multiple_audios(files: list[tuple[str, bytes]]) -> list[ClassificationResult]:
    if len(files) > MAX_FILES_PER_REQUEST: raise ValueError(f"Max {MAX_FILES_PER_REQUEST} files")
    tasks = [_safe_classify_audio(audio_bytes, filename) for filename, audio_bytes in files]
    return list(await asyncio.gather(*tasks, return_exceptions=False))

def clear_classification_caches() -> None:
    """Clear all classification caches to allow hot reloading of scoring rules."""
    load_audit_criteria_catalog.cache_clear()
    build_sectors_and_alerts_prompt.cache_clear()
    get_alert_lookup_by_id.cache_clear()
