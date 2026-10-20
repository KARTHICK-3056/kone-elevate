@echo off
rem KONE ELEVATE - stop the servers started by setup-and-run.cmd
title KONE ELEVATE - stop
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\windows\tasks.ps1" stop
if errorlevel 1 (
    pause
    exit /b 1
)
rem Leave the result on screen briefly when double-clicked.
ping -n 3 127.0.0.1 >nul
