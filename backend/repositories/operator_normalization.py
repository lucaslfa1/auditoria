"""Helpers puros de normalização/parsing de colaboradores (operadores).

Funções determinísticas extraídas de `repositories.operators` para legibilidade:
não acessam banco, rede nem IA, não leem variáveis de ambiente e não mantêm
estado de módulo. Recebem dados (texto cru ou uma row do banco) e devolvem o
valor normalizado/derivado.

`repositories.operators` reexporta todos estes nomes, então qualquer caller ou
teste que use `operators.<helper>` continua resolvendo sem alteração.

Dependências externas (estáveis, sem ciclo de import):
- `normalize_huawei_agent_id` (`repositories.common`)
- `is_technical_telephony_values` / `is_excluded_operation_values` (`core.operator_filters`)
"""
import unicodedata
from typing import Optional

from core.operator_filters import (
    is_excluded_operation_values,
    is_technical_telephony_values,
)
from repositories.common import normalize_huawei_agent_id


def _normalize_lookup_text(value: str) -> str:
    cleaned = str(value or "").replace("\xad", "").strip().lower()
    normalized = unicodedata.normalize("NFD", cleaned)
    res = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return res.replace("logiistica", "logistica").replace("logstica", "logistica")


def _map_status_telefonia_to_status(status_telefonia: str) -> str:
    normalized_status = _normalize_lookup_text(status_telefonia)
    if normalized_status in {"normal", "ativo", "active"}:
        return "ATIVO"
    if normalized_status:
        return "INATIVO"
    return "ATIVO"


def _is_active_status(status: str) -> bool:
    return _normalize_lookup_text(status) in {"", "ativo", "active", "normal"}


def _default_auditavel_from_status(status: str) -> int:
    return 1 if _is_active_status(status) else 0


def _is_auditable_row(row) -> bool:
    if "auditavel" not in row.keys():
        return True
    value = row["auditavel"]
    if value is None:
        return True
    if isinstance(value, str):
        normalized = _normalize_lookup_text(value)
        return normalized not in {"0", "false", "falso", "nao", "no", "inativo"}
    return bool(value)


def _coerce_auditavel(auditavel: Optional[bool], status: str) -> int:
    if auditavel is not None:
        return 1 if auditavel else 0
    return _default_auditavel_from_status(status)


def _normalize_operator_sector(
    setor: str = "",
    escala: str = "",
    organizacao_telefonia: str = "",
) -> str:
    raw_setor = str(setor or "").replace("\xad", "").strip()
    normalized_hints = " ".join(
        (
            _normalize_lookup_text(setor or ""),
            _normalize_lookup_text(escala or ""),
            _normalize_lookup_text(organizacao_telefonia or ""),
        )
    )
    if "fenix" in normalized_hints:
        return "Fênix"

    normalized_setor = _normalize_lookup_text(raw_setor)

    if normalized_setor.startswith("bas") or normalized_setor.startswith("base") or normalized_setor.startswith("rastreamento"):
        return "BAS"

    if normalized_setor.startswith("uti") or normalized_setor.startswith("rj"):
        return "UTI"

    # Strip colors from logistica/distribuicao/cadastro etc if they somehow got in the sector name
    import re
    cleaned_setor = re.sub(r'(?i)\s*-\s*(azul|amarela|verde|cinza)\s*', '', raw_setor)
    cleaned_setor = re.sub(r'(?i)\s*(azul|amarela|verde|cinza)\s*', '', cleaned_setor)

    return cleaned_setor.strip()


def _coerce_huawei_and_telefonia_ids(
    id_huawei: str = "",
    id_telefonia: str = "",
) -> tuple[str, str]:
    normalized_huawei = normalize_huawei_agent_id(id_huawei)
    normalized_telefonia = normalize_huawei_agent_id(id_telefonia)
    if normalized_huawei and not normalized_telefonia:
        normalized_telefonia = normalized_huawei
    elif normalized_telefonia and not normalized_huawei:
        normalized_huawei = normalized_telefonia
    return normalized_huawei, normalized_telefonia


def _resolve_huawei_id(row) -> str:
    id_huawei, _ = _coerce_huawei_and_telefonia_ids(
        row["id_huawei"] if "id_huawei" in row.keys() else "",
        row["id_telefonia"] if "id_telefonia" in row.keys() else "",
    )
    return id_huawei


def _is_technical_telephony_row(row) -> bool:
    return is_technical_telephony_values(
        nome=row["nome"] if "nome" in row.keys() else "",
        matricula=row["matricula"] if "matricula" in row.keys() else "",
        supervisor=row["supervisor"] if "supervisor" in row.keys() else "",
        telefonia_account=row["telefonia_account"] if "telefonia_account" in row.keys() else "",
        organizacao_telefonia=row["organizacao_telefonia"] if "organizacao_telefonia" in row.keys() else "",
        tipo_agente=row["tipo_agente"] if "tipo_agente" in row.keys() else "",
        status_telefonia=row["status_telefonia"] if "status_telefonia" in row.keys() else "",
        id_telefonia=row["id_telefonia"] if "id_telefonia" in row.keys() else "",
        softphone_number=row["softphone_number"] if "softphone_number" in row.keys() else "",
    )


def _is_excluded_operation_row(row) -> bool:
    return is_excluded_operation_values(
        row["setor"] if "setor" in row.keys() else "",
        row["escala"] if "escala" in row.keys() else "",
        row["organizacao_telefonia"] if "organizacao_telefonia" in row.keys() else "",
        row["telefonia_account"] if "telefonia_account" in row.keys() else "",
    )


def _is_removed_operator_row(row) -> bool:
    return _is_technical_telephony_row(row) or _is_excluded_operation_row(row)


def _pick_preferred_operator_id(row) -> tuple[str, str]:
    primary_huawei = _resolve_huawei_id(row)
    if primary_huawei:
        return primary_huawei, "ID Huawei"

    candidates = [
        ("softphone_number", "Softphone"),
        ("matricula", "Matricula"),
    ]
    for key, label in candidates:
        value = str(row[key] or "").strip()
        if value:
            return value, label
    return "", ""


def _operator_payload_from_row(row) -> dict:
    preferred_id, preferred_id_source = _pick_preferred_operator_id(row)
    resolved_setor = _normalize_operator_sector(
        row["setor"] if "setor" in row.keys() else "",
        row["escala"] if "escala" in row.keys() else "",
        row["organizacao_telefonia"] if "organizacao_telefonia" in row.keys() else "",
    )
    resolved_huawei_id = _resolve_huawei_id(row)
    _, resolved_telefonia_id = _coerce_huawei_and_telefonia_ids(
        row["id_huawei"] if "id_huawei" in row.keys() else "",
        row["id_telefonia"] if "id_telefonia" in row.keys() else "",
    )
    return {
        "id": row["id"] if "id" in row.keys() else None,
        "name": str(row["nome"] or "").strip(),
        "preferredId": preferred_id,
        "preferredIdSource": preferred_id_source,
        "supervisor": str(row["supervisor"] or "").strip(),
        "setor": resolved_setor,
        "escala": str(row["escala"] or "").strip(),
        "matricula": str(row["matricula"] or "").strip(),
        "idHuawei": resolved_huawei_id,
        "idTelefonia": resolved_telefonia_id,
        "softphoneNumber": str(row["softphone_number"] or "").strip(),
        "telefoniaAccount": str(row["telefonia_account"] or "").strip(),
        "organizacaoTelefonia": str(row["organizacao_telefonia"] or "").strip(),
        "tipoAgente": str(row["tipo_agente"] or "").strip(),
        "statusTelefonia": str(row["status_telefonia"] or "").strip(),
    }
