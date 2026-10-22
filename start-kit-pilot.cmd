@echo off
rem Kit Pilot: a separate program that builds the whole kit and ends on one report page.
rem Lab Builder must be running (start-lab-builder.cmd). Close this window to stop Kit Pilot.
set PY=%~dp0.local\runtime\python\python.exe
if not exist "%PY%" set PY=python
"%PY%" "%~dp0kit-pilot\pilot.py"
if errorlevel 1 (
    echo.
    echo Kit Pilot did not start. See the message above.
    pause
)
