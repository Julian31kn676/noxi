@echo off
cd /d "%~dp0\.."
py tools\make_release.py || python tools\make_release.py
pause
