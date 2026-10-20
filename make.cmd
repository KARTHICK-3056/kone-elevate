@echo off
rem Windows entry point for the task runner - see tools\windows\tasks.ps1 / ".\make help".
rem -ExecutionPolicy Bypass applies to this one process only; it lets the
rem script run on machines whose policy blocks unsigned local .ps1 files.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\windows\tasks.ps1" %*
exit /b %ERRORLEVEL%
