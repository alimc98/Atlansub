@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo.
echo ==============================================================
echo   Atlansub - Persian subtitle generator
echo ==============================================================
echo.

rem ---------- 1) Python ----------
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.9 or newer was not found.
  echo.
  echo Install it from https://www.python.org/downloads/ and tick
  echo "Add python.exe to PATH" during installation.
  echo If the Microsoft Store opens instead, disable the
  echo "python.exe" App Execution Alias in Windows Settings.
  echo.
  pause
  exit /b 1
)

rem ---------- 2) virtual environment ----------
if not exist ".venv\Scripts\python.exe" (
  echo [1/3] Creating a virtual environment in .venv ...
  python -m venv .venv
  if errorlevel 1 (
    echo Could not create the virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [1/3] Virtual environment: OK
)

set "PY=%CD%\.venv\Scripts\python.exe"

rem ---------- 3) dependencies ----------
"%PY%" -c "import fastapi, uvicorn, multipart, faster_whisper, arabic_reshaper, bidi" >nul 2>nul
if errorlevel 1 (
  echo [2/3] Installing Python dependencies. This can take a few minutes ...
  "%PY%" -m pip install --upgrade pip
  "%PY%" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed. Check your internet connection.
    pause
    exit /b 1
  )
) else (
  echo [2/3] Python dependencies: OK
)

rem ---------- 4) ffmpeg + speech model ----------
echo [3/3] Checking ffmpeg and the speech model ...
"%PY%" -m app.setup
if errorlevel 1 (
  echo Setup failed. See the messages above.
  pause
  exit /b 1
)

rem ---------- 5) run ----------
echo.
echo Starting Atlansub. Close this window to stop the server.
echo.
"%PY%" -m app.server
echo.
echo Server stopped.
pause
