#!/usr/bin/env bash
# =============================================================================
# 01_dump_neon.sh — Dump completo do banco Neon (origem) para migração Azure.
#
# Uso:
#   NEON_DATABASE_URL='postgresql://user:pass@ep-xxx.sa-east-1.aws.neon.tech/neondb?sslmode=require' \
#     ./01_dump_neon.sh [arquivo_saida.dump]
#
# Requisitos:
#   - pg_dump versão >= 17 (o servidor Neon é PostgreSQL 17; pg_dump mais
#     antigo recusa servidores mais novos).
#   - A URL deve apontar para o endpoint DIRETO (sem "-pooler"): o PgBouncer
#     do pooler não suporta as features de sessão que o pg_dump usa. Este
#     script remove o sufixo "-pooler" automaticamente por segurança.
#
# Saída: dump em formato custom (-Fc), restaurável com pg_restore (02_*).
# Tamanho esperado: ~46 MB de banco => dump na casa de poucos MB, segundos.
# =============================================================================
set -euo pipefail

if [[ -z "${NEON_DATABASE_URL:-}" ]]; then
  echo "ERRO: defina NEON_DATABASE_URL (connection string do Neon, endpoint direto)." >&2
  exit 1
fi

OUTPUT="${1:-auditoria_neon_$(date +%Y%m%d_%H%M%S).dump}"

# Endpoint direto: o pooler quebra pg_dump.
DIRECT_URL="${NEON_DATABASE_URL/-pooler/}"

echo "==> Dump do Neon (endpoint direto) para ${OUTPUT}..."
pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="${OUTPUT}" \
  "${DIRECT_URL}"

echo "==> OK: $(du -h "${OUTPUT}" | cut -f1) gravados em ${OUTPUT}"
echo "    Próximo passo: 02_restore_azure.sh ${OUTPUT}"
