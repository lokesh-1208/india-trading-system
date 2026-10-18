@echo off
title Kasauti
rem Double-click this file (or the Kasauti shortcut) to open Kasauti in your browser.
rem Keep this window open while you use it; close it to stop the app.
cd /d "%~dp0"
if not exist reports mkdir reports
echo %date% %time% started >> reports\kasauti_start.log
call .venv\Scripts\activate.bat
echo Checking libraries (the first time this takes about a minute)...
python -m pip install -q -r backend\requirements.txt >> reports\kasauti_start.log 2>&1
echo.
echo Starting Kasauti. The page opens in your browser as soon as it is ready.
echo Keep this window open while you use Kasauti. Close it to stop.
echo.
start "" /b python backend\server\open_browser.py
python -m uvicorn server.app:app --app-dir backend --host 127.0.0.1 --port 8765 2>> reports\kasauti_start.log
echo.
echo Kasauti stopped. If you see an error above, send it to Claude.
pause
