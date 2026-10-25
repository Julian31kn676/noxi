@echo off
chcp 65001 >nul
rem Копирует свежую версию Капри в папку репозитория GitHub (по умолчанию Desktop\capricorn),
rem не трогая личные файлы: настройки, журнал, отчёты, образцы и модель речи.
set "SRC=%~dp0.."
set "DST=%USERPROFILE%\Desktop\capricorn"
if not "%~1"=="" set "DST=%~1"
robocopy "%SRC%" "%DST%" /E /XD models reports samples __pycache__ .git .claude /XF config.json capri.log *.pyc *.zip /NFL /NDL /NJH /NP
echo.
echo Готово. Теперь открой GitHub Desktop: Commit to main, затем Push origin.
pause
