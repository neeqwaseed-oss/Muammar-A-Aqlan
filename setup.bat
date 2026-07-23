@echo off
REM =========================================================
REM Libyan ASR Dataset Builder Bot — Windows Setup Script
REM Run this once after cloning the project.
REM =========================================================

echo.
echo ========================================
echo  Libyan ASR Dataset Builder Bot Setup
echo ========================================
echo.

REM ── Check Python ──────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    echo Please install Python 3.10+ from https://www.python.org
    pause
    exit /b 1
)
echo [OK] Python found.

REM ── Check ffmpeg ──────────────────────────────────────────
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [WARNING] ffmpeg not found on PATH.
    echo Audio processing requires ffmpeg.
    echo Download from: https://ffmpeg.org/download.html
    echo After installing, add ffmpeg/bin to your system PATH.
    echo.
    pause
)

REM ── Create virtual environment ────────────────────────────
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    echo [OK] Virtual environment created.
) else (
    echo [OK] Virtual environment already exists.
)

REM ── Activate and install packages ─────────────────────────
echo Installing Python packages...
call venv\Scripts\activate.bat
pip install --upgrade pip --quiet
pip install -r requirements.txt

if errorlevel 1 (
    echo [ERROR] Package installation failed. Check the output above.
    pause
    exit /b 1
)
echo [OK] Packages installed.

REM ── Reminder ──────────────────────────────────────────────
echo.
echo ========================================
echo  Setup complete!
echo ========================================
echo.
echo Next steps:
echo   1. Open config\config.yaml
echo   2. Set your Telegram bot token (get one from @BotFather)
echo   3. Run the bot:  start.bat
echo.
pause
