@echo off
rem ======================================================================
rem  KONE ELEVATE - one-click setup and run (double-click this file)
rem
rem  First run : installs Python / Node.js if missing (via winget), creates
rem              backend\.venv, installs all dependencies, trains the models,
rem              seeds the demo data - then starts both servers and opens
rem              the web app. Takes a few minutes.
rem  Later runs: skips everything already done and starts in seconds.
rem
rem  Stop the servers with stop.cmd (or press Enter in this window).
rem ======================================================================
title KONE ELEVATE - setup and run
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\windows\tasks.ps1" start %*
if errorlevel 1 (
    echo.
    echo Setup or startup failed - read the messages above.
    echo Run "make doctor" in this folder for a full environment check.
    pause
    exit /b 1
)
