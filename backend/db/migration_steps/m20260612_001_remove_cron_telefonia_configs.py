"""Remove as configs do antigo cron continuo da Telefonia (revisao 2026-06-12).

As chaves abaixo deixaram de ter leitor no codigo:
- `telefonia_cron_sync_ativa`: gate do coletor no /cron/sync — removido; o
  pipeline D-1 ja respeita `huawei_d1_enabled` e roda no maximo 1 lote/dia.
- `automacao_intervalo_segundos`: intervalo do loop residente em processo,
  que foi removido (era o padrao de busca continua que estourou o orcamento
  de IA em junho/2026).
- `telefonia_sync_intervalo_segundos`: variante nunca consumida fora do
  diagnostics.

O historico de mudancas dessas chaves permanece em `configuracoes_audit_log`.
"""
from __future__ import annotations

MIGRATION_NAME = "m20260612_001_remove_cron_telefonia_configs"


def apply(c) -> None:
    c.execute(
        """
        DELETE FROM configuracoes
        WHERE chave IN (
            'telefonia_cron_sync_ativa',
            'automacao_intervalo_segundos',
            'telefonia_sync_intervalo_segundos'
        )
        """
    )
