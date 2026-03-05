import tkinter as tk
import tkinter.ttk as ttk
import threading
import queue
import time
from pathlib import Path
from datetime import datetime
from storage import load_reminders, add_reminder
from detector import detect_reminder

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
        self.geometry("540x800")
        self.minsize(440, 600)
        self.configure(bg=BG)
        self.resizable(True, True)

        self._queue = queue.Queue()
        self._listening = False
        self._dot_state = 0
        self._selected_model = "small"
        self._model_cards = {}
        self._dl_stop = threading.Event()

        self._build_ui()
        self._load_existing_reminders()
        self._refresh_model_badges()
        self._process_queue()

    # ── UI aufbauen ────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG, pady=16)
        header.pack(fill="x", padx=20)
        tk.Label(header, text="Erinnerungs", font=(FONT, 22, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(header, text="KI", font=(FONT, 22, "bold"),
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

        # ── Modellauswahl ──────────────────────────────────────────────────
        model_section = tk.Frame(self, bg=BG_CARD)
        model_section.pack(fill="x", padx=20, pady=(12, 0))

        title_row = tk.Frame(model_section, bg=BG_CARD)
        title_row.pack(fill="x", padx=12, pady=(10, 6))
        tk.Label(title_row, text="Whisper Modell", font=(FONT, 9, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(side="left")
        tk.Label(title_row, text="– Spracherkennung",
                 font=(FONT, 8), bg=BG_CARD, fg=TEXT_DIM).pack(side="left", padx=6)

        self._model_grid = tk.Frame(model_section, bg=BG_CARD)
        self._model_grid.pack(fill="x", padx=12, pady=(0, 10))

        for i, (name, info) in enumerate(WHISPER_MODELS.items()):
            self._build_model_card(name, info, row=i // 3, col=i % 3)

        # ── Download-Fortschritt ───────────────────────────────────────────
        self._dl_frame = tk.Frame(self, bg=BG_CARD)

        dl_top = tk.Frame(self._dl_frame, bg=BG_CARD)
        dl_top.pack(fill="x", padx=12, pady=(8, 4))
        self._dl_label = tk.Label(dl_top, text="", font=(FONT, 9, "bold"),
                                   bg=BG_CARD, fg=YELLOW)
        self._dl_label.pack(side="left")
        self._dl_size_label = tk.Label(dl_top, text="", font=(FONT, 8),
                                        bg=BG_CARD, fg=TEXT_DIM)
        self._dl_size_label.pack(side="right")

        style = ttk.Style()
        style.theme_use("default")
        style.configure("dl.Horizontal.TProgressbar",
                         troughcolor=BG_ITEM, background=ACCENT,
                         darkcolor=ACCENT, lightcolor=ACCENT,
                         bordercolor=BG_CARD, thickness=6)

        self._progress = ttk.Progressbar(
            self._dl_frame, style="dl.Horizontal.TProgressbar",
            mode="determinate", maximum=100, value=0,
        )
        self._progress.pack(fill="x", padx=12, pady=(0, 10))

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=20, pady=(10, 0))

        # Live-Transkript
        trans_frame = tk.Frame(self, bg=BG_CARD)
        trans_frame.pack(fill="x", padx=20, pady=(10, 0))
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
            self, text="  Start  ", font=(FONT, 11, "bold"),
            bg=ACCENT, fg="white", activebackground="#5551e0",
            activeforeground="white", relief="flat", bd=0,
            cursor="hand2", padx=20, pady=8,
            command=self._toggle_listening,
        )
        self._btn.pack(pady=12)

        # Erinnerungen-Liste
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", padx=20)
        header2 = tk.Frame(self, bg=BG, pady=10)
        header2.pack(fill="x", padx=20)
        tk.Label(header2, text="Erkannte Erinnerungen",
                 font=(FONT, 11, "bold"), bg=BG, fg=TEXT).pack(side="left")
        self._count_label = tk.Label(header2, text="0",
                                      font=(FONT, 9), bg=ACCENT,
                                      fg="white", padx=7, pady=1)
        self._count_label.pack(side="left", padx=8)

        container = tk.Frame(self, bg=BG)
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
        self._reminder_items = []

    # ── Modell-Karten ─────────────────────────────────────────────────────

    def _build_model_card(self, name: str, info: dict, row: int, col: int):
        selected = name == self._selected_model
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
            self._select_model(n)

        for w in (card, lbl_name, lbl_size, lbl_speed, lbl_badge):
            w.bind("<Button-1>", on_click)

    def _select_model(self, name: str):
        if name == self._selected_model:
            return

        # Alte Karte zurücksetzen
        old = self._model_cards.get(self._selected_model)
        if old:
            old["frame"].config(bg=BG_ITEM)
            old["name"].config(bg=BG_ITEM, fg=TEXT)
            old["size"].config(bg=BG_ITEM, fg=TEXT_DIM)
            old["speed"].config(bg=BG_ITEM, fg=TEXT_DIM)
            old["badge"].config(bg=BG_ITEM)

        # Neue Karte hervorheben
        self._selected_model = name
        new = self._model_cards.get(name)
        if new:
            new["frame"].config(bg=ACCENT)
            new["name"].config(bg=ACCENT, fg="white")
            new["size"].config(bg=ACCENT, fg="#ccc")
            new["speed"].config(bg=ACCENT, fg="#ccc")
            new["badge"].config(bg=ACCENT)

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

        # Monitoring-Thread: liest Cache-Ordner-Größe alle 500ms
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
                 bg=BG_ITEM, fg=TEXT, anchor="w", wraplength=340,
                 justify="left").pack(side="left", fill="x", expand=True)

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
        self._count_label.config(text=str(len(self._reminder_items)))
        self.after(100, lambda: self._canvas.yview_moveto(1.0))

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
            import collections
            from faster_whisper import WhisperModel
            from config import SAMPLE_RATE, WHISPER_LANGUAGE, VAD_MODE

            model_name = self._selected_model
            cached = is_model_cached(model_name)

            if not cached:
                self._queue.put(("download_start", model_name))
            else:
                self._queue.put(("status", f"Lade {model_name}...", YELLOW))

            whisper = WhisperModel(model_name, device="cpu", compute_type="int8")

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

            frame_ms = 30
            frame_samples = int(SAMPLE_RATE * frame_ms / 1000)
            silence_frames = int(1500 / frame_ms)
            ring = collections.deque(maxlen=silence_frames)
            voiced = []
            triggered = False

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
                if text:
                    self._queue.put(("transcript", text))
                    result = detect_reminder(text)
                    if result:
                        reminder = add_reminder(
                            result["task"],
                            result.get("time_expression"),
                            result.get("original", text),
                        )
                        self._queue.put(("reminder", reminder))

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
                elif kind == "status":
                    self._set_status(msg[1], msg[2])
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
