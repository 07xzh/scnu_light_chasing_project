@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "VENV=%~dp0venv"

if not exist "%VENV%\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found: %VENV%
    echo.
    echo Please create it first, see README.md - Getting Started:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo ===================================
echo   ASL Recognition Web Server
echo ===================================
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set ip=%%a
    set ip=!ip: =!
    if not "!ip!" == "127.0.0.1" (
        echo   Network URL: http://!ip!:8765
    )
)
echo   Local  URL: http://127.0.0.1:8765
echo.
echo   Tell classmates to open the Network URL
echo ===================================
echo.
start http://127.0.0.1:8765
"%VENV%\Scripts\python.exe" -m uvicorn backend.main:app --host 0.0.0.0 --port 8765
pause
