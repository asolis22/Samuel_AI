# ui/personality_panel.py
import re
import tkinter as tk
from tkinter import ttk, messagebox

import Samuel_AI.core.samuel_store as store
from Samuel_AI.core.llm_ollama import ollama_chat
from ui.theme import BG, PANEL, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2, TEXT_MODEL
from ui.prompts import build_system_prompt


# -----------------------------
# Style signals + rule updates
# -----------------------------
def analyze_style(reply: str) -> dict:
    t = reply or ""
    return {
        "has_ellipses": ("..." in t) or ("…" in t),
        "too_long": len(t) > 420,
        "robot_words": bool(re.search(r"\b(parameters|calibrate|functioning|as designed|fluctuation|system)\b", t, re.I)),
        "too_many_paras": t.count("\n\n") >= 2,
        "ends_question": t.strip().endswith("?"),
        "has_maam": bool(re.search(r"\bma['’]?am\b", t, re.I)),
    }


def update_rules_from_rating(reply: str, rating: int) -> None:
    sig = analyze_style(reply)
    good = rating <= 2
    bad = rating >= 4

    def bump(rule_key: str, rule_text: str, delta_good: float = 0.15, delta_bad: float = -0.20):
        if good:
            store.upsert_personality_rule(rule_key, rule_text, delta_good)
        elif bad:
            store.upsert_personality_rule(rule_key, rule_text, delta_bad)

    if sig["has_ellipses"]:
        bump("no_ellipses", "Never use ellipses or dramatic pauses. Write clean sentences.", delta_good=0.05, delta_bad=-0.35)

    if sig["robot_words"]:
        bump("no_robot_meta", "Never describe yourself as a system or talk about 'parameters' or 'functioning'.", delta_good=0.05, delta_bad=-0.35)

    if sig["too_long"] or sig["too_many_paras"]:
        bump("brevity", "Be concise by default: 1–3 sentences unless asked for detail.", delta_good=0.10, delta_bad=-0.30)

    if sig["ends_question"]:
        bump("one_followup", "Often end with one short follow-up question when it helps continue the conversation.", delta_good=0.20, delta_bad=-0.10)

    if sig["has_maam"]:
        bump("maam", "Use 'ma’am' occasionally, not every sentence.", delta_good=0.10, delta_bad=-0.10)


def _clean_personality_glitches(text: str) -> str:
    t = (text or "").strip()
    t = t.replace("...", ".").replace("..", ".")
    t = t.replace("It’s…", "It’s").replace("It's…", "It's").replace("I am…", "I am").replace("I’m…", "I’m")
    return t


def _avoidance_note(prev_reply: str) -> str:
    """
    For bad ratings: generate a compact instruction to avoid the same patterns again.
    """
    sig = analyze_style(prev_reply)
    notes = []

    if sig["has_ellipses"]:
        notes.append("Avoid ellipses and dramatic pauses.")
    if sig["robot_words"]:
        notes.append("Avoid robotic self-analysis (parameters/system/functioning).")
    if sig["too_long"] or sig["too_many_paras"]:
        notes.append("Keep it short: 1–3 sentences.")
    if sig["has_maam"]:
        notes.append("Use 'ma’am' sparingly.")
    # Even if none triggered, still push for variety
    notes.append("Do not reuse phrasing from the previous response. Generate a fresh response.")

    return " ".join(notes)

def _normalize_for_compare(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9\s']", "", s)
    return s

def _jaccard(a: str, b: str) -> float:
    wa = set(_normalize_for_compare(a).split())
    wb = set(_normalize_for_compare(b).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(1, len(wa | wb))

def _too_similar(new_reply: str, old_reply: str, threshold: float = 0.72) -> bool:
    # exact/near-exact
    if _normalize_for_compare(new_reply) == _normalize_for_compare(old_reply):
        return True
    # token overlap similarity
    return _jaccard(new_reply, old_reply) >= threshold

def _banlist_from_reply(old_reply: str, max_phrases: int = 6) -> str:
    """
    Pull a few short phrases from the last reply to ban reuse.
    Keeps it simple: 2–4 word chunks.
    """
    words = _normalize_for_compare(old_reply).split()
    phrases = []
    for n in (4, 3, 2):
        for i in range(0, max(0, len(words) - n + 1), max(1, n)):
            ph = " ".join(words[i:i+n]).strip()
            if ph and ph not in phrases:
                phrases.append(ph)
            if len(phrases) >= max_phrases:
                break
        if len(phrases) >= max_phrases:
            break
    return "; ".join([f'"{p}"' for p in phrases[:max_phrases]])


class PersonalityPanel(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app

        self.title("Personality Training")
        self.configure(bg=BG)
        self.geometry("1020x680")
        self.minsize(900, 560)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Q&A trainer state
        self.qa_last_question = ""
        self.qa_last_reply = ""

        # Prompt trainer state
        self.p_last_directive = ""
        self.p_last_reply = ""

        self._build_ui()

    # -----------------------------
    # UI
    # -----------------------------
    def _build_ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=16, pady=(16, 8))

        tk.Label(header, text="PERSONALITY TRAINING", bg=BG, fg=TEXT, font=("Menlo", 18, "bold")).pack(side="left")
        self.status = tk.Label(header, text="● TRAINING MODE", bg=BG, fg=ACCENT2, font=("Menlo", 11, "bold"))
        self.status.pack(side="right")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.tab_qa = tk.Frame(self.tabs, bg=BG)
        self.tab_prompt = tk.Frame(self.tabs, bg=BG)

        self.tabs.add(self.tab_qa, text="Q&A Trainer (with correction)")
        self.tabs.add(self.tab_prompt, text="Prompt Trainer (no correction)")

        self._build_qa_tab()
        self._build_prompt_tab()

    # -----------------------------
    # Shared prompt builder
    # -----------------------------
    def _build_training_system_prompt(self, query_text: str) -> str:
        today_str = self.app._today_str() if hasattr(self.app, "_today_str") else ""
        base_mem = ""
        try:
            base_mem = self.app._memory_pack(query_text) if hasattr(self.app, "_memory_pack") else ""
        except Exception:
            base_mem = ""

        # Strong rules at the top + example pack
        rules_pack = ""
        try:
            rules_pack = store.build_personality_rules_pack(max_rules=10)
        except Exception:
            rules_pack = ""

        ppack = ""
        try:
            ppack = store.build_personality_pack(query_text, max_items=6)
        except Exception:
            ppack = ""

        mem_pack = "\n\n".join([x for x in [base_mem, rules_pack, ppack] if x and x.strip()]).strip()

        system = build_system_prompt(today_str, getattr(self.app, "current_chat_name", "DEFAULT"), mem_pack)

        # Training constraints (targets)
        system += (
            "\n\nSTYLE RULES (obey):\n"
            "- Default 1–3 sentences.\n"
            "- If the user asks a simple question: answer in 1 sentence.\n"
            "- No ellipses.\n"
            "- No robotic self-analysis.\n"
            "- Do not talk about parameters, states, calibration, or 'functioning'.\n"
            "- Dry humor is fine, but keep it subtle.\n"
        )
        return system

    # =====================================================
    # TAB 1: Q&A Trainer (correction required for 4/5)
    # =====================================================
    def _build_qa_tab(self):
        body = tk.Frame(self.tab_qa, bg=BG)
        body.pack(fill="both", expand=True, padx=0, pady=10)

        left = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        right = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)

        # LEFT
        lpad = tk.Frame(left, bg=PANEL)
        lpad.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(lpad, text="Give me your question", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        self.qa_q_txt = tk.Text(
            lpad, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=4, wrap="word"
        )
        self.qa_q_txt.pack(fill="x", pady=(10, 10))

        qa_btn_row = tk.Frame(lpad, bg=PANEL)
        qa_btn_row.pack(fill="x", pady=(0, 12))

        tk.Button(
            qa_btn_row, text="GENERATE SAMUEL",
            bg=ACCENT, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.qa_generate_reply
        ).pack(side="left")

        tk.Label(
            qa_btn_row,
            text="Rate it. If 4–5, you must write your preferred response.",
            bg=PANEL, fg=MUTED, font=("Menlo", 10)
        ).pack(side="left", padx=10)

        tk.Frame(lpad, bg=BORDER, height=1).pack(fill="x", pady=(4, 12))

        tk.Label(lpad, text="Samuel’s response", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        self.qa_reply_txt = tk.Text(
            lpad, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=12, wrap="word"
        )
        self.qa_reply_txt.pack(fill="both", expand=True, pady=(10, 0))
        self.qa_reply_txt.config(state="disabled")

        # RIGHT
        rpad = tk.Frame(right, bg=PANEL)
        rpad.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(rpad, text="Rate it (1=best, 5=worst)", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        self.qa_rating_var = tk.IntVar(value=3)
        self.qa_rating_box = ttk.Combobox(rpad, values=[1, 2, 3, 4, 5], state="readonly", width=10, textvariable=self.qa_rating_var)
        self.qa_rating_box.pack(anchor="w", pady=(10, 16))

        tk.Label(rpad, text="If 4 or 5, write the better response", bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")).pack(anchor="w")

        self.qa_correct_txt = tk.Text(
            rpad, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=12, wrap="word"
        )
        self.qa_correct_txt.pack(fill="both", expand=True, pady=(10, 10))

        tk.Button(
            rpad, text="SAVE TRAINING EXAMPLE",
            bg=ACCENT2, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.qa_save_example
        ).pack(anchor="w")

    def qa_generate_reply(self):
        q = (self.qa_q_txt.get("1.0", "end-1c") or "").strip()
        if not q:
            messagebox.showinfo("Empty", "Type a question first.")
            return

        system = self._build_training_system_prompt(q)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": q},
        ]

        try:
            reply = ollama_chat(TEXT_MODEL, messages, temperature=0.35)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        reply = _clean_personality_glitches(reply)

        self.qa_last_question = q
        self.qa_last_reply = (reply or "").strip()

        self.qa_reply_txt.config(state="normal")
        self.qa_reply_txt.delete("1.0", "end")
        self.qa_reply_txt.insert("1.0", self.qa_last_reply)
        self.qa_reply_txt.config(state="disabled")

    def qa_save_example(self):
        if not self.qa_last_question or not self.qa_last_reply:
            messagebox.showinfo("Nothing to save", "Generate a Samuel response first.")
            return

        rating = int(self.qa_rating_var.get() or 3)
        corrected = (self.qa_correct_txt.get("1.0", "end-1c") or "").strip()

        if rating >= 4 and not corrected:
            messagebox.showwarning("Correction required", "If you rate 4 or 5, please type the response you wanted.")
            return

        try:
            store.add_personality_example(
                prompt=self.qa_last_question,
                samuel_reply=self.qa_last_reply,
                rating=rating,
                corrected_reply=corrected if corrected else None,
            )
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return

        # Update rule weights from rating + detected signals
        try:
            update_rules_from_rating(self.qa_last_reply, rating)
        except Exception:
            pass

        # Clear for next
        self.qa_q_txt.delete("1.0", "end")
        self.qa_reply_txt.config(state="normal")
        self.qa_reply_txt.delete("1.0", "end")
        self.qa_reply_txt.config(state="disabled")
        self.qa_correct_txt.delete("1.0", "end")
        self.qa_rating_var.set(3)

        messagebox.showinfo("Saved", "Training example saved (and rules updated).")

    # =====================================================
    # TAB 2: Prompt Trainer (no correction required)
    # =====================================================
    def _build_prompt_tab(self):
        body = tk.Frame(self.tab_prompt, bg=BG)
        body.pack(fill="both", expand=True, padx=0, pady=10)

        left = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        right = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)

        # LEFT
        lpad = tk.Frame(left, bg=PANEL)
        lpad.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(lpad, text="Give a style prompt (directive)", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")
        tk.Label(
            lpad,
            text='Examples: "Be confident."  "Be witty and short."  "Be gentle, not therapist-y."',
            bg=PANEL, fg=MUTED, font=("Menlo", 10)
        ).pack(anchor="w", pady=(6, 0))

        self.p_prompt_txt = tk.Text(
            lpad, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=4, wrap="word"
        )
        self.p_prompt_txt.pack(fill="x", pady=(10, 10))

        p_btn_row = tk.Frame(lpad, bg=PANEL)
        p_btn_row.pack(fill="x", pady=(0, 12))

        tk.Button(
            p_btn_row, text="GENERATE",
            bg=ACCENT, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.p_generate
        ).pack(side="left")

        tk.Button(
            p_btn_row, text="NEW RESPONSE (learn from rating)",
            bg=ACCENT2, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.p_new_response
        ).pack(side="left", padx=10)

        tk.Frame(lpad, bg=BORDER, height=1).pack(fill="x", pady=(4, 12))

        tk.Label(lpad, text="Samuel’s response", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        self.p_reply_txt = tk.Text(
            lpad, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=12, wrap="word"
        )
        self.p_reply_txt.pack(fill="both", expand=True, pady=(10, 0))
        self.p_reply_txt.config(state="disabled")

        # RIGHT
        rpad = tk.Frame(right, bg=PANEL)
        rpad.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(rpad, text="Rate it (1=best, 5=worst)", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        self.p_rating_var = tk.IntVar(value=3)
        self.p_rating_box = ttk.Combobox(rpad, values=[1, 2, 3, 4, 5], state="readonly", width=10, textvariable=self.p_rating_var)
        self.p_rating_box.pack(anchor="w", pady=(10, 10))

        tk.Label(
            rpad,
            text="No correction needed here. Rate it, then click NEW RESPONSE.\nGood rating = keep patterns. Bad rating = avoid patterns.",
            bg=PANEL, fg=MUTED, font=("Menlo", 10)
        ).pack(anchor="w", pady=(10, 0))

        tk.Frame(rpad, bg=BORDER, height=1).pack(fill="x", pady=(16, 10))

        tk.Label(rpad, text="(Optional) Notes for yourself", bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")).pack(anchor="w")
        self.p_notes = tk.Text(
            rpad, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=6, wrap="word"
        )
        self.p_notes.pack(fill="both", expand=True, pady=(8, 0))

    def _prompt_trainer_system(self, directive: str, extra_instruction: str = "") -> str:
        """
        Builds a system prompt for the Prompt Trainer.
        """
        system = self._build_training_system_prompt(directive)
        if extra_instruction.strip():
            system += "\n\nADDITIONAL INSTRUCTION (obey):\n" + extra_instruction.strip() + "\n"
        return system

    def _prompt_trainer_user_message(self, directive: str) -> str:
        # We make it explicit: the directive is the style request, and we want a sample reply
        return (
            f"STYLE DIRECTIVE:\n{directive}\n\n"
            "Write a short response that follows the directive. Do not mention the directive explicitly."
        )

    def p_generate(self):
        directive = (self.p_prompt_txt.get("1.0", "end-1c") or "").strip()
        if not directive:
            messagebox.showinfo("Empty", "Type a style prompt first.")
            return

        system = self._prompt_trainer_system(directive)
        user_msg = self._prompt_trainer_user_message(directive)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]

        try:
            reply = ollama_chat(TEXT_MODEL, messages, temperature=0.45)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        reply = _clean_personality_glitches(reply)

        self.p_last_directive = directive
        self.p_last_reply = (reply or "").strip()

        self.p_reply_txt.config(state="normal")
        self.p_reply_txt.delete("1.0", "end")
        self.p_reply_txt.insert("1.0", self.p_last_reply)
        self.p_reply_txt.config(state="disabled")

    def p_new_response(self):
        if not self.p_last_directive or not self.p_last_reply:
            messagebox.showinfo("Nothing yet", "Generate a response first.")
            return

        directive = self.p_last_directive
        rating = int(self.p_rating_var.get() or 3)
        old = self.p_last_reply

        # Store example (no correction)
        try:
            store.add_personality_example(
                prompt=f"[PROMPT] {directive}",
                samuel_reply=old,
                rating=rating,
                corrected_reply=None,
            )
        except Exception:
            pass

        # Update rule weights from rating + signals
        try:
            update_rules_from_rating(old, rating)
        except Exception:
            pass

        # Build extra instruction based on rating
        if rating <= 2:
            extra = (
                "Keep the same overall tone and brevity that worked, but do NOT reuse wording from the previous response. "
                "Write a fresh response with different phrasing."
            )
        elif rating >= 4:
            extra = _avoidance_note(old)
        else:
            extra = "Try a different approach, but keep it concise."

        banned = _banlist_from_reply(old)

        # Retry loop to FORCE novelty
        best = None
        for attempt in range(1, 6):
            system = self._prompt_trainer_system(
                directive,
                extra_instruction=(
                    f"{extra}\n"
                    f"Hard rule: Your new response must be meaningfully different from the previous one.\n"
                    f"Do NOT reuse any of these phrases: {banned}.\n"
                    f"Do not repeat the same opening line.\n"
                )
            )

            user_msg = self._prompt_trainer_user_message(directive)

            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ]

            try:
                # increase randomness slightly across retries to escape a loop
                temp = 0.48 + (attempt * 0.06)  # 0.54 .. 0.78
                reply = ollama_chat(TEXT_MODEL, messages, temperature=temp)
            except Exception as e:
                messagebox.showerror("Error", str(e))
                return

            reply = _clean_personality_glitches(reply).strip()

            if not reply:
                continue

            if not _too_similar(reply, old, threshold=0.72):
                best = reply
                break

            # keep the least-similar one as fallback
            best = reply

        # If we still ended up too similar, force a visible change by asking for a new angle
        if best and _too_similar(best, old, threshold=0.72):
            best = best + " (Different take.)"

        self.p_last_reply = best or old

        self.p_reply_txt.config(state="normal")
        self.p_reply_txt.delete("1.0", "end")
        self.p_reply_txt.insert("1.0", self.p_last_reply)
        self.p_reply_txt.config(state="disabled")
        # -----------------------------
    def _on_close(self):
        try:
            self.app.personality_mode = False
        except Exception:
            pass
        self.destroy()


def open_personality_panel(app):
    if getattr(app, "personality_win", None) is not None:
        try:
            if app.personality_win.winfo_exists():
                app.personality_win.lift()
                return app.personality_win
        except Exception:
            pass

    win = PersonalityPanel(app)
    app.personality_win = win
    return win