@echo off
cd /d "%~dp0"

:: Beim ersten Start: Abhaengigkeiten automatisch installieren
if not exist ".venv\Scripts\python.exe" (
    echo [*] Erster Start - installiere Abhaengigkeiten, bitte warten...
    python -m venv .venv
    .venv\Scripts\pip install --upgrade pip -q
    .venv\Scripts\pip install -r requirements.txt -q
    echo [OK] Bereit!
    echo.
)

.venv\Scripts\python main.py %*
