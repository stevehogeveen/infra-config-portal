param(
  [string[]]$PytestArgs = @("-q"),
  [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$backendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
& (Join-Path $PSScriptRoot "ensure-backend-venv.ps1") -ForceInstall:$Install

$env:PROVIDER_MODE = "mock"

Push-Location $backendRoot
try {
  & .\.venv\Scripts\python.exe -m pytest @PytestArgs
} finally {
  Pop-Location
}
