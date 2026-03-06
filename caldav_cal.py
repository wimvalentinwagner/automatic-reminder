"""
CalDAV-based calendar integration.
Supports: Apple iCloud, Microsoft Outlook 365, Nextcloud, generic CalDAV.
"""
import uuid
from datetime import datetime, timedelta

# Known CalDAV providers
PROVIDERS = {
    "apple": {
        "label":    "Apple iCloud",
        "url":      "https://caldav.icloud.com",
        "help": (
            "You need an app-specific password – NOT your regular Apple password.\n"
            "Step 1: Go to appleid.apple.com\n"
            "Step 2: Sign-In and Security → App-Specific Passwords\n"
            "Step 3: Click '+' and enter a name (e.g. 'Reminder AI')\n"
            "Step 4: Copy the generated password and enter it here."
        ),
        "help_url":  "https://appleid.apple.com",
        "user_hint": "Apple ID (email)",
        "pass_hint": "App-specific password",
    },
    "outlook": {
        "label":    "Microsoft Outlook 365",
        "url":      "https://outlook.office365.com",
        "help": (
            "Use your Microsoft email and regular password.\n"
            "If you have 2-factor authentication, you need an app password:\n"
            "Step 1: Go to account.microsoft.com\n"
            "Step 2: Security → Advanced security options\n"
            "Step 3: App passwords → Create a new app password\n"
            "Step 4: Enter the generated password here."
        ),
        "help_url":  "https://account.microsoft.com/security",
        "user_hint": "Microsoft account email",
        "pass_hint": "Password / App password",
    },
    "nextcloud": {
        "label":    "Nextcloud",
        "url":      "",
        "help": (
            "Enter the URL of your Nextcloud instance (e.g. https://cloud.example.com).\n"
            "Username and password are the same as your Nextcloud login.\n"
            "Tip: You can also create an app password under\n"
            "Settings → Security → Devices & Sessions → Create app password."
        ),
        "user_hint": "Username",
        "pass_hint": "Password",
        "custom_url": True,
    },
    "caldav": {
        "label":    "Custom CalDAV Server",
        "url":      "",
        "help": (
            "Enter the CalDAV URL of your server.\n"
            "You can find this in your calendar provider's settings or\n"
            "in your server's documentation (often /dav/ or /calendars/)."
        ),
        "user_hint": "Username",
        "pass_hint": "Password",
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
        ical.add("prodid", "-//Reminder-AI//EN")
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
        print(f"[caldav] Error creating event: {e}")
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
        print(f"[caldav] Error deleting event: {e}")
        return False
