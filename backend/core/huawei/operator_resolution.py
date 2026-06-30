"""Resolução de operador a partir da interação Huawei (matching + verdade do cadastro).

Identifica o operador de uma chamada (por id_huawei ou por nome), monta os índices
de busca, deriva o setor canônico e injeta a "verdade" do cadastro na interação.
Determinístico: lê só o dict da interação/operador e o cadastro via
`repositories.operators` (sem rede). Extraído de `core.huawei_sync`, que reexporta
todos estes nomes p/ compat (callers internos + sync_triagem/sync_enqueue/
sync_classification/audit_actions/automation_engine + chamadas em test_huawei_sync).
"""
import logging
from typing import Optional

from core.huawei_direction import (
    NON_TELEFONIA_SECTORS,
    OUTBOUND_ONLY_RISK_SECTORS,
    normalize_huawei_sector,
)
from core.huawei.download_candidates import (
    _clean_huawei_operator_id,
    _normalize_identity_text,
)
from repositories import operators

logger = logging.getLogger(__name__)

# Aliases locais (mesmo conjunto de core.huawei_direction) — preservam o corpo de
# _operator_sector_id idêntico ao original de huawei_sync.
_AUDIO_DIRECTION_GATE_SECTORS = OUTBOUND_ONLY_RISK_SECTORS
_NON_TELEFONIA_SECTORS = NON_TELEFONIA_SECTORS


def _normalize_setor_regra(raw_setor: str) -> str:
    return normalize_huawei_sector(raw_setor)


def _operator_sector_id(operador: dict) -> str:
    raw_setor = str(
        operador.get("setor")
        or operador.get("sectorId")
        or operador.get("displaySector")
        or operador.get("sector")
        or ""
    ).strip()
    escala = str(operador.get("escala") or "").strip()
    supervisor = str(operador.get("supervisor") or "").strip()
    raw_sector_slug = _normalize_setor_regra(raw_setor)
    if raw_sector_slug in _AUDIO_DIRECTION_GATE_SECTORS or raw_sector_slug in _NON_TELEFONIA_SECTORS:
        return raw_sector_slug

    mapped_sector: Optional[str] = None
    try:
        mapped_sector = operators.map_db_sector_to_classification_sector(
            raw_setor,
            escala,
            supervisor,
        )
    except Exception:
        logger.debug("Sync Huawei: falha ao mapear setor do operador.", exc_info=True)
    return _normalize_setor_regra(mapped_sector or raw_setor)


def _build_operator_indexes(operadores: list[dict]) -> tuple[dict[str, dict], dict[str, dict]]:
    by_id: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for operador in operadores:
        operador.setdefault("huawei_registered", True)
        for value in (
            operador.get("id_huawei"),
            operador.get("idHuawei"),
        ):
            text = _clean_huawei_operator_id(value)
            if text:
                by_id.setdefault(text, operador)
                by_id.setdefault(text.lower(), operador)
        name_key = _normalize_identity_text(operador.get("nome") or operador.get("name"))
        if name_key:
            by_name.setdefault(name_key, operador)
    return by_id, by_name

def _resolve_huawei_operator_id(interacao: dict) -> str:
    for key in (
        "agent_id",
        "agentId",
        "agentid",
        "workNo",
        "work_no",
        "operatorId",
        "operator_id",
    ):
        raw_val = interacao.get(key)
        if raw_val is not None:
            value = _clean_huawei_operator_id(raw_val)
            if value:
                return value
    return ""

def _resolve_operador_interacao(
    interacao: dict,
    by_id: dict[str, dict],
    by_name: dict[str, dict],
) -> dict:
    operator_id = _resolve_huawei_operator_id(interacao)
    if operator_id:
        operador = by_id.get(operator_id) or by_id.get(operator_id.lower())
        if operador:
            resolved = dict(operador)
            resolved["huawei_registered"] = True
            resolved["huawei_match_source"] = "id_huawei"
            resolved["huawei_call_operator_id"] = operator_id
            return resolved

    for value in (
        interacao.get("operatorName"),
        interacao.get("countName"),
        interacao.get("agentName"),
    ):
        name_key = _normalize_identity_text(value)
        if name_key and name_key in by_name:
            matched = by_name[name_key]
            operator_name = (
                interacao.get("operatorName")
                or interacao.get("countName")
                or interacao.get("agentName")
                or matched.get("nome")
                or "Nao Identificado"
            )
            from utils.text_processing import format_pt_br_name

            matched_huawei_id = _clean_huawei_operator_id(
                matched.get("id_huawei")
                or matched.get("idHuawei")
                or matched.get("id_telefonia")
                or matched.get("idTelefonia")
            )

            # Nome sozinho serve para diagnóstico, mas não autoriza download nem
            # altera o cadastro: a prova forte é o ID Huawei da chamada.
            return {
                "id": matched.get("id"),
                "nome": matched.get("nome") or matched.get("name") or format_pt_br_name(str(operator_name).strip()),
                "supervisor": matched.get("supervisor"),
                "setor": matched.get("setor"),
                "escala": matched.get("escala"),
                "matricula": matched.get("matricula"),
                "id_huawei": operator_id,
                "id_telefonia": operator_id,
                "auditavel_db": False,
                "huawei_registered": False,
                "huawei_match_source": "name_only",
                "matched_operator_id_huawei": matched_huawei_id,
            }

    operator_name = (
        interacao.get("operatorName")
        or interacao.get("countName")
        or interacao.get("agentName")
        or "Nao Identificado"
    )
    from utils.text_processing import format_pt_br_name
    return {
        "nome": format_pt_br_name(str(operator_name or "Nao Identificado").strip() or "Nao Identificado"),
        "id_huawei": str(operator_id or "").strip(),
        "id_telefonia": str(operator_id or "").strip(),
        "setor": "",
        "escala": "",
        "matricula": "",
        "auditavel_db": False,
        "huawei_registered": False,
        "huawei_match_source": "none",
    }


def _operator_field(operador: dict, *keys: str) -> str:
    for key in keys:
        value = str(operador.get(key) or "").strip()
        if value:
            return value
    return ""

def _operator_truth_snapshot(operador: dict) -> dict[str, str]:
    id_huawei = _operator_field(operador, "id_huawei", "idHuawei")
    return {
        "nome": _operator_field(operador, "nome", "name"),
        "setor": _operator_field(operador, "setor", "displaySector", "sector", "sectorId"),
        "setor_id": _operator_sector_id(operador),
        "escala": _operator_field(operador, "escala"),
        "matricula": _operator_field(operador, "matricula"),
        "id_huawei": id_huawei,
    }

def _inject_operator_truth(interacao: dict, operador: dict) -> dict[str, str]:
    truth = _operator_truth_snapshot(operador)
    interacao["operatorNameResolved"] = truth["nome"]
    interacao["operatorSectorResolved"] = truth["setor"]
    interacao["operatorSectorIdResolved"] = truth["setor_id"]
    interacao["operatorScaleResolved"] = truth["escala"]
    interacao["operatorMatriculaResolved"] = truth["matricula"]
    interacao["operatorIdHuaweiResolved"] = truth["id_huawei"]
    return truth
