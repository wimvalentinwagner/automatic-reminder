# Erinnerungs-Tool

Hört per Mikrofon zu, erkennt automatisch Erinnerungen/Aufgaben im Gespräch und speichert sie.

## Voraussetzungen

- Python 3.10+
- [Ollama](https://ollama.ai) läuft auf `localhost:11434`
- Ein Ollama-Modell (z.B. `llama3.2`)

## Installation

```bash
pip install -r requirements.txt
```

Bei Problemen mit `webrtcvad`:
```bash
pip install webrtcvad-wheels
# oder
pip install webrtcvad
```

## Konfiguration

In `config.py` anpassen:
- `OLLAMA_MODEL` → dein installiertes Ollama-Modell (z.B. `llama3.2`, `mistral`, `gemma3`)
- `WHISPER_MODEL` → Größe des Whisper-Modells (`tiny`, `base`, `small`, `medium`)
- `WHISPER_LANGUAGE` → Sprache (`de` für Deutsch)

## Verwendung

```bash
# Mikrofon starten - einfach reden, Erinnerungen werden automatisch erkannt
python main.py listen

# Alle gespeicherten Erinnerungen anzeigen
python main.py list

# Erinnerung manuell per Text hinzufügen
python main.py add "Ich muss morgen den Arzt anrufen"
```

## Wie es funktioniert

1. Mikrofon wird kontinuierlich abgehört
2. Spracherkennung (Whisper) transkribiert was du sagst
3. Ollama analysiert den Text und erkennt ob eine Erinnerung/Aufgabe darin steckt
4. Bei Erkennung: Desktop-Benachrichtigung + Speicherung in `reminders.json`

## Beispiel

Du sagst: *"...und ah ich muss das dann noch mit dem Chef besprechen, bevor ich am Freitag in den Urlaub fahre..."*

→ Wird erkannt als Erinnerung: **"Mit dem Chef besprechen"**, Zeitangabe: **"vor Freitag"**
