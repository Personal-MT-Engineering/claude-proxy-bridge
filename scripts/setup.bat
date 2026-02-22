@echo off
REM Setup script for Claude Proxy Bridge (Windows)

echo ============================================
echo   Claude Proxy Bridge — Setup
echo ============================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed. Install Python 3.10+ first.
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo [OK] Python %%i found

REM Check pip
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not available. Install pip first.
    exit /b 1
)
echo [OK] pip found

REM Check claude CLI
where claude.cmd >nul 2>&1
if errorlevel 1 (
    where claude.exe >nul 2>&1
    if errorlevel 1 (
        echo [WARN] Claude CLI not found on PATH.
        echo        Install it or set CLAUDE_CLI_PATH in .env
    ) else (
        echo [OK] Claude CLI found
    )
) else (
    echo [OK] Claude CLI found
)

REM Navigate to project directory
cd /d "%~dp0\.."

REM Create virtual environment
if not exist ".venv" (
    echo.
    echo Creating virtual environment...
    python -m venv .venv
    echo [OK] Virtual environment created
) else (
    echo [OK] Virtual environment already exists
)

REM Activate and install
echo.
echo Installing dependencies...
call .venv\Scripts\activate.bat
pip install -e . --quiet
echo [OK] Dependencies installed

REM Copy .env if needed
if not exist ".env" (
    copy .env.example .env >nul
    echo [OK] .env file created from .env.example
    echo      Edit .env to customize settings if needed.
) else (
    echo [OK] .env already exists
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo To start the proxy bridge:
echo   .venv\Scripts\activate.bat
echo   python start.py
echo.
echo To run the health check:
echo   python scripts\health_check.py
echo.
