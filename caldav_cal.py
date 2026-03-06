"""
CalDAV-basierte Kalender-Integration.
Unterstützt: Apple iCloud, Microsoft Outlook 365, Nextcloud, generisches CalDAV.
"""
import uuid
from datetime import datetime, timedelta

# Bekannte CalDAV-Server
PROVIDERS = {
    "apple": {
        "label":    "Apple iCloud",
        "url":      "https://caldav.icloud.com",
        "help":     "App-spezifisches Passwort unter appleid.apple.com → Sicherheit",
        "user_hint": "Apple ID (E-Mail)",
        "pass_hint": "App-spezifisches Passwort",
    },
    "outlook": {
        "label":    "Microsoft Outlook 365",
        "url":      "https://outlook.office365.com",
        "help":     "Microsoft-Konto E-Mail + Passwort (oder App-Passwort bei 2FA)",
        "user_hint": "Microsoft-Konto E-Mail",
        "pass_hint": "Passwort / App-Passwort",
    },
    "nextcloud": {
        "label":    "Nextcloud",
        "url":      "",  # wird vom User eingetragen
        "help":     "URL deiner Nextcloud-Instanz",
        "user_hint": "Benutzername",
        "pass_hint": "Passwort",
        "custom_url": True,
    },
    "caldav": {
        "label":    "Eigener CalDAV-Server",
        "url":      "",
        "help":     "Beliebiger CalDAV-kompatibler Server",
        "user_hint": "Benutzername",
        "pass_hint": "Passwort",
        "custom_url": True,
    },
}

DEFAULT_DURATION_H = 1


def test_connection(provider_id: str, url: str, username: str, password: str) -> bool:
    """Test if CalDAV credentials are valid."""
    try:
        import caldav
        client = caldav.DAVClient(url=url, username=username, password=password)
        principal = client.principal()
        principal.calendars()
        return True
    except Exception:
        return False


def add_event(url: str, username: str, password: str,
              task: str, start_dt: datetime | None) -> str | None:
    """Add event via CalDAV. Returns UID or None."""
    try:
        import caldav
        from icalendar import Calendar, Event as iEvent

        client = caldav.DAVClient(url=url, username=username, password=password)
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            return None
        cal = calendars[0]

        uid = str(uuid.uuid4())
        now = datetime.utcnow()

        ical = Calendar()
        ical.add("prodid", "-//Erinnerungs-KI//DE")
        ical.add("version", "2.0")

        event = iEvent()
        event.add("summary", task)
        event.add("uid", uid)
        event.add("dtstamp", now)

        if start_dt:
            event.add("dtstart", start_dt)
            event.add("dtend", start_dt + timedelta(hours=DEFAULT_DURATION_H))
        else:
            today = datetime.now().date()
            event.add("dtstart", today)
            event.add("dtend", today)

        ical.add_component(event)
        cal.save_event(ical.to_ical().decode("utf-8"))
        return uid

    except Exception as e:
        print(f"[caldav] Fehler beim Erstellen: {e}")
        return None


def delete_event(url: str, username: str, password: str, uid: str) -> bool:
    """Delete event by UID via CalDAV."""
    try:
        import caldav
        client = caldav.DAVClient(url=url, username=username, password=password)
        principal = client.principal()
        for cal in principal.calendars():
            try:
                events = cal.search(event=True)
                for ev in events:
                    ev.load()
                    if str(ev.vobject_instance.vevent.uid.value) == uid:
                        ev.delete()
                        return True
            except Exception:
                continue
        return False
    except Exception as e:
        print(f"[caldav] Fehler beim Löschen: {e}")
        return False
