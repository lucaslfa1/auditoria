param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$Region = "southamerica-east1"
$Service = "auditoria"
$Image = "southamerica-east1-docker.pkg.dev/auditoria-nstech/cloud-run-source-deploy/auditoria-manual"

function ConvertTo-SemverTuple {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    $match = [regex]::Match($Value.Trim(), "^(\d+)\.(\d+)\.(\d+)(?:$|[-_])")
    if (-not $match.Success) {
        return $null
    }

    return @(
        [int]$match.Groups[1].Value,
        [int]$match.Groups[2].Value,
        [int]$match.Groups[3].Value
    )
}

function Compare-SemverTuple {
    param(
        [int[]]$Left,
        [int[]]$Right
    )

    for ($i = 0; $i -lt 3; $i++) {
        if ($Left[$i] -ne $Right[$i]) {
            return $Left[$i] - $Right[$i]
        }
    }
    return 0
}

function Format-SemverTuple {
    param([int[]]$Version)
    return "$($Version[0]).$($Version[1]).$($Version[2])"
}

function Get-LatestLogVersion {
    $versionsDir = Join-Path (Get-Location) "logs\versions"
    if (-not (Test-Path -LiteralPath $versionsDir)) {
        return $null
    }

    $latest = $null
    foreach ($versionFile in Get-ChildItem -LiteralPath $versionsDir -Filter "*.md" -File) {
        $parsed = ConvertTo-SemverTuple $versionFile.BaseName
        if ($null -eq $parsed) {
            continue
        }
        if ($null -eq $latest -or (Compare-SemverTuple $parsed $latest) -gt 0) {
            $latest = $parsed
        }
    }

    if ($null -eq $latest) {
        return $null
    }
    return Format-SemverTuple $latest
}

function Resolve-AppVersion {
    $package = Get-Content -LiteralPath "package.json" -Raw | ConvertFrom-Json
    $packageVersion = [string]$package.version
    $packageSemver = ConvertTo-SemverTuple $packageVersion
    $logVersion = Get-LatestLogVersion
    $logSemver = ConvertTo-SemverTuple $logVersion

    if ($null -ne $packageSemver -and $null -ne $logSemver) {
        if ((Compare-SemverTuple $logSemver $packageSemver) -ge 0) {
            return $logVersion
        }
        return $packageVersion
    }

    if (-not [string]::IsNullOrWhiteSpace($logVersion)) {
        return $logVersion
    }
    return $packageVersion
}

function Invoke-DeployStep {
    param(
        [string]$Command,
        [string[]]$Arguments
    )

    Write-Host ("> " + $Command + " " + ($Arguments -join " "))
    if ($DryRun) {
        return
    }

    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$CommitSha = (git rev-parse HEAD).Trim()
$AppVersion = Resolve-AppVersion

Write-Host "Deploy release: commit=$($CommitSha.Substring(0, 12)) version=$AppVersion"

Invoke-DeployStep "gcloud" @("builds", "submit", "--tag", $Image, ".", "--region", $Region)
Invoke-DeployStep "gcloud" @(
    "run",
    "deploy",
    $Service,
    "--image",
    $Image,
    "--region",
    $Region,
    "--update-env-vars",
    "GIT_COMMIT_SHA=$CommitSha,APP_VERSION=$AppVersion"
)
