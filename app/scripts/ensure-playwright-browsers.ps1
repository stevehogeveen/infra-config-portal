param(
  [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$frontendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\frontend")
& (Join-Path $PSScriptRoot "ensure-frontend-deps.ps1") -CheckOnly

Push-Location $frontendRoot
try {
  $browserList = npx playwright install --list 2>&1
  $hasChromium = $LASTEXITCODE -eq 0 -and ($browserList -match "chromium_headless_shell")

  if (-not $hasChromium -and $Install) {
    npx playwright install chromium
    $browserList = npx playwright install --list 2>&1
    $hasChromium = $LASTEXITCODE -eq 0 -and ($browserList -match "chromium_headless_shell")
  }

  if (-not $hasChromium) {
    throw "Playwright Chromium browser is not installed. Run .\scripts\ensure-playwright-browsers.ps1 -Install, or run .\scripts\check-windows.ps1 -Install -E2E."
  }
} finally {
  Pop-Location
}

Write-Host "Playwright Chromium browser ready."
