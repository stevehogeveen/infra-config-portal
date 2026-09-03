param(
  [string]$HostName = "127.0.0.1",
  [int]$Port = 5173,
  [string]$ProxyTarget = "http://127.0.0.1:8001",
  [switch]$Install,
  [switch]$NoProxy
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

$frontendRoot = Resolve-Path (Join-Path $PSScriptRoot "..\frontend")
& (Join-Path $PSScriptRoot "ensure-frontend-deps.ps1") -ForceInstall:$Install -CheckOnly:(!$Install) -NoProxy:$NoProxy

if (-not (Test-PortAvailable -Address $HostName -ListenPort $Port)) {
  throw "Frontend port $HostName`:$Port is already in use. Stop the existing process or rerun with -Port <free-port>."
}

$env:FRONTEND_HOST = $HostName
$env:FRONTEND_PORT = [string]$Port
$env:APP_PROXY_TARGET = $ProxyTarget
$env:VITE_API_BASE_URL = ""

Push-Location $frontendRoot
try {
  npm run dev
} finally {
  Pop-Location
}
