@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [Capri] Устанавливаю библиотеки...
py -m pip install -r requirements.txt || python -m pip install -r requirements.txt
if not exist models mkdir models
if not exist models\vosk-model-small-ru-0.22 (
  echo [Capri] Скачиваю модель распознавания речи ^(~45 МБ^)...
  powershell -NoProfile -Command "Invoke-WebRequest https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip -OutFile models\ru.zip; Expand-Archive models\ru.zip -DestinationPath models -Force; Remove-Item models\ru.zip"
)
echo [Capri] Готово. Запускай run.bat
pause
