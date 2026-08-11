@echo off
REM ===========================================
REM   Stop all services
REM   Pure ASCII, no BOM, no chcp
REM ===========================================

cd /d "%~dp0"

echo.
echo Stopping services...
echo.

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do (
    echo Stopping backend PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 "') do (
    echo Stopping frontend PID %%a
    taskkill /F /PID %%a >nul 2>&1
)

taskkill /F /FI "WINDOWTITLE eq ZXF-Backend*" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq ZXF-Frontend*" >nul 2>&1

echo.
echo Done.
echo.
pause
exit /b 0
