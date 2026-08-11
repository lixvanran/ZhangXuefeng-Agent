@echo off
REM ===========================================
REM   ZhangXueFeng Agent - One-Click Launcher
REM   NO chcp (causes flash close in Win11 Chinese)
REM   Pure ASCII, no BOM
REM ===========================================

cd /d "%~dp0"

echo.
echo ============================================
echo   ZhangXueFeng Agent
echo ============================================
echo.
echo Working dir: %CD%
echo.

REM ===== Check Python =====
echo [1/5] Checking Python...
where python >nul 2>&1
if errorlevel 1 goto no_python
python --version
goto python_ok

:no_python
echo [ERROR] Python not found in PATH
echo Please install from https://www.python.org/downloads/
echo IMPORTANT: Check "Add Python to PATH" during install
pause
exit /b 1

:python_ok

REM ===== Check Node =====
echo.
echo [2/5] Checking Node.js...
where node >nul 2>&1
if errorlevel 1 goto no_node
node --version
goto node_ok

:no_node
echo [ERROR] Node.js not found
echo Please install from https://nodejs.org/
pause
exit /b 1

:node_ok

REM ===== Install backend deps if needed =====
echo.
echo [3/5] Checking backend dependencies (no actual import)...
python -c "import importlib.util; m=['fastapi','uvicorn','openai','sqlalchemy','duckduckgo_search','bs4','dotenv','multipart','aiofiles','httpx','sse_starlette','pydantic_settings']; x=[n for n in m if importlib.util.find_spec(n) is None]; print('OK' if not x else 'MISS:'+','.join(x))" 2>nul > "%TEMP%\zxf-c.txt"
set /p "CR=" < "%TEMP%\zxf-c.txt" >nul
del "%TEMP%\zxf-c.txt" >nul 2>&1
if not "%CR%"=="OK" goto need_install_backend
echo [OK] Already installed
goto backend_done

:need_install_backend
echo Installing backend dependencies (1-3 min)...
python -m pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
python -m pip install -r backend\requirements.txt > "%TEMP%\zxf-backend.log" 2>&1
if errorlevel 1 goto backend_fail
echo [OK] Backend deps installed
goto backend_done

:backend_fail
echo.
echo [FAIL] Backend install error
echo.
echo Last 10 lines of log:
powershell -Command "Get-Content '%TEMP%\zxf-backend.log' -Tail 10" 2>nul
echo.
echo Full log: %TEMP%\zxf-backend.log
pause
exit /b 1

:backend_done

REM ===== Verify optional packages =====
echo.
echo [INFO] Checking optional packages (RAG)...
python -c "import chromadb" 2>nul
if errorlevel 1 (
    echo        chromadb: NOT installed
) else (
    echo        chromadb: OK
)
python -c "import sentence_transformers" 2>nul
if errorlevel 1 (
    echo        sentence-transformers: NOT installed
) else (
    echo        sentence-transformers: OK
)
python -c "import duckduckgo_search" 2>nul
if errorlevel 1 (
    echo        duckduckgo-search: NOT installed
) else (
    echo        duckduckgo-search: OK
)

REM ===== Install frontend deps if needed =====
echo.
echo [4/5] Checking frontend dependencies...
if exist "frontend\node_modules" goto frontend_done
echo Installing frontend dependencies (2-5 min)...
call npm config set registry https://registry.npmmirror.com >nul 2>&1
cd frontend
call npm install --no-audit --no-fund --ignore-scripts > "%TEMP%\zxf-frontend.log" 2>&1
if errorlevel 1 goto frontend_fail
cd ..
echo [OK] Frontend deps installed
goto frontend_done

:frontend_fail
cd ..
echo.
echo [FAIL] Frontend install error
echo.
echo Last 10 lines of log:
powershell -Command "Get-Content '%TEMP%\zxf-frontend.log' -Tail 10" 2>nul
echo.
echo Full log: %TEMP%\zxf-frontend.log
pause
exit /b 1

:frontend_done

REM ===== Check .env =====
echo.
echo [5/5] Checking configuration...
if exist "backend\.env" goto env_ok
if exist ".env" goto copy_env
if exist ".env.example" goto create_env
echo [WARN] No .env found, backend may not work
goto env_ok

:copy_env
copy /Y ".env" "backend\.env" >nul
echo [OK] .env copied to backend
goto env_ok

:create_env
copy /Y ".env.example" "backend\.env" >nul
echo [OK] .env created from template
goto env_ok

:env_ok

REM ===== Ensure LLM_FALLBACK_MODELS exists =====
findstr /C:"LLM_FALLBACK_MODELS" "backend\.env" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Adding LLM_FALLBACK_MODELS to backend\.env ...
    >> "backend\.env" echo.
    >> "backend\.env" echo # Auto-fallback models (v0.6.2+)
    >> "backend\.env" echo LLM_FALLBACK_MODELS=minimax/minimax-m2,minimax/minimax-m1,qwen/qwen-2.5-72b-instruct,meta-llama/llama-3.1-8b-instruct,deepseek/deepseek-chat
)

REM ===== Kill old processes =====
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 "') do taskkill /F /PID %%a >nul 2>&1

REM ===== Start backend =====
echo.
echo [START] Backend on port 8000...
cd /d "%~dp0backend"
start "ZXF-Backend" cmd /K "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
cd /d "%~dp0"

REM ===== Start frontend =====
echo [START] Frontend on port 3000...
cd /d "%~dp0frontend"
start "ZXF-Frontend" cmd /K "npm run dev"
cd /d "%~dp0"

echo.
echo ============================================
echo   [DONE] Services starting
echo ============================================
echo.
echo   Wait 5-10 seconds, then open browser:
echo.
echo       http://localhost:3000
echo.
echo   Two service windows should be open:
echo     ZXF-Backend  (do not close)
echo     ZXF-Frontend (do not close)
echo.
echo   To stop later, run the stop script.
echo.
timeout /t 5 /nobreak >nul
exit /b 0
