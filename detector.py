import requests
import json
import re
from config import OLLAMA_URL, OLLAMA_MODEL

# Kurzer, klarer Prompt – keine langen Erklärungen die das Modell verwirren
SYSTEM_PROMPT = (
    "Du extrahierst Erinnerungen und Aufgaben aus gesprochenem Text. "
    "Antworte NUR mit JSON.\n\n"
    "Gibt es eine Aufgabe, einen Plan oder eine Absicht? (auch beiläufig erwähnt)\n"
    "JA → {\"is_reminder\": true, \"task\": \"...\", \"time_expression\": \"...oder null\", \"original\": \"...\"}\n"
    "NEIN → {\"is_reminder\": false}\n\n"
    "Beispiele:\n"
    "\"ich will um 6 Uhr trainieren\" → {\"is_reminder\": true, \"task\": \"Trainieren\", \"time_expression\": \"um 6 Uhr\", \"original\": \"ich will um 6 Uhr trainieren\"}\n"
    "\"ich muss noch den Arzt anrufen\" → {\"is_reminder\": true, \"task\": \"Arzt anrufen\", \"time_expression\": null, \"original\": \"ich muss noch den Arzt anrufen\"}\n"
    "\"wie war dein Tag?\" → {\"is_reminder\": false}"
)


def _extract_json(text: str) -> dict | None:
    """Robust JSON extraction: handles code blocks, extra text, etc."""
    # Markdown-Codeblöcke entfernen
    text = re.sub(r"```(?:json)?\s*", "", text).strip()

    # Erstes vollständiges JSON-Objekt extrahieren
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if start is None:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    start = None
    return None


def detect_reminder(text: str, model: str = None) -> dict | None:
    if not text or len(text.strip()) < 5:
        return None

    used_model = model or OLLAMA_MODEL

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": used_model,
                "system": SYSTEM_PROMPT,
                "prompt": text,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
            },
            timeout=20,
        )
        response.raise_for_status()
        raw = response.json()["response"].strip()

        print(f"[ollama] {raw[:120]}")     # Debug: was kommt zurück?

        data = _extract_json(raw)
        if data and data.get("is_reminder"):
            return data
        return None

    except requests.exceptions.ConnectionError:
        print("[!] Ollama nicht erreichbar – läuft Ollama auf localhost:11434?")
        return None
    except Exception as e:
        print(f"[!] Detector-Fehler: {e}")
        return None


def fetch_ollama_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
