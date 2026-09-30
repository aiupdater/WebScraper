@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
  echo Nejprve spustte _INSTALOVAT.bat.
  pause
  exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" -m system.run_all
exit /b 0
