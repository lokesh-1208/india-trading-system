@echo off
rem Double-click this file to open Kasauti in your browser.
rem Keep the black window open while you use it; close it to stop the app.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
rem Installs any library added since last time (quick when nothing is new).
python -m pip install -q -r requirements.txt
echo Starting Kasauti... the page opens in your browser in a few seconds.
start "" /b cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8765"
python -m uvicorn server.app:app --host 127.0.0.1 --port 8765
pause
