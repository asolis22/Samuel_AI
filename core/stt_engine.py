# stt_engine.py
# Whisper-based Speech-to-Text for Samuel.
# Two modes:
#   1. Push-to-talk  — hold mic button, release to transcribe
#   2. Always-on     — listens for wake word "Hey Samuel" / "Hola Samuel"
#                      then captures the full utterance after it
#
# Runs 100% locally via faster-whisper. No internet required.
# Handles English + Spanish automatically.

import threading
import time
import tempfile
import os
import re
import numpy as np


# -------------------------------------------------------
# CONSTANTS
# -------------------------------------------------------

INPUT_DEVICE   = 2
SAMPLE_RATE    = 16000
CHANNELS       = 1
DTYPE          = "float32"



# Silence threshold — raise if ghost words appear, lower if it misses you
MIN_RMS        = 0.005

# Seconds of silence that ends a phrase
SILENCE_AFTER  = 0.6

# Max seconds to record one utterance
MAX_PHRASE_S   = 4.0

# Chunk size for real-time VAD (voice activity detection)
CHUNK_S        = 0.4

_audio_lock = threading.Lock()

# -------------------------------------------------------
# WHISPER LOADER
# -------------------------------------------------------

_whisper_model = None
_whisper_lock  = threading.Lock()


def _get_whisper():
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model
    with _whisper_lock:
        if _whisper_model is not None:
            return _whisper_model
        try:
            from faster_whisper import WhisperModel
            print("[STT] Loading Whisper model (tiny)...")
            # "small" is fast + accurate enough. "medium" is better but slower.
            _whisper_model = WhisperModel(
                "tiny",
                device="cpu",
                compute_type="int8",
            )
            print("[STT] Whisper ready.")
        except ImportError:
            raise RuntimeError(
                "faster-whisper not installed.\n"
                "Run: pip install faster-whisper"
            )
    return _whisper_model


# -------------------------------------------------------
# TRANSCRIPTION
# -------------------------------------------------------

def transcribe(audio: np.ndarray) -> tuple[str, str]:
    """
    Transcribe a numpy float32 audio array.
    Returns (text, detected_language).
    Handles English + Spanish.
    """
    model = _get_whisper()
'''
    # Write to temp WAV
    import soundfile as sf
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        sf.write(wav_path, audio, SAMPLE_RATE)
        segments, info = model.transcribe(
            wav_path,
            language=None,          # auto-detect EN/ES/etc.
            beam_size=1,
            vad_filter=True,        # built-in VAD — skips silence automatically
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200,
            ),
        )
        text = " ".join(s.text for s in segments).strip()
        lang = info.language or "en"
        return text, lang
    finally:
        try:
            os.remove(wav_path)
        except Exception:
            pass
'''

def _rms(audio: np.ndarray) -> float:
    a = audio.astype(np.float32)
    return float(np.sqrt(np.mean(a * a)))



# -------------------------------------------------------
# AUDIO CAPTURE HELPERS
# -------------------------------------------------------

def _record_until_silence(max_seconds: float = MAX_PHRASE_S) -> np.ndarray:
    """
    Records audio until silence is detected or max_seconds reached.
    Uses chunked capture with real-time VAD.
    """
    import sounddevice as sd

    chunks        = []
    silent_chunks = 0
    chunk_frames  = int(SAMPLE_RATE * CHUNK_S)
    max_chunks    = int(max_seconds / CHUNK_S)
    silence_limit = int(SILENCE_AFTER / CHUNK_S)

    with _audio_lock:
        chunk = sd.rec(chunk_frames, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE,device=INPUT_DEVICE,)
        sd.wait()

    for _ in range(max_chunks):
        chunk = sd.rec(chunk_frames, samplerate=SAMPLE_RATE,
                        channels=CHANNELS, dtype=DTYPE)
        sd.wait()
        chunks.append(chunk)

        if _rms(chunk) < MIN_RMS:
            silent_chunks += 1
            if silent_chunks >= silence_limit and len(chunks) > 3:
                break
        else:
            silent_chunks = 0

    if not chunks:
        return np.zeros((0,), dtype=DTYPE)
    return np.concatenate(chunks, axis=0).flatten()


def _record_fixed(seconds: float) -> np.ndarray:
    """Record exactly N seconds (for push-to-talk held duration)."""
    import sounddevice as sd
    frames = int(SAMPLE_RATE * seconds)
    audio  = sd.rec(frames, samplerate=SAMPLE_RATE,
                     channels=CHANNELS, dtype=DTYPE)
    sd.wait()
    return audio.flatten()


# -------------------------------------------------------
# SPEECH LISTENER CLASS
# -------------------------------------------------------

class SpeechListener:
    """
    Unified STT listener supporting:
    - Always-on wake word detection ("Hey Samuel", "Hola Samuel", etc.)
    - Push-to-talk (call start_ptt() / stop_ptt())
    """

    def __init__(self, on_text, phrase_seconds: float = 4.0,
                 sample_rate: int = SAMPLE_RATE):
        self.on_text       = on_text       # callback(text: str, lang: str)
        self.phrase_seconds = phrase_seconds
        self.sample_rate   = sample_rate

        self._stop_event   = threading.Event()
        self._thread       = None

        # Push-to-talk state
        self._ptt_active   = False
        self._ptt_frames   = []
        self._ptt_thread   = None
        self._ptt_stop     = threading.Event()

        self.mode          = "always_on"   # "always_on" | "push_to_talk"

        # Preload Whisper in background so first use is instant
        threading.Thread(target=_get_whisper, daemon=True).start()

    # ------------------------------------------------------------------
    # ALWAYS-ON MODE
    # ------------------------------------------------------------------
    '''
    def start(self):
        """Start always-on listening (wake word detection)."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.mode    = "always_on"
        self._thread = threading.Thread(target=self._run_always_on, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop always-on listening."""
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run_always_on(self):
        """
        Continuously captures short chunks and checks for wake word.
        When wake word detected, captures the full utterance and fires callback.
        """
        import sounddevice as sd
        chunk_frames = int(SAMPLE_RATE * CHUNK_S)
        print("[STT] Always-on listening started. Say 'Hey Samuel' to activate.")

        with _audio_lock:
            chunk = sd.rec(chunk_frames, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
            sd.wait()

        while not self._stop_event.is_set():
            try:
                # Capture a short chunk
                chunk = sd.rec(
                    chunk_frames,
                    samplerate=SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype=DTYPE
                )
                sd.wait()

                if self._stop_event.is_set():
                    break

                # Skip silence
                if _rms(chunk) < MIN_RMS:
                    time.sleep(0.05)
                    continue

                # Quick transcribe to check for wake word
                text, lang = transcribe(chunk.flatten())
                if not text:
                    continue

                if _is_wake_word(text):
                    print(f"[STT] Wake word detected: '{text}'")

                    # Pause background learning immediately
                    begin_foreground_task()

                    try:
                        # Capture the actual command
                        remaining = _record_until_silence(max_seconds=MAX_PHRASE_S)

                        if _rms(remaining) > MIN_RMS:
                            full_audio = np.concatenate([chunk.flatten(), remaining])
                        else:
                            # Wake word only, no command yet — wait for one more phrase
                            remaining = _record_until_silence(max_seconds=MAX_PHRASE_S)
                            full_audio = remaining

                        if _rms(full_audio) < MIN_RMS:
                            continue

                        final_text, final_lang = transcribe(full_audio)
                        final_text = _strip_wake_word(final_text)

                        if final_text and len(final_text) >= 2:
                            print(f"[STT] Heard ({final_lang}): {final_text}")
                            self.on_text(final_text, final_lang)

                    finally:
                        end_foreground_task()

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[STT] Error: {e}")
                time.sleep(0.2)
         '''   
    # ------------------------------------------------------------------
    # PUSH-TO-TALK MODE
    # ------------------------------------------------------------------

    def start_ptt(self):
        """
        Begin recording for push-to-talk.
        Call this when the user presses the mic button.
        """
        if self._ptt_active:
            return
        
        begin_foreground_task()

        self._ptt_active = True
        self._ptt_stop.clear()
        self._ptt_frames  = []
        self._ptt_thread  = threading.Thread(
            target=self._record_ptt, daemon=True
        )
        self._ptt_thread.start()
        print("[STT] PTT: recording started...")

    def stop_ptt(self):
        """
        Stop recording and transcribe.
        Call this when the user releases the mic button.
        """
        if not self._ptt_active:
            return
        self._ptt_stop.set()
        self._ptt_active = False
        print("[STT] PTT: recording stopped, transcribing...")

        def _transcribe_ptt():
            try:
                if self._ptt_thread:
                    self._ptt_thread.join(timeout=3.0)

                if not self._ptt_frames:
                    return

                audio = np.concatenate(self._ptt_frames, axis=0).flatten()

                if _rms(audio) < MIN_RMS:
                    print("[STT] PTT: too quiet, ignoring.")
                    return

                text, lang = transcribe(audio)

                if text and len(text.strip()) >= 2:
                    print(f"[STT] PTT ({lang}): {text}")
                    self.on_text(text.strip(), lang)

            finally:
                # ▶️ Resume learning AFTER speaking finishes
                end_foreground_task()
        threading.Thread(target=_transcribe_ptt, daemon=True).start()

    def _record_ptt(self):
        """Background thread that captures audio while PTT is held."""
        import sounddevice as sd
        chunk_frames = int(SAMPLE_RATE * CHUNK_S)

        with _audio_lock:
            chunk = sd.rec(chunk_frames, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE)
            sd.wait()

        while not self._ptt_stop.is_set():
            try:
                chunk = sd.rec(chunk_frames, samplerate=SAMPLE_RATE,
                                channels=CHANNELS, dtype=DTYPE)
                sd.wait()
                self._ptt_frames.append(chunk)
            except Exception as e:
                print(f"[STT] PTT record error: {e}")
                break

    def is_ptt_active(self) -> bool:
        return self._ptt_active