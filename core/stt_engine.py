# stt_engine.py
# FINAL: Stable Push-to-Talk STT for Samuel

import threading
import tempfile
import os
import numpy as np

INPUT_DEVICE = 2
SAMPLE_RATE = 48000
CHANNELS = 1
DTYPE = "float32"

MIN_RMS = 0.003
CHUNK_S = 0.25
MAX_RECORD_SECONDS = 10.0

_audio_lock = threading.Lock()

_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper():
    global _whisper_model

    if _whisper_model:
        return _whisper_model

    with _whisper_lock:
        if _whisper_model:
            return _whisper_model

        from faster_whisper import WhisperModel

        print("[STT] Loading Whisper...")
        _whisper_model = WhisperModel(
            "base.en",
            device="cpu",
            compute_type="int8",
        )
        print("[STT] Whisper ready.")

    return _whisper_model


def _rms(audio):
    if audio is None or audio.size == 0:
        return 0.0
    a = audio.astype(np.float32)
    return float(np.sqrt(np.mean(a * a)))


def transcribe(audio):
    import soundfile as sf

    if audio is None or audio.size == 0:
        return "", "en"

    audio = audio.astype(np.float32).flatten()

    if _rms(audio) < MIN_RMS:
        print("[STT] Too quiet")
        return "", "en"

    model = _get_whisper()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        path = f.name

    try:
        sf.write(path, audio, SAMPLE_RATE)

        segments, info = model.transcribe(
            path,
            beam_size=1,
            vad_filter=True,
        )

        text = " ".join(s.text.strip() for s in segments).strip()
        lang = getattr(info, "language", "en")

        return text, lang

    finally:
        try:
            os.remove(path)
        except:
            pass


class SpeechListener:
    def __init__(self, on_text):
        self.on_text = on_text

        self._ptt_active = False
        self._frames = []
        self._stop = threading.Event()
        self._thread = None

    def start_ptt(self):
        if self._ptt_active:
            return

        self._ptt_active = True
        self._frames = []
        self._stop.clear()

        self._thread = threading.Thread(target=self._record, daemon=True)
        self._thread.start()

        print("[STT] Recording...")

    def stop_ptt(self):
        if not self._ptt_active:
            return

        self._stop.set()
        self._ptt_active = False

        print("[STT] Processing...")

        threading.Thread(target=self._process, daemon=True).start()

    def _record(self):
        import sounddevice as sd

        chunk = int(SAMPLE_RATE * CHUNK_S)
        max_chunks = int(MAX_RECORD_SECONDS / CHUNK_S)
        count = 0

        while not self._stop.is_set() and count < max_chunks:
            audio = sd.rec(
                chunk,
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=DTYPE,
                device=INPUT_DEVICE,
            )
            sd.wait()
            self._frames.append(audio)
            count += 1

    def _process(self):
        try:
            if self._thread:
                self._thread.join(timeout=2)

            if not self._frames:
                return

            audio = np.concatenate(self._frames).flatten()

            print("[STT] RMS:", _rms(audio))

            text, lang = transcribe(audio)

            if text:
                print(f"[STT] Heard: {text}")
                self.on_text(text, lang)
            else:
                print("[STT] Nothing detected")

        except Exception as e:
            print(f"[STT] Error: {e}")