param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8001,
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

$backendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\backend")
& (Join-Path $PSScriptRoot "ensure-backend-venv.ps1") -ForceInstall:$Install

if (-not (Test-PortAvailable -Address $HostName -ListenPort $Port)) {
  throw "Backend port $HostName`:$Port is already in use. Stop the existing process or rerun with -Port <free-port>."
}

$env:BACKEND_HOST = $HostName
$env:BACKEND_PORT = [string]$Port

Push-Location $backendRoot
try {
  & .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host $HostName --port $Port
} finally {
  Pop-Location
}
