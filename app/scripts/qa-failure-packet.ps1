param(
  [string]$Note = "",
  [int]$MaxArtifacts = 12,
  [switch]$ValidateLatest,
  [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$backendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
$backendPython = Join-Path $backendRoot ".venv\Scripts\python.exe"

& (Join-Path $PSScriptRoot "ensure-backend-venv.ps1") -ForceInstall:$Install
if (-not (Test-Path $backendPython)) {
  throw "Backend Python was not found at $backendPython after dependency check."
}

Push-Location $backendRoot
try {
  if ($ValidateLatest) {
    & $backendPython scripts\qa_failure_packet.py --validate-latest
  } else {
    & $backendPython scripts\qa_failure_packet.py --note $Note --max-artifacts $MaxArtifacts
  }
} finally {
  Pop-Location
}
