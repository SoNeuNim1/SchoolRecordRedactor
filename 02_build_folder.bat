@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
where py >nul 2>&1
if not errorlevel 1 (
  py -3 build_exe.py --mode onedir
) else (
  python build_exe.py --mode onedir
)
echo.
if errorlevel 1 echo BUILD FAILED. READ THE ERROR ABOVE.
echo Press any key to close.
pause >nul
