@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "PYTHON=.venv\Scripts\pythonw.exe"
if not exist "%PYTHON%" set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo VACNET virtual environment not found. Run install.bat first.
    exit /b 1
)

"%PYTHON%" main.py
exit /b %errorlevel%
