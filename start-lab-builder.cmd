@echo off
rem Lab Builder: double-click to turn the app on (no Docker needed).
rem Starts the backend, the web pages and the console bridge in minimized windows, then opens the app.
rem Close those windows to turn it off.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-lab-builder.ps1"
if errorlevel 1 (
    echo.
    echo Lab Builder did not start. See the message above.
    pause
)
