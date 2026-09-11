@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo   Сборка Rekordbox Auto Cue Generator (CueGrid Pro) .EXE
echo ========================================================
if exist "..\.venv\Scripts\python.exe" (
    ..\.venv\Scripts\python.exe build_exe.py
) else (
    python build_exe.py
)
if %ERRORLEVEL% EQU 0 (
    echo.
    echo [УСПЕХ] Сборка завершена!
    echo Файл запуска: ..\dist\CueGridPro\CueGridPro.exe
) else (
    echo.
    echo [ОШИБКА] Произошла ошибка во время сборки.
)
pause
