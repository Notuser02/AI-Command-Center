@echo off
title AI Command Center - Launcher
cd /d "%~dp0"

echo ============================================
echo   AI COMMAND CENTER - STARTING UP
echo ============================================
echo.

REM ── Start Ollama if it isn't running ──
%SystemRoot%\System32\curl.exe -s -o nul -m 2 http://localhost:11434/api/tags
if %errorlevel%==0 goto :ollama_ready

set "OLLAMA_EXE="
for /f "delims=" %%i in ('where ollama 2^>nul') do (
    if not defined OLLAMA_EXE set "OLLAMA_EXE=%%~fi"
)

if not defined OLLAMA_EXE (
    echo [!] Ollama is not installed on this PC - continuing without it.
    echo [!] Install it from https://ollama.com so agents can answer.
    echo.
    goto :backend
)

echo Starting Ollama (server on the CLI)...
start "Ollama Server" cmd /k ""%OLLAMA_EXE%" serve"

echo Waiting for Ollama to respond...
set /a otries=0
:ollamawait
%SystemRoot%\System32\timeout.exe /t 1 /nobreak >nul
%SystemRoot%\System32\curl.exe -s -o nul -m 2 http://localhost:11434/api/tags
if %errorlevel%==0 goto :ollama_ready
set /a otries+=1
if %otries% lss 45 goto :ollamawait
echo [!] Ollama did not respond within 45 seconds - continuing anyway.
echo.
goto :backend

:ollama_ready
echo Ollama is running.

:backend
REM ── If the backend is already running, just open the dashboard ──
%SystemRoot%\System32\curl.exe -s -o nul -m 2 http://127.0.0.1:8000/status
if %errorlevel%==0 (
    echo Backend is already running - opening the dashboard...
    start "" http://127.0.0.1:8000/
    goto :phone_hint
)

if not exist "backend\venv\Scripts\uvicorn.exe" (
    echo [ERROR] backend\venv not found. Run:
    echo         cd backend ^&^& python -m venv venv ^&^& .\venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting the backend on port 8000...
start "AI Command Center Backend" cmd /k "cd /d %~dp0backend && .\venv\Scripts\uvicorn.exe main:app --host 0.0.0.0 --port 8000"

echo Waiting for the server to come up...
set /a tries=0
:waitloop
%SystemRoot%\System32\timeout.exe /t 1 /nobreak >nul
%SystemRoot%\System32\curl.exe -s -o nul -m 2 http://127.0.0.1:8000/status
if %errorlevel%==0 goto :ready
set /a tries+=1
if %tries% lss 30 goto :waitloop
echo [ERROR] Backend did not start within 30 seconds.
echo         Check the "AI Command Center Backend" window for the error.
pause
exit /b 1

:ready
echo Server is up - opening your dashboard in the browser...
start "" http://127.0.0.1:8000/

REM ── Optionally start the mobile app dev server too ──
echo.
choice /c yn /t 6 /d n /m "Also start the MOBILE APP server (Expo) for your phone"
if errorlevel 2 goto :phone_hint
start "AI Command Center Mobile (Expo)" cmd /k "cd /d %~dp0mobile && npx expo start"
echo Mobile server starting in its own window - scan its QR code with Expo Go.

:phone_hint
echo.
echo --------------------------------------------
echo  Dashboard : http://127.0.0.1:8000
echo  Phone app : same Wi-Fi, then in app Settings use:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4" ^| findstr /v "192.168.56."') do (
    for /f "tokens=* delims= " %%b in ("%%a") do echo               http://%%b:8000
)
echo --------------------------------------------
echo  To STOP everything, close these console windows:
echo    - "AI Command Center Backend"
echo    - "Ollama Server"
echo.
echo This launcher window will close in a few seconds...
%SystemRoot%\System32\timeout.exe /t 6 >nul
