param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8001,
  [ValidateSet("", "mock", "local-readonly", "local-lab-readwrite")]
  [string]$Mode = "",
  [switch]$Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-PortAvailable {
  param(
    [string]$Address,
    [int]$ListenPort
  )

  $listener = $null
  try {
    $ipAddress = [System.Net.IPAddress]::Parse($Address)
    $listener = [System.Net.Sockets.TcpListener]::new($ipAddress, $ListenPort)
    $listener.Start()
    return $true
  } catch {
    return $false
  } finally {
    if ($null -ne $listener) {
      $listener.Stop()
    }
  }
}

function Resolve-ProviderMode {
  param(
    [string]$RequestedMode,
    [string]$RepositoryRoot
  )

  $allowedModes = @("mock", "local-readonly", "local-lab-readwrite")
  if ($RequestedMode -and $allowedModes -contains $RequestedMode) {
    return $RequestedMode
  }
  if ($env:PROVIDER_MODE -and $allowedModes -contains $env:PROVIDER_MODE) {
    return $env:PROVIDER_MODE
  }

  $modePath = Join-Path $RepositoryRoot ".local\app-mode.env"
  if (Test-Path -LiteralPath $modePath -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $modePath) {
      if ($line -match '^\s*PROVIDER_MODE\s*=\s*["'']?([^\s"'']+)["'']?\s*$') {
        $savedMode = $Matches[1]
        if ($allowedModes -contains $savedMode) {
          return $savedMode
        }
      }
    }
  }

  return "mock"
}

$backendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
& (Join-Path $PSScriptRoot "ensure-backend-venv.ps1") -ForceInstall:$Install

if (-not (Test-PortAvailable -Address $HostName -ListenPort $Port)) {
  throw "Backend port $HostName`:$Port is already in use. Stop the existing process or rerun with -Port <free-port>."
}

$env:BACKEND_HOST = $HostName
$env:BACKEND_PORT = [string]$Port
$env:PROVIDER_MODE = Resolve-ProviderMode -RequestedMode $Mode -RepositoryRoot $repoRoot.Path

Write-Host "Starting Lab Builder backend at http://$HostName`:$Port in $($env:PROVIDER_MODE) mode."

Push-Location $backendRoot
try {
  & .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host $HostName --port $Port
} finally {
  Pop-Location
}
