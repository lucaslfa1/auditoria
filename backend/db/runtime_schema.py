
from .domain_constants import (
    DEFAULT_AUDIT_SCOPE,
    DEFAULT_AUDIT_STATUS,
    DEFAULT_SOURCE_TYPE,
    DEFAULT_USER_ROLE,
    REVIEW_QUEUE_STATUS_PENDING,
    REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY,
)
from .schema_tools import ensure_column, get_existing_columns

CALL_QUALITY_SCOPE = DEFAULT_AUDIT_SCOPE


def _get_row_value(row, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    if hasattr(row, 'keys'):
        return row[key] if key in row.keys() else default
    return default


def _get_audit_scope(row) -> str:
    stored_scope = _get_row_value(row, "audit_scope")
    if stored_scope == CALL_QUALITY_SCOPE:
        return stored_scope
    return CALL_QUALITY_SCOPE


def _sync_audit_scopes(cursor) -> None:
    cursor.execute("SELECT id, source_type, audio_quality, audit_scope FROM audits")
    rows = cursor.fetchall()
    for row in rows:
        resolved_scope = _get_audit_scope(row)
        if _get_row_value(row, "audit_scope") != resolved_scope:
            cursor.execute("UPDATE audits SET audit_scope = %s WHERE id = %s", (resolved_scope, row["id"]))


def ensure_gestor_feedbacks_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS gestor_feedbacks (
            id SERIAL PRIMARY KEY,
            audit_id INTEGER NOT NULL UNIQUE,
            gestor_nome TEXT NOT NULL,
            feedback_texto TEXT NOT NULL,
            pontos_melhoria TEXT NOT NULL,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(audit_id) REFERENCES audits(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_gestor_feedbacks_audit_id ON gestor_feedbacks(audit_id)"
    )


def ensure_report_exports_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS report_exports (
            id SERIAL PRIMARY KEY,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            report_kind TEXT NOT NULL,
            file_format TEXT NOT NULL,
            filename TEXT,
            media_type TEXT,
            generated_by TEXT,
            operator_name TEXT,
            operator_id TEXT,
            alert_id TEXT,
            alert_label TEXT,
            sector_id TEXT,
            score REAL,
            max_score REAL,
            source_type TEXT,
            audit_timestamp TEXT,
            file_size_bytes INTEGER,
            metadata_json TEXT DEFAULT '{}'
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_report_exports_created_at ON report_exports(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_report_exports_kind ON report_exports(report_kind)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_report_exports_operator_id ON report_exports(operator_id)")


def ensure_arquivos_salvos_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS arquivos_salvos (
            id SERIAL PRIMARY KEY,
            tipo TEXT NOT NULL,
            conteudo TEXT,
            arquivo TEXT,
            data_analise TEXT DEFAULT CURRENT_TIMESTAMP,
            audit_id INTEGER,
            operator_name TEXT,
            sector_id TEXT,
            alert_label TEXT,
            score REAL,
            metadata_json TEXT DEFAULT '{}',
            criado_por TEXT,
            FOREIGN KEY(audit_id) REFERENCES audits(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_arquivos_salvos_tipo ON arquivos_salvos(tipo)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_arquivos_salvos_data ON arquivos_salvos(data_analise)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_arquivos_salvos_audit ON arquivos_salvos(audit_id)")


def ensure_runtime_schema(cursor) -> None:
    # ── Pipeline D-1 Tracking ──
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS huawei_d_minus_1_runs (
            date_str TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            first_attempt_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            last_attempt_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            manifest_csv_count INTEGER,
            manifest_rows_count INTEGER,
            candidates_count INTEGER,
            downloaded_count INTEGER,
            skipped_quota_count INTEGER,
            last_error TEXT,
            last_result_json JSONB,
            exhausted_alerted_at TIMESTAMPTZ
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hd1_status ON huawei_d_minus_1_runs(status)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_cycle_runs (
            id BIGSERIAL PRIMARY KEY,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            stage TEXT NOT NULL DEFAULT 'starting',
            message TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMPTZ,
            last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            baixadas INTEGER NOT NULL DEFAULT 0,
            auditadas INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            sync_result JSONB,
            audit_result JSONB,
            result JSONB
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_cycle_runs_started_at "
        "ON automation_cycle_runs(started_at DESC)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_cycle_runs_status "
        "ON automation_cycle_runs(status)"
    )

    # ── Extensão vetorial pgvector (RAG de triagem) ──
    # No provedor em nuvem, CREATE EXTENSION pode falhar por restrição de Role.
    # Nesse caso, fazemos rollback isolado e orientamos ativação manual.
    _pgvector_available = False
    try:
        cursor.execute("SAVEPOINT _pgvector_ext")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute("RELEASE SAVEPOINT _pgvector_ext")
        _pgvector_available = True
    except Exception as exc:
        try:
            cursor.execute("ROLLBACK TO SAVEPOINT _pgvector_ext")
        except Exception:
            # Fallback: rollback completo para limpar transação abortada
            cursor.connection.rollback()
        import logging as _log
        _log.getLogger(__name__).warning(
            "Provedor: Ative a extensao 'vector' manualmente no painel "
            "(Database -> Extensions). Erro: %s", exc
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audits (
            id SERIAL PRIMARY KEY,
            timestamp TEXT,
            operator_name TEXT,
            score REAL,
            max_score REAL,
            summary TEXT,
            details_json TEXT,
            transcription_json TEXT,
            input_hash TEXT,
            alert_id TEXT,
            alert_label TEXT,
            operator_id TEXT,
            driver_name TEXT
        )
        """
    )
    audit_columns = get_existing_columns(cursor, "audits")
    ensure_column(cursor, "audits", "input_hash", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "alert_id", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "alert_label", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "operator_id", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "driver_name", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "source_type", f"TEXT DEFAULT '{DEFAULT_SOURCE_TYPE}'", audit_columns)
    ensure_column(cursor, "audits", "sector_id", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audio_quality", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audit_scope", f"TEXT DEFAULT '{CALL_QUALITY_SCOPE}'", audit_columns)
    ensure_column(cursor, "audits", "status", f"TEXT DEFAULT '{DEFAULT_AUDIT_STATUS}'", audit_columns)
    ensure_column(cursor, "audits", "contestation_reason", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "contested_criteria", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "contestation_verdict", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "review_defense", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "reviewed_by", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "reviewed_at", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "ai_feedback", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audio_storage_path", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audio_original_filename", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audio_mime_type", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "audio_size_bytes", "INTEGER", audit_columns)
    ensure_column(cursor, "audits", "audit_date", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "discarded_at", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "discarded_by", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "discard_reason", "TEXT", audit_columns)
    ensure_column(cursor, "audits", "pre_discard_status", "TEXT", audit_columns)
    # NOTE: colaborador_id FK added AFTER colaboradores table is created (see below)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_input_hash ON audits(input_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_status ON audits(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_sector_id ON audits(sector_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_timestamp ON audits(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_operator_id ON audits(operator_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_sector_timestamp ON audits(sector_id, timestamp)")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS colaboradores (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            supervisor TEXT,
            setor TEXT,
            escala TEXT,
            status TEXT,
            matricula TEXT,
            id_weon TEXT,
            id_huawei TEXT,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_nome ON colaboradores(nome)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_escala ON colaboradores(escala)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_supervisor ON colaboradores(supervisor)")
    colaboradores_columns = get_existing_columns(cursor, "colaboradores")
    ensure_column(cursor, "colaboradores", "id_telefonia", "TEXT", colaboradores_columns)
    ensure_column(cursor, "colaboradores", "softphone_number", "TEXT", colaboradores_columns)
    ensure_column(cursor, "colaboradores", "telefonia_account", "TEXT", colaboradores_columns)
    ensure_column(cursor, "colaboradores", "organizacao_telefonia", "TEXT", colaboradores_columns)
    ensure_column(cursor, "colaboradores", "tipo_agente", "TEXT", colaboradores_columns)
    ensure_column(cursor, "colaboradores", "status_telefonia", "TEXT", colaboradores_columns)
    ensure_column(cursor, "colaboradores", "tipo_escala", "TEXT", colaboradores_columns)
    ensure_column(cursor, "colaboradores", "auditavel", "INTEGER DEFAULT 1", colaboradores_columns)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_matricula ON colaboradores(matricula)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_id_weon ON colaboradores(id_weon)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_id_huawei ON colaboradores(id_huawei)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_id_telefonia ON colaboradores(id_telefonia)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_colaboradores_softphone ON colaboradores(softphone_number)")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_colaboradores_status_auditavel ON colaboradores(status, auditavel)"
    )

    # Now that colaboradores exists, add the FK column to audits
    audit_columns = get_existing_columns(cursor, "audits")
    ensure_column(cursor, "audits", "colaborador_id", "INTEGER REFERENCES colaboradores(id)", audit_columns)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_colaborador_id ON audits(colaborador_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audits_colaborador_timestamp ON audits(colaborador_id, timestamp)")
    _sync_audit_scopes(cursor)

    # Tabela de Fechamento: precisa vir depois de colaboradores por causa da FK.
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fechamento_cadeia_contatos (
            id SERIAL PRIMARY KEY,
            colaborador_id INTEGER NOT NULL REFERENCES colaboradores(id) ON DELETE CASCADE,
            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,
            nota_mot REAL DEFAULT 0,
            nota_pa REAL DEFAULT 0,
            nota_cli REAL DEFAULT 0,
            nota_policia REAL DEFAULT 0,
            matricula_override TEXT,
            nome_override TEXT,
            operacional_override TEXT,
            telefonica_override TEXT,
            desempenho_override TEXT,
            status_override TEXT,
            turno_override TEXT,
            supervisor_override TEXT,
            setor_override TEXT,
            processo_override TEXT,
            final_override TEXT,
            huawei_override TEXT,
            weon_override TEXT,
            atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(colaborador_id, mes, ano)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fechamento_layout_operadores (
            id BIGSERIAL PRIMARY KEY,
            sequencia_bloco INTEGER NOT NULL,
            posicao INTEGER NOT NULL,
            id_visual INTEGER NOT NULL,
            matricula TEXT,
            nome TEXT NOT NULL,
            turno_operacao TEXT NOT NULL,
            supervisor TEXT NOT NULL,
            setor TEXT NOT NULL,
            nota_coluna TEXT NOT NULL DEFAULT 'OPERACIONAL',
            status_base TEXT NOT NULL DEFAULT 'ATIVO',
            huawei TEXT,
            weon TEXT,
            colaborador_id INTEGER REFERENCES colaboradores(id) ON DELETE SET NULL,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(sequencia_bloco, posicao)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_fechamento_layout_colaborador "
        "ON fechamento_layout_operadores(colaborador_id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_fechamento_layout_matricula "
        "ON fechamento_layout_operadores(matricula)"
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fechamento_layout_overrides (
            id BIGSERIAL PRIMARY KEY,
            layout_id BIGINT NOT NULL REFERENCES fechamento_layout_operadores(id) ON DELETE CASCADE,
            mes INTEGER NOT NULL,
            ano INTEGER NOT NULL,
            nota_mot REAL DEFAULT 0,
            nota_pa REAL DEFAULT 0,
            nota_cli REAL DEFAULT 0,
            nota_policia REAL DEFAULT 0,
            matricula_override TEXT,
            nome_override TEXT,
            operacional_override TEXT,
            telefonica_override TEXT,
            desempenho_override TEXT,
            status_override TEXT,
            turno_override TEXT,
            supervisor_override TEXT,
            setor_override TEXT,
            processo_override TEXT,
            final_override TEXT,
            huawei_override TEXT,
            weon_override TEXT,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(layout_id, mes, ano)
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_fechamento_layout_overrides_competencia "
        "ON fechamento_layout_overrides(ano, mes)"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ligacoes_auditadas (
            id SERIAL PRIMARY KEY,
            nome_arquivo TEXT NOT NULL,
            caminho_relativo TEXT NOT NULL,
            hash_arquivo TEXT NOT NULL UNIQUE,
            grupo TEXT,
            subgrupo TEXT,
            setor_referencia TEXT,
            alerta_referencia TEXT,
            qualidade_referencia TEXT NOT NULL DEFAULT 'indefinida',
            observacao TEXT DEFAULT '',
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ligacoes_auditadas_qualidade ON ligacoes_auditadas(qualidade_referencia)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ligacoes_auditadas_setor ON ligacoes_auditadas(setor_referencia)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ligacoes_auditadas_alerta ON ligacoes_auditadas(alerta_referencia)"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resultados_classificacao (
            id SERIAL PRIMARY KEY,
            ligacao_id INTEGER NOT NULL,
            setor_previsto TEXT,
            alerta_previsto TEXT,
            confianca REAL,
            operador_previsto TEXT,
            modelo TEXT,
            versao_prompt TEXT,
            acertou_setor INTEGER,
            acertou_alerta INTEGER,
            erro TEXT,
            metadata_json TEXT DEFAULT '{}',
            executado_em TEXT NOT NULL,
            FOREIGN KEY(ligacao_id) REFERENCES ligacoes_auditadas(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_resultados_classificacao_ligacao ON resultados_classificacao(ligacao_id)"
    )

    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS fila_revisao_classificacao (
            id SERIAL PRIMARY KEY,
            input_hash TEXT NOT NULL UNIQUE,
            nome_arquivo TEXT NOT NULL,
            setor_previsto TEXT,
            alerta_previsto TEXT,
            confianca REAL,
            operador_previsto TEXT,
            erro TEXT,
            prioridade TEXT NOT NULL DEFAULT '{REVIEW_QUEUE_TABLE_DEFAULT_PRIORITY}',
            motivos_json TEXT DEFAULT '[]',
            metadata_json TEXT DEFAULT '{{}}',
            status TEXT NOT NULL DEFAULT '{REVIEW_QUEUE_STATUS_PENDING}',
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_fila_revisao_classificacao_status ON fila_revisao_classificacao(status)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_fila_revisao_classificacao_prioridade ON fila_revisao_classificacao(prioridade)"
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resultados_auditoria (
            id SERIAL PRIMARY KEY,
            ligacao_id INTEGER NOT NULL,
            nota REAL,
            nota_maxima REAL,
            resumo TEXT,
            detalhes_json TEXT DEFAULT '[]',
            executado_em TEXT NOT NULL,
            FOREIGN KEY(ligacao_id) REFERENCES ligacoes_auditadas(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_resultados_auditoria_ligacao ON resultados_auditoria(ligacao_id)"
    )

    cursor.execute(
        """
        CREATE OR REPLACE VIEW ligacoes_boas AS
        SELECT * FROM ligacoes_auditadas WHERE qualidade_referencia = 'boa'
        """
    )
    cursor.execute(
        """
        CREATE OR REPLACE VIEW ligacoes_ruins AS
        SELECT * FROM ligacoes_auditadas WHERE qualidade_referencia = 'ruim'
        """
    )
    cursor.execute(
        """
        CREATE OR REPLACE VIEW ligacoes_zeradas AS
        SELECT * FROM ligacoes_auditadas WHERE qualidade_referencia = 'zerada'
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_sectors (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            description TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_alerts (
            id TEXT PRIMARY KEY,
            sector_id TEXT NOT NULL,
            label TEXT NOT NULL,
            context TEXT,
            pop_ref TEXT,
            expected_direction TEXT,
            FOREIGN KEY(sector_id) REFERENCES audit_sectors(id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_criteria (
            id SERIAL PRIMARY KEY,
            alert_id TEXT NOT NULL,
            chave TEXT,
            label TEXT NOT NULL,
            description TEXT,
            weight REAL DEFAULT 1.0,
            type TEXT DEFAULT 'boolean',
            deflator REAL DEFAULT 0,
            evaluation_type TEXT DEFAULT 'auto',
            referencia TEXT,
            exemplo TEXT,
            FOREIGN KEY(alert_id) REFERENCES audit_alerts(id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_drafts (
            input_hash TEXT NOT NULL,
            user_id TEXT NOT NULL,
            details_json TEXT,
            transcription_json TEXT,
            updated_at TEXT,
            PRIMARY KEY (input_hash, user_id)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT,
            descricao TEXT,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT '{DEFAULT_USER_ROLE}',
            supervisor_name TEXT
        )
        """
    )

    ensure_gestor_feedbacks_table(cursor)
    ensure_report_exports_table(cursor)
    ensure_arquivos_salvos_table(cursor)

    # ── Tabela de inteligência do RAG (ai_feedback) ──
    # A coluna vector(1536) só pode existir se pgvector estiver habilitado.
    _embedding_col = "transcricao_embedding vector(1536)," if _pgvector_available else ""
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS ai_feedback (
            id SERIAL PRIMARY KEY,
            tipo TEXT NOT NULL,
            setor TEXT,
            criterio_id TEXT,
            situacao TEXT NOT NULL,
            correcao TEXT NOT NULL,
            justificativa TEXT NOT NULL,
            exemplo_transcricao TEXT,
            {_embedding_col}
            criado_por TEXT NOT NULL,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            atualizado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_feedback_tipo ON ai_feedback(tipo)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_feedback_setor ON ai_feedback(setor)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_feedback_ativo ON ai_feedback(ativo)")

    # ── View: audits joined with colaborador data ──
    cursor.execute("DROP VIEW IF EXISTS audits_com_colaborador")
    cursor.execute(
        """
        CREATE VIEW audits_com_colaborador AS
        SELECT
            a.id,
            a.timestamp,
            a.operator_name,
            a.score,
            a.max_score,
            a.summary,
            a.sector_id,
            a.alert_id,
            a.alert_label,
            a.source_type,
            a.status,
            a.ai_feedback,
            a.colaborador_id,
            c.nome          AS colaborador_nome,
            c.matricula,
            c.id_huawei,
            c.supervisor,
            c.setor,
            c.escala,
            c.status        AS colaborador_status
        FROM audits a
        LEFT JOIN colaboradores c ON a.colaborador_id = c.id
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS huawei_sync_logs (
            id SERIAL PRIMARY KEY,
            call_id TEXT UNIQUE NOT NULL,
            agent_id TEXT,
            media_url TEXT,
            sincronizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'success',
            failure_reason TEXT
        )
        """
    )
    huawei_sync_log_columns = get_existing_columns(cursor, "huawei_sync_logs")
    ensure_column(cursor, "huawei_sync_logs", "status", "TEXT DEFAULT 'success'", huawei_sync_log_columns)
    ensure_column(cursor, "huawei_sync_logs", "failure_reason", "TEXT", huawei_sync_log_columns)
    ensure_column(cursor, "huawei_sync_logs", "operator_name", "TEXT", huawei_sync_log_columns)
    ensure_column(cursor, "huawei_sync_logs", "huawei_skill_id", "TEXT", huawei_sync_log_columns)
    ensure_column(cursor, "huawei_sync_logs", "discard_attempts", "INTEGER DEFAULT 0", huawei_sync_log_columns)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_huawei_sync_call_id ON huawei_sync_logs(call_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_huawei_sync_status ON huawei_sync_logs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_huawei_sync_agent_id ON huawei_sync_logs(agent_id)")

