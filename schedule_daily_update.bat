@echo off
rem Run this file ONCE (double-click). It asks Windows to run:
rem   update_daily.bat   every weekday at 6:30 pm, after NSE has published the day's prices
rem   update_morning.bat every weekday at 9:10 am, after NSE's pre-open session
rem The laptop must be switched on at those times.
rem To remove them later, run in Command Prompt:
rem     schtasks /Delete /TN "India Trading System daily update" /F
rem     schtasks /Delete /TN "India Trading System morning update" /F
schtasks /Create /TN "India Trading System daily update" /TR "\"%~dp0update_daily.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:30 /F
schtasks /Create /TN "India Trading System morning update" /TR "\"%~dp0update_morning.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:10 /F
pause
