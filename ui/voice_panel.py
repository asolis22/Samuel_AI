import math
import threading
import tkinter as tk

from Samuel_AI.ui.theme import BG, PANEL, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2, ACCENT3
from Samuel_AI.core.tts_engine import SPEAKING_EVENT
from Samuel_AI.core.stt_engine import SpeechListener


class VoicePanel(tk.Toplevel):
    def __init__(self, gui):
        super().__init__(gui.root)
        self.gui = gui

        self.title("Samuel — Voice Mode")
        self.configure(bg=BG)
        self.geometry("760x560")
        self.minsize(680, 500)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.auto_speak = True
        self._ptt_held = False
        self._pulse_phase = 0.0
        self._anim_job = None

        self.listener = SpeechListener(self._on_heard_text, phrase_seconds=4.0)

        self._build()
        self.after(60, self._start_animation)

    def _build(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(18, 10))

        tk.Label(header, text="VOICE MODE", bg=BG, fg=TEXT, font=("Menlo", 16, "bold")).pack(side="left")

        self.status = tk.Label(header, text="● READY", bg=BG, fg=MUTED, font=("Menlo", 11, "bold"))
        self.status.pack(side="right")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=10)

        left = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.hud = tk.Canvas(left, bg=PANEL, highlightthickness=0)
        self.hud.pack(fill="both", expand=True, padx=12, pady=12)
        self.hud.bind("<Configure>", lambda _e: self._draw_hud())

        right = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, width=260)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        inner = tk.Frame(right, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(inner, text="Controls", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        self.auto_btn = tk.Button(
            inner,
            text="AUTO SPEAK: ON",
            bg=ACCENT,
            fg="#11100F",
            relief="flat",
            font=("Menlo", 12, "bold"),
            command=self._toggle_auto,
        )
        self.auto_btn.pack(fill="x", pady=(12, 8))

        self.ptt_btn = tk.Button(
            inner,
            text="HOLD TO TALK",
            bg=CARD,
            fg=TEXT,
            relief="flat",
            font=("Menlo", 11, "bold"),
        )
        self.ptt_btn.pack(fill="x", pady=6)
        self.ptt_btn.bind("<ButtonPress-1>", self._ptt_press)
        self.ptt_btn.bind("<ButtonRelease-1>", self._ptt_release)

        tk.Label(
            inner,
            text="Press and hold to talk.\nRelease to transcribe and send.",
            bg=PANEL,
            fg=MUTED,
            font=("Menlo", 10),
            wraplength=220,
            justify="left",
        ).pack(anchor="w", pady=(10, 8))

        self._transcript_lbl = tk.Label(
            inner,
            text="",
            bg=PANEL,
            fg=ACCENT,
            font=("Menlo", 9),
            wraplength=220,
            justify="left",
        )
        self._transcript_lbl.pack(anchor="w", pady=(0, 8))

        self.entry = tk.Text(
            inner,
            bg=CARD,
            fg=TEXT,
            insertbackground=ACCENT,
            relief="flat",
            font=("Menlo", 12),
            height=5,
            wrap="word",
        )
        self.entry.pack(fill="x", pady=(0, 10))
        self.entry.bind("<Return>", self._on_enter_send)
        self.entry.bind("<Shift-Return>", self._on_shift_enter)

        tk.Button(
            inner,
            text="SEND",
            bg=ACCENT3,
            fg="#11100F",
            relief="flat",
            font=("Menlo", 12, "bold"),
            command=self._send_from_voice,
        ).pack(fill="x")

    def _draw_hud(self):
        c = self.hud
        c.delete("all")

        w = max(1, c.winfo_width())
        h = max(1, c.winfo_height())
        size = max(120, min(w, h) - 40)

        cx, cy = w // 2, h // 2
        r1 = size // 2
        r2 = int(r1 * 0.82)
        r3 = int(r1 * 0.62)

        speaking = SPEAKING_EVENT.is_set()
        pulse = (math.sin(self._pulse_phase) + 1.0) / 2.0

        amp = 10 if speaking else (6 if self._ptt_held else 2)
        w_amp = 2.0 if speaking else (1.5 if self._ptt_held else 0.6)
        radius_bump = int(amp * pulse)
        width_bump = w_amp * pulse

        ring = ACCENT2
        ring2 = ACCENT
        soft = BORDER

        def oval(r, width, color):
            c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=color, width=width)

        oval(r1 + radius_bump, 4 + width_bump, ring)
        oval(r2 + int(radius_bump * 0.7), 3 + width_bump, ring2)
        oval(r3 + int(radius_bump * 0.4), 2 + width_bump * 0.8, soft)

        c.create_text(cx, cy - 12, text="S A M U E L", fill=TEXT, font=("Menlo", 26, "bold"))
        c.create_text(cx, cy + 18, text="Push-To-Talk Interface", fill=MUTED, font=("Menlo", 12))

        if self._ptt_held:
            status_text = "● RECORDING"
            status_col = "#D3A09A"
        elif speaking:
            status_text = "● SPEAKING"
            status_col = ring
        else:
            status_text = "● READY"
            status_col = MUTED

        c.create_text(cx, cy + 54, text=status_text, fill=status_col, font=("Menlo", 12, "bold"))

    def _toggle_auto(self):
        self.auto_speak = not self.auto_speak
        self.auto_btn.config(text=f"AUTO SPEAK: {'ON' if self.auto_speak else 'OFF'}")

    def _ptt_press(self, _e=None):
        if self._ptt_held:
            return
        self._ptt_held = True
        self.ptt_btn.config(bg=ACCENT2, text="RECORDING...", fg="#11100F")
        self.status.config(text="● RECORDING", fg="#D3A09A")
        self.gui.set_presence("thinking", "curious")
        self.listener.start_ptt()

    def _ptt_release(self, _e=None):
        if not self._ptt_held:
            return
        self._ptt_held = False
        self.ptt_btn.config(bg=CARD, text="HOLD TO TALK", fg=TEXT)
        self.status.config(text="● PROCESSING...", fg=ACCENT)
        self.gui.set_presence("thinking", "curious")
        self.listener.stop_ptt()

    def _on_heard_text(self, text: str, lang: str):
        flag = "EN" if "en" in lang else "ES" if "es" in lang else "?"
        self._transcript_lbl.config(text=f"{flag} {text}")

        def send():
            self.gui.process_user_text(text)
        self.gui.root.after(0, send)

    def _send_from_voice(self):
        text = self.entry.get("1.0", "end-1c").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self.gui.process_user_text(text)

    def _on_enter_send(self, event):
        event.widget.tk.call("break")
        self._send_from_voice()

    def _on_shift_enter(self, event):
        self.entry.insert("insert", "\n")
        return "break"

    def _start_animation(self):
        if self._anim_job is not None:
            return
        self._animate()

    def _animate(self):
        self._pulse_phase += 0.18
        if self._pulse_phase > 6.283:
            self._pulse_phase -= 6.283
        self._draw_hud()
        self._anim_job = self.after(33, self._animate)

    def _on_close(self):
        try:
            self.listener.stop()
            self.listener._ptt_stop.set()
        except Exception:
            pass
        try:
            if self._anim_job is not None:
                self.after_cancel(self._anim_job)
        except Exception:
            pass
        self._anim_job = None
        self.destroy()


def open_voice_panel(gui):
    try:
        if getattr(gui, "voice_win", None) and gui.voice_win.winfo_exists():
            gui.voice_win.lift()
            return gui.voice_win
    except Exception:
        pass
    win = VoicePanel(gui)
    gui.voice_win = win
    return win
