@echo off
setlocal

rem Switch to this script's directory so the game can find local Python files.
cd /d "%~dp0"

rem Run the game with Gemini2 OBSENSOR mode by default.
rem Add --fullscreen if you want fullscreen by default.
python main.py --input obsensor --show-fps

rem Keep the window open if Python exits with an error.
if errorlevel 1 (
    echo.
    echo Game exited with an error. Press any key to close this window.
    pause >nul
)

endlocal
