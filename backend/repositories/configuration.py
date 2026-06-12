import logging
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

ConnectionFactory = Callable[[], Any]


_VALID_ORIGINS = {"ui", "api", "seed", "script", "system", "migration"}
_SECRET_MASK = "***"

# Chaves cujo valor representa um booleano lógico. A UI/scripts ocasionalmente
# enviam variações ("1", "yes", checkboxes serializados como número), e o backend
# espera consistentemente "true"/"false". Normalizar aqui evita divergência
# que já causou bug em produção (flag de cron gravada como "1" em vez de "true";
# a chave do incidente, telefonia_cron_sync_ativa, foi removida em 2026-06-12).
_BOOLEAN_KEYS = frozenset({
    "automacao_hibrida_ativa",
    "huawei_d1_enabled",
    "automacao_is_paused",
    "automacao_is_cancelled",
})

_BOOL_TRUE_TOKENS = frozenset({"true", "1", "yes", "on", "sim", "t"})
_BOOL_FALSE_TOKENS = frozenset({"false", "0", "no", "off", "nao", "não", "f"})


def _normalize_boolean_value(chave: str, valor: str) -> str:
    if chave not in _BOOLEAN_KEYS:
        return valor
    token = valor.strip().lower()
    if token in _BOOL_TRUE_TOKENS:
        return "true"
    if token in _BOOL_FALSE_TOKENS:
        return "false"
    return valor


def get_all_configs(
    get_connection: ConnectionFactory,
    *,
    mask_secrets: bool = True,
) -> dict:
    """Retorna todas as configuracoes.

    `mask_secrets=True` mascara o valor de chaves com `is_secret=true` (default
    para qualquer endpoint admin). Use `mask_secrets=False` apenas em codigo
    interno que precisa do valor real (ex.: monta cabecalho Huawei).
    """
    import psycopg2.extras
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cursor.execute(
            """
            SELECT chave, valor, descricao, atualizado_em, tipo, is_secret
              FROM configuracoes
            """
        )
        rows = cursor.fetchall()
        result = {}
        for row in rows:
            valor = row["valor"]
            if mask_secrets and row.get("is_secret") and valor:
                valor = _SECRET_MASK
            result[row["chave"]] = {
                "valor": valor,
                "descricao": row["descricao"],
                "tipo": row.get("tipo") or "string",
                "is_secret": bool(row.get("is_secret")),
            }
        return result
    except Exception as exc:
        logger.warning("Erro ao buscar configuracoes: %s", exc)
        return {}
    finally:
        conn.close()


def update_config(
    get_connection: ConnectionFactory,
    chave: str,
    valor: str,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
) -> bool:
    """UPSERT em `configuracoes` + INSERT em `configuracoes_audit_log` na mesma transacao.

    `alterado_por` e obrigatorio. Para chamadas internas (automacao, scripts) use
    o prefixo `system:` (ex.: `system:automation`). Para chamadas vindas do router
    admin, passe o `current_user.username`.

    `motivo` e opcional, mas recomendado para mudancas operacionais (ajuda a
    correlacionar com incidentes posteriores).

    `origem` precisa estar em {ui, api, seed, script, system, migration} —
    validado pelo CHECK no banco e pre-validado aqui pra falhar rapido.
    """
    if not alterado_por or not str(alterado_por).strip():
        logger.error(
            "update_config rejeitado: alterado_por obrigatorio (chave=%s)", chave
        )
        return False
    if origem not in _VALID_ORIGINS:
        logger.error(
            "update_config rejeitado: origem invalida '%s' (chave=%s)", origem, chave
        )
        return False

    valor_str = "" if valor is None else str(valor)
    valor_str = _normalize_boolean_value(chave, valor_str)
    conn = get_connection()
    try:
        cursor = conn.cursor()

        # 1. Snapshot do valor anterior + flag de secret (NULL se a chave nao existe)
        cursor.execute(
            "SELECT valor, is_secret FROM configuracoes WHERE chave = %s",
            (chave,),
        )
        row = cursor.fetchone()
        valor_antes = row[0] if row else None
        is_secret = bool(row[1]) if row and len(row) > 1 else False

        # 1b. Proteção contra round-trip: GET mascara secrets como '***'.
        # Se a UI re-enviar o valor mascarado, NAO sobrescrever o secret real.
        # Tratamos como no-op silencioso (status success) — UI nao precisa saber.
        if is_secret and valor_str == _SECRET_MASK:
            logger.info(
                "update_config no-op: chave secret '%s' recebeu valor mascarado '%s' "
                "(provavel round-trip da UI; segredo preservado)",
                chave,
                _SECRET_MASK,
            )
            return True

        # 2. UPSERT do valor novo
        cursor.execute(
            """
            INSERT INTO configuracoes (chave, valor, atualizado_em)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (chave)
            DO UPDATE SET valor = EXCLUDED.valor, atualizado_em = CURRENT_TIMESTAMP
            """,
            (chave, valor_str),
        )

        # 3. Trail (apenas se houve mudanca real — evita poluir audit_log com no-ops)
        if valor_antes != valor_str:
            cursor.execute(
                """
                INSERT INTO configuracoes_audit_log
                    (chave, valor_antes, valor_depois, alterado_por, motivo, origem)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (chave, valor_antes, valor_str, str(alterado_por).strip(), motivo or None, origem),
            )

        conn.commit()
        return True
    except Exception:
        logger.exception(
            "Erro ao atualizar configuracao chave=%s valor_len=%s alterado_por=%s",
            chave,
            len(valor_str),
            alterado_por,
        )
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()


def get_config_value(get_connection: ConnectionFactory, chave: str, default: str = "") -> str:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = %s", (chave,))
        row = cursor.fetchone()
        if row:
            return row[0]
        return default
    except Exception:
        return default
    finally:
        conn.close()


def list_audit_log(
    get_connection: ConnectionFactory,
    *,
    chave: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Lista as ultimas mudancas em `configuracoes`, mais recentes primeiro.

    Filtra por `chave` se informado. `limit` clampado em [1, 500].
    """
    import psycopg2.extras
    safe_limit = max(1, min(int(limit or 50), 500))
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if chave:
            cursor.execute(
                """
                SELECT id, chave, valor_antes, valor_depois, alterado_por,
                       alterado_em, motivo, origem
                  FROM configuracoes_audit_log
                 WHERE chave = %s
                 ORDER BY alterado_em DESC
                 LIMIT %s
                """,
                (chave, safe_limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, chave, valor_antes, valor_depois, alterado_por,
                       alterado_em, motivo, origem
                  FROM configuracoes_audit_log
                 ORDER BY alterado_em DESC
                 LIMIT %s
                """,
                (safe_limit,),
            )
        return [dict(row) for row in cursor.fetchall()]
    except Exception:
        logger.exception("Erro ao listar configuracoes_audit_log")
        return []
    finally:
        conn.close()
