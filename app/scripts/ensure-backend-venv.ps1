param(
  [switch]$ForceInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$backendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
$venvRoot = Join-Path $backendRoot ".venv"
$python = Join-Path $venvRoot "Scripts\python.exe"
$pip = Join-Path $venvRoot "Scripts\pip.exe"
$requirements = Join-Path $backendRoot "requirements.txt"

function Test-Python {
  param(
    [string]$Command,
    [string[]]$Arguments = @()
  )

  try {
    & $Command @Arguments --version *> $null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  }
}

if ((Test-Path $python) -and -not (Test-Python $python)) {
  $resolvedVenv = Resolve-Path $venvRoot
  if (-not $resolvedVenv.Path.StartsWith($backendRoot.Path, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove backend venv outside backend root: $($resolvedVenv.Path)"
  }
  Remove-Item -LiteralPath $resolvedVenv.Path -Recurse -Force
}

if (-not (Test-Path $python)) {
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCommand -and (Test-Python "python")) {
    & python -m venv $venvRoot
  } else {
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pythonLauncher -or -not (Test-Python "py" @("-3"))) {
      throw "Python was not found. Install Python 3 or add it to PATH, then rerun this script."
    }
    & py -3 -m venv $venvRoot
  }
}

if ($ForceInstall -or -not (Test-Path (Join-Path $venvRoot "Lib\site-packages\fastapi"))) {
  & $python -m pip install --upgrade pip
  & $pip install -r $requirements
}

Write-Host "Backend venv ready: $venvRoot"
