# Reminder AI

A privacy-first, AI-powered reminder tool that listens to your microphone, detects tasks and reminders in your speech, and saves them automatically — completely offline.

> **Alpha 0.1** — core features working, UI and calendar integrations functional.

---

## Features

- **Passive listening** — runs silently in the system tray and detects reminders without any button press
- **100% local / offline** — uses [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for speech recognition and [Ollama](https://ollama.com) for intent detection; no data leaves your machine
- **Multilingual** — supports English and German (switchable in-app with the EN/DE button)
- **Add & delete reminders by voice** — say "remind me to call John tomorrow" or "forget the workout reminder"
- **Calendar sync** — optional integration with Google Calendar, Apple iCloud, Microsoft Outlook 365, Nextcloud, or any CalDAV server

⚠️This feature has not yet been tested and may cause problems⚠️
- **Desktop UI** — clean dark-mode UI with model selection, live transcript, and reminder list
- **Auto-updater** — checks for git updates and missing packages on startup

---

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally (`ollama serve`)
- A microphone

---

## Installation

### Windows (recommended)

1. Install [Python 3.10+](https://python.org) and [Ollama](https://ollama.com)
2. Pull a model: `ollama pull gemma3:4b`
3. Clone this repo and double-click **`reminder.bat`**

The `.bat` file creates a virtual environment, installs all dependencies, and launches the app on first run.

### Manual (Windows / Linux / macOS)

```bash
git clone https://github.com/wimvalentinwagner/automatic-reminder.git
cd automatic-reminder
python -m venv .venv

# Windows:
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python ui.py

# Linux / macOS:
.venv/bin/pip install -r requirements.txt
.venv/bin/python ui.py
```

---

## Usage

### UI mode

Double-click `reminder.bat` (Windows) or run `python ui.py`.

- Select your Whisper model (tiny → large; smaller = faster, larger = more accurate)
- Select your Ollama model from the dropdown
- Switch language with the **EN** / **DE** button in the top-right corner
- Click **Start** — the app listens and auto-detects reminders
- Detected reminders appear in the list below

### Tray mode

Double-click `tray.bat` (Windows) or run `python tray.py`.

The app runs silently in your system tray and listens immediately. Right-click the icon to pause, open the UI, or quit. When the tray is running, the UI shows a green "● Tray running" indicator.

### CLI mode

```bash
python main.py listen                                        # Start microphone listener
python main.py list                                          # List all saved reminders
python main.py add "Buy milk"                                # Add a reminder manually
python main.py test "I need to call the dentist at 3pm"     # Test detection
```

---

## How it works

1. **Microphone** — captured via `sounddevice` with WebRTC VAD for silence detection
2. **Whisper** — transcribes speech segments locally (faster-whisper)
3. **Ollama** — analyzes the transcript and returns structured JSON (`add` / `delete` / `none`)
4. **Storage** — reminder saved to `reminders.json`
5. **Calendar** *(optional)* — event created via Google Calendar API or CalDAV

**Example:** You say: *"...and I need to discuss that with my boss before I leave for vacation on Friday..."*

→ Detected as reminder: **"Discuss with boss"**, time: **"before Friday"**

---

## Calendar Setup

### Google Calendar

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a project → Enable **Google Calendar API**
3. Create **OAuth 2.0 Client ID** (Desktop App) → Download JSON
4. In the app: **Calendar tab** → use the file picker to select the downloaded `credentials.json`

### Apple iCloud / Outlook / Nextcloud

Open the **Calendar tab** in the UI and click **Set up** next to the provider. You will need an app-specific password for iCloud and Outlook with 2FA enabled.

---

## Configuration

Settings are saved automatically to `settings.json` (excluded from git):

| Key | Default | Description |
|-----|---------|-------------|
| `ollama_model` | `gemma3:4b` | Ollama model for intent detection |
| `whisper_model` | `small` | Whisper model size |
| `language` | `en` | UI and speech recognition language (`en` or `de`) |

The Ollama model can be changed in the UI dropdown — any model available in Ollama works. `gemma3:4b` is a good balance of speed and accuracy.

---

## Project Structure

```
├── ui.py           # Main desktop UI (Tkinter)
├── tray.py         # System tray mode
├── main.py         # CLI entry point
├── detector.py     # Ollama-based reminder detection
├── listener.py     # Microphone + Whisper transcription
├── storage.py      # Reminder persistence (JSON)
├── notifier.py     # Desktop notifications
├── gcal.py         # Google Calendar integration
├── caldav_cal.py   # CalDAV integration (iCloud, Outlook, Nextcloud)
├── calendars.py    # Calendar provider coordinator
├── settings.py     # Settings load/save
├── config.py       # Default constants
├── updater.py      # Startup update checker UI
├── requirements.txt
├── reminder.bat  # Windows launcher (UI mode)
└── tray.bat        # Windows launcher (tray mode)
```
