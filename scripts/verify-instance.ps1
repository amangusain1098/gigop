param(
    [string]$BaseUrl = "http://127.0.0.1:8001",
    [string]$Username = "",
    [string]$Password = "",
    [string]$Output = "artifacts/verification-report.json"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $projectRoot
try {
    $args = @(
        "-m", "gigoptimizer.verify",
        "--base-url", $BaseUrl,
        "--output", $Output
    )

    if ($Username) {
        $args += @("--username", $Username)
    }

    if ($Password) {
        $args += @("--password", $Password)
    }

    python @args
}
finally {
    Pop-Location
}
