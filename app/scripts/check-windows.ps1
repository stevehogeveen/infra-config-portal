param(
  [switch]$Install,
  [switch]$NoProxy,
  [switch]$E2E,
  [string[]]$PytestArgs = @("-q")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$appRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $appRoot "..")
$frontendRoot = Join-Path $appRoot "frontend"
$backendRoot = Join-Path $appRoot "backend"
$backendPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$portablePathScript = Join-Path $repoRoot "scripts\check-portable-paths.py"

function Invoke-Step {
  param(
    [string]$Name,
    [scriptblock]$Script
  )

  Write-Host ""
  Write-Host "==> $Name"
  & $Script
}

Invoke-Step "Windows doctor" {
  & (Join-Path $PSScriptRoot "windows-doctor.ps1")
}

Invoke-Step "Backend dependencies" {
  & (Join-Path $PSScriptRoot "ensure-backend-venv.ps1") -ForceInstall:$Install
}

Invoke-Step "Portable repository paths" {
  Push-Location $repoRoot
  try {
    & $backendPython $portablePathScript
  } finally {
    Pop-Location
  }
}

Invoke-Step "Backend tests" {
  & (Join-Path $PSScriptRoot "test-backend.ps1") -PytestArgs $PytestArgs
}

Invoke-Step "Frontend dependencies" {
  & (Join-Path $PSScriptRoot "ensure-frontend-deps.ps1") -ForceInstall:$Install -CheckOnly:(!$Install) -NoProxy:$NoProxy
}

Invoke-Step "Frontend build" {
  Push-Location $frontendRoot
  try {
    npm run build
  } finally {
    Pop-Location
  }
}

if ($E2E) {
  Invoke-Step "Playwright browsers" {
    & (Join-Path $PSScriptRoot "ensure-playwright-browsers.ps1") -Install:$Install
  }

  Invoke-Step "Frontend e2e" {
    Push-Location $frontendRoot
    try {
      npm run test:e2e
    } finally {
      Pop-Location
    }
  }
}

Write-Host ""
Write-Host "Windows check completed."
