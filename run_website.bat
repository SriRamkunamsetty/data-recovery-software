@echo off
cd /d "%~dp0"
echo ===================================================
echo Starting RecoverX Product Showcase Website...
echo ===================================================
echo Opening in default browser at http://localhost:8080
echo Press Ctrl+C in this terminal window to stop the server.
echo ===================================================
start "" "http://localhost:8080"
.venv\Scripts\python.exe -m http.server 8080 --directory website
pause
