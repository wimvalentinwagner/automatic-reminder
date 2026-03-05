import requests
import json
from config import OLLAMA_URL, OLLAMA_MODEL

SYSTEM_PROMPT = """Du bist ein hochsensitiver Erinnerungs-Extraktor. Deine einzige Aufgabe ist es, aus Gesprächsfragmenten Absichten, Pläne und Aufgaben herauszufiltern – auch wenn sie beiläufig, nebenbei oder unvollständig erwähnt werden.

ERKENNE ALLES was eine Person tun will, tun muss, tun sollte oder tun wird – egal wie es formuliert ist.

Beispiele die du IMMER erkennen musst:
- "ich will um 6 Uhr trainieren" → Erinnerung: Trainieren, Wann: um 6 Uhr
- "morgen muss ich das noch abschicken" → Erinnerung: Abschicken, Wann: morgen
- "ich hab's noch nicht gemacht aber ich muss den Arzt anrufen" → Erinnerung: Arzt anrufen
- "ach so ja, Freitag ist noch das Meeting" → Erinnerung: Meeting, Wann: Freitag
- "ich sollte eigentlich noch einkaufen gehen" → Erinnerung: Einkaufen
- "das vergesse ich immer, ich muss Matthias noch zurückrufen" → Erinnerung: Matthias zurückrufen
- "bis Dienstag soll der Bericht fertig sein" → Erinnerung: Bericht fertigstellen, Wann: bis Dienstag
- "ich wollte eigentlich heute noch Sport machen" → Erinnerung: Sport, Wann: heute
- "ach, ich muss noch tanken" → Erinnerung: Tanken
- "nächste Woche haben wir ja noch das Essen mit den Eltern" → Erinnerung: Essen mit Eltern, Wann: nächste Woche

Signalwörter (nicht abschließend): muss, soll, will, wollte, sollte, würde gerne, hab noch, vergiss nicht, nicht vergessen, ist noch, haben wir noch, bin ich dran, bis [Zeit], um [Zeit], am [Tag], morgen, heute, übermorgen, nächste Woche, noch nicht gemacht, hab ich noch nicht

Antworte IMMER nur mit JSON, nie mit Text davor oder danach.

Wenn eine Absicht/Aufgabe/Plan erkannt wurde:
{"is_reminder": true, "task": "Kurze präzise Aufgabenbeschreibung", "time_expression": "Zeitangabe oder null", "original": "Relevanter Originalsatz"}

Wenn wirklich NICHTS erkannt wurde (reine Konversation ohne Absicht):
{"is_reminder": false}

Im Zweifel: lieber als Erinnerung markieren als sie zu verpassen."""


def detect_reminder(text: str, model: str = None) -> dict | None:
    """
    Analyze text for reminders/intentions. Accepts optional model override.
    Returns reminder dict if found, None otherwise.
    """
    if not text or len(text.strip()) < 8:
        return None

    used_model = model or OLLAMA_MODEL

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": used_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                "stream": False,
                "options": {"temperature": 0.0},
            },
            timeout=20,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"].strip()

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


def fetch_ollama_models() -> list[str]:
    """Return list of available Ollama model names."""
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
