# ui/voice_panel.py
# Voice panel — kept close to original design.
# Eyes open automatically in their own floating window when this opens.

import math
import threading
import tkinter as tk

from ui.theme import BG, PANEL, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2, ACCENT3
from tts_engine import SPEAKING_EVENT
from stt_engine import SpeechListener


class VoicePanel(tk.Toplevel):
    def __init__(self, gui):
        super().__init__(gui.root)
        self.gui = gui

        self.title("Samuel — Voice Mode")
        self.configure(bg=BG)
        self.geometry("820x620")
        self.minsize(720, 540)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.listening  = False
        self._resume_listening_after_ptt = False
        self.auto_speak = True
        self._ptt_held  = False



        self.listener = SpeechListener(self._on_heard_text, phrase_seconds=4.0)

        # Animation state
        self._pulse_phase = 0.0
        self._anim_job    = None

        # Build UI first (so self.hud exists)
        self._build()

        # Start animation AFTER widgets exist
        self.after(60, self._start_animation)

    # ------------------------------------------------------------------
    # UI BUILD  (matches original layout exactly)
    # ------------------------------------------------------------------
    def _build(self):
        # Header
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(18, 10))

        tk.Label(header, text="VOICE MODE",
                 bg=BG, fg=TEXT, font=("Menlo", 16, "bold")).pack(side="left")

        self.status = tk.Label(header, text="● READY",
                                bg=BG, fg=MUTED, font=("Menlo", 11, "bold"))
        self.status.pack(side="right")

        # Main layout
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=10)

        # Left: HUD ring
        left = tk.Frame(body, bg=PANEL,
                         highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.hud = tk.Canvas(left, bg=PANEL, highlightthickness=0)
        self.hud.pack(fill="both", expand=True, padx=12, pady=12)
        self.hud.bind("<Configure>", lambda _e: self._draw_hud())

        # Right: controls
        right = tk.Frame(body, bg=PANEL,
                          highlightbackground=BORDER, highlightthickness=1,
                          width=260)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        inner = tk.Frame(right, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(inner, text="Controls",
                 bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        # Auto speak toggle
        self.auto_btn = tk.Button(
            inner, text="AUTO SPEAK: ON",
            bg=ACCENT, fg="#11100F", relief="flat",
            font=("Menlo", 12, "bold"), command=self._toggle_auto
        )
        self.auto_btn.pack(fill="x", pady=(12, 6))

        # Always-on mic toggle
        self.mic_btn = tk.Button(
            inner, text="MIC: OFF",
            bg=CARD, fg=TEXT, relief="flat",
            font=("Menlo", 12, "bold"), command=self._toggle_mic
        )
        self.mic_btn.pack(fill="x", pady=6)

        # Eyes toggle button
        self.eyes_btn = tk.Button(
            inner, text="EYES: OFF",
            bg=CARD, fg=TEXT, relief="flat",
            font=("Menlo", 11, "bold"),
            command=self._toggle_eyes,
        )
        self.eyes_btn.pack(fill="x", pady=6)

        # Push to talk
        self.ptt_btn = tk.Button(
            inner, text="HOLD TO TALK",
            bg=CARD, fg=TEXT, relief="flat",
            font=("Menlo", 11, "bold"),
        )
        self.ptt_btn.pack(fill="x", pady=6)
        self.ptt_btn.bind("<ButtonPress-1>",   self._ptt_press)
        self.ptt_btn.bind("<ButtonRelease-1>",  self._ptt_release)

        tk.Label(inner,
                 text='Say "Hey Samuel" to activate,\nor hold button to talk.',
                 bg=PANEL, fg=MUTED, font=("Menlo", 10),
                 wraplength=220, justify="left").pack(anchor="w", pady=(10, 8))

        # Transcript label
        self._transcript_lbl = tk.Label(
            inner, text="", bg=PANEL, fg=ACCENT,
            font=("Menlo", 9), wraplength=220, justify="left"
        )
        self._transcript_lbl.pack(anchor="w", pady=(0, 8))

        # Text entry + send  (fallback)
        self.entry = tk.Text(
            inner, bg=CARD, fg=TEXT,
            insertbackground=ACCENT, relief="flat",
            font=("Menlo", 12), height=5, wrap="word"
        )
        self.entry.pack(fill="x", pady=(0, 10))
        self.entry.bind("<Return>",       self._on_enter_send)
        self.entry.bind("<Shift-Return>", self._on_shift_enter)

        tk.Button(inner, text="SEND",
                  bg=ACCENT3, fg="#11100F", relief="flat",
                  font=("Menlo", 12, "bold"),
                  command=self._send_from_voice).pack(fill="x")

    # ------------------------------------------------------------------
    # HUD  (original drawing code, untouched)
    # ------------------------------------------------------------------
    def _draw_hud(self):
        if not hasattr(self, "hud") or self.hud is None:
            return

        c = self.hud
        c.delete("all")

        w    = max(1, c.winfo_width())
        h    = max(1, c.winfo_height())
        size = max(120, min(w, h) - 40)

        cx, cy = w // 2, h // 2
        r1 = size // 2
        r2 = int(r1 * 0.82)
        r3 = int(r1 * 0.62)

        speaking = SPEAKING_EVENT.is_set()
        pulse    = (math.sin(self._pulse_phase) + 1.0) / 2.0

        amp        = 10 if speaking else (6 if self._ptt_held else 2)
        w_amp      = 2.0 if speaking else (1.5 if self._ptt_held else 0.6)
        radius_bump = int(amp * pulse)
        width_bump  = w_amp * pulse

        ring  = ACCENT2
        ring2 = ACCENT
        soft  = BORDER

        def oval(r, width, color):
            c.create_oval(cx-r, cy-r, cx+r, cy+r, outline=color, width=width)

        oval(r1 + radius_bump,          4 + width_bump, ring)
        oval(r2 + int(radius_bump*0.7), 3 + width_bump, ring2)
        oval(r3 + int(radius_bump*0.4), 2 + width_bump*0.8, soft)

        for i in range(60):
            ang   = (i / 60.0) * math.tau
            inner = r1 - (18 if i % 5 == 0 else 10)
            x1 = cx + inner * math.cos(ang)
            y1 = cy + inner * math.sin(ang)
            x2 = cx + r1    * math.cos(ang)
            y2 = cy + r1    * math.sin(ang)
            c.create_line(x1, y1, x2, y2, fill=soft,
                          width=2 if i % 5 == 0 else 1)

        c.create_text(cx, cy - 12, text="S A M U E L",
                      fill=TEXT, font=("Menlo", 26, "bold"))
        c.create_text(cx, cy + 18, text="British Voice Interface",
                      fill=MUTED, font=("Menlo", 12))

        if self._ptt_held:
            status_text = "● RECORDING"
            status_col  = "#D3A09A"
        elif speaking:
            status_text = "● SPEAKING"
            status_col  = ring
        elif self.listening:
            status_text = "● LISTENING"
            status_col  = ring
        else:
            status_text = "● READY"
            status_col  = MUTED

        c.create_text(cx, cy + 54, text=status_text,
                      fill=status_col, font=("Menlo", 12, "bold"))

    # ------------------------------------------------------------------
    # CONTROLS
    # ------------------------------------------------------------------
    def _toggle_auto(self):
        self.auto_speak = not self.auto_speak
        self.auto_btn.config(
            text=f"AUTO SPEAK: {'ON' if self.auto_speak else 'OFF'}"
        )

    def _toggle_mic(self):
        self.listening = not self.listening
        if self.listening:
            self.status.config(text="● LISTENING", fg=ACCENT2)
            self.listener.start()
            self.mic_btn.config(text="MIC: ON", bg=ACCENT, fg="#11100F")
        else:
            self.status.config(text="● READY", fg=MUTED)
            self.listener.stop()
            self.mic_btn.config(text="MIC: OFF", bg=CARD, fg=TEXT)
        self._draw_hud()

    def _ptt_press(self, _e=None):
        if self._ptt_held:
            return

        # ✅ Pause always-on so sounddevice isn't recording in 2 threads
        self._resume_listening_after_ptt = False
        if self.listening:
            self._resume_listening_after_ptt = True
            self.listener.stop()
            self.listening = False
            self.mic_btn.config(text="MIC: OFF", bg=CARD, fg=TEXT)

        self._ptt_held = True
        self.ptt_btn.config(bg=ACCENT2, text="RECORDING...", fg="#11100F")
        self.status.config(text="● RECORDING", fg="#D3A09A")
        self.listener.start_ptt()

    def _ptt_release(self, _e=None):
        if not self._ptt_held:
            return
        self._ptt_held = False
        self.ptt_btn.config(bg=CARD, text="HOLD TO TALK", fg=TEXT)
        self.status.config(text="● PROCESSING...", fg=ACCENT)
        self.listener.stop_ptt()

        # ✅ Resume always-on after PTT finishes (small delay so audio releases cleanly)
        if self._resume_listening_after_ptt:
            def _resume():
                self.listening = True
                self.status.config(text="● LISTENING", fg=ACCENT2)
                self.listener.start()
                self.mic_btn.config(text="MIC: ON", bg=ACCENT, fg="#11100F")
            self.after(600, _resume)

    def _on_heard_text(self, text: str, lang: str):
        flag = "EN" if "en" in lang else "ES" if "es" in lang else "?"
        self._transcript_lbl.config(text=f"{flag} {text}")

        # Set eyes to curious while thinking
        self._set_eyes("curious")

        def send():
            self.gui._user_say(text)
            self.gui.status.config(text="● THINKING...", fg=ACCENT2)
            threading.Thread(target=self.gui._respond,
                              args=(text,), daemon=True).start()
        self.gui.root.after(0, send)

    # ------------------------------------------------------------------
    # EYES WINDOW
    # ------------------------------------------------------------------
    def _toggle_eyes(self):
        from ui.eyes_window import open_eyes_window
        existing = getattr(self.gui, "eyes_win", None)
        try:
            if existing and existing.winfo_exists():
                existing._close()
                self.eyes_btn.config(text="EYES: OFF", bg=CARD, fg=TEXT)
                return
        except Exception:
            pass
        win = open_eyes_window(self.gui, parent_widget=self)
        self.eyes_win = win
        self.eyes_btn.config(text="EYES: ON", bg=ACCENT, fg="#11100F")

    def _open_eyes_window(self):
        """Auto-open eyes when voice panel opens."""
        pass   # now controlled by button only — user chooses when to open

    def _set_eyes(self, expression: str):
        """Set expression on the floating eyes window if open."""
        try:
            ew = getattr(self.gui, "eyes_win", None)
            if ew and ew.winfo_exists():
                self.gui.root.after(
                    0, lambda e=expression: ew.samuel_eyes.set_expression(e)
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # SENDING
    # ------------------------------------------------------------------
    def _send_from_voice(self):
        text = self.entry.get("1.0", "end-1c").strip()
        if not text:
            return
        self.entry.delete("1.0", "end")
        self.gui._user_say(text)
        self.gui.status.config(text="● THINKING...", fg=ACCENT2)
        threading.Thread(target=self.gui._respond,
                          args=(text,), daemon=True).start()

    def _on_enter_send(self, event):
        event.widget.tk.call("break")
        self._send_from_voice()

    def _on_shift_enter(self, event):
        self.entry.insert("insert", "\n")
        return "break"

    # ------------------------------------------------------------------
    # ANIMATION
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------
    def _on_close(self):
        # Close eyes window too
        try:
            if hasattr(self, "eyes_win") and self.eyes_win.winfo_exists():
                self.eyes_win.destroy()
        except Exception:
            pass
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