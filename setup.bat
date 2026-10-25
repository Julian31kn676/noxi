@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=python"
where py >nul 2>nul && set "PY=py"
echo [Capri] Устанавливаю библиотеки...
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo [Capri] Библиотеки не установились. Проверь интернет и что Python поставлен с галочкой «Add python.exe to PATH».
  pause
  exit /b 1
)
echo.
%PY% tools\download_model.py
if errorlevel 1 (
  pause
  exit /b 1
)
echo.
echo [Capri] Готово. Запускай run.bat
pause
