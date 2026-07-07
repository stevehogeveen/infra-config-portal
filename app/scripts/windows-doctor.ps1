Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Check {
  param(
    [string]$Name,
    [bool]$Ok,
    [string]$Detail
  )

  $status = if ($Ok) { "OK" } else { "WARN" }
  Write-Host "[$status] $Name - $Detail"
}

function Get-CommandVersion {
  param(
    [string]$Command,
    [string[]]$Arguments
  )

  $candidate = Get-Command $Command -ErrorAction SilentlyContinue
  if (-not $candidate) {
    return $null
  }

  try {
    $output = & $Command @Arguments 2>$null
  } catch {
    return $null
  }
  if ($LASTEXITCODE -ne 0 -or -not $output) {
    return $null
  }
  return ($output | Select-Object -First 1)
}

$appRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $appRoot "..")
$frontendRoot = Join-Path $appRoot "frontend"
$backendRoot = Join-Path $appRoot "backend"
$backendPython = Join-Path $backendRoot ".venv\Scripts\python.exe"

$node = Get-Command node -ErrorAction SilentlyContinue
Write-Check "Node.js" ([bool]$node) ($(if ($node) { & node --version } else { "node is not on PATH" }))

$npm = Get-Command npm -ErrorAction SilentlyContinue
Write-Check "npm" ([bool]$npm) ($(if ($npm) { & npm --version } else { "npm is not on PATH" }))

$npmProxy = if ($npm) { npm config get proxy } else { $null }
$npmHttpsProxy = if ($npm) { npm config get https-proxy } else { $null }
$proxyValues = @($npmProxy, $npmHttpsProxy) | Where-Object { $_ -and $_ -ne "null" -and $_ -ne "undefined" }
$proxyDetail = if ($proxyValues.Count) {
  "proxy configured; use -NoProxy if npm tarball downloads time out"
} else {
  "no npm proxy configured"
}
Write-Check "npm proxy" $true $proxyDetail

$pythonVersion = Get-CommandVersion "py" @("-3", "--version")
if (-not $pythonVersion) {
  $pythonVersion = Get-CommandVersion "python" @("--version")
}
if (-not $pythonVersion -and (Test-Path $backendPython)) {
  $venvVersion = & $backendPython --version 2>$null
  if ($LASTEXITCODE -eq 0 -and $venvVersion) {
    $pythonVersion = "backend venv: $($venvVersion | Select-Object -First 1)"
  }
}
Write-Check "Python" ([bool]$pythonVersion) ($(if ($pythonVersion) { $pythonVersion } else { "Python 3 is not on PATH and backend venv is not ready" }))

$backendVenvReady = Test-Path $backendPython
Write-Check "backend venv" $backendVenvReady ($(if ($backendVenvReady) { $backendPython } else { "run .\scripts\ensure-backend-venv.ps1" }))

$backendDepsReady = $false
if ($backendVenvReady) {
  & $backendPython -c "import fastapi, pytest, uvicorn" 2>$null
  $backendDepsReady = $LASTEXITCODE -eq 0
}
Write-Check "backend dependencies" $backendDepsReady ($(if ($backendDepsReady) { "FastAPI, pytest, and uvicorn import cleanly" } else { "run .\scripts\ensure-backend-venv.ps1 -ForceInstall" }))

$portablePathScript = Join-Path $repoRoot "scripts\check-portable-paths.py"
$portablePathsReady = $false
$portablePathDetail = "run after backend venv exists"
if ($backendVenvReady -and (Test-Path $portablePathScript)) {
  Push-Location $repoRoot
  try {
    $portableOutput = & $backendPython $portablePathScript 2>&1
    $portablePathsReady = $LASTEXITCODE -eq 0
    $portablePathDetail = if ($portablePathsReady) {
      ($portableOutput | Select-Object -Last 1)
    } else {
      "unsafe repository path(s) detected"
    }
  } finally {
    Pop-Location
  }
}
Write-Check "portable paths" $portablePathsReady $portablePathDetail

$packageLock = Test-Path (Join-Path $frontendRoot "package-lock.json")
Write-Check "frontend package lock" $packageLock $frontendRoot

$frontendBin = Join-Path $frontendRoot "node_modules\.bin"
$requiredBins = @("vite.cmd", "tsc.cmd", "playwright.cmd")
$missingBins = @($requiredBins | Where-Object { -not (Test-Path (Join-Path $frontendBin $_)) })
$dependenciesReady = $missingBins.Count -eq 0
$dependencyDetail = if ($dependenciesReady) {
  "Vite, TypeScript, and Playwright command shims exist"
} else {
  "run npm install in app/frontend; missing $($missingBins -join ', ')"
}
Write-Check "frontend dependencies" $dependenciesReady $dependencyDetail

$playwrightReady = $false
$playwrightDetail = "run after frontend dependencies exist"
if ($dependenciesReady) {
  Push-Location $frontendRoot
  try {
    $browserList = npx playwright install --list 2>&1
    $playwrightReady = $LASTEXITCODE -eq 0 -and ($browserList -match "chromium_headless_shell")
    $playwrightDetail = if ($playwrightReady) {
      "Chromium browser is installed"
    } else {
      "run .\scripts\ensure-playwright-browsers.ps1 -Install"
    }
  } finally {
    Pop-Location
  }
}
Write-Check "Playwright browser" $playwrightReady $playwrightDetail

$backendTarget = if ($env:APP_PROXY_TARGET) { $env:APP_PROXY_TARGET } else { "http://127.0.0.1:8001" }
Write-Check "API proxy target" $true $backendTarget

if ($npm) {
  Write-Host ""
  Write-Host "Backend test command:"
  Write-Host "  .\scripts\test-backend.ps1"
  Write-Host "Backend start command:"
  Write-Host "  .\scripts\start-backend.ps1"
  Write-Host "Frontend install command:"
  Write-Host "  .\scripts\ensure-frontend-deps.ps1"
  Write-Host "Playwright install command:"
  Write-Host "  .\scripts\ensure-playwright-browsers.ps1 -Install"
  Write-Host "Frontend start command:"
  Write-Host "  .\scripts\start-frontend.ps1"
}
