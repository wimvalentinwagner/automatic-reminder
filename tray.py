"""
Erinnerungs-Tool – Tray-Modus
Startet sofort im System-Tray und hört direkt zu.
Kein Fenster, keine Klicks nötig.
"""
import threading
import collections
import subprocess
import sys
import os

import pystray
from PIL import Image, ImageDraw

from detector import detect_reminder, is_model_installed, pull_model
from storage import add_reminder, find_reminder_by_keyword, delete_reminder
from notifier import notify
from settings import load_settings
from config import SAMPLE_RATE, WHISPER_LANGUAGE, VAD_MODE

# ── Tray-Icon zeichnen ────────────────────────────────────────────────────

def _make_icon(listening: bool) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = "#4ade80" if listening else "#666666"
    # Kreis
    d.ellipse([4, 4, size - 4, size - 4], fill=color)
    # Mikrofon-Symbol (vereinfacht)
    d.rectangle([24, 14, 40, 38], fill="white", outline="white")
    d.arc([18, 28, 46, 50], start=0, end=180, fill="white", width=4)
    d.line([32, 50, 32, 56], fill="white", width=4)
    d.line([24, 56, 40, 56], fill="white", width=4)
    return img


# ── Haupt-App ─────────────────────────────────────────────────────────────

class TrayApp:
    def __init__(self):
        self._listening = False
        self._paused = False
        self._listener_thread = None
        self._stop_event = threading.Event()
        self._settings = load_settings()

        self._icon = pystray.Icon(
            "Erinnerungs-KI",
            _make_icon(False),
            "Erinnerungs-KI",
            menu=pystray.Menu(
                pystray.MenuItem("● Zuhören läuft", lambda: None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Pause / Fortsetzen", self._toggle_pause),
                pystray.MenuItem("UI öffnen", self._open_ui),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Beenden", self._quit),
            ),
        )

    def run(self):
        # Sofort mit Zuhören starten
        threading.Thread(target=self._start_listening, daemon=True).start()
        self._icon.run()

    def _update_icon(self):
        active = self._listening and not self._paused
        self._icon.icon = _make_icon(active)
        self._icon.title = "Erinnerungs-KI – Zuhört" if active else "Erinnerungs-KI – Pausiert"

    def _toggle_pause(self):
        self._paused = not self._paused
        self._update_icon()
        if self._paused:
            self._icon.notify("Pausiert", "Erinnerungs-KI hört nicht mehr zu.")
        else:
            self._icon.notify("Fortgesetzt", "Erinnerungs-KI hört wieder zu.")

    def _open_ui(self):
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.py")
        venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   ".venv", "Scripts", "pythonw.exe")
        if not os.path.exists(venv_python):
            venv_python = sys.executable
        subprocess.Popen([venv_python, script])

    def _quit(self):
        self._stop_event.set()
        self._listening = False
        self._icon.stop()

    # ── Listener ──────────────────────────────────────────────────────────

    def _start_listening(self):
        try:
            import numpy as np
            import sounddevice as sd
            from faster_whisper import WhisperModel

            settings = self._settings
            whisper_model = settings.get("whisper_model", "small")
            ollama_model  = settings.get("ollama_model", "gemma3:4b")

            # Ollama-Modell sicherstellen
            if not is_model_installed(ollama_model):
                self._icon.notify("Lade Modell...", f"'{ollama_model}' wird heruntergeladen.")
                pull_model(ollama_model)
                self._icon.notify("Modell bereit", f"'{ollama_model}' wurde geladen.")

            # Whisper laden
            self._icon.notify("Erinnerungs-KI", "Lade Sprachmodell...")
            whisper = WhisperModel(whisper_model, device="cpu", compute_type="int8")

            self._listening = True
            self._update_icon()
            self._icon.notify("Erinnerungs-KI", "Hört jetzt zu.")

            try:
                import webrtcvad
                vad = webrtcvad.Vad(VAD_MODE)
                use_vad = True
            except ImportError:
                vad = None
                use_vad = False

            frame_ms      = 30
            frame_samples = int(SAMPLE_RATE * frame_ms / 1000)
            silence_frames = int(1500 / frame_ms)
            ring    = collections.deque(maxlen=silence_frames)
            voiced  = []
            triggered = False
            context_buf   = collections.deque(maxlen=5)
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
                if self._paused:
                    return
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
                full_context = " ".join(context_buf)
                result = detect_reminder(full_context, model=ollama_model)

                if result:
                    action = result.get("action")
                    if action == "add":
                        task_key = result["task"].lower().strip()
                        if task_key not in seen_reminders:
                            seen_reminders.add(task_key)
                            reminder = add_reminder(
                                result["task"],
                                result.get("time_expression"),
                                result.get("original", text),
                            )
                            time_str = f"\nWann: {reminder['time_expression']}" if reminder.get("time_expression") else ""
                            self._icon.notify("Erinnerung gespeichert", reminder["task"] + time_str)
                    elif action == "delete":
                        found = find_reminder_by_keyword(result.get("target", ""))
                        if found:
                            delete_reminder(found["id"])
                            self._icon.notify("Erinnerung gelöscht", found["task"])

            def audio_cb(indata, frames, time_info, status):
                nonlocal triggered, voiced
                if self._stop_event.is_set():
                    raise sd.CallbackStop()
                if self._paused:
                    return
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
                self._stop_event.wait()

        except Exception as e:
            self._icon.notify("Fehler", str(e))
            self._listening = False
            self._update_icon()


if __name__ == "__main__":
    TrayApp().run()
