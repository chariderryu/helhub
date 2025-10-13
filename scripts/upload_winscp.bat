@echo off
set SCRIPT=C:\00work\OneDrive - keio.jp\zEtc\keioacjp\helhub\scripts\upload_winscp.txt
set LOGDIR=C:\bin\WinSCP\log
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

"C:\bin\WinSCP\WinSCP.com" ^
  /log="%LOGDIR%\helhub_!Y!M!D_!T.log" ^
  /script="%SCRIPT%"

set ERR=%ERRORLEVEL%
if %ERR% NEQ 0 (
  echo WinSCP failed with code %ERR%
  exit /b %ERR%
)
echo Upload done.
