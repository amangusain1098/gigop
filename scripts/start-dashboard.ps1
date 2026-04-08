param(
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    Write-Host "Starting GigOptimizer Pro dashboard at http://127.0.0.1:8001 ..."
    if ($OpenBrowser) {
        Start-Process "http://127.0.0.1:8001/"
    }
    python -m gigoptimizer.api.main
}
finally {
    Pop-Location
}
