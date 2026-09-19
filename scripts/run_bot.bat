@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "PYTHON=.venv\Scripts\pythonw.exe"
if not exist "%PYTHON%" (
    exit /b 1
)

"%PYTHON%" main.py
exit /b 0
