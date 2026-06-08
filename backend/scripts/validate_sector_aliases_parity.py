"""Fase 2 — valida que o resolver DB-backed casa byte-a-byte com a logica
hardcoded que vivia em `repositories/operators.py:map_db_sector_to_classification_sector`
e `_map_organizacao_telefonia_to_sector` antes da migracao.

Rode com `python -m scripts.validate_sector_aliases_parity` a partir de
`backend/`. Exit code 1 se houver qualquer divergencia.

Inputs cobertos:
- Todas as combinacoes distintas (setor, escala, supervisor) da tabela
  `colaboradores WHERE auditavel=1`.
- Todas as organizacao_telefonia distintas da mesma tabela.

Nao depende de conexao Neon externa — usa `database.get_connection`.
"""

from __future__ import annotations

import logging
import sys
import unicodedata
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _norm(value: str | None) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _old_map_db_sector_to_classification_sector(
    setor: str, escala: str, supervisor: str = "",
) -> Optional[str]:
    """Copia EXATA da logica original (pre-Fase 2). Nao altere — base de comparacao."""
    normalized_setor = _norm(setor or "")
    normalized_escala = _norm(escala or "")
    normalized_supervisor = _norm(supervisor or "")

    if "miralha" in normalized_supervisor:
        return "transferencia"
    if normalized_setor.startswith("uti") or normalized_setor.startswith("rj"):
        return "uti"
    if normalized_setor.startswith("bas"):
        return "bas"
    if "distribuicao" in normalized_setor or normalized_setor == "dist":
        return "distribuicao"
    if "transferencia" in normalized_setor:
        return "transferencia"
    if "fenix" in normalized_setor or "fenix" in normalized_escala:
        return "fenix"
    if "cadastro" in normalized_setor:
        return "cadastro"
    if "checklist" in normalized_setor or "checklist" in normalized_escala:
        return "checklist"
    if "celula" in normalized_setor or "celula" in normalized_escala:
        return "celula_atendimento"
    if "receptivo" in normalized_setor:
        return "celula_atendimento"
    if "unilever" in normalized_escala or "unilever" in normalized_setor:
        return "logistica_unilever"
    if "mondelez" in normalized_escala or "mondelez" in normalized_setor:
        return "mondelez"
    if "taborda" in normalized_escala or "taborda" in normalized_setor:
        return "logistica"
    if normalized_setor == "logistica":
        return "logistica"
    return None


def _old_map_organizacao_telefonia_to_sector(organizacao: str) -> str:
    """Copia EXATA da logica original (pre-Fase 2)."""
    normalized_org = _norm(organizacao)
    if not normalized_org:
        return ""
    if "cadastro" in normalized_org:
        return "cadastro"
    if "unilever" in normalized_org:
        return "logistica_unilever"
    if "mondelez" in normalized_org:
        return "mondelez"
    if "taborda" in normalized_org:
        return "logistica"
    if "fenix" in normalized_org:
        return "fenix"
    if "checklist" in normalized_org:
        return "checklist"
    if "celula" in normalized_org:
        return "celula_atendimento"
    if "base de sinistro" in normalized_org:
        return "bas"
    if "distribu" in normalized_org:
        return "distribuicao"
    if normalized_org.startswith("uti") or " uti" in normalized_org:
        return "uti"
    if any(tag in normalized_org for tag in ("rastreamento", "lp", "bbm")):
        return "transferencia"
    if any(tag in normalized_org for tag in ("logistica", "profarma", "comandolog", "tora", "sanofi")):
        return "logistica"
    return ""


def _old_resolve_db_sector_alias(db_sector: str | None) -> str | None:
    """Copia EXATA do dict-only check do `_resolve_db_sector_alias`. Sem fallback
    para catalog (esse caminho preserva-se na funcao nova; testamos so o dict).
    """
    if not db_sector:
        return None
    raw_id = str(db_sector).strip().lower()
    alias_map = {
        "grs": "uti", "rastreamento": "transferencia", "rast": "transferencia",
        "longo percurso": "transferencia", "longo_percurso": "transferencia",
        "dist": "distribuicao", "sinistro": "bas", "sinistros": "bas",
        "unilever": "logistica_unilever", "receptivo": "celula_atendimento",
        "celula atendimento": "celula_atendimento",
        "celula_atendimento": "celula_atendimento",
    }
    return alias_map.get(raw_id)


def _fetch_distinct_inputs(get_connection):
    conn = get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT DISTINCT
                COALESCE(setor, '') AS setor,
                COALESCE(escala, '') AS escala,
                COALESCE(supervisor, '') AS supervisor,
                COALESCE(organizacao_telefonia, '') AS organizacao_telefonia
              FROM colaboradores
             WHERE auditavel = 1
            """
        )
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()


def main() -> int:
    from db.database import get_connection
    from repositories import sector_aliases as sa

    rows = _fetch_distinct_inputs(get_connection)
    logger.info("Carregadas %d combinacoes distintas de colaboradores.auditavel=1.", len(rows))

    diffs: list[str] = []

    # 1. map_db_sector_to_classification_sector
    for row in rows:
        old = _old_map_db_sector_to_classification_sector(row["setor"], row["escala"], row["supervisor"])
        new = sa.resolve_canonical_sector(
            get_connection,
            setor=row["setor"], escala=row["escala"], supervisor=row["supervisor"],
        )
        if old != new:
            diffs.append(
                f"[map_db_sector] setor={row['setor']!r}, escala={row['escala']!r}, "
                f"supervisor={row['supervisor']!r} → OLD={old!r}, NEW={new!r}"
            )

    # 2. _map_organizacao_telefonia_to_sector
    seen_orgs = {row["organizacao_telefonia"] for row in rows}
    for org in sorted(seen_orgs):
        old = _old_map_organizacao_telefonia_to_sector(org)
        new = sa.resolve_canonical_sector(get_connection, organizacao=org) or ""
        if old != new:
            diffs.append(f"[map_org] organizacao={org!r} → OLD={old!r}, NEW={new!r}")

    # 3. setor_exact alias dict (subset que o `_resolve_db_sector_alias` cobre)
    db_aliases = sa.get_setor_exact_aliases(get_connection)
    legacy_inputs = [
        "GRS", "Rastreamento", "rast", "Longo Percurso", "longo_percurso",
        "dist", "sinistro", "sinistros", "unilever", "receptivo",
        "celula atendimento", "celula_atendimento",
        "BAS - Amarela", "RJ - AZUL",  # extras nao mapeados pelo alias-dict
    ]
    for raw in legacy_inputs:
        old = _old_resolve_db_sector_alias(raw)
        new = db_aliases.get(_norm(raw))
        if old != new:
            diffs.append(f"[alias_dict] raw={raw!r} → OLD={old!r}, NEW={new!r}")

    # 4. Inputs extras de smoke-test (cases historicos importantes)
    smoke_cases = [
        # (setor, escala, supervisor, expected)
        ("UTI - AZUL", "Azul", "", "uti"),
        ("BAS - Amarela", "Amarela", "", "bas"),
        ("BASE DE PR - CINZA", "Cinza", "", "bas"),
        ("RJ - VERDE", "Verde", "", "uti"),
        ("RASTREAMENTO - AMARELA", "Amarela", "", None),
        ("FENIX", "FÊNIX", "Adryan Celso", "fenix"),
        ("transferencia", "FÊNIX", "Adryan Celso", "transferencia"),
        ("", "UNILEVER", "", "logistica_unilever"),
        ("", "MONDELEZ", "", "mondelez"),
        ("Logística", "Comercial", "Miralha", "transferencia"),
        ("Logística", "Comercial", "", "logistica"),
        ("Cadastro", "CADASTRO", "", "cadastro"),
        ("Célula", "", "", "celula_atendimento"),
    ]
    for setor, escala, supervisor, expected in smoke_cases:
        new = sa.resolve_canonical_sector(
            get_connection, setor=setor, escala=escala, supervisor=supervisor,
        )
        if new != expected:
            diffs.append(
                f"[smoke] setor={setor!r}, escala={escala!r}, supervisor={supervisor!r} "
                f"→ NEW={new!r}, EXPECTED={expected!r}"
            )

    if diffs:
        logger.error("Encontrados %d diffs:", len(diffs))
        for d in diffs:
            logger.error("  %s", d)
        return 1

    logger.info("Parity OK. Nenhuma divergencia encontrada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
