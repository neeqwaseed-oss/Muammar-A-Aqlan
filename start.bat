@echo off
REM =========================================================
REM Start the Libyan ASR Dataset Builder Bot
REM =========================================================
title Libyan ASR Dataset Builder Bot

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found.
    echo Please run setup.bat first.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo Starting bot...
python main.py

if errorlevel 1 (
    echo.
    echo [ERROR] Bot exited with an error. See logs\bot.log for details.
    pause
)
