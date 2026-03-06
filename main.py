#!/usr/bin/env python3
"""
Reminder AI
Listens via microphone, detects reminders/tasks in conversation
and saves them automatically.
"""
import sys
import argparse
from detector import detect_reminder, is_model_installed, pull_model
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
            "New reminder detected!",
            f"{reminder['task']}" + (f"\nWhen: {reminder['time_expression']}" if reminder.get("time_expression") else ""),
        )


def run_listener():
    from listener import MicListener
    listener = MicListener(on_speech_callback=on_speech)
    try:
        listener.start()
    except KeyboardInterrupt:
        print("\n[*] Stopping...")
        listener.stop()


def main():
    parser = argparse.ArgumentParser(description="Reminder AI with Ollama + microphone")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("listen", help="Start microphone and listen for reminders")
    subparsers.add_parser("list", help="Show all saved reminders")

    add_parser = subparsers.add_parser("add", help="Manually add a reminder")
    add_parser.add_argument("text", help="Reminder text")

    test_parser = subparsers.add_parser("test", help="Test reminder detection directly")
    test_parser.add_argument("text", help="Text to test")

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
    elif args.command == "test":
        from config import OLLAMA_MODEL
        if not is_model_installed(OLLAMA_MODEL):
            print(f"[*] Model '{OLLAMA_MODEL}' not installed – downloading...")
            def show(status, pct, done, total):
                bar = ("█" * (pct // 5)).ljust(20)
                print(f"\r  [{bar}] {pct}% – {status}", end="", flush=True)
            pull_model(OLLAMA_MODEL, progress_callback=show)
            print("\n[OK] Done!")
        print(f"\nTest text: \"{args.text}\"")
        result = detect_reminder(args.text)
        if result:
            print(f"[OK] Reminder detected!")
            print(f"     Task: {result['task']}")
            print(f"     Time: {result.get('time_expression')}")
        else:
            print("[--] No reminder detected.")


if __name__ == "__main__":
    main()
