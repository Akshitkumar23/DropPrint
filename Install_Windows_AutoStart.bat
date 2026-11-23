@echo off
title DropPrint Auto-Start On Boot Setup
cd /d "%~dp0"

echo ============================================================
echo   DropPrint - Automatic Startup Setup
echo ============================================================
echo This will configure DropPrint to start automatically
echo whenever this computer is turned on in the morning.
echo.

set "TARGET=%~dp0Start_DropPrint.bat"
set "WORKING_DIR=%~dp0"
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "SHORTCUT_PATH=%STARTUP_FOLDER%\DropPrint Counter.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%WORKING_DIR%'; $s.IconLocation = 'shell32.dll,17'; $s.Description = 'Auto-Start DropPrint'; $s.Save()"

if exist "%SHORTCUT_PATH%" (
    echo [SUCCESS] Auto-start configured!
    echo DropPrint will now start automatically whenever the computer boots up.
) else (
    echo [ERROR] Could not configure auto-start.
)

pause
