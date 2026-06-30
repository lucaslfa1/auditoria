"""Seed configs for initial-month audit coverage prioritization.

The automation queue uses these values to prioritize ready audit items from
operators still below the early-month minimum coverage. Existing values are
preserved.
"""
from __future__ import annotations

MIGRATION_NAME = "m20260630_001_initial_quota_coverage_configs"


def apply(c) -> None:
    c.execute(
        """
        INSERT INTO configuracoes (chave, valor, descricao, tipo, is_secret)
        VALUES
            (
                'automacao_cobertura_inicial_dias',
                '3',
                'Dias iniciais do mes em que a automacao prioriza operadores abaixo da cobertura minima',
                'int',
                false
            ),
            (
                'automacao_cobertura_inicial_min_por_operador',
                '2',
                'Minimo de auditorias por operador priorizado nos primeiros dias do mes',
                'int',
                false
            )
        ON CONFLICT (chave) DO NOTHING
        """
    )
    c.execute(
        """
        UPDATE configuracoes
           SET tipo = 'int', is_secret = false
         WHERE chave IN (
            'automacao_cobertura_inicial_dias',
            'automacao_cobertura_inicial_min_por_operador'
         )
        """
    )
