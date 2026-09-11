@echo off
if exist "%~dp0dist\CueGridPro\CueGridPro.exe" (
    start "" "%~dp0dist\CueGridPro\CueGridPro.exe"
) else if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0start.py"
) else (
    start pythonw "%~dp0start.py"
)
