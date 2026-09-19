@echo off
setlocal EnableExtensions
title VACNET Uninstaller
color 0C

rem Task Scheduler and process termination require administrator rights.
fltmc >nul 2>&1
if errorlevel 1 (
    echo [INFO] Administrator access is required. Requesting elevation...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%ComSpec%' -ArgumentList '/c ""%~f0""' -WorkingDirectory '%~dp0' -Verb RunAs"
    exit /b 0
)

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
echo [1/2] Stopping and removing startup task...
schtasks /End /TN "VACNET Bot" /F >nul 2>&1
schtasks /Delete /TN "VACNET Bot" /F >nul 2>&1
if errorlevel 1 (
    echo [INFO] Task was not registered or was already removed.
) else (
    echo [OK] Startup task stopped and removed.
)

echo [INFO] Stopping VACNET tunnel processes...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -ieq 'cloudflared.exe' -and $_.CommandLine -like '*127.0.0.1:8765*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

echo [2/2] Removing installation files...
set "VACNET_REMOVE_PATH=%INSTALL_DIR%"
set "VACNET_UNINSTALL_COMMAND=$path = $env:VACNET_REMOVE_PATH; Set-Location $env:TEMP; $deadline = (Get-Date).AddSeconds(45); while ((Test-Path -LiteralPath $path) -and (Get-Date) -lt $deadline) { Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and (( $_.ExecutablePath -and $_.ExecutablePath -match 'python(w)?\.exe$' -and $_.CommandLine -like ('*' + $path + '*')) -or ($_.Name -ieq 'cloudflared.exe' -and $_.CommandLine -like '*127.0.0.1:8765*')) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; try { Remove-Item -LiteralPath $path -Recurse -Force -ErrorAction Stop } catch { Start-Sleep -Milliseconds 500 } }"
start "" /b powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "%VACNET_UNINSTALL_COMMAND%"
echo.
echo ============================================================
echo UNINSTALL STARTED - VACNET will be stopped and removed shortly.
echo ============================================================
exit /b 0
