"""
Google Calendar Integration.
Erfordert credentials.json aus der Google Cloud Console.
"""
import os
import json
import requests
from datetime import datetime, timedelta, timezone

from config import OLLAMA_URL, OLLAMA_MODEL

BASE           = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS    = os.path.join(BASE, "credentials.json")
TOKEN          = os.path.join(BASE, "token.json")
SCOPES         = ["https://www.googleapis.com/auth/calendar"]
DEFAULT_DURATION_H = 1


# ── Auth ──────────────────────────────────────────────────────────────────

def is_configured() -> bool:
    return os.path.exists(CREDENTIALS)


def is_connected() -> bool:
    return os.path.exists(TOKEN)


def get_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN):
        creds = Credentials.from_authorized_user_file(TOKEN, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN, "w") as f:
            f.write(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def disconnect():
    if os.path.exists(TOKEN):
        os.remove(TOKEN)


# ── Zeitausdruck → datetime ───────────────────────────────────────────────

def parse_time_expression(expr: str | None, model: str = None) -> datetime | None:
    """Use Ollama to convert German natural language time to datetime."""
    if not expr:
        return None

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
    used_model = model or OLLAMA_MODEL

    prompt = (
        f"Heute ist {now_str}. "
        f"Wandle diesen deutschen Zeitausdruck in ein ISO 8601 Datum+Uhrzeit um: \"{expr}\". "
        "Antworte NUR mit dem ISO-Datetime (z.B. 2025-03-07T18:00:00) oder null wenn unklar."
    )

    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": used_model, "prompt": prompt,
                  "stream": False, "options": {"temperature": 0}},
            timeout=15,
        )
        raw = r.json()["response"].strip().strip('"').strip("'")
        if raw.lower() == "null" or not raw:
            return None
        # Nur den datetime-Teil extrahieren
        for token in raw.split():
            try:
                return datetime.fromisoformat(token.rstrip("."))
            except ValueError:
                continue
    except Exception:
        pass
    return None


# ── Kalender-Events ───────────────────────────────────────────────────────

def add_event(task: str, time_expression: str | None,
              model: str = None) -> str | None:
    """
    Add event to Google Calendar.
    Returns event_id or None on failure.
    """
    try:
        service = get_service()
        start_dt = parse_time_expression(time_expression, model)

        if start_dt:
            end_dt = start_dt + timedelta(hours=DEFAULT_DURATION_H)
            event_body = {
                "summary": task,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Berlin"},
                "end":   {"dateTime": end_dt.isoformat(),   "timeZone": "Europe/Berlin"},
            }
            if time_expression:
                event_body["description"] = f"Zeitangabe: {time_expression}"
        else:
            # Kein Zeitpunkt → Ganztages-Event für heute
            today = datetime.now().strftime("%Y-%m-%d")
            event_body = {
                "summary": task,
                "start": {"date": today},
                "end":   {"date": today},
            }

        event = service.events().insert(calendarId="primary", body=event_body).execute()
        return event.get("id")

    except Exception as e:
        print(f"[gcal] Fehler beim Erstellen: {e}")
        return None


def delete_event(event_id: str) -> bool:
    """Delete event from Google Calendar by event_id."""
    try:
        service = get_service()
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return True
    except Exception as e:
        print(f"[gcal] Fehler beim Löschen: {e}")
        return False
