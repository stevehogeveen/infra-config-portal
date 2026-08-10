param(
  [string]$HostName = "127.0.0.1",
  [int]$BackendPort = 8001,
  [int]$FrontendPort = 5173,
  [ValidateSet("", "mock", "local-readonly", "local-lab-readwrite")]
  [string]$Mode = "",
  [switch]$Install,
  [switch]$NoProxy,
  [switch]$NoBrowser,
  [int]$StartupTimeoutSeconds = 90
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

function Wait-HttpReady {
  param(
    [string]$Url,
    [int]$TimeoutSeconds,
    [System.Diagnostics.Process[]]$Processes
  )

  $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
  while ([DateTime]::UtcNow -lt $deadline) {
    foreach ($process in $Processes) {
      if ($process.HasExited) {
        throw "A Lab Builder process exited before $Url became ready."
      }
    }
    try {
      $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
        return
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  }
  throw "Timed out waiting for $Url after $TimeoutSeconds seconds."
}

function Format-ProcessArgument {
  param([string]$Value)

  return '"' + $Value.Replace('"', '\"') + '"'
}

function Stop-OwnedProcess {
  param([AllowNull()][System.Diagnostics.Process]$Process)

  if ($null -ne $Process -and -not $Process.HasExited) {
    if ($env:OS -eq "Windows_NT") {
      & taskkill.exe /PID $Process.Id /T /F 2>$null | Out-Null
    } else {
      Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
    }
  }
}

$appRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$repoRoot = Resolve-Path (Join-Path $appRoot "..")
$runtimeDir = Join-Path $repoRoot ".local\windows-runtime"
$pidPath = Join-Path $runtimeDir "lab-builder-processes.json"
$backendLog = Join-Path $runtimeDir "backend.log"
$backendErrorLog = Join-Path $runtimeDir "backend-error.log"
$frontendLog = Join-Path $runtimeDir "frontend.log"
$frontendErrorLog = Join-Path $runtimeDir "frontend-error.log"

if (-not (Test-PortAvailable -Address $HostName -ListenPort $BackendPort)) {
  throw "Backend port $HostName`:$BackendPort is already in use. Stop the existing process or choose -BackendPort <free-port>."
}
if (-not (Test-PortAvailable -Address $HostName -ListenPort $FrontendPort)) {
  throw "Frontend port $HostName`:$FrontendPort is already in use. Stop the existing process or choose -FrontendPort <free-port>."
}

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
Remove-Item -LiteralPath $backendLog, $backendErrorLog, $frontendLog, $frontendErrorLog -Force -ErrorAction SilentlyContinue

$shell = Get-Command pwsh -ErrorAction SilentlyContinue
if ($null -eq $shell) {
  $shell = Get-Command powershell -ErrorAction Stop
}

$backendArgs = @(
  "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
  (Join-Path $PSScriptRoot "start-backend.ps1"),
  "-HostName", $HostName,
  "-Port", [string]$BackendPort
)
if ($Mode) {
  $backendArgs += @("-Mode", $Mode)
}
if ($Install) {
  $backendArgs += "-Install"
}

$frontendArgs = @(
  "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
  (Join-Path $PSScriptRoot "start-frontend.ps1"),
  "-HostName", $HostName,
  "-Port", [string]$FrontendPort,
  "-ProxyTarget", "http://$HostName`:$BackendPort"
)
if ($Install) {
  $frontendArgs += "-Install"
}
if ($NoProxy) {
  $frontendArgs += "-NoProxy"
}

$backendProcess = $null
$frontendProcess = $null
try {
  $backendArgumentLine = ($backendArgs | ForEach-Object { Format-ProcessArgument -Value ([string]$_) }) -join " "
  $frontendArgumentLine = ($frontendArgs | ForEach-Object { Format-ProcessArgument -Value ([string]$_) }) -join " "
  $backendProcess = Start-Process -FilePath $shell.Source -ArgumentList $backendArgumentLine -PassThru -WindowStyle Hidden -RedirectStandardOutput $backendLog -RedirectStandardError $backendErrorLog
  Wait-HttpReady -Url "http://$HostName`:$BackendPort/health" -TimeoutSeconds $StartupTimeoutSeconds -Processes @($backendProcess)

  $frontendProcess = Start-Process -FilePath $shell.Source -ArgumentList $frontendArgumentLine -PassThru -WindowStyle Hidden -RedirectStandardOutput $frontendLog -RedirectStandardError $frontendErrorLog
  Wait-HttpReady -Url "http://$HostName`:$FrontendPort/simple" -TimeoutSeconds $StartupTimeoutSeconds -Processes @($backendProcess, $frontendProcess)

  $state = [ordered]@{
    schema_version = "lab-builder-windows-runtime/v1"
    started_at = [DateTime]::UtcNow.ToString("o")
    host = $HostName
    backend_port = $BackendPort
    frontend_port = $FrontendPort
    backend_pid = $backendProcess.Id
    frontend_pid = $frontendProcess.Id
    backend_started_at = $backendProcess.StartTime.ToUniversalTime().ToString("o")
    frontend_started_at = $frontendProcess.StartTime.ToUniversalTime().ToString("o")
    frontend_url = "http://$HostName`:$FrontendPort/simple"
    backend_health_url = "http://$HostName`:$BackendPort/health"
  }
  $state | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding utf8
} catch {
  Stop-OwnedProcess -Process $frontendProcess
  Stop-OwnedProcess -Process $backendProcess
  Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
  throw
}

Write-Host "Lab Builder is ready: $($state.frontend_url)"
Write-Host "Health check: $($state.backend_health_url)"
Write-Host "Logs and owned process IDs: $runtimeDir"
if (-not $NoBrowser) {
  Start-Process $state.frontend_url
}
