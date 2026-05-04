# gui_app.py
# VERSION: 2.5 -- Voice-only push-to-talk Samuel UI + ESP32 LED ring

import os
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog
from datetime import datetime

from Samuel_AI.core.tools import sniff_and_read_file, image_to_base64_png
from Samuel_AI.core.llm_ollama import ollama_chat, ollama_vision
from Samuel_AI.core.tts_engine import speak_async
from Samuel_AI.core.stt_engine import SpeechListener
from Samuel_AI.ui.loading_screen import LoadingScreen, run_preload

import Samuel_AI.core.samuel_store as store

from Samuel_AI.core.reaction_gif_engine import (
    init_reaction_db,
    predict_reaction_and_gif,
    fetch_reaction_gif,
)

from Samuel_AI.ui.eyes_ui import EyesUI, detect_expression_request

try:
    from Samuel_AI.features.google_calendar import build_today_context, build_calendar_context
    _CALENDAR_AVAILABLE = True
except Exception as _cal_err:
    print(f"[CALENDAR] Not available: {_cal_err}")
    _CALENDAR_AVAILABLE = False

    def build_today_context():
        return ""

    def build_calendar_context(days=3):
        return ""

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
from Samuel_AI.features.contacts_store import init_contacts_db, build_contacts_context

from Samuel_AI.ui.theme import (
    BG,
    CARD,
    ACCENT,
    ACCENT2,
    TEXT,
    MUTED,
    BORDER,
    TEXT_MODEL,
    VISION_MODEL,
    DEFAULT_CHAT,
)

from Samuel_AI.ui.prompts import build_system_prompt
from Samuel_AI.ui.text_utils import sanitize_markdown_links, now_ts, is_image, is_doc
from Samuel_AI.ui.clipboard import enable_clipboard_shortcuts

try:
    from Samuel_AI.core.memory_autosave import auto_memory_capture
except Exception:
    def auto_memory_capture(*args, **kwargs):
        return None

try:
    from Samuel_AI.core.memory_retrieval import build_smart_memory_pack, build_cross_chat_pack
except Exception:
    def build_smart_memory_pack(*args, **kwargs):
        return ""

    def build_cross_chat_pack(*args, **kwargs):
        return ""

try:
    from Samuel_AI.core.memory_filter import _is_ephemeral_text
except Exception:
    def _is_ephemeral_text(*args, **kwargs):
        return False

try:
    from Samuel_AI.core.knowledge_store import build_knowledge_context, init_knowledge_db
except Exception:
    def build_knowledge_context(*args, **kwargs):
        return ""

    def init_knowledge_db(*args, **kwargs):
        return None

# -- ESP32 LED ring ------------------------------------------------------------
try:
    from Samuel_AI.core.led_controller import LEDController
    _led = LEDController()
except Exception as _led_err:
    print(f"[LED] Not available: {_led_err}")
    _led = None
# ------------------------------------------------------------------------------


class SamuelGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SAMUEL")
        self.root.configure(bg="#0F0D0B")
        self.root.geometry("980x720")
        self.root.minsize(860, 580)

        style = ttk.Style()
        style.theme_use("clam")

        self.action_state = ActionState()
        self.current_chat_name = DEFAULT_CHAT
        self.current_chat_id = None

        self.speech_listener = None
        self.mic_btn = None

        self._last_assistant_text = ""
        self._last_assistant_ts = 0

        self.current_presence = "idle"
        self.current_expression = "neutral"

        self._loader = LoadingScreen(self.root, on_complete=self._finish_init)
        self._start_preload()

    def _start_preload(self):
        from Samuel_AI.core.tts_engine import _try_init_piper

        tasks = [
            ("Loading databases...", 1, store.init_db),
            ("Loading knowledge base...", 1, init_knowledge_db),
            ("Loading contacts...", 1, init_contacts_db),
            ("Loading reaction data...", 1, init_reaction_db),
            ("Warming up voice...", 3, _try_init_piper),
            ("Warming up calendar...", 1, self._preload_calendar),
            ("Almost ready...", 1, lambda: None),
        ]

        run_preload(self._loader, tasks, on_all_done=lambda: None)

    def _preload_calendar(self):
        try:
            if _CALENDAR_AVAILABLE:
                build_today_context()
        except Exception:
            pass

    def _finish_init(self):
        self.current_chat_id = store.get_or_create_chat(self.current_chat_name)
        self._build_layout()
        enable_clipboard_shortcuts(self.root)
        self._init_voice_input()

    def _init_voice_input(self):
        try:
            self.speech_listener = SpeechListener(
                on_text=lambda text, lang="en": self.root.after(
                    0, lambda: self._handle_voice_text(text, lang)
                )
            )
            print("[VOICE] Push-to-talk ready.")
        except Exception as e:
            print(f"[VOICE] Could not initialize STT: {e}")
            self.speech_listener = None
            self._system_say("Voice input is not ready. Check the terminal for the microphone error.")

    def _build_layout(self):
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=16, pady=(14, 8))

        tk.Label(
            top,
            text="SAMUEL",
            bg=BG,
            fg=TEXT,
            font=("Menlo", 24, "bold"),
        ).pack(side="left")

        right = tk.Frame(top, bg=BG)
        right.pack(side="right")

        self.status = tk.Label(
            right,
            text="? IDLE",
            bg=BG,
            fg=MUTED,
            font=("Menlo", 11, "bold"),
        )
        self.status.pack(side="right", padx=(14, 0))

        self.chat_lbl = tk.Label(
            right,
            text=f"CHAT: {self.current_chat_name}",
            bg=BG,
            fg=MUTED,
            font=("Menlo", 11),
        )
        self.chat_lbl.pack(side="right")

        controls = tk.Frame(
            self.root,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        controls.pack(fill="x", padx=16, pady=(0, 10))

        self._make_link(controls, "ATTACH", self.attach_file, fg=ACCENT2).pack(
            side="left",
            padx=(12, 8),
            pady=10,
        )

        self._make_link(controls, "WEB", self.web_search_prompt, fg=ACCENT).pack(
            side="left",
            padx=8,
            pady=10,
        )

        stage = tk.Frame(self.root, bg=BG)
        stage.pack(fill="both", expand=True, padx=16, pady=(0, 10))

        self.eyes = EyesUI(stage)
        self.eyes.pack(fill="both", expand=True)

        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=16, pady=(0, 16))

        self.input_bar = tk.Frame(
            bottom,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.input_bar.pack(fill="x")

        self.mic_btn = tk.Button(
            self.input_bar,
            text="HOLD TO TALK",
            bg=ACCENT,
            fg="#11100F",
            activebackground=ACCENT2,
            relief="flat",
            font=("Menlo", 18, "bold"),
        )
        self.mic_btn.pack(fill="x", padx=14, pady=14, ipady=16)

        self.mic_btn.bind("<ButtonPress-1>", self._on_mic_press)
        self.mic_btn.bind("<ButtonRelease-1>", self._on_mic_release)

    def _make_link(self, parent, text, command, fg=MUTED):
        lbl = tk.Label(
            parent,
            text=text,
            bg=CARD,
            fg=fg,
            cursor="hand2",
            font=("Menlo", 12, "bold"),
        )
        lbl.bind("<Button-1>", lambda _e=None: command())
        return lbl

    def _on_mic_press(self, _e=None):
        if not self.speech_listener:
            self._system_say("Voice input is not ready.")
            return "break"

        self.set_presence("listening", "curious")
        self.set_caption("YOU", "Listening...")

        self.mic_btn.config(
            text="LISTENING... RELEASE TO SEND",
            bg=ACCENT2,
        )

        try:
            self.speech_listener.start_ptt()
        except Exception as e:
            print(f"[VOICE] start_ptt error: {e}")
            self.set_presence("idle", "neutral")
            self._system_say("I could not start recording.")
            self.mic_btn.config(text="HOLD TO TALK", bg=ACCENT)

        return "break"

    def _on_mic_release(self, _e=None):
        if not self.speech_listener:
            return "break"

        self.set_presence("thinking", "curious")
        self.set_caption("SAMUEL", "Processing...")
        self.mic_btn.config(text="HOLD TO TALK", bg=ACCENT)

        try:
            self.speech_listener.stop_ptt()
        except Exception as e:
            print(f"[VOICE] stop_ptt error: {e}")
            self.set_presence("idle", "neutral")
            self._system_say("I could not process the recording.")

        return "break"

    def _handle_voice_text(self, text: str, lang: str = "en"):
        text = (text or "").strip()

        if not text:
            self.set_presence("idle", "neutral")
            self._system_say("I did not catch that.")
            return

        self.set_caption("YOU", text)
        self.process_user_text(text)

    def set_presence(self, presence: str, expression: str | None = None):
        self.current_presence = presence

        if expression:
            self.current_expression = expression

        color = MUTED
        label = "? IDLE"

        if presence == "listening":
            color = ACCENT2
            label = "? LISTENING"
        elif presence == "thinking":
            color = ACCENT
            label = "? THINKING"
        elif presence == "speaking":
            color = "#7A5C46"
            label = "? SPEAKING"

        self.status.config(text=label, fg=color)
        self.eyes.set_state(presence, expression or self.current_expression)
        self.eyes.set_mic(presence in {"listening", "thinking", "speaking"})

        # -- LED ring ----------------------------------------------------------
        if _led:
            if presence == "listening":
                _led.set_listening()   # GREEN
            elif presence in ("thinking", "speaking"):
                _led.set_thinking()    # BLUE
            else:
                _led.set_idle()        # RED
        # ----------------------------------------------------------------------

    def set_caption(self, speaker: str, text: str):
        self.eyes.set_caption_typewriter(speaker, text)

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

        self.set_presence("thinking", self.current_expression)

        started = threading.Event()

        def _on_start():
            started.set()
            self.root.after(0, lambda: self.set_presence("speaking", self.current_expression))
            self.root.after(0, lambda: self.set_caption("SAMUEL", cleaned))
            self.root.after(
                0,
                lambda: store.add_message(
                    self.current_chat_id,
                    "assistant",
                    cleaned,
                    ts=ts,
                ),
            )

        def _on_done():
            started.set()
            self.root.after(0, lambda: self.set_presence("idle", self.current_expression))

        def _timeout_watchdog():
            if not started.wait(timeout=10):
                print("[TTS] Watchdog: on_start never fired after 10s - forcing caption.")
                self.root.after(0, lambda: self.set_presence("speaking", self.current_expression))
                self.root.after(0, lambda: self.set_caption("SAMUEL", cleaned))
                self.root.after(
                    0,
                    lambda: store.add_message(
                        self.current_chat_id,
                        "assistant",
                        cleaned,
                        ts=ts,
                    ),
                )
                self.root.after(3000, lambda: self.set_presence("idle", self.current_expression))

        threading.Thread(target=_timeout_watchdog, daemon=True).start()

        try:
            speak_async(cleaned, on_start=_on_start, on_done=_on_done)
        except Exception as e:
            print(f"[TTS] speak_async raised immediately: {e}")
            _on_start()
            self.root.after(2000, lambda: self.set_presence("idle", self.current_expression))

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
            self._assistant_say(f"Today's date is {date_str}.")
            return True

        return False

    def _maybe_show_reaction_gif(self, text: str, after_gif_expression: str = "neutral"):
        def _worker():
            try:
                gif_data = predict_reaction_and_gif(text)
                confidence = gif_data.get("confidence", 0.0)
                reaction = gif_data.get("reaction", "neutral")
                prompt = gif_data.get("gif_prompt", "")

                print(f"[GIF] trigger={reaction} conf={confidence:.2f} prompt='{prompt}'")

                if not gif_data.get("should_react_with_gif") or confidence < 0.40:
                    self.root.after(0, lambda: self.set_presence("idle", after_gif_expression))
                    return

                gif_url = fetch_reaction_gif(prompt) if prompt else None

                if gif_url:
                    print(f"[GIF] Playing: {gif_url}")
                    self.root.after(
                        0,
                        lambda url=gif_url, expr=after_gif_expression: self.eyes.show_reaction_gif(
                            url,
                            duration_ms=5000,
                            on_complete=lambda: self.root.after(
                                0,
                                lambda: self.set_presence("idle", expr),
                            ),
                        ),
                    )
                else:
                    print("[GIF] No gif found - falling back to eyes only")
                    self.root.after(0, lambda: self.set_presence("idle", after_gif_expression))

            except Exception as e:
                import traceback
                print(f"[GIF] error: {e}")
                traceback.print_exc()
                self.root.after(0, lambda: self.set_presence("idle", after_gif_expression))

        threading.Thread(target=_worker, daemon=True).start()

    def web_search_prompt(self):
        self._system_say("Hold the microphone and say: web search, then your question.")

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
            self.root.after(
                0,
                lambda: self._assistant_say(f"Searched: {query}\n\nNo good sources found."),
            )
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
            reply = ollama_vision(
                VISION_MODEL,
                user_text=user_text,
                image_b64=b64,
                system=system_prompt,
            )
        except Exception as e:
            reply = f"I hit an error using vision.\n\n{e}"

        self.root.after(0, lambda: self._assistant_say(reply))
        self.root.after(0, lambda: self.set_presence("idle", "neutral"))

    def process_user_text(self, user_text: str):
        user_text = (user_text or "").strip()

        if not user_text:
            return

        lowered = user_text.lower()

        if lowered.startswith("web search "):
            query = user_text[len("web search "):].strip()
            if query:
                self._user_say(user_text)
                self._run_web_search(query)
                return

        if lowered.startswith("search "):
            query = user_text[len("search "):].strip()
            if query:
                self._user_say(user_text)
                self._run_web_search(query)
                return

        if self.action_state.has_pending():
            if is_confirmation(user_text):
                self._user_say(user_text)
                action = self.action_state.pending_action

                if action == "email_send":
                    handle_email_send(
                        self.action_state,
                        self._assistant_say,
                        self._system_say,
                    )
                elif action == "calendar_add":
                    handle_calendar_confirm(
                        self.action_state,
                        self._system_say,
                    )

                return

            if is_cancellation(user_text):
                self._user_say(user_text)
                self.action_state.clear()
                self._system_say("Cancelled. No worries.")
                return

        def _llm(msgs, temperature=0.3):
            return ollama_chat(TEXT_MODEL, msgs, temperature=temperature)

        intent = detect_intent(user_text)
        tool_mode = intent is not None

        if intent == "calendar_check":
            self._user_say(user_text)
            handle_calendar_check(self._assistant_say, self._system_say)
            return

        if intent == "email_draft":
            self._user_say(user_text)
            handle_email_draft(
                user_text,
                self.action_state,
                self._assistant_say,
                self._system_say,
                _llm,
            )
            return

        if intent == "calendar_add":
            self._user_say(user_text)
            handle_calendar_add(
                user_text,
                self.action_state,
                self._assistant_say,
                self._system_say,
                _llm,
            )
            return

        self._user_say(user_text)

        if self._direct_datetime_reply(user_text):
            self.set_presence("idle", "neutral")
            return

        try:
            recent = store.get_messages(self.current_chat_id, limit=6)
            recent_context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])
            auto_memory_capture(
                user_text,
                recent_context=recent_context,
                chat_id=self.current_chat_id,
            )
        except Exception:
            pass

        requested_expr = detect_expression_request(user_text)

        if requested_expr:
            self.set_presence("idle", requested_expr)
            self.root.after(0, lambda e=requested_expr: self.eyes.set_state("idle", e))
            return

        signal = route_emotion(user_text, tool_mode=tool_mode)

        self.current_expression = requested_expr or signal.eye_expression

        self._maybe_show_reaction_gif(
            user_text,
            after_gif_expression=self.current_expression,
        )

        self.set_presence("thinking", "curious")
        threading.Thread(
            target=self._respond,
            args=(user_text, signal),
            daemon=True,
        ).start()

    def _respond(self, user_text: str, signal=None):
        now_ctx = self.get_local_datetime_context()
        mem_pack = self._memory_pack(user_text)

        if _CALENDAR_AVAILABLE:
            try:
                cal_today = build_today_context()
                cal_week = build_calendar_context(days=7)
                cal_parts = [x for x in [cal_today, cal_week] if x]

                if cal_parts:
                    cal_block = "\n".join(cal_parts)
                    mem_pack = cal_block + "\n\n" + mem_pack
            except Exception as ce:
                print("[CALENDAR] Context error: " + str(ce))

        system_prompt = build_system_prompt(
            now_ctx,
            self.current_chat_name,
            mem_pack,
        )

        if signal:
            system_prompt += f"\n\n[EMOTIONAL CONTEXT]\n{signal.system_hint}"

        system_prompt += (
            "\n\n[ABSOLUTE RULE - NEVER BREAK THIS] "
            "You are a TEXT-ONLY voice assistant. You CANNOT show, send, paste, describe, "
            "suggest, or reference any GIF, image, meme, emoji sequence, or visual media. "
            "FORBIDDEN phrases include: '[Image of', 'here is a GIF', 'here's a GIF', "
            "'[cartoon', '[smiling', '[animated', 'check out this', 'sending you a'. "
            "If you are tempted to show an image, DO NOT. Just respond in plain spoken words only. "
            "The display system handles ALL visuals automatically without your involvement."
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
        self.root.after(500, lambda: self.set_presence("speaking", final_expression))

    def _call_model_async(self, user_text: str):
        def worker():
            now_ctx = self.get_local_datetime_context()
            mem_snips = self._memory_pack(user_text)

            system_prompt = build_system_prompt(
                now_ctx,
                self.current_chat_name,
                mem_snips,
            )

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