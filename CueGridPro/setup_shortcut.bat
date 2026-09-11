@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ========================================================
echo     Создание ярлыка запуска CueGrid Pro
echo ========================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell; " ^
  "$root = (Get-Item '%~dp0..').FullName; " ^
  "$lnk = Join-Path $root 'CueGrid Pro.lnk'; " ^
  "$sc = $ws.CreateShortcut($lnk); " ^
  "$sc.TargetPath = 'wscript.exe'; " ^
  "$sc.Arguments = '\"' + (Join-Path '%~dp0' 'Launch_CueGridPro.vbs') + '\"'; " ^
  "$sc.WorkingDirectory = '%~dp0'; " ^
  "$sc.IconLocation = (Join-Path '%~dp0' 'icon.ico') + ',0'; " ^
  "$sc.Description = 'Rekordbox Auto Cue Generator (CueGrid Pro)'; " ^
  "$sc.Save(); " ^
  "Write-Host '[УСПЕХ] Ярлык успешно создан в корневой папке!' -ForegroundColor Green"
echo.
pause
