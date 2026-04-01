# tts_engine.py (edge-tts + multi-language)
import os
import asyncio
import tempfile
import threading

from playsound import playsound
import edge_tts

import queue
import threading


from tts_languages import pick_voice

SPEAKING_EVENT = threading.Event()

def _speak_edge(text: str, lang: str | None = "auto"):
    text = (text or "").strip()
    if not text:
        return

    cfg = pick_voice(text, lang=lang)

    async def _run():
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
            out_path = f.name

        communicate = edge_tts.Communicate(text, cfg.voice, rate=cfg.rate, pitch=cfg.pitch)
        await communicate.save(out_path)

        try:
            playsound(out_path)
        finally:
            try:
                os.remove(out_path)
            except Exception:
                pass

    asyncio.run(_run())

def speak(text: str, lang: str | None = "auto"):
    cleaned = (text or "").replace("**", "").replace("*", "").strip()
    if not cleaned:
        return

    SPEAKING_EVENT.set()
    try:
        _speak_edge(cleaned, lang=lang)
    finally:
        SPEAKING_EVENT.clear()

TTS_QUEUE = queue.Queue()
_TTS_WORKER_STARTED = False
_TTS_LOCK = threading.Lock()

def _tts_worker():
    while True:
        text = TTS_QUEUE.get()
        try:
            speak(text)  # speak() is blocking (good)
        except Exception:
            pass
        finally:
            TTS_QUEUE.task_done()

def speak_async(text: str):
    global _TTS_WORKER_STARTED
    text = (text or "").strip()
    if not text:
        return

    with _TTS_LOCK:
        if not _TTS_WORKER_STARTED:
            threading.Thread(target=_tts_worker, daemon=True).start()
            _TTS_WORKER_STARTED = True

    # enqueue (so it waits its turn)
    TTS_QUEUE.put(text)