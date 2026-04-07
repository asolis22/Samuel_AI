import os
import re
import threading
import traceback
from pathlib import Path
import numpy as np
import sounddevice as sd

# --- Paths ---
_THIS_DIR = Path(__file__).resolve().parent
_DATA_DIR = _THIS_DIR.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = str(_DATA_DIR / "kokoro-v1.0.onnx")
VOICES_PATH = str(_DATA_DIR / "voices-v1.0.bin")

SPEAKING_EVENT = threading.Event()
_KOKORO_MODEL = None

def _get_best_output_device():
    """Automatically finds the best working speaker (handles Mac & Pi)."""
    try:
        devices = sd.query_devices()
        # Try the default output first
        default_out = sd.default.device[1]

        if default_out != -1 and devices[default_out]['max_output_channels'] > 0:
            return default_out

        # Fallback: Find the first available output device
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] > 0:
                return i
    except Exception:
        pass
    return None

def _try_init_kokoro():
    global _KOKORO_MODEL
    if _KOKORO_MODEL is not None:
        return True
    try:
        from kokoro_onnx import Kokoro
        if os.path.exists(MODEL_PATH) and os.path.exists(VOICES_PATH):
            _KOKORO_MODEL = Kokoro(MODEL_PATH, VOICES_PATH)
            return True
        else:
            # ── FIX: Print exactly which files are missing so you know what to download
            if not os.path.exists(MODEL_PATH):
                print(f"[TTS] Missing model file: {MODEL_PATH}")
            if not os.path.exists(VOICES_PATH):
                print(f"[TTS] Missing voices file: {VOICES_PATH}")
    except Exception as e:
        print(f"[TTS] Kokoro init failed: {e}")
        traceback.print_exc()
    return False

def _speak_kokoro(text, on_start=None):
    global _KOKORO_MODEL
    try:
        # Generate audio samples
        samples, sample_rate = _KOKORO_MODEL.create(
            text, voice="af_sky", speed=1.0, lang="en-us"
        )

        device_id = _get_best_output_device()
        if device_id is None:
            print("[TTS] No speakers detected!")
            return

        # Trigger the "Speaking" UI state
        if on_start:
            on_start()

        # Play the audio
        sd.play(samples, sample_rate, device=device_id)
        sd.wait()  # Wait until finished speaking

    except Exception as e:
        # ── FIX: Print the full traceback so you can see exactly what Kokoro
        # complained about (version mismatch, bad audio format, missing voice, etc.)
        print(f"[TTS] Audio playback error: {e}")
        traceback.print_exc()
    finally:
        # Reset the flag so Samuel returns to IDLE
        SPEAKING_EVENT.clear()

def speak_async(text, on_start=None, on_done=None):
    """
    The main entry point.
    on_start: called just before audio begins playing (optional).
    on_done:  called after audio finishes or if TTS fails (optional).
    """
    # Clean out performance tags [pause:long] etc for the actual TTS engine
    clean_text = re.sub(r"\[[\w:]+\]\s*", "", text).strip()
    if not clean_text:
        return

    def run():
        SPEAKING_EVENT.set()
        if _try_init_kokoro():
            _speak_kokoro(clean_text, on_start=on_start)
        else:
            print("[TTS] Kokoro model files missing in /data folder.")
            SPEAKING_EVENT.clear()

        # on_done always fires whether audio succeeded or failed,
        # so the GUI always gets a chance to return to idle.
        if on_done:
            on_done()

    threading.Thread(target=run, daemon=True).start()

def stop_audio():
    """Immediately stops any ongoing speech."""
    try:
        sd.stop()
    except Exception:
        pass
    SPEAKING_EVENT.clear()