"""Repositório do histórico de sincronizações da Telefonia (Huawei).

Persiste e consulta a tabela ``telefonia_sync_history``, que registra cada
execução (run) do sync de ligações da Telefonia: quando começou/terminou, status,
quantas ligações foram baixadas/enfileiradas, erros e o tipo de gatilho
(manual/cron). Suporta runs longos e observáveis:

- ``start_*``/``finalize_*`` abrem (``finished_at=NULL``) e fecham um run;
- ``heartbeat_*`` atualiza ``last_heartbeat_at`` periodicamente;
- ``set_*_pause``/``set_*_cancel`` persistem pedidos de pausa/cancelamento para
  sobreviverem a um restart do pod;
- ``reconcile_stale_*`` é chamado no bootstrap do app para fechar runs órfãos
  (pod reiniciou no meio de um sync).

Sem custo de API: só acesso a banco (PostgreSQL via psycopg2). Todas as funções
recebem a fábrica de conexão ``get_connection`` por injeção e fecham a conexão no
``finally``. Erros são logados e absorvidos (retornam -1/None/0 ou no-op) em vez
de propagados, para não derrubar o pipeline de sync.
"""

import logging
from typing import Optional

from repositories.common import extract_returning_id, get_row_value

logger = logging.getLogger(__name__)

def save_telefonia_sync_history(
    get_connection,
    started_at: str,
    finished_at: Optional[str],
    status: str,
    horas_retroativas,
    baixadas: int,
    enfileiradas: int,
    erros_totais: int,
    mensagem_erro: Optional[str],
    trigger_type: str
) -> int:
    """Insere um registro completo (já finalizado) de sync na history.

    Diferente de ``start_telefonia_sync_run``/``finalize_telefonia_sync_run`` (que
    abrem e fecham um run em duas etapas), esta função grava a row inteira de uma
    vez, com início e fim já conhecidos.

    ``horas_retroativas`` é arredondado e convertido para INTEGER (a coluna é
    INTEGER, mas o código passa floats — ex.: 0.5h = 30min), com piso em 0.

    Efeitos colaterais: INSERT + commit. Em erro, faz rollback, loga e retorna -1.
    Retorna o ``id`` da row criada.
    """
    # A coluna horas_retroativas e INTEGER mas o codigo agora aceita floats
    # (ex: 0.5h = 30min). Arredondamos para evitar falha de tipo no INSERT.
    try:
        horas_int = int(round(float(horas_retroativas or 0)))
    except (TypeError, ValueError):
        horas_int = 0
    if horas_int < 0:
        horas_int = 0

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO telefonia_sync_history
            (started_at, finished_at, status, horas_retroativas, baixadas, enfileiradas, erros_totais, mensagem_erro, trigger_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (started_at, finished_at, status, horas_int, baixadas, enfileiradas, erros_totais, mensagem_erro, trigger_type)
        )
        history_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return history_id
    except Exception as e:
        logger.error(f"Erro ao salvar history da telefonia: {e}")
        conn.rollback()
        return -1
    finally:
        conn.close()

def start_telefonia_sync_run(
    get_connection,
    *,
    started_at: str,
    horas_retroativas,
    trigger_type: str,
) -> int:
    """Cria a row do run em progresso (finished_at=NULL) e devolve o id.

    `last_heartbeat_at` ja entra preenchido para o reconcile do bootstrap
    nao marcar runs muito recentes como interrupted.
    """
    try:
        horas_int = int(round(float(horas_retroativas or 0)))
    except (TypeError, ValueError):
        horas_int = 0
    if horas_int < 0:
        horas_int = 0

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO telefonia_sync_history
            (started_at, finished_at, status, horas_retroativas, baixadas,
             enfileiradas, erros_totais, mensagem_erro, trigger_type,
             pause_requested, cancel_requested, last_heartbeat_at)
            VALUES (%s, NULL, %s, %s, 0, 0, 0, NULL, %s, false, false, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (started_at, "running", horas_int, trigger_type),
        )
        run_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return run_id
    except Exception as e:
        logger.error(f"Erro ao iniciar run de sync da telefonia: {e}")
        conn.rollback()
        return -1
    finally:
        conn.close()


def heartbeat_telefonia_sync_run(
    get_connection,
    run_id: int,
    *,
    status: Optional[str] = None,
) -> None:
    """Atualiza `last_heartbeat_at` (e opcionalmente `status`) do run em progresso."""
    if run_id is None or run_id < 0:
        return
    conn = get_connection()
    try:
        cursor = conn.cursor()
        if status is not None:
            cursor.execute(
                """
                UPDATE telefonia_sync_history
                SET last_heartbeat_at = CURRENT_TIMESTAMP, status = %s
                WHERE id = %s
                """,
                (status, run_id),
            )
        else:
            cursor.execute(
                """
                UPDATE telefonia_sync_history
                SET last_heartbeat_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (run_id,),
            )
        conn.commit()
    except Exception as e:
        logger.warning(f"Falha no heartbeat do sync telefonia (run_id={run_id}): {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def set_telefonia_sync_pause(get_connection, run_id: int, pause: bool) -> None:
    """Persiste o pedido de pause/resume para sobreviver restart do pod."""
    if run_id is None or run_id < 0:
        return
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE telefonia_sync_history
            SET pause_requested = %s, last_heartbeat_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (bool(pause), run_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Falha ao persistir pause_requested (run_id={run_id}): {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def set_telefonia_sync_cancel(get_connection, run_id: int, cancel: bool) -> None:
    """Persiste o pedido de cancel para sobreviver restart do pod."""
    if run_id is None or run_id < 0:
        return
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE telefonia_sync_history
            SET cancel_requested = %s, last_heartbeat_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (bool(cancel), run_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"Falha ao persistir cancel_requested (run_id={run_id}): {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def finalize_telefonia_sync_run(
    get_connection,
    run_id: int,
    *,
    finished_at: str,
    status: str,
    baixadas: int,
    enfileiradas: int,
    erros_totais: int,
    mensagem_erro: Optional[str],
) -> None:
    """Fecha o run em progresso com o resultado final."""
    if run_id is None or run_id < 0:
        return
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE telefonia_sync_history
            SET finished_at = %s,
                status = %s,
                baixadas = %s,
                enfileiradas = %s,
                erros_totais = %s,
                mensagem_erro = %s,
                last_heartbeat_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (finished_at, status, baixadas, enfileiradas, erros_totais, mensagem_erro, run_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(f"Falha ao finalizar run de sync telefonia (run_id={run_id}): {e}")
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


def get_active_telefonia_sync_run(get_connection) -> Optional[dict]:
    """Devolve a row em progresso (`finished_at IS NULL`) ou None."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, started_at, status, horas_retroativas, baixadas, enfileiradas,
                   erros_totais, mensagem_erro, trigger_type,
                   pause_requested, cancel_requested, last_heartbeat_at
            FROM telefonia_sync_history
            WHERE finished_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": get_row_value(row, "id"),
            "started_at": get_row_value(row, "started_at"),
            "status": get_row_value(row, "status"),
            "horas_retroativas": get_row_value(row, "horas_retroativas"),
            "baixadas": get_row_value(row, "baixadas"),
            "enfileiradas": get_row_value(row, "enfileiradas"),
            "erros_totais": get_row_value(row, "erros_totais"),
            "mensagem_erro": get_row_value(row, "mensagem_erro"),
            "trigger_type": get_row_value(row, "trigger_type"),
            "pause_requested": bool(get_row_value(row, "pause_requested")),
            "cancel_requested": bool(get_row_value(row, "cancel_requested")),
            "last_heartbeat_at": get_row_value(row, "last_heartbeat_at"),
        }
    except Exception as e:
        logger.warning(f"Falha ao consultar run ativo de sync telefonia: {e}")
        return None
    finally:
        conn.close()


def reconcile_stale_telefonia_sync_runs(
    get_connection,
    stale_after_seconds: int = 120,
) -> int:
    """Marca como 'interrupted' qualquer run aberto cujo heartbeat (ou started_at) for mais antigo
    que `stale_after_seconds`. Chamado no bootstrap do app e devolve a quantidade reconciliada.
    """
    threshold = max(60, int(stale_after_seconds or 120))
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE telefonia_sync_history
            SET status = 'interrupted',
                finished_at = CURRENT_TIMESTAMP,
                mensagem_erro = COALESCE(mensagem_erro, 'Run interrompido por reinicio do pod.')
            WHERE finished_at IS NULL
              AND COALESCE(last_heartbeat_at, started_at) < CURRENT_TIMESTAMP - (%s * interval '1 second')
            """,
            (threshold,),
        )
        affected = int(getattr(cursor, "rowcount", 0) or 0)
        conn.commit()
        return affected
    except Exception as e:
        logger.warning(f"Falha ao reconciliar runs orfaos de sync telefonia: {e}")
        try:
            conn.rollback()
        except Exception:
            pass
        return 0
    finally:
        conn.close()


def list_telefonia_sync_history(get_connection, limit: int = 50) -> list[dict]:
    """Lista os runs de sync mais recentes (ordenados por ``started_at`` DESC).

    ``limit`` é normalizado para o intervalo [1, 500]. Cada item traz os campos da
    row e também um sub-objeto ``result`` no formato legado (mantém compatibilidade
    com o frontend que espera a chave ``message``). ``started_at``/``finished_at``
    são serializados via ``.isoformat()`` quando presentes.

    Efeito colateral: somente leitura no banco. Em erro, loga e retorna lista
    vazia. A conexão é sempre fechada.
    """
    limite = max(1, min(int(limit), 500))
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, started_at, finished_at, status, horas_retroativas, baixadas, 
                   enfileiradas, erros_totais, mensagem_erro, trigger_type
            FROM telefonia_sync_history
            ORDER BY started_at DESC
            LIMIT %s
            """,
            (limite,)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            started_at = get_row_value(r, "started_at")
            finished_at = get_row_value(r, "finished_at")
            status = get_row_value(r, "status")
            horas_retroativas = get_row_value(r, "horas_retroativas")
            baixadas = get_row_value(r, "baixadas")
            enfileiradas = get_row_value(r, "enfileiradas")
            erros_totais = get_row_value(r, "erros_totais")
            mensagem_erro = get_row_value(r, "mensagem_erro")
            result.append({
                "id": get_row_value(r, "id"),
                "started_at": started_at.isoformat() if started_at else None,
                "finished_at": finished_at.isoformat() if finished_at else None,
                "status": status,
                "horas_retroativas": horas_retroativas,
                "baixadas": baixadas,
                "enfileiradas": enfileiradas,
                "erros_totais": erros_totais,
                "mensagem_erro": mensagem_erro,
                "trigger_type": get_row_value(r, "trigger_type"),
                "result": { # format as legacy result to keep frontend compatibility if it expects 'result' object
                    "status": status,
                    "horas_retroativas": horas_retroativas,
                    "baixadas": baixadas,
                    "enfileiradas": enfileiradas,
                    "erros_totais": erros_totais,
                    "message": mensagem_erro
                }
            })
        return result
    except Exception as e:
        logger.error(f"Erro ao listar history da telefonia: {e}")
        return []
    finally:
        conn.close()


