@echo off
rem Double-click this file ONCE. It puts a Kasauti icon on your desktop that opens the app.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$desk=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desk 'Kasauti.lnk')); $s.TargetPath='%~dp0start_kasauti.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0kasauti.ico'; $s.Description='Open Kasauti'; $s.Save(); Write-Host ('Shortcut made: ' + (Join-Path $desk 'Kasauti.lnk'))"
pause
