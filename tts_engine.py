# tts_engine.py
# TTS for Samuel. Tries Kokoro first, falls back to macOS say, then silent.
# Kokoro needs two model files — auto-downloads if missing.

import os, re, threading, queue, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SPEAKING_EVENT = threading.Event()

# ── Performance script tags ────────────────────────────────────────────
# [pause:beat] [pause:short] [pause:long]
# [voice:soft] [voice:excited] [voice:slow] [voice:firm] [voice:normal]
# [expression:happy] etc.

_PAUSE_TIMES = {"beat": 0.25, "short": 0.5, "medium": 0.9, "long": 1.4}


def strip_performance_tags(text: str) -> str:
    return re.sub(r"\[[\w:]+\]\s*", "", text).strip()


def parse_performance_script(script: str):
    """Split script into list of action dicts."""
    tokens = re.split(r"(\[[\w:]+\])", script)
    actions = []
    pending_text = ""
    for tok in tokens:
        m = re.match(r"\[([\w]+)(?::([\w]+))?\]", tok)
        if m:
            if pending_text.strip():
                actions.append({"type": "speak", "text": pending_text.strip()})
                pending_text = ""
            kind, val = m.group(1), m.group(2) or ""
            if kind == "pause":
                actions.append({"type": "pause", "duration": _PAUSE_TIMES.get(val, 0.4)})
            elif kind == "voice":
                actions.append({"type": "voice_style", "style": val})
            elif kind == "expression":
                actions.append({"type": "expression", "name": val})
        else:
            pending_text += tok
    if pending_text.strip():
        actions.append({"type": "speak", "text": pending_text.strip()})
    return actions


# ── Kokoro engine ──────────────────────────────────────────────────────

_kokoro = None
_kokoro_lock = threading.Lock()
_USE_KOKORO = False

def _try_init_kokoro():
    global _kokoro, _USE_KOKORO
    with _kokoro_lock:
        if _kokoro is not None:
            return _USE_KOKORO
        try:
            from kokoro_onnx import Kokoro
            model_path  = os.path.join(BASE_DIR, "kokoro-v1.0.onnx")
            voices_path = os.path.join(BASE_DIR, "voices-v1.0.bin")

            # Auto-download model files if missing
            if not os.path.exists(model_path) or not os.path.exists(voices_path):
                print("[TTS] Kokoro model files missing — downloading...")
                _download_kokoro_models(model_path, voices_path)

            print("[TTS] Loading Kokoro model...")
            _kokoro = Kokoro(model_path, voices_path)
            _USE_KOKORO = True
            print("[TTS] Kokoro ready.")
        except Exception as e:
            print(f"[TTS] Kokoro unavailable: {e}")
            _kokoro = False
            _USE_KOKORO = False
        return _USE_KOKORO


def _download_kokoro_models(model_path, voices_path):
    """Download Kokoro model files using urllib (no requests needed)."""
    import urllib.request
    base_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
    files = [
        (model_path,  base_url + "kokoro-v1.0.onnx"),
        (voices_path, base_url + "voices-v1.0.bin"),
    ]
    for path, url in files:
        if not os.path.exists(path):
            print(f"[TTS] Downloading {os.path.basename(path)}...")
            try:
                urllib.request.urlretrieve(url, path)
                print(f"[TTS] Downloaded {os.path.basename(path)}")
            except Exception as e:
                print(f"[TTS] Download failed for {os.path.basename(path)}: {e}")


def _speak_kokoro(text: str, voice: str = "bm_george", speed: float = 1.0):
    global _kokoro
    try:
        import numpy as np
        import sounddevice as sd

        samples, sr = _kokoro.create(text, voice=voice, speed=speed)

        # --- sanitize audio for PortAudio/CoreAudio ---
        samples = np.asarray(samples, dtype=np.float32)

        # ensure mono (1D) or (N,1)
        if samples.ndim == 2 and samples.shape[1] > 1:
            samples = samples.mean(axis=1)
        samples = samples.flatten()

        # resample to a "safe" macOS rate if needed
        target_sr = 44100
        if sr not in (44100, 48000):
            x_old = np.linspace(0.0, 1.0, num=len(samples), endpoint=False)
            new_len = int(len(samples) * (target_sr / float(sr)))
            x_new = np.linspace(0.0, 1.0, num=new_len, endpoint=False)
            samples = np.interp(x_new, x_old, samples).astype(np.float32)
            sr = target_sr

        SPEAKING_EVENT.set()
        sd.play(samples, sr)
        sd.wait()

    except Exception as e:
        print(f"[TTS] Kokoro speak error: {e}")
        _speak_macos(text)
    finally:
        SPEAKING_EVENT.clear()


# ── macOS fallback ─────────────────────────────────────────────────────

def _speak_macos(text: str):
    """Use macOS built-in 'say' command — always available, no install needed."""
    clean = strip_performance_tags(text)
    clean = re.sub(r'[^\w\s.,!?\'"-]', '', clean)
    if not clean.strip():
        return
    SPEAKING_EVENT.set()
    try:
        import subprocess
        # Daniel is a good British male voice on macOS
        subprocess.run(["say", "-v", "Daniel", clean],
                       capture_output=True, timeout=60)
    except Exception as e:
        print(f"[TTS] macOS say failed: {e}")
    finally:
        SPEAKING_EVENT.clear()


# ── Voice style → speed/voice mapping ─────────────────────────────────

_STYLE_PARAMS = {
    "soft":    {"speed": 0.90},
    "excited": {"speed": 1.15},
    "slow":    {"speed": 0.80},
    "firm":    {"speed": 1.00},
    "whisper": {"speed": 0.85},
    "normal":  {"speed": 1.00},
}


# ── Script executor ────────────────────────────────────────────────────

class ScriptExecutor:
    def __init__(self, on_expression=None):
        self.on_expression = on_expression
        self._style = "normal"

    def run(self, script: str):
        actions = parse_performance_script(script)
        for action in actions:
            t = action["type"]
            if t == "speak":
                text = action["text"]
                speed = _STYLE_PARAMS.get(self._style, {}).get("speed", 1.0)
                if _try_init_kokoro():
                    _speak_kokoro(text, speed=speed)
                else:
                    _speak_macos(text)
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

_speak_queue  = queue.Queue()
_speak_thread = None
_stop_event   = threading.Event()


def _worker():
    while True:
        item = _speak_queue.get()
        if item is None:
            break
        script, callback = item
        try:
            executor = ScriptExecutor(on_expression=callback)
            executor.run(script)
        except Exception as e:
            print(f"[TTS] Worker error: {e}")
        _speak_queue.task_done()


def _ensure_worker():
    global _speak_thread
    if _speak_thread is None or not _speak_thread.is_alive():
        _speak_thread = threading.Thread(target=_worker, daemon=True)
        _speak_thread.start()


def speak_async(script: str, on_expression=None):
    """Queue a script for async speech."""
    _ensure_worker()
    _speak_queue.put((script, on_expression))


def stop_speaking():
    """Clear the queue and stop current speech."""
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
    """Speak immediately (blocking, no queue)."""
    if _try_init_kokoro():
        _speak_kokoro(text)
    else:
        _speak_macos(text)


# ── Performance script generator ──────────────────────────────────────

_PERF_SYSTEM = """You are Samuel's performance director. 
Convert the plain response into a performance script using these tags:
[pause:beat] = 0.25s pause, [pause:short] = 0.5s, [pause:long] = 1.4s
[voice:soft] [voice:excited] [voice:slow] [voice:firm] [voice:normal]
[expression:happy] [expression:curious] [expression:amused] [expression:confident]
[expression:concerned] [expression:surprised] [expression:thinking] [expression:neutral]

Rules:
- Add natural pauses between sentences
- Change voice style to match tone
- Add expression tags where emotional tone shifts
- Keep the actual words IDENTICAL — only add tags between phrases
- Output the script only, no explanation"""


def generate_performance_script(response: str, llm_fn) -> str:
    """Ask LLM to add performance tags to Samuel's response."""
    try:
        result = llm_fn([
            {"role": "system", "content": _PERF_SYSTEM},
            {"role": "user",   "content": response},
        ], temperature=0.3)
        if result and len(result) > 10:
            return result
    except Exception as e:
        print(f"[TTS] Script generation failed: {e}")
    return response