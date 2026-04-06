# loading_screen.py
# Samuel startup loading screen.
# Shows a progress bar while models/DBs load in background.
# When everything is ready, calls on_complete() to reveal the main UI.

import threading
import tkinter as tk
import math
import time

# Match Samuel's color scheme
BG       = "#0F0D0B"
ACCENT   = "#7FCFCB"   # teal
ACCENT2  = "#C4A882"   # warm tan
TEXT     = "#E8DDD0"
MUTED    = "#5A5248"
CARD     = "#1A1714"
DARK_BAR = "#1E1B18"
BAR_FILL = "#7FCFCB"


class LoadingScreen(tk.Frame):
    """
    Full-screen loading overlay. Shows animated progress bar
    and status messages while background tasks complete.
    Call start(tasks) to begin loading.
    """

    def __init__(self, root: tk.Tk, on_complete):
        super().__init__(root, bg=BG)
        self.root        = root
        self.on_complete = on_complete

        self._progress   = 0.0   # 0.0 → 1.0
        self._status     = "Starting up..."
        self._anim_phase = 0.0
        self._done       = False
        self._anim_job   = None

        self.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.lift()

        self._build()
        self._animate()

    def _build(self):
        # Center content frame
        center = tk.Frame(self, bg=BG)
        center.place(relx=0.5, rely=0.5, anchor="center")

        # ── S A M U E L title ──
        tk.Label(center, text="S A M U E L",
                 bg=BG, fg=TEXT,
                 font=("Menlo", 36, "bold")).pack(pady=(0, 6))

        tk.Label(center, text="Initializing systems...",
                 bg=BG, fg=MUTED,
                 font=("Menlo", 12)).pack(pady=(0, 40))

        # ── Progress bar container ──
        bar_frame = tk.Frame(center, bg=BG)
        bar_frame.pack(pady=(0, 16))

        self._bar_canvas = tk.Canvas(
            bar_frame,
            width=480, height=38,
            bg=BG, highlightthickness=0
        )
        self._bar_canvas.pack()

        # ── Status text ──
        self._status_lbl = tk.Label(
            center,
            text=self._status,
            bg=BG, fg=ACCENT,
            font=("Menlo", 11),
            width=50, anchor="center"
        )
        self._status_lbl.pack(pady=(0, 24))

        # ── Percentage ──
        self._pct_lbl = tk.Label(
            center,
            text="0%",
            bg=BG, fg=MUTED,
            font=("Menlo", 10)
        )
        self._pct_lbl.pack()

    def _draw_bar(self):
        c = self._bar_canvas
        c.delete("all")
        W, H = 480, 38
        r = 8   # corner radius

        # ── Outer border (rounded rect) ──
        self._rrect(c, 0, 0, W, H, r, outline=ACCENT, fill=DARK_BAR, width=2)

        # ── Filled portion ──
        fill_w = max(0, int((W - 4) * self._progress))
        if fill_w > 0:
            self._rrect(c, 2, 2, 2 + fill_w, H - 2, r - 1,
                        fill=BAR_FILL, outline="")

            # Shimmer effect — bright moving highlight
            shimmer_x = int(fill_w * ((math.sin(self._anim_phase * 2) + 1) / 2))
            shimmer_w = min(60, fill_w)
            sx1 = max(2, 2 + shimmer_x - shimmer_w // 2)
            sx2 = min(2 + fill_w, sx1 + shimmer_w)
            if sx2 > sx1:
                self._rrect(c, sx1, 4, sx2, H - 4, r - 2,
                            fill="#A8E8E4", outline="")

        # ── Segment dividers (decorative) ──
        segs = 10
        seg_w = (W - 4) // segs
        for i in range(1, segs):
            x = 2 + i * seg_w
            c.create_line(x, 4, x, H - 4, fill=BG, width=2)

    def _rrect(self, c, x1, y1, x2, y2, r, **kw):
        r = max(1, min(r, (x2-x1)//2, (y2-y1)//2))
        pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
               x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
               x1,y2, x1,y2-r, x1,y1+r, x1,y1]
        return c.create_polygon(pts, smooth=True, **kw)

    def _animate(self):
        if self._done:
            return
        self._anim_phase += 0.06
        self._draw_bar()
        self._anim_job = self.after(33, self._animate)

    def update_progress(self, progress: float, status: str):
        """Call from any thread to update the bar."""
        self.root.after(0, lambda p=progress, s=status:
                        self._set_progress(p, s))

    def _set_progress(self, progress: float, status: str):
        self._progress = min(1.0, max(0.0, progress))
        self._status   = status
        self._status_lbl.config(text=status)
        self._pct_lbl.config(text=f"{int(self._progress * 100)}%")
        self._draw_bar()

        if self._progress >= 1.0 and not self._done:
            self.after(600, self._finish)

    def _finish(self):
        """Fade out and call on_complete."""
        self._done = True
        if self._anim_job:
            try: self.after_cancel(self._anim_job)
            except: pass
        self._fade_out(alpha=1.0)

    def _fade_out(self, alpha: float):
        if alpha <= 0:
            self.destroy()
            try:
                self.on_complete()
            except Exception as e:
                print(f"[LOADING] on_complete error: {e}")
            return
        # Simulate fade by darkening the bar
        self._bar_canvas.configure(bg=BG)
        self.after(30, lambda: self._fade_out(alpha - 0.1))

    def destroy(self):
        self._done = True
        if self._anim_job:
            try: self.after_cancel(self._anim_job)
            except: pass
        super().destroy()


# ─────────────────────────────────────────────────────────────────
# PRELOADER  — runs all startup tasks with progress reporting
# ─────────────────────────────────────────────────────────────────

def run_preload(screen: LoadingScreen, tasks: list, on_all_done):
    """
    Fast tasks (weight=1) run in parallel threads.
    Heavy tasks (weight>1) run sequentially so progress is accurate.
    """
    def _worker():
        import concurrent.futures

        fast  = [(l, w, f) for l, w, f in tasks if w == 1]
        heavy = [(l, w, f) for l, w, f in tasks if w  > 1]
        total_weight = sum(w for _, w, _ in tasks)
        done_weight  = 0.0

        # Run all fast tasks in parallel
        screen.update_progress(0.0, "Loading...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(fn): (label, weight)
                    for label, weight, fn in fast}
            for fut in concurrent.futures.as_completed(futs):
                label, weight = futs[fut]
                try: fut.result()
                except Exception