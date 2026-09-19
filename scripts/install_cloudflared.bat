@echo off
setlocal EnableExtensions
title VACNET cloudflared installer

echo Installing Cloudflare cloudflared for VACNET...
where winget >nul 2>&1
if errorlevel 1 (
    echo winget was not found.
    echo Install cloudflared manually from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    pause
    exit /b 1
)

winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
if errorlevel 1 (
    echo cloudflared installation failed.
    pause
    exit /b 1
)

echo.
echo cloudflared installed. Open a new terminal before starting VACNET.
pause
