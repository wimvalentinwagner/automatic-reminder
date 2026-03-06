import tkinter as tk
import os
import tkinter.ttk as ttk
import threading
import queue
import time
import collections
from pathlib import Path
from datetime import datetime
from storage import load_reminders, add_reminder, delete_reminder, find_reminder_by_keyword
from detector import detect_reminder, fetch_ollama_models, is_model_installed, pull_model
from settings import load_settings, save_settings
import gcal
import caldav_cal
import calendars as cal_providers

# ── Farben & Stil ──────────────────────────────────────────────────────────
BG       = "#0f0f0f"
BG_CARD  = "#1a1a1a"
BG_ITEM  = "#222222"
ACCENT   = "#6c63ff"
ACCENT2  = "#ff6584"
TEXT     = "#f0f0f0"
TEXT_DIM = "#666666"
TEXT_MID = "#aaaaaa"
GREEN    = "#4ade80"
YELLOW   = "#facc15"
BORDER   = "#2a2a2a"
FONT     = "Segoe UI"

WHISPER_MODELS = {
    "tiny":   {"size": "~75 MB",  "speed": "Sehr schnell", "mb": 75},
    "base":   {"size": "~145 MB", "speed": "Schnell",      "mb": 145},
    "small":  {"size": "~465 MB", "speed": "Mittel",       "mb": 465},
    "medium": {"size": "~1.5 GB", "speed": "Langsam",      "mb": 1500},
    "large":  {"size": "~3 GB",   "speed": "Sehr langsam", "mb": 3000},
}

# Wie viele Sprach-Segmente werden zusammen analysiert (Kontext-Fenster)
CONTEXT_WINDOW = 5


def is_model_cached(model_name: str) -> bool:
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    model_dir = cache_dir / f"models--Systran--faster-whisper-{model_name}"
    return model_dir.exists() and any(model_dir.iterdir())


def get_cache_size_mb(model_name: str) -> float:
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    model_dir = cache_dir / f"models--Systran--faster-whisper-{model_name}"
    if not model_dir.exists():
        return 0.0
    total = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())
    return total / (1024 * 1024)


class ReminderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Erinnerungs-Tool")
        self.geometry("540x860")
        self.minsize(440, 640)
        self.configure(bg=BG)
        self.resizable(True, True)

        self._queue = queue.Queue()
        self._listening = False
        self._dot_state = 0
        self._settings = load_settings()
        self._selected_whisper = self._settings.get("whisper_model", "small")
        self._selected_ollama = tk.StringVar(value=self._settings.get("ollama_model", "Lade..."))
        self._model_cards = {}
        self._dl_stop = threading.Event()

        self._build_ui()
        self._load_existing_reminders()
        self._refresh_model_badges()
        self._process_queue()

        # Ollama-Modelle im Hintergrund laden
        threading.Thread(target=self._load_ollama_models, daemon=True).start()

    # ── UI aufbauen ────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG, pady=14)
        header.pack(fill="x", padx=20)
        tk.Label(header, text="Erinnerungs", font=(FONT, 20, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(header, text="KI", font=(FONT, 20, "bold"),
                 bg=BG, fg=ACCENT).pack(side="left")

        status_row = tk.Frame(header, bg=BG)
        status_row.pack(side="right", pady=4)
        self._dot = tk.Label(status_row, text="●", font=(FONT, 12),
                              bg=BG, fg=TEXT_DIM)
        self._dot.pack(side="left")
        self._status_label = tk.Label(status_row, text="Gestoppt",
                                       font=(FONT, 9), bg=BG, fg=TEXT_DIM)
        self._status_label.pack(side="left", padx=(3, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=20)

        # ── Tabs ──────────────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dark.TNotebook", background=BG, borderwidth=0,
                         tabmargins=[20, 8, 0, 0])
        style.configure("Dark.TNotebook.Tab",
                         background=BG_ITEM, foreground=TEXT_DIM,
                         font=(FONT, 9), padding=[14, 6],
                         borderwidth=0, relief="flat")
        style.map("Dark.TNotebook.Tab",
                   background=[("selected", BG_CARD)],
                   foreground=[("selected", TEXT)])

        self._notebook = ttk.Notebook(self, style="Dark.TNotebook")
        self._notebook.pack(fill="both", expand=True)

        tab1 = tk.Frame(self._notebook, bg=BG)
        tab2 = tk.Frame(self._notebook, bg=BG)
        self._notebook.add(tab1, text="  Erinnerungen  ")
        self._notebook.add(tab2, text="  Kalender  ")

        self._build_tab_main(tab1)
        self._build_tab_calendar(tab2)

    def _build_tab_main(self, parent):
        style = ttk.Style()
        # ── Whisper Modellauswahl ──────────────────────────────────────────
        whisper_section = tk.Frame(parent, bg=BG_CARD)
        whisper_section.pack(fill="x", padx=20, pady=(12, 0))

        title_row = tk.Frame(whisper_section, bg=BG_CARD)
        title_row.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(title_row, text="Whisper Modell", font=(FONT, 9, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(side="left")
        tk.Label(title_row, text="– Spracherkennung",
                 font=(FONT, 8), bg=BG_CARD, fg=TEXT_DIM).pack(side="left", padx=6)

        self._model_grid = tk.Frame(whisper_section, bg=BG_CARD)
        self._model_grid.pack(fill="x", padx=12, pady=(0, 10))

        for i, (name, info) in enumerate(WHISPER_MODELS.items()):
            self._build_model_card(name, info, row=i // 3, col=i % 3)

        # ── Ollama Modellauswahl ───────────────────────────────────────────
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(8, 0))

        ollama_section = tk.Frame(parent, bg=BG_CARD)
        ollama_section.pack(fill="x", padx=20, pady=(0, 0))

        ollama_row = tk.Frame(ollama_section, bg=BG_CARD)
        ollama_row.pack(fill="x", padx=12, pady=10)

        tk.Label(ollama_row, text="Ollama Modell", font=(FONT, 9, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(side="left")
        tk.Label(ollama_row, text="– Erinnerungserkennung",
                 font=(FONT, 8), bg=BG_CARD, fg=TEXT_DIM).pack(side="left", padx=6)

        # Refresh-Button
        self._refresh_btn = tk.Button(
            ollama_row, text="↻", font=(FONT, 10),
            bg=BG_ITEM, fg=TEXT_DIM, relief="flat", bd=0,
            cursor="hand2", padx=6, pady=0,
            command=lambda: threading.Thread(
                target=self._load_ollama_models, daemon=True).start()
        )
        self._refresh_btn.pack(side="right")

        # Dropdown für Ollama-Modelle
        style = ttk.Style()
        style.theme_use("default")
        style.configure("dark.TCombobox",
                         fieldbackground=BG_ITEM, background=BG_ITEM,
                         foreground=TEXT, selectbackground=ACCENT,
                         selectforeground="white", arrowcolor=TEXT_DIM)

        self._ollama_combo = ttk.Combobox(
            ollama_section, textvariable=self._selected_ollama,
            style="dark.TCombobox", state="readonly",
            font=(FONT, 9), height=8,
        )
        self._ollama_combo.pack(fill="x", padx=12, pady=(0, 6))
        self._ollama_combo.bind("<<ComboboxSelected>>", self._on_ollama_model_selected)

        # Neues Modell herunterladen
        add_row = tk.Frame(ollama_section, bg=BG_CARD)
        add_row.pack(fill="x", padx=12, pady=(0, 10))

        self._new_model_var = tk.StringVar()
        self._new_model_entry = tk.Entry(
            add_row, textvariable=self._new_model_var,
            font=(FONT, 9), bg=BG_ITEM, fg=TEXT,
            insertbackground=TEXT, relief="flat",
            highlightthickness=1, highlightcolor=ACCENT,
            highlightbackground=BORDER,
        )
        self._new_model_entry.insert(0, "z.B. llama3.2:3b")
        self._new_model_entry.config(fg=TEXT_DIM)
        self._new_model_entry.bind("<FocusIn>",  self._entry_focus_in)
        self._new_model_entry.bind("<FocusOut>", self._entry_focus_out)
        self._new_model_entry.bind("<Return>",   lambda _: self._download_new_model())
        self._new_model_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))

        self._dl_btn = tk.Button(
            add_row, text="↓ Laden", font=(FONT, 9),
            bg=ACCENT, fg="white", activebackground="#5551e0",
            activeforeground="white", relief="flat", bd=0,
            cursor="hand2", padx=10, pady=5,
            command=self._download_new_model,
        )
        self._dl_btn.pack(side="right")

        # ── Download-Fortschritt ───────────────────────────────────────────
        self._dl_frame = tk.Frame(parent, bg=BG_CARD)

        dl_top = tk.Frame(self._dl_frame, bg=BG_CARD)
        dl_top.pack(fill="x", padx=12, pady=(8, 4))
        self._dl_label = tk.Label(dl_top, text="", font=(FONT, 9, "bold"),
                                   bg=BG_CARD, fg=YELLOW)
        self._dl_label.pack(side="left")
        self._dl_size_label = tk.Label(dl_top, text="", font=(FONT, 8),
                                        bg=BG_CARD, fg=TEXT_DIM)
        self._dl_size_label.pack(side="right")

        style.configure("dl.Horizontal.TProgressbar",
                         troughcolor=BG_ITEM, background=ACCENT,
                         darkcolor=ACCENT, lightcolor=ACCENT,
                         bordercolor=BG_CARD, thickness=6)
        self._progress = ttk.Progressbar(
            self._dl_frame, style="dl.Horizontal.TProgressbar",
            mode="determinate", maximum=100, value=0,
        )
        self._progress.pack(fill="x", padx=12, pady=(0, 10))

        # Live-Transkript
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(8, 0))
        trans_frame = tk.Frame(parent, bg=BG_CARD)
        trans_frame.pack(fill="x", padx=20, pady=(8, 0))
        tk.Label(trans_frame, text="Zuhören", font=(FONT, 9, "bold"),
                 bg=BG_CARD, fg=ACCENT, pady=8, padx=12).pack(anchor="w")
        self._transcript = tk.Label(
            trans_frame, text="Drücke Start zum Zuhören...",
            font=(FONT, 10), bg=BG_CARD, fg=TEXT_DIM,
            wraplength=460, justify="left", anchor="w", pady=6, padx=12,
        )
        self._transcript.pack(fill="x")
        tk.Frame(trans_frame, bg=BG, height=8).pack()

        # Start/Stop Button
        self._btn = tk.Button(
            parent, text="  Start  ", font=(FONT, 11, "bold"),
            bg=ACCENT, fg="white", activebackground="#5551e0",
            activeforeground="white", relief="flat", bd=0,
            cursor="hand2", padx=20, pady=8,
            command=self._toggle_listening,
        )
        self._btn.pack(pady=10)

        # Erinnerungen-Liste
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", padx=20)
        header2 = tk.Frame(parent, bg=BG, pady=10)
        header2.pack(fill="x", padx=20)
        tk.Label(header2, text="Erkannte Erinnerungen",
                 font=(FONT, 11, "bold"), bg=BG, fg=TEXT).pack(side="left")
        self._count_label = tk.Label(header2, text="0",
                                      font=(FONT, 9), bg=ACCENT,
                                      fg="white", padx=7, pady=1)
        self._count_label.pack(side="left", padx=8)

        container = tk.Frame(parent, bg=BG)
        container.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        scrollbar = tk.Scrollbar(container, bg=BG, troughcolor=BG_CARD,
                                  relief="flat", bd=0, width=6)
        scrollbar.pack(side="right", fill="y")
        self._canvas = tk.Canvas(container, bg=BG, bd=0,
                                  highlightthickness=0,
                                  yscrollcommand=scrollbar.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self._canvas.yview)
        self._list_frame = tk.Frame(self._canvas, bg=BG)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._list_frame, anchor="nw"
        )
        self._list_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._reminder_items = []       # list of card frames
        self._reminder_cards = {}       # {reminder_id: card}

    def _build_tab_calendar(self, parent):
        # Scrollable wrapper
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True)
        sb = tk.Scrollbar(wrap, bg=BG, troughcolor=BG_CARD, relief="flat", bd=0, width=6)
        sb.pack(side="right", fill="y")
        cv = tk.Canvas(wrap, bg=BG, bd=0, highlightthickness=0, yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.config(command=cv.yview)
        inner = tk.Frame(cv, bg=BG)
        cw = cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfig(cw, width=e.width))
        cv.bind_all("<MouseWheel>",
                    lambda e: cv.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        tk.Label(inner, text="Kalender-Integrationen", font=(FONT, 11, "bold"),
                 bg=BG, fg=TEXT, pady=14, padx=20, anchor="w").pack(fill="x")

        self._build_cal_google(inner)
        for pid, pinfo in caldav_cal.PROVIDERS.items():
            self._build_cal_caldav(inner, pid, pinfo)

    def _build_cal_google(self, parent):
        card = tk.Frame(parent, bg=BG_CARD)
        card.pack(fill="x", padx=20, pady=(0, 8))

        hrow = tk.Frame(card, bg=BG_CARD, padx=12, pady=10)
        hrow.pack(fill="x")

        left = tk.Frame(hrow, bg=BG_CARD)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text="Google Kalender", font=(FONT, 10, "bold"),
                 bg=BG_CARD, fg=TEXT).pack(anchor="w")
        self._gcal_status = tk.Label(left, text="", font=(FONT, 8),
                                     bg=BG_CARD, fg=TEXT_DIM)
        self._gcal_status.pack(anchor="w")

        self._gcal_btn = tk.Button(
            hrow, text="", font=(FONT, 8),
            bg=ACCENT, fg="white", activebackground="#5551e0",
            activeforeground="white", relief="flat", bd=0,
            cursor="hand2", padx=10, pady=4,
        )
        self._gcal_btn.pack(side="right")

        # ── Einrichtungs-Panel (nur wenn nicht konfiguriert) ───────────────
        self._gcal_setup = tk.Frame(card, bg=BG_CARD, padx=12)

        steps = (
            "So richtest du Google Kalender ein:\n"
            "1.  Klicke 'Google Cloud Console öffnen'\n"
            "2.  Erstelle ein neues Projekt (oben links)\n"
            "3.  APIs & Dienste  →  Bibliothek  →  'Google Calendar API' aktivieren\n"
            "4.  APIs & Dienste  →  Anmeldedaten  →  'Anmeldedaten erstellen'\n"
            "5.  Wähle 'OAuth 2.0-Client-ID'  →  Typ: Desktop-App  →  Erstellen\n"
            "6.  Klicke das Download-Symbol (↓) neben der erstellten ID\n"
            "7.  Wähle die heruntergeladene JSON-Datei mit dem Button unten aus"
        )
        tk.Label(self._gcal_setup, text=steps, font=(FONT, 8), bg=BG_CARD,
                 fg=TEXT_MID, justify="left", anchor="w",
                 wraplength=440).pack(fill="x", pady=(0, 10))

        link_row = tk.Frame(self._gcal_setup, bg=BG_CARD)
        link_row.pack(fill="x", pady=(0, 12))

        tk.Button(
            link_row, text="Google Cloud Console öffnen", font=(FONT, 8),
            bg=BG_ITEM, fg=TEXT, activebackground=ACCENT, activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=10, pady=5,
            command=lambda: __import__("webbrowser").open(
                "https://console.cloud.google.com/apis/credentials"),
        ).pack(side="left")

        tk.Button(
            link_row, text="credentials.json auswählen", font=(FONT, 8),
            bg=ACCENT, fg="white", activebackground="#5551e0", activeforeground="white",
            relief="flat", bd=0, cursor="hand2", padx=10, pady=5,
            command=self._pick_gcal_credentials,
        ).pack(side="right")

        self._update_gcal_ui()

    def _pick_gcal_credentials(self):
        import tkinter.filedialog as fd
        import shutil
        path = fd.askopenfilename(
            title="credentials.json auswählen",
            filetypes=[("JSON-Datei", "*.json"), ("Alle Dateien", "*.*")],
        )
        if path:
            dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
            shutil.copy(path, dest)
            self._update_gcal_ui()

    def _build_cal_caldav(self, parent, pid: str, pinfo: dict):
        cfg = cal_providers.get_provider_config(pid)
        is_enabled = cfg.get("enabled", False)

        card = tk.Frame(parent, bg=BG_CARD)
        card.pack(fill="x", padx=20, pady=(0, 8))

        hrow = tk.Frame(card, bg=BG_CARD, padx=12, pady=10)
        hrow.pack(fill="x")

        left = tk.Frame(hrow, bg=BG_CARD)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=pinfo["label"], font=(FONT, 10, "bold"),
                 bg=BG_CARD, fg=TEXT).pack(anchor="w")
        status_lbl = tk.Label(left,
                               text="● Aktiviert" if is_enabled else "Nicht verbunden",
                               font=(FONT, 8), bg=BG_CARD,
                               fg=GREEN if is_enabled else TEXT_DIM)
        status_lbl.pack(anchor="w")

        # Form frame
        form = tk.Frame(card, bg=BG_CARD, padx=12)

        def _make_field(lbl_text, var, show=""):
            row = tk.Frame(form, bg=BG_CARD)
            row.pack(fill="x", pady=(0, 4))
            tk.Label(row, text=lbl_text, font=(FONT, 8), bg=BG_CARD, fg=TEXT_DIM,
                     width=12, anchor="w").pack(side="left")
            tk.Entry(row, textvariable=var, font=(FONT, 9), bg=BG_ITEM, fg=TEXT,
                     insertbackground=TEXT, relief="flat", highlightthickness=1,
                     highlightcolor=ACCENT, highlightbackground=BORDER,
                     show=show).pack(side="left", fill="x", expand=True, ipady=4)

        url_var  = tk.StringVar(value=cfg.get("url", ""))
        user_var = tk.StringVar(value=cfg.get("username", ""))
        pw_var   = tk.StringVar(value=cfg.get("password", ""))

        if pinfo.get("custom_url"):
            _make_field("Server-URL:", url_var)
        _make_field(pinfo.get("user_hint", "Benutzer") + ":", user_var)
        _make_field(pinfo.get("pass_hint", "Passwort") + ":", pw_var, show="*")

        if pinfo.get("help"):
            tk.Label(form, text=pinfo["help"], font=(FONT, 8), bg=BG_CARD,
                     fg=TEXT_MID, wraplength=400, justify="left",
                     anchor="w").pack(fill="x", pady=(0, 8))
        if pinfo.get("help_url"):
            tk.Button(form, text=f"Anleitung öffnen: {pinfo['help_url']}",
                      font=(FONT, 7), bg=BG_ITEM, fg=TEXT_DIM,
                      activebackground=ACCENT, activeforeground="white",
                      relief="flat", bd=0, cursor="hand2", padx=8, pady=3,
                      command=lambda u=pinfo["help_url"]: __import__("webbrowser").open(u),
                      ).pack(anchor="w", pady=(0, 8))

        btn_row = tk.Frame(form, bg=BG_CARD)
        btn_row.pack(fill="x", pady=(0, 10))
        save_btn = tk.Button(btn_row, text="Verbinden", font=(FONT, 8),
                             bg=ACCENT, fg="white", activebackground="#5551e0",
                             activeforeground="white", relief="flat", bd=0,
                             cursor="hand2", padx=10, pady=4)
        save_btn.pack(side="right")

        def toggle_form():
            if form.winfo_ismapped():
                form.pack_forget()
            else:
                form.pack(fill="x")

        edit_btn = tk.Button(hrow,
                             text="Bearbeiten" if is_enabled else "Einrichten",
                             font=(FONT, 8), bg=BG_ITEM, fg=TEXT,
                             activebackground=ACCENT, activeforeground="white",
                             relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
                             command=toggle_form)
        edit_btn.pack(side="right")

        def _disconnect():
            cal_providers.save_provider_config(pid, False)
            status_lbl.config(text="Nicht verbunden", fg=TEXT_DIM)
            edit_btn.config(text="Einrichten")
            form.pack(fill="x")
            discon_btn.pack_forget()

        discon_btn = tk.Button(hrow, text="Trennen", font=(FONT, 8),
                               bg=BG_ITEM, fg=TEXT_DIM,
                               activebackground=ACCENT2, activeforeground="white",
                               relief="flat", bd=0, cursor="hand2", padx=10, pady=4,
                               command=_disconnect)
        if is_enabled:
            discon_btn.pack(side="right", padx=(0, 4))

        def _test_connect():
            save_btn.config(state="disabled", text="Prüfe...")
            url  = url_var.get() if pinfo.get("custom_url") else pinfo["url"]
            user = user_var.get().strip()
            pw   = pw_var.get().strip()
            if not user or not pw or (pinfo.get("custom_url") and not url.strip()):
                status_lbl.config(text="Bitte alle Felder ausfüllen", fg=ACCENT2)
                save_btn.config(state="normal", text="Verbinden")
                return

            def do_test():
                ok = caldav_cal.test_connection(pid, url, user, pw)
                if ok:
                    cal_providers.save_provider_config(pid, True, user, pw, url)
                    def _on_ok():
                        status_lbl.config(text="● Aktiviert", fg=GREEN)
                        edit_btn.config(text="Bearbeiten")
                        save_btn.config(state="normal", text="Speichern")
                        form.pack_forget()
                        discon_btn.pack(side="right", padx=(0, 4))
                    self.after(0, _on_ok)
                else:
                    def _on_err():
                        status_lbl.config(text="Verbindung fehlgeschlagen", fg=ACCENT2)
                        save_btn.config(state="normal", text="Verbinden")
                    self.after(0, _on_err)

            threading.Thread(target=do_test, daemon=True).start()

        save_btn.config(command=_test_connect)

        if not is_enabled:
            form.pack(fill="x")

    # ── Ollama Modelle laden & auswählen ──────────────────────────────────

    def _load_ollama_models(self):
        models = fetch_ollama_models()
        self._queue.put(("ollama_models", models))

    def _entry_focus_in(self, _evt):
        if self._new_model_var.get() == "z.B. llama3.2:3b":
            self._new_model_entry.delete(0, "end")
            self._new_model_entry.config(fg=TEXT)

    def _entry_focus_out(self, _evt):
        if not self._new_model_var.get().strip():
            self._new_model_entry.insert(0, "z.B. llama3.2:3b")
            self._new_model_entry.config(fg=TEXT_DIM)

    def _download_new_model(self):
        model = self._new_model_var.get().strip()
        if not model or model == "z.B. llama3.2:3b":
            return
        self._new_model_entry.delete(0, "end")
        self._new_model_entry.config(fg=TEXT_DIM)
        self._new_model_entry.insert(0, "z.B. llama3.2:3b")
        self._dl_btn.config(state="disabled", text="Lädt...")
        threading.Thread(
            target=self._pull_ollama_model,
            args=(model,),
            daemon=True,
        ).start()

    def _on_ollama_model_selected(self, _evt=None):
        model = self._selected_ollama.get()
        if not model or model.startswith("("):
            return
        self._settings["ollama_model"] = model
        save_settings(self._settings)
        if not is_model_installed(model):
            threading.Thread(
                target=self._pull_ollama_model, args=(model,), daemon=True
            ).start()

    def _pull_ollama_model(self, model: str):
        self._queue.put(("ollama_pull_start", model))

        def on_progress(status, pct, completed, total):
            mb_done  = completed / (1024 * 1024)
            mb_total = total     / (1024 * 1024)
            label = status if pct == 0 else f"{mb_done:.0f} MB / {mb_total:.0f} MB"
            self._queue.put(("ollama_pull_progress", pct, label))

        try:
            pull_model(model, progress_callback=on_progress)
            self._queue.put(("ollama_pull_done", model))
            threading.Thread(target=self._load_ollama_models, daemon=True).start()
        except Exception as e:
            self._queue.put(("error", f"Pull fehlgeschlagen: {e}"))
            self._queue.put(("ollama_pull_done", model))
        finally:
            self._queue.put(("dl_btn_reset",))

    # ── Google Calendar ───────────────────────────────────────────────────

    def _update_gcal_ui(self):
        if not gcal.is_configured():
            self._gcal_status.config(text="Nicht eingerichtet", fg=ACCENT2)
            self._gcal_btn.pack_forget()
            self._gcal_setup.pack(fill="x")
        elif gcal.is_connected():
            self._gcal_status.config(text="● Verbunden", fg=GREEN)
            self._gcal_btn.config(text="Trennen", command=self._toggle_gcal)
            self._gcal_btn.pack(side="right")
            self._gcal_setup.pack_forget()
        else:
            self._gcal_status.config(text="Eingerichtet – noch nicht verbunden", fg=TEXT_DIM)
            self._gcal_btn.config(text="Verbinden", command=self._toggle_gcal)
            self._gcal_btn.pack(side="right")
            self._gcal_setup.pack_forget()

    def _toggle_gcal(self):
        if gcal.is_connected():
            gcal.disconnect()
            self._update_gcal_ui()
        else:
            threading.Thread(target=self._gcal_connect, daemon=True).start()

    def _gcal_connect(self):
        try:
            gcal.get_service()
            self._queue.put(("gcal_connected",))
        except Exception as e:
            self._queue.put(("gcal_error", str(e)))

    # ── Whisper Modell-Karten ──────────────────────────────────────────────

    def _build_model_card(self, name: str, info: dict, row: int, col: int):
        selected = name == self._selected_whisper
        bg = ACCENT if selected else BG_ITEM

        card = tk.Frame(self._model_grid, bg=bg, padx=8, pady=6, cursor="hand2")
        card.grid(row=row, column=col, padx=3, pady=3, sticky="nsew")
        self._model_grid.columnconfigure(col, weight=1)

        lbl_name  = tk.Label(card, text=name,         font=(FONT, 9, "bold"),
                              bg=bg, fg="white" if selected else TEXT)
        lbl_size  = tk.Label(card, text=info["size"],  font=(FONT, 7),
                              bg=bg, fg="#ccc" if selected else TEXT_DIM)
        lbl_speed = tk.Label(card, text=info["speed"], font=(FONT, 7),
                              bg=bg, fg="#ccc" if selected else TEXT_DIM)
        lbl_badge = tk.Label(card, text="...",         font=(FONT, 7),
                              bg=bg, fg=TEXT_DIM)

        for lbl in (lbl_name, lbl_size, lbl_speed, lbl_badge):
            lbl.pack(anchor="w")

        self._model_cards[name] = {
            "frame": card,
            "name": lbl_name, "size": lbl_size,
            "speed": lbl_speed, "badge": lbl_badge,
        }

        def on_click(_evt, n=name):
            self._select_whisper(n)

        for w in (card, lbl_name, lbl_size, lbl_speed, lbl_badge):
            w.bind("<Button-1>", on_click)

    def _select_whisper(self, name: str):
        if name == self._selected_whisper:
            return
        old = self._model_cards.get(self._selected_whisper)
        if old:
            old["frame"].config(bg=BG_ITEM)
            old["name"].config(bg=BG_ITEM, fg=TEXT)
            old["size"].config(bg=BG_ITEM, fg=TEXT_DIM)
            old["speed"].config(bg=BG_ITEM, fg=TEXT_DIM)
            old["badge"].config(bg=BG_ITEM)
        self._selected_whisper = name
        new = self._model_cards.get(name)
        if new:
            new["frame"].config(bg=ACCENT)
            new["name"].config(bg=ACCENT, fg="white")
            new["size"].config(bg=ACCENT, fg="#ccc")
            new["speed"].config(bg=ACCENT, fg="#ccc")
            new["badge"].config(bg=ACCENT)
        self._settings["whisper_model"] = name
        save_settings(self._settings)

    def _refresh_model_badges(self):
        for name, card in self._model_cards.items():
            cached = is_model_cached(name)
            card["badge"].config(
                text="✓ Bereit" if cached else "↓ Nicht geladen",
                fg=GREEN if cached else YELLOW,
            )

    # ── Download-Fortschritt ───────────────────────────────────────────────

    def _show_download(self, model_name: str):
        expected_mb = WHISPER_MODELS[model_name]["mb"]
        self._dl_label.config(text=f"Lade '{model_name}' herunter...")
        self._dl_size_label.config(text=f"0 MB / {expected_mb} MB")
        self._progress.config(value=0)
        self._dl_frame.pack(fill="x", padx=20, pady=(6, 0), before=self._btn)
        self._dl_stop.clear()
        threading.Thread(
            target=self._monitor_download,
            args=(model_name, expected_mb),
            daemon=True,
        ).start()

    def _monitor_download(self, model_name: str, expected_mb: float):
        while not self._dl_stop.is_set():
            current_mb = get_cache_size_mb(model_name)
            pct = min(int(current_mb / expected_mb * 100), 99) if expected_mb > 0 else 0
            self._queue.put(("download_progress", pct,
                             f"{current_mb:.0f} MB / {expected_mb} MB"))
            time.sleep(0.5)

    def _hide_download(self):
        self._dl_stop.set()
        self._progress.config(value=100)
        self.after(400, self._dl_frame.pack_forget)
        self._refresh_model_badges()

    # ── Erinnerungen ──────────────────────────────────────────────────────

    def _load_existing_reminders(self):
        for r in load_reminders():
            self._add_reminder_card(r)

    def _add_reminder_card(self, reminder: dict):
        card = tk.Frame(self._list_frame, bg=BG_ITEM, pady=10, padx=12)
        card.pack(fill="x", pady=4)

        top = tk.Frame(card, bg=BG_ITEM)
        top.pack(fill="x")
        tk.Label(top, text="●", font=(FONT, 8), bg=BG_ITEM, fg=ACCENT).pack(
            side="left", padx=(0, 6))
        tk.Label(top, text=reminder["task"], font=(FONT, 10, "bold"),
                 bg=BG_ITEM, fg=TEXT, anchor="w", wraplength=300,
                 justify="left").pack(side="left", fill="x", expand=True)

        # Lösch-Button
        def on_delete(rid=reminder["id"], c=card):
            self._remove_reminder_card(rid)

        tk.Button(top, text="✕", font=(FONT, 8), bg=BG_ITEM, fg=TEXT_DIM,
                  activebackground=ACCENT2, activeforeground="white",
                  relief="flat", bd=0, cursor="hand2", padx=4,
                  command=on_delete).pack(side="right", padx=(4, 0))

        if reminder.get("time_expression"):
            tk.Label(top, text=reminder["time_expression"],
                     font=(FONT, 8), bg=ACCENT2, fg="white",
                     padx=6, pady=1).pack(side="right")

        if reminder.get("original") and reminder["original"] != reminder["task"]:
            tk.Label(card, text=f'"{reminder["original"]}"',
                     font=(FONT, 8, "italic"), bg=BG_ITEM, fg=TEXT_DIM,
                     anchor="w", wraplength=440, justify="left").pack(
                fill="x", pady=(4, 0))

        try:
            dt = datetime.fromisoformat(reminder["created_at"])
            time_str = dt.strftime("%d.%m.%Y %H:%M")
        except Exception:
            time_str = ""
        tk.Label(card, text=time_str, font=(FONT, 7), bg=BG_ITEM,
                 fg=TEXT_DIM, anchor="e").pack(fill="x", pady=(2, 0))

        self._reminder_items.append(card)
        self._reminder_cards[reminder["id"]] = card
        self._count_label.config(text=str(len(self._reminder_items)))
        self.after(100, lambda: self._canvas.yview_moveto(1.0))

    def _remove_reminder_card(self, reminder_id: str):
        from storage import load_reminders
        for r in load_reminders():
            if r["id"] == reminder_id:
                ids = r.get("cal_event_ids") or {}
                # backward compat: old reminders stored gcal_event_id as string
                if not ids and r.get("gcal_event_id"):
                    ids = {"google": r["gcal_event_id"]}
                if ids:
                    threading.Thread(
                        target=cal_providers.delete_from_all, args=(ids,), daemon=True
                    ).start()
                break
        delete_reminder(reminder_id)
        card = self._reminder_cards.pop(reminder_id, None)
        if card:
            if card in self._reminder_items:
                self._reminder_items.remove(card)
            card.destroy()
            self._count_label.config(text=str(len(self._reminder_items)))

    # ── Mikrofon Start/Stop ───────────────────────────────────────────────

    def _toggle_listening(self):
        if not self._listening:
            self._start_listening()
        else:
            self._stop_listening()

    def _start_listening(self):
        self._listening = True
        self._btn.config(text="  Stop  ", bg=ACCENT2, activebackground="#e05570")
        self._set_status("Starte...", YELLOW)
        self._animate_dot()
        threading.Thread(target=self._listener_worker, daemon=True).start()

    def _stop_listening(self):
        self._listening = False
        self._btn.config(text="  Start  ", bg=ACCENT, activebackground="#5551e0")
        self._set_status("Gestoppt", TEXT_DIM)
        self._dot.config(fg=TEXT_DIM)
        self._transcript.config(text="Drücke Start zum Zuhören...", fg=TEXT_DIM)

    def _set_status(self, text, color):
        self._status_label.config(text=text, fg=color)

    def _animate_dot(self):
        if not self._listening:
            return
        colors = [GREEN, "#2d7a4f", GREEN, TEXT_DIM]
        self._dot.config(fg=colors[self._dot_state % len(colors)])
        self._dot_state += 1
        self.after(600, self._animate_dot)

    # ── Listener Worker ───────────────────────────────────────────────────

    def _listener_worker(self):
        try:
            import numpy as np
            import sounddevice as sd
            from faster_whisper import WhisperModel
            from config import SAMPLE_RATE, WHISPER_LANGUAGE, VAD_MODE

            whisper_model = self._selected_whisper
            ollama_model  = self._selected_ollama.get()

            # ── Ollama-Modell prüfen & ggf. herunterladen ─────────────────
            if not is_model_installed(ollama_model):
                self._queue.put(("ollama_pull_start", ollama_model))
                try:
                    def _on_prog(status, pct, completed, total):
                        mb_done  = completed / (1024 * 1024)
                        mb_total = total     / (1024 * 1024)
                        label = status if pct == 0 else f"{mb_done:.0f} MB / {mb_total:.0f} MB"
                        self._queue.put(("ollama_pull_progress", pct, label))
                    pull_model(ollama_model, progress_callback=_on_prog)
                    self._queue.put(("ollama_pull_done", ollama_model))
                except Exception as e:
                    self._queue.put(("error", f"Ollama Pull fehlgeschlagen: {e}"))
                    return


            # ── Whisper-Modell laden ───────────────────────────────────────
            cached = is_model_cached(whisper_model)
            if not cached:
                self._queue.put(("download_start", whisper_model))
            else:
                self._queue.put(("status", f"Lade {whisper_model}...", YELLOW))

            whisper = WhisperModel(whisper_model, device="cpu", compute_type="int8")

            if not cached:
                self._queue.put(("download_done", None))

            self._queue.put(("status", "Zuhören...", GREEN))

            try:
                import webrtcvad
                vad = webrtcvad.Vad(VAD_MODE)
                use_vad = True
            except ImportError:
                vad = None
                use_vad = False

            frame_ms     = 30
            frame_samples = int(SAMPLE_RATE * frame_ms / 1000)
            silence_frames = int(1500 / frame_ms)
            ring    = collections.deque(maxlen=silence_frames)
            voiced  = []
            triggered = False

            # Kontext-Fenster: letzte N transkribierte Segmente
            context_buf = collections.deque(maxlen=CONTEXT_WINDOW)
            # Bereits gespeicherte Erinnerungen (verhindert Dopplungen)
            seen_reminders: set[str] = set()

            def is_speech(frame_bytes):
                if use_vad:
                    try:
                        return vad.is_speech(frame_bytes, SAMPLE_RATE)
                    except Exception:
                        pass
                audio = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
                return np.sqrt(np.mean(audio**2)) > 500

            def process(frames):
                audio = np.concatenate(frames).astype(np.float32) / 32768.0
                if len(audio) < SAMPLE_RATE * 0.3:
                    return
                segs, _ = whisper.transcribe(
                    audio, language=WHISPER_LANGUAGE, beam_size=3, vad_filter=True
                )
                text = " ".join(s.text for s in segs).strip()
                if not text:
                    return

                context_buf.append(text)
                self._queue.put(("transcript", text))

                # Analysiere immer den vollen Kontext der letzten N Segmente
                full_context = " ".join(context_buf)
                result = detect_reminder(full_context, model=ollama_model)

                if result:
                    action = result.get("action")
                    if action == "add":
                        task_key = result["task"].lower().strip()
                        if task_key not in seen_reminders:
                            seen_reminders.add(task_key)
                            # Calendar events erstellen
                            start_dt = None
                            if result.get("time_expression"):
                                start_dt = gcal.parse_time_expression(
                                    result["time_expression"], model=ollama_model)
                            cal_ids = cal_providers.add_to_all(
                                result["task"], start_dt, model=ollama_model)
                            reminder = add_reminder(
                                result["task"],
                                result.get("time_expression"),
                                result.get("original", text),
                                cal_event_ids=cal_ids,
                            )
                            self._queue.put(("reminder", reminder))
                    elif action == "delete":
                        target = result.get("target", "")
                        found = find_reminder_by_keyword(target)
                        if found:
                            ids = found.get("cal_event_ids") or {}
                            if not ids and found.get("gcal_event_id"):
                                ids = {"google": found["gcal_event_id"]}
                            if ids:
                                cal_providers.delete_from_all(ids)
                            self._queue.put(("delete_reminder", found["id"], found["task"]))

            def audio_cb(indata, frames, time_info, status):
                nonlocal triggered, voiced
                if not self._listening:
                    raise sd.CallbackStop()
                pcm = (indata[:, 0] * 32767).astype(np.int16)
                for i in range(0, len(pcm) - frame_samples + 1, frame_samples):
                    frame = pcm[i:i + frame_samples]
                    speech = is_speech(frame.tobytes())
                    if not triggered:
                        ring.append((frame, speech))
                        if sum(1 for _, s in ring if s) / max(len(ring), 1) > 0.6:
                            triggered = True
                            voiced = [f for f, _ in ring]
                            ring.clear()
                    else:
                        voiced.append(frame)
                        ring.append((frame, speech))
                        if sum(1 for _, s in ring if s) / max(len(ring), 1) < 0.2:
                            frames_copy = voiced[:]
                            threading.Thread(
                                target=process, args=(frames_copy,), daemon=True
                            ).start()
                            ring.clear()
                            voiced = []
                            triggered = False

            with sd.InputStream(
                samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                blocksize=frame_samples, callback=audio_cb,
            ):
                while self._listening:
                    sd.sleep(100)

        except Exception as e:
            self._queue.put(("error", str(e)))

    # ── Queue-Verarbeitung ────────────────────────────────────────────────

    def _process_queue(self):
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "transcript":
                    self._transcript.config(text=msg[1], fg=TEXT_MID)
                elif kind == "reminder":
                    self._add_reminder_card(msg[1])
                    self._transcript.config(
                        text=f"Erinnerung erkannt: {msg[1]['task']}", fg=GREEN)
                elif kind == "delete_reminder":
                    self._remove_reminder_card(msg[1])
                    self._transcript.config(
                        text=f"Erinnerung gelöscht: {msg[2]}", fg=ACCENT2)
                elif kind == "status":
                    self._set_status(msg[1], msg[2])
                elif kind == "ollama_models":
                    models = msg[1]
                    if models:
                        self._ollama_combo["values"] = models
                        saved = self._settings.get("ollama_model", "")
                        self._selected_ollama.set(saved if saved in models else models[0])
                    else:
                        self._ollama_combo["values"] = ["(Ollama nicht erreichbar)"]
                        self._selected_ollama.set("(Ollama nicht erreichbar)")
                elif kind == "ollama_pull_start":
                    self._dl_label.config(text=f"Lade Ollama-Modell '{msg[1]}'...")
                    self._dl_size_label.config(text="")
                    self._progress.config(value=0)
                    self._dl_frame.pack(fill="x", padx=20, pady=(6, 0), before=self._btn)
                    self._set_status(f"Lade {msg[1]}...", YELLOW)
                elif kind == "ollama_pull_progress":
                    self._progress.config(value=msg[1])
                    self._dl_size_label.config(text=msg[2])
                elif kind == "ollama_pull_done":
                    self._dl_frame.pack_forget()
                    self._set_status(f"{msg[1]} bereit", GREEN)
                elif kind == "dl_btn_reset":
                    self._dl_btn.config(state="normal", text="↓ Laden")
                elif kind == "gcal_connected":
                    self._update_gcal_ui()
                elif kind == "gcal_error":
                    self._gcal_status.config(text=f"Fehler: {msg[1]}", fg=ACCENT2)
                    self._gcal_btn.config(text="Verbinden")
                elif kind == "download_start":
                    self._show_download(msg[1])
                    self._set_status(f"Lade {msg[1]}...", YELLOW)
                elif kind == "download_progress":
                    self._progress.config(value=msg[1])
                    self._dl_size_label.config(text=msg[2])
                elif kind == "download_done":
                    self._hide_download()
                    self._set_status("Zuhören...", GREEN)
                elif kind == "error":
                    self._set_status(f"Fehler: {msg[1]}", ACCENT2)
                    self._listening = False
                    self._btn.config(text="  Start  ", bg=ACCENT)
                    self._hide_download()
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    def _on_frame_configure(self, _):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


if __name__ == "__main__":
    ReminderApp().mainloop()
