@echo off
echo Stopping all Python processes...
taskkill /F /IM python.exe /T 2>nul
if %errorlevel% equ 0 (
    echo Successfully stopped Python processes.
) else (
    echo No Python processes were running.
)
timeout /t 2 >nul
echo Done! Files should be unlocked now.
pause
