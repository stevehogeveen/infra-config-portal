param(
  [ValidateSet("local-readonly", "local-lab-readwrite")]
  [string]$Mode = "local-readonly",
  [string[]]$Providers = @(),
  [switch]$IncludeOperatorSweep,
  [switch]$AcknowledgeReadOnly,
  [switch]$AllowWriteMode,
  [switch]$Install,
  [switch]$WhatIfOnly,
  [switch]$ValidatePlan
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$appRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $appRoot "..")
$backendRoot = Join-Path $appRoot "backend"
$backendPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$artifactRoot = Join-Path $repoRoot "artifacts\codex-runs"
$hardwareSmokePlanArtifact = Join-Path $artifactRoot "hardware-smoke-plan.json"

function Write-PlanLine {
  param([string]$Message)
  Write-Host "  $Message"
}

function Invoke-HardwareStep {
  param(
    [string]$Name,
    [scriptblock]$Script
  )

  Write-Host ""
  Write-Host "==> $Name" -ForegroundColor Cyan
  if ($WhatIfOnly) {
    return
  }
  $global:LASTEXITCODE = 0
  & $Script
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
}

function Set-EnvValue {
  param(
    [string]$Name,
    [string]$Value
  )
  Set-Item -Path "Env:$Name" -Value $Value
}

function Test-HardwareSmokePlan {
  param([string]$Path)

  $errors = [System.Collections.Generic.List[string]]::new()
  if (-not (Test-Path $Path)) {
    $errors.Add("hardware smoke plan artifact not found")
    return [ordered]@{ valid = $false; artifact = "artifacts/codex-runs/hardware-smoke-plan.json"; errors = @($errors) }
  }
  try {
    $plan = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
  } catch {
    $errors.Add("hardware smoke plan JSON is invalid: $($_.Exception.Message)")
    return [ordered]@{ valid = $false; artifact = "artifacts/codex-runs/hardware-smoke-plan.json"; errors = @($errors) }
  }

  if ($plan.schema_version -ne "hardware-smoke-plan/v1") { $errors.Add("schema_version must be hardware-smoke-plan/v1") }
  if ($plan.mode -notin @("local-readonly", "local-lab-readwrite")) { $errors.Add("mode must be local-readonly or local-lab-readwrite") }
  if ($plan.mode -eq "local-lab-readwrite" -and $plan.allow_write_mode -ne $true) { $errors.Add("local-lab-readwrite requires allow_write_mode=true") }
  if ($plan.provider_smoke_require_real -ne $true) { $errors.Add("provider_smoke_require_real must be true") }
  if (-not ($plan.steps -is [array]) -or @($plan.steps).Count -lt 1) { $errors.Add("steps must be a non-empty array") }
  foreach ($step in @($plan.steps)) {
    if (-not $step.id) { $errors.Add("step id is required") }
    if (-not $step.command) { $errors.Add("step command is required for $($step.id)") }
    $command = " $($step.command) ".ToLowerInvariant()
    foreach ($unsafe in @(" apply ", " reset ", " power ", " factory-reset ")) {
      if ($command.Contains($unsafe)) {
        $errors.Add("step command contains unsafe token '$($unsafe.Trim())' for $($step.id)")
      }
    }
  }
  if (-not ($plan.safety_notes -is [array]) -or @($plan.safety_notes).Count -lt 1) { $errors.Add("safety_notes must be a non-empty array") }

  return [ordered]@{
    valid = $errors.Count -eq 0
    artifact = "artifacts/codex-runs/hardware-smoke-plan.json"
    errors = @($errors)
  }
}

if ($ValidatePlan) {
  $result = Test-HardwareSmokePlan -Path $hardwareSmokePlanArtifact
  $result | ConvertTo-Json -Depth 6
  if (-not $result.valid) {
    exit 2
  }
  exit 0
}

if ($Mode -eq "local-lab-readwrite" -and -not $AllowWriteMode) {
  throw "Refusing hardware smoke in local-lab-readwrite without -AllowWriteMode. Prefer local-readonly for smoke verification."
}

Write-Host "Hardware smoke verification plan" -ForegroundColor Green
Write-PlanLine "Mode: $Mode"
Write-PlanLine "Providers: $(if ($Providers.Count) { $Providers -join ', ' } else { 'all provider-smoke defaults' })"
Write-PlanLine "Read-only acknowledgements: $(if ($AcknowledgeReadOnly) { 'set for this process' } else { 'left unchanged' })"
Write-PlanLine "Operator sweep: $(if ($IncludeOperatorSweep) { 'included' } else { 'skipped' })"
Write-PlanLine "Execution: $(if ($WhatIfOnly) { 'dry run only' } else { 'will run selected read-only smoke commands' })"

$hardwareSteps = @(
  [ordered]@{
    id = "provider-smoke"
    label = "Provider smoke lane"
    command = "cd backend; python scripts\provider_smoke.py"
    reason = "Provider smoke collects read-only real-lab provider evidence."
  }
)
if ($IncludeOperatorSweep) {
  $hardwareSteps += [ordered]@{
    id = "operator-readonly-sweep"
    label = "Operator read-only sweep lane"
    command = "cd backend; python scripts\operator_readonly_sweep.py"
    reason = "Operator sweep collects broader read-only workflow evidence."
  }
}
$plan = [ordered]@{
  schema_version = "hardware-smoke-plan/v1"
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  mode = $Mode
  providers = @($Providers)
  include_operator_sweep = [bool]$IncludeOperatorSweep
  acknowledge_readonly = [bool]$AcknowledgeReadOnly
  allow_write_mode = [bool]$AllowWriteMode
  provider_smoke_require_real = $true
  execution = if ($WhatIfOnly) { "dry-run" } else { "execute" }
  steps = @($hardwareSteps)
  artifact = "artifacts/codex-runs/hardware-smoke-plan.json"
  safety_notes = @(
    "Hardware smoke is operator-triggered and separate from fast-verify.",
    "Default mode is local-readonly.",
    "local-lab-readwrite requires -AllowWriteMode and remains separate from destructive workflow confirmations."
  )
}
New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
$plan | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $hardwareSmokePlanArtifact -Encoding UTF8
Write-PlanLine "Plan artifact: artifacts/codex-runs/hardware-smoke-plan.json"

if ($WhatIfOnly) {
  Write-Host ""
  Write-Host "Dry run complete. Re-run without -WhatIfOnly to execute." -ForegroundColor Yellow
  exit 0
}

& (Join-Path $PSScriptRoot "ensure-backend-venv.ps1") -ForceInstall:$Install
if (-not (Test-Path $backendPython)) {
  throw "Backend Python was not found at $backendPython after dependency check."
}

$previousProviderMode = $env:PROVIDER_MODE
$previousSmokeProviders = $env:PROVIDER_SMOKE_PROVIDERS
$previousSmokeRequireReal = $env:PROVIDER_SMOKE_REQUIRE_REAL
$previousClosedLoopAck = $env:LAB_CLOSED_LOOP_ACK
$previousReadonlyAck = $env:LAB_READONLY_ACK

try {
  Set-EnvValue "PROVIDER_MODE" $Mode
  Set-EnvValue "PROVIDER_SMOKE_REQUIRE_REAL" "true"
  if ($Providers.Count) {
    Set-EnvValue "PROVIDER_SMOKE_PROVIDERS" ($Providers -join ",")
  } elseif (Test-Path Env:PROVIDER_SMOKE_PROVIDERS) {
    Remove-Item Env:PROVIDER_SMOKE_PROVIDERS
  }
  if ($AcknowledgeReadOnly) {
    Set-EnvValue "LAB_CLOSED_LOOP_ACK" "YES"
    Set-EnvValue "LAB_READONLY_ACK" "YES"
  }

  Invoke-HardwareStep "Provider smoke lane" {
    Push-Location $backendRoot
    try {
      & $backendPython scripts\provider_smoke.py
    } finally {
      Pop-Location
    }
  }

  if ($IncludeOperatorSweep) {
    Invoke-HardwareStep "Operator read-only sweep lane" {
      Push-Location $backendRoot
      try {
        & $backendPython scripts\operator_readonly_sweep.py
      } finally {
        Pop-Location
      }
    }
  }
} finally {
  if ($null -eq $previousProviderMode) { Remove-Item Env:PROVIDER_MODE -ErrorAction SilentlyContinue } else { Set-EnvValue "PROVIDER_MODE" $previousProviderMode }
  if ($null -eq $previousSmokeProviders) { Remove-Item Env:PROVIDER_SMOKE_PROVIDERS -ErrorAction SilentlyContinue } else { Set-EnvValue "PROVIDER_SMOKE_PROVIDERS" $previousSmokeProviders }
  if ($null -eq $previousSmokeRequireReal) { Remove-Item Env:PROVIDER_SMOKE_REQUIRE_REAL -ErrorAction SilentlyContinue } else { Set-EnvValue "PROVIDER_SMOKE_REQUIRE_REAL" $previousSmokeRequireReal }
  if ($null -eq $previousClosedLoopAck) { Remove-Item Env:LAB_CLOSED_LOOP_ACK -ErrorAction SilentlyContinue } else { Set-EnvValue "LAB_CLOSED_LOOP_ACK" $previousClosedLoopAck }
  if ($null -eq $previousReadonlyAck) { Remove-Item Env:LAB_READONLY_ACK -ErrorAction SilentlyContinue } else { Set-EnvValue "LAB_READONLY_ACK" $previousReadonlyAck }
}

Write-Host ""
Write-Host "Hardware smoke verification complete." -ForegroundColor Green
