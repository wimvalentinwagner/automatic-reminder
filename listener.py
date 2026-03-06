import numpy as np
import sounddevice as sd
import collections
import threading
from faster_whisper import WhisperModel
from config import (
    SAMPLE_RATE, CHANNELS, SILENCE_DURATION, VAD_MODE, WHISPER_MODEL, WHISPER_LANGUAGE
)

try:
    import webrtcvad
    HAS_VAD = True
except ImportError:
    HAS_VAD = False
    print("[!] webrtcvad not available, using energy-based detection")


class MicListener:
    def __init__(self, on_speech_callback):
        self.on_speech = on_speech_callback
        self.running = False

        print(f"[*] Loading Whisper model '{WHISPER_MODEL}'...")
        self.whisper = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        print("[*] Whisper loaded.")

        if HAS_VAD:
            self.vad = webrtcvad.Vad(VAD_MODE)
        else:
            self.vad = None

        # Frame duration for VAD (10, 20 or 30 ms)
        self.frame_ms = 30
        self.frame_samples = int(SAMPLE_RATE * self.frame_ms / 1000)

        silence_frames = int(SILENCE_DURATION * 1000 / self.frame_ms)
        self.ring_buffer = collections.deque(maxlen=silence_frames)
        self.voiced_frames = []
        self.triggered = False

    def _is_speech(self, frame_bytes: bytes) -> bool:
        if self.vad:
            try:
                return self.vad.is_speech(frame_bytes, SAMPLE_RATE)
            except Exception:
                pass
        # Fallback: energy-based
        audio = np.frombuffer(frame_bytes, dtype=np.int16).astype(np.float32)
        rms = np.sqrt(np.mean(audio**2))
        return rms > 500

    def _process_audio(self, audio_frames: list):
        audio = np.concatenate(audio_frames).astype(np.float32) / 32768.0
        if len(audio) < SAMPLE_RATE * 0.3:  # Ignore < 0.3 seconds
            return
        segments, _ = self.whisper.transcribe(
            audio,
            language=WHISPER_LANGUAGE,
            beam_size=3,
            vad_filter=True,
        )
        text = " ".join(s.text for s in segments).strip()
        if text:
            print(f"[mic] {text}")
            self.on_speech(text)

    def _audio_callback(self, indata, frames, time_info, status):
        # Convert float32 -> int16 for VAD
        pcm = (indata[:, 0] * 32767).astype(np.int16)

        # Process in VAD frame chunks
        for start in range(0, len(pcm) - self.frame_samples + 1, self.frame_samples):
            frame = pcm[start:start + self.frame_samples]
            frame_bytes = frame.tobytes()
            is_speech = self._is_speech(frame_bytes)

            if not self.triggered:
                self.ring_buffer.append((frame, is_speech))
                speech_ratio = sum(1 for _, s in self.ring_buffer if s) / max(len(self.ring_buffer), 1)
                if speech_ratio > 0.6:
                    self.triggered = True
                    self.voiced_frames = [f for f, _ in self.ring_buffer]
                    self.ring_buffer.clear()
            else:
                self.voiced_frames.append(frame)
                self.ring_buffer.append((frame, is_speech))
                speech_ratio = sum(1 for _, s in self.ring_buffer if s) / max(len(self.ring_buffer), 1)
                if speech_ratio < 0.2:
                    # Speech ended - transcribe in background
                    frames_to_process = self.voiced_frames[:]
                    threading.Thread(
                        target=self._process_audio,
                        args=(frames_to_process,),
                        daemon=True,
                    ).start()
                    self.ring_buffer.clear()
                    self.voiced_frames = []
                    self.triggered = False

    def start(self):
        self.running = True
        print(f"[*] Listening... (language: {WHISPER_LANGUAGE}, {SAMPLE_RATE}Hz)")
        print("[*] Press Ctrl+C to stop.\n")
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=self.frame_samples,
            callback=self._audio_callback,
        ):
            while self.running:
                sd.sleep(100)

    def stop(self):
        self.running = False
