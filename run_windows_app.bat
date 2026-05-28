@echo off
setlocal
cd /d "%~dp0"
python bitcoin_monitor_windows.py
if errorlevel 1 (
  echo.
  echo O aplicativo encontrou um erro. Verifique a mensagem acima.
  pause
)
