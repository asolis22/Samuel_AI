# samuel_eyes.py
# Robot eyes — solid filled shapes, no pupils, Cozmo/Emo-style.
# Expressions: 20 built-in. Each is two solid colored shapes on black.
# Reacts to: user typing, user messages, Samuel's replies, voice commands.

import math, threading, time, re, tkinter as tk
from typing import Optional

# ─────────────────────────────────────────────
# SHAPE HELPERS
# ─────────────────────────────────────────────

def _rrect(c, x1, y1, x2, y2, r, **kw):
    """Solid rounded rectangle."""
    r = max(1, min(r, (x2-x1)//2, (y2-y1)//2))
    pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
           x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
           x1,y2, x1,y2-r, x1,y1+r, x1,y1]
    return c.create_polygon(pts, smooth=True, **kw)

# ─────────────────────────────────────────────
# EXPRESSION DEFINITIONS
# ─────────────────────────────────────────────
# Each expression draws two eye shapes.
# Parameters per eye (L=left, R=right):
#   open_l/r      : 0=closed  1=fully open
#   cut_top_l/r   : black cut from TOP   (0-1 fraction of eye height)
#   cut_bot_l/r   : black cut from BOTTOM
#   slant_l/r     : V-slant from top  (+ = angry inner drop, - = sad inner drop)
#   shape         : "oval" | "rect" | "dash" | "arc_up" | "arc_down"
#   color         : fill color
#   blink_speed   : seconds between auto blinks
#   offset_y_l/r  : vertical shift of individual eye (-1 up, +1 down)

EXPRESSIONS = {
    # ── NEUTRAL ── two even ovals
    "neutral": dict(
        open_l=1.0, open_r=1.0,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#4DCFCF", blink_speed=4.5,
    ),
    # ── HAPPY ── bottom cut makes upward arc smile shape
    "happy": dict(
        open_l=0.75, open_r=0.75,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.50, cut_bot_r=0.50,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#5DFFAA", blink_speed=3.0,
    ),
    # ── EXCITED ── wide open, bright
    "excited": dict(
        open_l=1.0, open_r=1.0,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#FFFFFF", blink_speed=6.0,
    ),
    # ── CURIOUS ── one eye slightly squinted top
    "curious": dict(
        open_l=1.0, open_r=0.80,
        cut_top_l=0.0, cut_top_r=0.18,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#80C8FF", blink_speed=5.0,
    ),
    # ── THINKING ── one eye half closed from top, other normal
    "thinking": dict(
        open_l=1.0, open_r=0.55,
        cut_top_l=0.0, cut_top_r=0.42,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="rect", color="#80C8FF", blink_speed=7.0,
    ),
    # ── CONCERNED ── inner corners raised (sad V)
    "concerned": dict(
        open_l=0.85, open_r=0.85,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=-0.28, slant_r=0.28,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#C8A0FF", blink_speed=3.5,
    ),
    # ── SAD ── heavy bottom cut + sad slant
    "sad": dict(
        open_l=0.6, open_r=0.6,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=-0.40, slant_r=0.40,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#7090C0", blink_speed=2.5,
    ),
    # ── AMUSED ── slight bottom squint, relaxed
    "amused": dict(
        open_l=0.80, open_r=0.80,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.22, cut_bot_r=0.22,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#FFD080", blink_speed=3.0,
    ),
    # ── CONFIDENT ── heavy top cut, rect, angled inward
    "confident": dict(
        open_l=0.70, open_r=0.70,
        cut_top_l=0.32, cut_top_r=0.32,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.18, slant_r=-0.18,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="rect", color="#4DCFCF", blink_speed=6.0,
    ),
    # ── SHY ── half open, slightly down
    "shy": dict(
        open_l=0.50, open_r=0.50,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.15, offset_y_r=0.15,
        shape="oval", color="#FFB0C8", blink_speed=2.0,
    ),
    # ── HMPH ── very heavy top cut, flat rect, inner slant
    "hmph": dict(
        open_l=0.45, open_r=0.45,
        cut_top_l=0.50, cut_top_r=0.50,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.35, slant_r=-0.35,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="rect", color="#A0A0A0", blink_speed=7.0,
    ),
    # ── ANGRY ── strong inner slant + top cut
    "angry": dict(
        open_l=0.65, open_r=0.65,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.45, slant_r=-0.45,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="rect", color="#FF6040", blink_speed=5.0,
    ),
    # ── SURPRISED ── max open
    "surprised": dict(
        open_l=1.0, open_r=1.0,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#80FFFF", blink_speed=9.0,
    ),
    # ── EVIL ── strong angular inner cut, red, rect
    "evil": dict(
        open_l=0.60, open_r=0.60,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.55, slant_r=-0.55,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="rect", color="#FF2040", blink_speed=5.5,
    ),
    # ── SILLY ── eyes at different heights, one squinted
    "silly": dict(
        open_l=1.0, open_r=0.50,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.35,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=-0.20, offset_y_r=0.20,
        shape="oval", color="#FFD700", blink_speed=2.5,
    ),
    # ── SLEEPY ── heavy top cuts, slow blink
    "sleepy": dict(
        open_l=0.35, open_r=0.35,
        cut_top_l=0.60, cut_top_r=0.60,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#7080FF", blink_speed=2.0,
    ),
    # ── LOVE ── heart-ish: bottom cut high + bright pink
    "love": dict(
        open_l=0.80, open_r=0.80,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.40, cut_bot_r=0.40,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#FF80C0", blink_speed=3.5,
    ),
    # ── SCARED ── wide open + inner sad slant
    "scared": dict(
        open_l=1.0, open_r=1.0,
        cut_top_l=0.0, cut_top_r=0.0,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=-0.30, slant_r=0.30,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="oval", color="#C0E0FF", blink_speed=1.5,
    ),
    # ── FOCUSED ── narrow rect, slight top cut, direct
    "focused": dict(
        open_l=0.65, open_r=0.65,
        cut_top_l=0.20, cut_top_r=0.20,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="rect", color="#40E0FF", blink_speed=5.0,
    ),
    # ── SMUG ── one eye lower, inner confident slant
    "smug": dict(
        open_l=0.70, open_r=0.55,
        cut_top_l=0.25, cut_top_r=0.38,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.20, slant_r=-0.10,
        offset_y_l=0.0, offset_y_r=0.10,
        shape="rect", color="#C0FF80", blink_speed=6.0,
    ),
    # ── BORED ── very flat top cut, half-lidded
    "bored": dict(
        open_l=0.50, open_r=0.50,
        cut_top_l=0.45, cut_top_r=0.45,
        cut_bot_l=0.0, cut_bot_r=0.0,
        slant_l=0.0, slant_r=0.0,
        offset_y_l=0.0, offset_y_r=0.0,
        shape="rect", color="#909090", blink_speed=3.0,
    ),
}

# ── voice command aliases ──
VOICE_EXPRESSION_MAP = {
    "happy":      "happy",
    "excited":    "excited",
    "sad":        "sad",
    "angry":      "angry",
    "evil":       "evil",
    "mischievous":"evil",
    "silly":      "silly",
    "sleepy":     "sleepy",
    "tired":      "sleepy",
    "curious":    "curious",
    "thinking":   "thinking",
    "concerned":  "concerned",
    "worried":    "concerned",
    "amused":     "amused",
    "confident":  "confident",
    "shy":        "shy",
    "embarrassed":"shy",
    "hmph":       "hmph",
    "unimpressed":"hmph",
    "surprised":  "surprised",
    "shocked":    "surprised",
    "love":       "love",
    "focused":    "focused",
    "smug":       "smug",
    "bored":      "bored",
    "neutral":    "neutral",
    "normal":     "neutral",
    "default":    "neutral",
}

# text emotion → expression (for auto-react)
EMOTION_MAP = {
    "happy":"happy","glad":"happy","pleased":"happy","great":"happy","yay":"happy",
    "excited":"excited","amazing":"excited","love":"love","wonderful":"excited",
    "sad":"sad","upset":"sad","miss":"sad","lonely":"sad","depressed":"sad",
    "angry":"angry","frustrated":"angry","mad":"angry","annoyed":"hmph",
    "curious":"curious","interested":"curious","wonder":"curious","question":"curious",
    "thinking":"thinking","hmm":"thinking","considering":"thinking",
    "concerned":"concerned","worried":"concerned","anxious":"concerned","scared":"scared",
    "amused":"amused","funny":"amused","haha":"amused","lol":"amused",
    "confident":"confident","sure":"confident","certain":"confident",
    "shy":"shy","embarrassed":"shy","blush":"shy",
    "hmph":"hmph","bored":"bored","whatever":"hmph","unimpressed":"hmph",
    "surprised":"surprised","wow":"surprised","whoa":"surprised","omg":"surprised",
    "evil":"evil","mischievous":"evil","sneaky":"evil",
    "silly":"silly","goofy":"silly","playful":"silly",
    "sleepy":"sleepy","tired":"sleepy","exhausted":"sleepy",
    "focused":"focused","serious":"focused","determined":"focused",
    "smug":"smug","proud":"smug",
}


def parse_emotion_tag(text: str) -> Optional[str]:
    m = re.search(r"\[(\w+)\]", text)
    if not m: return None
    return EMOTION_MAP.get(m.group(1).lower())

def strip_emotion_tag(text: str) -> str:
    return re.sub(r"\[\w+\]\s*", "", text).strip()

def detect_voice_command(text: str) -> Optional[str]:
    """Check if user is telling Samuel to change expression. Returns expression name or None."""
    t = text.lower().strip()
    patterns = [
        r"be\s+(\w+)",
        r"look\s+(\w+)",
        r"act\s+(\w+)",
        r"show\s+(\w+)",
        r"feel\s+(\w+)",
        r"make\s+(?:a\s+)?(\w+)\s+face",
        r"(\w+)\s+face",
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            word = m.group(1).lower()
            if word in VOICE_EXPRESSION_MAP:
                return VOICE_EXPRESSION_MAP[word]
    return None


# ─────────────────────────────────────────────
# LERP
# ─────────────────────────────────────────────

def _lerp(a, b, t): return a + (b-a)*t

def _lerp_dict(a, b, t):
    out = {}
    for k in a:
        if isinstance(a[k], (int,float)):
            out[k] = _lerp(a[k], b.get(k, a[k]), t)
        else:
            out[k] = b[k] if t > 0.5 else a[k]
    return out


# ─────────────────────────────────────────────
# EYES ENGINE
# ─────────────────────────────────────────────

class SamuelEyes:
    def __init__(self, canvas: tk.Canvas, bg_color: str = "#0A0A0A"):
        self.canvas      = canvas
        self.bg          = bg_color
        self._expr_name  = "neutral"
        self._current    = dict(EXPRESSIONS["neutral"])
        self._target     = dict(EXPRESSIONS["neutral"])
        self._lerp_t     = 1.0
        self._lerp_speed = 0.10

        self._blink_phase = 0.0
        self._blinking    = False
        self._next_blink  = time.time() + 3.0

        self._audio_rms  = 0.0
        self._audio_lock = threading.Lock()

        self._micro_phase = 0.0
        self._running     = True
        self._anim_job    = None
        canvas.after(60, self._animate)

    def set_expression(self, name: str):
        name = name.lower().strip()
        if name not in EXPRESSIONS:
            name = "neutral"
        if name == self._expr_name and self._lerp_t >= 1.0:
            return
        self._expr_name = name
        self._target    = dict(EXPRESSIONS[name])
        self._lerp_t    = 0.0

    def audio_react(self, rms: float, _pitch: float = 0.5):
        with self._audio_lock:
            self._audio_rms = self._audio_rms * 0.6 + rms * 0.4

    def stop(self):
        self._running = False
        if self._anim_job:
            try: self.canvas.after_cancel(self._anim_job)
            except: pass

    # ── animation ─────────────────────────────

    def _animate(self):
        if not self._running: return
        try:
            self._micro_phase = (self._micro_phase + 0.032) % (math.pi*2)

            if self._lerp_t < 1.0:
                self._lerp_t = min(1.0, self._lerp_t + self._lerp_speed)
                base = EXPRESSIONS.get(self._expr_name, EXPRESSIONS["neutral"])
                self._current = _lerp_dict(base, self._target, self._lerp_t)

            now = time.time()
            if not self._blinking and now >= self._next_blink:
                self._blinking    = True
                self._blink_phase = 0.0
            if self._blinking:
                self._blink_phase += 0.20
                if self._blink_phase >= 1.0:
                    self._blinking   = False
                    spd = self._current.get("blink_speed", 4.5)
                    self._next_blink = now + spd + (math.sin(self._micro_phase)+1)*0.8

            self._draw()
        except Exception:
            pass
        self._anim_job = self.canvas.after(33, self._animate)

    # ── draw ──────────────────────────────────

    def _draw(self):
        c = self.canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())

        p     = self._current
        color = p.get("color", "#4DCFCF")
        shape = p.get("shape", "oval")

        # geometry
        eye_w = int(min(w * 0.32, h * 0.68))
        eye_h = int(eye_w * 0.58)
        gap   = int(eye_w * 0.26)
        base_cy = h // 2 + int(math.sin(self._micro_phase * 0.55) * 2)

        lx = w//2 - gap//2 - eye_w//2
        rx = w//2 + gap//2 + eye_w//2

        blink = 0.0
        if self._blinking:
            blink = math.sin(self._blink_phase * math.pi)

        for side in ("left","right"):
            cx      = lx if side=="left" else rx
            open_   = p["open_l"]     if side=="left" else p["open_r"]
            cut_top = p["cut_top_l"]  if side=="left" else p["cut_top_r"]
            cut_bot = p["cut_bot_l"]  if side=="left" else p["cut_bot_r"]
            slant   = p["slant_l"]    if side=="left" else p["slant_r"]
            oy      = p.get("offset_y_l",0) if side=="left" else p.get("offset_y_r",0)

            eff_open = max(0.0, open_ * (1.0 - blink))
            ah = int(eye_h * eff_open)        # actual height
            cy = base_cy + int(eye_h * oy * 0.4)

            if ah < 3:
                # closed = thin line
                c.create_rectangle(cx-eye_w//2, cy-2, cx+eye_w//2, cy+2,
                                    fill=color, outline="")
                continue

            x1, x2 = cx-eye_w//2, cx+eye_w//2
            y1, y2 = cy-ah//2, cy+ah//2
            rad = min(ah//2, eye_w//5)

            # ── solid eye body ──
            if shape == "rect":
                _rrect(c, x1, y1, x2, y2, rad, fill=color, outline="")
            else:
                c.create_oval(x1, y1, x2, y2, fill=color, outline="")

            # ── slant cut (angry / sad) — black wedge from top ──
            if abs(slant) > 0.02:
                sh = int(ah * 0.6 * abs(slant))
                # left eye: positive slant = inner (right) corner wedge
                # right eye: negative slant = inner (left) corner wedge
                if side == "left":
                    yi = y1 + (sh if slant > 0 else -sh)
                else:
                    yi = y1 + (-sh if slant < 0 else sh)
                c.create_polygon(x1-1, y1-1, (x1+x2)//2, yi, x2+1, y1-1,
                                  fill="#0A0A0A", outline="")

            # ── cut from top ──
            if cut_top > 0.01:
                ch = int(ah * cut_top)
                c.create_rectangle(x1-1, y1-1, x2+1, y1+ch,
                                    fill="#0A0A0A", outline="")

            # ── cut from bottom ──
            if cut_bot > 0.01:
                ch = int(ah * cut_bot)
                c.create_rectangle(x1-1, y2-ch, x2+1, y2+1,
                                    fill="#0A0A0A", outline="")


# ─────────────────────────────────────────────
# AUDIO MONITOR
# ─────────────────────────────────────────────

class AudioMonitor:
    def __init__(self, eyes: SamuelEyes):
        self.eyes     = eyes
        self._running = False
        self._thread  = None

    def start(self):
        if self._running: return
        self._running = True
        self._thread  = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        try:
            import sounddevice as sd, numpy as np
            RATE, CHUNK = 16000, int(16000*0.05)
            while self._running:
                try:
                    chunk = sd.rec(CHUNK, samplerate=RATE, channels=1, dtype="float32")
                    sd.wait()
                    rms = min(1.0, float(np.sqrt(np.mean(chunk**2))) * 8.0)
                    self.eyes.audio_react(rms)
                except: time.sleep(0.05)
        except ImportError: pass


# ─────────────────────────────────────────────
# EMOTION PREDICTOR  (for Samuel's reply)
# ─────────────────────────────────────────────

_EMOTION_SYSTEM = (
    "You are Samuel's emotion engine. Given his response, pick ONE tag:\n"
    "[happy][excited][curious][thinking][concerned][sad][amused][confident]"
    "[shy][hmph][angry][surprised][evil][silly][sleepy][love][scared]"
    "[focused][smug][bored][neutral]\n"
    "Output the tag only."
)

def predict_emotion(response_text: str, llm_fn) -> str:
    try:
        raw = llm_fn([
            {"role":"system","content":_EMOTION_SYSTEM},
            {"role":"user","content":response_text[:400]},
        ], temperature=0.2)
        tag = parse_emotion_tag(raw or "")
        return tag or "neutral"
    except:
        return "neutral"