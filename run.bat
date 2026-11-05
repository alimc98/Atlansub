@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

rem ---- adjust these two paths for your machine ----
if not defined WHISPER_MODEL set "WHISPER_MODEL=F:\whisper-models\large-v3-turbo-local"
set "PY=F:\WW\whisper-env\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" -m app.server
echo.
echo Server stopped.
pause
