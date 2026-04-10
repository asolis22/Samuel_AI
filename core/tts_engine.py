import re
import io
import wave
import threading
import traceback
from pathlib import Path
import numpy as np
import sounddevice as sd

# --- Paths ---
_THIS_DIR = Path(__file__).resolve().parent
_DATA_DIR = _THIS_DIR.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Piper model — place both .onnx and .onnx.json in the data/ folder.
# Current voice: en_GB-alan-medium (British male, warm)
MODEL_PATH = str(_DATA_DIR / "en_GB-alan-medium.onnx")

SPEAKING_EVENT = threading.Event()
_PIPER_VOICE = None


def _get_best_output_device():
    """Automatically finds the best working speaker (handles Mac & Pi)."""
    try:
        devices = sd.query_devices()
        default_out = sd.default.device[1]
        if default_out != -1 and devices[default_out]['max_output_channels'] > 0:
            return default_out
        for i, dev in enumerate(devices):
            if dev['max_output_channels'] > 0:
                return i
    except Exception:
        pass
    return None


def _try_init_piper():
    """Load the Piper voice model. Returns True on success."""
    global _PIPER_VOICE
    if _PIPER_VOICE is not None:
        return True
    try:
        from piper.voice import PiperVoice
        json_path = MODEL_PATH + ".json"
        if not Path(MODEL_PATH).exists():
            print(f"[TTS] Missing Piper model: {MODEL_PATH}")
            print("[TTS] Download from: https://piper.ttstool.com")
            return False
        if not Path(json_path).exists():
            print(f"[TTS] Missing Piper config: {json_path}")
            print("[TTS] Make sure the .onnx.json file is next to the .onnx file.")
            return False
        print(f"[TTS] Loading Piper voice: {MODEL_PATH}")
        _PIPER_VOICE = PiperVoice.load(MODEL_PATH, config_path=json_path)
        print("[TTS] Piper ready.")
        return True
    except ImportError:
        print("[TTS] piper-tts not installed. Run: pip install piper-tts")
        traceback.print_exc()
    except Exception as e:
        print(f"[TTS] Piper init failed: {e}")
        traceback.print_exc()
    return False


def _speak_piper(text, on_start=None):
    """
    Synthesize audio with Piper and play via sounddevice.
    synthesize_wav needs a wave.Wave_write object, so we wrap a BytesIO in one.
    on_start fires just before playback begins.
    """
    global _PIPER_VOICE
    try:
        device_id = _get_best_output_device()
        if device_id is None:
            print("[TTS] No speakers detected!")
            if on_start:
                on_start()
            return

        print("[TTS] Synthesizing with Piper...")

        # Wrap BytesIO in a proper wave.Wave_write object — this is what Piper expects
        raw_buffer = io.BytesIO()
        with wave.open(raw_buffer, 'wb') as wav_writer:
            _PIPER_VOICE.synthesize_wav(text, wav_writer)

        # Now read the PCM back out
        raw_buffer.seek(0)
        with wave.open(raw_buffer, 'rb') as wav_reader:
            n_channels = wav_reader.getnchannels()
            framerate  = wav_reader.getframerate()
            raw_frames = wav_reader.readframes(wav_reader.getnframes())

        audio = np.frombuffer(raw_frames, dtype=np.int16)

        # Mix stereo down to mono if needed
        if n_channels == 2:
            audio = audio.reshape(-1, 2).mean(axis=1).astype(np.int16)

        print(f"[TTS] Playing {len(audio)} samples at {framerate}Hz on device {device_id}...")

        # Fire on_start just before audio plays so caption appears in sync
        if on_start:
            on_start()

        sd.play(audio, framerate, device=device_id)
        sd.wait()
        print("[TTS] Playback finished.")

    except Exception as e:
        print(f"[TTS] Piper playback error: {e}")
        traceback.print_exc()
        if on_start:
            on_start()
    finally:
        SPEAKING_EVENT.clear()


def speak_async(text, on_start=None, on_done=None):
    """
    Main TTS entry point.
    on_start : fires just before audio plays — shows caption + switches to Speaking.
    on_done  : fires after audio finishes OR on failure — returns Samuel to idle.
    """
    clean_text = re.sub(r"\[[\w:]+\]\s*", "", text).strip()
    if not clean_text:
        return

    def run():
        SPEAKING_EVENT.set()
        if _try_init_piper():
            _speak_piper(clean_text, on_start=on_start)
        else:
            print("[TTS] Piper unavailable — showing caption without audio.")
            SPEAKING_EVENT.clear()
            if on_start:
                on_start()

        # on_done always fires so the GUI never gets stuck on SPEAKING
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