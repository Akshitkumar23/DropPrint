@echo off
title DropPrint Counter Service
cd /d "%~dp0"

echo ============================================================
echo   DropPrint - Smart Jan Seva Kendra Print System
echo ============================================================
echo Starting background services...

:: 1. Find Python executable
set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else if exist "python_embed\python.exe" (
    set "PYTHON_EXE=python_embed\python.exe"
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [ERROR] Python not found! Please ensure Python or .venv is installed.
        pause
        exit /b 1
    )
)

:: 2. Start DropPrint Server in background if not already running on port 8000
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo [OK] DropPrint Server is already running on port 8000.
) else (
    echo [*] Starting DropPrint Server...
    pushd mfp-print-scan-server
    start /b "" "..\%PYTHON_EXE%" run.py
    popd
    timeout /t 3 /nobreak >nul
)

:: 3. Start Cloudflare Tunnel if cloudflared.exe exists and not already running
tasklist /fi "imagename eq cloudflared.exe" | findstr /i "cloudflared.exe" >nul
if %errorlevel% equ 0 (
    echo [OK] Cloudflare Tunnel is already running.
) else (
    if exist "cloudflared.exe" (
        set "CF_TOKEN="
        if exist ".env" (
            for /f "tokens=1,2 delims==" %%A in ('findstr /i "^TUNNEL_TOKEN= ^CLOUDFLARE_TUNNEL_TOKEN=" .env 2^>nul') do (
                if not "%%B"=="" set "CF_TOKEN=%%B"
            )
        )
        if not "%CF_TOKEN%"=="" (
            echo [*] Starting Permanent Cloudflare Named Tunnel...
            start /b "" "cloudflared.exe" tunnel run --token %CF_TOKEN%
        ) else (
            echo [*] Starting Cloudflare Secure Tunnel...
            start /b "" "cloudflared.exe" tunnel --url http://127.0.0.1:8000
        )
        timeout /t 2 /nobreak >nul
    )
)

:: 4. Automatically open Shopkeeper Counter in browser
echo [*] Opening Shopkeeper Counter Dashboard...
start "" "http://localhost:8000/shopkeeper/"

echo ============================================================
echo [SUCCESS] DropPrint is ready and running!
echo Shopkeeper Dashboard: http://localhost:8000/shopkeeper/
echo ============================================================
echo (This window will automatically close in 5 seconds)
timeout /t 5 >nul
exit /b 0
