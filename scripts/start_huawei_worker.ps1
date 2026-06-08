
param(
    [int]$horas = 1
)

$env:PYTHONPATH = "backend;."
$env:ENABLE_HUAWEI_SYNC = "true"

Write-Host "--- Disparando Sincronismo Huawei Manual ---" -ForegroundColor Cyan
Write-Host "Buscando ligacoes das ultimas $horas hora(s)..."

if (Test-Path "backend\.venv\Scripts\python.exe") {
    backend\.venv\Scripts\python.exe scripts/huawei_manual_sync.py --horas $horas
} else {
    python scripts/huawei_manual_sync.py --horas $horas
}
