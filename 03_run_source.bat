@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -m pip install -r requirements-runtime.txt
  py -3 src\boot.py
) else (
  python -m pip install -r requirements-runtime.txt
  python src\boot.py
)
if errorlevel 1 pause
