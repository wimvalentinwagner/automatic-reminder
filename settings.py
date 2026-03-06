import json
import os
from config import OLLAMA_MODEL, WHISPER_MODEL

SETTINGS_FILE = "settings.json"


def load_settings() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"ollama_model": OLLAMA_MODEL, "whisper_model": WHISPER_MODEL, "language": "en"}


def save_settings(settings: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
