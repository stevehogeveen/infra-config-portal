@echo off
rem Lab Builder console bridge: lets the app reach a switch's console cable (COM port) on this PC.
rem Keep this window open while setting up a switch from the app.
start "Lab Builder console bridge" powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%~dp0scripts\console-bridge.ps1"
