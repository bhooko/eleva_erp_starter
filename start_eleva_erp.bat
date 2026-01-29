@echo off
setlocal
title Eleva ERP Starter

REM -------------------------------------------------
REM Set project root (this folder)
REM -------------------------------------------------
cd /d C:\eleva_erp_starter

echo ======================================
echo   Eleva ERP Startup
echo ======================================
echo.

REM -------------------------------------------------
REM Ensure Python launcher exists
REM -------------------------------------------------
where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python launcher not found.
  echo Install Python 3.12 and tick "Add Python to PATH".
  pause
  exit /b 1
)

REM -------------------------------------------------
REM Create virtual environment if missing
REM -------------------------------------------------
if not exist venv\Scripts\activate.bat (
  echo Creating virtual environment using Python 3.12...
  py -3.12 -m venv venv
  if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
  )
)

REM -------------------------------------------------
REM Activate virtual environment
REM -------------------------------------------------
call venv\Scripts\activate
if errorlevel 1 (
  echo ERROR: Failed to activate virtual environment.
  pause
  exit /b 1
)

echo Using:
python --version
echo.

REM -------------------------------------------------
REM Ensure Flask exists; if not, install dependencies
REM -------------------------------------------------
python -c "import flask" >nul 2>&1
if errorlevel 1 (
  echo Installing dependencies...
  python -m pip install --upgrade pip setuptools wheel
  pip install -r requirements.txt
  if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
  )
)

REM -------------------------------------------------
REM Check database folder
REM -------------------------------------------------
if not exist instance (
  echo Creating instance folder...
  mkdir instance
)

REM -------------------------------------------------
REM Start server
REM -------------------------------------------------
echo Opening browser...
start "" http://127.0.0.1:5000

echo Starting Eleva ERP server...
python app.py

echo.
echo Server stopped.
pause
