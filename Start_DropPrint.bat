@echo off
setlocal enabledelayedexpansion
title DropPrint Counter Service
cd /d "%~dp0"

echo ============================================================
echo   DropPrint - Smart Jan Seva Kendra Print System
echo ============================================================
echo Starting background services...

:: 1. Find Python executable (prefer pythonw for silent windowless background execution)
set "PYTHON_EXE="
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\pythonw.exe"
) else if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0python_embed\pythonw.exe" (
    set "PYTHON_EXE=%~dp0python_embed\pythonw.exe"
) else if exist "%~dp0python_embed\python.exe" (
    set "PYTHON_EXE=%~dp0python_embed\python.exe"
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
    echo [*] Starting DropPrint Server in background...
    pushd "%~dp0mfp-print-scan-server"
    start "" "%PYTHON_EXE%" run.py --log-file "%~dp0server.log"
    popd
    
    :: Wait up to 10 seconds for server to be responsive on port 8000
    for /l %%i in (1,1,10) do (
        netstat -ano | findstr :8000 | findstr LISTENING >nul
        if !errorlevel! equ 0 goto :server_up
        ping 127.0.0.1 -n 2 >nul
    )
    :server_up
    echo [OK] DropPrint Server is listening on port 8000.
)

:: 3. Start Cloudflare Tunnel if cloudflared.exe exists and not already running
tasklist /fi "imagename eq cloudflared.exe" | findstr /i "cloudflared.exe" >nul
if %errorlevel% equ 0 (
    echo [OK] Cloudflare Tunnel is already running.
) else (
    if exist "%~dp0cloudflared.exe" (
        set "CF_TOKEN="
        if exist "%~dp0.env" (
            for /f "tokens=1,2 delims==" %%A in ('findstr /i "^TUNNEL_TOKEN= ^CLOUDFLARE_TUNNEL_TOKEN=" "%~dp0.env" 2^>nul') do (
                if not "%%B"=="" set "CF_TOKEN=%%B"
            )
        )
        if not "!CF_TOKEN!"=="" (
            echo [*] Starting Permanent Cloudflare Named Tunnel...
            start "" /min "%~dp0cloudflared.exe" tunnel run --token !CF_TOKEN!
        ) else (
            echo [*] Starting Cloudflare Secure Tunnel - Auto-sync...
            if exist "%~dp0cloudflared.log" del /f /q "%~dp0cloudflared.log"
            start "" /min "%~dp0cloudflared.exe" tunnel --url http://127.0.0.1:8000 --logfile "%~dp0cloudflared.log"
        )
        ping 127.0.0.1 -n 4 >nul
        echo [OK] Cloudflare Tunnel initialized.
    )
)

:: 4. Automatically open Shopkeeper Counter in browser
echo [*] Opening Shopkeeper Counter Dashboard...
start "" "http://localhost:8000/shopkeeper/"

echo ============================================================
echo [SUCCESS] DropPrint is ready and running in the background!
echo Shopkeeper Dashboard: http://localhost:8000/shopkeeper/
echo ============================================================
echo Note: Closing this window will NOT stop DropPrint.
echo To stop services anytime, double-click Stop_DropPrint.bat.
ping 127.0.0.1 -n 4 >nul
exit /b 0
