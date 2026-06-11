#!/usr/bin/env bash
# =============================================================================
# 02_restore_destino.sh — Restaura o dump do Neon no PostgreSQL de DESTINO
# escolhido pelo time de engenharia (o serviço ainda não está definido;
# requisitos em docs/10-migracao-banco.md §1: PostgreSQL >= 17 + pgvector).
#
# Uso:
#   TARGET_DATABASE_URL='postgresql://user:pass@servidor:5432/auditoria?sslmode=require' \
#     ./02_restore_destino.sh <arquivo.dump>
#
# PRÉ-REQUISITOS NO SERVIDOR DE DESTINO (uma única vez, antes do restore):
#   1. PostgreSQL >= 17 (origem é 17).
#   2. Extensão pgvector habilitada ANTES do restore — o dump contém o
#      CREATE EXTENSION vector; sem ela, o restore falha nas tabelas de RAG
#      (procedimento_chunks). Exemplos por provedor em docs/10 §3.2
#      (Azure: parâmetro azure.extensions; RDS: direto; Cloud SQL: flag).
#   3. pg_stat_statements é OPCIONAL (observabilidade) — sem ela, ignore o
#      erro de CREATE EXTENSION correspondente.
#   4. Banco de destino criado e vazio (ex.: CREATE DATABASE auditoria).
#
# O restore usa --no-owner/--no-privileges: os objetos ficam do usuário da
# conexão (recomendado: o usuário da aplicação, não o superusuário).
# =============================================================================
set -euo pipefail

if [[ -z "${TARGET_DATABASE_URL:-}" ]]; then
  echo "ERRO: defina TARGET_DATABASE_URL (connection string do PostgreSQL de destino)." >&2
  exit 1
fi
if [[ $# -lt 1 || ! -f "$1" ]]; then
  echo "ERRO: informe o arquivo .dump gerado pelo 01_dump_neon.sh." >&2
  exit 1
fi

DUMP_FILE="$1"

echo "==> Restaurando ${DUMP_FILE} no destino (4 jobs paralelos)..."
# --exit-on-error desligado de propósito: o dump pode conter CREATE EXTENSION
# pg_stat_statements (opcional). Erros são listados ao final; avalie cada um.
pg_restore \
  --no-owner \
  --no-privileges \
  --jobs=4 \
  --dbname="${TARGET_DATABASE_URL}" \
  "${DUMP_FILE}" || true

echo "==> Restore concluído (verifique avisos acima, se houver)."
echo "    Próximo passo: python 03_validate.py (compara origem x destino)."
