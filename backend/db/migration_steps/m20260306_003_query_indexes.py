from typing import Any


MIGRATION_NAME = "20260306_003_query_indexes"


def apply(cursor: Any) -> None:
    # Normalize controlled identifiers so exact-match queries can use indexes reliably.
    cursor.execute(
        """
        UPDATE users
        SET username = LOWER(TRIM(username))
        WHERE username IS NOT NULL AND username != ''
        """
    )
    cursor.execute(
        """
        UPDATE audits
        SET sector_id = LOWER(TRIM(sector_id))
        WHERE sector_id IS NOT NULL AND sector_id != ''
        """
    )
    cursor.execute(
        """
        UPDATE ligacoes_auditadas
        SET setor_referencia = LOWER(TRIM(setor_referencia))
        WHERE setor_referencia IS NOT NULL AND setor_referencia != ''
        """
    )
    cursor.execute(
        """
        UPDATE fila_revisao_classificacao
        SET setor_previsto = LOWER(TRIM(setor_previsto))
        WHERE setor_previsto IS NOT NULL AND setor_previsto != ''
        """
    )
    cursor.execute(
        """
        UPDATE report_exports
        SET report_kind = LOWER(TRIM(report_kind)),
            file_format = LOWER(TRIM(file_format))
        WHERE report_kind IS NOT NULL OR file_format IS NOT NULL
        """
    )

    # Queries reais do dashboard, supervisor e arquivos salvos.
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_audits_status_sector_timestamp ON audits(status, sector_id, timestamp)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_audits_status_id ON audits(status, id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_resultados_classificacao_ligacao_id ON resultados_classificacao(ligacao_id, id)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ligacoes_auditadas_setor_qualidade ON ligacoes_auditadas(setor_referencia, qualidade_referencia)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_fila_revisao_status_setor_prioridade_atualizado ON fila_revisao_classificacao(status, setor_previsto, prioridade, atualizado_em)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_colaboradores_status_supervisor_escala ON colaboradores(status, supervisor, escala)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_arquivos_salvos_tipo_data ON arquivos_salvos(tipo, data_analise)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_exports_kind_format_created_at ON report_exports(report_kind, file_format, created_at)"
    )
