param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$pidPath = Join-Path $repoRoot ".local\windows-runtime\lab-builder-processes.json"

if (-not (Test-Path -LiteralPath $pidPath -PathType Leaf)) {
  Write-Host "No Lab Builder process record was found."
  exit 0
}

$state = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
foreach ($property in @("frontend_pid", "backend_pid")) {
  $processId = [int]$state.$property
  if ($processId -le 0) {
    continue
  }
  $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
  if ($null -ne $process) {
    $startedProperty = $property.Replace("_pid", "_started_at")
    $recordedStart = [DateTime]::Parse([string]$state.$startedProperty).ToUniversalTime()
    $actualStart = $process.StartTime.ToUniversalTime()
    if ([Math]::Abs(($actualStart - $recordedStart).TotalSeconds) -gt 2) {
      throw "Refusing to stop process $processId because its start time does not match the owned Lab Builder session."
    }
    if ($env:OS -eq "Windows_NT") {
      & taskkill.exe /PID $processId /T /F | Out-Null
    } else {
      Stop-Process -Id $processId -Force
    }
    Write-Host "Stopped owned Lab Builder process $processId."
  }
}

Remove-Item -LiteralPath $pidPath -Force
Write-Host "Lab Builder Windows session stopped."
