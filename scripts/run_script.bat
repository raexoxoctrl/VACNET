@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo VACNET virtual environment not found. Run install.bat first.
    pause
    exit /b 1
)

"%PYTHON%" exes\script.py
set "EXIT_CODE=%ERRORLEVEL%"
if errorlevel 1 (
    echo.
    echo VACNET script stopped with an error.
    if not defined VACNET_NONINTERACTIVE pause
)
exit /b %EXIT_CODE%
