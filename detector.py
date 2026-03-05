import requests
import json
from config import OLLAMA_URL, OLLAMA_MODEL

SYSTEM_PROMPT = """Du bist ein Assistent, der Erinnerungen und To-Dos aus Gesprächen erkennt.

Wenn der Text eine Erinnerung, Aufgabe oder einen Termin enthält (z.B. "ich muss...", "ich soll...", "vergiss nicht...", "erinnere mich...", "bis dann...", "am Montag...", etc.), antworte mit einem JSON-Objekt:

{
  "is_reminder": true,
  "task": "Was muss gemacht werden (kurze Zusammenfassung)",
  "time_expression": "Zeitangabe wie im Text (z.B. 'morgen', 'um 15 Uhr', 'nächsten Montag') oder null",
  "original": "Der relevante Originalsatz"
}

Wenn KEIN Erinnerung/Aufgabe enthalten ist, antworte nur mit:
{"is_reminder": false}

Antworte NUR mit dem JSON, ohne weitere Erklärungen."""


def detect_reminder(text: str) -> dict | None:
    """
    Send transcribed text to Ollama and check if it contains a reminder.
    Returns reminder dict if found, None otherwise.
    """
    if not text or len(text.strip()) < 5:
        return None

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            },
            timeout=15,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"].strip()

        # Extract JSON from response
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        data = json.loads(content[start:end])
        if data.get("is_reminder"):
            return data
        return None

    except requests.exceptions.ConnectionError:
        print("[!] Ollama nicht erreichbar. Läuft Ollama auf localhost:11434?")
        return None
    except (json.JSONDecodeError, KeyError) as e:
        print(f"[!] Fehler beim Parsen der Ollama-Antwort: {e}")
        return None
