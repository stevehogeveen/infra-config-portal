param(
  [switch]$Full,
  [switch]$WhatIfOnly,
  [switch]$NoFailurePacket,
  [switch]$ValidatePlan
)

$ErrorActionPreference = "Stop"

function New-FailurePacket {
  param(
    [string]$StepName
  )

  if ($NoFailurePacket -or $WhatIfOnly) {
    return
  }
  $packetScript = Join-Path $backendRoot "scripts\qa_failure_packet.py"
  if (-not (Test-Path $packetScript)) {
    Write-Warning "QA failure packet script is unavailable; skipping advisory packet creation."
    return
  }
  try {
    Write-Host ""
    Write-Host "==> Creating advisory QA failure packet" -ForegroundColor Yellow
    & $backendPython $packetScript --note "fast-verify step failed: $StepName" --max-artifacts 12
  } catch {
    Write-Warning "QA failure packet creation failed: $($_.Exception.Message)"
  }
}

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Script
  )

  Write-Host ""
  Write-Host "==> $Name" -ForegroundColor Cyan
  if ($WhatIfOnly) {
    return
  }
  try {
    $global:LASTEXITCODE = 0
    & $Script
    if ($LASTEXITCODE -ne 0) {
      throw "$Name failed with exit code $LASTEXITCODE"
    }
  } catch {
    New-FailurePacket -StepName $Name
    throw
  }
}

function Add-Unique {
  param(
    [System.Collections.Generic.List[string]]$List,
    [string]$Value,
    [string]$Reason = ""
  )
  if (-not $List.Contains($Value)) {
    $List.Add($Value)
  }
  if ($Reason -and $script:stepReasons -and -not $script:stepReasons.Contains($Value)) {
    $script:stepReasons[$Value] = $Reason
  }
}

function Test-FastVerifyPlan {
  param(
    [string]$Path
  )

  $errors = [System.Collections.Generic.List[string]]::new()
  if (-not (Test-Path $Path)) {
    $errors.Add("plan artifact not found")
    return [ordered]@{ valid = $false; artifact = "artifacts/codex-runs/fast-verify-plan.json"; errors = @($errors) }
  }
  try {
    $plan = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
  } catch {
    $errors.Add("plan JSON is invalid: $($_.Exception.Message)")
    return [ordered]@{ valid = $false; artifact = "artifacts/codex-runs/fast-verify-plan.json"; errors = @($errors) }
  }

  $plannedSteps = @($plan.planned_steps)
  $stepDetails = @($plan.step_details)
  if (-not $plan.created_at) { $errors.Add("created_at is required") }
  if ($plan.mode -notin @("selective", "full", "what-if")) { $errors.Add("mode must be selective, full, or what-if") }
  if (-not ($plan.changed_files -is [array])) { $errors.Add("changed_files must be an array") }
  if (-not ($plan.planned_steps -is [array])) { $errors.Add("planned_steps must be an array") }
  if (-not ($plan.step_details -is [array])) { $errors.Add("step_details must be an array") }
  if ($plannedSteps.Count -ne $stepDetails.Count) { $errors.Add("step_details count must match planned_steps count") }
  if ($null -eq $plan.advisory_failure_packet_enabled) { $errors.Add("advisory_failure_packet_enabled is required") }

  $detailIds = @($stepDetails | ForEach-Object { $_.id })
  foreach ($step in $plannedSteps) {
    if ($detailIds -notcontains $step) {
      $errors.Add("missing step_details entry for $step")
    }
  }
  foreach ($detail in $stepDetails) {
    if (-not $detail.id) { $errors.Add("step detail id is required") }
    if (-not $detail.reason) { $errors.Add("step detail reason is required for $($detail.id)") }
    if (-not $detail.command) { $errors.Add("step detail command is required for $($detail.id)") }
    $command = " $($detail.command) ".ToLowerInvariant()
    foreach ($unsafe in @(" -allowwritemode ", " local-lab-readwrite ", " factory-reset ", " reset ", " power ")) {
      if ($command.Contains($unsafe)) {
        $errors.Add("step detail command contains unsafe token '$($unsafe.Trim())' for $($detail.id)")
      }
    }
  }

  return [ordered]@{
    valid = $errors.Count -eq 0
    artifact = "artifacts/codex-runs/fast-verify-plan.json"
    planned_steps = @($plannedSteps)
    errors = @($errors)
  }
}

$appRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $appRoot "..")
$frontendRoot = Join-Path $appRoot "frontend"
$backendRoot = Join-Path $appRoot "backend"
$artifactRoot = Join-Path $repoRoot "artifacts\codex-runs"
$fastVerifyPlanArtifact = Join-Path $artifactRoot "fast-verify-plan.json"
$backendPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $backendPython)) {
  $backendPython = "python"
}

if ($ValidatePlan) {
  $result = Test-FastVerifyPlan -Path $fastVerifyPlanArtifact
  $result | ConvertTo-Json -Depth 6
  if (-not $result.valid) {
    exit 2
  }
  exit 0
}

$changed = @()
if (Get-Command git -ErrorAction SilentlyContinue) {
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $tracked = git -C $repoRoot diff --name-only HEAD 2>$null
    $untracked = git -C $repoRoot ls-files --others --exclude-standard 2>$null
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  $changed = @($tracked + $untracked | Where-Object {
      $_ -like "app/*" -and
      $_ -notlike "app/.codex-run-logs/*" -and
      $_ -notlike "app/frontend/dist/*" -and
      $_ -notlike "app/backend/.local/*"
    } | Sort-Object -Unique)
}

$steps = [System.Collections.Generic.List[string]]::new()
$script:stepReasons = [ordered]@{}

if ($Full -or -not $changed.Count) {
  $reason = if ($Full) { "Full verification was requested with -Full." } else { "No git diff was detected, so the safest useful default is the full app gate." }
  Add-Unique $steps "frontend-build" $reason
  Add-Unique $steps "frontend-component-tests" $reason
  Add-Unique $steps "frontend-e2e-full" $reason
  Add-Unique $steps "backend-api-full" $reason
  Add-Unique $steps "backend-workflow-diagnosis" $reason
  Add-Unique $steps "backend-openapi-contract" $reason
  Add-Unique $steps "backend-qa-capability-audit" $reason
} else {
  $frontendChanged = $changed | Where-Object { $_ -like "app/frontend/*" }
  $backendChanged = $changed | Where-Object { $_ -like "app/backend/*" }
  $scriptChanged = $changed | Where-Object { $_ -like "app/scripts/*" -or $_ -eq "app/Makefile" }
  $topologyFrontendChanged = $changed | Where-Object {
    $_ -in @(
      "app/frontend/src/operatorPages.tsx",
      "app/frontend/src/styles.css",
      "app/frontend/src/types.ts",
      "app/frontend/src/api.ts",
      "app/frontend/tests/safe-action-runner.spec.ts"
    )
  }
  $topologyFrontendFiles = @(
    "app/frontend/src/operatorPages.tsx",
    "app/frontend/src/styles.css",
    "app/frontend/src/types.ts",
    "app/frontend/src/api.ts",
    "app/frontend/tests/safe-action-runner.spec.ts"
  )
  $topologyBackendChanged = $changed | Where-Object {
    $_ -in @(
      "app/backend/app/services/topology_design_drafts.py",
      "app/backend/app/schemas.py",
      "app/backend/app/api/routes.py",
      "app/backend/tests/test_api.py"
    )
  }
  $topologyBackendFiles = @(
    "app/backend/app/services/topology_design_drafts.py",
    "app/backend/app/schemas.py",
    "app/backend/app/api/routes.py",
    "app/backend/tests/test_api.py"
  )
  $workflowDiagnosisBackendChanged = $changed | Where-Object {
    $_ -in @(
      "app/backend/app/api/routes.py",
      "app/backend/app/schemas.py",
      "app/backend/app/services/operator_issue_packets.py",
      "app/backend/scripts/qa_failure_packet.py",
      "app/backend/tests/test_qa_failure_packet.py",
      "app/backend/app/services/workflow_action_diagnosis.py",
      "app/backend/app/services/workflow_action_runner.py",
      "app/backend/app/services/workflow_action_run_store.py",
      "app/backend/app/services/workflow_registry.py",
      "app/scripts/fast-verify.ps1",
      "app/scripts/qa-failure-packet.ps1",
      "app/backend/tests/test_workflow_action_runner.py"
    )
  }
  $openapiContractChanged = $changed | Where-Object {
    $_ -in @(
      "app/backend/app/api/routes.py",
      "app/backend/app/schemas.py",
      "app/backend/app/main.py",
      "app/backend/app/services/workflow_registry.py",
      "app/backend/app/services/workflow_action_allowlist.py",
      "app/backend/scripts/openapi_contract_probe.py",
      "app/backend/tests/test_openapi_contract_probe.py"
    )
  }
  $qaCapabilityAuditChanged = $changed | Where-Object {
    $_ -in @(
      "app/backend/scripts/qa_capability_audit.py",
      "app/backend/tests/test_qa_capability_audit.py",
      "app/backend/tests/test_windows_scripts.py",
      "app/docs/testing-acceleration.md",
      "app/README.md",
      "app/scripts/fast-verify.ps1",
      "app/scripts/qa-artifact-health.ps1",
      ".github/workflows/ci.yml"
    )
  }
  $frontendOutsideTopology = $frontendChanged | Where-Object { $topologyFrontendFiles -notcontains $_ }
  $backendOutsideTopology = $backendChanged | Where-Object { $topologyBackendFiles -notcontains $_ }

  if ($frontendChanged) {
    Add-Unique $steps "frontend-build" "Frontend files changed; run TypeScript and production build before browser checks."
    Add-Unique $steps "frontend-component-tests" "Frontend files changed; run fast component/server-render checks before browser checks."
  }
  if ($frontendOutsideTopology) {
    Add-Unique $steps "frontend-e2e-full" "Frontend changes touched files outside the focused topology/design allowlist."
  } elseif ($topologyFrontendChanged) {
    Add-Unique $steps "frontend-e2e-overview-design" "Topology/composer frontend files changed; run the focused Overview Design Playwright lane."
  } elseif ($frontendChanged -and ($frontendChanged | Where-Object { $_ -like "app/frontend/tests/*" })) {
    Add-Unique $steps "frontend-e2e-full" "Frontend test files changed; run the browser suite that owns those tests."
  }

  if ($backendOutsideTopology) {
    Add-Unique $steps "backend-api-full" "Backend changes touched files outside the focused topology/design allowlist."
  } elseif ($topologyBackendChanged) {
    Add-Unique $steps "backend-api-topology-design" "Topology draft backend files changed; run focused topology draft API tests."
  } elseif ($backendChanged) {
    Add-Unique $steps "backend-api-full" "Backend files changed without a narrower registered fast lane."
  }
  if ($workflowDiagnosisBackendChanged) {
    Add-Unique $steps "backend-workflow-diagnosis" "Workflow diagnosis, QA packet, or workflow registry files changed."
  }
  if ($openapiContractChanged) {
    Add-Unique $steps "backend-openapi-contract" "API routes, schemas, workflow registry, or generated OpenAPI contract probe changed."
  }
  if ($qaCapabilityAuditChanged) {
    Add-Unique $steps "backend-qa-capability-audit" "QA acceleration capability evidence, docs, CI, or validators changed."
  }
  if ($scriptChanged) {
    Add-Unique $steps "backend-windows-scripts" "Windows helper scripts or the app Makefile changed."
  }
}

Write-Host "Fast verification plan" -ForegroundColor Green
if ($changed.Count) {
  Write-Host "Changed app files:"
  $changed | ForEach-Object { Write-Host "  $_" }
} else {
  Write-Host "No git diff detected; using full verification."
}
Write-Host "Planned steps:"
if ($steps.Count) {
  $steps | ForEach-Object { Write-Host "  $_" }
} else {
  Write-Host "  none - only docs/scripts/local files changed"
}

$stepCommands = [ordered]@{
  "frontend-build" = "cd frontend; npm run build"
  "frontend-component-tests" = "cd frontend; npm run test:component"
  "frontend-e2e-overview-design" = "cd frontend; npm run test:e2e -- -g `"overview design mode`""
  "frontend-e2e-full" = "cd frontend; npm run test:e2e"
  "backend-api-topology-design" = "cd backend; python -m pytest tests\test_api.py -q -k topology_design_draft"
  "backend-api-full" = "cd backend; python -m pytest tests\test_api.py -q"
  "backend-workflow-diagnosis" = "cd backend; python -m pytest tests\test_workflow_action_runner.py tests\test_qa_failure_packet.py -q -k `"diagnosis or issue_packet or qa_failure_packet`""
  "backend-openapi-contract" = "cd backend; python scripts\openapi_contract_probe.py; python -m pytest tests\test_openapi_contract_probe.py -q"
  "backend-qa-capability-audit" = "cd backend; python scripts\qa_capability_audit.py; python -m pytest tests\test_qa_capability_audit.py -q"
  "backend-windows-scripts" = "cd backend; python -m pytest tests\test_windows_scripts.py -q"
}
$stepDetails = @(
  foreach ($step in $steps) {
    [ordered]@{
      id = $step
      reason = if ($script:stepReasons.Contains($step)) { $script:stepReasons[$step] } else { "Selected by fast-verify routing." }
      command = if ($stepCommands.Contains($step)) { $stepCommands[$step] } else { "" }
    }
  }
)

if (-not $WhatIfOnly) {
  New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
}
$plan = [ordered]@{
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  mode = if ($Full) { "full" } elseif ($WhatIfOnly) { "what-if" } else { "selective" }
  changed_files = @($changed)
  planned_steps = @($steps)
  step_details = @($stepDetails)
  artifact = "artifacts/codex-runs/fast-verify-plan.json"
  advisory_failure_packet_enabled = -not [bool]$NoFailurePacket
  notes = @(
    "Plan is derived from git diff and untracked app files.",
    "Hardware smoke is intentionally separate; run scripts/hardware-smoke.ps1 explicitly.",
    "Failure packets are redacted, advisory-only, and do not call external AI services."
  )
}
$planJson = $plan | ConvertTo-Json -Depth 5
if ($WhatIfOnly) {
  Write-Host "Plan artifact preview:"
  Write-Host $planJson
} else {
  Set-Content -LiteralPath $fastVerifyPlanArtifact -Value $planJson -Encoding UTF8
  Write-Host "Plan artifact: artifacts/codex-runs/fast-verify-plan.json"
}

foreach ($step in $steps) {
  switch ($step) {
    "frontend-build" {
      Invoke-Step "Frontend build/type check" {
        Push-Location $frontendRoot
        try {
          npm run build
        } finally {
          Pop-Location
        }
      }
    }
    "frontend-e2e-overview-design" {
      Invoke-Step "Focused Overview Design Playwright flow" {
        Push-Location $frontendRoot
        try {
          npm run test:e2e -- -g "overview design mode"
        } finally {
          Pop-Location
        }
      }
    }
    "frontend-component-tests" {
      Invoke-Step "Frontend component/server-render tests" {
        Push-Location $frontendRoot
        try {
          npm run test:component
        } finally {
          Pop-Location
        }
      }
    }
    "frontend-e2e-full" {
      Invoke-Step "Full Playwright flow" {
        Push-Location $frontendRoot
        try {
          npm run test:e2e
        } finally {
          Pop-Location
        }
      }
    }
    "backend-api-topology-design" {
      Invoke-Step "Focused topology draft API tests" {
        Push-Location $backendRoot
        try {
          & $backendPython -m pytest tests\test_api.py -q -k topology_design_draft
        } finally {
          Pop-Location
        }
      }
    }
    "backend-api-full" {
      Invoke-Step "Backend API tests" {
        Push-Location $backendRoot
        try {
          & $backendPython -m pytest tests\test_api.py -q
        } finally {
          Pop-Location
        }
      }
    }
    "backend-workflow-diagnosis" {
      Invoke-Step "Focused workflow diagnosis and issue-packet tests" {
        Push-Location $backendRoot
        try {
          & $backendPython -m pytest tests\test_workflow_action_runner.py tests\test_qa_failure_packet.py -q -k "diagnosis or issue_packet or qa_failure_packet"
        } finally {
          Pop-Location
        }
      }
    }
    "backend-windows-scripts" {
      Invoke-Step "Windows helper script tests" {
        Push-Location $backendRoot
        try {
          & $backendPython -m pytest tests\test_windows_scripts.py -q
        } finally {
          Pop-Location
        }
      }
    }
    "backend-openapi-contract" {
      Invoke-Step "Generated OpenAPI contract probe" {
        Push-Location $backendRoot
        try {
          & $backendPython scripts\openapi_contract_probe.py
          if ($LASTEXITCODE -ne 0) { throw "OpenAPI contract probe failed with exit code $LASTEXITCODE" }
          & $backendPython -m pytest tests\test_openapi_contract_probe.py -q
        } finally {
          Pop-Location
        }
      }
    }
    "backend-qa-capability-audit" {
      Invoke-Step "QA capability audit" {
        Push-Location $backendRoot
        try {
          & $backendPython scripts\qa_capability_audit.py
          if ($LASTEXITCODE -ne 0) { throw "QA capability audit failed with exit code $LASTEXITCODE" }
          & $backendPython -m pytest tests\test_qa_capability_audit.py -q
        } finally {
          Pop-Location
        }
      }
    }
  }
}

Write-Host ""
if ($WhatIfOnly) {
  Write-Host "Dry run complete. Re-run without -WhatIfOnly to execute." -ForegroundColor Yellow
} else {
  Write-Host "Fast verification complete." -ForegroundColor Green
}
