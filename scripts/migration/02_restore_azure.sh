#!/usr/bin/env bash
# =============================================================================
# 02_restore_azure.sh — Restaura o dump do Neon no Azure Database for
# PostgreSQL Flexible Server (destino).
#
# Uso:
#   AZURE_DATABASE_URL='postgresql://user:pass@servidor.postgres.database.azure.com:5432/auditoria?sslmode=require' \
#     ./02_restore_azure.sh <arquivo.dump>
#
# PRÉ-REQUISITOS NO SERVIDOR AZURE (uma única vez, antes do restore):
#   1. Servidor Flexible Server com PostgreSQL >= 17 (origem é 17).
#   2. Extensão pgvector habilitada:
#      - Portal/CLI: parâmetro de servidor `azure.extensions` deve incluir VECTOR
#        (az postgres flexible-server parameter set --name azure.extensions \
#          --value 'VECTOR' ...)
#      - O dump contém o CREATE EXTENSION vector; sem o allowlist, o restore
#        falha nas tabelas de RAG (procedimento_chunks).
#      - pg_stat_statements é OPCIONAL (só observabilidade) — se não quiser
#        habilitar, ignore os erros de CREATE EXTENSION correspondentes.
#   3. Banco de destino criado e vazio (ex.: CREATE DATABASE auditoria).
#
# O restore usa --no-owner/--no-privileges: os objetos ficam do usuário da
# conexão (recomendado: o admin do app, não o superusuário do servidor).
# =============================================================================
set -euo pipefail

if [[ -z "${AZURE_DATABASE_URL:-}" ]]; then
  echo "ERRO: defina AZURE_DATABASE_URL (connection string do Azure PostgreSQL)." >&2
  exit 1
fi
if [[ $# -lt 1 || ! -f "$1" ]]; then
  echo "ERRO: informe o arquivo .dump gerado pelo 01_dump_neon.sh." >&2
  exit 1
fi

DUMP_FILE="$1"

echo "==> Restaurando ${DUMP_FILE} no Azure (4 jobs paralelos)..."
# --exit-on-error desligado de propósito: o dump pode conter CREATE EXTENSION
# pg_stat_statements (opcional). Erros são listados ao final; avalie cada um.
pg_restore \
  --no-owner \
  --no-privileges \
  --jobs=4 \
  --dbname="${AZURE_DATABASE_URL}" \
  "${DUMP_FILE}" || true

echo "==> Restore concluído (verifique avisos acima, se houver)."
echo "    Próximo passo: python 03_validate.py (compara origem x destino)."
