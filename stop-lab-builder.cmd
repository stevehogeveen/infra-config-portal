@echo off
rem Lab Builder: double-click to turn the app off (backend, web pages and console bridge).
powershell -NoProfile -Command "foreach ($port in 18001, 15173, 7091) { Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }"
echo Lab Builder is off.
ping -n 3 127.0.0.1 >nul
