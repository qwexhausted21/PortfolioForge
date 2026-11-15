@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ========================================
echo   PortfolioForge - Application Launcher
echo ========================================
echo.

REM Step 1: Check Python
echo [1/4] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Install Python 3.11+ and add it to PATH.
    pause
    exit /b 1
)

REM Step 2: Create virtual environment
echo [2/4] Creating virtual environment...
if not exist venv (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM Step 3: Install dependencies
echo [3/4] Installing dependencies...
call venv\Scripts\activate.bat
pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

REM Step 4: Setup .env
echo [4/4] Setting up .env...
if not exist .env copy .env.example .env >nul

echo.
echo Starting PortfolioForge...
echo (The application window will open automatically)
echo.

venv\Scripts\python.exe app.py

pause
