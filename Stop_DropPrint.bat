@echo off
title Stop DropPrint
echo ============================================================
echo   Stopping DropPrint Background Services
echo ============================================================

taskkill /f /im cloudflared.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

echo [OK] DropPrint services stopped cleanly.
timeout /t 3 >nul
