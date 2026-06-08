"""Fase 2 do plano de migracao DB-first.

Repositorio para `sector_aliases` (mapeamento setor cru -> canonico, prioridade,
pattern type) e `sector_aliases_audit_log`.

Pontos chaves:

- `resolve_canonical_sector(setor, escala, supervisor, organizacao)` substitui o
  ladder hardcoded de `repositories/operators.py:map_db_sector_to_classification_sector`
  e `_map_organizacao_telefonia_to_sector`.
- `get_setor_exact_aliases()` retorna o dicionario classico `{alias: canonical}`
  para os call sites que ainda querem o dict (`_matches_operador_sector`,
  `_resolve_db_sector_alias`).
- Cache de regras em memoria (per-process). Invalidado em qualquer mutacao do
  proprio repository. Em Cloud Run multi-pod a invalidacao so afeta o pod que
  recebeu a requisicao — mesma limitacao da Fase 1.1 (lru_cache do catalogo).

Padrao de audit_log identico a `repositories/admin_criteria.py` (Fase 1.1):
toda mutacao captura snapshot antes/depois em JSONB na mesma transacao.
"""

from __future__ import annotations

import logging
import threading
import unicodedata
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


_VALID_ORIGINS = {"ui", "api", "seed", "script", "system", "migration"}
_VALID_PATTERN_TYPES = {
    "setor_exact",
    "setor_startswith",
    "setor_contains",
    "escala_contains",
    "supervisor_contains",
    "organizacao_contains",
    "organizacao_startswith",
}

_AUDIT_LOG_TABLE = "sector_aliases_audit_log"

_cache_lock = threading.Lock()
_rules_cache: Optional[list[dict]] = None


def _norm(value: Optional[str]) -> str:
    """Normalizacao identica a `_normalize_lookup_text` em operators.py.

    Lowercase + NFD + remove combining marks. Sem regex de pontuacao — match e
    feito por substring/startswith, entao pontuacao da input passa intocada.
    """
    if not value:
        return ""
    normalized = unicodedata.normalize("NFD", str(value).strip().lower())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def clear_cache() -> None:
    global _rules_cache
    with _cache_lock:
        _rules_cache = None


def _load_rules(db_connection_factory: Callable) -> list[dict]:
    """Carrega regras ativas ordenadas por priority DESC, id ASC (memoizado).

    Fail-soft: em erro de DB retorna `[]` e nao cacheia. Caller deve tratar
    None / lista vazia como "nenhuma regra disponivel".
    """
    global _rules_cache
    with _cache_lock:
        if _rules_cache is not None:
            return _rules_cache

    rules: list[dict] = []
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, pattern_type, pattern_value, canonical_sector_id, priority
              FROM sector_aliases
             WHERE ativo
             ORDER BY priority DESC, id ASC
            """
        )
        for row in c.fetchall():
            rules.append({
                "id": row["id"],
                "pattern_type": row["pattern_type"],
                "pattern_value": row["pattern_value"],
                "canonical_sector_id": row["canonical_sector_id"],
                "priority": row["priority"],
            })
    except Exception:
        logger.exception("Falha ao carregar sector_aliases — fallback para []")
        return []
    finally:
        conn.close()

    with _cache_lock:
        _rules_cache = rules
    return rules


def list_active_rules(db_connection_factory: Callable) -> list[dict]:
    """Acessor publico das regras ativas (priority DESC, id ASC), memoizadas.

    Para callers que querem rodar `match_canonical_sector` em lote (ex: a cascata
    de rename de setor) sem reabrir conexao por item.
    """
    return _load_rules(db_connection_factory)


def match_canonical_sector(
    rules: list[dict],
    *,
    setor: str = "",
    escala: str = "",
    supervisor: str = "",
    organizacao: str = "",
) -> Optional[str]:
    """Matcher puro (sem I/O): dado o conjunto de `rules` ja carregado + os hints do
    RH, retorna o `canonical_sector_id` da primeira regra que casa (ordem de
    priority DESC) ou None.

    Separado de `resolve_canonical_sector` para reuso em lote dentro de uma
    transacao/loop que ja carregou as regras uma unica vez.
    """
    if not rules:
        return None

    n_setor = _norm(setor)
    n_escala = _norm(escala)
    n_supervisor = _norm(supervisor)
    n_organizacao = _norm(organizacao)

    for rule in rules:
        pt = rule["pattern_type"]
        pv = rule["pattern_value"]
        target = rule["canonical_sector_id"]

        if pt == "supervisor_contains":
            if pv and pv in n_supervisor:
                return target
        elif pt == "escala_contains":
            if pv and pv in n_escala:
                return target
        elif pt == "setor_exact":
            if pv == n_setor:
                return target
        elif pt == "setor_startswith":
            if pv and n_setor.startswith(pv):
                return target
        elif pt == "setor_contains":
            if pv and pv in n_setor:
                return target
        elif pt == "organizacao_startswith":
            if pv and n_organizacao.startswith(pv):
                return target
        elif pt == "organizacao_contains":
            if pv and pv in n_organizacao:
                return target

    return None


def resolve_canonical_sector(
    db_connection_factory: Callable,
    *,
    setor: str = "",
    escala: str = "",
    supervisor: str = "",
    organizacao: str = "",
) -> Optional[str]:
    """Resolve sector_id canonico a partir dos hints do RH.

    Substitui a logica de `map_db_sector_to_classification_sector` +
    `_map_organizacao_telefonia_to_sector`. Itera regras em ordem de priority
    DESC e retorna o `canonical_sector_id` da primeira regra que casa.

    Returns None se nenhuma regra casar — comportamento identico ao original.
    """
    rules = _load_rules(db_connection_factory)
    return match_canonical_sector(
        rules,
        setor=setor,
        escala=escala,
        supervisor=supervisor,
        organizacao=organizacao,
    )


def get_setor_exact_aliases(db_connection_factory: Callable) -> dict[str, str]:
    """Retorna {pattern_value_normalizado: canonical_sector_id} apenas para regras
    de tipo `setor_exact`.

    Usado por `_matches_operador_sector` e `_resolve_db_sector_alias` que ainda
    operam sobre um dicionario plano.
    """
    rules = _load_rules(db_connection_factory)
    return {
        rule["pattern_value"]: rule["canonical_sector_id"]
        for rule in rules
        if rule["pattern_type"] == "setor_exact"
    }


# -------------------- CRUD --------------------


def _validate_audit_args(alterado_por: str, origem: str, op_label: str) -> bool:
    if not alterado_por or not str(alterado_por).strip():
        logger.error("%s rejeitado: alterado_por obrigatorio", op_label)
        return False
    if origem not in _VALID_ORIGINS:
        logger.error("%s rejeitado: origem invalida '%s'", op_label, origem)
        return False
    return True


def _log_change(
    cursor: Any,
    *,
    acao: str,
    entity_id: int,
    payload_antes: Optional[dict],
    payload_depois: Optional[dict],
    alterado_por: str,
    motivo: str,
    origem: str,
) -> None:
    from psycopg2.extras import Json

    cursor.execute(
        f"""
        INSERT INTO {_AUDIT_LOG_TABLE}
            (acao, entity_id, payload_antes, payload_depois, alterado_por, motivo, origem)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            acao,
            str(entity_id),
            Json(payload_antes) if payload_antes is not None else None,
            Json(payload_depois) if payload_depois is not None else None,
            str(alterado_por).strip(),
            (motivo or "").strip() or None,
            origem,
        ),
    )


def _row_to_dict(row: Any) -> dict:
    return dict(row)


def list_aliases(db_connection_factory: Callable) -> list[dict]:
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, pattern_type, pattern_value, canonical_sector_id,
                   priority, descricao, ativo, criado_em, atualizado_em
              FROM sector_aliases
             ORDER BY priority DESC, pattern_type ASC, pattern_value ASC
            """
        )
        return [_row_to_dict(row) for row in c.fetchall()]
    finally:
        conn.close()


def get_alias(db_connection_factory: Callable, alias_id: int) -> Optional[dict]:
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT id, pattern_type, pattern_value, canonical_sector_id,
                   priority, descricao, ativo, criado_em, atualizado_em
              FROM sector_aliases WHERE id = %s
            """,
            (int(alias_id),),
        )
        row = c.fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def _snapshot_payload(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    return {
        "pattern_type": row.get("pattern_type"),
        "pattern_value": row.get("pattern_value"),
        "canonical_sector_id": row.get("canonical_sector_id"),
        "priority": row.get("priority"),
        "descricao": row.get("descricao"),
        "ativo": row.get("ativo"),
    }


def create_alias(
    db_connection_factory: Callable,
    *,
    pattern_type: str,
    pattern_value: str,
    canonical_sector_id: str,
    priority: int = 100,
    descricao: Optional[str] = None,
    ativo: bool = True,
    alterado_por: str,
    motivo: Optional[str] = None,
    origem: str = "ui",
) -> Optional[int]:
    if not _validate_audit_args(alterado_por, origem, "create_alias"):
        return None
    if pattern_type not in _VALID_PATTERN_TYPES:
        logger.error("create_alias rejeitado: pattern_type invalido '%s'", pattern_type)
        return None
    normalized_value = _norm(pattern_value)
    if not normalized_value:
        logger.error("create_alias rejeitado: pattern_value vazio apos normalizacao")
        return None
    if not str(canonical_sector_id or "").strip():
        logger.error("create_alias rejeitado: canonical_sector_id vazio")
        return None

    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO sector_aliases (pattern_type, pattern_value, canonical_sector_id,
                                        priority, descricao, ativo)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                pattern_type,
                normalized_value,
                str(canonical_sector_id).strip(),
                int(priority),
                (descricao or "").strip() or None,
                bool(ativo),
            ),
        )
        new_id = c.fetchone()[0]
        payload_depois = {
            "pattern_type": pattern_type,
            "pattern_value": normalized_value,
            "canonical_sector_id": str(canonical_sector_id).strip(),
            "priority": int(priority),
            "descricao": (descricao or "").strip() or None,
            "ativo": bool(ativo),
        }
        _log_change(
            c, acao="create", entity_id=new_id,
            payload_antes=None, payload_depois=payload_depois,
            alterado_por=alterado_por, motivo=motivo or "", origem=origem,
        )
        conn.commit()
        clear_cache()
        return int(new_id)
    except Exception:
        logger.exception("create_alias falhou (pattern_type=%s, pattern_value=%s)",
                         pattern_type, pattern_value)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def update_alias(
    db_connection_factory: Callable,
    alias_id: int,
    *,
    pattern_type: Optional[str] = None,
    pattern_value: Optional[str] = None,
    canonical_sector_id: Optional[str] = None,
    priority: Optional[int] = None,
    descricao: Optional[str] = None,
    ativo: Optional[bool] = None,
    alterado_por: str,
    motivo: Optional[str] = None,
    origem: str = "ui",
) -> bool:
    if not _validate_audit_args(alterado_por, origem, "update_alias"):
        return False

    current = get_alias(db_connection_factory, alias_id)
    if not current:
        return False

    new_values = {
        "pattern_type": pattern_type if pattern_type is not None else current["pattern_type"],
        "pattern_value": _norm(pattern_value) if pattern_value is not None else current["pattern_value"],
        "canonical_sector_id": (
            str(canonical_sector_id).strip()
            if canonical_sector_id is not None else current["canonical_sector_id"]
        ),
        "priority": int(priority) if priority is not None else current["priority"],
        "descricao": (
            (descricao or "").strip() or None
            if descricao is not None else current["descricao"]
        ),
        "ativo": bool(ativo) if ativo is not None else current["ativo"],
    }

    if new_values["pattern_type"] not in _VALID_PATTERN_TYPES:
        logger.error("update_alias rejeitado: pattern_type invalido '%s'", new_values["pattern_type"])
        return False
    if not new_values["pattern_value"]:
        logger.error("update_alias rejeitado: pattern_value vazio apos normalizacao")
        return False
    if not new_values["canonical_sector_id"]:
        logger.error("update_alias rejeitado: canonical_sector_id vazio")
        return False

    snapshot_antes = _snapshot_payload(current)
    if _snapshot_payload({**current, **new_values}) == snapshot_antes:
        # No-op — nao polui audit_log
        return True

    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            """
            UPDATE sector_aliases
               SET pattern_type = %s,
                   pattern_value = %s,
                   canonical_sector_id = %s,
                   priority = %s,
                   descricao = %s,
                   ativo = %s,
                   atualizado_em = NOW()
             WHERE id = %s
            """,
            (
                new_values["pattern_type"],
                new_values["pattern_value"],
                new_values["canonical_sector_id"],
                new_values["priority"],
                new_values["descricao"],
                new_values["ativo"],
                int(alias_id),
            ),
        )
        if c.rowcount == 0:
            conn.rollback()
            return False
        _log_change(
            c, acao="update", entity_id=int(alias_id),
            payload_antes=snapshot_antes, payload_depois=new_values,
            alterado_por=alterado_por, motivo=motivo or "", origem=origem,
        )
        conn.commit()
        clear_cache()
        return True
    except Exception:
        logger.exception("update_alias falhou (id=%s)", alias_id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def delete_alias(
    db_connection_factory: Callable,
    alias_id: int,
    *,
    alterado_por: str,
    motivo: Optional[str] = None,
    origem: str = "ui",
) -> bool:
    if not _validate_audit_args(alterado_por, origem, "delete_alias"):
        return False

    current = get_alias(db_connection_factory, alias_id)
    if not current:
        return False

    snapshot_antes = _snapshot_payload(current)
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("DELETE FROM sector_aliases WHERE id = %s", (int(alias_id),))
        if c.rowcount == 0:
            conn.rollback()
            return False
        _log_change(
            c, acao="delete", entity_id=int(alias_id),
            payload_antes=snapshot_antes, payload_depois=None,
            alterado_por=alterado_por, motivo=motivo or "", origem=origem,
        )
        conn.commit()
        clear_cache()
        return True
    except Exception:
        logger.exception("delete_alias falhou (id=%s)", alias_id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def list_audit_log(
    db_connection_factory: Callable,
    *,
    entity_id: Optional[int] = None,
    limit: int = 50,
) -> list[dict]:
    import psycopg2.extras

    safe_limit = max(1, min(int(limit or 50), 500))
    conn = db_connection_factory()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if entity_id is not None:
            cursor.execute(
                f"""
                SELECT id, acao, entity_id, payload_antes, payload_depois,
                       alterado_por, alterado_em, motivo, origem
                  FROM {_AUDIT_LOG_TABLE}
                 WHERE entity_id = %s
                 ORDER BY alterado_em DESC
                 LIMIT %s
                """,
                (str(entity_id), safe_limit),
            )
        else:
            cursor.execute(
                f"""
                SELECT id, acao, entity_id, payload_antes, payload_depois,
                       alterado_por, alterado_em, motivo, origem
                  FROM {_AUDIT_LOG_TABLE}
                 ORDER BY alterado_em DESC
                 LIMIT %s
                """,
                (safe_limit,),
            )
        return [dict(row) for row in cursor.fetchall()]
    except Exception:
        logger.exception("list_audit_log (sector_aliases) falhou")
        return []
    finally:
        conn.close()
