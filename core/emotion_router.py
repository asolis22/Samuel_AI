from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class EmotionSignal:
    labels: List[Tuple[str, float]]
    primary: str
    eye_expression: str
    reply_style: str
    system_hint: str


class EmotionRouter:
    def __init__(self, local_model_path: str | None = None):
        self.local_model_path = local_model_path or os.path.join("Samuel_AI", "data", "goemotions_model")
        self._classifier = None
        self._load_attempted = False

    def analyze(self, text: str, tool_mode: bool = False) -> EmotionSignal:
        text = (text or "").strip()
        if not text:
            return self._neutral_signal()

        if tool_mode:
            return EmotionSignal(
                labels=[("neutral", 1.0)],
                primary="neutral",
                eye_expression="neutral",
                reply_style="direct",
                system_hint="The user is making a tool request. Be clear, efficient, and factual.",
            )

        model_result = self._predict_with_model(text)
        if model_result:
            primary, labels = model_result
            return self._map_emotion(primary, labels)

        primary, labels = self._predict_with_rules(text)
        return self._map_emotion(primary, labels)

    def _load_model(self):
        if self._load_attempted:
            return self._classifier
        self._load_attempted = True

        if not os.path.isdir(self.local_model_path):
            return None

        try:
            from transformers import pipeline
            self._classifier = pipeline(
                "text-classification",
                model=self.local_model_path,
                tokenizer=self.local_model_path,
                top_k=5,
            )
            return self._classifier
        except Exception as e:
            print("[EMOTION] local model load failed:", e)
            self._classifier = None
            return None

    def _predict_with_model(self, text: str):
        clf = self._load_model()
        if clf is None:
            return None

        try:
            raw = clf(text)
            if raw and isinstance(raw, list) and len(raw) == 1 and isinstance(raw[0], list):
                raw = raw[0]

            labels = []
            for item in raw[:5]:
                label = str(item.get("label", "")).lower().strip()
                score = float(item.get("score", 0.0))
                if label:
                    labels.append((label, score))

            if not labels:
                return None

            return labels[0][0], labels
        except Exception as e:
            print("[EMOTION] inference failed:", e)
            return None

    def _predict_with_rules(self, text: str):
        t = text.lower()
        rules = [
            ("gratitude", [r"\bthank you\b", r"\bthanks\b", r"\bappreciate\b"]),
            ("joy", [r"\bso happy\b", r"\bexcited\b", r"\byay\b"]),
            ("nervousness", [r"\bnervous\b", r"\banxious\b", r"\bworried\b", r"\bstressed\b"]),
            ("sadness", [r"\bsad\b", r"\bdown\b", r"\bhurt\b", r"\bcry\b"]),
            ("confusion", [r"\bconfused\b", r"\bi don't understand\b", r"\bwhat does this mean\b"]),
            ("curiosity", [r"\bi wonder\b", r"\bcurious\b", r"\bwhat if\b"]),
            ("fear", [r"\bafraid\b", r"\bscared\b", r"\bterrified\b"]),
            ("anger", [r"\bangry\b", r"\bfurious\b", r"\bmad\b"]),
            ("annoyance", [r"\bannoyed\b", r"\birritated\b", r"\bfrustrated\b"]),
            ("embarrassment", [r"\bembarrassed\b", r"\bawkward\b"]),
            ("neutral", []),
        ]

        for label, patterns in rules:
            for p in patterns:
                if re.search(p, t):
                    return label, [(label, 0.85), ("neutral", 0.15)]

        return "neutral", [("neutral", 0.75), ("curiosity", 0.12), ("confusion", 0.13)]

    def _map_emotion(self, primary: str, labels: List[Tuple[str, float]]) -> EmotionSignal:
        eye_map = {
            "joy": "happy",
            "gratitude": "happy",
            "curiosity": "curious",
            "confusion": "confused",
            "fear": "concerned",
            "nervousness": "concerned",
            "sadness": "tired",
            "anger": "angry",
            "annoyance": "angry",
            "embarrassment": "concerned",
            "neutral": "neutral",
        }

        style_map = {
            "joy": "warm_playful",
            "gratitude": "warm_gentle",
            "curiosity": "curious_helpful",
            "confusion": "clear_reassuring",
            "fear": "calm_reassuring",
            "nervousness": "calm_reassuring",
            "sadness": "gentle_supportive",
            "anger": "calm_deescalating",
            "annoyance": "calm_deescalating",
            "embarrassment": "kind_reassuring",
            "neutral": "direct_warm",
        }

        hint_map = {
            "warm_playful": "The user sounds positive. Respond warmly and naturally.",
            "warm_gentle": "The user sounds grateful. Respond sincerely and gently.",
            "curious_helpful": "The user sounds curious. Respond clearly and helpfully.",
            "clear_reassuring": "The user sounds confused. Explain simply and reassuringly.",
            "calm_reassuring": "The user sounds anxious or afraid. Be calm and reassuring.",
            "gentle_supportive": "The user sounds sad. Be gentle and supportive.",
            "calm_deescalating": "The user sounds upset. Stay calm and respectful.",
            "kind_reassuring": "The user sounds embarrassed. Reassure them kindly.",
            "direct_warm": "Respond clearly and warmly.",
        }

        eye_expression = eye_map.get(primary, "neutral")
        reply_style = style_map.get(primary, "direct_warm")
        system_hint = hint_map.get(reply_style, "Respond clearly and warmly.")

        return EmotionSignal(
            labels=labels,
            primary=primary,
            eye_expression=eye_expression,
            reply_style=reply_style,
            system_hint=system_hint,
        )

    def _neutral_signal(self):
        return EmotionSignal(
            labels=[("neutral", 1.0)],
            primary="neutral",
            eye_expression="neutral",
            reply_style="direct_warm",
            system_hint="Respond clearly and warmly.",
        )


_router = EmotionRouter()


def route_emotion(text: str, tool_mode: bool = False) -> EmotionSignal:
    return _router.analyze(text, tool_mode=tool_mode)
