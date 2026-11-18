@echo off
rem Saves today's free 5-minute candles for the intraday lab (Yahoo gives only about 60 days,
rem so run this at least weekly; daily is best). What happened is written to reports\intraday_log.txt.
cd /d "%~dp0"
if not exist reports mkdir reports
call .venv\Scripts\activate.bat
echo ==== %date% %time% ==== >> reports\intraday_log.txt
cd backend
python -m intraday.refresh >> ..\reports\intraday_log.txt 2>&1
