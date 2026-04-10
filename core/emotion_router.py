# emotion_router.py
# Detects USER emotion using enriched keyword rules drawn from GoEmotions labels.
# All 28 GoEmotions categories are covered — no model loading, instant, Pi-friendly.
# High-confidence labels from GoEmotions (gratitude F1=0.92, love F1=0.81, etc.)
# are given priority. Rarer labels (grief, relief, pride) use sensitive patterns.
#
# Also includes detect_samuel_reaction() — reads social context directed AT Samuel
# and returns an appropriate self-reaction expression (shame, pleased, incredulous, etc.)

from __future__ import annotations
import os, re
from dataclasses import dataclass
from typing import List, Tuple, Optional
from pathlib import Path


@dataclass
class EmotionSignal:
    labels:         List[Tuple[str, float]]
    primary:        str        # detected USER emotion
    eye_expression: str        # SAMUEL'S reaction expression
    reply_style:    str
    system_hint:    str


# ── GoEmotions-informed keyword rules ─────────────────────────────────
_RULES: List[Tuple[str, float, List[str]]] = [

    # ── F1 > 0.80 — very reliable labels ──────────────────────────

    ("gratitude", 0.92, [
        r"\bthank you\b", r"\bthanks\b", r"\bthank u\b", r"\bso grateful\b",
        r"\bi appreciate\b", r"\bappreciate you\b", r"\bappreciate it\b",
        r"\bblessed\b", r"\bgod is good\b", r"\bthankful\b",
    ]),
    ("love", 0.81, [
        r"\bi love\b", r"\bso sweet\b", r"\baww\b", r"\byou're amazing\b",
        r"\byou are amazing\b", r"\bthis is so cute\b", r"\badore\b",
        r"\bi care about\b", r"\bmy favorite\b",
    ]),
    ("amusement", 0.83, [
        r"\bhaha\b", r"\blol\b", r"\blmao\b", r"\blmfao\b", r"\bso funny\b",
        r"\bthat's hilarious\b", r"\bdead\b", r"\bi'm crying\b", r"\bim crying\b",
        r"\bthis is so funny\b", r"\bromfl\b", r"\bkekw\b",
    ]),

    # ── F1 0.60-0.80 — reliable ────────────────────────────────────

    ("joy", 0.63, [
        r"\bso happy\b", r"\bim happy\b", r"\bi'm happy\b", r"\byay\b",
        r"\bwoo\b", r"\bwoohoo\b", r"\bfinally\b", r"\bbest day\b",
        r"\bthis made my day\b", r"\bi love this\b", r"\bgreat news\b",
    ]),
    ("sadness", 0.59, [
        r"\bi'm sad\b", r"\bim sad\b", r"\bi feel sad\b", r"\bfeeling down\b",
        r"\bso sad\b", r"\bi'm upset\b", r"\bim upset\b", r"\bi'm hurt\b",
        r"\bim hurt\b", r"\bi miss\b", r"\bhaving a bad day\b",
        r"\bbroken heart\b", r"\bheartbroken\b", r"\bi want to cry\b",
    ]),
    ("anger", 0.52, [
        r"\bi'm so mad\b", r"\bim so mad\b", r"\bso angry\b",
        r"\bfurious\b", r"\bpissed\b", r"\bthis is so unfair\b",
        r"\bwhy would they\b", r"\bi hate this\b", r"\bi hate when\b",
    ]),
    ("fear", 0.67, [
        r"\bi'm afraid\b", r"\bim afraid\b", r"\bi'm scared\b",
        r"\bim scared\b", r"\bterrified\b", r"\bfreaking out\b",
        r"\bso scared\b", r"\bthis is scary\b", r"\bi'm terrified\b",
    ]),
    ("surprise", 0.60, [
        r"\bno way\b", r"\byou're kidding\b", r"\bare you serious\b",
        r"\bwow\b", r"\bwhoa\b", r"\bomg\b", r"\boh my god\b",
        r"\bi can't believe\b", r"\bshocked\b", r"\bwhat the\b",
    ]),
    ("excitement", 0.45, [
        r"\bso excited\b", r"\bcan't wait\b", r"\bcant wait\b",
        r"\bpumped\b", r"\bhyped\b", r"\blet's go\b", r"\blets go\b",
        r"\bthis is happening\b", r"\bfinally happening\b",
        r"\bi'm going to\b", r"\bim going to\b",
    ]),
    ("curiosity", 0.57, [
        r"\bi wonder\b", r"\bhow does\b", r"\bwhat if\b", r"\bwhy does\b",
        r"\btell me more\b", r"\bi want to know\b", r"\bwhat is\b",
        r"\bhow do\b", r"\bexplain\b", r"\bi'm curious\b", r"\bim curious\b",
    ]),
    ("confusion", 0.47, [
        r"\bi'm confused\b", r"\bim confused\b", r"\bdon't understand\b",
        r"\bwhat does this mean\b", r"\bthis makes no sense\b",
        r"\bi don't get it\b", r"\bwhat\?\b", r"\bwhat\?\!\b",
        r"\bcan you explain\b", r"\bso confused\b",
    ]),

    # ── F1 0.40-0.60 — moderate ────────────────────────────────────

    ("admiration", 0.70, [
        r"\bthat's amazing\b", r"\bso impressive\b", r"\brespect\b",
        r"\bi admire\b", r"\btalented\b", r"\bbrilliant\b",
        r"\bincredible\b", r"\byou're so good\b",
    ]),
    ("annoyance", 0.35, [
        r"\bso annoying\b", r"\bugh\b", r"\bthis is annoying\b",
        r"\bstop it\b", r"\bfrustra\b", r"\birritating\b",
        r"\bannoyed\b", r"\bdriving me crazy\b",
    ]),
    ("disappointment", 0.39, [
        r"\bso disappointed\b", r"\bi'm disappointed\b", r"\bim disappointed\b",
        r"\bexpected better\b", r"\blet me down\b", r"\bdidnt work out\b",
        r"\bdidn't work out\b", r"\bfailed again\b",
    ]),
    ("nervousness", 0.43, [
        r"\bso nervous\b", r"\bi'm nervous\b", r"\bim nervous\b",
        r"\banxious\b", r"\bworried\b", r"\bstressed\b",
        r"\bwish me luck\b", r"\bnervous wreck\b",
        r"\bpresentation\b", r"\binterview tomorrow\b",
    ]),
    ("caring", 0.40, [
        r"\bare you okay\b", r"\bhow are you feeling\b", r"\bi'm here for you\b",
        r"\bim here for you\b", r"\bi hope you're okay\b", r"\btake care\b",
        r"\bi care\b", r"\byou okay\b",
    ]),
    ("approval", 0.44, [
        r"\bthat's great\b", r"\bnice work\b", r"\bwell done\b",
        r"\bgood job\b", r"\bi agree\b", r"\bexactly\b",
        r"\bperfect\b", r"\bthats right\b", r"\byou got it\b",
    ]),
    ("optimism", 0.57, [
        r"\bit'll be okay\b", r"\bthings will get better\b",
        r"\blooking forward\b", r"\bcan't wait to\b",
        r"\bexcited for\b", r"\bhopeful\b", r"\bpositive\b",
    ]),
    ("disgust", 0.45, [
        r"\bgross\b", r"\bdisgusting\b", r"\brevolting\b",
        r"\bthat's nasty\b", r"\bew\b", r"\beww\b",
        r"\bthats disgusting\b", r"\bhorrible\b",
    ]),
    ("disapproval", 0.44, [
        r"\bthat's wrong\b", r"\bi disagree\b", r"\bshouldn't\b",
        r"\bthat's bad\b", r"\bnot okay\b", r"\bunacceptable\b",
        r"\bthis is not right\b",
    ]),
    ("embarrassment", 0.37, [
        r"\bso embarrassed\b", r"\bim embarrassed\b", r"\bi'm embarrassed\b",
        r"\bawkward\b", r"\bcringe\b", r"\bthat was awkward\b",
        r"\bwant to hide\b", r"\bmy face\b",
    ]),

    # ── F1 < 0.40 — rarer but still worth catching ─────────────────

    ("grief", 0.33, [
        r"\bgrieving\b", r"\bpassed away\b", r"\blost my\b",
        r"\bthey died\b", r"\bhe died\b", r"\bshe died\b",
        r"\bi'm mourning\b", r"\bim mourning\b", r"\bfuneral\b",
    ]),
    ("remorse", 0.64, [
        r"\bi'm sorry\b", r"\bim sorry\b", r"\bi regret\b",
        r"\bi shouldn't have\b", r"\bmy fault\b", r"\bi messed up\b",
        r"\bi feel terrible\b", r"\bi feel bad about\b",
    ]),
    ("desire", 0.52, [
        r"\bi want\b", r"\bi wish\b", r"\bi need\b", r"\bi crave\b",
        r"\bi really want\b", r"\bif only\b", r"\bi hope i can\b",
    ]),
    ("realization", 0.27, [
        r"\boh wait\b", r"\bi just realized\b", r"\bnow i get it\b",
        r"\bnow i understand\b", r"\bit just hit me\b",
        r"\boh that's why\b", r"\bso that's\b",
    ]),
    ("relief", 0.25, [
        r"\bso relieved\b", r"\bthank god\b", r"\bfinally over\b",
        r"\bthat's a relief\b", r"\bphew\b", r"\bi was so worried\b",
    ]),
    ("pride", 0.58, [
        r"\bi'm so proud\b", r"\bim so proud\b", r"\bproud of\b",
        r"\bi did it\b", r"\bi nailed it\b", r"\bi aced\b",
        r"\bi passed\b", r"\bi got in\b", r"\bi got the job\b",
    ]),

    # ── neutral — always last ───────────────────────────────────────
    ("neutral", 0.30, []),
]


# ── USER emotion → SAMUEL's response expression ────────────────────────
_REACTION_MAP = {
    "gratitude":     "pleased",
    "love":          "pleased",
    "amusement":     "laughing",
    "joy":           "happy",
    "excitement":    "excited",
    "admiration":    "pleased",
    "approval":      "pleased",
    "optimism":      "pleased",
    "pride":         "triumph",
    "relief":        "calm",
    "sadness":       "concerned",
    "grief":         "concerned",
    "disappointment":"concerned",
    "remorse":       "concerned",
    "embarrassment": "concerned",
    "caring":        "concerned",
    "fear":          "calm",
    "nervousness":   "calm",
    "disapproval":   "calm",
    "anger":         "serious",
    "annoyance":     "serious",
    "disgust":       "serious",
    "surprise":      "surprised",
    "confusion":     "curious",
    "curiosity":     "curious",
    "realization":   "curious",
    "desire":        "curious",
    "neutral":       "neutral",
}

# ── USER emotion → system hint for LLM ────────────────────────────────
_HINTS = {
    "gratitude":     "The user is expressing gratitude. Receive it sincerely and warmly.",
    "love":          "The user is expressing love or affection. Respond gently and warmly.",
    "amusement":     "The user finds something funny. Be playful and light.",
    "joy":           "The user is happy. Celebrate with them warmly.",
    "excitement":    "The user is excited. Match their energy with warmth.",
    "admiration":    "The user is admiring something. Respond with genuine appreciation.",
    "approval":      "The user is approving. Respond positively and affirm.",
    "optimism":      "The user is hopeful. Reinforce and encourage.",
    "pride":         "The user is proud of something. Celebrate with them.",
    "relief":        "The user feels relieved. Validate and affirm.",
    "sadness":       "The user is sad. Be warm, gentle, and supportive. Don't rush to fix things.",
    "grief":         "The user is grieving. Be gentle, present, and compassionate.",
    "disappointment":"The user is disappointed. Acknowledge their feelings with empathy.",
    "remorse":       "The user feels remorse or guilt. Be kind and non-judgmental.",
    "embarrassment": "The user is embarrassed. Reassure them warmly.",
    "caring":        "The user is being caring toward you or someone. Respond warmly.",
    "fear":          "The user is scared or anxious. Be calm, steady, and reassuring.",
    "nervousness":   "The user is nervous. Be calm, grounding, and reassuring.",
    "disapproval":   "The user disapproves of something. Listen and respond respectfully.",
    "anger":         "The user is angry. Stay calm, acknowledge their frustration, don't escalate.",
    "annoyance":     "The user is annoyed. Be patient and understanding.",
    "disgust":       "The user is disgusted. Acknowledge and respond calmly.",
    "surprise":      "The user is surprised. Respond with matching curiosity.",
    "confusion":     "The user is confused. Clarify gently and reassuringly.",
    "curiosity":     "The user is curious. Engage their curiosity helpfully and clearly.",
    "realization":   "The user just realized something. Help them process it.",
    "desire":        "The user wants or wishes for something. Engage helpfully.",
    "relief":        "The user is relieved. Validate and affirm.",
    "neutral":       "Respond clearly and warmly.",
}


# ─────────────────────────────────────────────────────────────────────
# SAMUEL SELF-REACTION SYSTEM
# Reads social context directed AT Samuel and returns his self-reaction
# expression. Runs AFTER route_emotion and overrides eye_expression
# when a high-confidence match is found.
#
# Rules ordered by priority — first match wins.
# Each entry: (expression, confidence, [patterns])
# ─────────────────────────────────────────────────────────────────────

_SAMUEL_REACTION_RULES: List[Tuple[str, float, List[str]]] = [

    # ── Being corrected / he got something wrong ───────────────────
    ("shame", 0.90, [
        r"\byou(?:'re| are) wrong\b",
        r"\bthat(?:'s| is) wrong\b",
        r"\bthat(?:'s| is) incorrect\b",
        r"\bactually[,\s]+(?:it|that|the)\b",
        r"\bno[,\s]+(?:that|it|you)\b",
        r"\byou got (?:that|it) wrong\b",
        r"\bwrong answer\b",
        r"\bthat(?:'s| is) not right\b",
        r"\bnot quite\b",
        r"\bclose but\b",
        r"\byou missed\b",
        r"\byou(?:'re| are) mistaken\b",
        r"\bcorrection\b",
        r"\blet me correct\b",
        r"\bthe correct (?:answer|one|thing)\b",
    ]),

    # ── Being praised / good job ───────────────────────────────────
    ("pleased", 0.88, [
        r"\bgood (?:job|work|answer|response|one)\b",
        r"\bwell done\b",
        r"\bnice (?:job|work|answer|one)\b",
        r"\byou(?:'re| are) (?:so )?good\b",
        r"\byou(?:'re| are) (?:so )?smart\b",
        r"\byou(?:'re| are) (?:so )?helpful\b",
        r"\byou(?:'re| are) (?:so )?great\b",
        r"\byou(?:'re| are) amazing\b",
        r"\bi (?:love|like) (?:that|your|you)\b",
        r"\bperfect(?:ly)?\b",
        r"\bexactly (?:right|what i needed)\b",
        r"\bthank(?:s| you)[,\s]+(?:that|you|samuel)\b",
        r"\bthat(?:'s| is) (?:exactly|just) what i (?:needed|wanted)\b",
        r"\bkeep it up\b",
        r"\bi(?:'m| am) impressed\b",
    ]),

    # ── Being told something weird / odd / unexpected ──────────────
    ("incredulous", 0.85, [
        r"\bthat(?:'s| is) (?:so )?weird\b",
        r"\bthat(?:'s| is) (?:so )?strange\b",
        r"\bthat(?:'s| is) (?:so )?odd\b",
        r"\bthat(?:'s| is) (?:so )?random\b",
        r"\bwhat(?:\?|!|\?!)\s*$",
        r"\bwhat the\b",
        r"\bwhat even\b",
        r"\bwait what\b",
        r"\bwait[,\s]+(?:what|huh)\b",
        r"\bi don't understand\b",
        r"\bthat makes no sense\b",
        r"\bhow does that (?:even )?make sense\b",
 