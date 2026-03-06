import requests
import json
import re
from config import OLLAMA_URL, OLLAMA_MODEL

SYSTEM_PROMPT = (
    "You analyze spoken text (any language) and detect two things: new reminders/tasks AND deletion of reminders. "
    "Reply ONLY with JSON.\n\n"
    "NEW TASK detected (even mentioned casually):\n"
    "{\"action\": \"add\", \"task\": \"...\", \"time_expression\": \"... or null\", \"original\": \"...\"}\n\n"
    "DELETION of a reminder detected:\n"
    "{\"action\": \"delete\", \"target\": \"keyword of the reminder to delete\"}\n\n"
    "NOTHING detected:\n"
    "{\"action\": \"none\"}\n\n"
    "Examples:\n"
    "\"I want to work out at 6\" → {\"action\": \"add\", \"task\": \"Work out\", \"time_expression\": \"at 6\", \"original\": \"I want to work out at 6\"}\n"
    "\"I need to call the doctor\" → {\"action\": \"add\", \"task\": \"Call doctor\", \"time_expression\": null, \"original\": \"I need to call the doctor\"}\n"
    "\"forget the workout reminder\" → {\"action\": \"delete\", \"target\": \"workout\"}\n"
    "\"the doctor thing is taken care of, delete it\" → {\"action\": \"delete\", \"target\": \"doctor\"}\n"
    "\"I don't need the grocery reminder anymore\" → {\"action\": \"delete\", \"target\": \"grocery\"}\n"
    "\"how was your day?\" → {\"action\": \"none\"}"
)


def _extract_json(text: str) -> dict | None:
    """Robust JSON extraction: handles code blocks, extra text, etc."""
    # Strip markdown code blocks
    text = re.sub(r"```(?:json)?\s*", "", text).strip()

    # Extract first complete JSON object
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

        print(f"[ollama] {raw[:120]}")

        data = _extract_json(raw)
        if data and data.get("action") in ("add", "delete"):
            return data
        return None

    except requests.exceptions.ConnectionError:
        print("[!] Ollama not reachable – is Ollama running on localhost:11434?")
        return None
    except Exception as e:
        print(f"[!] Detector error: {e}")
        return None


def fetch_ollama_models() -> list[str]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def is_model_installed(model: str) -> bool:
    return model in fetch_ollama_models()


def pull_model(model: str, progress_callback=None):
    """
    Pull an Ollama model. progress_callback(status, percent) is called during download.
    Blocks until complete.
    """
    with requests.post(
        f"{OLLAMA_URL}/api/pull",
        json={"name": model, "stream": True},
        stream=True,
        timeout=None,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            status = data.get("status", "")
            total = data.get("total", 0)
            completed = data.get("completed", 0)
            pct = int(completed / total * 100) if total > 0 else 0

            if progress_callback:
                progress_callback(status, pct, completed, total)

            if status == "success":
                break
