@echo off
rem Run this file ONCE (double-click). It asks Windows to run update_daily.bat
rem every weekday at 6:30 pm, after the market has closed.
rem The laptop must be switched on at that time.
rem To remove it later, run in Command Prompt:
rem     schtasks /Delete /TN "India Trading System daily update" /F
schtasks /Create /TN "India Trading System daily update" /TR "\"%~dp0update_daily.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:30 /F
pause
