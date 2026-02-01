@echo off
setlocal
title Eleva ERP Starter

REM -------------------------------------------------
REM Set project root
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
REM Ensure instance folder exists
REM -------------------------------------------------
if not exist instance (
  mkdir instance
)

REM -------------------------------------------------
REM Start server in a separate window
REM -------------------------------------------------
echo Starting Eleva ERP server...
start "Eleva ERP Server" cmd /k ^
  "cd /d C:\eleva_erp_starter && call venv\Scripts\activate && python app.py"

REM -------------------------------------------------
REM Wait until server responds
REM -------------------------------------------------
echo Waiting for server to be ready...
powershell -NoProfile -Command ^
  "$url='http://127.0.0.1:5000/';" ^
  "$max=60; $ok=$false;" ^
  "for($i=0; $i -lt $max; $i++){" ^
  "  try { Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 1 }" ^
  "}" ^
  "if($ok){ exit 0 } else { exit 1 }"

if errorlevel 1 (
  echo ERROR: Server did not become ready within 60 seconds.
  echo Check the 'Eleva ERP Server' window for errors.
  pause
  exit /b 1
)

REM -------------------------------------------------
REM Open browser and exit starter
REM -------------------------------------------------
start "" http://127.0.0.1:5000

exit /b 0
