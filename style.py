# style.py
# FINAL VERSION — Controlled style, no unconscious mirroring

import re
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------
# CORE STYLE (LOCKED DEFAULT)
# ---------------------------------------------------------------------

@dataclass(frozen=True)
class StyleProfile:
    """
    Samuel's DEFAULT speaking style.
    This does NOT change unless explicitly updated.
    """
    vibe: str = (
        "Modern British butler tone: calm, polite, articulate, quietly warm. "
        "Professional and composed. Expressive through word choice, not punctuation."
    )
    rules: str = (
        "Use clear, complete sentences. No ellipses, no stage directions, "
        "no performative pauses. Slightly formal but never stiff. "
        "Readable, grounded, and respectful."
    )
    temperature: float = 0.6


DEFAULT_STYLE = StyleProfile()


# ---------------------------------------------------------------------
# TEMPORARY CLARITY HINTS (NON-PERSISTENT)
# ---------------------------------------------------------------------

def infer_temporary_clarity_hint(user_text: str) -> Optional[str]:
    """
    Lightweight, NON-PERSISTENT hints to improve clarity or appropriateness.
    These NEVER affect personality, tone, or memory.
    """
    text = user_text.lower()
    hints = []

    # Professional context
    if re.search(r"\bemail\b|\bprofessor\b|\bresume\b|\bapplication\b", text):
        hints.append(
            "Keep wording polished and professional. No emojis or slang."
        )

    # User explicitly asks for simplicity
    if re.search(r"\bbreak it down\b|\bsimple\b|\bexplain\b", text):
        hints.append(
            "Use plain language and short explanations without changing tone."
        )

    # Emotional or stressed language
    if re.search(r"\bstressed\b|\boverwhelmed\b|\bconfused\b", text):
        hints.append(
            "Be reassuring and steady, but do not soften into casual speech."
        )

    return " ".join(hints) if hints else None


# ---------------------------------------------------------------------
# EXPLICIT STYLE OVERRIDE (USER-CONTROLLED)
# ---------------------------------------------------------------------

def explicit_style_override(style_instruction: str) -> StyleProfile:
    """
    Explicit style update requested by the user.
    This should only be called when the user says things like:
    'Remember to speak like this' or 'From now on, use this tone.'
    """
    return StyleProfile(
        vibe=style_instruction,
        rules=DEFAULT_STYLE.rules,
        temperature=DEFAULT_STYLE.temperature
    )