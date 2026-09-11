@echo off
title Rekordbox Auto Cue Generator (CueGrid Pro)
cd /d "%~dp0"
echo ========================================================
echo        Rekordbox Auto Cue Generator (CueGrid Pro)
echo ========================================================
echo.
if exist ".venv\Scripts\python.exe" (
    echo Запуск через локальное виртуальное окружение...
    .venv\Scripts\python.exe start.py
) else (
    echo Проверка зависимостей Python...
    python -m pip install -r requirements.txt --quiet --no-warn-script-location
    echo.
    echo Запуск приложения...
    python start.py
)
pause
