# eyes_ui.py
# EyesUI — solid teal robot eyes with animated expressions.
# When a reaction GIF fires, the eyes canvas is replaced by an animated GIF
# for ~5 seconds, then the eyes return automatically.

import io
import random
import threading
import tkinter as tk
from typing import Optional

BG_BLACK  = "#000000"
EYE_CYAN  = "#21D7E8"
TEXT_DIM  = "#D3C2B1"
USER_PINK = "#F1A3C7"
SAMUEL_BLUE = "#6FD8FF"


class EyesUI(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG_BLACK)

        self.presence   = "not active"
        self.expression = "neutral"
        self.mic_on     = False

        self.caption_speaker = "SAMUEL"
        self.caption_text    = "Samuel is online."

        # Eye geometry
        self.eye_w_default      = 120
        self.eye_h_default      = 120
        self.eye_radius_default = 24
        self.space_default      = 38

        self.eyeL_w = self.eye_w_default
        self.eyeR_w = self.eye_w_default
        self.eyeL_h = float(self.eye_h_default)
        self.eyeR_h = float(self.eye_h_default)

        self.eyeL_target_h = float(self.eye_h_default)
        self.eyeR_target_h = float(self.eye_h_default)

        self.eye_dx_target = 0.0
        self.eye_dy_target = 0.0
        self.eye_dx        = 0.0
        self.eye_dy        = 0.0

        self.confused_frames = 0
        self.laugh_frames    = 0
        self.blink_frames    = 0
        self.tick            = 0
        self.anim_job        = None

        # ── GIF overlay state ──────────────────────────────────────────
        self._gif_active    = False      # True while GIF is showing
        self._gif_frames    = []         # list of PhotoImage frames
        self._gif_idx       = 0
        self._gif_job       = None       # after() handle for frame cycling
        self._gif_hide_job  = None       # after() handle for auto-dismiss
        self._gif_label: Optional[tk.Label] = None
        # ──────────────────────────────────────────────────────────────

        # ── Typewriter / paging state ─────────────────────────────
        self._tw_speaker   = "SAMUEL"
        self._tw_full_text = ""
        self._tw_displayed = ""
        self._tw_job       = None
        self._tw_pages     = []      # list of page strings
        self._tw_page_idx  = 0
        self._tw_char_idx  = 0
        self._tw_speed_ms  = 28      # ms per character
        self._tw_page_hold = 3200    # ms to hold completed page before next
        # ──────────────────────────────────────────────────────────────

        self.canvas = tk.Canvas(self, bg=BG_BLACK, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _e: self._draw())

        self.after(50, self._animate)

    # ──────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────

    def set_state(self, presence: str, expression: Optional[str] = None):
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
        """
        Display text with a typewriter effect, split into pages if long.
        Each page types out character by character, holds, then advances.
        """
        # Cancel any in-progress typewriter
        if self._tw_job:
            try:
                self.after_cancel(self._tw_job)
            except Exception:
                pass
            self._tw_job = None

        self._tw_speaker   = speaker.upper()
        self._tw_full_text = text
        self._tw_displayed = ""

        # Split into pages of ~120 chars at word boundaries
        self._tw_pages   = _split_pages(text, max_chars=120)
        self._tw_page_idx = 0
        self._tw_char_idx = 0

        # Update caption_speaker/text for _draw()
        self.caption_speaker = speaker.upper()
        self.caption_text    = ""

        self._tw_tick()

    def _tw_tick(self):
        """Advance typewriter by one character."""
        if self._tw_page_idx >= len(self._tw_pages):
            return   # all pages done

        page = self._tw_pages[self._tw_page_idx]

        if self._tw_char_idx < len(page):
            # Type next character
            self._tw_char_idx += 1
            self.caption_text = page[:self._tw_char_idx]
            if not self._gif_active:
                self._draw()
            self._tw_job = self.after(self._tw_speed_ms, self._tw_tick)
        else:
            # Page complete — hold then advance
            self._tw_job = self.after(self._tw_page_hold, self._tw_next_page)

    def _tw_next_page(self):
        """Move to the next page."""
        self._tw_page_idx += 1
        self._tw_char_idx  = 0
        if self._tw_page_idx < len(self._tw_pages):
            self.caption_text = ""
            self._tw_tick()
        # else: all pages shown, leave last page visible

    def blink(self):
        self.blink_frames = 6

    def anim_confused(self):
        self.confused_frames = 16

    def anim_laugh(self):
        self.laugh_frames = 16

    # ──────────────────────────────────────────────────────────────────
    # GIF REACTION  (public entry point)
    # ──────────────────────────────────────────────────────────────────

    def show_reaction_gif(self, gif_url: str, duration_ms: int = 5000):
        """
        Download gif_url in a background thread, then display it
        overlaid on the eyes for duration_ms milliseconds.
        Calls back to the main thread via self.after().
        """
        def _fetch_and_show():
            frames = _load_gif_frames(gif_url)
            if not frames:
                return   # silently skip if download/parse fails
            self.after(0, lambda: self._start_gif(frames, duration_ms))

        threading.Thread(target=_fetch_and_show, daemon=True).start()

    # ──────────────────────────────────────────────────────────────────
    # INTERNAL GIF DISPLAY
    # ──────────────────────────────────────────────────────────────────

    def _start_gif(self, frames, duration_ms: int):
        """Must be called from the main thread."""
        self._stop_gif()   # cancel any previous gif

        self._gif_frames = frames
        self._gif_idx    = 0
        self._gif_active = True

        # Create a Label that covers the whole canvas
        self._gif_label = tk.Label(self, bg=BG_BLACK, bd=0, highlightthickness=0)
        self._gif_label.place(relx=0, rely=0, relwidth=1, relheight=1)

        self._gif_tick()

        # Auto-dismiss after duration_ms
        self._gif_hide_job = self.after(duration_ms, self._stop_gif)

    def _gif_tick(self):
        """Cycle through GIF frames."""
        if not self._gif_active or not self._gif_frames:
            return
        frame = self._gif_frames[self._gif_idx % len(self._gif_frames)]
        self._gif_label.config(image=frame)
        self._gif_idx += 1
        delay = max(60, 1000 // max(1, len(self._gif_frames)))  # ~fps
        self._gif_job = self.after(delay, self._gif_tick)

    def _stop_gif(self):
        """Remove GIF overlay and return to eyes."""
        self._gif_active = False

        if self._gif_job:
            try:
                self.after_cancel(self._gif_job)
            except Exception:
                pass
            self._gif_job = None

        if self._gif_hide_job:
            try:
                self.after_cancel(self._gif_hide_job)
            except Exception:
                pass
            self._gif_hide_job = None

        if self._gif_label:
            try:
                self._gif_label.destroy()
            except Exception:
                pass
            self._gif_label = None

        self._gif_frames = []
        self._draw()   # redraw eyes immediately

    # ──────────────────────────────────────────────────────────────────
    # ANIMATION LOOP
    # ──────────────────────────────────────────────────────────────────

    def _animate(self):
        self.tick += 1

        # Random blink
        if self.blink_frames <= 0 and random.random() < 0.015:
            self.blink()

        if self.blink_frames > 0:
            seq = [120, 90, 40, 18, 55, 100]
            idx = 6 - self.blink_frames
            h = seq[max(0, min(idx, len(seq) - 1))]
            self.eyeL_target_h = float(h)
            self.eyeR_target_h = float(h)
            self.blink_frames -= 1
        else:
            self.eyeL_target_h = float(self.eye_h_default)
            self.eyeR_target_h = float(self.eye_h_default)

        # Presence-based look direction
        if self.presence == "thinking":
            self.eye_dx_target = -10.0
            self.eye_dy_target = -2.0
        elif self.presence == "listening":
            self.eye_dx_target = 0.0
            self.eye_dy_target = -4.0
        elif self.presence == "speaking":
            self.eye_dx_target = 4.0
            self.eye_dy_target = 0.0
        else:
            if self.tick % 45 == 0:
                self.eye_dx_target = float(random.randint(-6, 6))
                self.eye_dy_target = float(random.randint(-3, 3))

        self.eye_dx = (self.eye_dx * 3 + self.eye_dx_target) / 4
        self.eye_dy = (self.eye_dy * 3 + self.eye_dy_target) / 4

        self.eyeL_h = (self.eyeL_h * 2 + self.eyeL_target_h) / 3
        self.eyeR_h = (self.eyeR_h * 2 + self.eyeR_target_h) / 3

        if not self._gif_active:
            self._draw()

        self.anim_job = self.after(33, self._animate)

    # ──────────────────────────────────────────────────────────────────
    # DRAWING
    # ──────────────────────────────────────────────────────────────────

    def _draw(self):
        c = self.canvas
        c.delete("all")

        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())

        left_status  = self.presence.upper()
        right_status = "MIC ON" if self.mic_on else "MIC OFF"

        c.create_text(24, 24, text=left_status, anchor="w",
                      fill=TEXT_DIM, font=("Menlo", 15, "bold"))
        c.create_text(w - 24, 24, text=right_status, anchor="e",
                      fill=TEXT_DIM, font=("Menlo", 15, "bold"))

        cx = w // 2
        cy = h // 2 - 55   # shift eyes up to make room for captions below

        space = self.space_default
        lx = cx - (self.eye_w_default // 2) - (space // 2)
        rx = cx + (self.eye_w_default // 2) + (space // 2)

        eyeL_h = max(14, int(self.eyeL_h))
        eyeR_h = max(14, int(self.eyeR_h))

        if self.expression == "curious":
            if self.eye_dx < -2:
                eyeL_h += 20
            elif self.eye_dx > 2:
                eyeR_h += 20

        shake_x = shake_y = 0
        if self.confused_frames > 0:
            shake_x = random.choice([-8, 8])
            self.confused_frames -= 1
        if self.laugh_frames > 0:
            shake_y = random.choice([-5, 5])
            self.laugh_frames -= 1

        lx += int(self.eye_dx) + shake_x
        rx += int(self.eye_dx) + shake_x
        y   = cy + int(self.eye_dy) + shake_y

        self._draw_eye(c, lx, y, self.eye_w_default, eyeL_h, side="left")
        self._draw_eye(c, rx, y, self.eye_w_default, eyeR_h, side="right")

        # ── Captions: anchored near bottom of canvas ───────────────
        speaker_color = USER_PINK if self.caption_speaker == "YOU" else SAMUEL_BLUE

        # subtle divider line near bottom
        c.create_line(w // 6, h - 100, w * 5 // 6, h - 100,
                      fill="#222222", width=1)

        # speaker name — centered, 90px from bottom
        c.create_text(w // 2, h - 88,
                      text=self.caption_speaker,
                      anchor="n",
                      fill=speaker_color,
                      font=("Menlo", 12, "bold"))

        # caption text — centered, wraps, 64px from bottom
        c.create_text(w // 2, h - 64,
                      text=self.caption_text,
                      anchor="n",
                      fill=speaker_color,
                      font=("Menlo", 15),
                      width=max(300, w - 80),
                      justify="center")

    def _draw_eye(self, c, cx, cy, ew, eh, side="left"):
        x1 = cx - ew // 2
        y1 = cy - eh // 2
        x2 = cx + ew // 2
        y2 = cy + eh // 2
        r  = self.eye_radius_default

        expr = self.expression

        # Eyes always stay cyan — expressions shown through lid shape only
        self._round_rect(c, x1, y1, x2, y2, r, fill=EYE_CYAN, outline=EYE_CYAN)

        if expr == "tired":
            # Heavy top lid — covers top half
            if side == "left":
                c.create_polygon(x1-2, y1-2, x2+2, y1-2, x2+2, cy, x1-2, cy,
                                  fill=BG_BLACK, outline=BG_BLACK)
            else:
                c.create_polygon(x1-2, y1-2, x2+2, y1-2, x2+2, cy, x1-2, cy,
                                  fill=BG_BLACK, outline=BG_BLACK)

        elif expr == "angry":
            # Angled top cut — V shape toward inner corner
            if side == "left":
                c.create_polygon(x1-2, y1-2, x2+2, y1-2, x2+2, y1 + eh//2,
                                  fill=BG_BLACK, outline=BG_BLACK)
            else:
                c.create_polygon(x1-2, y1-2, x2+2, y1-2, x1-2, y1 + eh//2,
                                  fill=BG_BLACK, outline=BG_BLACK)

        elif expr == "happy":
            # Squint from bottom — leaves top 60% visible, looks like a smile
            c.create_rectangle(x1 - 2, cy + eh // 4, x2 + 2, y2 + eh,
                                fill=BG_BLACK, outline=BG_BLACK)

        elif expr == "concerned":
            # Sad slant — inner corners raised
            if side == "left":
                c.create_polygon(x1-2, y1-2, x2+2, y1-2, x1 + 20, y1 + eh//3,
                                  fill=BG_BLACK, outline=BG_BLACK)
            else:
                c.create_polygon(x1-2, y1-2, x2+2, y1-2, x2 - 20, y1 + eh//3,
                                  fill=BG_BLACK, outline=BG_BLACK)

        elif expr == "confused":
            # Asymmetric — one side deeper cut
            if side == "left":
                c.create_polygon(x1-2, y1-2, x2+2, y1-2, x1 + 10, y1 + eh//2,
                                  fill=BG_BLACK, outline=BG_BLACK)
            else:
                c.create_polygon(x1-2, y1-2, x2+2, y1-2, x2 - 10, y1 + eh//2 + 12,
                                  fill=BG_BLACK, outline=BG_BLACK)

    def _round_rect(self, c, x1, y1, x2, y2, r, fill, outline):
        c.create_arc(x1, y1, x1 + 2*r, y1 + 2*r, start=90,  extent=90, fill=fill, outline=outline)
        c.create_arc(x2 - 2*r, y1, x2, y1 + 2*r, start=0,   extent=90, fill=fill, outline=outline)
        c.create_arc(x1, y2 - 2*r, x1 + 2*r, y2, start=180, extent=90, fill=fill, outline=outline)
        c.create_arc(x2 - 2*r, y2 - 2*r, x2, y2, start=270, extent=90, fill=fill, outline=outline)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=outline)
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=outline)

    def destroy(self):
        self._stop_gif()
        if self._tw_job:
            try:
                self.after_cancel(self._tw_job)
            except Exception:
                pass
            self._tw_job = None
        try:
            if self.anim_job is not None:
                self.after_cancel(self.anim_job)
        except Exception:
            pass
        self.anim_job = None
        super().destroy()


# ──────────────────────────────────────────────────────────────────────
# GIF LOADER  (runs in background thread)
# ──────────────────────────────────────────────────────────────────────

def _load_gif_frames(url: str):
    """
    Download a GIF from url and split it into a list of tk.PhotoImage frames.
    Returns [] on any error. Must be called from a background thread.
    """
    try:
        import requests
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        raw = resp.content
    except Exception as e:
        print(f"[GIF] download failed: {e}")
        return []

    try:
        from PIL import Image, ImageTk
        img = Image.open(io.BytesIO(raw))
        frames = []
        try:
            while True:
                frame = img.copy().convert("RGBA")
                # Resize to reasonable display size
                frame.thumbnail((400, 300), Image.LANCZOS)
                frames.append(ImageTk.PhotoImage(frame))
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        return frames if frames else []
    except ImportError:
        # Pillow not installed — fall back to tkinter's built-in GIF support
        try:
            photo = tk.PhotoImage(data=raw)
            return [photo]
        except Exception as e:
            print(f"[GIF] tkinter fallback failed: {e}")
            return []
    except Exception as e:
        print(f"[GIF] frame decode failed: {e}")
        return []