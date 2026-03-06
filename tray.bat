@echo off
cd /d "%~dp0"

:: Beim ersten Start: venv und Abhaengigkeiten installieren
if not exist ".venv\Scripts\python.exe" (
    echo [*] Erster Start - installiere Abhaengigkeiten, bitte warten...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip -q
    .venv\Scripts\python.exe -m pip install -r requirements.txt -q
    echo [OK] Bereit!
    echo.
)

:: Startup-Check (Updates + Dependencies)
.venv\Scripts\python.exe updater.py
echo.

:: Im Tray starten, kein Konsolenfenster
start "" .venv\Scripts\pythonw.exe tray.py
