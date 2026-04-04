# tts_languages.py
from __future__ import annotations
from dataclasses import dataclass
import re

@dataclass(frozen=True)
class VoiceConfig:
    voice: str
    rate: str = "-8%"
    pitch: str = "-3Hz"

# Good “default” voices by language.
# You can expand this list anytime.
VOICE_BY_LANG: dict[str, VoiceConfig] = {
    # English
    "en":    VoiceConfig("en-GB-RyanNeural", rate="-8%", pitch="-3Hz"),  # Alfred-ish
    "en-gb": VoiceConfig("en-GB-RyanNeural", rate="-8%", pitch="-3Hz"),
    "en-us": VoiceConfig("en-US-GuyNeural", rate="-5%", pitch="-1Hz"),

    # Spanish
    "es":    VoiceConfig("es-MX-JorgeNeural", rate="-5%", pitch="+0Hz"),
    "es-mx": VoiceConfig("es-MX-JorgeNeural", rate="-5%", pitch="+0Hz"),
    "es-es": VoiceConfig("es-ES-AlvaroNeural", rate="-5%", pitch="+0Hz"),

    # French
    "fr":    VoiceConfig("fr-FR-HenriNeural", rate="-5%", pitch="+0Hz"),

    # German
    "de":    VoiceConfig("de-DE-ConradNeural", rate="-5%", pitch="+0Hz"),

    # Italian
    "it":    VoiceConfig("it-IT-DiegoNeural", rate="-5%", pitch="+0Hz"),

    # Portuguese
    "pt":    VoiceConfig("pt-BR-AntonioNeural", rate="-5%", pitch="+0Hz"),

    # Japanese
    "ja":    VoiceConfig("ja-JP-KeitaNeural", rate="-5%", pitch="+0Hz"),

    # Korean
    "ko":    VoiceConfig("ko-KR-InJoonNeural", rate="-5%", pitch="+0Hz"),

    # Chinese
    "zh":    VoiceConfig("zh-CN-YunxiNeural", rate="-5%", pitch="+0Hz"),
}

DEFAULT_LANG = "en"

def normalize_lang(lang: str | None) -> str:
    if not lang:
        return DEFAULT_LANG
    lang = lang.strip().lower().replace("_", "-")
    # keep common shapes (en, en-gb, es-mx, etc.)
    return lang

def guess_language(text: str) -> str:
    """
    Lightweight heuristic language guesser (no external deps).
    It's not perfect, but it works well for obvious EN/ES/FR/DE cases.
    If you want perfect detection later, we can add 'langdetect' or fastText.
    """
    t = (text or "").lower()

    # Spanish indicators
    if any(ch in t for ch in "áéíóúñ¿¡"):
        return "es"
    if re.search(r"\b(hola|gracias|por favor|buenos días|buenas|qué|porque|para|pero|también)\b", t):
        return "es"

    # French indicators
    if any(ch in t for ch in "àâçéèêëîïôùûüÿœæ"):
        return "fr"
    if re.search(r"\b(bonjour|merci|s'il vous plaît|pourquoi|parce que|avec|mais)\b", t):
        return "fr"

    # German indicators
    if any(ch in t for ch in "äöüß"):
        return "de"
    if re.search(r"\b(hallo|danke|bitte|weil|aber|und|nicht)\b", t):
        return "de"

    # Default
    return "en"

def pick_voice(text: str, lang: str | None = None) -> VoiceConfig:
    lang = normalize_lang(lang)

    # If lang is "auto", guess from text
    if lang in {"auto", "detect"}:
        lang = guess_language(text)

    # Try exact match first (es-mx), then base (es)
    if lang in VOICE_BY_LANG:
        return VOICE_BY_LANG[lang]

    base = lang.split("-")[0]
    return VOICE_BY_LANG.get(base, VOICE_BY_LANG[DEFAULT_LANG])