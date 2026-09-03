param(
  [switch]$ForceInstall,
  [switch]$CheckOnly,
  [switch]$NoProxy
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$frontendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\frontend")
$viteShim = Join-Path $frontendRoot "node_modules\.bin\vite.cmd"
$tscShim = Join-Path $frontendRoot "node_modules\.bin\tsc.cmd"

if (-not $CheckOnly -and ($ForceInstall -or -not (Test-Path $viteShim) -or -not (Test-Path $tscShim))) {
  $npm = Get-Command npm -ErrorAction SilentlyContinue
  if (-not $npm) {
    throw "npm was not found. Install Node.js/npm or add npm to PATH, then rerun this script."
  }

  Push-Location $frontendRoot
  try {
    $npmArgs = @()
    if ($NoProxy) {
      $npmArgs += @("--proxy=null", "--https-proxy=null")
    }
    if (Test-Path (Join-Path $frontendRoot "package-lock.json")) {
      npm @npmArgs ci
    } else {
      npm @npmArgs install
    }
  } finally {
    Pop-Location
  }
}

if (-not (Test-Path $viteShim) -or -not (Test-Path $tscShim)) {
  throw "Frontend dependencies are incomplete. Run .\scripts\ensure-frontend-deps.ps1 after network/package registry access is available, or start with .\scripts\start-frontend.ps1 -Install."
}

Write-Host "Frontend dependencies ready: $frontendRoot"
