"""Repository da fila de revisão de classificação (`fila_revisao_classificacao`).

Coração da triagem: cada gravação que entra no sistema (sync Huawei D-1 ou
upload manual no Classificador) vira UMA linha nesta fila, deduplicada pelo
`input_hash` (UNIQUE, hash do conteúdo do arquivo). A linha carrega a
classificação prevista (setor/alerta/operador), confiança, prioridade,
motivos de revisão e um `metadata_json` rico (origem, ids Huawei, caminho da
mídia classificada, flags de processamento) — o payload parseado devolvido
por este módulo é contrato público para a UI de triagem, a automação e os
relatórios.

Posição no fluxo: sync Huawei → classificação GPT → ESTA FILA → automação
audita os itens READY (`core/automation.py`) → "Arquivos Salvos"
(`awaiting_pair`) → revisão humana → fechamento.

Ciclo de vida (constantes em `db/domain_constants.py`):
- `downloaded`        → baixado do Huawei, aguardando classificação (fase 2);
- `pending` / `needs_manual_triage` / `blocked_operator` → exigem triagem humana;
- `auto_resolved` / `reviewed` → READY: elegíveis à auditoria automática;
- `audited`           → terminal: já virou auditoria em Arquivos Salvos;
- `monthly_capped`    → retido por cota mensal do operador; volta a ser
  elegível quando o período (YYYY-MM) gravado no metadata difere do corrente;
- `ready_for_audit` e `all` são status VIRTUAIS de consulta — nunca persistidos.

Descarte (esteira binária v1.3.103): item que não presta NÃO fica preso — a
linha é removida da fila e o `huawei_sync_logs` vira tombstone:
`discarded_permanent` (lixo definitivo; nunca reentra) ou
`discarded_recoverable` (falha técnica transitória; pode voltar num próximo
sync até o limite anti-loop, quando é promovido a permanente).

CUSTO DE API: módulo é quase todo acesso a banco (sem custo Azure). Exceção
pontual: `corrigir_classificacao_fila_revisao` dispara o gatilho RLHF quando
o humano contradiz a IA — 1 chamada de embedding (Azure OpenAI) por correção.

O dataset de benchmark de classificação (`ligacoes_auditadas` +
`resultados_classificacao` + `resultados_auditoria`: gabarito humano para medir
a taxa de acerto de setor/alerta da IA) foi extraído para
`classification_review_benchmark.py` (v1.3.141) e é reexportado daqui para
compatibilidade.

Todas as funções públicas recebem `get_connection` (factory) e gerenciam a
própria conexão/transação; helpers que recebem cursor explícito rodam dentro
da transação do caller.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Any

from db.domain_constants import (
    REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    REVIEW_QUEUE_MANUAL_TRIAGE_STATUSES,
    REVIEW_QUEUE_READY_STATUSES,
    REVIEW_QUEUE_STATUS_ALL,
    REVIEW_QUEUE_STATUS_AUTO_RESOLVED,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_STATUS_READY_FOR_AUDIT,
    REVIEW_QUEUE_STATUS_REVIEWED,
    REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY,
)
from repositories.common import (
    extract_returning_id,
    json_loads,
    normalize_review_priority,
    normalize_review_status,
    normalize_sector_id as _normalize_sector_id,
)

# Dataset de benchmark (ground truth) extraido para modulo proprio; reexportado
# aqui p/ manter `repositories.classification_review.<nome>` e a fachada
# db.database validos (v1.3.141).
from repositories.classification_review_benchmark import (  # noqa: E402,F401
    upsert_ligacao_auditada,
    get_ligacao_auditada_por_hash,
    registrar_resultado_classificacao,
    registrar_resultado_auditoria,
    get_resumo_ligacoes_auditadas,
    listar_ligacoes_auditadas,
)

# Purga/descarte de itens da fila extraido para modulo proprio (v1.3.143);
# reexportado para manter os imports diretos e a fachada db.database validos.
from repositories.classification_review_purge import (  # noqa: E402,F401
    limpar_fila_revisao_classificacao_antiga,
    descartar_item_automacao,
    _purgar_item_fila,
    _unlink_item_media,
)

# Helpers de metadata extraidos (v1.3.144); usados pelas transicoes abaixo e
# pelas consultas. Importa-los aqui tambem preserva o namespace
# `classification_review._normalize_metadata_value` para compat.
from repositories.classification_review_helpers import (  # noqa: E402,F401
    _normalize_metadata_value,
    _parse_metadata_datetime,
)

# Consultas (read-only) da fila extraidas para modulo proprio (v1.3.144);
# reexportadas para compat (import direto + fachada db.database).
from repositories.classification_review_queries import (  # noqa: E402,F401
    listar_fila_revisao_classificacao,
    obter_fila_revisao_classificacao_por_hash,
    obter_fila_revisao_classificacao_por_auditoria,
    listar_paths_audio_classificado_fila_revisao,
)


# ── Constantes e helpers internos ────────────────────────────────────────────

ConnectionFactory = Callable[[], Any]

# Statuses que um re-sync NÃO pode sobrescrever: ou representam trabalho humano
# já concluído (reviewed/audited), ou decisões de gate tomadas pelo pipeline
# (monthly_capped/needs_manual_triage/blocked_operator). Para eles,
# `sincronizar_fila_revisao_classificacao` devolve o id existente sem alterar a linha.
PROTECTED_SYNC_STATUSES = (
    REVIEW_QUEUE_STATUS_REVIEWED,
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
)

# Statuses que impedem abrir nova task de auditoria em background para o item
# (ver `tentar_iniciar_processamento_auditoria`): ou já foi auditado, ou está
# retido por um gate que a auditoria disparada manualmente não deve atropelar.
AUDIT_TASK_BLOCKED_STATUSES = {
    REVIEW_QUEUE_STATUS_AUDITED,
    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
    REVIEW_QUEUE_STATUS_NEEDS_MANUAL_TRIAGE,
    REVIEW_QUEUE_STATUS_BLOCKED_OPERATOR,
}


# ── Upsert e transições de status da fila ────────────────────────────────────


def sincronizar_fila_revisao_classificacao(
    get_connection: ConnectionFactory,
    input_hash: str,
    nome_arquivo: str,
    setor_previsto: Optional[str] = None,
    alerta_previsto: Optional[str] = None,
    confianca: Optional[float] = None,
    operador_previsto: Optional[str] = None,
    erro: Optional[str] = None,
    precisa_revisao: bool = False,
    prioridade: str = REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    motivos_revisao: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
    status_override: Optional[str] = None,
) -> Optional[int]:
    """Insere ou atualiza (dedupe por `input_hash`) um item na fila de revisão.

    Porta de entrada única da fila — usada pelo sync Huawei (enqueue) e pelo
    classificador manual. Regras:
    - Tombstone permanente: se a origem é huawei_sync e o call_id está
      'discarded_permanent' no huawei_sync_logs, o item NÃO reentra (retorna None);
    - Statuses protegidos (PROTECTED_SYNC_STATUSES): a linha existente não é
      sobrescrita; retorna o id atual sem alterar nada;
    - Status calculado: `pending` quando `precisa_revisao`, senão `auto_resolved`
      (elegível à automação) — salvo `status_override` explícito.

    Retorna o id da linha (None quando bloqueado por tombstone).
    """
    if not input_hash or not nome_arquivo:
        raise ValueError("input_hash e nome_arquivo são obrigatórios")

    now = datetime.now().isoformat()
    motivos_json = json.dumps(motivos_revisao or [], ensure_ascii=False)
    metadata_json = json.dumps(metadata or {}, ensure_ascii=False)
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    huawei_call_id = str(metadata_dict.get("huawei_call_id") or "").strip()
    origem_metadata = str(metadata_dict.get("origem") or "").strip().lower()
    
    if status_override:
        status = status_override
    else:
        status = REVIEW_QUEUE_STATUS_PENDING if precisa_revisao else REVIEW_QUEUE_STATUS_AUTO_RESOLVED
        
    setor_previsto_normalizado = _normalize_sector_id(setor_previsto)
    prioridade_normalizada = normalize_review_priority(
        prioridade,
        default=REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY if not precisa_revisao else REVIEW_QUEUE_APPLICATION_DEFAULT_PRIORITY,
    )

    conn = get_connection()
    try:
        cursor = conn.cursor()
        if origem_metadata == "huawei_sync" and huawei_call_id:
            cursor.execute(
                """
                SELECT 1
                FROM huawei_sync_logs
                WHERE call_id = %s
                  AND status = 'discarded_permanent'
                LIMIT 1
                """,
                (huawei_call_id,),
            )
            if cursor.fetchone():
                conn.rollback()
                return None

        cursor.execute(
            "SELECT id, status FROM fila_revisao_classificacao WHERE input_hash = %s",
            (input_hash,),
        )
        row = cursor.fetchone()

        if row:
            current_status = normalize_review_status(row.get("status"))
            if current_status in PROTECTED_SYNC_STATUSES:
                return int(row["id"])
            cursor.execute(
                """
                UPDATE fila_revisao_classificacao
                SET nome_arquivo = %s, setor_previsto = %s, alerta_previsto = %s, confianca = %s,
                    operador_previsto = %s, erro = %s, prioridade = %s, motivos_json = %s,
                    metadata_json = %s, status = %s, atualizado_em = %s
                WHERE input_hash = %s
                """,
                (
                    nome_arquivo,
                    setor_previsto_normalizado,
                    alerta_previsto,
                    confianca,
                    operador_previsto,
                    erro,
                    prioridade_normalizada,
                    motivos_json,
                    metadata_json,
                    status,
                    now,
                    input_hash,
                ),
            )
            conn.commit()
            return int(row["id"])

        cursor.execute(
            """
            INSERT INTO fila_revisao_classificacao (
                input_hash, nome_arquivo, setor_previsto, alerta_previsto,
                confianca, operador_previsto, erro, prioridade,
                motivos_json, metadata_json, status, criado_em, atualizado_em
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                input_hash,
                nome_arquivo,
                setor_previsto_normalizado,
                alerta_previsto,
                confianca,
                operador_previsto,
                erro,
                prioridade_normalizada,
                motivos_json,
                metadata_json,
                status,
                now,
                now,
            ),
        )
        review_id = extract_returning_id(cursor.fetchone())
        conn.commit()
        return review_id
    finally:
        conn.close()


def tentar_iniciar_processamento_auditoria(
    get_connection: ConnectionFactory,
    input_hash: str,
    *,
    status: str,
    metadata_merge: dict,
    inflight_timeout_seconds: int = 600,
    ignore_status_block: bool = False,
) -> dict:
    """Marca uma gravação como em processamento com lock transacional (claim).

    A rota de auditoria em background pode receber dois cliques quase
    simultâneos. O `SELECT ... FOR UPDATE` serializa essas chamadas para que
    apenas uma delas saia com permissão de criar a task. Recusa quando:
    - o item não existe → {"started": False, "reason": "not_found"};
    - o status atual está em AUDIT_TASK_BLOCKED_STATUSES e
      `ignore_status_block` é False → reason "blocked_status";
    - já existe task viva (metadata.audit_task_status == "processing" iniciada
      há menos de `inflight_timeout_seconds`) → reason "processing". Passado o
      timeout, o claim anterior é tratado como órfão e pode ser retomado.

    Em sucesso aplica `status` + `metadata_merge` na linha (commit) e retorna
    {"started": True, "status": ..., "started_at": ...}.
    """
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")

    timeout = timedelta(seconds=max(1, int(inflight_timeout_seconds or 600)))
    now = datetime.now(timezone.utc)
    now_text = now.isoformat()
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT status, metadata_json
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            FOR UPDATE
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return {"started": False, "reason": "not_found"}

        current_status = normalize_review_status(row["status"])
        metadata = _normalize_metadata_value(row["metadata_json"])
        if current_status in AUDIT_TASK_BLOCKED_STATUSES and not ignore_status_block:
            conn.rollback()
            return {
                "started": False,
                "reason": "blocked_status",
                "status": current_status,
            }

        task_status = str(metadata.get("audit_task_status") or "").strip().lower()
        started_at = _parse_metadata_datetime(metadata.get("audit_task_started_at"))
        if task_status == "processing" and started_at and (now - started_at) < timeout:
            conn.rollback()
            return {
                "started": False,
                "reason": "processing",
                "status": current_status,
                "started_at": metadata.get("audit_task_started_at"),
            }

        metadata.update(metadata_merge or {})
        normalized_status = normalize_review_status(status or current_status)
        cursor.execute(
            """
            UPDATE fila_revisao_classificacao
            SET status = %s,
                metadata_json = %s,
                atualizado_em = %s
            WHERE input_hash = %s
            """,
            (
                normalized_status,
                json.dumps(metadata, ensure_ascii=False),
                now_text,
                input_hash,
            ),
        )
        conn.commit()
        return {
            "started": True,
            "status": normalized_status,
            "started_at": metadata.get("audit_task_started_at"),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def atualizar_status_fila_revisao_classificacao(
    get_connection: ConnectionFactory,
    input_hash: str,
    *,
    status: str,
    erro: Optional[str] = None,
    motivos_revisao_append: Optional[list[str]] = None,
    metadata_merge: Optional[dict] = None,
) -> bool:
    """Transiciona o status de um item e faz merge incremental de motivos/metadata.

    - `motivos_revisao_append`: anexa motivos novos sem duplicar (preserva ordem);
    - `metadata_merge`: update raso (shallow) sobre o metadata existente;
    - `erro=None` preserva o erro atual (passar string vazia para limpar);
    - statuses VIRTUAIS de consulta (`all`, `ready_for_audit`) são rejeitados
      com ValueError — nunca devem ser persistidos.

    Retorna True se o item existia e foi atualizado; False caso contrário.
    """
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")

    status_normalizado = normalize_review_status(status)
    if status_normalizado in {REVIEW_QUEUE_STATUS_ALL, REVIEW_QUEUE_STATUS_READY_FOR_AUDIT}:
        raise ValueError("status de consulta nao pode ser persistido")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT erro, motivos_json, metadata_json
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return False

        motivos_existentes = json_loads(row["motivos_json"], [])
        if not isinstance(motivos_existentes, list):
            motivos_existentes = []
        novos_motivos = [str(item).strip() for item in (motivos_revisao_append or []) if str(item).strip()]
        motivos_atualizados = list(dict.fromkeys([*motivos_existentes, *novos_motivos]))

        metadata_atual = _normalize_metadata_value(row["metadata_json"])
        if metadata_merge:
            metadata_atual.update(metadata_merge)

        erro_atualizado = row["erro"] if erro is None else erro

        cursor.execute(
            """
            UPDATE fila_revisao_classificacao
            SET status = %s,
                erro = %s,
                motivos_json = %s,
                metadata_json = %s,
                atualizado_em = %s
            WHERE input_hash = %s
            """,
            (
                status_normalizado,
                erro_atualizado,
                json.dumps(motivos_atualizados, ensure_ascii=False),
                json.dumps(metadata_atual, ensure_ascii=False),
                datetime.now().isoformat(),
                input_hash,
            ),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def corrigir_classificacao_fila_revisao(
    get_connection: ConnectionFactory,
    input_hash: str,
    *,
    setor_previsto: str,
    alerta_previsto: str,
    operador_previsto: Optional[str] = None,
    operator_id: Optional[str] = None,
    revisado_por: Optional[str] = None,
) -> Optional[dict]:
    """Aplica correção humana de setor/alerta a um item da fila (triagem manual).

    Sobrescreve a classificação da IA, registra quem revisou em
    `motivos_revisao` e promove o item para o fluxo de auditoria.
    Retorna o item atualizado ou None se o hash não existir.
    """
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")
    if not setor_previsto or not alerta_previsto:
        raise ValueError("setor_previsto e alerta_previsto sao obrigatorios")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        metadata_atual = _normalize_metadata_value(row["metadata_json"])
        previous_classification = {
            "setor_previsto": row["setor_previsto"],
            "alerta_previsto": row["alerta_previsto"],
            "erro": row["erro"],
            "motivos_revisao": json_loads(row["motivos_json"], []),
            "status": row["status"],
        }
        metadata_atual["manual_review_source"] = "triagem_ui"
        metadata_atual["manual_reviewed_at"] = datetime.now().isoformat()
        metadata_atual["manual_reviewed_by"] = revisado_por or ""
        metadata_atual["manual_review_previous"] = previous_classification
        # v1.3.96: correcao manual finaliza a classificacao do item. Frontend
        # (RemoteTriageQueue.tsx) le metadata.classification_status para
        # decidir se mostra o botao "Triar"; sem este flip o botao reaparece
        # mesmo com setor/alerta ja preenchidos.
        metadata_atual["classification_status"] = "done"
        metadata_atual["classification_error"] = None
        metadata_atual["manual_review_current"] = {
            "setor_previsto": _normalize_sector_id(setor_previsto),
            "alerta_previsto": alerta_previsto,
            "operador_previsto": operador_previsto,
            "operator_id": operator_id,
            "status": REVIEW_QUEUE_STATUS_REVIEWED,
        }
        if operator_id:
            metadata_atual["operator_id"] = operator_id

        cursor.execute(
            """
            UPDATE fila_revisao_classificacao
            SET setor_previsto = %s,
                alerta_previsto = %s,
                operador_previsto = COALESCE(NULLIF(%s, ''), operador_previsto),
                erro = NULL,
                prioridade = %s,
                motivos_json = %s,
                metadata_json = %s,
                status = %s,
                atualizado_em = %s
            WHERE input_hash = %s
            """,
            (
                _normalize_sector_id(setor_previsto),
                alerta_previsto,
                str(operador_previsto or "").strip(),
                REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY,
                json.dumps([], ensure_ascii=False),
                json.dumps(metadata_atual, ensure_ascii=False),
                REVIEW_QUEUE_STATUS_REVIEWED,
                datetime.now().isoformat(),
                input_hash,
            ),
        )
        conn.commit()

        cursor.execute(
            """
            SELECT *
            FROM fila_revisao_classificacao
            WHERE input_hash = %s
            """,
            (input_hash,),
        )
        updated = cursor.fetchone()
        if not updated:
            return None

        result = {
            "id": updated["id"],
            "input_hash": updated["input_hash"],
            "nome_arquivo": updated["nome_arquivo"],
            "setor_previsto": updated["setor_previsto"],
            "alerta_previsto": updated["alerta_previsto"],
            "confianca": updated["confianca"],
            "operador_previsto": updated["operador_previsto"],
            "erro": updated["erro"],
            "prioridade": updated["prioridade"],
            "motivos_revisao": json_loads(updated["motivos_json"], []),
            "metadata": json_loads(updated["metadata_json"], {}),
            "status": updated["status"],
            "criado_em": updated["criado_em"],
            "atualizado_em": updated["atualizado_em"],
        }
    finally:
        conn.close()

    # === GATILHO DE APRENDIZADO (RLHF) ===
    # Se a IA errou e o humano corrigiu, gera feedback automáticocom embedding
    # para alimentar o RAG semântico nas próximas classificações.
    try:
        ia_alerta = previous_classification.get("alerta_previsto")
        ia_setor = previous_classification.get("setor_previsto")
        # Só aciona se a IA deu uma resposta diferente da correção humana
        if ia_alerta and ia_alerta != alerta_previsto and ia_alerta != "desconhecido":
            transcricao = metadata_atual.get("transcription", "") or ""
            from core.rag_triagem import disparar_feedback_rag_background
            disparar_feedback_rag_background(
                tipo="classificacao",
                situacao=f"A IA classificou como setor='{ia_setor}' alerta='{ia_alerta}'.",
                correcao=f"O correto e setor='{_normalize_sector_id(setor_previsto)}' alerta='{alerta_previsto}'.",
                justificativa="Correcao manual do auditor na fila de triagem.",
                setor=_normalize_sector_id(setor_previsto),
                criado_por=revisado_por or "sistema_rlhf",
                exemplo_transcricao=transcricao[:2000] if transcricao else None,
            )
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Falha ao acionar RAG RLHF: %s", exc)

    return result
