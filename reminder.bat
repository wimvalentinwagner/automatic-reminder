@echo off
cd /d "%~dp0"

:: First run: create venv and install dependencies
if not exist ".venv\Scripts\python.exe" (
    echo [*] First run - installing dependencies, please wait...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip -q
    .venv\Scripts\python.exe -m pip install -r requirements.txt -q
    echo [OK] Ready!
    echo.
)

:: Startup check UI (blocks until window is closed)
.venv\Scripts\python.exe updater.py
echo.

:: With arguments: CLI mode, without: UI mode
if "%~1"=="" (
    start "" .venv\Scripts\pythonw.exe ui.py
) else (
    .venv\Scripts\python.exe main.py %*
)
