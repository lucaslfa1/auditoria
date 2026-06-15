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

import contextlib
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


def _normalize_metadata_value(value: Optional[object]) -> dict:
    """Converte `metadata_json` (dict ou string JSON) em dict mutável; inválido vira {}."""
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json_loads(value, {})
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_metadata_datetime(value: Any) -> Optional[datetime]:
    """Interpreta timestamp ISO vindo do metadata; retorna datetime UTC-aware ou None.

    Aceita sufixo "Z" e assume UTC quando o valor é naive (sem timezone),
    para permitir comparação segura com `datetime.now(timezone.utc)`.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


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


def listar_fila_revisao_classificacao(
    get_connection: ConnectionFactory,
    limit: Optional[int] = None,
    status: Optional[str] = REVIEW_QUEUE_STATUS_PENDING,
    sector_id: Optional[str] = None,
    origem: Optional[str] = None,
    order_by: str = "priority",
) -> list[dict]:
    """Lista itens da fila de triagem com filtros de status/setor/origem.

    `status=ready_for_audit` tem regra especial: além dos statuses prontos,
    inclui itens `monthly_capped` de períodos ANTERIORES (a trava de cota
    mensal expira na virada do mês e o item volta a ser elegível).
    `status=pending` unifica auto e manual na mesma lista (v1.3.92).
    """
    status_normalizado = normalize_review_status(status)

    conn = get_connection()
    try:
        cursor = conn.cursor()
        filtros = []
        params: list = []

        if status_normalizado == REVIEW_QUEUE_STATUS_READY_FOR_AUDIT:
            current_period = datetime.now().strftime("%Y-%m")
            filtros.append(
                """
                (
                    status = ANY(%s)
                    OR (
                        status = %s
                        AND COALESCE((metadata_json::jsonb ->> 'monthly_cap_period'), '') <> %s
                    )
                )
                """
            )
            params.extend(
                [
                    list(REVIEW_QUEUE_READY_STATUSES),
                    REVIEW_QUEUE_STATUS_MONTHLY_CAPPED,
                    current_period,
                ]
            )
        elif status_normalizado == REVIEW_QUEUE_STATUS_PENDING:
            # Fluxo unificado (v1.3.92): auto e manual aparecem juntos em Triagem.
            # A distincao visual fica no badge "Auto" do frontend, que olha
            # metadata.is_manual + metadata.origem. Antes existia um NOT clause
            # que escondia huawei_sync com classification_status='pending' ate a
            # fase 2 rodar, mas Lucas pediu fluxo unico.
            filtros.append(
                """
                (
                    status = %s
                    OR status = ANY(%s)
                    OR (
                        status = 'downloaded'
                        AND COALESCE(metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
                    )
                )
                """
            )
            params.extend(
                [
                    status_normalizado,
                    [
                        item
                        for item in REVIEW_QUEUE_MANUAL_TRIAGE_STATUSES
                        if item != REVIEW_QUEUE_STATUS_PENDING
                    ],
                ]
            )
        elif status_normalizado != REVIEW_QUEUE_STATUS_ALL:
            filtros.append("status = %s")
            params.append(status_normalizado)
        if sector_id:
            filtros.append("COALESCE(setor_previsto, '') = %s")
            params.append(_normalize_sector_id(sector_id) or "")
        if origem:
            filtros.append("metadata_json::jsonb ->> 'origem' = %s")
            params.append(origem)

        where_clause = f"WHERE {' AND '.join(filtros)}" if filtros else ""
        
        if order_by == "recent":
            order_clause = "ORDER BY atualizado_em DESC, id DESC"
        else:
            order_clause = "ORDER BY CASE prioridade WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, atualizado_em DESC, id DESC"
            
        limit_clause = "LIMIT %s" if limit is not None else ""
        
        query = f"""
            SELECT f.*,
                   official_by_huawei.nome AS official_operator_name,
                   official_by_huawei.id_huawei AS official_operator_id_huawei,
                   CASE
                       WHEN COALESCE(f.metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
                           THEN official_by_huawei.id_huawei IS NOT NULL
                       ELSE EXISTS(SELECT 1
                                      FROM colaboradores c
                                      WHERE LOWER(TRIM(c.nome)) = LOWER(TRIM(COALESCE(NULLIF(f.operador_previsto, ''), f.metadata_json::jsonb ->> 'operator_name')))
                                         AND c.status = 'ATIVO'
                                    )
                   END as is_oficial
            FROM fila_revisao_classificacao f
            LEFT JOIN LATERAL (
                SELECT c.nome, c.id_huawei
                FROM colaboradores c
                WHERE c.status = 'ATIVO'
                  AND COALESCE(c.auditavel, 1) = 1
                  AND COALESCE(NULLIF(TRIM(c.id_huawei), ''), '') <> ''
                  AND TRIM(c.id_huawei) = COALESCE(
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id_huawei_real'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'id_huawei'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_work_no'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_agent_id'), '')
                  )
                ORDER BY
                    CASE WHEN UPPER(c.status) = 'ATIVO' THEN 0 ELSE 1 END,
                    CASE WHEN COALESCE(c.auditavel, 1) = 1 THEN 0 ELSE 1 END,
                    c.atualizado_em DESC NULLS LAST,
                    c.nome
                LIMIT 1
            ) official_by_huawei ON TRUE
            {where_clause}
            {order_clause}
            {limit_clause}
        """
        if limit is not None:
            params.append(limit)
            
        cursor.execute(query, params)
        rows = cursor.fetchall()
    finally:
        conn.close()

    items: list[dict] = []
    for row in rows:
        metadata = json_loads(row["metadata_json"], {})
        if not isinstance(metadata, dict):
            metadata = {}
        official_operator_name = row["official_operator_name"] if "official_operator_name" in row.keys() else None
        official_operator_id_huawei = (
            row["official_operator_id_huawei"] if "official_operator_id_huawei" in row.keys() else None
        )
        operator_name = (
            official_operator_name
            or row["operador_previsto"]
            or metadata.get("operator_name")
            or metadata.get("operator_name_real")
            or metadata.get("huawei_operator_name")
        )
        operator_id = (
            official_operator_id_huawei
            or metadata.get("operator_id_huawei_real")
            or metadata.get("id_huawei")
            or metadata.get("operator_id")
            or metadata.get("operator_matricula")
            or metadata.get("matricula")
            or metadata.get("huawei_agent_id")
        )
        items.append(
            {
                "id": row["id"],
                "input_hash": row["input_hash"],
                "nome_arquivo": row["nome_arquivo"],
                "setor_previsto": row["setor_previsto"] or metadata.get("operator_sector_id"),
                "alerta_previsto": row["alerta_previsto"],
                "confianca": row["confianca"],
                "operador_previsto": row["operador_previsto"],
                "operator_name": operator_name,
                "operator_id": operator_id,
                "erro": row["erro"],
                "prioridade": row["prioridade"],
                "motivos_revisao": json_loads(row["motivos_json"], []),
                "metadata": metadata,
                "status": row["status"],
                "criado_em": row["criado_em"],
                "atualizado_em": row["atualizado_em"],
                "is_oficial": row["is_oficial"],
            }
        )
    return items


def obter_fila_revisao_classificacao_por_hash(
    get_connection: ConnectionFactory,
    input_hash: str,
) -> Optional[dict]:
    """Busca um item da fila pelo `input_hash` (chave de dedupe da gravação).

    Inclui o flag `is_oficial` calculado (operador cadastrado e ATIVO em
    `colaboradores`) com a mesma regra da listagem.
    """
    if not input_hash:
        raise ValueError("input_hash e obrigatorio")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        # is_oficial replicado de listar_fila_revisao_classificacao: huawei_sync
        # casa por id_huawei; demais origens casam por nome do operador.
        cursor.execute(
            """
            SELECT f.*,
                   CASE
                       WHEN COALESCE(f.metadata_json::jsonb ->> 'origem', '') = 'huawei_sync'
                           THEN official_by_huawei.id_huawei IS NOT NULL
                       ELSE EXISTS(SELECT 1
                                      FROM colaboradores c
                                      WHERE LOWER(TRIM(c.nome)) = LOWER(TRIM(COALESCE(NULLIF(f.operador_previsto, ''), f.metadata_json::jsonb ->> 'operator_name')))
                                         AND c.status = 'ATIVO'
                                    )
                   END as is_oficial
            FROM fila_revisao_classificacao f
            LEFT JOIN LATERAL (
                SELECT c.id_huawei
                FROM colaboradores c
                WHERE c.status = 'ATIVO'
                  AND COALESCE(c.auditavel, 1) = 1
                  AND COALESCE(NULLIF(TRIM(c.id_huawei), ''), '') <> ''
                  AND TRIM(c.id_huawei) = COALESCE(
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id_huawei_real'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'id_huawei'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'operator_id'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_work_no'), ''),
                      NULLIF(TRIM(f.metadata_json::jsonb ->> 'huawei_agent_id'), '')
                  )
                ORDER BY
                    CASE WHEN UPPER(c.status) = 'ATIVO' THEN 0 ELSE 1 END,
                    CASE WHEN COALESCE(c.auditavel, 1) = 1 THEN 0 ELSE 1 END,
                    c.atualizado_em DESC NULLS LAST,
                    c.nome
                LIMIT 1
            ) official_by_huawei ON TRUE
            WHERE f.input_hash = %s
            LIMIT 1
            """,
            (input_hash,),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row["id"],
            "input_hash": row["input_hash"],
            "nome_arquivo": row["nome_arquivo"],
            "setor_previsto": row["setor_previsto"],
            "alerta_previsto": row["alerta_previsto"],
            "confianca": row["confianca"],
            "operador_previsto": row["operador_previsto"],
            "erro": row["erro"],
            "prioridade": row["prioridade"],
            "motivos_revisao": json_loads(row["motivos_json"], []),
            "metadata": json_loads(row["metadata_json"], {}),
            "status": row["status"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
            "is_oficial": row["is_oficial"],
        }
    finally:
        conn.close()


def obter_fila_revisao_classificacao_por_auditoria(
    get_connection: ConnectionFactory,
    audit_id: int,
    audit_input_hash: Optional[str] = None,
) -> Optional[dict]:
    """Localiza o item da fila vinculado a uma auditoria já criada.

    O vínculo vive em `metadata.audit_id` / `metadata.audit_input_hash`
    (gravados quando a auditoria nasce do item). Retorna o mais recente.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM fila_revisao_classificacao
            WHERE COALESCE((metadata_json::jsonb ->> 'audit_id'), '') = %s
               OR (
                    %s <> ''
                    AND COALESCE((metadata_json::jsonb ->> 'audit_input_hash'), '') = %s
               )
            ORDER BY atualizado_em DESC, id DESC
            LIMIT 1
            """,
            (str(audit_id), str(audit_input_hash or ""), str(audit_input_hash or "")),
        )
        row = cursor.fetchone()
        if not row:
            return None

        return {
            "id": row["id"],
            "input_hash": row["input_hash"],
            "nome_arquivo": row["nome_arquivo"],
            "setor_previsto": row["setor_previsto"],
            "alerta_previsto": row["alerta_previsto"],
            "confianca": row["confianca"],
            "operador_previsto": row["operador_previsto"],
            "erro": row["erro"],
            "prioridade": row["prioridade"],
            "motivos_revisao": json_loads(row["motivos_json"], []),
            "metadata": json_loads(row["metadata_json"], {}),
            "status": row["status"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
        }
    finally:
        conn.close()


def listar_paths_audio_classificado_fila_revisao(
    get_connection: ConnectionFactory,
) -> list[str]:
    """Lista os paths de áudio classificado (`metadata.classified_audio_path`).

    Usado pela limpeza de storage para saber quais arquivos ainda têm dono.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT metadata_json
            FROM fila_revisao_classificacao
            WHERE metadata_json IS NOT NULL
              AND metadata_json != ''
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    paths: list[str] = []
    for row in rows:
        metadata = _normalize_metadata_value(row["metadata_json"])
        path = str(metadata.get("classified_audio_path") or "").strip()
        if path:
            paths.append(path)
    return paths
