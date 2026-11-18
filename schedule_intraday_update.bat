@echo off
rem Run this file ONCE (double-click). It asks Windows to run update_intraday.bat
rem every weekday at 4:15 pm, after the market has closed. The laptop must be switched on.
rem To remove it later, run in Command Prompt:
rem     schtasks /Delete /TN "India Trading System intraday data" /F
schtasks /Create /TN "India Trading System intraday data" /TR "\"%~dp0update_intraday.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:15 /F
pause
