#!/usr/bin/env python3
"""
Erinnerungs-Tool
Hört per Mikrofon zu, erkennt Erinnerungen/Aufgaben im Gespräch
und speichert sie automatisch.
"""
import sys
import argparse
from detector import detect_reminder
from storage import add_reminder, list_reminders
from notifier import notify


def on_speech(text: str):
    """Called for every transcribed speech segment."""
    result = detect_reminder(text)
    if result:
        reminder = add_reminder(
            task=result["task"],
            time_expression=result.get("time_expression"),
            original=result.get("original", text),
        )
        notify(
            "Neue Erinnerung erkannt!",
            f"{reminder['task']}" + (f"\nWann: {reminder['time_expression']}" if reminder.get("time_expression") else ""),
        )


def run_listener():
    from listener import MicListener
    listener = MicListener(on_speech_callback=on_speech)
    try:
        listener.start()
    except KeyboardInterrupt:
        print("\n[*] Beende...")
        listener.stop()


def main():
    parser = argparse.ArgumentParser(description="Erinnerungs-Tool mit Ollama + Mikrofon")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("listen", help="Mikrofon starten und auf Erinnerungen warten")
    subparsers.add_parser("list", help="Alle gespeicherten Erinnerungen anzeigen")

    add_parser = subparsers.add_parser("add", help="Erinnerung manuell hinzufügen")
    add_parser.add_argument("text", help="Text der Erinnerung")

    args = parser.parse_args()

    if args.command == "listen" or args.command is None:
        run_listener()
    elif args.command == "list":
        list_reminders()
    elif args.command == "add":
        result = detect_reminder(args.text)
        if result:
            add_reminder(result["task"], result.get("time_expression"), args.text)
        else:
            add_reminder(args.text, None, args.text)


if __name__ == "__main__":
    main()
