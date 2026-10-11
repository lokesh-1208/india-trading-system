@echo off
rem Double-click this file to open the dashboard in your browser.
rem Keep the black window open while you use the dashboard; close it to stop.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
streamlit run dashboard.py
pause
