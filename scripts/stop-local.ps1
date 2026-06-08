param(
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$listenerPids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

if (-not $listenerPids) {
    Write-Host "No backend listener found on port $Port."
    exit 0
}

foreach ($procId in $listenerPids) {
    try {
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "Stopped process $procId"
    } catch {
        Write-Host "Failed to stop process $procId"
    }
}

Start-Sleep -Seconds 1
$stillListening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($stillListening) {
    Write-Error "Port $Port is still listening."
    exit 1
}

Write-Host "Backend stopped."
