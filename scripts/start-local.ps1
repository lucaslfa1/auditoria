param(
    [switch]$OpenBrowser,
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$pythonExe = Join-Path $backendDir ".venv\\Scripts\\python.exe"
$outLog = Join-Path $backendDir "service-localhost.out.log"
$errLog = Join-Path $backendDir "service-localhost.err.log"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python venv not found at $pythonExe"
    exit 1
}

$listenerPids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

if ($listenerPids) {
    foreach ($procId in $listenerPids) {
        try { Stop-Process -Id $procId -Force -ErrorAction Stop } catch {}
    }
    Start-Sleep -Seconds 1
}

if (Test-Path $outLog) { Remove-Item $outLog -Force }
if (Test-Path $errLog) { Remove-Item $errLog -Force }

$env:ENVIRONMENT = "development"
$env:BACKEND_PORT = "$Port"
$env:PORT = "$Port"
$env:SESSION_COOKIE_SECURE = "false"
$env:AUDITORIA_TRUST_ENV_PROXY = "false"
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:GIT_HTTP_PROXY = ""
$env:GIT_HTTPS_PROXY = ""
$env:NO_PROXY = "localhost,127.0.0.1,::1"

Start-Process -FilePath $pythonExe `
    -ArgumentList "main.py" `
    -WorkingDirectory $backendDir `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog | Out-Null

$healthy = $false
for ($i = 1; $i -le 25; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($response.StatusCode -eq 200) {
            $healthy = $true
            break
        }
    } catch {}
}

if (-not $healthy) {
    Write-Error "Backend failed to pass health check on http://127.0.0.1:$Port/api/health"
    if (Test-Path $errLog) {
        Write-Host "--- backend stderr tail ---"
        Get-Content $errLog -Tail 80
    }
    exit 1
}

Write-Host "Backend is up: http://localhost:$Port"
Write-Host "Health check: OK"

if ($OpenBrowser) {
    Start-Process "http://localhost:$Port"
}
