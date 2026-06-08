param (
    [int]$Minutes = 120
)

$code = @'
using System;
using System.Runtime.InteropServices;

public static class PowerRequest {
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);

    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED = 0x00000002;
}
'@

try {
    Add-Type -TypeDefinition $code -ErrorAction SilentlyContinue
} catch {
    # Type might already be loaded
}

Write-Host "Iniciando keep awake por $Minutes minutos..."
# ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
$flags = [PowerRequest]::ES_CONTINUOUS -bor [PowerRequest]::ES_SYSTEM_REQUIRED -bor [PowerRequest]::ES_DISPLAY_REQUIRED
[PowerRequest]::SetThreadExecutionState($flags)

$endAt = (Get-Date).AddMinutes($Minutes)
while ((Get-Date) -lt $endAt) {
    $remaining = ($endAt - (Get-Date)).TotalMinutes
    Write-Host ("Mantendo acordado... Restam {0:N1} minutos" -f $remaining)
    Start-Sleep -Seconds 60
}

# Reset to normal
[PowerRequest]::SetThreadExecutionState([PowerRequest]::ES_CONTINUOUS)
Write-Host "Tempo esgotado. Keep awake finalizado."
