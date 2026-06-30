"""Seed configs for directed operator coverage backfill.

The automation cycle can run a bounded targeted Huawei search for operators that
remain below the monthly coverage minimum. Existing values are preserved.
"""
from __future__ import annotations

MIGRATION_NAME = "m20260630_002_operator_coverage_backfill_configs"


def apply(c) -> None:
    c.execute(
        """
        INSERT INTO configuracoes (chave, valor, descricao, tipo, is_secret)
        VALUES
            (
                'automacao_cobertura_backfill_ativa',
                'true',
                'Ativa busca direcionada de ligacoes para operadores abaixo da cobertura',
                'bool',
                false
            ),
            (
                'automacao_cobertura_backfill_lookback_dias',
                '7',
                'Dias retroativos da busca direcionada por operador abaixo da cobertura',
                'int',
                false
            ),
            (
                'automacao_cobertura_backfill_max_operadores',
                '3',
                'Maximo de operadores abaixo da cobertura buscados por ciclo',
                'int',
                false
            )
        ON CONFLICT (chave) DO NOTHING
        """
    )
    c.execute(
        """
        UPDATE configuracoes
           SET is_secret = false,
               tipo = CASE
                   WHEN chave = 'automacao_cobertura_backfill_ativa' THEN 'bool'
                   ELSE 'int'
               END
         WHERE chave IN (
            'automacao_cobertura_backfill_ativa',
            'automacao_cobertura_backfill_lookback_dias',
            'automacao_cobertura_backfill_max_operadores'
         )
        """
    )
