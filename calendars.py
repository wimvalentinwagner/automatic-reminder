"""
Zentrale Kalender-Schnittstelle.
Koordiniert alle aktivierten Kalender-Provider.
"""
from __future__ import annotations
from datetime import datetime
import gcal
import caldav_cal
from settings import load_settings, save_settings


def get_enabled_providers() -> list[str]:
    s = load_settings()
    return [k for k, v in s.get("calendars", {}).items() if v.get("enabled")]


def add_to_all(task: str, start_dt: datetime | None,
               model: str = None) -> dict[str, str]:
    """Add event to all enabled calendars. Returns {provider_id: event_id}."""
    ids: dict[str, str] = {}
    s = load_settings()
    cal_cfg = s.get("calendars", {})

    # Google Calendar
    if cal_cfg.get("google", {}).get("enabled") and gcal.is_connected():
        eid = gcal.add_event_dt(task, start_dt)
        if eid:
            ids["google"] = eid

    # CalDAV-Provider
    for pid in caldav_cal.PROVIDERS:
        cfg = cal_cfg.get(pid, {})
        if not cfg.get("enabled"):
            continue
        url  = cfg.get("url") or caldav_cal.PROVIDERS[pid]["url"]
        user = cfg.get("username", "")
        pw   = cfg.get("password", "")
        if not user or not pw:
            continue
        eid = caldav_cal.add_event(url, user, pw, task, start_dt)
        if eid:
            ids[pid] = eid

    return ids


def delete_from_all(event_ids: dict[str, str]):
    """Delete events from all calendars based on stored IDs."""
    s = load_settings()
    cal_cfg = s.get("calendars", {})

    if "google" in event_ids and gcal.is_connected():
        gcal.delete_event(event_ids["google"])

    for pid in caldav_cal.PROVIDERS:
        if pid not in event_ids:
            continue
        cfg  = cal_cfg.get(pid, {})
        url  = cfg.get("url") or caldav_cal.PROVIDERS[pid]["url"]
        user = cfg.get("username", "")
        pw   = cfg.get("password", "")
        if user and pw:
            caldav_cal.delete_event(url, user, pw, event_ids[pid])


def save_provider_config(provider_id: str, enabled: bool,
                          username: str = "", password: str = "",
                          url: str = ""):
    s = load_settings()
    if "calendars" not in s:
        s["calendars"] = {}
    s["calendars"][provider_id] = {
        "enabled":  enabled,
        "username": username,
        "password": password,
        "url":      url,
    }
    save_settings(s)


def get_provider_config(provider_id: str) -> dict:
    s = load_settings()
    return s.get("calendars", {}).get(provider_id, {})
