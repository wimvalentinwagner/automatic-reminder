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

:: Start in tray mode, no console window
start "" .venv\Scripts\pythonw.exe tray.py
