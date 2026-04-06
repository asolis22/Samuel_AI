import os
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime

from Samuel_AI.core.tools import sniff_and_read_file, image_to_base64_png
from Samuel_AI.core.llm_ollama import ollama_chat, ollama_vision
from Samuel_AI.core.tts_engine import speak_async
import Samuel_AI.core.samuel_store as store
from Samuel_AI.core.reaction_gif_engine import init_reaction_db, predict_reaction_and_gif, giphy_search_one_gif
from Samuel_AI.core.action_handler import (
    ActionState,
    detect_intent,
    is_confirmation,
    is_cancellation,
    handle_calendar_check,
    handle_email_draft,
    handle_email_send,
    handle_calendar_add,
    handle_calendar_confirm,
)
from Samuel_AI.core.emotion_router import route_emotion

from Samuel_AI.features.web_search import research
from Samuel_AI.features.contacts_autosave import auto_detect_and_queue, save_contact_from_candidate
from Samuel_AI.features.contacts_store import init_contacts_db, build_contacts_context

from Samuel_AI.ui.theme import BG, CARD, ACCENT, ACCENT2, TEXT, MUTED, BORDER, TEXT_MODEL, VISION_MODEL, DEFAULT_CHAT
from Samuel_AI.ui.prompts import build_system_prompt
from Samuel_AI.ui.text_utils import sanitize_markdown_links, now_ts, clean_chat_name, is_image, is_doc
from Samuel_AI.ui.clipboard import enable_clipboard_shortcuts
from Samuel_AI.ui.voice_panel import open_voice_panel
from Samuel_AI.ui.eyes_ui import EyesUI

# optional / transitional imports
try:
    from Samuel_AI.core.memory_autosave import auto_memory_capture
except Exception:
    try:
        from memory_autosave import auto_memory_capture
    except Exception:
        def auto_memory_capture(*args, **kwargs):
            return None

try:
    from Samuel_AI.core.memory_retrieval import build_smart_memory_pack, build_cross_chat_pack
except Exception:
    try:
        from memory_retrieval import build_smart_memory_pack, build_cross_chat_pack
    except Exception:
        def build_smart_memory_pack(*args, **kwargs):
            return ""
        def build_cross_chat_pack(*args, **kwargs):
            return ""

try:
    from Samuel_AI.core.memory_filter import should_remember, _is_ephemeral_text
except Exception:
    try:
        from memory_filter import should_remember, _is_ephemeral_text
    except Exception:
        def should_remember(*args, **kwargs):
            return True, ""
        def _is_ephemeral_text(*args, **kwargs):
            return False

try:
    from Samuel_AI.core.knowledge_store import build_knowledge_context, init_knowledge_db
except Exception:
    try:
        from knowledge_store import build_knowledge_context, init_knowledge_db
    except Exception:
        def build_knowledge_context(*args, **kwargs):
            return ""
        def init_knowledge_db(*args, **kwargs):
            return None



# ── Tenor GIF fallback (no API key required) ─────────────────────────
_TENOR_KEY = "AIzaSyAyimkuYQYF_FXVALexPuGQctUWRURdCDY"  # Tenor demo key

_TENOR_REACTION_MAP = {
    "excited":    "excited happy reaction",
    "happy":      "happy smile reaction",
    "sad":        "sad crying reaction",
    "anger":      "angry frustrated reaction",
    "supportive": "supportive hug reaction",
    "reassuring": "its okay calm reaction",
    "comforting": "comfort gentle reaction",
    "blessed":    "blessed grateful thankful",
    "neutral":    "okay nodding reaction",
}

def _fetch_tenor_gif(reaction: str) -> str | None:
    try:
        import requests as _req, random
        query = _TENOR_REACTION_MAP.get(reaction.split("+")[0].strip(),
                                        reaction + " reaction")
        r = _req.get(
            "https://tenor.googleapis.com/v2/search",
            params={"q": query, "key": _TENOR_KEY, "limit": 8,
                    "contentfilter": "medium", "media_filter": "gif"},
            timeout=10,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            print(f"[GIF] Tenor returned 0 results for: {query}")
            return None
        item = random.choice(results[:5])
        for fmt in ("tinygif", "mediumgif", "gif"):
            url = item.get("media_formats", {}).get(fmt, {}).get("url")
            if url:
                print(f"[GIF] Tenor URL ({fmt}): {url}")
                return url
    except Exception as e:
        print(f"[GIF] Tenor error: {e}")
    return None
# ─────────────────────────────────────────────────────────────────────

class SamuelGUI:
    def __init__(self, root: tk.Tk):
        store.init_db()
        init_knowledge_db()
        init_contacts_db()
        init_reaction_db()

        self.action_state = ActionState()

        self.root = root
        self.root.title("SAMUEL")
        self.root.configure(bg=BG)
        self.root.geometry("980x720")
        self.root.minsize(860, 580)

        style = ttk.Style()
        style.theme_use("clam")

        self.current_chat_name = DEFAULT_CHAT
        self.current_chat_id = store.get_or_create_chat(self.current_chat_name)

        self.placeholder_text = "Type here..."
        self.voice_win = None

        self._last_assistant_text = ""
        self._last_assistant_ts = 0
        self.current_presence = "idle"
        self.current_expression = "neutral"
        self._samuel_day_state = "neutral"

        self._build_layout()
        enable_clipboard_shortcuts(self.root)
        self.entry.focus_set()

    def _build_layout(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(top, text="SAMUEL", bg=BG, fg=TEXT, font=("Menlo", 24, "bold")).pack(side="left")

        right = tk.Frame(top, bg=BG)
        right.pack(side="right")

        self.status = tk.Label(right, text="● IDLE", bg=BG, fg=MUTED, font=("Menlo", 11, "bold"))
        self.status.pack(side="right", padx=(14, 0))

        self.chat_lbl = tk.Label(
            right,
            text=f"CHAT: {self.current_chat_name}",
            bg=BG,
            fg=MUTED,
            font=("Menlo", 11),
        )
        self.chat_lbl.pack(side="right")

        controls = tk.Frame(self.root, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        controls.pack(fill="x", padx=16, pady=(0, 10))

        self._make_link(controls, "ATTACH", self.attach_file, fg=ACCENT2).pack(side="left", padx=(12, 8), pady=10)
        self._make_link(controls, "WEB", self.web_search_prompt, fg=ACCENT).pack(side="left", padx=8, pady=10)
        self._make_link(controls, "VOICE", self.open_voice_panel, fg=ACCENT2).pack(side="left", padx=8, pady=10)

        stage = tk.Frame(self.root, bg=BG)
        stage.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        self.eyes = EyesUI(stage)
        self.eyes.pack(fill="both", expand=True)

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=16, pady=(0, 16))

        self.input_bar = tk.Frame(bottom, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        self.input_bar.pack(fill="x")

        self.entry = tk.Text(
            self.input_bar,
            bg=CARD,
            fg=TEXT,
            insertbackground=ACCENT,
            relief="flat",
            font=("Menlo", 13),
            height=1,
            wrap="word",
            undo=True,
        )
        self.entry.pack(side="left", fill="both", expand=True, padx=(12, 8), pady=10)
        self.entry.bind("<Return>", self._on_enter_send)
        self.entry.bind("<Shift-Return>", self._on_shift_enter_newline)
        self.entry.bind("<KeyRelease>", self._auto_resize_input)

        self._install_text_placeholder(self.placeholder_text)

        self.send_btn = tk.Button(
            self.input_bar,
            text="SEND",
            bg=ACCENT,
            fg="#11100F",
            relief="flat",
            font=("Menlo", 12, "bold"),
            command=self.send_message,
        )
        self.send_btn.pack(side="right", padx=(0, 12), pady=8, ipadx=10, ipady=3)

    def _make_link(self, parent, text, command, fg=MUTED):
        lbl = tk.Label(parent, text=text, bg=CARD, fg=fg, cursor="hand2", font=("Menlo", 12, "bold"))
        lbl.bind("<Button-1>", lambda _e: command())
        return lbl

    def set_presence(self, presence: str, expression: str | None = None):
        self.current_presence = presence
        if expression:
            self.current_expression = expression

        color = MUTED
        label = "● NOT ACTIVE"

        if presence == "listening":
            color = ACCENT2
            label = "● LISTENING"
        elif presence == "thinking":
            color = ACCENT
            label = "● THINKING"
        elif presence == "speaking":
            color = "#7A5C46"
            label = "● SPEAKING"

        self.status.config(text=label, fg=color)
        self.eyes.set_state(presence, expression or self.current_expression)
        self.eyes.set_mic(presence in {"listening", "thinking", "speaking"})


    def set_caption(self, speaker: str, text: str):
        self.eyes.set_caption_typewriter(speaker, text)

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
        self.entry.configure(height=max(1, min(5, display_lines)))

    def _install_text_placeholder(self, text: str):
        self.placeholder_text = text
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", self.placeholder_text)
        self.entry.tag_add("placeholder", "1.0", "end")
        self.entry.tag_config("placeholder", foreground=MUTED)
        self.entry.mark_set("insert", "1.0")

        def clear(_e=None):
            if self._get_input_text() == self.placeholder_text:
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

    def open_voice_panel(self):
        self.voice_win = open_voice_panel(self)

    def _memory_pack(self, user_text):
        if _is_ephemeral_text(user_text):
            return ""

        parts = []

        try:
            saved = build_smart_memory_pack(user_text, owner="user", max_items=12)
            if saved.strip():
                parts.append(saved)
        except Exception:
            pass

        try:
            contacts = build_contacts_context(user_text)
            if contacts.strip():
                parts.append(contacts)
        except Exception:
            pass

        try:
            cross = build_cross_chat_pack(user_text, current_chat_id=self.current_chat_id, limit=4)
            if cross.strip():
                parts.append(cross)
        except Exception:
            pass

        try:
            knowledge = build_knowledge_context(user_text, max_nuggets=5)
            if knowledge.strip():
                parts.append(knowledge)
        except Exception:
            pass

        return "\n\n".join(parts).strip()

    def _system_say(self, text: str):
        self.set_caption("SAMUEL", text)

    def _user_say(self, text: str):
        ts = now_ts()
        self.set_caption("YOU", text)
        store.add_message(self.current_chat_id, "user", text, ts=ts)

    def _assistant_say(self, text: str):
        ts = now_ts()
        text = sanitize_markdown_links(text or "")
        cleaned = text.replace("**", "").replace("*", "").strip()
        if not cleaned:
            return

        if cleaned == self._last_assistant_text and (ts - self._last_assistant_ts) <= 2:
            return

        self._last_assistant_text = cleaned
        self._last_assistant_ts = ts

        self.set_presence("speaking", self.current_expression)
        self.set_caption("SAMUEL", cleaned)
        store.add_message(self.current_chat_id, "assistant", cleaned, ts=ts)

        try:
            vw = getattr(self, "voice_win", None)
            if vw and vw.winfo_exists() and getattr(vw, "auto_speak", False):
                speak_async(cleaned)
        except Exception as e:
            print("[TTS] speak failed:", e)

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

    def _maybe_show_reaction_gif(self, text: str):
        """Show a reaction GIF overlaid on eyes for 5 seconds."""
        def _worker():
            try:
                gif_data = predict_reaction_and_gif(text)
                confidence = gif_data.get("confidence", 0.0)
                reaction   = gif_data.get("reaction", "neutral")
                print(f"[GIF] reaction={reaction} conf={confidence:.2f}")

                if confidence < 0.40:
                    print("[GIF] Confidence too low, skipping")
                    return

                import os
                gif_url = None

                if os.getenv("GIPHY_API_KEY"):
                    gif = giphy_search_one_gif(gif_data.get("gif_prompt", reaction))
                    if gif and gif.get("gif_url"):
                        gif_url = gif["gif_url"]

                if not gif_url:
                    gif_url = _fetch_tenor_gif(reaction)

                if gif_url:
                    print(f"[GIF] Showing on screen: {gif_url}")
                    self.root.after(0, lambda url=gif_url:
                                    self.eyes.show_reaction_gif(url, duration_ms=5000))
                else:
                    print("[GIF] No gif URL found")
            except Exception as e:
                import traceback
                print(f"[GIF] error: {e}")
                traceback.print_exc()

        threading.Thread(target=_worker, daemon=True).start()

    def web_search_prompt(self):
        txt = self.entry.get("1.0", "end-1c").strip()
        if txt and txt != self.placeholder_text:
            self.entry.delete("1.0", "end")
            self._user_say(f"web: {txt}")
            self._run_web_search(txt)
        else:
            self._system_say("Type a query then click WEB.")

    def _run_web_search(self, query: str):
        self.set_presence("thinking", "curious")
        threading.Thread(target=self._web_worker, args=(query,), daemon=True).start()

    def _web_worker(self, query: str):
        try:
            sources = research(query, max_results=10, fetch_top_k=5)
        except Exception as e:
            self.root.after(0, lambda: self._assistant_say(f"Web search error:\n{e}"))
            self.root.after(0, lambda: self.set_presence("idle", "neutral"))
            return

        if not sources:
            self.root.after(0, lambda: self._assistant_say(f"Searched: {query}\n\nNo good sources found."))
            self.root.after(0, lambda: self.set_presence("idle", "neutral"))
            return

        lines = [f"Searched: {query}\n", "Sources:"]
        for i, r in enumerate(sources[:6], 1):
            lines.append(f"{i}) {r['title']}")
        final = "\n".join(lines)

        self.root.after(0, lambda: self._assistant_say(final))
        self.root.after(0, lambda: self.set_presence("idle", "neutral"))

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
            self.set_presence("thinking", "curious")
            threading.Thread(target=self._vision_worker, args=(path,), daemon=True).start()
            return

        if is_doc(path):
            self._user_say(f"[File sent] {filename}")
            self.set_presence("thinking", "curious")
            threading.Thread(target=self._file_worker, args=(path,), daemon=True).start()
            return

        self._system_say("That file type isn't supported yet.")

    def _file_worker(self, path: str):
        try:
            ftype, text = sniff_and_read_file(path)
        except Exception as e:
            self.root.after(0, lambda: self._system_say(f"Couldn't read file:\n{e}"))
            self.root.after(0, lambda: self.set_presence("idle", "neutral"))
            return

        prompt = f"The user attached a {ftype} file. Summarize it clearly:\n\n{text[:8000]}"
        self._call_model_async(prompt)

    def _vision_worker(self, path: str):
        try:
            b64 = image_to_base64_png(path)
        except Exception as e:
            self.root.after(0, lambda: self._system_say(f"Couldn't read image:\n{e}"))
            self.root.after(0, lambda: self.set_presence("idle", "neutral"))
            return

        now_ctx = self.get_local_datetime_context()
        user_text = "Describe what is in this image. Read text if visible."
        mem_snips = self._memory_pack(user_text)
        system_prompt = build_system_prompt(now_ctx, self.current_chat_name, mem_snips)

        try:
            reply = ollama_vision(VISION_MODEL, user_text=user_text, image_b64=b64, system=system_prompt)
        except Exception as e:
            reply = f"I hit an error using vision.\n\n{e}"

        self.root.after(0, lambda: self._assistant_say(reply))
        self.root.after(0, lambda: self.set_presence("idle", "neutral"))

    def send_message(self):
        user_text = self._get_input_text().strip()
        if user_text:
            self.process_user_text(user_text)

    def process_user_text(self, user_text: str):
        if not user_text:
            return

        if self.action_state.has_pending():
            if is_confirmation(user_text):
                self._clear_input()
                self._user_say(user_text)
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

        def _llm(msgs, temperature=0.3):
            return ollama_chat(TEXT_MODEL, msgs, temperature=temperature)

        intent = detect_intent(user_text)
        tool_mode = intent is not None

        if intent == "calendar_check":
            self._clear_input()
            self._user_say(user_text)
            handle_calendar_check(self._assistant_say, self._system_say)
            return
        elif intent == "email_draft":
            self._clear_input()
            self._user_say(user_text)
            handle_email_draft(user_text, self.action_state, self._assistant_say, self._system_say, _llm)
            return
        elif intent == "calendar_add":
            self._clear_input()
            self._user_say(user_text)
            handle_calendar_add(user_text, self.action_state, self._assistant_say, self._system_say, _llm)
            return

        self._clear_input()
        self._user_say(user_text)

        if self._direct_datetime_reply(user_text):
            self.set_presence("idle", "neutral")
            return

        try:
            recent = store.get_messages(self.current_chat_id, limit=6)
            recent_context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
            auto_memory_capture(user_text, recent_context=recent_context, chat_id=self.current_chat_id)
        except Exception:
            pass

        self._maybe_show_reaction_gif(user_text)

        signal = route_emotion(user_text, tool_mode=tool_mode)
        self.current_expression = signal.eye_expression

        if signal.eye_expression == "confused":
            self.eyes.anim_confused()
        elif signal.eye_expression == "happy":
            self.eyes.anim_laugh()

        self.set_presence("thinking", signal.eye_expression)
        threading.Thread(target=self._respond, args=(user_text, signal), daemon=True).start()

    def _respond(self, user_text: str, signal=None):
        now_ctx = self.get_local_datetime_context()
        mem_pack = self._memory_pack(user_text)

        system_prompt = build_system_prompt(now_ctx, self.current_chat_name, mem_pack)

        if signal:
            system_prompt += f"\n\n[EMOTIONAL CONTEXT]\n{signal.system_hint}"

        # HARD RULE: Never describe or mention GIFs/images in text responses
        system_prompt += (
            "\n\n[ABSOLUTE RULE] You are a voice assistant with a face display. "
            "You CANNOT send, show, describe, or reference GIFs, images, memes, or any visual media. "
            "NEVER write things like '[Image of...]', 'here is a GIF', 'here\'s a happy GIF', "
            "'[smiling sunflower]', or anything similar. "
            "The system handles all visuals automatically. Just respond in plain conversational text only."
        )

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
        final_expression = signal.eye_expression if signal else "neutral"
        self.root.after(0, lambda: self.set_presence("idle", final_expression))

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
            self.root.after(0, lambda: self.set_presence("idle", "neutral"))

        threading.Thread(target=worker, daemon=True).start()

    def get_local_datetime_context(self):
        now = datetime.now().astimezone()
        return {
            "date": now.strftime("%B %d, %Y").replace(" 0", " "),
            "weekday": now.strftime("%A"),
            "time": now.strftime("%I:%M %p").lstrip("0"),
            "timezone": now.tzname() or "local time",
            "iso": now.isoformat(),
        }


if __name__ == "__main__":
    root = tk.Tk()
    SamuelGUI(root)
    root.mainloop()