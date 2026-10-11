@echo off
rem Downloads the latest data. The scheduled task runs this every weekday evening.
rem What happened is written to reports\update_log.txt.
cd /d "%~dp0"
if not exist reports mkdir reports
call .venv\Scripts\activate.bat
echo ==== %date% %time% ==== >> reports\update_log.txt
python update_data.py >> reports\update_log.txt 2>&1
