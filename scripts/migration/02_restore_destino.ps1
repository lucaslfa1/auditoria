# =============================================================================
# 02_restore_destino.ps1 — Restaura o dump do Neon no PostgreSQL de DESTINO
# escolhido pelo time de engenharia. Equivalente Windows do
# 02_restore_destino.sh — leia os PRÉ-REQUISITOS lá (PostgreSQL >= 17 +
# pgvector habilitado ANTES do restore; detalhes em docs/10-migracao-banco.md).
#
# Uso:
#   $env:TARGET_DATABASE_URL = 'postgresql://user:pass@servidor:5432/auditoria?sslmode=require'
#   .\02_restore_destino.ps1 <arquivo.dump>
# =============================================================================
$ErrorActionPreference = 'Stop'

if (-not $env:TARGET_DATABASE_URL) {
    Write-Error 'Defina TARGET_DATABASE_URL (connection string do PostgreSQL de destino).'
}
if ($args.Count -lt 1 -or -not (Test-Path $args[0])) {
    Write-Error 'Informe o arquivo .dump gerado pelo 01_dump_neon.ps1.'
}

$dumpFile = $args[0]

Write-Host "==> Restaurando $dumpFile no destino (4 jobs paralelos)..."
# Erros de CREATE EXTENSION pg_stat_statements (opcional) podem ser ignorados;
# qualquer outro erro deve ser investigado antes do 03_validate.py.
pg_restore --no-owner --no-privileges --jobs=4 --dbname=$env:TARGET_DATABASE_URL $dumpFile
Write-Host "==> Restore concluído (verifique avisos acima, se houver)."
Write-Host "    Próximo passo: python 03_validate.py (compara origem x destino)."
