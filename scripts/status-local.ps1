param(
    [int]$Port = 8080
)

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -First 1

if (-not $listener) {
    Write-Host "Backend status: DOWN (no listener on port $Port)"
    exit 1
}

Write-Host "Backend status: LISTENING on port $Port (pid $($listener.OwningProcess))"

try {
    $health = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
    Write-Host "Health endpoint: $($health.StatusCode) $($health.Content)"
    exit 0
} catch {
    Write-Host "Health endpoint: FAILED ($($_.Exception.Message))"
    exit 1
}
