# ui/eyes_window.py
# Floating eyes window — no title bar, draggable, always on top.
# Opens from voice panel OR from main chat via Eyes button.

import tkinter as tk
from ui.theme import BG, BORDER, MUTED, ACCENT, TEXT
from samuel_eyes import SamuelEyes, AudioMonitor, EXPRESSIONS


class EyesWindow(tk.Toplevel):
    def __init__(self, parent_widget, gui):
        super().__init__(gui.root)
        self.gui    = gui
        self.title("Samuel — Eyes")
        self.configure(bg="#0A0A0A")
        self.attributes("-topmost", True)
        self.overrideredirect(True)   # no title bar

        self._drag_x = 0
        self._drag_y = 0

        self._set_initial_position(parent_widget)
        self._build()

        self.audio_monitor = AudioMonitor(self.samuel_eyes)
        self.audio_monitor.start()

        self.protocol("WM_DELETE_WINDOW", self._close)

    def _set_initial_position(self, parent):
        self.update_idletasks()
        try:
            px = parent.winfo_x()
            py = parent.winfo_y()
            self.geometry(f"340x140+{px - 360}+{py + 20}")
        except Exception:
            # fallback: top-right of screen
            self.geometry("340x140+40+40")

    def _build(self):
        # thin border
        outer = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        outer.pack(fill="both", expand=True)

        inner = tk.Frame(outer, bg="#0A0A0A")
        inner.pack(fill="both", expand=True)

        # top bar
        bar = tk.Frame(inner, bg="#151210", height=22)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(bar, text="SAMUEL", bg="#151210", fg=MUTED,
                 font=("Menlo", 8, "bold")).pack(side="left", padx=8)

        close_lbl = tk.Label(bar, text="X", bg="#151210", fg=MUTED,
                              font=("Menlo", 9, "bold"), cursor="hand2")
        close_lbl.pack(side="right", padx=8)
        close_lbl.bind("<Button-1>", lambda _: self._close())

        sz_lbl = tk.Label(bar, text="[ ]", bg="#151210", fg=MUTED,
                          font=("Menlo", 9), cursor="hand2")
        sz_lbl.pack(side="right", padx=4)
        sz_lbl.bind("<Button-1>", lambda _: self._cycle_size())

        # drag on bar
        bar.bind("<ButtonPress-1>",  self._drag_start)
        bar.bind("<B1-Motion>",       self._drag_motion)

        # eyes canvas
        self.canvas = tk.Canvas(inner, bg="#0A0A0A",
                                 highlightthickness=0,
                                 width=340, height=112)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>",  self._drag_start)
        self.canvas.bind("<B1-Motion>",       self._drag_motion)

        self.samuel_eyes = SamuelEyes(self.canvas, bg_color="#0A0A0A")

    # ── drag ──────────────────────────────────

    def _drag_start(self, e):
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _drag_motion(self, e):
        self.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    # ── size cycle ────────────────────────────

    _sizes    = [(340, 112), (500, 160), (240, 90)]
    _size_idx = 0

    def _cycle_size(self):
        self._size_idx = (self._size_idx + 1) % len(self._sizes)
        w, h = self._sizes[self._size_idx]
        self.geometry(f"{w}x{h + 22}+{self.winfo_x()}+{self.winfo_y()}")

    # ── close ─────────────────────────────────

    def _close(self):
        try: self.audio_monitor.stop()
        except: pass
        try: self.samuel_eyes.stop()
        except: pass
        # clear reference on gui
        if getattr(self.gui, "eyes_win", None) is self:
            self.gui.eyes_win = None
        # clear reference on voice_win
        vw = getattr(self.gui, "voice_win", None)
        if vw and getattr(vw, "eyes_win", None) is self:
            vw.eyes_win = None
        self.destroy()

    def destroy(self):
        try: self.audio_monitor.stop()
        except: pass
        try: self.samuel_eyes.stop()
        except: pass
        super().destroy()


# ─────────────────────────────────────────────
# OPENER  — call from anywhere
# ─────────────────────────────────────────────

def open_eyes_window(gui, parent_widget=None):
    """Open or raise the eyes window. Returns the window."""
    existing = getattr(gui, "eyes_win", None)
    try:
        if existing and existing.winfo_exists():
            existing.lift()
            return existing
    except Exception:
        pass

    parent = parent_widget or gui.root
    win = EyesWindow(parent, gui)
    gui.eyes_win = win
    return win