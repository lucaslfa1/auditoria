from typing import Any


MIGRATION_NAME = "20260420_001_remove_non_process_operators"


def apply(cursor: Any) -> None:
    """Remove operadores fora do processo e servicos tecnicos de telefonia."""
    cursor.execute("DROP TABLE IF EXISTS tmp_removed_non_process_colaboradores")
    cursor.execute(
        """
        CREATE TEMP TABLE tmp_removed_non_process_colaboradores ON COMMIT DROP AS
        SELECT id
        FROM colaboradores
        WHERE (
            LOWER(
                COALESCE(setor, '') || ' ' ||
                COALESCE(escala, '') || ' ' ||
                COALESCE(organizacao_telefonia, '') || ' ' ||
                COALESCE(telefonia_account, '')
            ) LIKE ANY (ARRAY[
                '%comandolog%',
                '%gestao e coordenacao%',
                '%gestão e coordenação%',
                '%operacao profarma%',
                '%operação profarma%',
                '%profarma%',
                '%operacao tora pa%',
                '%operação tora pa%',
                '%tora pa%',
                '%operacao tora%',
                '%operação tora%',
                '%tora%',
                '%sanofi%',
                '%time bbm%'
            ])
        )
        OR (
            COALESCE(TRIM(matricula), '') = ''
            AND COALESCE(TRIM(supervisor), '') = ''
            AND (
                LOWER(COALESCE(nome, '')) LIKE 'contencao%'
                OR LOWER(COALESCE(nome, '')) LIKE 'contenção%'
                OR LOWER(COALESCE(telefonia_account, '')) LIKE 'contencao%'
                OR LOWER(COALESCE(telefonia_account, '')) LIKE 'contenção%'
            )
        )
        OR (
            COALESCE(TRIM(nome), '') = ''
            AND (
                COALESCE(TRIM(telefonia_account), '') <> ''
                OR COALESCE(TRIM(organizacao_telefonia), '') <> ''
                OR COALESCE(TRIM(tipo_agente), '') <> ''
                OR COALESCE(TRIM(status_telefonia), '') <> ''
                OR COALESCE(TRIM(id_telefonia), '') <> ''
                OR COALESCE(TRIM(softphone_number), '') <> ''
            )
        )
        """
    )
    cursor.execute(
        """
        UPDATE audits
        SET colaborador_id = NULL
        WHERE colaborador_id IN (SELECT id FROM tmp_removed_non_process_colaboradores)
        """
    )
    cursor.execute(
        """
        DELETE FROM fechamento_cadeia_contatos
        WHERE colaborador_id IN (SELECT id FROM tmp_removed_non_process_colaboradores)
        """
    )
    cursor.execute(
        """
        DELETE FROM colaboradores
        WHERE id IN (SELECT id FROM tmp_removed_non_process_colaboradores)
        """
    )
