@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
set EXIT_CODE=%ERRORLEVEL%

echo.
if not "%EXIT_CODE%"=="0" (
    echo MusicGetter startup failed with exit code %EXIT_CODE%.
) else (
    echo MusicGetter stopped.
)
pause
exit /b %EXIT_CODE%
