"""Pipeline "D-1" da Huawei: coleta diária do lote do(s) dia(s) anterior(es).

Papel no sistema: orquestra a baixa automática das gravações que a Huawei sobe
para o OBS referentes ao dia anterior (D-1). Como a Huawei pode demorar horas
para finalizar o upload, o pipeline tem retry, janela de lookback (vários dias
para trás) e horário programado, tudo configurável pela tabela `configuracoes`
(ver `PIPELINE_CONFIG_DEFAULTS`). E acionado por scheduler HTTP externo
(Cloud Scheduler no GCP; Container Apps Job ou Logic App no Azure) e tambem
manualmente pela UI (force=True bypassa os gates de retry).

Fluxo de `executar_d_minus_1`: adquire um lock em `configuracoes`
('huawei_d1_run_lock'), verifica no OBS se há áudio + manifesto CSV do dia, e
então delega o processamento real a `core.huawei_sync.executar_sync_huawei`
(obs_only=True). O estado de cada dia (status, tentativas, contagens) é
persistido na tabela `huawei_d_minus_1_runs` via `HuaweiDMinus1Tracker`.

Custo de API: este módulo em si não chama Azure (OpenAI/Speech). As chamadas
pagas/de rede ocorrem no `executar_sync_huawei` que ele invoca (download de
áudio Huawei e, depois, transcrição/avaliação a jusante). Efeitos colaterais
diretos daqui: banco (tabela de runs + lock), OBS (Huawei), e webhook HTTP de
alerta em caso de tentativas esgotadas.
"""

import asyncio
import logging
import os
import json
from datetime import datetime, timedelta, time as dt_time, timezone
from zoneinfo import ZoneInfo
from typing import Callable, Optional, Any, List

import db.database as database
from core.huawei_sync import executar_sync_huawei
from core.huawei_obs_client import HuaweiOBSClient
import httpx

logger = logging.getLogger(__name__)

SP_TZ = ZoneInfo("America/Sao_Paulo")
RUN_RETENTION_DAYS = 180

# ─── Configs runtime (chave → default) ────────────────────────────────
# Defaults conservadores: Huawei pode demorar horas para finalizar o upload
# do dia anterior, então max_retries alto + lookback de 3 dias evitam perda
# permanente de lotes quando a janela de coleta cai num momento ruim ou a
# automação fica temporariamente desligada.
PIPELINE_CONFIG_DEFAULTS: dict[str, str] = {
    "huawei_d1_enabled": "true",
    "huawei_d1_horario_execucao": "06:00",          # HH:MM em America/Sao_Paulo
    "huawei_d1_max_retries": "8",                   # tentativas se OBS vazio/erro
    "huawei_d1_retry_intervalo_minutos": "60",      # intervalo entre tentativas
    "huawei_d1_lookback_dias": "3",                 # quantos dias para trás verificar
    "huawei_cota_max_por_operador_mes": "2",
}

_NON_TERMINAL_STATUSES = {
    "pending",
    "in_progress",
    "empty",
    "obs_voice_empty_will_retry",
    "obs_manifest_empty_will_retry",
    "error",
    "partial",
}


def get_pipeline_config() -> dict[str, str]:
    """Lê todas as configs do D-1 do banco com defaults."""
    cfg = database.get_config_values(
        tuple(PIPELINE_CONFIG_DEFAULTS.keys()),
        PIPELINE_CONFIG_DEFAULTS,
    )
    return {
        key: str(cfg.get(key) or default)
        for key, default in PIPELINE_CONFIG_DEFAULTS.items()
    }


class HuaweiDMinus1Tracker:
    """Acesso à tabela `huawei_d_minus_1_runs` (estado por dia do pipeline D-1).

    Cada linha representa uma data (`date_str` no formato YYYYMMDD) e guarda
    status, número de tentativas, timestamps e as contagens do último resultado.
    Todos os métodos abrem/commitam a própria conexão de banco. Sem custo de API.
    """

    @staticmethod
    def get_run(date_str: str) -> Optional[dict]:
        """Lê a linha de run de uma data (YYYYMMDD) ou None se não existir.

        Retorna o registro como dict (lê do banco). Apenas leitura.
        """
        with database.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM huawei_d_minus_1_runs WHERE date_str = %s", (date_str,))
                row = cur.fetchone()
                if row:
                    try:
                        return dict(row)
                    except (TypeError, ValueError):
                        colnames = [desc[0] for desc in cur.description]
                        return dict(zip(colnames, row))
                return None

    @staticmethod
    def mark_in_progress(date_str: str):
        """Marca a data como 'in_progress' e incrementa o contador de tentativas.

        Faz UPSERT em `huawei_d_minus_1_runs`: cria a linha (attempts=1) ou
        soma +1 às tentativas existentes, atualizando `last_attempt_at`.
        Efeito colateral: escreve no banco (commit).
        """
        with database.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO huawei_d_minus_1_runs (date_str, status, attempts, last_attempt_at)
                    VALUES (%s, 'in_progress', 1, CURRENT_TIMESTAMP)
                    ON CONFLICT (date_str) DO UPDATE
                    SET status = 'in_progress',
                        attempts = huawei_d_minus_1_runs.attempts + 1,
                        last_attempt_at = CURRENT_TIMESTAMP
                """, (date_str,))
                conn.commit()

    @staticmethod
    def mark_empty(date_str: str, reason: str):
        """Marca a data como 'empty' (OBS sem áudio/manifesto) gravando o motivo.

        `reason` vai para a coluna `last_error`. Escreve no banco (commit).
        """
        with database.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE huawei_d_minus_1_runs
                    SET status = 'empty', last_error = %s
                    WHERE date_str = %s
                """, (reason, date_str))
                conn.commit()

    @staticmethod
    def mark_result(date_str: str, status: str, result: dict, error: Optional[str] = None):
        """Persiste o resultado final de uma execução para a data.

        Grava `status` e extrai contagens do dict `result` (chamadas no
        manifesto OBS, candidatos a download, baixadas, ignoradas por cota) para
        colunas dedicadas, além do `result` completo em `last_result_json`.
        `error` vai para `last_error`. Regra importante: em status='completed'
        ZERA o contador de tentativas e marca `completed_at`; nos demais status
        as tentativas são mantidas. Escreve no banco (commit).
        """
        with database.get_connection() as conn:
            with conn.cursor() as cur:
                # Reset attempts on success, keep incrementing on failure
                attempts_sql = "attempts"
                if status == 'completed':
                    attempts_sql = "0"

                cur.execute(f"""
                    UPDATE huawei_d_minus_1_runs
                    SET status = %s,
                        attempts = {attempts_sql},
                        completed_at = CASE WHEN %s = 'completed' THEN CURRENT_TIMESTAMP ELSE completed_at END,
                        manifest_rows_count = %s,
                        candidates_count = %s,
                        downloaded_count = %s,
                        skipped_quota_count = %s,
                        last_error = %s,
                        last_result_json = %s
                    WHERE date_str = %s
                """, (
                    status,
                    status,
                    result.get("chamadas_no_manifest_obs", 0),
                    result.get("candidatos_download", 0),
                    result.get("baixadas", 0),
                    result.get("ignoradas_cota_mensal_pre_download", 0),
                    error,
                    json.dumps(result, ensure_ascii=False),
                    date_str
                ))
                conn.commit()

    @staticmethod
    def mark_retry_exhausted_alerted(date_str: str) -> bool:
        """Marca (uma única vez) que o alerta de tentativas esgotadas foi disparado.

        Seta `exhausted_alerted_at` SOMENTE se ainda estava NULL e retorna True
        nesse caso; se já havia sido marcado antes, retorna False. Serve de
        guarda de idempotência para não alertar repetidamente. Escreve no banco.
        """
        with database.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE huawei_d_minus_1_runs
                    SET exhausted_alerted_at = CURRENT_TIMESTAMP
                    WHERE date_str = %s
                      AND exhausted_alerted_at IS NULL
                    RETURNING date_str
                    """,
                    (date_str,),
                )
                updated = cur.fetchone() is not None
                conn.commit()
                return updated

    @staticmethod
    async def notify_retry_exhausted(
        date_str: str,
        *,
        attempts: int,
        last_error: Optional[str] = None,
    ) -> bool:
        """Alerta (uma vez) que um lote esgotou as tentativas de retry.

        Usa `mark_retry_exhausted_alerted` como guarda: se já foi alertado
        antes, retorna False sem fazer nada. Caso contrário loga em nível
        CRITICAL e, se houver webhook configurado (`_get_failure_webhook_url`),
        envia um POST de alerta (rede). Retorna True quando o alerta foi
        emitido. `attempts`/`last_error` entram na mensagem/payload.
        """
        if not HuaweiDMinus1Tracker.mark_retry_exhausted_alerted(date_str):
            return False

        message = (
            f"Atenção, o lote de {_format_date_str(date_str)} não pôde ser "
            f"processado após {attempts} tentativas."
        )
        logger.critical(
            "[D-1] %s",
            message,
            extra={
                "event_type": "huawei_d1_retry_exhausted",
                "date_str": date_str,
                "attempts": attempts,
            },
        )

        webhook_url = _get_failure_webhook_url()
        if webhook_url:
            await _send_failure_webhook(
                webhook_url,
                {
                    "event": "huawei_d1_retry_exhausted",
                    "date_str": date_str,
                    "attempts": attempts,
                    "message": message,
                    "last_error": last_error,
                },
            )
        return True

    @staticmethod
    def cleanup_old_runs(retention_days: int = RUN_RETENTION_DAYS) -> int:
        """Apaga runs mais antigos que `retention_days` (housekeeping).

        Calcula o corte em America/Sao_Paulo e deleta linhas com `date_str`
        (formato YYYYMMDD) anterior a ele. Retorna a quantidade removida.
        Escreve no banco (DELETE + commit).
        """
        cutoff = (datetime.now(SP_TZ) - timedelta(days=retention_days)).strftime("%Y%m%d")
        with database.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM huawei_d_minus_1_runs
                    WHERE date_str ~ '^[0-9]{8}$'
                      AND date_str < %s
                    """,
                    (cutoff,),
                )
                deleted = int(cur.rowcount or 0)
                conn.commit()
                return deleted


def _calc_date_str_d_minus_1() -> str:
    yesterday = datetime.now(SP_TZ) - timedelta(days=1)
    return yesterday.strftime("%Y%m%d")


def _format_date_str(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y%m%d").strftime("%d/%m/%Y")
    except ValueError:
        return date_str


def _calc_day_window_ms(date_str: str, begin_time_str: Optional[str] = None) -> tuple[int, int]:
    """Devolve (begin_ms, end_ms) cobrindo o dia `date_str` em America/Sao_Paulo.

    Início é meia-noite do dia (ou "HH:MM" se `begin_time_str` for dado e
    parseável); fim é 1s antes da meia-noite seguinte. Valores em epoch ms.
    """
    dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=SP_TZ)
    if begin_time_str:
        try:
            hh, mm = map(int, begin_time_str.split(":"))
            begin_dt = dt.replace(hour=hh, minute=mm)
            begin_ms = int(begin_dt.timestamp() * 1000)
        except Exception:
            begin_ms = int(dt.timestamp() * 1000)
    else:
        begin_ms = int(dt.timestamp() * 1000)
    end_ms = int((dt + timedelta(days=1, seconds=-1)).timestamp() * 1000)
    return begin_ms, end_ms


async def executar_d_minus_1(
    date_str: Optional[str] = None,
    *,
    force: bool = False,
    begin_time_str: Optional[str] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> dict:
    """Executa o pipeline D-1 para UMA data (default: ontem em America/Sao_Paulo).

    Passos: adquire o lock `huawei_d1_run_lock` em `configuracoes` (libera locks
    presos há +2h; se outra instância já roda, retorna status 'skipped');
    verifica no OBS se há áudio (`Voice/<date>/`) e manifesto CSV — se faltar,
    marca a data como 'empty' e devolve status *_will_retry; senão chama
    `executar_sync_huawei(obs_only=True)` para baixar/processar o lote.

    Ao fim calcula a cobertura (itens processados / linhas do manifesto) e
    classifica como 'completed' (>= HUAWEI_D_MINUS_1_COVERAGE_THRESHOLD, default
    0.8) ou 'partial', persistindo via `HuaweiDMinus1Tracker.mark_result`.

    Parâmetros:
    - date_str: data alvo YYYYMMDD; None usa D-1.
    - force: documentado no wrapper; aqui é só repassado a jusante.
    - begin_time_str: "HH:MM" para recortar o início da janela do dia.
    - should_cancel: callback de cancelamento cooperativo (verificado em
      pontos-chave; retorna status 'cancelled').
    - progress_callback: callback (stage, current, total) repassado ao sync.

    Retorno: dict com `status` ('completed'/'partial'/'skipped'/'cancelled'/
    'error'/obs_*_will_retry), `date_str`, e (quando processou) `coverage` e
    `result` do sync.

    Efeitos colaterais: banco (lock + tabela de runs), OBS/Huawei e tudo que o
    sync chamado dispara (download de áudio; transcrição/avaliação a jusante —
    aí sim há custo de API). O lock é sempre liberado no finally.
    """
    if not date_str:
        date_str = _calc_date_str_d_minus_1()

    logger.info(f"[D-1] Iniciando pipeline para data {date_str} (force={force}, begin_time={begin_time_str})")

    conn_lock = database.get_connection()
    try:
        cur_lock = conn_lock.cursor()
        
        cur_lock.execute(
            """
            INSERT INTO configuracoes (chave, valor, atualizado_em)
            VALUES ('huawei_d1_run_lock', 'false', CURRENT_TIMESTAMP)
            ON CONFLICT (chave) DO NOTHING
            """
        )
        conn_lock.commit()
        cur_lock.execute(
            """
            UPDATE configuracoes
            SET valor = 'running', atualizado_em = CURRENT_TIMESTAMP
            WHERE chave = 'huawei_d1_run_lock'
              AND (valor = 'false' OR CAST(atualizado_em AS timestamp) < CURRENT_TIMESTAMP - interval '2 hours')
            RETURNING chave
            """
        )
        lock_acquired = bool(cur_lock.fetchone())
        conn_lock.commit()
        
        if not lock_acquired:
            logger.info("[D-1] Outra instancia do pipeline D-1 ja esta rodando (db lock).")
            return {"status": "skipped", "message": "Pipeline D-1 ja em andamento."}

        run = HuaweiDMinus1Tracker.get_run(date_str)
        # Removido bloqueio de 'completed' para permitir busca contínua de novos arquivos (D-1 flexível).
        # A lógica de intervalo de retry no wrapper _pipeline já garante o espaçamento entre ciclos.

        if _cancel_requested(should_cancel):
            logger.warning("[D-1] Execucao cancelada antes de iniciar data %s.", date_str)
            return {"status": "cancelled", "date_str": date_str, "message": "Pipeline D-1 cancelado."}

        HuaweiDMinus1Tracker.mark_in_progress(date_str)

        from core.huawei_sync import _load_config
        cfg = _load_config()
        obs_kwargs = {
            "ak": cfg.get("obs_ak"),
            "sk": cfg.get("obs_sk"),
            "bucket": cfg.get("obs_bucket"),
            "endpoint": cfg.get("obs_endpoint"),
        }

        async with httpx.AsyncClient(timeout=120.0) as http_client:
            obs_client = HuaweiOBSClient(http_client=http_client, **obs_kwargs)

            if not await obs_client.voice_dir_has_objects(date_str):
                msg = f"Diretório Voice/{date_str}/ está vazio ou não existe no OBS."
                logger.warning(f"[D-1] {msg}")
                HuaweiDMinus1Tracker.mark_empty(date_str, "obs_voice_empty")
                return {"status": "obs_voice_empty_will_retry", "date_str": date_str}

            manifest_rows = await obs_client.listar_contact_record_rows(date_str)
            if not manifest_rows:
                msg = f"Nenhum manifesto CSV encontrado para {date_str} no OBS."
                logger.warning(f"[D-1] {msg}")
                HuaweiDMinus1Tracker.mark_empty(date_str, "obs_manifest_empty")
                return {"status": "obs_manifest_empty_will_retry", "date_str": date_str}

            begin_ms, end_ms = _calc_day_window_ms(date_str, begin_time_str)
            try:
                result = await executar_sync_huawei(
                    begin_time_ms=begin_ms,
                    end_time_ms=end_ms,
                    obs_only=True,
                    prefetched_obs_client=obs_client,
                    should_cancel=should_cancel,
                    progress_callback=progress_callback,
                )

                if str(result.get("status") or "").strip().lower() == "cancelled":
                    HuaweiDMinus1Tracker.mark_result(
                        date_str,
                        "cancelled",
                        result,
                        error=result.get("message") or "Pipeline D-1 cancelado.",
                    )
                    return {"status": "cancelled", "date_str": date_str, "result": result}

                manifest_count = len(manifest_rows)
                processed = (
                    result.get("baixadas", 0) +
                    result.get("ignoradas_ja_sincronizadas", 0) +
                    result.get("ignoradas_cota_mensal_pre_download", 0) +
                    result.get("ignoradas_mondelez", 0) +
                    result.get("ignoradas_setor_nao_telefonia", 0) +
                    result.get("ignoradas_operador_huawei_nao_cadastrado", 0) +
                    result.get("ignoradas_receptiva_setor_risco", 0) +
                    result.get("ignoradas_receptiva_setor_desconhecido", 0) +
                    result.get("ignoradas_direcao_desconhecida", 0) +
                    result.get("ignoradas_duracao_minima", 0) +
                    result.get("triagem_descartados", 0)
                )
                coverage = processed / manifest_count if manifest_count > 0 else 1.0
                threshold = float(os.getenv("HUAWEI_D_MINUS_1_COVERAGE_THRESHOLD", "0.8"))
                final_status = "completed" if coverage >= threshold else "partial"

                HuaweiDMinus1Tracker.mark_result(date_str, final_status, result)
                return {
                    "status": final_status,
                    "date_str": date_str,
                    "coverage": round(coverage, 2),
                    "result": result,
                }
            except Exception as e:
                logger.exception(f"[D-1] Erro durante execução do sync para {date_str}")
                HuaweiDMinus1Tracker.mark_result(date_str, "error", {"error": str(e)}, error=str(e))
                return {"status": "error", "date_str": date_str, "message": str(e)}
    finally:
        try:
            cur_lock = conn_lock.cursor()
            cur_lock.execute(
                """
                UPDATE configuracoes
                SET valor = 'false', atualizado_em = CURRENT_TIMESTAMP
                WHERE chave = 'huawei_d1_run_lock'
                  AND valor = 'running'
                """
            )
            conn_lock.commit()
        except Exception:
            try:
                conn_lock.rollback()
            except Exception:
                pass
            logger.warning("[D-1] Falha ao liberar lock huawei_d1_run_lock.", exc_info=True)
        finally:
            conn_lock.close()


# ────────────────────────────────────────────────────────────────────
# Wrapper de orquestração: aplica configs (horário, lookback, retry).
# Chamado pelo scheduler externo (Cloud Scheduler/Container Apps Job/Logic App)
# ou pela UI manual; nao ha loop residente.
# ────────────────────────────────────────────────────────────────────

def _parse_horario(raw: str, fallback: dt_time = dt_time(6, 0)) -> dt_time:
    try:
        hh, mm = raw.split(":")
        return dt_time(int(hh), int(mm))
    except Exception:
        return fallback


def _coerce_int(raw: Any, fallback: int) -> int:
    try:
        return int(str(raw).strip())
    except Exception:
        return fallback


def _cancel_requested(should_cancel: Optional[Callable[[], bool]]) -> bool:
    if should_cancel is None:
        return False
    try:
        return bool(should_cancel())
    except Exception as exc:
        logger.warning("[D-1] Callback de cancelamento falhou: %s", exc)
        return False


def _last_attempt_sp(run: Optional[dict]) -> Optional[datetime]:
    if not run:
        return None
    raw = run.get("last_attempt_at")
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            return None
    if not isinstance(raw, datetime):
        return None
    if raw.tzinfo is None:
        raw = raw.replace(tzinfo=timezone.utc)
    return raw.astimezone(SP_TZ)


def _is_retry_exhausted(run: Optional[dict], max_retries: int) -> bool:
    """True se a data já bateu `max_retries` e segue em estado não-terminal.

    Considera esgotado quando attempts >= max_retries E o status ainda é um dos
    que pediriam nova tentativa (empty/error/partial/obs_*_will_retry). Status
    'completed' nunca conta como esgotado.
    """
    if not run:
        return False
    status = (run or {}).get("status") or "pending"
    attempts = int((run or {}).get("attempts") or 0)
    return attempts >= max_retries and status in {
        "empty",
        "error",
        "partial",
        "obs_voice_empty_will_retry",
        "obs_manifest_empty_will_retry",
    }


def _get_failure_webhook_url() -> str:
    try:
        url = str(database.get_config_value("huawei_d1_failure_webhook_url", "") or "").strip()
    except Exception as exc:
        logger.warning("[D-1] Falha ao ler webhook de alerta D-1: %s", exc)
        url = ""
    return url or (os.getenv("HUAWEI_D1_FAILURE_WEBHOOK_URL") or "").strip()


async def _send_failure_webhook(webhook_url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as cli:
            response = await cli.post(webhook_url, json=payload)
            response.raise_for_status()
    except Exception as exc:
        logger.error("[D-1] Falha ao enviar webhook de alerta D-1: %s", exc)


async def _cleanup_d_minus_1_history() -> int:
    try:
        deleted = await asyncio.to_thread(HuaweiDMinus1Tracker.cleanup_old_runs, RUN_RETENTION_DAYS)
        if deleted:
            logger.info("[D-1] Housekeeping removeu %s execuções antigas.", deleted)
        return deleted
    except Exception as exc:
        logger.warning("[D-1] Falha no housekeeping de execuções antigas: %s", exc)
        return 0


def _deve_executar(
    run: Optional[dict],
    *,
    now_sp: datetime,
    horario_execucao: dt_time,
    max_retries: int,
    retry_intervalo: timedelta,
    is_today_d1: bool,
    force: bool = False,
) -> tuple[bool, str]:
    """Decide se o pipeline deve rodar para uma data com base no estado salvo.

    Quando force=True (acionado pelo botão Manual Executar via UI), bypassa
    os gates de retry — tentativas_esgotadas, horário programado e intervalo
    de retry.

    A pedido do usuário (2026-05-27), não há mais limite de ciclos por dia;
    mesmo estados 'completed' podem ser re-executados para buscar novos arquivos
    que possam ter subido para o OBS tardiamente.
    """
    status = (run or {}).get("status") or "pending"

    # 'completed' não bloqueia mais a execução (removido limite de ciclos diários).
    # O sistema apenas aguardará o intervalo de retry entre ciclos automáticos.

    if not force and _is_retry_exhausted(run, max_retries):
        return False, "tentativas_esgotadas"

    last_attempt_sp = _last_attempt_sp(run)

    # Para D-1 do dia atual: respeitar horário programado na primeira tentativa.
    if not force and is_today_d1 and not last_attempt_sp:
        if now_sp.time() < horario_execucao:
            return False, "antes_do_horario_programado"

    if not force and last_attempt_sp:
        elapsed = now_sp - last_attempt_sp
        if elapsed < retry_intervalo:
            return False, "aguardando_intervalo_retry"

    return True, "ok"


async def executar_d_minus_1_pipeline(
    *,
    should_cancel: Optional[Callable[[], bool]] = None,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    force: bool = False,
) -> dict:
    """Loop de orquestração. Lê configs e roda D-1 + lookback respeitando retry.

    Quando force=True, ignora gates de retry (tentativas_esgotadas, horário
    programado, intervalo de retry) — usado pelo botão Manual Executar para
    permitir re-baixar D-1 mesmo após o ciclo automático já ter desistido.
    """
    cfg = get_pipeline_config()

    if str(cfg["huawei_d1_enabled"]).strip().lower() != "true":
        return {"status": "disabled", "message": "Pipeline D-1 desligado nas configurações."}

    horario_exec = _parse_horario(cfg["huawei_d1_horario_execucao"])
    max_retries = max(1, _coerce_int(cfg["huawei_d1_max_retries"], 8))
    retry_min = max(1, _coerce_int(cfg["huawei_d1_retry_intervalo_minutos"], 60))
    lookback_dias = max(1, _coerce_int(cfg["huawei_d1_lookback_dias"], 3))

    retry_intervalo = timedelta(minutes=retry_min)
    now_sp = datetime.now(SP_TZ)

    executados: List[dict] = []
    pulados: List[dict] = []

    for offset in range(1, lookback_dias + 1):
        if _cancel_requested(should_cancel):
            return {
                "status": "cancelled",
                "now_sp": now_sp.isoformat(),
                "message": "Pipeline D-1 cancelado.",
                "config": {
                    "horario_execucao": cfg["huawei_d1_horario_execucao"],
                    "max_retries": max_retries,
                    "retry_intervalo_minutos": retry_min,
                    "lookback_dias": lookback_dias,
                },
                "executados": executados,
                "pulados": pulados,
            }

        target_date = now_sp - timedelta(days=offset)
        date_str = target_date.strftime("%Y%m%d")
        run = HuaweiDMinus1Tracker.get_run(date_str)

        deve, motivo = _deve_executar(
            run,
            now_sp=now_sp,
            horario_execucao=horario_exec,
            max_retries=max_retries,
            retry_intervalo=retry_intervalo,
            is_today_d1=(offset == 1),
            force=force,
        )

        if not deve:
            retry_alerted = False
            if motivo == "tentativas_esgotadas":
                retry_alerted = await HuaweiDMinus1Tracker.notify_retry_exhausted(
                    date_str,
                    attempts=int((run or {}).get("attempts") or 0),
                    last_error=(run or {}).get("last_error"),
                )
            pulados.append({"date_str": date_str, "motivo": motivo,
                           "status_atual": (run or {}).get("status", "pending"),
                           "alertado": retry_alerted})
            continue

        try:
            result = await executar_d_minus_1(
                date_str,
                should_cancel=should_cancel,
                progress_callback=progress_callback,
                force=force,
            )
            executados.append({"date_str": date_str, **result})
            if str(result.get("status") or "").strip().lower() == "cancelled":
                break
            latest_run = HuaweiDMinus1Tracker.get_run(date_str)
            if _is_retry_exhausted(latest_run, max_retries):
                await HuaweiDMinus1Tracker.notify_retry_exhausted(
                    date_str,
                    attempts=int((latest_run or {}).get("attempts") or 0),
                    last_error=(latest_run or {}).get("last_error"),
                )
        except Exception as exc:
            logger.exception("[D-1 pipeline] Erro inesperado processando %s", date_str)
            executados.append({"date_str": date_str, "status": "error", "message": str(exc)})

    cleanup_deleted = await _cleanup_d_minus_1_history()
    executed_statuses = {
        str(item.get("status") or "").strip().lower()
        for item in executados
        if isinstance(item, dict)
    }
    if "cancelled" in executed_statuses:
        pipeline_status = "cancelled"
    elif executed_statuses and executed_statuses <= {"error", "missing_credentials"}:
        pipeline_status = "error"
    elif executed_statuses.intersection({"error", "missing_credentials", "partial"}):
        pipeline_status = "partial"
    else:
        pipeline_status = "ok"

    return {
        "status": pipeline_status,
        "now_sp": now_sp.isoformat(),
        "config": {
            "horario_execucao": cfg["huawei_d1_horario_execucao"],
            "max_retries": max_retries,
            "retry_intervalo_minutos": retry_min,
            "lookback_dias": lookback_dias,
        },
        "executados": executados,
        "pulados": pulados,
        "housekeeping": {
            "retention_days": RUN_RETENTION_DAYS,
            "deleted_runs": cleanup_deleted,
        },
    }
