"""Repositorio do catalogo de criterios de auditoria (setores/alertas/criterios).

CRUD da hierarquia que define COMO a IA pontua cada ligacao:
`audit_sectors` -> `audit_alerts` -> `audit_criteria`. Consumido pela tela admin
de Criterios (via router) e pela avaliacao. Toda operacao de ESCRITA grava uma
trilha de auditoria (audit_log) na MESMA transacao da mudanca, exigindo os
parametros keyword-only `alterado_por`/`motivo`/`origem` (validados por
`_validate_audit_args`); um no-op (sem mudanca real) nao polui o log.

Primitivas de trilha de auditoria (`_log_change`, `_validate_audit_args`,
`_AUDIT_LOG_TABLES`) e de export/serializacao (`_with_row_factory`,
`get_export_format`, etc.) foram extraidas para modulos irmaos
(`admin_criteria_audit_log`, `admin_criteria_export`) e reexportadas aqui para
compatibilidade de import.

Funcao especial: `rename_sector_with_cascade` renomeia o rotulo do setor e
propaga o nome para os colaboradores vinculados sem mexer no `id` interno (regras
de auditoria intactas). Sem custo de API (apenas acesso a banco).
"""
import logging
from typing import Optional, Any

from psycopg2 import sql

from repositories.common import extract_returning_id
# Primitivas de trilha de auditoria extraídas para admin_criteria_audit_log;
# reexportadas p/ compat (usadas pelas operações de escrita e por get_audit_log).
from repositories.admin_criteria_audit_log import (  # noqa: F401
    _AUDIT_LOG_TABLES,
    _validate_audit_args,
    _log_change,
)

logger = logging.getLogger(__name__)


# Export/serialização do catálogo de critérios: extraído para
# admin_criteria_export (v1.3.166); reexportado p/ compat (router usa
# get_export_format; _with_row_factory é usado pelos getters/CRUD daqui).
from repositories.admin_criteria_export import (  # noqa: E402,F401
    _with_row_factory,
    _get_existing_columns,
    _safe_select_rows,
    get_export_format,
)


# --- Trava de orçamento de pesos por alerta (v1.3.203) ---
# A nota é (pontos obtidos / soma dos pesos do alerta) * 10. Isso só equivale a
# "peso = ponto na escala 0-10" quando a soma dos pesos do alerta é 10. Se a soma
# passar de 10, todos os critérios são reescalados e a nota infla (foi o caso da
# qualificação do checklist: 4,00 -> 9,07). Logo, ao criar/editar um critério a
# soma do alerta não pode passar de 10. Estados abaixo de 10 são permitidos
# (edição em progresso, ex.: logo após excluir um critério). A decisão é uma
# função pura (testável sem banco); a query da soma é fina por cima.
WEIGHT_BUDGET = 10.0
WEIGHT_BUDGET_TOLERANCE = 0.01  # somas de floats (0.1*n) podem dar 10.0000001


class AlertWeightBudgetExceeded(Exception):
    """Salvar o critério faria a soma dos pesos do alerta passar de 10."""


def weight_budget_exceeded(
    existing_sum: float,
    new_weight: float,
    *,
    budget: float = WEIGHT_BUDGET,
    tolerance: float = WEIGHT_BUDGET_TOLERANCE,
) -> bool:
    """True se ``existing_sum + new_weight`` passa do orçamento (10) além da tolerância.

    ``existing_sum`` é a soma dos pesos dos OUTROS critérios do alerta (excluindo o
    que está sendo criado/editado); ``new_weight`` é o peso novo/atualizado.
    """
    return (existing_sum + new_weight) > (budget + tolerance)


def weight_budget_message(alert_id: str, *, existing_sum: float, new_weight: float, budget: float = WEIGHT_BUDGET) -> str:
    """Mensagem pt-BR explicando por que o save foi bloqueado e o que fazer."""
    total = existing_sum + new_weight
    return (
        f"Os pesos do alerta '{alert_id}' passariam de {budget:g} "
        f"(ficariam em {total:.2f}). A soma dos pesos precisa ser no máximo "
        f"{budget:g} para a nota sair correta — reduza outro peso antes de salvar."
    )


def _alert_weight_sum(cursor, alert_id: str, *, exclude_id: Optional[int] = None) -> float:
    """Soma dos pesos dos critérios de ``alert_id``, opcionalmente excluindo um id.

    Usa o cursor/transação corrente (mesma conexão da escrita) para enxergar um
    estado consistente. Retorna 0.0 se o alerta não tem critérios.
    """
    if exclude_id is None:
        cursor.execute(
            "SELECT COALESCE(SUM(weight), 0) FROM audit_criteria WHERE alert_id = %s",
            (alert_id,),
        )
    else:
        cursor.execute(
            "SELECT COALESCE(SUM(weight), 0) FROM audit_criteria WHERE alert_id = %s AND id <> %s",
            (alert_id, exclude_id),
        )
    row = cursor.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


def get_sectors(db_connection_factory):
    """Lista todos os setores de auditoria (id, label, description), ordenados por label.

    `db_connection_factory` e uma callable que devolve uma conexao do pool.
    Read-only; abre e fecha a conexao. Retorna lista de dicts.
    """
    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        c.execute("SELECT id, label, description FROM audit_sectors ORDER BY label")
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_alerts(db_connection_factory, sector_id: Optional[str] = None):
    """Lista alertas de auditoria; se `sector_id` for dado, filtra por aquele setor.

    Retorna campos id, sector_id, label, context, pop_ref e expected_direction,
    ordenados por label (ou por sector_id, label quando sem filtro). Read-only;
    abre e fecha a conexao. Retorna lista de dicts.
    """
    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        if sector_id:
            c.execute(
                "SELECT id, sector_id, label, context, pop_ref, expected_direction FROM audit_alerts WHERE sector_id = %s ORDER BY label",
                (sector_id,),
            )
        else:
            c.execute(
                "SELECT id, sector_id, label, context, pop_ref, expected_direction FROM audit_alerts ORDER BY sector_id, label"
            )
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()

def get_criteria(db_connection_factory, alert_id: Optional[str] = None):
    """Lista criterios de auditoria; se `alert_id` for dado, filtra por aquele alerta.

    Retorna campos id, alert_id, chave, label, weight, description, type,
    deflator, referencia, exemplo e evaluation_type, ordenados por id (ou por
    alert_id, id quando sem filtro). Read-only; abre e fecha a conexao. Retorna
    lista de dicts.
    """
    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        if alert_id:
            c.execute(
                """
                SELECT id, alert_id, chave, label, weight, description, type,
                       deflator, referencia, exemplo, evaluation_type
                FROM audit_criteria
                WHERE alert_id = %s
                ORDER BY id
                """,
                (alert_id,),
            )
        else:
            c.execute(
                """
                SELECT id, alert_id, chave, label, weight, description, type,
                       deflator, referencia, exemplo, evaluation_type
                FROM audit_criteria
                ORDER BY alert_id, id
                """
            )
        return [dict(row) for row in c.fetchall()]
    finally:
        conn.close()


# CRUD Operations (todas com audit_log na mesma transacao)

def create_sector(
    db_connection_factory,
    id: str,
    label: str,
    description: Optional[str] = None,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
) -> bool:
    """Cria um setor de auditoria (`audit_sectors`) e registra a criacao no audit_log.

    `id`/`label`/`description` sao os campos do setor; `alterado_por`/`motivo`/
    `origem` (keyword-only) alimentam a trilha. Insert + log na mesma transacao
    (commit ao final; rollback e re-raise em erro). Retorna False se a validacao
    de auditoria falhar, True em sucesso. Efeito colateral: escreve no DB.
    """
    if not _validate_audit_args(alterado_por, origem, "create_sector"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO audit_sectors (id, label, description) VALUES (%s, %s, %s)",
            (id, label, description),
        )
        _log_change(
            c,
            entity_type="sector",
            acao="create",
            entity_id=id,
            payload_antes=None,
            payload_depois={"id": id, "label": label, "description": description},
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return True
    except Exception:
        logger.exception("create_sector falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def update_sector(
    db_connection_factory,
    id: str,
    label: str,
    description: Optional[str] = None,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    """Atualiza label/description de um setor e registra a mudanca no audit_log.

    Le o estado anterior; se nada mudou (antes == depois), retorna True sem tocar
    no DB nem no log (no-op silencioso). Caso contrario faz UPDATE + log na mesma
    transacao. Retorna False se o setor nao existe ou se a validacao de auditoria
    falhar. Efeito colateral: escreve no DB. Rollback e re-raise em erro.
    """
    if not _validate_audit_args(alterado_por, origem, "update_sector"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, label, description FROM audit_sectors WHERE id = %s", (id,))
        row = c.fetchone()
        if not row:
            return False
        antes = {"id": row[0], "label": row[1], "description": row[2]}
        depois = {"id": id, "label": label, "description": description}
        if antes == depois:
            return True  # no-op silencioso, nao polui audit_log
        c.execute(
            "UPDATE audit_sectors SET label = %s, description = %s WHERE id = %s",
            (label, description, id),
        )
        _log_change(
            c,
            entity_type="sector",
            acao="update",
            entity_id=id,
            payload_antes=antes,
            payload_depois=depois,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("update_sector falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def get_sector_members(db_connection_factory, sector_id: str) -> list[dict]:
    """Colaboradores cujo setor resolve (via sector_aliases) para `sector_id`.

    Read-only. Fonte unica da "associacao funcionario->setor": usada tanto pelo
    preview `/members` quanto pela cascata de rename. A vinculacao principal e
    implicita (string `colaboradores.setor` -> mapa de apelidos ->
    `audit_sectors.id`), mas tambem aceita match exato com o label atual do setor
    e com o id interno. Esse fallback cobre setores criados/renomeados antes de
    terem alias explicito, evitando cascata com contagem zero.
    """
    from repositories import sector_aliases as _sa

    conn = _with_row_factory(db_connection_factory())
    try:
        c = conn.cursor()
        rules = _sa.list_active_rules(db_connection_factory)
        c.execute(
            """
            SELECT c.id, c.nome, c.setor, c.escala, c.supervisor,
                   c.organizacao_telefonia, s.label AS sector_label
              FROM colaboradores c
              LEFT JOIN audit_sectors s ON s.id = %s
             ORDER BY c.nome
            """,
            (sector_id,),
        )
        sector_id_norm = _sa._norm(sector_id)
        members: list[dict] = []
        for raw in c.fetchall():
            colab = dict(raw)
            raw_setor_norm = _sa._norm(colab.get("setor") or "")
            direct_matches = {
                value
                for value in (sector_id_norm, _sa._norm(colab.get("sector_label") or ""))
                if value
            }
            canon = _sa.match_canonical_sector(
                rules,
                setor=colab.get("setor") or "",
                escala=colab.get("escala") or "",
                supervisor=colab.get("supervisor") or "",
                organizacao=colab.get("organizacao_telefonia") or "",
            )
            if canon == sector_id or (
                canon is None and raw_setor_norm in direct_matches
            ):
                members.append(
                    {"id": colab["id"], "nome": colab.get("nome"), "setor": colab.get("setor")}
                )
        return members
    finally:
        conn.close()


def rename_sector_with_cascade(
    db_connection_factory,
    sector_id: str,
    new_label: str,
    description: Optional[str] = None,
    *,
    cascade: bool = True,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
) -> Optional[dict]:
    """Renomeia o rotulo de um setor e, se `cascade`, propaga o novo nome para todos
    os colaboradores vinculados — mantendo as regras de auditoria intactas.

    O `id` do setor (chave a que `audit_alerts.sector_id` aponta) NUNCA muda; por
    isso a auditoria nao e afetada. Passos, numa unica transacao de escrita:
      1. `UPDATE audit_sectors.label/description`;
      2. detecta membros (`get_sector_members`) e faz bulk `UPDATE colaboradores.setor`
         para o novo nome, com snapshot pre/pos em `colaboradores_audit_log`;
      3. garante um alias `setor_exact` (_norm(new_label) -> sector_id) com prioridade
         alta, para o novo nome continuar resolvendo ao mesmo `sector_id`;
      4. registra a mudanca em `audit_sectors_audit_log` (com resumo da cascata).

    Retorna {"affected": int, "label": str} ou None se o setor nao existe.
    """
    if not _validate_audit_args(alterado_por, origem, "rename_sector_with_cascade"):
        return None

    new_label = (new_label or "").strip()
    if not new_label:
        logger.error("rename_sector_with_cascade rejeitado: new_label vazio")
        return None

    from repositories import sector_aliases as _sa
    from repositories.operators import _snapshot_colaborador, _log_colaborador_audit

    # Deteccao (read-only) antes da transacao de escrita — exclui quem ja esta no nome novo.
    affected_ids: list[int] = []
    if cascade:
        affected_ids = [
            int(m["id"])
            for m in get_sector_members(db_connection_factory, sector_id)
            if (m.get("setor") or "") != new_label
        ]

    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, label, description FROM audit_sectors WHERE id = %s", (sector_id,))
        row = c.fetchone()
        if not row:
            conn.rollback()
            return None
        antes = {"id": row[0], "label": row[1], "description": row[2]}
        c.execute(
            "UPDATE audit_sectors SET label = %s, description = %s WHERE id = %s",
            (new_label, description, sector_id),
        )

        if cascade and affected_ids:
            snapshots_before = {cid: _snapshot_colaborador(c, cid) for cid in affected_ids}
            c.execute(
                "UPDATE colaboradores SET setor = %s, atualizado_em = CURRENT_TIMESTAMP "
                "WHERE id = ANY(%s)",
                (new_label, affected_ids),
            )
            cascade_motivo = motivo or f"rename setor '{antes['label']}' -> '{new_label}'"
            for cid in affected_ids:
                _log_colaborador_audit(
                    c,
                    acao="update",
                    entity_id=cid,
                    payload_antes=snapshots_before.get(cid),
                    payload_depois=_snapshot_colaborador(c, cid),
                    alterado_por=alterado_por,
                    motivo=cascade_motivo,
                    origem=origem,
                )

        if cascade:
            # Garante que o novo nome resolva para este sector_id (regras intactas).
            norm_label = _sa._norm(new_label)
            if norm_label:
                c.execute(
                    "SELECT 1 FROM sector_aliases "
                    "WHERE pattern_type = 'setor_exact' AND pattern_value = %s "
                    "AND canonical_sector_id = %s AND ativo",
                    (norm_label, sector_id),
                )
                if not c.fetchone():
                    c.execute(
                        "INSERT INTO sector_aliases "
                        "(pattern_type, pattern_value, canonical_sector_id, priority, descricao, ativo) "
                        "VALUES ('setor_exact', %s, %s, %s, %s, TRUE)",
                        (norm_label, sector_id, 200, f"auto: rename setor -> {new_label}"),
                    )

        _log_change(
            c,
            entity_type="sector",
            acao="update",
            entity_id=sector_id,
            payload_antes=antes,
            payload_depois={
                "id": sector_id,
                "label": new_label,
                "description": description,
                "cascade": cascade,
                "affected_colaboradores": len(affected_ids),
            },
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return {"affected": len(affected_ids), "label": new_label}
    except Exception:
        logger.exception("rename_sector_with_cascade falhou (id=%s)", sector_id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()
        try:
            _sa.clear_cache()  # novo alias publicado -> invalida cache de regras
        except Exception:
            pass


def delete_sector(
    db_connection_factory,
    id: str,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    """Remove um setor (`audit_sectors`) e registra a exclusao no audit_log.

    Snapshota o estado anterior antes do DELETE; insere o log na mesma transacao.
    Retorna False se o setor nao existe ou se a validacao de auditoria falhar.
    Efeito colateral: escreve no DB. Rollback e re-raise em erro.
    """
    if not _validate_audit_args(alterado_por, origem, "delete_sector"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, label, description FROM audit_sectors WHERE id = %s", (id,))
        row = c.fetchone()
        if not row:
            return False
        antes = {"id": row[0], "label": row[1], "description": row[2]}
        c.execute("DELETE FROM audit_sectors WHERE id = %s", (id,))
        _log_change(
            c,
            entity_type="sector",
            acao="delete",
            entity_id=id,
            payload_antes=antes,
            payload_depois=None,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("delete_sector falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def create_alert(
    db_connection_factory,
    sector_id: str,
    label: str,
    context: Optional[str] = None,
    original_id: Optional[str] = None,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
    pop_ref: Optional[str] = None,
    expected_direction: Optional[str] = None,
):
    """Cria um alerta (`audit_alerts`) sob `sector_id` e registra no audit_log.

    Gera o id como `{sector_id}::{original_id}` quando `original_id` e dado, senao
    `{sector_id}::{uuid curto}`. `label`/`context`/`pop_ref`/`expected_direction`
    sao os campos do alerta. Insert + log na mesma transacao. Retorna o id gerado
    (str) em sucesso, ou None se a validacao de auditoria falhar. Efeito
    colateral: escreve no DB. Rollback e re-raise em erro.
    """
    if not _validate_audit_args(alterado_por, origem, "create_alert"):
        return None

    import uuid
    if original_id:
        a_id = f"{sector_id}::{original_id}"
    else:
        a_id = f"{sector_id}::{uuid.uuid4().hex[:8]}"

    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO audit_alerts (id, sector_id, label, context, pop_ref, expected_direction) VALUES (%s, %s, %s, %s, %s, %s)",
            (a_id, sector_id, label, context, pop_ref, expected_direction),
        )
        _log_change(
            c,
            entity_type="alert",
            acao="create",
            entity_id=a_id,
            payload_antes=None,
            payload_depois={
                "id": a_id, "sector_id": sector_id, "label": label,
                "context": context, "pop_ref": pop_ref, "expected_direction": expected_direction,
            },
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return a_id
    except Exception:
        logger.exception("create_alert falhou (sector_id=%s, label=%s)", sector_id, label)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def update_alert(
    db_connection_factory,
    id: str,
    label: str,
    context: Optional[str] = None,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
    pop_ref: Optional[str] = None,
    expected_direction: Optional[str] = None,
):
    """Atualiza um alerta (label/context/pop_ref/expected_direction) e registra no log.

    `pop_ref` e `expected_direction` so sao alterados quando passados explicitamente
    (None preserva o valor atual). No-op silencioso se nada mudou (retorna True).
    Faz UPDATE + log na mesma transacao. Retorna False se o alerta nao existe ou
    se a validacao de auditoria falhar. Efeito colateral: escreve no DB. Rollback
    e re-raise em erro.
    """
    if not _validate_audit_args(alterado_por, origem, "update_alert"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, sector_id, label, context, pop_ref, expected_direction FROM audit_alerts WHERE id = %s", (id,))
        row = c.fetchone()
        if not row:
            return False
        antes = {
            "id": row[0], "sector_id": row[1], "label": row[2],
            "context": row[3], "pop_ref": row[4], "expected_direction": row[5]
        }
        # pop_ref e expected_direction nao mexido a nao ser que o caller passe explicitamente
        new_pop_ref = pop_ref if pop_ref is not None else row[4]
        new_expected_direction = expected_direction if expected_direction is not None else row[5]
        depois = {
            "id": id, "sector_id": row[1], "label": label,
            "context": context, "pop_ref": new_pop_ref, "expected_direction": new_expected_direction
        }
        if antes == depois:
            return True
        c.execute(
            "UPDATE audit_alerts SET label = %s, context = %s, pop_ref = %s, expected_direction = %s WHERE id = %s",
            (label, context, new_pop_ref, new_expected_direction, id),
        )
        _log_change(
            c,
            entity_type="alert",
            acao="update",
            entity_id=id,
            payload_antes=antes,
            payload_depois=depois,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("update_alert falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def delete_alert(
    db_connection_factory,
    id: str,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    """Remove um alerta (`audit_alerts`) e registra a exclusao no audit_log.

    Snapshota o estado anterior antes do DELETE; insere o log na mesma transacao.
    Retorna False se o alerta nao existe ou se a validacao de auditoria falhar.
    Efeito colateral: escreve no DB. Rollback e re-raise em erro.
    """
    if not _validate_audit_args(alterado_por, origem, "delete_alert"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute("SELECT id, sector_id, label, context, pop_ref, expected_direction FROM audit_alerts WHERE id = %s", (id,))
        row = c.fetchone()
        if not row:
            return False
        antes = {
            "id": row[0], "sector_id": row[1], "label": row[2],
            "context": row[3], "pop_ref": row[4], "expected_direction": row[5]
        }
        c.execute("DELETE FROM audit_alerts WHERE id = %s", (id,))
        _log_change(
            c,
            entity_type="alert",
            acao="delete",
            entity_id=id,
            payload_antes=antes,
            payload_depois=None,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("delete_alert falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def create_criterion(
    db_connection_factory,
    alert_id: str,
    chave: str,
    label: str,
    weight: float,
    description: Optional[str] = None,
    type: str = "boolean",
    deflator: float = 0,
    referencia: Optional[str] = None,
    exemplo: Optional[str] = None,
    evaluation_type: str = "auto",
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    """Cria um criterio (`audit_criteria`) sob `alert_id` e registra no audit_log.

    `chave`/`label`/`weight`/`description`/`type`/`deflator`/`referencia`/`exemplo`/
    `evaluation_type` sao os campos do criterio. Insert com RETURNING id + log na
    mesma transacao. Retorna o novo id (int) em sucesso, ou None se a validacao de
    auditoria falhar. Efeito colateral: escreve no DB. Rollback e re-raise em erro.
    """
    if not _validate_audit_args(alterado_por, origem, "create_criterion"):
        return None
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        existing_sum = _alert_weight_sum(c, alert_id)
        if weight_budget_exceeded(existing_sum, weight):
            raise AlertWeightBudgetExceeded(
                weight_budget_message(alert_id, existing_sum=existing_sum, new_weight=weight)
            )
        c.execute(
            "INSERT INTO audit_criteria (alert_id, chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (alert_id, chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type),
        )
        new_id = extract_returning_id(c.fetchone())
        _log_change(
            c,
            entity_type="criterion",
            acao="create",
            entity_id=new_id,
            payload_antes=None,
            payload_depois={
                "id": new_id, "alert_id": alert_id, "chave": chave, "label": label,
                "weight": weight, "description": description, "type": type,
                "deflator": deflator, "referencia": referencia, "exemplo": exemplo,
                "evaluation_type": evaluation_type,
            },
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return new_id
    except AlertWeightBudgetExceeded:
        # Falha de validação esperada — não loga como erro; o router devolve 400.
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception:
        logger.exception("create_criterion falhou (alert_id=%s, chave=%s)", alert_id, chave)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def update_criterion(
    db_connection_factory,
    id: int,
    chave: str,
    label: str,
    weight: float,
    description: Optional[str] = None,
    type: str = "boolean",
    deflator: float = 0,
    referencia: Optional[str] = None,
    exemplo: Optional[str] = None,
    evaluation_type: str = "auto",
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    """Atualiza um criterio (todos os campos exceto alert_id) e registra no audit_log.

    No-op silencioso se nada mudou (retorna True). Faz UPDATE + log na mesma
    transacao. Retorna False se o criterio nao existe ou se a validacao de
    auditoria falhar. Efeito colateral: escreve no DB. Rollback e re-raise em erro.
    """
    if not _validate_audit_args(alterado_por, origem, "update_criterion"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT id, alert_id, chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type FROM audit_criteria WHERE id = %s",
            (id,),
        )
        row = c.fetchone()
        if not row:
            return False
        antes = {
            "id": row[0], "alert_id": row[1], "chave": row[2], "label": row[3],
            "weight": row[4], "description": row[5], "type": row[6],
            "deflator": row[7], "referencia": row[8], "exemplo": row[9],
            "evaluation_type": row[10],
        }
        depois = {
            "id": id, "alert_id": row[1], "chave": chave, "label": label,
            "weight": weight, "description": description, "type": type,
            "deflator": deflator, "referencia": referencia, "exemplo": exemplo,
            "evaluation_type": evaluation_type,
        }
        if antes == depois:
            return True
        alert_id = row[1]
        existing_sum = _alert_weight_sum(c, alert_id, exclude_id=id)
        if weight_budget_exceeded(existing_sum, weight):
            raise AlertWeightBudgetExceeded(
                weight_budget_message(alert_id, existing_sum=existing_sum, new_weight=weight)
            )
        c.execute(
            "UPDATE audit_criteria SET chave = %s, label = %s, weight = %s, description = %s, type = %s, deflator = %s, referencia = %s, exemplo = %s, evaluation_type = %s WHERE id = %s",
            (chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type, id),
        )
        _log_change(
            c,
            entity_type="criterion",
            acao="update",
            entity_id=id,
            payload_antes=antes,
            payload_depois=depois,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except AlertWeightBudgetExceeded:
        # Falha de validação esperada — não loga como erro; o router devolve 400.
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception:
        logger.exception("update_criterion falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()

def delete_criterion(
    db_connection_factory,
    id: int,
    *,
    alterado_por: str,
    motivo: str = "",
    origem: str = "ui",
):
    """Remove um criterio (`audit_criteria`) e registra a exclusao no audit_log.

    Snapshota o estado anterior antes do DELETE; insere o log na mesma transacao.
    Retorna False se o criterio nao existe ou se a validacao de auditoria falhar.
    Efeito colateral: escreve no DB. Rollback e re-raise em erro.
    """
    if not _validate_audit_args(alterado_por, origem, "delete_criterion"):
        return False
    conn = db_connection_factory()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT id, alert_id, chave, label, weight, description, type, deflator, referencia, exemplo, evaluation_type FROM audit_criteria WHERE id = %s",
            (id,),
        )
        row = c.fetchone()
        if not row:
            return False
        antes = {
            "id": row[0], "alert_id": row[1], "chave": row[2], "label": row[3],
            "weight": row[4], "description": row[5], "type": row[6],
            "deflator": row[7], "referencia": row[8], "exemplo": row[9],
            "evaluation_type": row[10],
        }
        c.execute("DELETE FROM audit_criteria WHERE id = %s", (id,))
        _log_change(
            c,
            entity_type="criterion",
            acao="delete",
            entity_id=id,
            payload_antes=antes,
            payload_depois=None,
            alterado_por=alterado_por,
            motivo=motivo,
            origem=origem,
        )
        conn.commit()
        return c.rowcount > 0
    except Exception:
        logger.exception("delete_criterion falhou (id=%s)", id)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def list_audit_log(
    db_connection_factory,
    *,
    entity_type: str,
    entity_id: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Lista as ultimas mudancas em sector/alert/criterion, mais recentes primeiro.

    `entity_type` deve ser 'sector', 'alert' ou 'criterion'. Filtra por `entity_id`
    se informado. `limit` clampado em [1, 500].
    """
    import psycopg2.extras
    if entity_type not in _AUDIT_LOG_TABLES:
        return []
    table = _AUDIT_LOG_TABLES[entity_type]
    safe_limit = max(1, min(int(limit or 50), 500))
    conn = db_connection_factory()
    try:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if entity_id:
            cursor.execute(
                f"""
                SELECT id, acao, entity_id, payload_antes, payload_depois,
                       alterado_por, alterado_em, motivo, origem
                  FROM {table}
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
                  FROM {table}
                 ORDER BY alterado_em DESC
                 LIMIT %s
                """,
                (safe_limit,),
            )
        return [dict(row) for row in cursor.fetchall()]
    except Exception:
        logger.exception("list_audit_log falhou (entity_type=%s)", entity_type)
        return []
    finally:
        conn.close()
