@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "PYTHON=.venv\Scripts\pythonw.exe"
if not exist "%PYTHON%" set "PYTHON=.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo VACNET virtual environment not found. Run install.bat first.
    exit /b 1
)

rem Replace this command later with the real Immich/image-server script.
"%PYTHON%" -c "print('hello')"
exit /b %errorlevel%
