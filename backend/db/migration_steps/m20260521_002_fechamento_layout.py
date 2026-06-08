from typing import Any


MIGRATION_NAME = "20260521_002_fechamento_layout"


def apply(cursor: Any) -> None:
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
        "ALTER TABLE fechamento_cadeia_contatos ADD COLUMN IF NOT EXISTS weon_override TEXT"
    )
