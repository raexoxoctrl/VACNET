@echo off
setlocal EnableExtensions
title VACNET Uninstaller
color 0C

echo ============================================================
echo                    VACNET UNINSTALLER
echo ============================================================
echo.

set "INSTALL_DIR=%~dp0"
if "%INSTALL_DIR:~-1%"=="\" set "INSTALL_DIR=%INSTALL_DIR:~0,-1%"

rem A standalone installer may have cloned the real installation to %USERPROFILE%\VACNET.
if not exist "%INSTALL_DIR%\.git\HEAD" if exist "%USERPROFILE%\VACNET\.git\HEAD" (
    set "INSTALL_DIR=%USERPROFILE%\VACNET"
)

if not exist "%INSTALL_DIR%" (
    echo [INFO] Installation directory not found: %INSTALL_DIR%
    exit /b 0
)

echo The following will be removed permanently:
echo   - VACNET files and source code
echo   - Python virtual environment and dependencies
echo   - .env secrets and local logs
echo   - Windows Task Scheduler entry: VACNET Bot
echo.
echo Install path: %INSTALL_DIR%
echo.
choice /M "Continue with uninstall"
if errorlevel 2 (
    echo [INFO] Uninstall cancelled.
    exit /b 0
)

echo.
echo [1/2] Removing startup task...
schtasks /Delete /TN "VACNET Bot" /F >nul 2>&1
if errorlevel 1 echo [INFO] Task was not registered or was already removed.
if not errorlevel 1 echo [OK] Startup task removed.

echo [2/2] Removing installation files...
set "REMOVE_PATH=%INSTALL_DIR%"
start "" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$path = '%REMOVE_PATH%'; Set-Location $env:TEMP; Start-Sleep -Seconds 1; if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }"
echo.
echo ============================================================
echo UNINSTALL STARTED - this window will close automatically.
echo ============================================================
exit /b 0
