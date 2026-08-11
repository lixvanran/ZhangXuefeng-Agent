@echo off
REM ===========================================
REM   Diagnostic - saves report to file
REM   Pure ASCII, no BOM, no chcp
REM ===========================================

cd /d "%~dp0"

set REPORT=diagnose.txt

echo Saving diagnostic to %REPORT%...

(
    echo ============================================
    echo   Diagnostic Report
    echo   %DATE% %TIME%
    echo ============================================
    echo.
    echo --- Working Dir ---
    echo %CD%
    echo.
    echo --- System ---
    ver
    echo.
    echo --- Python ---
    where python 2>&1
    python --version 2>&1
    python -m pip --version 2>&1
    echo pip config:
    python -m pip config list 2>&1
    echo.
    echo --- Node ---
    where node 2>&1
    node --version 2>&1
    where npm 2>&1
    npm --version 2>&1
    npm config get registry 2>&1
    echo.
    echo --- Ports 3000/8000 ---
    netstat -ano | findstr ":3000 :8000" 2>&1
    echo.
    echo --- Project files ---
    dir /b
    echo.
    echo --- Backend ---
    if exist backend\requirements.txt (
        echo requirements.txt exists
    ) else (
        echo requirements.txt MISSING
    )
    if exist backend\.env (
        echo .env exists
    ) else (
        echo .env MISSING
    )
    echo.
    echo --- Frontend ---
    if exist frontend\node_modules (
        echo node_modules exists
    ) else (
        echo node_modules MISSING
    )
) > "%REPORT%" 2>&1

echo.
echo Done. Report: %CD%\%REPORT%
echo.
echo Please send this file to support.
echo.
pause
exit /b 0
