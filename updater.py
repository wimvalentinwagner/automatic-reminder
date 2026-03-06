"""
Startup-Check mit UI: Git-Updates und fehlende Dependencies prüfen.
"""
import subprocess
import sys
import os
import threading
import queue
import tkinter as tk
import tkinter.ttk as ttk

# ── Pfade ─────────────────────────────────────────────────────────────────

BASE   = os.path.dirname(os.path.abspath(__file__))
PIP    = os.path.join(BASE, ".venv", "Scripts", "pip.exe")
REQ    = os.path.join(BASE, "requirements.txt")

BG       = "#0f0f0f"
BG_CARD  = "#1a1a1a"
BG_ITEM  = "#222222"
ACCENT   = "#6c63ff"
ACCENT2  = "#ff6584"
GREEN    = "#4ade80"
YELLOW   = "#facc15"
TEXT     = "#f0f0f0"
TEXT_DIM = "#666666"
BORDER   = "#2a2a2a"
FONT     = "Segoe UI"


def run(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=BASE, **kw)


# ── Checks (laufen im Hintergrund) ────────────────────────────────────────

def check_git_updates() -> list[str]:
    run(["git", "fetch", "origin", "main"])
    log = run(["git", "log", "HEAD..origin/main", "--oneline"])
    return [l.strip() for l in log.stdout.strip().splitlines() if l.strip()]


def check_dependencies() -> list[str]:
    if not os.path.exists(REQ):
        return []
    installed = run([PIP, "list", "--format=columns"])
    installed_names = {
        line.split()[0].lower().replace("-", "_")
        for line in installed.stdout.splitlines()[2:]
        if line.strip()
    }
    missing = []
    with open(REQ) as f:
        for line in f:
            pkg = line.strip()
            if not pkg or pkg.startswith("#"):
                continue
            name = pkg.split(">=")[0].split("==")[0].split("[")[0].strip()
            if name.lower().replace("-", "_") not in installed_names:
                missing.append(pkg)
    return missing


def apply_git_update(log_cb):
    log_cb("Git pull läuft...")
    result = run(["git", "pull", "origin", "main"])
    if result.returncode == 0:
        log_cb("Code aktualisiert.")
    else:
        log_cb(f"Fehler: {result.stderr.strip()}")


def install_packages(packages: list[str], log_cb):
    for pkg in packages:
        log_cb(f"Installiere {pkg}...")
        run([PIP, "install", pkg, "-q"])
    log_cb("Alle Pakete installiert.")


# ── Update-UI ─────────────────────────────────────────────────────────────

class UpdaterWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Erinnerungs-KI – Update")
        self.geometry("480x460")
        self.resizable(False, False)
        self.configure(bg=BG)
        # Fenster mittig auf dem Bildschirm
        self.eval("tk::PlaceWindow . center")

        self._q: queue.Queue = queue.Queue()
        self._commits: list[str] = []
        self._missing: list[str] = []
        self._checked = False

        self._build()
        self.after(100, self._start_checks)
        self.after(100, self._poll)

    # ── UI aufbauen ───────────────────────────────────────────────────────

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG, pady=16)
        hdr.pack(fill="x", padx=20)
        tk.Label(hdr, text="Erinnerungs", font=(FONT, 18, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text="KI", font=(FONT, 18, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")
        tk.Label(hdr, text="Update-Check", font=(FONT, 10),
                 bg=BG, fg=TEXT_DIM).pack(side="left", padx=10, pady=4)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=20)

        # Status-Bereich
        status_frame = tk.Frame(self, bg=BG_CARD)
        status_frame.pack(fill="x", padx=20, pady=(12, 0))

        self._git_row  = self._status_row(status_frame, "Git-Updates")
        self._dep_row  = self._status_row(status_frame, "Abhängigkeiten")

        # Liste (Commits / Pakete)
        list_frame = tk.Frame(self, bg=BG_CARD)
        list_frame.pack(fill="both", expand=True, padx=20, pady=(8, 0))

        self._list_title = tk.Label(list_frame, text="", font=(FONT, 9, "bold"),
                                     bg=BG_CARD, fg=ACCENT, pady=6, padx=12)
        self._list_title.pack(anchor="w")

        self._listbox = tk.Frame(list_frame, bg=BG_CARD)
        self._listbox.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        # Log-Zeile
        self._log_label = tk.Label(self, text="", font=(FONT, 8),
                                    bg=BG, fg=TEXT_DIM)
        self._log_label.pack(pady=(6, 0))

        # Fortschrittsbalken (versteckt)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("up.Horizontal.TProgressbar",
                         troughcolor=BG_ITEM, background=ACCENT,
                         darkcolor=ACCENT, lightcolor=ACCENT,
                         bordercolor=BG, thickness=4)
        self._progress = ttk.Progressbar(self, style="up.Horizontal.TProgressbar",
                                          mode="indeterminate")

        # Buttons
        btn_row = tk.Frame(self, bg=BG, pady=14)
        btn_row.pack(fill="x", padx=20)

        self._skip_btn = tk.Button(
            btn_row, text="Überspringen", font=(FONT, 10),
            bg=BG_ITEM, fg=TEXT_DIM, activebackground=BG_CARD,
            activeforeground=TEXT, relief="flat", bd=0,
            cursor="hand2", padx=16, pady=8,
            command=self._skip,
        )
        self._skip_btn.pack(side="right", padx=(8, 0))

        self._update_btn = tk.Button(
            btn_row, text="Prüfe...", font=(FONT, 10, "bold"),
            bg=BG_ITEM, fg=TEXT_DIM, activebackground=ACCENT,
            activeforeground="white", relief="flat", bd=0,
            cursor="hand2", padx=16, pady=8,
            state="disabled", command=self._apply_updates,
        )
        self._update_btn.pack(side="right")

    def _status_row(self, parent, label: str) -> dict:
        row = tk.Frame(parent, bg=BG_CARD, pady=6, padx=12)
        row.pack(fill="x")
        tk.Label(row, text=label, font=(FONT, 9), bg=BG_CARD,
                 fg=TEXT).pack(side="left")
        dot = tk.Label(row, text="●  Prüfe...", font=(FONT, 9),
                        bg=BG_CARD, fg=TEXT_DIM)
        dot.pack(side="right")
        return {"dot": dot}

    # ── Checks starten ────────────────────────────────────────────────────

    def _start_checks(self):
        threading.Thread(target=self._run_checks, daemon=True).start()

    def _run_checks(self):
        self._q.put(("git_checking",))
        commits = check_git_updates()
        self._commits = commits
        self._q.put(("git_done", commits))

        self._q.put(("dep_checking",))
        missing = check_dependencies()
        self._missing = missing
        self._q.put(("dep_done", missing))

        self._q.put(("checks_done",))

    # ── Queue pollen ──────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                kind = msg[0]

                if kind == "git_checking":
                    self._git_row["dot"].config(text="● Prüfe...", fg=YELLOW)

                elif kind == "git_done":
                    commits = msg[1]
                    if commits:
                        self._git_row["dot"].config(
                            text=f"● {len(commits)} Update(s)", fg=YELLOW)
                    else:
                        self._git_row["dot"].config(text="● Aktuell", fg=GREEN)

                elif kind == "dep_checking":
                    self._dep_row["dot"].config(text="● Prüfe...", fg=YELLOW)

                elif kind == "dep_done":
                    missing = msg[1]
                    if missing:
                        self._dep_row["dot"].config(
                            text=f"● {len(missing)} fehlend", fg=ACCENT2)
                    else:
                        self._dep_row["dot"].config(text="● Vollständig", fg=GREEN)

                elif kind == "checks_done":
                    self._checked = True
                    self._show_results()

                elif kind == "log":
                    self._log_label.config(text=msg[1])

                elif kind == "done":
                    self._progress.stop()
                    self._progress.pack_forget()
                    self._log_label.config(text="Fertig.", fg=GREEN)
                    self._update_btn.config(text="Starten", bg=GREEN,
                                             fg=BG, state="normal",
                                             command=self.destroy)
                    self._skip_btn.config(state="disabled")

        except queue.Empty:
            pass
        self.after(100, self._poll)

    # ── Ergebnisse anzeigen ───────────────────────────────────────────────

    def _show_results(self):
        # Alten Inhalt leeren
        for w in self._listbox.winfo_children():
            w.destroy()

        has_update = bool(self._commits or self._missing)

        if self._commits:
            self._list_title.config(text="Neue Commits")
            for c in self._commits:
                tk.Label(self._listbox, text=f"• {c}", font=(FONT, 8),
                          bg=BG_CARD, fg=TEXT_DIM, anchor="w",
                          wraplength=420, justify="left").pack(anchor="w", pady=1)

        if self._missing:
            self._list_title.config(text="Fehlende Pakete" if not self._commits
                                     else "Neue Commits + Fehlende Pakete")
            for p in self._missing:
                tk.Label(self._listbox, text=f"• {p}", font=(FONT, 8),
                          bg=BG_CARD, fg=ACCENT2, anchor="w").pack(anchor="w", pady=1)

        if not has_update:
            self._list_title.config(text="Alles aktuell")
            tk.Label(self._listbox, text="Keine Updates oder fehlenden Pakete.",
                      font=(FONT, 9), bg=BG_CARD, fg=TEXT_DIM).pack(pady=8)
            self._update_btn.config(text="Starten", bg=GREEN, fg=BG,
                                     state="normal", command=self.destroy)
            self._skip_btn.config(state="disabled")
        else:
            self._update_btn.config(text="Jetzt updaten", bg=ACCENT, fg="white",
                                     state="normal")

    # ── Aktionen ──────────────────────────────────────────────────────────

    def _apply_updates(self):
        self._update_btn.config(state="disabled")
        self._skip_btn.config(state="disabled")
        self._progress.pack(fill="x", padx=20, pady=(0, 4))
        self._progress.start(10)
        threading.Thread(target=self._run_updates, daemon=True).start()

    def _run_updates(self):
        def log(msg):
            self._q.put(("log", msg))

        if self._commits:
            apply_git_update(log)
        if self._missing:
            install_packages(self._missing, log)

        self._q.put(("done",))

    def _skip(self):
        self.destroy()


# ── Einstieg ──────────────────────────────────────────────────────────────

def main():
    app = UpdaterWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
