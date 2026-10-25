@echo off
cd /d "%~dp0"
where pyw >nul 2>nul && (start "" pyw main.py) || (start "" pythonw main.py)
