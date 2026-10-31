@echo off
cd /d "%~dp0"
echo ===================================================
echo Starting RecoverX Desktop GUI...
echo ===================================================
call .venv\Scripts\activate.bat
python -m recoverx.cli gui
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Application exited with error code %ERRORLEVEL%
    pause
)
