@echo off
rem Before the market opens: global markets, overnight news, NSE pre-open prices.
rem The scheduled task runs this every weekday at 9:10 am.
rem What happened is written to reports\update_log.txt.
cd /d "%~dp0"
if not exist reports mkdir reports
call .venv\Scripts\activate.bat
echo ==== %date% %time% (before the open) ==== >> reports\update_log.txt
python premarket_update.py >> reports\update_log.txt 2>&1
