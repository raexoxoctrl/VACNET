@echo off
setlocal EnableExtensions
title VACNET Installer
color 0B

echo ============================================================
echo                     VACNET INSTALLER
echo ============================================================
echo.
echo This installer will:
echo   [1] Download or update VACNET from GitHub
echo   [2] Create the Python virtual environment
echo   [3] Install Python dependencies
echo   [4] Install Cloudflare cloudflared
echo   [5] Configure the authenticated dashboard
echo   [6] Register VACNET to start with Windows
echo.
echo.

set "REPO_URL=%~1"
if not defined REPO_URL set "REPO_URL=https://github.com/raexoxoctrl/VACNET.git"
set "SCRIPT_DIR=%~dp0"
fltmc >nul 2>&1
if errorlevel 1 (
    echo [INFO] Administrator access is required. Requesting elevation...
    powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -WorkingDirectory '%~dp0' -Verb RunAs"
    if errorlevel 1 goto :install_failed
    exit /b 0
)
set "INSTALL_DIR=%SCRIPT_DIR:~0,-1%"

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git is required. Install Git for Windows and run this again.
    goto :install_failed
)
where py >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is required. Install Python 3.11 or newer and run this again.
    goto :install_failed
)

if exist "%INSTALL_DIR%\.git\HEAD" (
    echo [1/4] Updating existing VACNET checkout...
    pushd "%INSTALL_DIR%"
    git fetch origin main
    if errorlevel 1 goto :install_failed
    git checkout -B main origin/main --force
    if errorlevel 1 goto :install_failed
) else if exist "%INSTALL_DIR%\install.bat" (
    echo [1/4] Bootstrapping VACNET in the current installer folder...
    pushd "%INSTALL_DIR%"
    git init
    if errorlevel 1 goto :install_failed
    git remote remove origin >nul 2>&1
    git remote add origin "%REPO_URL%"
    if errorlevel 1 goto :install_failed
    git fetch origin main
    if errorlevel 1 goto :install_failed
    git checkout -B main origin/main --force
    if errorlevel 1 goto :install_failed
) else (
    set "INSTALL_DIR=%USERPROFILE%\VACNET"
    if exist "%INSTALL_DIR%" (
        echo [ERROR] Install target already exists and is not a Git checkout:
        echo          %INSTALL_DIR%
        echo Remove that folder, or run install.bat with a clean target folder.
        goto :install_failed
    )
    echo [1/4] Cloning VACNET from %REPO_URL%...
    git clone --branch main "%REPO_URL%" "%INSTALL_DIR%"
    if errorlevel 1 goto :install_failed
    pushd "%INSTALL_DIR%"
)

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    echo [INFO] Created .env from .env.example.
) else (
    echo [INFO] Existing .env preserved.
)

if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Creating Python virtual environment...
    py -3 -m venv .venv
    if errorlevel 1 goto :install_failed
)

echo [3/4] Installing Python dependencies...
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :install_failed
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :install_failed

echo [4/6] Installing Cloudflare cloudflared...
where cloudflared >nul 2>&1
if errorlevel 1 (
    where winget >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] cloudflared is missing and winget is unavailable.
        echo         Install cloudflared manually, then run this installer again.
        goto :install_failed
    )
    winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 goto :install_failed
)

echo [5/6] Configuring dashboard authentication...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$envPath = Join-Path '%INSTALL_DIR%' '.env'; $text = Get-Content -LiteralPath $envPath -Raw; if ($text -match '(?m)^DASHBOARD_AUTH_TOKEN=(replace_with_|\s*$)') { $bytes = New-Object byte[] 32; [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes); $token = [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_'); $text = [regex]::Replace($text, '(?m)^DASHBOARD_AUTH_TOKEN=.*$', ('DASHBOARD_AUTH_TOKEN=' + $token)); Set-Content -LiteralPath $envPath -Value $text -Encoding UTF8 }"
if errorlevel 1 goto :install_failed

echo [6/6] Registering VACNET to start with Windows...
set "TASK_NAME=VACNET Bot"
set "BOT_RUNNER=%INSTALL_DIR%\scripts\run_bot.bat"
schtasks /Create /TN "%TASK_NAME%" /TR "\"%BOT_RUNNER%\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F >nul
if errorlevel 1 goto :install_failed

popd
echo.
echo ============================================================
echo                 INSTALLATION COMPLETE
echo ============================================================
echo Install path : %INSTALL_DIR%
echo Task name    : %TASK_NAME%
echo Start trigger: Windows startup
echo Bot runner   : %BOT_RUNNER%
echo.
echo Next step: edit %INSTALL_DIR%\.env with your real values.
echo.
echo Press any key to close this installer.
pause >nul
exit /b 0

:install_failed
popd >nul 2>&1
echo.
echo [ERROR] Installation failed. Review the message above.
echo.
echo Press any key to close this installer.
pause >nul
exit /b 1
