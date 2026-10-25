@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
py tools\make_release.py || python tools\make_release.py
pause
