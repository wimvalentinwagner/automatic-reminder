import subprocess
import sys


def notify(title: str, message: str):
    """Send a desktop notification (Linux/macOS)."""
    try:
        if sys.platform == "linux":
            subprocess.run(
                ["notify-send", "-u", "critical", "-t", "0", title, message],
                check=True
            )
        elif sys.platform == "darwin":
            script = f'display notification "{message}" with title "{title}" sound name "Ping"'
            subprocess.run(["osascript", "-e", script], check=True)
        else:
            print(f"\n[!] ERINNERUNG: {title} - {message}\n")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"\n[!] ERINNERUNG: {title}\n    {message}\n")
