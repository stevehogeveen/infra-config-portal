param(
  [switch]$GenerateMissingPlans
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$appRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $appRoot "..")
$artifactRoot = Join-Path $repoRoot "artifacts\codex-runs"
$healthArtifact = Join-Path $artifactRoot "qa-artifact-health.json"
$backendPython = Join-Path $appRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $backendPython)) {
  $backendPython = "python"
}

function Invoke-JsonValidator {
  param(
    [string]$Name,
    [scriptblock]$Script
  )

  $global:LASTEXITCODE = 0
  $output = & $Script
  if ($LASTEXITCODE -ne 0) {
    return [ordered]@{
      name = $Name
      valid = $false
      exit_code = $LASTEXITCODE
      errors = @("validator command failed", ($output -join "`n"))
    }
  }
  try {
    $jsonText = ($output | Out-String).Trim()
    $jsonStart = $jsonText.IndexOf("{")
    if ($jsonStart -gt 0) {
      $jsonText = $jsonText.Substring($jsonStart)
    }
    $parsed = $jsonText | ConvertFrom-Json
  } catch {
    return [ordered]@{
      name = $Name
      valid = $false
      exit_code = 0
      errors = @("validator output was not JSON: $($_.Exception.Message)")
    }
  }
  $artifact = $null
  if ($parsed.PSObject.Properties.Name -contains "artifact") {
    $artifact = $parsed.artifact
  }
  $errors = @()
  if ($parsed.PSObject.Properties.Name -contains "errors") {
    $errors = @($parsed.errors)
  }
  return [ordered]@{
    name = $Name
    valid = [bool]$parsed.valid
    artifact = $artifact
    errors = $errors
  }
}

if ($GenerateMissingPlans) {
  & (Join-Path $PSScriptRoot "fast-verify.ps1") -WhatIfOnly | Out-Null
  & (Join-Path $PSScriptRoot "hardware-smoke.ps1") -WhatIfOnly | Out-Null
  Push-Location (Join-Path $appRoot "backend")
  try {
    & $backendPython "scripts\openapi_contract_probe.py" | Out-Null
    & $backendPython "scripts\qa_capability_audit.py" | Out-Null
  } finally {
    Pop-Location
  }
}

New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null

$checks = @(
  (Invoke-JsonValidator "fast-verify-plan" { & (Join-Path $PSScriptRoot "fast-verify.ps1") -ValidatePlan }),
  (Invoke-JsonValidator "hardware-smoke-plan" { & (Join-Path $PSScriptRoot "hardware-smoke.ps1") -ValidatePlan }),
  (Invoke-JsonValidator "qa-failure-packet" { & (Join-Path $PSScriptRoot "qa-failure-packet.ps1") -ValidateLatest }),
  (Invoke-JsonValidator "openapi-contract-probe" {
      Push-Location (Join-Path $appRoot "backend")
      try {
        & $backendPython "scripts\openapi_contract_probe.py" --validate (Join-Path $artifactRoot "openapi-contract-probe.json")
      } finally {
        Pop-Location
      }
    }),
  (Invoke-JsonValidator "qa-capability-audit" {
      Push-Location (Join-Path $appRoot "backend")
      try {
        & $backendPython "scripts\qa_capability_audit.py" --validate (Join-Path $artifactRoot "qa-capability-audit.json")
      } finally {
        Pop-Location
      }
    })
)

$failed = @($checks | Where-Object { -not $_.valid })
$summary = [ordered]@{
  schema_version = "qa-artifact-health/v1"
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  valid = $failed.Count -eq 0
  artifact = "artifacts/codex-runs/qa-artifact-health.json"
  checks = @($checks)
  safety_notes = @(
    "This health check validates local QA artifacts only.",
    "It does not run tests, workflow actions, provider probes, hardware commands, or external AI calls.",
    "Use -GenerateMissingPlans to create dry-run plan artifacts only."
  )
}

$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $healthArtifact -Encoding UTF8
$summary | ConvertTo-Json -Depth 8

if ($failed.Count) {
  exit 2
}
