# emotion_detector.py
# Detects YOUR emotional state from voice audio + text combined.
# Uses SpeechBrain for voice-based emotion + LLM for text-based emotion.
# Samuel uses this to understand how you're feeling and respond accordingly.
#
# Install: pip install speechbrain torchaudio

import threading
import numpy as np
import time
from typing import Optional, Dict, Callable

# -------------------------------------------------------
# VOICE EMOTION DETECTOR  (SpeechBrain)
# -------------------------------------------------------

_sb_classifier = None
_sb_lock        = threading.Lock()
_sb_failed      = False


def _get_speechbrain():
    global _sb_classifier, _sb_failed
    if _sb_failed:
        return None
    if _sb_classifier is not None:
        return _sb_classifier
    with _sb_lock:
        if _sb_classifier is not None:
            return _sb_classifier
        try:
            from speechbrain.pretrained import EncoderClassifier
            print("[EMOTION] Loading SpeechBrain emotion classifier...")
            _sb_classifier = EncoderClassifier.from_hparams(
                source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
                savedir="pretrained_models/emotion-recognition",
            )
            print("[EMOTION] SpeechBrain ready.")
            return _sb_classifier
        except ImportError:
            print("[EMOTION] SpeechBrain not installed. "
                  "Run: pip install speechbrain torchaudio")
            _sb_failed = True
            return None
        except Exception as e:
            print(f"[EMOTION] SpeechBrain init failed: {e}")
            _sb_failed = True
            return None


# SpeechBrain emotion labels → friendly names
_SB_LABEL_MAP = {
    "ang": "angry",
    "hap": "happy",
    "sad": "sad",
    "neu": "neutral",
    "fea": "fearful",
    "dis": "disgusted",
    "sur": "surprised",
    "exc": "excited",
}


def detect_voice_emotion(audio: np.ndarray,
                          sample_rate: int = 16000) -> Optional[Dict]:
    """
    Detect emotion from audio array.
    Returns dict: {emotion, confidence, raw_scores}
    """
    classifier = _get_speechbrain()
    if not classifier:
        return _acoustic_fallback(audio, sample_rate)

    try:
        import torch
        import torchaudio

        # Convert to tensor
        waveform = torch.tensor(audio).unsqueeze(0).float()

        # Resample if needed
        if sample_rate != 16000:
            waveform = torchaudio.functional.resample(
                waveform, sample_rate, 16000
            )

        out_prob, score, index, text_lab = classifier.classify_batch(waveform)
        label    = text_lab[0] if text_lab else "neu"
        emotion  = _SB_LABEL_MAP.get(label, label)
        confidence = float(score[0]) if score is not None else 0.5

        return {
            "emotion":    emotion,
            "confidence": confidence,
            "source":     "speechbrain",
        }
    except Exception as e:
        print(f"[EMOTION] Voice detection error: {e}")
        return _acoustic_fallback(audio, sample_rate)


def _acoustic_fallback(audio: np.ndarray,
                        sample_rate: int = 16000) -> Dict:
    """
    Lightweight acoustic feature fallback when SpeechBrain unavailable.
    Uses RMS energy, zero-crossing rate, and pitch variation to estimate emotion.
    """
    if len(audio) == 0:
        return {"emotion": "neutral", "confidence": 0.3, "source": "acoustic"}

    audio = audio.astype(np.float32)

    # RMS energy
    rms = float(np.sqrt(np.mean(audio ** 2)))

    # Zero-crossing rate (proxy for brightness/excitement)
    signs    = np.sign(audio)
    zcr      = float(np.sum(np.abs(np.diff(signs))) / (2 * len(audio)))

    # Pitch variation (std of short-term energy)
    frame_size = sample_rate // 10
    frames     = [audio[i:i+frame_size] for i in
                  range(0, len(audio) - frame_size, frame_size)]
    energies   = [float(np.sqrt(np.mean(f**2))) for f in frames if len(f) > 0]
    energy_std = float(np.std(energies)) if energies else 0.0

    # Simple rule-based mapping
    if rms < 0.015:
        emotion = "neutral"
    elif rms > 0.12 and zcr > 0.15:
        emotion = "excited" if energy_std > 0.02 else "angry"
    elif rms > 0.08 and energy_std > 0.025:
        emotion = "excited"
    elif zcr < 0.05 and rms < 0.05:
        emotion = "sad"
    elif energy_std < 0.01 and rms > 0.04:
        emotion = "neutral"
    else:
        emotion = "neutral"

    return {
        "emotion":    emotion,
        "confidence": 0.55,
        "source":     "acoustic",
        "rms":        rms,
        "zcr":        zcr,
    }


# -------------------------------------------------------
# TEXT EMOTION DETECTOR
# -------------------------------------------------------

# Simple lexicon-based — no LLM call needed, instant
_EMOTION_LEXICON = {
    "excited":   ["excited", "amazing", "omg", "wow", "yes!", "love", "awesome",
                  "incredible", "finally", "yes yes", "can't wait"],
    "happy":     ["happy", "great", "good", "nice", "glad", "pleased", "yay",
                  "haha", "lol", "fun", "thanks", "thank you"],
    "sad":       ["sad", "upset", "crying", "miss", "lonely", "depressed",
                  "heartbroken", "disappointed", "unfortunate", "hurt"],
    "angry":     ["angry", "annoyed", "frustrated", "ugh", "hate", "terrible",
                  "awful", "ridiculous", "stupid", "furious", "mad"],
    "anxious":   ["worried", "nervous", "anxious", "scared", "afraid", "stress",
                  "stressed", "overwhelmed", "panic", "help"],
    "curious":   ["how", "why", "what", "wonder", "interesting", "explain",
                  "tell me", "curious", "question", "?"],
    "tired":     ["tired", "exhausted", "sleepy", "can't sleep", "haven't slept",
                  "worn out", "drained"],
    "neutral":   [],
}


def detect_text_emotion(text: str) -> Dict:
    """Detect emotion from text using lexicon matching."""
    t      = text.lower()
    scores = {e: 0 for e in _EMOTION_LEXICON}

    for emotion, words in _EMOTION_LEXICON.items():
        for w in words:
            if w in t:
                scores[emotion] += 1

    best       = max(scores, key=scores.get)
    best_score = scores[best]

    if best_score == 0:
        return {"emotion": "neutral", "confidence": 0.4, "source": "text"}

    total      = sum(scores.values()) or 1
    confidence = min(0.95, best_score / total + 0.3)

    return {
        "emotion":    best,
        "confidence": confidence,
        "source":     "text",
        "scores":     scores,
    }


# -------------------------------------------------------
# COMBINED DETECTOR
# -------------------------------------------------------

# Maps detected user emotion → Samuel's suggested response emotion
_RESPONSE_EMOTION_MAP = {
    "excited":  ["happy", "amused", "excited"],
    "happy":    ["happy", "amused", "confident"],
    "sad":      ["concerned", "soft", "gentle"],
    "angry":    ["concerned", "firm", "calm"],
    "anxious":  ["concerned", "soft", "reassuring"],
    "curious":  ["curious", "confident", "thoughtful"],
    "tired":    ["concerned", "soft", "gentle"],
    "neutral":  ["neutral", "confident"],
    "fearful":  ["concerned", "soft"],
    "surprised":["surprised", "curious"],
    "disgusted":["hmph", "concerned"],
}


def combine_emotions(voice_result: Optional[Dict],
                     text_result: Dict) -> Dict:
    """
    Merge voice + text emotion signals into a final reading.
    Voice has higher weight if confidence is high.
    """
    if not voice_result:
        return text_result

    v_conf = voice_result.get("confidence", 0)
    t_conf = text_result.get("confidence", 0)

    # Weight by confidence
    if v_conf > 0.7:
        primary = voice_result["emotion"]
        confidence = v_conf
    elif t_conf > 0.6:
        primary = text_result["emotion"]
        confidence = t_conf
    else:
        # Blend: if they agree, boost confidence
        if voice_result["emotion"] == text_result["emotion"]:
            primary    = voice_result["emotion"]
            confidence = min(0.95, (v_conf + t_conf) / 2 + 0.15)
        else:
            # Disagree — trust voice slightly more
            primary    = voice_result["emotion"] if v_conf >= t_conf else text_result["emotion"]
            confidence = max(v_conf, t_conf)

    return {
        "emotion":    primary,
        "confidence": round(confidence, 2),
        "source":     "combined",
        "voice":      voice_result,
        "text":       text_result,
    }


def get_samuel_response_mood(user_emotion: str) -> str:
    """
    Given the user's detected emotion, suggest Samuel's response expression.
    """
    import random
    options = _RESPONSE_EMOTION_MAP.get(user_emotion,
                                         _RESPONSE_EMOTION_MAP["neutral"])
    return random.choice(options)


# -------------------------------------------------------
# REAL-TIME EMOTION MONITOR
# -------------------------------------------------------

class EmotionMonitor:
    """
    Continuously monitors mic audio and estimates emotional state.
    Fires callback when emotion changes significantly.
    """

    def __init__(self,
                 on_emotion_change: Optional[Callable[[Dict], None]] = None,
                 sample_rate: int = 16000,
                 window_seconds: float = 2.0):
        self.on_emotion_change = on_emotion_change
        self.sample_rate       = sample_rate
        self.window_seconds    = window_seconds
        self._running          = False
        self._thread           = None
        self._last_emotion     = "neutral"
        self.current           = {
            "emotion": "neutral", "confidence": 0.5, "source": "init"
        }

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def update_text(self, text: str):
        """Call this with the user's typed/spoken text for text emotion."""
        result = detect_text_emotion(text)
        combined = combine_emotions(
            self.current if self.current.get("source") != "init" else None,
            result
        )
        self.current = combined
        if (combined["emotion"] != self._last_emotion and
                combined["confidence"] > 0.5):
            self._last_emotion = combined["emotion"]
            if self.on_emotion_change:
                self.on_emotion_change(combined)

    def _run(self):
        try:
            import sounddevice as sd
            frames = int(self.sample_rate * self.window_seconds)

            while self._running:
                try:
                    audio = sd.rec(frames, samplerate=self.sample_rate,
                                   channels=1, dtype="float32")
                    sd.wait()
                    flat = audio.flatten()

                    # Skip silence
                    rms = float(np.sqrt(np.mean(flat ** 2)))
                    if rms < 0.008:
                        time.sleep(0.1)
                        continue

                    result   = detect_voice_emotion(flat, self.sample_rate)
                    combined = combine_emotions(result,
                                               detect_text_emotion(""))
                    self.current = combined

                    if (combined["emotion"] != self._last_emotion and
                            combined["confidence"] > 0.55):
                        self._last_emotion = combined["emotion"]
                        if self.on_emotion_change:
                            self.on_emotion_change(combined)

                except Exception:
                    time.sleep(0.2)

        except ImportError:
            print("[EMOTION] sounddevice not available for real-time monitoring")
