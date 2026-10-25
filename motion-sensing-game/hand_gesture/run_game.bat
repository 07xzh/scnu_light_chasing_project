@echo off
echo ========================================
echo Hand Gesture Control Game
echo ========================================
echo.

cd /d "%~dp0"

echo Installing dependencies...
pip install pygame opencv-python numpy mediapipe -q

echo.
echo Starting game...
python main.py

if errorlevel 1 (
    echo.
    echo Game exited with error.
    pause
)
