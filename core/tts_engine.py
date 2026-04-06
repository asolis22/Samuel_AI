# tts_engine.py
# TTS for Samuel. Uses Kokoro (high quality British voice) with macOS say fallback.
# Model files live in Samuel_AI/data/
# voices-v1.0.bin  — upload manually (you have this)
# kokoro-v1.0.onnx — auto-downloads if missing (~85MB)

import os
import re
import threading
import queue
import time
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
# This file is at Samuel_AI/core/tts_engine.py
# Data folder is at Samuel_AI/data/
_THIS_DIR = Path(__file__).resolve().parent          # Samuel_AI/core/
_DATA_DIR = _THIS_DIR.parent / "data"                # Samuel_AI/data/
_DATA_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = str(_DATA_DIR / "kokoro-v1.0.onnx")
VOICES_PATH = str(_DATA_DIR / "voices-v1.0.bin")

SPEAKING_EVENT = threading.Event()

_PAUSE_TIMES = {"beat": 0.25, "short": 0.5, "medium": 0.9, "long": 1.4}


# ── Performance script helpers ─────────────────────────────────────────

def strip_performance_tags(text: str) -> str:
    return re.sub(r"\[[\w:]+\]\s*", "", text).strip()


def parse_performance_script(script: str):
    tokens = re.split(r"(\[[\w:]+\])", script)
    actions = []
    pending = ""

    for tok in tokens:
        m = re.match(r"\[([\w]+)(?::([\w]+))?\]", tok)
        if m:
            if pending.strip():
                actions.append({"type": "speak", "text": pending.strip()})
                pending = ""
            kind, val = m.group(1), m.group(2) or ""
            if kind == "pause":
                actions.append({"type": "pause", "duration": _PAUSE_TIMES.get(val, 0.4)})
            elif kind == "voice":
                actions.append({"type": "voice_style", "style": val})
            elif kind == "expression":
                actions.append({"type": "expression", "name": val})
        else:
            pending += tok

    if pending.strip():
        actions.append({"type": "speak", "text": pending.strip()})

    return actions


# ── Kokoro ─────────────────────────────────────────────────────────────

_kokoro = None
_kokoro_lock = threading.Lock()
_USE_KOKORO = False


def _download_if_missing():
    """Download kokoro-v1.0.onnx if not present. voices-v1.0.bin must be placed manually."""
    base_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"

    if not os.path.exists(MODEL_PATH):
        print(f"[TTS] Downloading kokoro-v1.0.onnx to {_DATA_DIR} ...")
        try:
            import urllib.request
            urllib.request.urlretrieve(base_url + "kokoro-v1.0.onnx", MODEL_PATH)
            print("[TTS] kokoro-v1.0.onnx downloaded.")
        except Exception as e:
            print(f"[TTS] Download failed: {e}")

    if not os.path.exists(VOICES_PATH):
        print(f"[TTS] voices-v1.0.bin not found at {VOICES_PATH}")
        print("[TTS] Please copy voices-v1.0.bin into Samuel_AI/data/")


def _try_init_kokoro() -> bool:
    global _kokoro, _USE_KOKORO
    with _kokoro_lock:
        if _kokoro is not None:
            return _USE_KOKORO
        try:
            _download_if_missing()

            if not os.path.exists(MODEL_PATH):
                raise FileNotFoundError(f"kokoro-v1.0.onnx not found at {MODEL_PATH}")
            if not os.path.exists(VOICES_PATH):
                raise FileNotFoundError(f"voices-v1.0.bin not found at {VOICES_PATH}")

            from kokoro_onnx import Kokoro
            print(f"[TTS] Loading Kokoro from {_DATA_DIR} ...")
            _kokoro = Kokoro(MODEL_PATH, VOICES_PATH)
            _USE_KOKORO = True
            print("[TTS] Kokoro ready. Voice: bm_george (British male)")
        except Exception as e:
            print(f"[TTS] Kokoro unavailable: {e}")
            print("[TTS] Falling back to macOS say command.")
            _kokoro = False
            _USE_KOKORO = False
        return _USE_KOKORO


def _speak_kokoro(text: str, voice: str = "bm_george", speed: float = 1.0, on_start=None):
    try:
        import numpy as np
        import sounddevice as sd

        samples, sr = _kokoro.create(text, voice=voice, speed=speed)
        samples = np.asarray(samples, dtype=np.float32)

        if samples.ndim == 2 and samples.shape[1] > 1:
            samples = samples.mean(axis=1)
        samples = samples.flatten()

        # Resample to 44100 if needed (macOS PortAudio is happiest here)
        if sr not in (44100, 48000):
            target = 44100
            x_old = np.linspace(0.0, 1.0, len(samples), endpoint=False)
            x_new = np.linspace(0.0, 1.0, int(len(samples) * target / sr), endpoint=False)
            samples = np.interp(x_new, x_old, samples).astype(np.float32)
            sr = target

        SPEAKING_EVENT.set()

        if on_start:
            try:
                on_start()
            except Exception:
                pass

        sd.play(samples, sr)
        sd.wait()

    except Exception as e:
        print(f"[TTS] Kokoro speak error: {e}")
        _speak_macos(text, on_start=on_start)
    finally:
        SPEAKING_EVENT.clear()


# ── macOS say fallback ─────────────────────────────────────────────────

def _speak_macos(text: str, on_start=None):
    clean = strip_performance_tags(text)
    clean = re.sub(r"[\x00-\x1f\x7f]", "", clean).strip()
    if not clean:
        return

    SPEAKING_EVENT.set()
    try:
        import subprocess
        import shutil

        if not shutil.which("say"):
            print("[TTS] say command not found — is this macOS?")
            return

        if on_start:
            try:
                on_start()
            except Exception:
                pass

        r = subprocess.run(["say", "-v", "Daniel", clean], timeout=120)
        if r.returncode != 0:
            subprocess.run(["say", clean], timeout=120)

    except subprocess.TimeoutExpired:
        print("[TTS] say timed out")
    except Exception as e:
        print(f"[TTS] macOS say failed: {e}")
    finally:
        SPEAKING_EVENT.clear()


# ── Voice style params ─────────────────────────────────────────────────

_STYLE_PARAMS = {
    "soft": {"speed": 0.90},
    "excited": {"speed": 1.15},
    "slow": {"speed": 0.80},
    "firm": {"speed": 1.00},
    "whisper": {"speed": 0.85},
    "normal": {"speed": 1.00},
}


# ── Script executor ────────────────────────────────────────────────────

class ScriptExecutor:
    def __init__(self, on_expression=None, on_start=None):
        self.on_expression = on_expression
        self.on_start = on_start
        self._style = "normal"
        self._started = False

    def _fire_start_once(self):
        if not self._started and self.on_start:
            self._started = True
            try:
                self.on_start()
            except Exception:
                pass

    def run(self, script: str):
        for action in parse_performance_script(script):
            t = action["type"]

            if t == "speak":
                speed = _STYLE_PARAMS.get(self._style, {}).get("speed", 1.0)

                def _start_once():
                    self._fire_start_once()

                if _try_init_kokoro():
                    _speak_kokoro(action["text"], speed=speed, on_start=_start_once)
                else:
                    _speak_macos(action["text"], on_start=_start_once)

            elif t == "pause":
                time.sleep(action["duration"])

            elif t == "voice_style":
                self._style = action["style"]

            elif t == "expression":
                if self.on_expression:
                    try:
                        self.on_expression(action["name"])
                    except Exception:
                        pass


# ── Async queue ────────────────────────────────────────────────────────

_speak_queue = queue.Queue()
_speak_thread = None


def _worker():
    while True:
        item = _speak_queue.get()
        if item is None:
            break

        script, expr_callback, start_callback, done_callback = item

        try:
            print(f"[TTS] Speaking: {script[:60]}...")
            ScriptExecutor(
                on_expression=expr_callback,
                on_start=start_callback,
            ).run(script)
            print("[TTS] Done speaking")

        except Exception as e:
            import traceback
            print(f"[TTS] Worker error: {e}")
            traceback.print_exc()
            try:
                _speak_macos(strip_performance_tags(script), on_start=start_callback)
            except Exception as e2:
                print(f"[TTS] macOS fallback also failed: {e2}")

        finally:
            if done_callback:
                try:
                    done_callback()
                except Exception:
                    pass

        _speak_queue.task_done()


def _ensure_worker():
    global _speak_thread
    if _speak_thread is None or not _speak_thread.is_alive():
        _speak_thread = threading.Thread(target=_worker, daemon=True)
        _speak_thread.start()


def speak_async(script: str, on_expression=None, on_start=None, on_done=None):
    """Queue text/script for async speech. Safe to call from any thread."""
    _ensure_worker()

    parts = re.split(r"(?<=[.!?])\s+", script.strip())
    parts = [p.strip() for p in parts if p.strip()]

    if not parts:
        return

    first = True
    for i, part in enumerate(parts):
        start_cb = on_start if first else None
        done_cb = on_done if i == len(parts) - 1 else None
        _speak_queue.put((part, on_expression, start_cb, done_cb))
        first = False


def stop_speaking():
    while not _speak_queue.empty():
        try:
            _speak_queue.get_nowait()
        except Exception:
            pass
    try:
        import sounddevice as sd
        sd.stop()
    except Exception:
        pass
    SPEAKING_EVENT.clear()


def speak_now(text: str):
    """Speak immediately, blocking."""
    if _try_init_kokoro():
        _speak_kokoro(text)
    else:
        _speak_macos(text)


# ── Pre-warm Kokoro in background at import time ───────────────────────
threading.Thread(target=_try_init_kokoro, daemon=True).start()


# ── Performance script generator ──────────────────────────────────────

_PERF_SYSTEM = """You are Samuel's performance director.
Convert the plain response into a performance script using these tags:
[pause:beat]=0.25s  [pause:short]=0.5s  [pause:long]=1.4s
[voice:soft] [voice:excited] [voice:slow] [voice:firm] [voice:normal]
[expression:happy] [expression:curious] [expression:amused] [expression:confident]
[expression:concerned] [expression:surprised] [expression:thinking] [expression:neutral]

Rules:
- Add natural pauses between sentences
- Change voice style to match emotional tone
- Add expression tags where tone shifts
- Keep the actual words IDENTICAL — only add tags between phrases
- Output the script only, no explanation"""


def generate_performance_script(response: str, llm_fn) -> str:
    try:
        result = llm_fn([
            {"role": "system", "content": _PERF_SYSTEM},
            {"role": "user", "content": response},
        ])
        return (result or "").strip() or response
    except Exception:
        return response