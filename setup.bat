@echo off
cd /d "%~dp0"
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
  echo [Capri] Python not found. Install Python 3.11+ from https://www.python.org/downloads/
  echo         and tick "Add python.exe to PATH" during installation.
  pause
  exit /b 1
)
%PY% tools\install.py
pause
