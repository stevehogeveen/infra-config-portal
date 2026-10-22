<#
Starts Lab Builder natively on Windows (no Docker): the backend (Python, SQLite database in
.local\lab-builder.db), the web page server (Vite), and the console bridge for switch console
cables. Each runs in its own minimized window; close those windows to stop the app.

Started by start-lab-builder.cmd. Settings come from .local\native.env (local only, never committed).
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.local\runtime\venv\Scripts\python.exe'
$envFile = Join-Path $root '.local\native.env'
$backendPort = 18001
$frontendPort = 15173

function Test-Port([int]$port) {
    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', $port); $c.Close(); return $true } catch { return $false }
}

if (-not (Test-Path $python)) { throw "Python for Lab Builder is missing ($python). Ask Claude or Codex to set it up again." }
if (-not (Test-Path $envFile)) { throw "Settings file .local\native.env is missing." }

# Settings for this process; the windows started below inherit them.
foreach ($line in Get-Content $envFile) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $name, $value = $line -split '=', 2
    [Environment]::SetEnvironmentVariable($name.Trim(), $value.Trim(), 'Process')
}
$tools = Join-Path $root '.local\runtime\bin'
if (Test-Path $tools) { $env:PATH = "$tools;$env:PATH" }
$env:PYTHON = $python

if (Test-Port $backendPort) {
    Write-Host "Backend already running on port $backendPort."
} else {
    Write-Host 'Starting the backend...'
    Start-Process -FilePath $python -ArgumentList '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$backendPort" `
        -WorkingDirectory (Join-Path $root 'app\backend') -WindowStyle Minimized
}

if (Test-Port $frontendPort) {
    Write-Host "Web page server already running on port $frontendPort."
} else {
    Write-Host 'Starting the web page server...'
    $env:FRONTEND_PORT = "$frontendPort"
    $env:FRONTEND_HOST = '127.0.0.1'
    $env:APP_PROXY_TARGET = "http://127.0.0.1:$backendPort"
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'title Lab Builder web pages && npm run dev' `
        -WorkingDirectory (Join-Path $root 'app\frontend') -WindowStyle Minimized
}

if (-not (Test-Port 7091)) {
    Write-Host 'Starting the console bridge...'
    Start-Process -FilePath 'powershell.exe' -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-File', (Join-Path $root 'scripts\console-bridge.ps1') `
        -WindowStyle Minimized
}

Write-Host 'Waiting for Lab Builder to answer...'
$deadline = (Get-Date).AddMinutes(2)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$frontendPort/health" -UseBasicParsing -TimeoutSec 3 | Out-Null
        Start-Process "http://127.0.0.1:$frontendPort/simple"
        Write-Host "Lab Builder is running at http://127.0.0.1:$frontendPort"
        exit 0
    } catch { Start-Sleep -Seconds 2 }
}
throw 'Lab Builder did not answer within 2 minutes. Open the minimized Lab Builder windows to see why.'
