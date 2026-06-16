"""Resolução e matching de setor canônico do colaborador.

Subdomínio coeso extraído de `repositories/operators.py` (v1.3.165) sem mudança
de comportamento. Delega a `repositories.sector_aliases` (regras de setor em DB,
editáveis via UI) a resolução do setor canônico a partir de
organização/escala/supervisor, e oferece o matching usado na auditoria.

Os nomes seguem reexportados de `repositories.operators` (callers internos e
fachada usam `operators.<nome>`). Imports de `sector_aliases`/`db.database` são
feitos em runtime dentro das funções (evita ciclo e preserva monkeypatch).
"""

from typing import Callable, Optional, Any

from repositories.operator_normalization import _normalize_lookup_text


ConnectionFactory = Callable[[], Any]


def _get_sector_aliases_repo():
    from repositories import sector_aliases as _sa
    return _sa


def _get_default_connection_factory() -> ConnectionFactory:
    from db.database import get_connection
    return get_connection


def _load_sector_aliases_dict() -> dict[str, str]:
    """Fase 2: dicionario plano {alias: canonical} oriundo de sector_aliases (setor_exact).
    Fallback silencioso para {} se o DB indisponivel.
    """
    try:
        sa = _get_sector_aliases_repo()
        return sa.get_setor_exact_aliases(_get_default_connection_factory())
    except Exception:
        return {}


def _map_organizacao_telefonia_to_sector(organizacao: str) -> str:
    """Fase 2: delega para sector_aliases.resolve_canonical_sector(organizacao=...).
    Contrato preservado: retorna `""` (string vazia) quando nao ha match.
    """
    if not organizacao:
        return ""
    try:
        sa = _get_sector_aliases_repo()
        result = sa.resolve_canonical_sector(
            _get_default_connection_factory(),
            organizacao=organizacao,
        )
    except Exception:
        return ""
    return result or ""


def map_db_sector_to_classification_sector(
    setor: str,
    escala: str,
    supervisor: str = "",
) -> Optional[str]:
    """Map database (HR) sector/escala/supervisor to classification sector_id.

    Fase 2: delega para `sector_aliases.resolve_canonical_sector` (regras em DB,
    editaveis via UI sem PR). Ordem de match e definida pelo `priority` da regra.
    Returns None quando nenhuma regra casa.
    """
    try:
        sa = _get_sector_aliases_repo()
        return sa.resolve_canonical_sector(
            _get_default_connection_factory(),
            setor=setor or "",
            escala=escala or "",
            supervisor=supervisor or "",
        )
    except Exception:
        return None


def _matches_operador_sector(sector_id: Optional[str], setor: str, escala: str) -> bool:
    normalized_sector_id = _normalize_lookup_text(sector_id or "")
    normalized_setor = _normalize_lookup_text(setor or "")
    normalized_escala = _normalize_lookup_text(escala or "")

    if not normalized_sector_id:
        return True
    
    aliases = _load_sector_aliases_dict()
    normalized_sector_id = aliases.get(normalized_sector_id, normalized_sector_id)
    mapped_setor = aliases.get(normalized_setor, normalized_setor)

    if normalized_sector_id == "uti":
        return (
            mapped_setor.startswith("uti")
            or normalized_setor.startswith("uti")
            or mapped_setor.startswith("rj")
            or normalized_setor.startswith("rj")
        )
    if normalized_sector_id == "bas":
        return mapped_setor.startswith("bas") or normalized_setor.startswith("bas")
    if normalized_sector_id == "distribuicao":
        return mapped_setor == "distribuicao" or normalized_setor == "distribuicao"
    if normalized_sector_id == "transferencia":
        return (mapped_setor == "transferencia" or "transferencia" in normalized_setor or "longo" in normalized_setor or "rastreamento" in normalized_setor) and "fenix" not in normalized_escala
    if normalized_sector_id == "fenix":
        return mapped_setor == "fenix" or normalized_setor == "fenix" or "fenix" in normalized_escala
    if normalized_sector_id == "cadastro":
        return mapped_setor == "cadastro" or normalized_setor == "cadastro"
    if normalized_sector_id == "checklist":
        return mapped_setor == "checklist" or normalized_setor == "checklist" or "checklist" in normalized_escala
    if normalized_sector_id == "celula_atendimento":
        return mapped_setor == "celula_atendimento" or mapped_setor == "receptivo" or normalized_setor == "receptivo" or "celula" in normalized_escala or "celula" in normalized_setor or "celula" in mapped_setor
    if normalized_sector_id == "logistica_unilever":
        return "unilever" in normalized_escala or "unilever" in normalized_setor or "unilever" in mapped_setor
    if normalized_sector_id == "mondelez":
        return "mondelez" in normalized_escala or "mondelez" in normalized_setor or "mondelez" in mapped_setor
    if normalized_sector_id == "logistica":
        return (
            mapped_setor == "logistica"
            or normalized_setor == "logistica"
            or "taborda" in normalized_escala
            or "taborda" in normalized_setor
        ) and not any(tag in normalized_escala for tag in ("unilever", "mondelez"))
    return mapped_setor == normalized_sector_id or normalized_setor == normalized_sector_id or normalized_escala == normalized_sector_id
