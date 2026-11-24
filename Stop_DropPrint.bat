@echo off
title Stop DropPrint
echo ============================================================
echo   Stopping DropPrint Background Services
echo ============================================================

taskkill /f /im cloudflared.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
taskkill /f /im pythonw.exe >nul 2>&1

echo [OK] DropPrint services stopped cleanly.
ping 127.0.0.1 -n 3 >nul
exit /b 0
