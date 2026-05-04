# stt_engine.py
# EMERGENCY DEMO VERSION — fast push-to-talk STT

import threading
import tempfile
import os
import numpy as np

# IMPORTANT:
# Use None first so the Pi/Mac chooses the default mic.
# If this does not hear you, change it back to 2.
INPUT_DEVICE = 2

# IMPORTANT:
# 16000 is much faster for Whisper than 48000.
SAMPLE_RATE = 48000

CHANNELS = 1
DTYPE = "float32"

MIN_RMS = 0.002
CHUNK_S = 0.25
MAX_RECORD_SECONDS = 6.0

_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper():
    global _whisper_model

    if _whisper_model is not None:
        return _whisper_model

    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model

        from faster_whisper import WhisperModel

        print("[STT] Loading Whisper tiny.en...")
        _whisper_model = WhisperModel(
            "tiny.en",
            device="cpu",
            compute_type="int8",
        )
        print("[STT] Whisper ready.")

        return _whisper_model


def _rms(audio):
    if audio is None or audio.size == 0:
        return 0.0

    audio = audio.astype(np.float32)
    return float(np.sqrt(np.mean(audio * audio)))


def transcribe(audio):
    import soundfile as sf

    if audio is None or audio.size == 0:
        return "", "en"

    audio = audio.astype(np.float32).flatten()

    level = _rms(audio)
    print("[STT] RMS:", level)

    if level < MIN_RMS:
        print("[STT] Too quiet")
        return "", "en"

    model = _get_whisper()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name

    try:
        sf.write(wav_path, audio, SAMPLE_RATE)

        print("[STT] Transcribing...")

        segments, info = model.transcribe(
            wav_path,
            language="en",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )

        text = " ".join(segment.text.strip() for segment in segments).strip()

        print("[STT] Transcription done.")

        return text, "en"

    finally:
        try:
            os.remove(wav_path)
        except Exception:
            pass


class SpeechListener:
    def __init__(self, on_text):
        self.on_text = on_text

        self._ptt_active = False
        self._frames = []
        self._stop = threading.Event()
        self._thread = None

        # Load Whisper in background so the first button press is not as slow.
        threading.Thread(target=self._preload, daemon=True).start()

    def _preload(self):
        try:
            _get_whisper()
        except Exception as e:
            print(f"[STT] Preload error: {e}")

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

        chunk_frames = int(SAMPLE_RATE * CHUNK_S)
        max_chunks = int(MAX_RECORD_SECONDS / CHUNK_S)
        count = 0

        while not self._stop.is_set() and count < max_chunks:
            try:
                kwargs = {
                    "samplerate": SAMPLE_RATE,
                    "channels": CHANNELS,
                    "dtype": DTYPE,
                }

                if INPUT_DEVICE is not None:
                    kwargs["device"] = INPUT_DEVICE

                audio = sd.rec(chunk_frames, **kwargs)
                sd.wait()

                self._frames.append(audio)
                count += 1

            except Exception as e:
                print(f"[STT] Recording error: {e}")
                break

    def _process(self):
        try:
            if self._thread:
                self._thread.join(timeout=1.5)

            if not self._frames:
                print("[STT] No frames captured.")
                self.on_text("", "en")
                return

            audio = np.concatenate(self._frames, axis=0).flatten()

            text, lang = transcribe(audio)

            if text:
                print(f"[STT] Heard: {text}")
                self.on_text(text, lang)
            else:
                print("[STT] Nothing detected.")
                self.on_text("", "en")

        except Exception as e:
            print(f"[STT] Error: {e}")
            self.on_text("", "en")

    def is_ptt_active(self):
        return self._ptt_active