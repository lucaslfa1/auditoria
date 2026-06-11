# =============================================================================
# 02_restore_azure.ps1 — Restaura o dump do Neon no Azure Database for
# PostgreSQL Flexible Server. Equivalente Windows do 02_restore_azure.sh —
# leia os PRÉ-REQUISITOS no .sh (pgvector via azure.extensions etc.).
#
# Uso:
#   $env:AZURE_DATABASE_URL = 'postgresql://user:pass@servidor.postgres.database.azure.com:5432/auditoria?sslmode=require'
#   .\02_restore_azure.ps1 <arquivo.dump>
# =============================================================================
$ErrorActionPreference = 'Stop'

if (-not $env:AZURE_DATABASE_URL) {
    Write-Error 'Defina AZURE_DATABASE_URL (connection string do Azure PostgreSQL).'
}
if ($args.Count -lt 1 -or -not (Test-Path $args[0])) {
    Write-Error 'Informe o arquivo .dump gerado pelo 01_dump_neon.ps1.'
}

$dumpFile = $args[0]

Write-Host "==> Restaurando $dumpFile no Azure (4 jobs paralelos)..."
# Erros de CREATE EXTENSION pg_stat_statements (opcional) podem ser ignorados;
# qualquer outro erro deve ser investigado antes do 03_validate.py.
pg_restore --no-owner --no-privileges --jobs=4 --dbname=$env:AZURE_DATABASE_URL $dumpFile
Write-Host "==> Restore concluído (verifique avisos acima, se houver)."
Write-Host "    Próximo passo: python 03_validate.py (compara origem x destino)."
