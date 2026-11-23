@echo off
title Create DropPrint Desktop Shortcut
cd /d "%~dp0"

echo ============================================================
echo   DropPrint - 1-Click Desktop Setup
echo ============================================================

set "TARGET=%~dp0Start_DropPrint.bat"
set "WORKING_DIR=%~dp0"
set "SHORTCUT_PATH=%USERPROFILE%\Desktop\DropPrint Counter.lnk"

echo Creating Desktop Shortcut: "%SHORTCUT_PATH%"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%WORKING_DIR%'; $s.IconLocation = 'shell32.dll,17'; $s.Description = 'Open DropPrint Shopkeeper Counter'; $s.Save()"

if exist "%USERPROFILE%\Desktop\DropPrint Counter.lnk" (
    echo.
    echo ============================================================
    echo [SUCCESS] Desktop Shortcut created successfully!
    echo Look for 'DropPrint Counter' icon on your Windows Desktop.
    echo Double-click that icon anytime to start the printing counter.
    echo ============================================================
) else (
    echo.
    echo [ERROR] Could not create shortcut automatically.
)

pause
