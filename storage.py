import json
import os
import uuid
from datetime import datetime
from config import REMINDERS_FILE


def load_reminders() -> list:
    if not os.path.exists(REMINDERS_FILE):
        return []
    with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_reminders(reminders: list):
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, ensure_ascii=False, indent=2)


def add_reminder(task: str, time_expression: str | None, original: str,
                 gcal_event_id: str | None = None) -> dict:
    reminders = load_reminders()
    reminder = {
        "id": str(uuid.uuid4())[:8],
        "task": task,
        "time_expression": time_expression,
        "original": original,
        "created_at": datetime.now().isoformat(),
        "notified": False,
        "gcal_event_id": gcal_event_id,
    }
    reminders.append(reminder)
    save_reminders(reminders)
    print(f"\n[+] Erinnerung gespeichert: '{task}'")
    if time_expression:
        print(f"    Zeitangabe: {time_expression}")
    print(f"    ID: {reminder['id']}\n")
    return reminder


def delete_reminder(reminder_id: str) -> bool:
    reminders = load_reminders()
    new = [r for r in reminders if r["id"] != reminder_id]
    if len(new) == len(reminders):
        return False
    save_reminders(new)
    return True


def find_reminder_by_keyword(keyword: str) -> dict | None:
    """Find the best matching reminder by keyword (case-insensitive)."""
    keyword = keyword.lower()
    reminders = load_reminders()
    for r in reminders:
        if keyword in r["task"].lower() or keyword in r.get("original", "").lower():
            return r
    return None


def list_reminders():
    reminders = load_reminders()
    if not reminders:
        print("Keine Erinnerungen gespeichert.")
        return
    print(f"\n--- {len(reminders)} Erinnerung(en) ---")
    for r in reminders:
        status = "[erledigt]" if r.get("notified") else "[offen]  "
        time_str = f" | Wann: {r['time_expression']}" if r.get("time_expression") else ""
        print(f"{status} [{r['id']}] {r['task']}{time_str}")
    print()
