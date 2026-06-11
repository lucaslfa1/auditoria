# =============================================================================
# 01_dump_neon.ps1 — Dump completo do banco Neon (origem) para migração Azure.
# Equivalente Windows do 01_dump_neon.sh (mesmos requisitos e saída).
#
# Uso:
#   $env:NEON_DATABASE_URL = 'postgresql://user:pass@ep-xxx.sa-east-1.aws.neon.tech/neondb?sslmode=require'
#   .\01_dump_neon.ps1 [arquivo_saida.dump]
#
# Requisitos: pg_dump >= 17 no PATH (ex.: C:\Program Files\PostgreSQL\18\bin).
# A URL deve usar o endpoint DIRETO (sem "-pooler") — removido automaticamente.
# =============================================================================
$ErrorActionPreference = 'Stop'

if (-not $env:NEON_DATABASE_URL) {
    Write-Error 'Defina NEON_DATABASE_URL (connection string do Neon, endpoint direto).'
}

$output = if ($args.Count -ge 1) { $args[0] } else { "auditoria_neon_$(Get-Date -Format yyyyMMdd_HHmmss).dump" }
$directUrl = $env:NEON_DATABASE_URL -replace '-pooler', ''

Write-Host "==> Dump do Neon (endpoint direto) para $output..."
pg_dump --format=custom --no-owner --no-privileges --file=$output $directUrl
if ($LASTEXITCODE -ne 0) { Write-Error "pg_dump falhou (exit $LASTEXITCODE)." }

$size = (Get-Item $output).Length / 1MB
Write-Host ("==> OK: {0:N1} MB gravados em {1}" -f $size, $output)
Write-Host "    Próximo passo: .\02_restore_destino.ps1 $output"
