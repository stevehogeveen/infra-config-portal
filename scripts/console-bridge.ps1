<#
Console bridge: lets Lab Builder (running in Docker) reach a switch's serial console cable on this PC.

Docker containers on Windows cannot open COM ports, so this small helper runs on the PC itself and
listens on this PC only (127.0.0.1). It understands two one-line requests per connection:

  LIST                  -> one JSON line describing the COM ports Windows can see
  OPEN <COMn> <baud>    -> "OK" then a raw byte relay between the connection and that COM port,
                           or "ERR <reason>"

It never sends anything to a port by itself; bytes only come from the app's read-only checks
and from steps the operator confirms in the app.

Run:  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\console-bridge.ps1
#>
param([int]$Port = 7091)

$ErrorActionPreference = 'Stop'
$AllowedBauds = @(9600, 19200, 38400, 57600, 115200)

function Get-ConsolePorts {
    $ports = @()
    foreach ($device in (Get-PnpDevice -Class Ports -PresentOnly -ErrorAction SilentlyContinue)) {
        if ($device.FriendlyName -notmatch '\((COM\d{1,3})\)') { continue }
        $com = $Matches[1]
        $hwid = $device.InstanceId
        if ($device.InstanceId -match '^USB\\VID_([0-9A-F]{4})&PID_([0-9A-F]{4})\\(.+)$') {
            # Same shape as pyserial's hwid, so the app's verifier reads it unchanged.
            $hwid = "USB VID:PID=$($Matches[1]):$($Matches[2]) LOCATION=$($Matches[3])"
        }
        $ports += [ordered]@{
            device       = $com
            description  = ($device.FriendlyName -replace '\s*\(COM\d{1,3}\)\s*$', '')
            manufacturer = $device.Manufacturer
            hwid         = $hwid
            status       = $device.Status
        }
    }
    return ,$ports
}

function Send-Line($stream, [string]$text) {
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($text + "`n")
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
}

function Read-Line($stream) {
    $buffer = New-Object System.Collections.Generic.List[byte]
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline -and $buffer.Count -lt 200) {
        if ($stream.DataAvailable) {
            $b = $stream.ReadByte()
            if ($b -lt 0 -or $b -eq 10) { break }
            if ($b -ne 13) { $buffer.Add([byte]$b) }
        } else { Start-Sleep -Milliseconds 10 }
    }
    return [System.Text.Encoding]::ASCII.GetString($buffer.ToArray()).Trim()
}

function Invoke-Relay($client, $stream, [string]$com, [int]$baud) {
    $serial = New-Object System.IO.Ports.SerialPort $com, $baud, 'None', 8, 'One'
    $serial.Handshake = 'None'; $serial.DtrEnable = $false; $serial.RtsEnable = $false
    $serial.ReadTimeout = 50; $serial.WriteTimeout = 500
    try { $serial.Open() } catch { Send-Line $stream "ERR $($_.Exception.GetType().Name): $($_.Exception.Message)"; return }
    Send-Line $stream 'OK'
    Write-Host "$(Get-Date -Format T) relaying $com at $baud"
    $buffer = New-Object byte[] 4096
    try {
        while ($true) {
            $idle = $true
            if ($serial.BytesToRead -gt 0) {
                $n = $serial.Read($buffer, 0, [Math]::Min($buffer.Length, $serial.BytesToRead))
                if ($n -gt 0) { $stream.Write($buffer, 0, $n); $idle = $false }
            }
            if ($stream.DataAvailable) {
                $n = $stream.Read($buffer, 0, $buffer.Length)
                if ($n -le 0) { break }
                $serial.Write($buffer, 0, $n); $idle = $false
            } elseif ($client.Client.Poll(0, [System.Net.Sockets.SelectMode]::SelectRead) -and $client.Client.Available -eq 0) {
                break  # the app closed the connection
            }
            if ($idle) { Start-Sleep -Milliseconds 10 }
        }
    } catch {
        Write-Host "$(Get-Date -Format T) relay stopped: $($_.Exception.Message)"
    } finally {
        $serial.Close()
        Write-Host "$(Get-Date -Format T) closed $com"
    }
}

$listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Loopback), $Port
$listener.Start()
Write-Host "Lab Builder console bridge listening on 127.0.0.1:$Port (Ctrl+C to stop)"
try {
    while ($true) {
        $client = $listener.AcceptTcpClient()
        try {
            $stream = $client.GetStream()
            $request = Read-Line $stream
            if ($request -eq 'LIST') {
                $list = Get-ConsolePorts; Send-Line $stream (ConvertTo-Json -InputObject $list -Compress -Depth 3)
            } elseif ($request -match '^OPEN (COM\d{1,3}) (\d{3,6})$') {
                $com = $Matches[1]; $baud = [int]$Matches[2]
                if ($AllowedBauds -notcontains $baud) { Send-Line $stream "ERR baud $baud is not allowed" }
                elseif (-not ((Get-ConsolePorts) | ForEach-Object { $_ } | Where-Object { $_.device -eq $com })) { Send-Line $stream "ERR $com is not present" }
                else { Invoke-Relay $client $stream $com $baud }
            } else {
                Send-Line $stream 'ERR unknown request'
            }
        } catch {
            Write-Host "$(Get-Date -Format T) request failed: $($_.Exception.Message)"
        } finally {
            $client.Close()
        }
    }
} finally {
    $listener.Stop()
}
