# eyes_ui.py
# Robot eyes for Samuel — 35 expressions matching the reference chart exactly.
# Each expression defined by eye shape + optional eyebrows.
# GIF overlay replaces eyes for 5s then returns.

import io, os, random, tempfile, threading, tkinter as tk
from typing import Optional

BG       = "#000000"
CYAN     = "#21D7E8"
TEXT_DIM = "#D3C2B1"
USER_COL = "#F1A3C7"
SAM_COL  = "#6FD8FF"

#edit
# ─────────────────────────────────────────────────────────────────
# EXPRESSION COMMAND MAP  — for "show me your X expression"
# ─────────────────────────────────────────────────────────────────
EXPRESSION_ALIASES = {
    # exact names
    "happy":"happy","sad":"sad","angry":"angry","confused":"confused",
    "pleased":"pleased","pain":"pain","scared":"scared","serious":"serious",
    "silly":"silly","flirty":"flirty","nervous":"nervous","tired":"tired",
    "surprised":"surprised","shocked":"surprised","irritated":"irritated",
    "wtf":"wtf","rage":"rage","disgusted":"disgusted","confident":"confident",
    "drunk":"drunk","concerned":"concerned","curious":"curious","pouty":"pouty",
    "sick":"sick","laughing":"laughing","shame":"shame","embarrassed":"shame",
    "incredulous":"incredulous","bored":"bored","snooty":"snooty","cold":"cold",
    "neutral":"neutral","calm":"neutral","crying":"crying","devious":"devious",
    "pensive":"pensive","excited":"excited","triumph":"triumph","normal":"neutral",
    # aliases
    "love":"pleased","amused":"laughing","sleepy":"tired","frustrated":"angry",
    "worried":"concerned","anxious":"nervous","mad":"angry","annoyed":"irritated",
    "shocked":"surprised","startled":"surprised","proud":"triumph","smug":"devious",
}

import re as _re

def detect_expression_request(text: str):
    """Returns expression name if user asks to see one, else None."""
    t = text.lower().strip()
    patterns = [
        # "show me your happy face / expression / eyes"
        r"show\s+me\s+(?:your\s+)?(\w+)\s+(?:expression|face|eyes?)",
        # "give me a happy face / expression"
        r"give\s+me\s+(?:a\s+|your\s+)?(\w+)\s+(?:expression|face|eyes?)",
        # "can you give me a happy face"
        r"give\s+me\s+(?:a\s+)?(\w+)\s+face",
        # "make a happy face / expression"
        r"make\s+(?:a\s+)?(\w+)\s+(?:expression|face|eyes?)",
        # "make your face happy"
        r"make\s+your\s+face\s+(\w+)",
        # "be happy / look happy / act happy"
        r"(?:be|look|act)\s+(\w+)(?:\s+(?:expression|face))?",
        # "happy expression please / happy face please"
        r"(\w+)\s+(?:expression|face)\s+please",
        # "show happy / show your happy"
        r"show\s+(?:your\s+)?(\w+)",
        # "can you look happy" / "can you be happy"
        r"can\s+you\s+(?:look|be|act|make\s+a)\s+(\w+)",
        # "do your happy face"
        r"do\s+(?:your\s+)?(\w+)\s+(?:expression|face|eyes?)",
        # "switch to happy" / "go to happy"
        r"(?:switch|go)\s+to\s+(\w+)",
    ]
    for pat in patterns:
        m = _re.search(pat, t)
        if m:
            word = m.group(1).lower()
            if word in EXPRESSION_ALIASES:
                return EXPRESSION_ALIASES[word]
    return None


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _rrect(c, x1, y1, x2, y2, r, **kw):
    r = max(1, min(r, (x2-x1)//2, (y2-y1)//2))
    pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
           x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
           x1,y2, x1,y2-r, x1,y1+r, x1,y1]
    return c.create_polygon(pts, smooth=True, **kw)

def _arc_eye(c, cx, cy, ew, eh, upward=True, color=CYAN):
    """Draw an arc-shaped eye (happy/pleased style)."""
    x1, y1 = cx-ew//2, cy-eh//2
    x2, y2 = cx+ew//2, cy+eh//2
    start = 0 if upward else 180
    c.create_arc(x1, y1, x2, y2, start=start, extent=180,
                  style="chord", fill=color, outline=color)

def _wavy_line(c, cx, cy, ew, color=CYAN, amplitude=6, waves=3):
    """Draw a wavy horizontal line (sick expression)."""
    pts = []
    steps = 30
    for i in range(steps+1):
        x = cx - ew//2 + i * ew // steps
        y = cy + int(amplitude * __import__('math').sin(i * waves * 3.14159 / steps * 2))
        pts.extend([x, y])
    if len(pts) >= 4:
        c.create_line(pts, fill=color, width=6, smooth=True)

def _spiral(c, cx, cy, r, color=CYAN):
    """Draw a spiral (drunk expression)."""
    import math
    pts = []
    for i in range(100):
        angle = i * 0.3
        radius = r * (1 - i/100)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        pts.extend([x, y])
    if len(pts) >= 4:
        c.create_line(pts, fill=color, width=4, smooth=True)

def _tear(c, cx, cy_bottom, color="#6FD8FF"):
    """Draw a teardrop below an eye."""
    c.create_oval(cx-5, cy_bottom, cx+5, cy_bottom+14,
                   fill=color, outline=color)

def _spark(c, cx, cy, size=18, color=CYAN):
    """Draw a star/spark mark (rage)."""
    import math
    for i in range(4):
        angle = i * math.pi / 4
        x1 = cx + size * math.cos(angle)
        y1 = cy + size * math.sin(angle)
        x2 = cx - size * math.cos(angle)
        y2 = cy - size * math.sin(angle)
        c.create_line(x1, y1, x2, y2, fill=color, width=3)


# ─────────────────────────────────────────────────────────────────
# MAIN EYES WIDGET
# ─────────────────────────────────────────────────────────────────

class EyesUI(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)

        self.presence  = "idle"
        self.expression = "neutral"
        self.mic_on    = False
        self.caption_speaker = "SAMUEL"
        self.caption_text    = "Samuel is online."

        # Eye geometry defaults
        self.EW = 120   # eye width
        self.EH = 120   # eye height
        self.GAP = 38   # gap between eyes
        self.R  = 22    # corner radius

        # Animation
        self.tick      = 0
        self.eye_dx    = 0.0
        self.eye_dy    = 0.0
        self.eye_dx_t  = 0.0
        self.eye_dy_t  = 0.0
        self.blink_frames = 0
        self.eyeL_h    = float(self.EH)
        self.eyeR_h    = float(self.EH)
        self.eyeL_h_t  = float(self.EH)
        self.eyeR_h_t  = float(self.EH)
        self.anim_job  = None

        # GIF state
        self._gif_active      = False
        self._gif_frames      = []
        self._gif_idx         = 0
        self._gif_job         = None
        self._gif_hide_job    = None
        self._gif_label: Optional[tk.Label] = None
        self._gif_on_complete = None

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._draw())
        self.after(50, self._animate)

    # ── public api ────────────────────────────────────────────────

    def set_state(self, presence: str, expression: str = None):
        self.presence = presence
        if expression:
            self.expression = expression
        self.mic_on = presence == "listening"
        if not self._gif_active:
            self._draw()

    def set_mic(self, on: bool):
        self.mic_on = on
        if not self._gif_active:
            self._draw()

    def set_caption(self, speaker: str, text: str):
        self.caption_speaker = speaker.upper()
        self.caption_text    = text
        if not self._gif_active:
            self._draw()

    def set_caption_typewriter(self, speaker: str, text: str):
        self.set_caption(speaker, text)

    def blink(self):
        self.blink_frames = 6

    def anim_confused(self):
        pass  # expression handles it

    def anim_laugh(self):
        pass  # expression handles it

    # ── GIF overlay ───────────────────────────────────────────────

    def show_reaction_gif(self, gif_url: str, duration_ms: int = 5000,
                           on_complete=None):
        def _fetch():
            frames = _load_gif_frames(gif_url)
            if not frames:
                if on_complete:
                    try: self.after(0, on_complete)
                    except: pass
                return
            self.after(0, lambda: self._start_gif(frames, duration_ms, on_complete))
        threading.Thread(target=_fetch, daemon=True).start()

    def _start_gif(self, frames, duration_ms, on_complete=None):
        self._stop_gif()
        self._gif_frames      = frames
        self._gif_idx         = 0
        self._gif_active      = True
        self._gif_on_complete = on_complete
        self._gif_label = tk.Label(self, bg=BG, bd=0, highlightthickness=0)
        self._gif_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._gif_tick()
        self._gif_hide_job = self.after(duration_ms, self._stop_gif)

    def _gif_tick(self):
        if not self._gif_active or not self._gif_frames:
            return
        frame = self._gif_frames[self._gif_idx % len(self._gif_frames)]
        self._gif_label.config(image=frame)
        self._gif_idx += 1
        delay = max(50, 1000 // max(1, len(self._gif_frames)))
        self._gif_job = self.after(delay, self._gif_tick)

    def _stop_gif(self):
        self._gif_active = False
        for job in [self._gif_job, self._gif_hide_job]:
            if job:
                try: self.after_cancel(job)
                except: pass
        self._gif_job = self._gif_hide_job = None
        if self._gif_label:
            try: self._gif_label.destroy()
            except: pass
            self._gif_label = None
        self._gif_frames = []
        self._draw()
        cb = self._gif_on_complete
        self._gif_on_complete = None
        if cb:
            try: cb()
            except Exception as e: print(f"[GIF] on_complete error: {e}")

    # ── animation loop ────────────────────────────────────────────

    def _animate(self):
        self.tick += 1

        # random blink
        if self.blink_frames <= 0 and random.random() < 0.015:
            self.blink()
        if self.blink_frames > 0:
            seq = [self.EH, 80, 30, 8, 40, 90]
            idx = 6 - self.blink_frames
            h = float(seq[max(0, min(idx, 5))])
            self.eyeL_h_t = self.eyeR_h_t = h
            self.blink_frames -= 1
        else:
            # Expression-based eye height
            expr = self.expression
            if expr in ("surprised", "shocked", "excited", "wtf"):
                th = float(self.EH) * 1.3
            elif expr in ("tired", "bored", "pouty", "shame", "drunk"):
                th = float(self.EH) * 0.50
            elif expr in ("serious", "confident", "irritated", "cold"):
                th = float(self.EH) * 0.68
            elif expr in ("silly",):
                th = float(self.EH)   # handled per-eye in draw
            elif expr in ("pleased", "laughing", "triumph"):
                th = float(self.EH) * 0.55
            else:
                th = float(self.EH)
            self.eyeL_h_t = self.eyeR_h_t = th

        self.eyeL_h = (self.eyeL_h * 2 + self.eyeL_h_t) / 3
        self.eyeR_h = (self.eyeR_h * 2 + self.eyeR_h_t) / 3

        # look direction
        if self.presence == "thinking":
            self.eye_dx_t, self.eye_dy_t = -10.0, -2.0
        elif self.presence == "listening":
            self.eye_dx_t, self.eye_dy_t = 0.0, -4.0
        elif self.presence == "speaking":
            self.eye_dx_t, self.eye_dy_t = 4.0, 0.0
        else:
            if self.tick % 50 == 0:
                self.eye_dx_t = float(random.randint(-6, 6))
                self.eye_dy_t = float(random.randint(-3, 3))

        self.eye_dx = (self.eye_dx * 3 + self.eye_dx_t) / 4
        self.eye_dy = (self.eye_dy * 3 + self.eye_dy_t) / 4

        if not self._gif_active:
            self._draw()
        self.anim_job = self.after(33, self._animate)

    # ── main draw ─────────────────────────────────────────────────

    def _draw(self):
        c = self.canvas
        c.delete("all")
        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())

        # status labels
        c.create_text(24, 24, text=self.presence.upper(), anchor="w",
                       fill=TEXT_DIM, font=("Menlo", 14, "bold"))
        c.create_text(w-24, 24, text="MIC ON" if self.mic_on else "MIC OFF",
                       anchor="e", fill=TEXT_DIM, font=("Menlo", 14, "bold"))

        cx   = w // 2
        cy   = h // 2 - 55
        lx   = cx - self.GAP//2 - self.EW//2
        rx   = cx + self.GAP//2 + self.EW//2
        lx  += int(self.eye_dx)
        rx  += int(self.eye_dx)
        cy  += int(self.eye_dy)

        self._draw_expression(c, lx, rx, cy, w, h)
        self._draw_caption(c, w, h)

    def _draw_expression(self, c, lx, rx, cy, w, h):
        """Draw both eyes + optional eyebrows for current expression."""
        expr  = self.expression
        ew    = self.EW
        ehL   = max(6, int(self.eyeL_h))
        ehR   = max(6, int(self.eyeR_h))
        r     = self.R
        col   = CYAN

        # ── per-expression drawing ──────────────────────────────────

        if expr == "neutral" or expr == "calm":
            # Two plain open rounded rectangles — NO brows
            _rrect(c, lx-ew//2, cy-ehL//2, lx+ew//2, cy+ehL//2, r, fill=col, outline=col)
            _rrect(c, rx-ew//2, cy-ehR//2, rx+ew//2, cy+ehR//2, r, fill=col, outline=col)

        elif expr == "happy":
            # Bottom-cut arcs (smiley shape) — NO brows
            _rrect(c, lx-ew//2, cy-ehL//2, lx+ew//2, cy+ehL//2, r, fill=col, outline=col)
            c.create_rectangle(lx-ew//2-2, cy, lx+ew//2+2, cy+ehL+2, fill=BG, outline=BG)
            _rrect(c, rx-ew//2, cy-ehR//2, rx+ew//2, cy+ehR//2, r, fill=col, outline=col)
            c.create_rectangle(rx-ew//2-2, cy, rx+ew//2+2, cy+ehR+2, fill=BG, outline=BG)

        elif expr == "sad":
            # Smaller eyes, inner top corners cut (sad slant) — NO brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                # inner top triangle cut
                if ex == lx:
                    c.create_polygon(x2-4, y1-2, x2+2, y1-2, x2+2, y1+eh//2,
                                      fill=BG, outline=BG)
                else:
                    c.create_polygon(x1+4, y1-2, x1-2, y1-2, x1-2, y1+eh//2,
                                      fill=BG, outline=BG)

        elif expr == "angry":
            # Rect eyes, inner-top diagonal cut — HAS brows (angry V)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                if ex == lx:
                    c.create_polygon(x1-2,y1-2, x2+2,y1-2, x2+2,y1+eh//2,
                                      fill=BG, outline=BG)
                else:
                    c.create_polygon(x1-2,y1-2, x2+2,y1-2, x1-2,y1+eh//2,
                                      fill=BG, outline=BG)
            # brows — angry V (inner ends drop)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=14, dy_outer=-2)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=14, dy_outer=-2)

        elif expr == "confused":
            # Left: normal oval. Right: smaller squished — NO brows
            _rrect(c, lx-ew//2, cy-ehL//2, lx+ew//2, cy+ehL//2, r, fill=col, outline=col)
            sh = int(ehR * 0.45)
            _rrect(c, rx-ew//2, cy-sh//2, rx+ew//2, cy+sh//2, r, fill=col, outline=col)

        elif expr == "pleased":
            # Just thin arcs (curved lines) — NO brows
            for ex in [lx, rx]:
                c.create_arc(ex-ew//2, cy-ehL//4, ex+ew//2, cy+ehL//2,
                              start=0, extent=180, style="arc",
                              outline=col, width=8)

        elif expr == "pain":
            # Strong diagonal slashes, squinted — HAS brows (severe V)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                # heavy top AND inner cut
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y1-2, x2+2, y1+int(eh*0.55), fill=BG, outline=BG)
                if ex == lx:
                    c.create_polygon(x1-2,y2-2, x2+2,y2-2, x2+2,y2-int(eh*0.4),
                                      fill=BG, outline=BG)
                else:
                    c.create_polygon(x1-2,y2-2, x2+2,y2-2, x1-2,y2-int(eh*0.4),
                                      fill=BG, outline=BG)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=18, dy_outer=2)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=18, dy_outer=2)

        elif expr == "scared":
            # Wide open eyes — HAS brows (arched high in middle)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                _rrect(c, ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2, r, fill=col, outline=col)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=-12, dy_outer=-6)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=-12, dy_outer=-6)

        elif expr == "serious":
            # Rectangular half-lidded — NO brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y1-2, x2+2, y1+int(eh*0.38), fill=BG, outline=BG)

        elif expr == "silly":
            # Left: closed line (wink). Right: open circle — NO brows
            c.create_line(lx-ew//2, cy, lx+ew//2, cy, fill=col, width=8, capstyle="round")
            _rrect(c, rx-ew//2, cy-ehR//2, rx+ew//2, cy+ehR//2, r, fill=col, outline=col)

        elif expr == "flirty":
            # Left: curved wink. Right: open + lash marks — HAS brow on right
            c.create_arc(lx-ew//2, cy-ehL//4, lx+ew//2, cy+ehL//2,
                          start=0, extent=180, style="arc", outline=col, width=8)
            _rrect(c, rx-ew//2, cy-ehR//2, rx+ew//2, cy+ehR//2, r, fill=col, outline=col)
            # lash marks on right eye
            for i in range(3):
                bx = rx - ew//2 + i * ew//2 + ew//4
                c.create_line(bx, cy-ehR//2-2, bx+4, cy-ehR//2-12, fill=col, width=3)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=-8, dy_outer=-12)

        elif expr == "nervous":
            # Shaky/trembling eyes — HAS brows (inner raised)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                # inner corner notch (trembling look)
                if ex == lx:
                    c.create_polygon(x2-2,y1-2, x2+2,y1-2, x2+2,y1+eh//3,
                                      fill=BG, outline=BG)
                else:
                    c.create_polygon(x1+2,y1-2, x1-2,y1-2, x1-2,y1+eh//3,
                                      fill=BG, outline=BG)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=-8, dy_outer=0)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=-8, dy_outer=0)

        elif expr == "tired":
            # Very heavy top lid — NO brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y1-2, x2+2, y1+int(eh*0.65), fill=BG, outline=BG)

        elif expr == "surprised":
            # Perfectly round, wide open — NO brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                c.create_oval(ex-eh//2, cy-eh//2, ex+eh//2, cy+eh//2,
                               fill=col, outline=col)

        elif expr == "irritated":
            # Flat rect + angular inner cuts — HAS brows (angled in)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y1-2, x2+2, y1+int(eh*0.42), fill=BG, outline=BG)
                if ex == lx:
                    c.create_polygon(x2-2,y1+int(eh*0.42)-2, x2+2,y1+int(eh*0.42)-2,
                                      x2+2, y1+int(eh*0.7), fill=BG, outline=BG)
                else:
                    c.create_polygon(x1+2,y1+int(eh*0.42)-2, x1-2,y1+int(eh*0.42)-2,
                                      x1-2, y1+int(eh*0.7), fill=BG, outline=BG)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=10, dy_outer=-2)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=10, dy_outer=-2)

        elif expr == "wtf":
            # Left: huge eye. Right: tiny eye + spiral — HAS brows (one huge, one tiny)
            big = int(self.EH * 1.25)
            tiny = int(self.EH * 0.3)
            _rrect(c, lx-ew//2, cy-big//2, lx+ew//2, cy+big//2, r, fill=col, outline=col)
            _rrect(c, rx-tiny//2, cy-tiny//2, rx+tiny//2, cy+tiny//2, r//2, fill=col, outline=col)
            _spiral(c, rx+ew//2+12, cy-big//4, 12, col)
            self._brow(c, lx, cy-big//2,  ew, "left",  dy_inner=-14, dy_outer=-10)
            self._brow(c, rx, cy-tiny//2, ew, "right", dy_inner=8,   dy_outer=4)

        elif expr == "rage":
            # Eyes barely visible, extreme diagonal — HAS brows (severe V) + spark
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                if ex == lx:
                    c.create_polygon(x1-2,y1-2, x2+2,y1-2, x2+2,y1+int(eh*0.8),
                                      fill=BG, outline=BG)
                else:
                    c.create_polygon(x1-2,y1-2, x2+2,y1-2, x1-2,y1+int(eh*0.8),
                                      fill=BG, outline=BG)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=20, dy_outer=0)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=20, dy_outer=0)
            _spark(c, lx-ew//2-20, cy-ehL//2-10, 14, col)

        elif expr == "disgusted":
            # Half-closed, bottom cut — HAS brows (slight frown outward)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y1-2, x2+2, y1+int(eh*0.35), fill=BG, outline=BG)
                c.create_rectangle(x1-2, y2-int(eh*0.25), x2+2, y2+2, fill=BG, outline=BG)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=0, dy_outer=8)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=0, dy_outer=8)

        elif expr == "confident":
            # Half-lidded rect, slight inner slant — NO brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y1-2, x2+2, y1+int(eh*0.30), fill=BG, outline=BG)

        elif expr == "drunk":
            # Spiral/swirl eyes — NO brows
            for ex in [lx, rx]:
                _spiral(c, ex, cy, self.EH//2-4, col)

        elif expr == "concerned":
            # Inner top corner cuts (worried look) — HAS brows (inner raised)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                if ex == lx:
                    c.create_polygon(x2-2,y1-2, x2+2,y1-2, x2+2,y1+int(eh*0.38),
                                      fill=BG, outline=BG)
                else:
                    c.create_polygon(x1+2,y1-2, x1-2,y1-2, x1-2,y1+int(eh*0.38),
                                      fill=BG, outline=BG)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=-10, dy_outer=2)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=-10, dy_outer=2)

        elif expr == "curious":
            # One big eye, one smaller — NO brows
            big  = int(self.EH * 1.15)
            sm   = int(self.EH * 0.72)
            _rrect(c, lx-ew//2, cy-big//2, lx+ew//2, cy+big//2, r, fill=col, outline=col)
            _rrect(c, rx-ew//2, cy-sm//2,  rx+ew//2, cy+sm//2,  r, fill=col, outline=col)

        elif expr == "pouty":
            # Very heavy top + bottom cuts — just a thin slit — NO brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y1-2, x2+2, y1+int(eh*0.38), fill=BG, outline=BG)
                c.create_rectangle(x1-2, y2-int(eh*0.38), x2+2, y2+2, fill=BG, outline=BG)

        elif expr == "sick":
            # Wavy droopy lines — NO brows
            for ex in [lx, rx]:
                _wavy_line(c, ex, cy, ew, col)

        elif expr == "laughing":
            # Eyes squeezed to upward curves (^_^) — NO brows
            for ex in [lx, rx]:
                c.create_arc(ex-ew//2, cy-ehL//2, ex+ew//2, cy+ehL//4,
                              start=0, extent=180, style="arc",
                              outline=col, width=8)

        elif expr == "shame":
            # Tiny dots/dashes — NO brows
            dot_w, dot_h = 16, 8
            for ex in [lx, rx]:
                c.create_oval(ex-dot_w, cy-dot_h//2, ex+dot_w, cy+dot_h//2,
                               fill=col, outline=col)

        elif expr == "incredulous":
            # Left: wide open. Right: squinted — HAS brows one up, one flat
            big = int(self.EH * 1.2)
            sm  = int(self.EH * 0.45)
            _rrect(c, lx-ew//2, cy-big//2, lx+ew//2, cy+big//2, r, fill=col, outline=col)
            x1,y1,x2,y2 = rx-ew//2, cy-sm//2, rx+ew//2, cy+sm//2
            _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
            c.create_rectangle(x1-2, y1-2, x2+2, y1+int(sm*0.45), fill=BG, outline=BG)
            self._brow(c, lx, cy-big//2, ew, "left",  dy_inner=-14, dy_outer=-10)
            self._brow(c, rx, cy-sm//2,  ew, "right", dy_inner=4,   dy_outer=2)

        elif expr == "bored":
            # Very heavy top lid, rectangular — NO brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y1-2, x2+2, y1+int(eh*0.62), fill=BG, outline=BG)

        elif expr == "snooty":
            # Eyes tilted upward/outward — HAS brows (raised outward)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                # outer bottom cut (looking up)
                if ex == lx:
                    c.create_polygon(x1-2,y2+2, x1+int(ew*0.5),y2+2,
                                      x1-2,y2-int(eh*0.4), fill=BG, outline=BG)
                else:
                    c.create_polygon(x2+2,y2+2, x2-int(ew*0.5),y2+2,
                                      x2+2,y2-int(eh*0.4), fill=BG, outline=BG)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=0,  dy_outer=-12)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=0,  dy_outer=-12)

        elif expr == "cold":
            # Just two thin horizontal dashes — NO brows
            dash_h = 10
            for ex in [lx, rx]:
                c.create_rectangle(ex-ew//2, cy-dash_h//2, ex+ew//2, cy+dash_h//2,
                                    fill=col, outline=col)

        elif expr == "crying":
            # Squeezed shut (curved) + teardrops — HAS brows (sad arch)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                c.create_arc(ex-ew//2, cy-eh//4, ex+ew//2, cy+eh//2,
                              start=0, extent=180, style="arc",
                              outline=col, width=8)
                _tear(c, ex, cy+eh//2+2)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=-10, dy_outer=4)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=-10, dy_outer=4)

        elif expr == "devious":
            # Heavy inner slant, right eye slightly larger — HAS brows (devious arch)
            for ex, eh, scale in [(lx, ehL, 1.0), (rx, ehR, 1.12)]:
                ew2 = int(ew * scale)
                x1,y1,x2,y2 = ex-ew2//2, cy-eh//2, ex+ew2//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                if ex == lx:
                    c.create_polygon(x1-2,y1-2, x2+2,y1-2, x2+2,y1+int(eh*0.55),
                                      fill=BG, outline=BG)
                else:
                    c.create_polygon(x1-2,y1-2, x2+2,y1-2, x1-2,y1+int(eh*0.55),
                                      fill=BG, outline=BG)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=12, dy_outer=-4)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=-8, dy_outer=-14)

        elif expr == "pensive":
            # Eyes looking slightly down, slight outer slant — NO brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2+8, ex+ew//2, cy+eh//2+8
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                if ex == lx:
                    c.create_polygon(x1-2,y1-2, x1+int(ew*0.5),y1-2,
                                      x1-2,y1+int(eh*0.35), fill=BG, outline=BG)
                else:
                    c.create_polygon(x2+2,y1-2, x2-int(ew*0.5),y1-2,
                                      x2+2,y1+int(eh*0.35), fill=BG, outline=BG)

        elif expr == "excited":
            # Wide open + slight top cut — HAS brows (slightly raised)
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                _rrect(c, ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2, r, fill=col, outline=col)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=-6, dy_outer=-8)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=-6, dy_outer=-8)

        elif expr == "triumph":
            # Squinted + upward curve (smug arch bottom) — HAS brows
            for ex, eh in [(lx, ehL), (rx, ehR)]:
                x1,y1,x2,y2 = ex-ew//2, cy-eh//2, ex+ew//2, cy+eh//2
                _rrect(c, x1, y1, x2, y2, r, fill=col, outline=col)
                c.create_rectangle(x1-2, y2-int(eh*0.42), x2+2, y2+2, fill=BG, outline=BG)
                c.create_arc(x1, y2-int(eh*0.55), x2, y2+int(eh*0.2),
                              start=180, extent=180, style="arc",
                              outline=col, width=6)
            self._brow(c, lx, cy-ehL//2, ew, "left",  dy_inner=-4, dy_outer=-10)
            self._brow(c, rx, cy-ehR//2, ew, "right", dy_inner=-4, dy_outer=-10)

        else:
            # Fallback: neutral
            _rrect(c, lx-ew//2, cy-ehL//2, lx+ew//2, cy+ehL//2, r, fill=col, outline=col)
            _rrect(c, rx-ew//2, cy-ehR//2, rx+ew//2, cy+ehR//2, r, fill=col, outline=col)

    def _brow(self, c, cx, eye_top_y, ew, side, dy_inner=0, dy_outer=0):
        """Draw one eyebrow. dy_inner/outer = offset from base brow height."""
        base_y = eye_top_y - 16
        bw     = int(ew * 0.72)
        bx1    = cx - bw // 2
        bx2    = cx + bw // 2
        # left eye: inner=right(bx2), outer=left(bx1)
        # right eye: inner=left(bx1), outer=right(bx2)
        if side == "left":
            ox, oy = bx1, base_y + dy_outer
            ix, iy = bx2, base_y + dy_inner
        else:
            ox, oy = bx2, base_y + dy_outer
            ix, iy = bx1, base_y + dy_inner
        c.create_line(ox, oy, ix, iy, fill=CYAN, width=6, capstyle="round")

    def _draw_caption(self, c, w, h):
        speaker_col = USER_COL if self.caption_speaker == "YOU" else SAM_COL
        c.create_line(w//6, h-108, w*5//6, h-108, fill="#1E1E1E", width=1)
        c.create_text(w//2, h-92, text=self.caption_speaker, anchor="n",
                       fill=speaker_col, font=("Menlo", 12, "bold"))
        c.create_text(w//2, h-68, text=self.caption_text, anchor="n",
                       fill=speaker_col, font=("Menlo", 15),
                       width=max(300, w-80), justify="center")

    def destroy(self):
        self._stop_gif()
        if self.anim_job:
            try: self.after_cancel(self.anim_job)
            except: pass
        self.anim_job = None
        super().destroy()


# ─────────────────────────────────────────────────────────────────
# GIF FRAME LOADER
# ─────────────────────────────────────────────────────────────────

def _load_gif_frames(url: str):
    try:
        import requests
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        raw  = resp.content
        print(f"[GIF] Downloaded {len(raw)} bytes")
    except Exception as e:
        print(f"[GIF] Download failed: {e}")
        return []

    # Try Pillow first
    try:
        from PIL import Image, ImageTk
        img    = Image.open(io.BytesIO(raw))
        frames = []
        try:
            while True:
                frame = img.copy().convert("RGBA")
                frame.thumbnail((500, 380), Image.LANCZOS)
                frames.append(ImageTk.PhotoImage(frame))
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        if frames:
            print(f"[GIF] Pillow: {len(frames)} frames")
            return frames
    except ImportError:
        pass
    except Exception as e:
        print(f"[GIF] Pillow error: {e}")

    # Tkinter native fallback
    try:
        with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as f:
            f.write(raw)
            tmp = f.name
        frames = []
        i = 0
        while True:
            try:
                p = tk.PhotoImage(file=tmp, format=f"gif -index {i}")
                frames.append(p)
                i += 1
            except Exception:
                break
        os.unlink(tmp)
        if frames:
            print(f"[GIF] tkinter: {len(frames)} frames")
        else:
            print("[GIF] tkinter: 0 frames")
        return frames
    except Exception as e:
        print(f"[GIF] tkinter fallback error: {e}")
        return []