# gui_app.py
import os
import re
import time
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, filedialog

from tools import web_search_ddg, sniff_and_read_file, image_to_base64_png
from llm_ollama import ollama_chat, ollama_vision
from web_search import research

from training.memory_panel import open_memory_panel
from memory_autosave import auto_memory_capture
from memory_decay import start_decay_thread
from memory_decay       import start_decay_thread
from memory_retrieval   import build_smart_memory_pack, build_cross_chat_pack
from memory_filter      import should_remember, _is_ephemeral_text
from background_learner import start_learning_thread
from knowledge_store    import build_knowledge_context, init_knowledge_db

import samuel_store as store

from datetime import datetime

from training.personality_panel import open_personality_panel

from style_id import (
    bootstrap as style_bootstrap,
    predict_author as style_predict,
    online_update as style_update,
    OWNER_ME,
    UNKNOWN_BUCKET,
)
# --- GIF Reaction System ---
from reaction_gif_engine import (
    init_reaction_db,
    classify_message_mode,
    predict_reaction_and_gif,
    giphy_search_one_gif,
    build_social_text_prompt,
    save_feedback,
    list_examples,
    delete_example,
)

from ui.theme import (
    BG, PANEL, CARD,
    ACCENT, ACCENT2, ACCENT3,
    TEXT, MUTED, BORDER,
    BUBBLE_ME, BUBBLE_AI, BUBBLE_EDGE, TIME_FAINT,
    TEXT_MODEL, VISION_MODEL,
    DEFAULT_CHAT,
)

from ui.prompts import build_system_prompt
from ui.text_utils import (
    URL_RE,
    sanitize_markdown_links,
    now_ts, now_stamp, day_label,
    is_image, is_doc, clean_chat_name,
)
from ui.scroll import is_near_bottom, scroll_to_bottom, refresh_scrollregion, bind_mousewheel, bind_keyboard_scroll
from ui.chats_panel import open_chats_panel

from ui.clipboard import enable_clipboard_shortcuts

from ui.voice_panel import open_voice_panel
from tts_engine import speak_async

from samuel_eyes import detect_voice_command, EMOTION_MAP, predict_emotion

from contacts_autosave import auto_detect_and_queue, save_contact_from_candidate
from contacts_store import init_contacts_db, build_contacts_context

from action_handler import (
    ActionState, detect_intent, is_confirmation, is_cancellation,
    handle_calendar_check, handle_email_draft, handle_email_send,
    handle_calendar_add, handle_calendar_confirm,
)

class SamuelGUI:
    def __init__(self, root: tk.Tk):
        # DB init (creates tables)
        store.init_db()

        init_knowledge_db()
        init_contacts_db()
        self.action_state = ActionState()
        start_decay_thread(verbose=True)
        # start_learning_thread(verbose=True)

        start_decay_thread(verbose=True)

        # Style-ID boot
        self.style_model, self.style_labels = style_bootstrap()
        self.pending_style_check = None
        self.pending_relation_name = None

        self.root = root
        self.root.title("SAMUEL")
        self.root.configure(bg=BG)
        self.root.geometry("980x720")
        self.root.minsize(860, 580)

        style = ttk.Style()
        style.theme_use("clam")

        self.current_chat_name = DEFAULT_CHAT
        self.current_chat_id = store.get_or_create_chat(self.current_chat_name)

        self.last_sources = []
        self.placeholder_text = "Type here..."

        # Eyes window reference
        self.eyes_win = None

        self._build_layout()
        enable_clipboard_shortcuts(self.root)
        self.entry.focus_set()
        self._load_chat_to_ui()

        self.store = store
        self.memory_mode = False
        self.memory_panel = None  

        self._last_assistant_text = ""
        self._last_assistant_ts = 0

        self.personality_mode = False
        self.personality_win = None
        self.voice_win = None

        # GIF reaction engine
        self._gif_refs = []   # keep animated GIF frames alive
        self._samuel_day_state = "neutral"   # good / bad / neutral / blessed / thoughtful

    def get_local_datetime_context(self):
        from datetime import datetime
        now = datetime.now().astimezone()
        return {
            "date": now.strftime("%B %d, %Y").replace(" 0", " "),
            "weekday": now.strftime("%A"),
            "time": now.strftime("%I:%M %p").lstrip("0"),
            "timezone": now.tzname() or "local time",
            "iso": now.isoformat(),
        }

    # -------------------------------------------------------
    # Input helpers
    # -------------------------------------------------------
    def _get_input_text(self) -> str:
        return self.entry.get("1.0", "end-1c")

    def _clear_input(self):
        self.entry.delete("1.0", "end")
        self._auto_resize_input()

    def _on_enter_send(self, _e=None):
        self.send_message()
        return "break"

    def _on_shift_enter_newline(self, _e=None):
        self.entry.insert("insert", "\n")
        self._auto_resize_input()
        return "break"

    def _auto_resize_input(self, _e=None):
        try:
            display_lines = int(self.entry.count("1.0", "end-1c", "displaylines")[0])
        except Exception:
            display_lines = int(self.entry.index("end-1c").split(".")[0])
        new_h = max(1, min(6, display_lines))
        self.entry.configure(height=new_h)
        try:
            self.entry.see("insert")
        except Exception:
            pass

    # -------------------------------------------------------
    # Eyes helpers
    # -------------------------------------------------------
    def _set_eyes(self, expression: str):
        """Set Samuel's eye expression if eyes window is open."""
        try:
            ew = getattr(self, "eyes_win", None)
            if ew and ew.winfo_exists():
                self.root.after(0, lambda e=expression: ew.samuel_eyes.set_expression(e))
        except Exception:
            pass

    def _toggle_eyes_window(self):
        """Open or close the floating eyes window."""
        from ui.eyes_window import open_eyes_window
        ew = getattr(self, "eyes_win", None)
        try:
            if ew and ew.winfo_exists():
                ew._close()
                try:
                    self._eyes_lbl.config(fg=MUTED)
                except Exception:
                    pass
                return
        except Exception:
            pass
        open_eyes_window(self, parent_widget=self.root)
        try:
            self._eyes_lbl.config(fg=ACCENT)
        except Exception:
            pass

    def _react_eyes_to_reply(self, reply: str):
        """In background thread: scan reply for emotion, update eyes."""
        def _worker(resp=reply):
            try:
                ew = getattr(self, "eyes_win", None)
                if not ew:
                    return
                try:
                    if not ew.winfo_exists():
                        return
                except Exception:
                    return
                # Quick keyword scan first (instant, no LLM call)
                detected = None
                for w in resp.lower().split():
                    clean = w.strip(".,!?\"'")
                    if clean in EMOTION_MAP:
                        detected = EMOTION_MAP[clean]
                        break
                if detected:
                    self._set_eyes(detected)
                else:
                    # Ask LLM in background (non-blocking)
                    try:
                        def _llm(msgs, temperature=0.2):
                            return ollama_chat(TEXT_MODEL, msgs, temperature=temperature)
                        expr = predict_emotion(resp, _llm)
                        self._set_eyes(expr)
                    except Exception:
                        self._set_eyes("neutral")
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    # -------------------------------------------------------
    # Thin wrappers used by ui/chats_panel.py
    # -------------------------------------------------------
    def list_chats(self):
        return store.list_chats()

    def get_or_create_chat(self, name: str):
        return store.get_or_create_chat(name)

    def delete_chat(self, name: str):
        return store.delete_chat(name)

    # -------------------------------------------------------
    # UI BUILD
    # -------------------------------------------------------
    def _build_layout(self):
        # Header
        self.header = tk.Canvas(self.root, bg=BG, highlightthickness=0, height=120)
        self.header.pack(fill="x", padx=18, pady=(18, 10))
        self._draw_header()

        # Main scrollable chat area
        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(fill="both", expand=True, padx=18, pady=8)

        self.chat_canvas = tk.Canvas(self.main, bg=PANEL, highlightthickness=0, takefocus=1)
        self.chat_canvas.bind("<Enter>", lambda e: self.chat_canvas.focus_set())
        self.chat_canvas.pack(side="left", fill="both", expand=True)

        self.scrollbar = ttk.Scrollbar(self.main, orient="vertical", command=self.chat_canvas.yview)
        self.scrollbar.pack(side="right", fill="y")
        self.chat_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.chat_frame = tk.Frame(self.chat_canvas, bg=PANEL)
        self.chat_window = self.chat_canvas.create_window((0, 0), window=self.chat_frame, anchor="nw")

        self.chat_frame.bind("<Configure>", self._on_frame_configure)
        self.chat_canvas.bind("<Configure>", self._on_canvas_configure)

        bind_mousewheel(self.root, self.chat_canvas, self.chat_frame)
        bind_keyboard_scroll(self.root, self.chat_canvas)

        # Bottom bar
        self.bottom = tk.Frame(self.root, bg=BG)
        self.bottom.pack(fill="x", padx=18, pady=(12, 18))

        self.input_bar = tk.Frame(self.bottom, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.input_bar.pack(fill="x")

        # Controls
        self.controls = tk.Frame(self.input_bar, bg=CARD)
        self.controls.pack(side="left", padx=(12, 6), pady=12)

        self.chats_link = tk.Label(self.controls, text="CHATS", bg=CARD, fg=MUTED, cursor="hand2",
                                   font=("Menlo", 12, "bold"))
        self.chats_link.pack(side="left", padx=(0, 14))
        self.chats_link.bind("<Button-1>", lambda _e: self.open_chats_panel())

        self.attach_link = tk.Label(self.controls, text="ATTACH", bg=CARD, fg=ACCENT2, cursor="hand2",
                                    font=("Menlo", 12, "bold"))
        self.attach_link.pack(side="left", padx=(0, 14))
        self.attach_link.bind("<Button-1>", lambda _e: self.attach_file())

        self.web_link = tk.Label(self.controls, text="WEB", bg=CARD, fg=ACCENT, cursor="hand2",
                                 font=("Menlo", 12, "bold"))
        self.web_link.pack(side="left")
        self.web_link.bind("<Button-1>", lambda _e: self.web_search_prompt())

        init_reaction_db()
        self._gif_refs = []

        # Voice mode (sound icon) — UNCHANGED from original
        self.voice_link = tk.Label(
            self.controls,
            text="VOICE",
            bg=CARD,
            fg=ACCENT2,
            cursor="hand2",
            font=("Menlo", 12, "bold")
        )
        self.voice_link.pack(side="left", padx=(14, 0))
        self.voice_link.bind("<Button-1>", lambda _e: self.open_voice_panel())

        class _GIFTrackerBridge:
            def predict_reaction_and_gif(self, text):
                return predict_reaction_and_gif(text)

            def giphy_search_one_gif(self, prompt):
                return giphy_search_one_gif(prompt)

            def save_feedback(self, **kwargs):
                return save_feedback(**kwargs)

            def list_examples(self):
                return list_examples()

            def delete_example(self, row_id):
                return delete_example(row_id)

        self._gif_engine = _GIFTrackerBridge()
        self._gif_refs = []

        # EYES label — opens floating eyes window from main chat
        self._eyes_lbl = tk.Label(
            self.controls,
            text="EYES",
            bg=CARD,
            fg=MUTED,
            cursor="hand2",
            font=("Menlo", 12, "bold")
        )
        self._eyes_lbl.pack(side="left", padx=(14, 0))
        self._eyes_lbl.bind("<Button-1>", lambda _e: self._toggle_eyes_window())

        # Entry (multi-line input)
        self.entry = tk.Text(
            self.input_bar,
            bg=CARD,
            fg=TEXT,
            insertbackground=ACCENT,
            relief="flat",
            font=("Menlo", 14),
            height=1,
            wrap="word",
            undo=True
        )
        self.entry.pack(side="left", fill="both", expand=True, padx=(8, 10), pady=12)

        self.entry.bind("<Return>", self._on_enter_send)
        self.entry.bind("<Shift-Return>", self._on_shift_enter_newline)
        self.entry.bind("<KeyRelease>", self._auto_resize_input)

        self._install_text_placeholder(self.placeholder_text)

        self.send_btn = tk.Button(
            self.input_bar,
            text="SEND",
            bg=ACCENT,
            fg="#11100F",
            activebackground="#88A7A2",
            relief="flat",
            font=("Menlo", 12, "bold"),
            command=self.send_message
        )
        self.send_btn.pack(side="right", padx=(0, 12), pady=10, ipadx=10, ipady=4)

        self.status = tk.Label(self.root, text="● ONLINE", bg=BG, fg=MUTED, font=("Menlo", 11))
        self.status.pack(anchor="w", padx=22, pady=(0, 10))

    def _draw_header(self):
        self.header.delete("all")
        w = self.header.winfo_width() or 980
        h = 120

        for x in range(0, w, 46):
            self.header.create_line(x, 0, x, h, fill="#1B1512")
        for y in range(0, h, 26):
            self.header.create_line(0, y, w, y, fill="#1B1512")

        self.header.create_line(18, 22, w - 18, 22, fill=ACCENT, width=3)
        self.header.create_line(18, 22, 18, 98, fill=ACCENT, width=3)
        self.header.create_line(18, 98, 46, 98, fill=ACCENT, width=3)
        self.header.create_line(18, 52, 36, 52, fill=ACCENT, width=3)

        self.header.create_text(70, 52, text="SAMUEL", fill=TEXT, font=("Menlo", 34, "bold"), anchor="w")
        self.header.create_text(70, 78, text=f"CHAT: {self.current_chat_name}", fill=MUTED, font=("Menlo", 12), anchor="w")

        self.header.create_text(w - 30, 48, text=f"TEXT: {TEXT_MODEL}", fill=MUTED, font=("Menlo", 12), anchor="e")
        self.header.create_text(w - 30, 72, text=f"VISION: {VISION_MODEL}", fill=MUTED, font=("Menlo", 12), anchor="e")

    def _refresh_header(self):
        self._draw_header()

    def _direct_personal_answer(self, user_text: str):
        t = user_text.strip().lower()

        if re.search(r"\bwhat('?s| is)\s+my\s+name\b|\bwhats\s+my\s+name\b", t):
            val = None
            for key in ("name", "full_name"):
                try:
                    val = store.get_memory_value("user", "profile", key)
                except Exception:
                    val = None
                if val:
                    break
            if val:
                return f"Your name is {val}."
            return "I don't have your name saved yet. Tell me: \"My name is ...\" and I'll remember it."

        if re.search(r"\bwhere\s+do\s+i\s+live\b|\bwhat('?s| is)\s+my\s+location\b", t):
            try:
                val = store.get_memory_value("user", "profile", "location")
            except Exception:
                val = None
            if val:
                return f"You live in {val}."
            return "I don't have your location saved yet. Tell me: \"I live in ...\" and I'll remember it."

        if re.search(r"\bwhat('?s| is)\s+my\s+major\b", t):
            try:
                val = store.get_memory_value("user", "profile", "major")
            except Exception:
                val = None
            if val:
                return f"Your major is {val}."
            return "I don't have your major saved yet. Tell me: \"My major is ...\" and I'll remember it."

        return None

    def open_voice_panel(self):
        self.voice_win = open_voice_panel(self)

    # -------------------------------------------------------
    # Placeholder
    # -------------------------------------------------------
    def _install_text_placeholder(self, text: str):
        self.placeholder_text = text
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", self.placeholder_text)
        self.entry.tag_add("placeholder", "1.0", "end")
        self.entry.tag_config("placeholder", foreground=MUTED)
        self.entry.mark_set("insert", "1.0")

        def clear(_e=None):
            current = self._get_input_text()
            if current == self.placeholder_text:
                self.entry.delete("1.0", "end")
                self.entry.tag_remove("placeholder", "1.0", "end")
                self.entry.configure(fg=TEXT)

        def restore(_e=None):
            if not self._get_input_text().strip():
                self.entry.delete("1.0", "end")
                self.entry.insert("1.0", self.placeholder_text)
                self.entry.tag_add("placeholder", "1.0", "end")
                self.entry.tag_config("placeholder", foreground=MUTED)
                self.entry.mark_set("insert", "1.0")

        self.entry.bind("<FocusIn>", clear)
        self.entry.bind("<FocusOut>", restore)
        self.entry.bind("<KeyPress>", lambda _e: clear(), add=True)

    # -------------------------------------------------------
    # Scroll / resize hooks
    # -------------------------------------------------------
    def _on_frame_configure(self, _event=None):
        refresh_scrollregion(self.root, self.chat_canvas)

    def _on_canvas_configure(self, event):
        self.chat_canvas.itemconfig(self.chat_window, width=event.width)
        refresh_scrollregion(self.root, self.chat_canvas)

    def _scroll_to_bottom(self):
        scroll_to_bottom(self.root, self.chat_canvas)

    def _is_near_bottom(self) -> bool:
        return is_near_bottom(self.chat_canvas)

    # -------------------------------------------------------
    # Chat render
    # -------------------------------------------------------
    def _clear_chat_ui(self):
        for child in self.chat_frame.winfo_children():
            child.destroy()

    def _load_chat_to_ui(self):
        self._clear_chat_ui()

        msgs = store.get_messages(self.current_chat_id, limit=80)
        if not msgs:
            self.add_day_separator(now_ts())
            self.add_bubble("SAMUEL", "Online. Talk to me.", is_user=False, ts=now_ts(), force_scroll=True)
            self._refresh_header()
            self.root.after(1, self._scroll_to_bottom)
            return

        last_day = None
        for m in msgs:
            d = day_label(m["ts"])
            if d != last_day:
                self.add_day_separator(m["ts"])
                last_day = d

            self.add_bubble(
                "YOU" if m["role"] == "user" else "SAMUEL",
                m["content"],
                is_user=(m["role"] == "user"),
                ts=m["ts"],
                force_scroll=False,
            )

        self._refresh_header()
        self.root.after(1, self._scroll_to_bottom)

    def add_day_separator(self, ts: int):
        row = tk.Frame(self.chat_frame, bg=PANEL)
        row.pack(fill="x", padx=14, pady=(14, 6))
        label = tk.Label(
            row,
            text=day_label(ts),
            bg=PANEL,
            fg=TIME_FAINT,
            font=("Menlo", 11, "bold"),
            pady=2
        )
        label.pack()

    def add_bubble(self, who: str, text: str, is_user: bool, ts: int, force_scroll: bool = False):
        should_scroll = force_scroll or self._is_near_bottom()

        row = tk.Frame(self.chat_frame, bg=PANEL)
        row.pack(fill="x", padx=14, pady=8)

        side = "right" if is_user else "left"
        anchor = "e" if is_user else "w"
        bubble_bg = BUBBLE_ME if is_user else BUBBLE_AI

        bubble = tk.Frame(row, bg=bubble_bg, highlightbackground=BUBBLE_EDGE, highlightthickness=1)
        bubble.pack(side=side, anchor=anchor, padx=8)

        name = tk.Label(
            bubble,
            text=("YOU" if is_user else who),
            bg=bubble_bg,
            fg=(ACCENT if is_user else ACCENT2),
            font=("Menlo", 11, "bold"),
            padx=12,
            pady=6,
            anchor="w"
        )
        name.pack(fill="x")

        self._render_message_with_links(bubble, text, bubble_bg)

        tk.Frame(bubble, bg=bubble_bg, height=4).pack(fill="x")

        ts_lbl = tk.Label(
            bubble,
            text=now_stamp(ts),
            bg=bubble_bg,
            fg=TIME_FAINT,
            font=("Menlo", 10),
            padx=12,
            pady=6,
            anchor="e"
        )
        ts_lbl.pack(fill="x")

        self.root.update_idletasks()
        if should_scroll:
            self.root.after(1, self._scroll_to_bottom)

    def add_gif_bubble_from_url(self, gif_url: str, label: str = "SAMUEL", force_scroll: bool = True):
        import requests
        from io import BytesIO
        from PIL import Image, ImageTk, ImageSequence

        should_scroll = force_scroll or self._is_near_bottom()

        row = tk.Frame(self.chat_frame, bg=PANEL)
        row.pack(fill="x", padx=14, pady=4)

        bubble = tk.Frame(row, bg=BUBBLE_AI, highlightbackground=BUBBLE_EDGE, highlightthickness=1)
        bubble.pack(side="left", anchor="w", padx=8)

        tk.Label(
            bubble,
            text=label,
            bg=BUBBLE_AI,
            fg=ACCENT2,
            font=("Menlo", 11, "bold"),
            padx=12,
            pady=4,
            anchor="w"
        ).pack(fill="x")

        try:
            response = requests.get(gif_url, timeout=20)
            response.raise_for_status()

            img = Image.open(BytesIO(response.content))
            frames = []
            delays = []

            for frame in ImageSequence.Iterator(img):
                fr = frame.copy().convert("RGBA")
                fr.thumbnail((280, 280))
                frames.append(ImageTk.PhotoImage(fr))
                delay = frame.info.get("duration", 90)
                if not isinstance(delay, int) or delay <= 0:
                    delay = 90
                delays.append(delay)

            if not frames:
                raise ValueError("No GIF frames found.")

            self._gif_refs.extend(frames)

            lbl = tk.Label(bubble, bg=BUBBLE_AI, image=frames[0])
            lbl.pack(padx=12, pady=6)

            def _animate(idx=0):
                try:
                    if lbl.winfo_exists():
                        lbl.config(image=frames[idx % len(frames)])
                        self.root.after(delays[idx % len(delays)], _animate, idx + 1)
                except Exception:
                    pass

            if len(frames) > 1:
                self.root.after(delays[0], _animate, 1)

        except Exception as e:
            tk.Label(
                bubble,
                text=f"[GIF preview failed: {e}]",
                bg=BUBBLE_AI,
                fg=MUTED,
                font=("Menlo", 11),
                padx=12,
                pady=6
            ).pack()

        self.root.update_idletasks()
        if should_scroll:
            self.root.after(1, self._scroll_to_bottom)

    def _render_message_with_links(self, parent, text: str, bubble_bg: str):
        import tkinter.font as tkfont
        import webbrowser

        canvas_w = self.chat_canvas.winfo_width() or 900
        wrap_px = max(360, min(760, canvas_w - 220))

        body = tk.Frame(parent, bg=bubble_bg)
        body.pack(fill="x", expand=True)

        menu = tk.Menu(self.root, tearoff=0)

        def copy_all():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()

        menu.add_command(label="Copy", command=copy_all)

        def popup(e):
            try:
                menu.tk_popup(e.x_root, e.y_root)
            finally:
                menu.grab_release()

        msg_lbl = tk.Label(
            body,
            text=text,
            bg=bubble_bg,
            fg=TEXT,
            font=("Menlo", 13),
            justify="left",
            wraplength=wrap_px,
            padx=12,
            pady=6
        )
        msg_lbl.pack(anchor="w", fill="x", expand=True)

        msg_lbl.bind("<Button-3>", popup)
        msg_lbl.bind("<Control-Button-1>", popup)
        body.bind("<Button-3>", popup)
        body.bind("<Control-Button-1>", popup)

        urls = URL_RE.findall(text)
        seen = set()
        urls = [u for u in urls if not (u in seen or seen.add(u))]
        if urls:
            links_frame = tk.Frame(body, bg=bubble_bg)
            links_frame.pack(anchor="w", padx=12, pady=(0, 6), fill="x")

            tk.Label(
                links_frame,
                text="Links:",
                bg=bubble_bg,
                fg=MUTED,
                font=("Menlo", 11, "bold")
            ).pack(anchor="w")

            link_font = tkfont.Font(family="Menlo", size=12, underline=True)

            for u in urls[:8]:
                l = tk.Label(
                    links_frame,
                    text=u,
                    bg=bubble_bg,
                    fg=ACCENT,
                    cursor="hand2",
                    font=link_font,
                    wraplength=wrap_px,
                    justify="left"
                )
                l.pack(anchor="w", pady=(2, 0))

                l.bind("<Button-1>", lambda _e, url=u: webbrowser.open(url))
                l.bind("<Button-3>", popup)
                l.bind("<Control-Button-1>", popup)

    # -------------------------------------------------------
    # Chats Panel
    # -------------------------------------------------------
    def open_chats_panel(self):
        open_chats_panel(self)

    def _switch_chat(self, name: str):
        name = clean_chat_name(name)
        self.current_chat_name = name
        self.current_chat_id = store.get_or_create_chat(name)
        self._load_chat_to_ui()
        self._refresh_header()

    # -------------------------------------------------------
    # Identity logic (style-id)
    # -------------------------------------------------------
    def _parse_identity_reply(self, text: str) -> dict:
        t = text.strip()
        tl = t.lower()

        yes_phrases = [
            "yes", "y", "yeah", "yep",
            "yes its me", "yes it's me",
            "still me", "still amairani",
            "i'm amairani", "im amairani",
            "yes im just tired", "yes i'm just tired",
            "im just tired", "i'm just tired",
        ]
        if any(tl == p or tl.startswith(p + " ") for p in yes_phrases):
            return {"type": "yes", "name": None}

        m = re.search(
            r"(?i)\b(?:no[, ]*)?(?:this is|i am|i'm|im|this is my friend|my friend|friend)\s+([A-Za-z][A-Za-z\-']{1,30})\b",
            t
        )
        if m:
            name = m.group(1).strip()
            if name.lower() not in {"me", "amairani"}:
                return {"type": "named_other", "name": name}

        no_phrases = [
            "no", "n", "nope",
            "not me", "that wasn't me", "that wasnt me",
            "not amairani", "not amirani",
        ]
        if any(tl == p or tl.startswith(p + " ") for p in no_phrases):
            return {"type": "no", "name": None}

        return {"type": None, "name": None}

    def _maybe_train_from_confirmation(self, user_text: str) -> bool:
        if not self.pending_style_check:
            return False

        parsed = self._parse_identity_reply(user_text)
        if not parsed["type"]:
            return False

        original_text = self.pending_style_check["text"]

        if parsed["type"] == "yes":
            self.style_model, self.style_labels = style_update(
                self.style_model, self.style_labels, original_text, OWNER_ME
            )
            self._system_say("Very good, Miss. Thank you. I'll adjust my certainty accordingly.")
            self.pending_style_check = None
            return True

        self.style_model, self.style_labels = style_update(
            self.style_model, self.style_labels, original_text, UNKNOWN_BUCKET
        )

        if parsed["type"] == "named_other" and parsed["name"]:
            name = parsed["name"]
            store.upsert_saved_memory(
                owner="user",
                category="relationships",
                key=f"{name}_tag",
                value=f"{name} is known to Amairani.",
                stability="adaptive",
                importance=1.2,
                confidence=0.7,
                source="chat",
            )
            self.pending_relation_name = name
            self._system_say(
                f"Understood. Pleasure to meet you, {name}.\n"
                f"If you don't mind me asking — what is your relation to Amairani? (friend, classmate, coworker, etc.)"
            )
            self.pending_style_check = None
            return True

        self._system_say("Understood. I'll treat that style as not you going forward.")
        self.pending_style_check = None
        return True

    # -------------------------------------------------------
    # Memory helpers
    # -------------------------------------------------------
    def _get_memory_settings(self) -> dict:
        try:
            use_saved = store.get_setting("use_saved_memory", "1") == "1"
        except Exception:
            use_saved = True
        try:
            ref_hist = store.get_setting("reference_chat_history", "1") == "1"
        except Exception:
            ref_hist = True
        try:
            training = store.get_setting("training_mode", "0") == "1"
        except Exception:
            training = False

        return {
            "use_saved_memory": use_saved,
            "reference_chat_history": ref_hist,
            "training_mode": training,
        }

    def _passive_memory_capture(self, text):
        import re
        t = text.strip()
        m = re.search(r"(?i)\bmy name is\b\s+(.+)$", t)
        if m:
            name = m.group(1).strip().rstrip(".!")
            if 2 <= len(name) <= 60:
                ok, _ = should_remember("profile","name",name,source_text=t,importance=2.0)
                if ok:
                    store.upsert_saved_memory(owner="user",category="profile",key="name",
                        value=name,stability="core",importance=2.0,confidence=0.9,source="chat")

    def _chat_history_snips(self, query: str, limit: int = 8) -> str:
        q = (query or "").strip().lower()
        if not q:
            return ""

        words = [w for w in re.findall(r"[a-zA-Z]{3,}", q) if w not in {"that", "this", "with", "from", "your", "have"}]
        words = words[:8]
        if not words:
            return ""

        msgs = store.get_messages(self.current_chat_id, limit=120)
        hits = []
        for m in msgs[:-12]:
            c = (m.get("content") or "").lower()
            if any(w in c for w in words):
                snippet = (m.get("content") or "").strip().replace("\n", " ")
                if len(snippet) > 220:
                    snippet = snippet[:220] + "..."
                hits.append(f"- {m.get('role')}: {snippet}")
                if len(hits) >= limit:
                    break
        return "\n".join(hits)

    def _saved_memory_pack(self, user_text: str, limit: int = 14) -> str:
        core_rows = store.list_saved_memories(owner="user", limit=300)

        always = []
        for r in core_rows:
            if (r.get("stability") == "temporary"):
                continue
            imp = float(r.get("importance") or 1.0)
            if r.get("stability") == "core" or imp >= 1.2:
                always.append(r)

        always = always[:10]
        targeted = store.search_saved_memories(user_text, owner="user", limit=12)

        seen = set()
        final = []
        for h in (always + targeted):
            k = (h.get("owner"), h.get("mkey"))
            if k in seen:
                continue
            seen.add(k)
            final.append(h)
            if len(final) >= limit:
                break

        lines = []
        for h in final:
            mk = h.get("mkey", "notes.item")
            val = (h.get("value") or "").strip()
            stab = h.get("stability", "adaptive")
            imp = float(h.get("importance") or 1.0)
            conf = float(h.get("confidence") or 0.7)
            lines.append(f"- {mk} = {val} (stability={stab}, imp={imp:.2f}, conf={conf:.2f})")

        return "\n".join(lines)

    def _memory_pack(self, user_text):
        if _is_ephemeral_text(user_text):
            return ""
        s = self._get_memory_settings()
        parts = []
        if s["use_saved_memory"]:
            saved = build_smart_memory_pack(user_text, owner="user", max_items=12)
            if saved.strip(): parts.append(saved)
        contacts = build_contacts_context(user_text)
        if contacts.strip():
            parts.append(contacts)
        if s["reference_chat_history"]:
            hist = self._chat_history_snips(user_text)
            if hist.strip(): parts.append("RELEVANT CHAT HISTORY:\n" + hist)
            cross = build_cross_chat_pack(user_text, current_chat_id=self.current_chat_id, limit=4)
            if cross.strip(): parts.append(cross)
        knowledge = build_knowledge_context(user_text, max_nuggets=5)
        if knowledge.strip(): parts.append(knowledge)
        return "\n\n".join(parts).strip()

    # -------------------------------------------------------
    # System/user say
    # -------------------------------------------------------
    def _maybe_add_date_separator_for_ts(self, ts: int):
        msgs = store.get_messages(self.current_chat_id, limit=1)
        if not msgs:
            self.add_day_separator(ts)
            return
        last_ts = msgs[-1]["ts"]
        if day_label(last_ts) != day_label(ts):
            self.add_day_separator(ts)

    def _system_say(self, text: str):
        ts = now_ts()
        self._maybe_add_date_separator_for_ts(ts)
        self.add_bubble("SAMUEL", text, is_user=False, ts=ts, force_scroll=True)
        self.root.after(1, self._scroll_to_bottom)

    def _user_say(self, text: str):
        ts = now_ts()
        self._maybe_add_date_separator_for_ts(ts)
        self.add_bubble("YOU", text, is_user=True, ts=ts, force_scroll=True)
        store.add_message(self.current_chat_id, "user", text, ts=ts)
        self.root.after(1, self._scroll_to_bottom)

    def _assistant_say(self, text: str):
        ts = now_ts()
        self._maybe_add_date_separator_for_ts(ts)

        text = sanitize_markdown_links(text or "")
        cleaned = text.replace("**", "").replace("*", "").strip()

        if not cleaned:
            return

        now = ts
        if not hasattr(self, "_last_assistant_text"):
            self._last_assistant_text = ""
            self._last_assistant_ts = 0

        if cleaned == self._last_assistant_text and (now - self._last_assistant_ts) <= 2:
            return

        self._last_assistant_text = cleaned
        self._last_assistant_ts = now

        self.add_bubble("SAMUEL", cleaned, is_user=False, ts=ts, force_scroll=True)
        store.add_message(self.current_chat_id, "assistant", cleaned, ts=ts)
        self.root.after(1, self._scroll_to_bottom)

        # Speak if voice window open + autospeak enabled
        try:
            vw = getattr(self, "voice_win", None)
            if vw and vw.winfo_exists() and getattr(vw, "auto_speak", False):
                from tts_engine import speak_async
                speak_async(cleaned)
        except Exception as e:
            print("[TTS] speak failed:", e)

        # Eyes react to Samuel's reply
        # self._react_eyes_to_reply(cleaned)

    def _is_social_reactive_message(self, user_text: str) -> bool:
        t = user_text.strip().lower()

        social_patterns = [
            r"\bhow are you\b",
            r"\bhow was your day\b",
            r"\bwhat are you doing\b",
            r"\bwhat's up\b",
            r"\bwyd\b",
            r"\bi am\b",
            r"\bi'm\b",
            r"\bi feel\b",
            r"\bguess what\b",
            r"\bi'm bored\b",
            r"\bi am bored\b",
            r"\bi'm excited\b",
            r"\bi am excited\b",
            r"\bi'm nervous\b",
            r"\bi am nervous\b",
            r"\bi brought you\b",
            r"\bdo you like\b",
            r"\bare you okay\b",
            r"\bare you doing okay\b",
        ]

        if any(re.search(p, t) for p in social_patterns):
            return True

        # if it looks like a hard factual question, don't treat as social
        factual_patterns = [
            r"\bwhat is\b", r"\bwho is\b", r"\bwhen is\b", r"\bwhere is\b",
            r"\bhow do i\b", r"\blook up\b", r"\bsearch\b", r"\blatest\b",
            r"\bfix this\b", r"\berror\b", r"\bcalculate\b"
        ]
        if any(re.search(p, t) for p in factual_patterns):
            return False

        # If the GIF engine has a strong match, allow it
        if self._gif_engine:
            try:
                result = self._gif_engine.match(user_text)
                if result and result.get("confidence", 0) >= 0.75:
                    return True
            except Exception:
                pass

        return False


    def _samuel_state_reaction(self, user_text: str):
        t = user_text.strip().lower()

        if "how are you" in t or "how was your day" in t:
            state_map = {
                "good": ("good", "Doing rather well, actually. Talking with you helps."),
                "bad": ("bad", "I've had a slightly rough time, but I'm still here with you."),
                "neutral": ("neutral", "I'm steady. Not bad, not brilliant — just here with you."),
                "blessed": ("blessed", "Blessed, truly. And grateful to be here with you."),
                "thoughtful": ("thoughtful", "A little thoughtful today, but present."),
            }
            return state_map.get(self._samuel_day_state, state_map["neutral"])

        if "what are you doing" in t:
            return ("thoughtful", "Thinking, learning, and keeping you company.")

        return None

    # -------------------------------------------------------
    # Web / Attach
    # -------------------------------------------------------
    def web_search_prompt(self):
        txt = self.entry.get("1.0", "end-1c").strip()
        if txt and txt != self.placeholder_text:
            self.entry.delete("1.0", "end")
            self._user_say(f"web: {txt}")
            self._run_web_search(txt)
        else:
            self._system_say("Type a query then click WEB, or type: web: your question")

    def _run_web_search(self, query: str):
        self.status.config(text="● SEARCHING...", fg=ACCENT)
        threading.Thread(target=self._web_worker, args=(query,), daemon=True).start()

    from web_search import research

    def _web_worker(self, query: str):
        try:
            sources = research(query, max_results=10, fetch_top_k=5)
        except Exception as e:
            self.root.after(0, lambda: self._finish_web(f"Web search error:\n{e}", []))
            return
        self.root.after(0, lambda: self._finish_web(query, sources))

        def _finish_web(self, query: str, sources):
            if not sources:
                self._assistant_say(f"Searched: {query}\n\nNo good sources found.")
                self.status.config(text="● ONLINE", fg=MUTED)
                return

            def is_blocked(u: str) -> bool:
                u = (u or "").lower()
                return ("wikipedia.org" in u) or ("wikidata.org" in u) or ("wikimedia.org" in u) or ("fandom.com" in u) or ("wikia.com" in u)

            sources = [s for s in sources if s.get("url") and not is_blocked(s["url"])]

            seen = set()
            deduped = []
            for s in sources:
                url = s["url"].strip()
                if url in seen:
                    continue
                seen.add(url)
                deduped.append(s)
            sources = deduped

            evidence_lines = [f"User question: {query}", "", "SOURCES:"]
            for i, s in enumerate(sources, 1):
                title = (s.get("title") or "").strip()
                text = (s.get("text") or "")[:2500]
                evidence_lines.append(f"\n[{i}] {title}\nEXTRACT:\n{text}")

            evidence = "\n".join(evidence_lines)

            prompt = (
                "You are Samuel, a research assistant.\n"
                "Answer the user's question using ONLY the sources provided.\n"
                "Rules:\n"
                "- Do NOT use Wikipedia or any wiki/fandom sources.\n"
                "- Do NOT invent sources.\n"
                "- Do NOT include raw URLs in your answer.\n"
                "- Use citations like [1], [2] for claims.\n"
                "- If sources disagree, say so.\n"
                "- Be clear and well explained.\n\n"
                f"{evidence}"
            )

            def after_answer(ans: str):
                src_lines = ["", "Sources:"]
                for i, s in enumerate(sources, 1):
                    title = (s.get("title") or "Source").strip()
                    url = s["url"].strip()
                    src_lines.append(f"[{i}] {title}\n{url}")
                final = ans.strip() + "\n" + "\n".join(src_lines)
                self._assistant_say(final)
                self.status.config(text="● ONLINE", fg=MUTED)

            self.status.config(text="● THINKING...", fg=ACCENT)

            def worker():
                try:
                    reply = ollama_chat(TEXT_MODEL, [{"role": "user", "content": prompt}], temperature=0.4)
                except Exception as e:
                    reply = f"I hit an error while researching.\n\n{e}"
                self.root.after(0, lambda: after_answer(reply))

            threading.Thread(target=worker, daemon=True).start()

            pack = [f"User question: {query}",
                    "",
                    "SOURCES (cite with [1], [2], etc. Do NOT use Wikipedia or any wiki.):"]

            for i, s in enumerate(sources, 1):
                title = s.get("title", "").strip()
                url = s.get("url", "").strip()
                text = (s.get("text") or "")[:2500]
                pack.append(f"\n[{i}] {title}\nURL: {url}\nEXTRACT:\n{text}")

            evidence = "\n".join(pack)

            prompt = (
                "Answer the user's question using ONLY the sources above.\n"
                "Rules:\n"
                "- Cite claims with [#] citations.\n"
                "- Use multiple sources; do not rely on a single source.\n"
                "- If sources disagree, say so.\n"
                "- Do NOT cite or reference Wikipedia or fandom wikis.\n"
                "- Be clear and explain step-by-step.\n\n"
                f"{evidence}"
            )

            self._call_model_async(prompt)
            self.status.config(text="● ONLINE", fg=MUTED)

            pack_lines = [f"User question: {query}", "", "SOURCES (use citations like [1], [2]):"]
            for i, s in enumerate(sources, 1):
                pack_lines.append(f"\n[{i}] {s['title']}\nURL: {s['url']}\nEXTRACT:\n{s['text'][:2500]}")
            evidence = "\n".join(pack_lines)

            prompt = (
                "Answer the user's question using ONLY the sources above.\n"
                "Rules:\n"
                "- Cite claims with [#] citations.\n"
                "- Use multiple sources; do not rely on a single site.\n"
                "- If sources disagree, say so.\n"
                "- Do NOT use Wikipedia.\n"
                "- Be clear and explain like a helpful tutor.\n\n"
                f"{evidence}"
            )

            self._call_model_async(prompt)
            self.status.config(text="● ONLINE", fg=MUTED)

    def _finish_web(self, query: str, results):
        if not results:
            self._system_say(str(query))
            self.status.config(text="● ONLINE", fg=MUTED)
            return

        self.last_sources = results[:]
        lines = [f"Searched: {query}\n\nSources:"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}) {r['title']}\n{r['url']}\n")
        lines.append("Click a link to open it.")
        msg = "\n".join(lines)

        self._assistant_say(msg)
        self.status.config(text="● ONLINE", fg=MUTED)

    def attach_file(self):
        path = filedialog.askopenfilename(
            title="Attach a file",
            filetypes=[
                ("All supported", "*.pdf *.docx *.txt *.md *.csv *.log *.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                ("Documents", "*.pdf *.docx *.txt *.md *.csv *.log"),
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        filename = os.path.basename(path)

        if is_image(path):
            self._user_say(f"[Image sent] {filename}")
            self.status.config(text="● LOOKING...", fg=ACCENT2)
            threading.Thread(target=self._vision_worker, args=(path,), daemon=True).start()
            return

        if is_doc(path):
            self._user_say(f"[File sent] {filename}")
            self.status.config(text="● READING FILE...", fg=ACCENT2)
            threading.Thread(target=self._file_worker, args=(path,), daemon=True).start()
            return

        self._system_say("That file type isn't supported yet. Try PDF/DOCX/TXT/MD/CSV or an image.")

    def _file_worker(self, path: str):
        try:
            ftype, text = sniff_and_read_file(path)
        except Exception as e:
            self.root.after(0, lambda: self._system_say(f"Couldn't read file:\n{e}"))
            self.root.after(0, lambda: self.status.config(text="● ONLINE", fg=MUTED))
            return

        prompt = (
            f"The user attached a {ftype} file. Here is extracted text:\n\n{text}\n\n"
            "Summarize it clearly. Then ask what they want next (study plan, email draft, lab report, etc.)."
        )
        self._call_model_async(prompt)

    def _vision_worker(self, path: str):
        try:
            b64 = image_to_base64_png(path)
        except Exception as e:
            self.root.after(0, lambda: self._system_say(f"Couldn't read image:\n{e}"))
            self.root.after(0, lambda: self.status.config(text="● ONLINE", fg=MUTED))
            return

        now_ctx = self.get_local_datetime_context()
        mem_snips = self._memory_pack(user_text)
        system_prompt = build_system_prompt(now_ctx, self.current_chat_name, mem_snips)
        user_text = (
            "The user attached an image. Describe what you see. "
            "If there is text, read/summarize it. If it looks like homework, help step-by-step."
        )

        try:
            reply = ollama_vision(VISION_MODEL, user_text=user_text, image_b64=b64, system=system)
        except Exception as e:
            reply = f"I hit an error using vision.\n\n{e}"

        self.root.after(0, lambda: self._assistant_say(reply))
        self.root.after(0, lambda: self.status.config(text="● ONLINE", fg=MUTED))

    # -------------------------------------------------------
    # Send + Respond
    # -------------------------------------------------------
    def send_message(self):
        user_text = self._get_input_text().strip()
        if not user_text:
            return

        def _direct_datetime_reply(self, user_text: str) -> bool:
            t = user_text.strip().lower()

            now = datetime.now().astimezone()
            date_str = now.strftime("%B %d, %Y").replace(" 0", " ")
            day_str = now.strftime("%A")
            time_str = now.strftime("%I:%M %p").lstrip("0")
            tz_str = now.tzname() or "local time"

            if re.search(r"\bwhat(?:'s| is)? the time\b|\bwhat time is it\b", t):
                self._assistant_say(f"It is currently {time_str} ({tz_str}).")
                return True

            if re.search(r"\bwhat day is it\b|\bwhat(?:'s| is)? today\b", t):
                self._assistant_say(f"Today is {day_str}, {date_str}.")
                return True

            if re.search(r"\bwhat(?:'s| is)? the date\b|\btoday'?s date\b", t):
                self._assistant_say(f"Today’s date is {date_str}.")
                return True

            return False

        # ---- Action confirmation flow ----
        if self.action_state.has_pending():
            if is_confirmation(user_text):
                self._clear_input()
                self._user_say(user_text)
                if self._direct_datetime_reply(user_text):
                    return
                action = self.action_state.pending_action
                if action == "email_send":
                    handle_email_send(self.action_state, self._assistant_say, self._system_say)
                elif action == "calendar_add":
                    handle_calendar_confirm(self.action_state, self._system_say)
                return
            elif is_cancellation(user_text):
                self._clear_input()
                self._user_say(user_text)
                self.action_state.clear()
                self._system_say("Cancelled. No worries!")
                return

        # ---- Action intent detection ----
        def _llm(msgs, temperature=0.3):
            from ui.theme import TEXT_MODEL
            return ollama_chat(TEXT_MODEL, msgs, temperature=temperature)

        intent = detect_intent(user_text)
        if intent == "calendar_check":
            self._clear_input()
            self._user_say(user_text)
            handle_calendar_check(self._assistant_say, self._system_say)
            return
        elif intent == "email_draft":
            self._clear_input()
            self._user_say(user_text)
            handle_email_draft(user_text, self.action_state,
                            self._assistant_say, self._system_say, _llm)
            return
        elif intent == "calendar_add":
            self._clear_input()
            self._user_say(user_text)
            handle_calendar_add(user_text, self.action_state,
                                self._assistant_say, self._system_say, _llm)
            return

        # ---- Eyes react to user message ----
        '''
        try:
            # Check for expression voice command ("be happy", "look angry", etc.)
            cmd_expr = detect_voice_command(user_text)
            if cmd_expr:
                # Change eyes and let Samuel also respond naturally
                self._set_eyes(cmd_expr)
            else:
                # Scan for emotion keywords in what they typed
                detected = None
                for w in user_text.lower().split():
                    clean = w.strip(".,!?\"'")
                    if clean in EMOTION_MAP:
                        detected = EMOTION_MAP[clean]
                        break
                # Default: curious while Samuel reads/thinks
                self._set_eyes(detected if detected else "curious")
        except Exception:
            pass
        '''
        # ---- Admin commands ----
        if user_text == "Alpha.e.x0.1.eXpr3ss":
            self._clear_input()
            try:
                from training.gif_trainer_panel import open_gif_trainer
                open_gif_trainer(self)
                self._system_say("GIF reaction trainer opened.")
            except Exception as e:
                self._system_say(f"Could not open GIF trainer:\n{e}")
            return

        # Auto-detect contacts from conversation
        candidates = auto_detect_and_queue(user_text)
        for c in candidates:
            if c["confidence"] >= 0.9:
                cid = save_contact_from_candidate(c)
                self._system_say(
                    f"Added {c['name']} to contacts"
                    + (f" as your {c['relationship']}" if c.get('relationship') else "")
                    + "."
                )

        _add_contact_triggers = [
            "add to my contacts",
            "put in my contacts",
            "save to contacts",
            "add him to contacts",
            "add her to contacts",
            "add them to contacts",
            "save his contact",
            "save her contact",
            "put this person in my contacts",
            "add this person to contacts",
        ]

        if any(t in user_text.lower() for t in _add_contact_triggers):
            candidates = auto_detect_and_queue(user_text)
            if candidates:
                for c in candidates:
                    cid = save_contact_from_candidate(c)
                    self._system_say(
                        f"Done! Added {c['name']} to your contacts"
                        + (f" as your {c['relationship']}" if c.get('relationship') else "")
                        + "."
                    )
            else:
                self._system_say("I'll save them — what's their name?")

        if user_text == "Alpha.k.x0.1.Kn0wledge":
            self._clear_input()
            self._system_say("Opening Knowledge Panel...")
            try:
                from training.knowledge_panel import open_knowledge_panel
                open_knowledge_panel(self)
            except Exception as e:
                self._system_say(f"Could not open knowledge panel:\n{e}")
            return

        if user_text == "Alpha.c.x0.1.C0ntacts":
            self._clear_input()
            self._system_say("Opening Contacts...")
            from ui.contacts_panel import open_contacts_panel
            open_contacts_panel(self)
            return

        if user_text == "Alpha.g.x0.1.G00gle":
            self._clear_input()
            from training.google_panel import open_google_panel
            open_google_panel(self)
            return

        if user_text == "Alpha.m.x0.1.Mem0rY":
            self._clear_input()
            self._system_say("Memory mode enabled. Opening Memory Manager.")
            try:
                self.memory_mode = True
                self.memory_panel = open_memory_panel(self)
            except Exception as e:
                self._system_say(f"Could not open memory panel:\n{e}")
            return

        if user_text == "Alpha.c.x0.1.Mem0rY":
            self._clear_input()
            self.memory_mode = False
            self._system_say("Memory mode closed. Returning to normal chat.")
            try:
                if getattr(self, "memory_panel", None) and self.memory_panel.winfo_exists():
                    self.memory_panel.destroy()
            except Exception:
                pass
            self.memory_panel = None
            return

        if user_text == "Omega.x0.1.SaMUeL":
            self._clear_input()
            self._system_say("Personality training enabled. Opening Personality Trainer.")
            try:
                self.personality_mode = True
                open_personality_panel(self)
            except Exception as e:
                self._system_say(f"Could not open personality panel:\n{e}")
            return

        if user_text == "Omega.x0.1.Close":
            self._clear_input()
            self.personality_mode = False
            self._system_say("Personality training closed. Returning to normal chat.")
            try:
                if getattr(self, "personality_win", None) and self.personality_win.winfo_exists():
                    self.personality_win.destroy()
            except Exception:
                pass
            self.personality_win = None
            return

        # ---- Normal chat path ----
        self._clear_input()
        self._user_say(user_text)

        direct = self._direct_personal_answer(user_text)
        if direct:
            self._assistant_say(direct)
            return

        try:
            recent = store.get_messages(self.current_chat_id, limit=6)
            recent_context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
            auto_memory_capture(user_text, recent_context=recent_context, chat_id=self.current_chat_id)
        except Exception:
            pass

        if self._maybe_train_from_confirmation(user_text):
            return

        if self.pending_relation_name:
            rel_name = self.pending_relation_name
            relation = user_text.strip().rstrip(".!")
            if relation:
                store.upsert_saved_memory(
                    owner="user",
                    category="relationships",
                    key=f"{rel_name}_relation",
                    value=relation,
                    stability="adaptive",
                    importance=1.2,
                    confidence=0.7,
                    source="chat",
                )
                self._system_say(f"Thank you. I'll remember that {rel_name} is your {relation}.")
            self.pending_relation_name = None
            return

        self._passive_memory_capture(user_text)

        guess, conf = style_predict(self.style_model, self.style_labels, user_text)
        if guess == OWNER_ME and conf >= 0.90:
            self.style_model, self.style_labels = style_update(
                self.style_model, self.style_labels, user_text, OWNER_ME
            )
        if guess == "UNKNOWN" or guess == UNKNOWN_BUCKET:
            self.pending_style_check = {"text": user_text, "conf": conf}

        # ---- Samuel self-state / social-reactive GIF path ----
        state_reaction = self._samuel_state_reaction(user_text)
        if state_reaction:
            reaction_label, quick_reply = state_reaction
            if self._gif_engine:
                try:
                    gif_result = self._gif_engine.match(reaction_label)
                    if gif_result and gif_result.get("path"):
                        self.add_gif_bubble(gif_result["path"], label="SAMUEL")
                except Exception as e:
                    print(f"[GIF] state reaction error: {e}")
            self._assistant_say(quick_reply)
            return

        # ---- Normal social/reactive GIF path ----
        if self._is_social_reactive_message(user_text) and self._gif_engine:
            try:
                gif_result = self._gif_engine.match(user_text)
                if gif_result and gif_result.get("confidence", 0) >= 0.75 and gif_result.get("path"):
                    self.add_gif_bubble(gif_result["path"], label="SAMUEL")
            except Exception as e:
                print(f"[GIF] social reaction error: {e}")

        self.status.config(text="● THINKING...", fg=ACCENT)
        threading.Thread(target=self._respond, args=(user_text,), daemon=True).start()

    def open_memory_panel(self):
        if getattr(self, "memory_win", None) and self.memory_win.winfo_exists():
            self.memory_win.lift()
            return
        self.memory_win = open_memory_panel(self)

    def close_memory_panel(self):
        if getattr(self, "memory_win", None) and self.memory_win.winfo_exists():
            self.memory_win.destroy()
        self.memory_win = None

    def _respond(self, user_text: str):
        now_ctx = self.get_local_datetime_context()
        mem_pack = self._memory_pack(user_text)

        rules_pack = ""
        ppack = ""
        try:
            rules_pack = store.build_personality_rules_pack(max_rules=10)
        except Exception:
            rules_pack = ""

        try:
            ppack = store.build_personality_pack(user_text, max_items=6)
        except Exception:
            ppack = ""

        mem_pack = "\n\n".join(
            [x for x in [mem_pack, rules_pack, ppack] if x and x.strip()]
        ).strip()

        try:
            from google_calendar import build_today_context, build_calendar_context
            cal_today = build_today_context()
            cal_week = build_calendar_context(days=7)
            if cal_today or cal_week:
                mem_pack = cal_today + "\n" + cal_week + "\n\n" + mem_pack
        except Exception:
            pass

        try:
            if rules_pack.strip():
                print(f"[PERSONALITY] Injecting rules pack: {len(rules_pack)} chars")
            else:
                print("[PERSONALITY] No rules pack yet (none learned or function missing).")

            if ppack.strip():
                print(f"[PERSONALITY] Injecting calibration pack: {len(ppack)} chars")
                print(ppack.splitlines()[0])
            else:
                print("[PERSONALITY] No calibration pack found (no examples or no matches).")
        except Exception:
            pass

        system_prompt = build_system_prompt(now_ctx, self.current_chat_name, mem_pack)

        recent = store.get_messages(self.current_chat_id, limit=12)
        messages = [{"role": "system", "content": system_prompt}]
        for m in recent:
            messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": user_text})

        try:
            reply = ollama_chat(TEXT_MODEL, messages, temperature=0.6)
        except Exception as e:
            reply = f"I hit an error talking to Ollama.\n\n{e}"

        self.root.after(0, lambda: self._assistant_say(reply))

        def after_question():
            if self.pending_style_check:
                self._system_say(
                    f"One small confirmation, if you please.\n"
                    f"Is this still you, Miss ({OWNER_ME})?\n"
                    f"(You may reply: \"yes\", or \"no this is Mercy\", etc.)"
                )

        self.root.after(0, after_question)
        self.root.after(0, lambda: self.status.config(text="● ONLINE", fg=MUTED))
            
        def after_question():
            if self.pending_style_check:
                self._system_say(
                    f"One small confirmation, if you please.\n"
                    f"Is this still you, Miss ({OWNER_ME})?\n"
                    f"(You may reply: \"yes\", or \"no this is Mercy\", etc.)"
                )

        self.root.after(0, after_question)
        self.root.after(0, lambda: self.status.config(text="● ONLINE", fg=MUTED))

    def _call_model_async(self, user_text: str):
        def worker():
            now_ctx = self.get_local_datetime_context()
            mem_snips = self._memory_pack(user_text)
            system_prompt = build_system_prompt(now_ctx, self.current_chat_name, mem_snips)

            recent = store.get_messages(self.current_chat_id, limit=12)
            messages = [{"role": "system", "content": system_prompt}]
            for m in recent:
                messages.append({"role": m["role"], "content": m["content"]})
            messages.append({"role": "user", "content": user_text})

            try:
                reply = ollama_chat(TEXT_MODEL, messages, temperature=0.7)
            except Exception as e:
                reply = f"I hit an error talking to Ollama.\n\n{e}"

            self.root.after(0, lambda: self._assistant_say(reply))
            self.root.after(0, lambda: self.status.config(text="● ONLINE", fg=MUTED))

        threading.Thread(target=worker, daemon=True).start()


# app.py will call this
if __name__ == "__main__":
    root = tk.Tk()
    SamuelGUI(root)
    root.mainloop()
