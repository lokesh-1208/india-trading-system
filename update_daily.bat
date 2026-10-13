@echo off
rem Downloads the latest data. The scheduled task runs this every weekday evening.
rem What happened is written to reports\update_log.txt.
cd /d "%~dp0"
if not exist reports mkdir reports
call .venv\Scripts\activate.bat
rem New libraries added to requirements.txt are installed here (quick when nothing is new).
python -m pip install -q -r requirements.txt >> reports\update_log.txt 2>&1
echo ==== %date% %time% ==== >> reports\update_log.txt
python update_data.py >> reports\update_log.txt 2>&1
