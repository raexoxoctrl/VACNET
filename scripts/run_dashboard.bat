@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo VACNET virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

start "VACNET Dev Dashboard" http://127.0.0.1:8765
"%PYTHON%" -m app.dashboard
exit /b %ERRORLEVEL%
