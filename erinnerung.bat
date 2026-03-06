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

:: Startup-Check UI (blockiert bis Fenster geschlossen)
.venv\Scripts\python.exe updater.py
echo.

:: Mit Argumenten: CLI, ohne Argumente: UI
if "%~1"=="" (
    start "" .venv\Scripts\pythonw.exe ui.py
) else (
    .venv\Scripts\python.exe main.py %*
)
