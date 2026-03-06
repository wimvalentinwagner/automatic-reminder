"""
Startup-Check: Git-Updates und fehlende Dependencies prüfen.
Wird vor dem eigentlichen Start aufgerufen.
"""
import subprocess
import sys
import os

VENV_PIP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         ".venv", "Scripts", "pip.exe")


def run(cmd, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


# ── Git-Update-Check ──────────────────────────────────────────────────────

def check_git_updates() -> list[str]:
    """Fetch remote and return list of new commit messages if updates exist."""
    print("[*] Prüfe auf Updates...", end=" ", flush=True)

    fetch = run(["git", "fetch", "origin", "main"])
    if fetch.returncode != 0:
        print("(kein Netzwerk, übersprungen)")
        return []

    log = run(["git", "log", "HEAD..origin/main", "--oneline"])
    commits = [l.strip() for l in log.stdout.strip().splitlines() if l.strip()]

    if commits:
        print(f"{len(commits)} Update(s) verfügbar.")
    else:
        print("Aktuell.")
    return commits


def apply_git_update():
    print("[*] Lade Updates...")
    result = run(["git", "pull", "origin", "main"])
    if result.returncode == 0:
        print("[OK] Code aktualisiert.")
    else:
        print(f"[!] Git pull fehlgeschlagen:\n{result.stderr}")


# ── Dependency-Check ──────────────────────────────────────────────────────

def check_dependencies() -> list[str]:
    """Return list of missing packages from requirements.txt."""
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    if not os.path.exists(req_file):
        return []

    print("[*] Prüfe Abhängigkeiten...", end=" ", flush=True)

    result = run([VENV_PIP, "install", "--dry-run", "-r", req_file])
    # packages that would be installed = missing or outdated
    missing = [
        line.split()[1] for line in result.stdout.splitlines()
        if line.strip().startswith("Would install")
    ]

    # Simpler approach: check each package individually
    missing = []
    with open(req_file) as f:
        packages = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    installed = run([VENV_PIP, "list", "--format=columns"])
    installed_names = {
        line.split()[0].lower().replace("-", "_")
        for line in installed.stdout.splitlines()[2:]
        if line.strip()
    }

    for pkg in packages:
        name = pkg.split(">=")[0].split("==")[0].split("[")[0].strip()
        normalized = name.lower().replace("-", "_")
        if normalized not in installed_names:
            missing.append(pkg)

    if missing:
        print(f"{len(missing)} fehlend.")
    else:
        print("Vollständig.")
    return missing


def install_dependencies(packages: list[str] = None):
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    if packages:
        print(f"[*] Installiere: {', '.join(packages)}")
        run([VENV_PIP, "install"] + packages)
    else:
        print("[*] Installiere alle Abhängigkeiten...")
        run([VENV_PIP, "install", "-r", req_file, "-q"])
    print("[OK] Abhängigkeiten installiert.")


# ── Hauptlogik ────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  Erinnerungs-KI – Startup-Check")
    print("=" * 50)

    any_action = False

    # 1. Git-Updates prüfen
    commits = check_git_updates()
    if commits:
        print("\n  Neue Updates:")
        for c in commits:
            print(f"    • {c}")
        print()
        answer = input("  Updates installieren? [J/n] ").strip().lower()
        if answer in ("", "j", "y", "ja", "yes"):
            apply_git_update()
            any_action = True
        else:
            print("[--] Updates übersprungen.")

    # 2. Abhängigkeiten prüfen
    missing = check_dependencies()
    if missing:
        print(f"\n  Fehlende Pakete: {', '.join(missing)}")
        answer = input("  Jetzt installieren? [J/n] ").strip().lower()
        if answer in ("", "j", "y", "ja", "yes"):
            install_dependencies(missing)
            any_action = True
        else:
            print("[!] Warnung: Fehlende Pakete könnten Fehler verursachen.")

    if not any_action:
        print("\n  Alles aktuell – starte...")
    else:
        print("\n  Fertig – starte...")

    print("=" * 50)


if __name__ == "__main__":
    main()
