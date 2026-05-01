# ui/memory_panel.py
import random
import tkinter as tk
from tkinter import ttk, messagebox

import Samuel_AI.core.samuel_store as store

# We reuse your extractor functions, but we control WHERE the memories get saved
from Samuel_AI.core.memory_autosave import (
    extract_rule_memories,
    extract_event_memories,
    llm_suggest_memories,
    filter_memories,
)

from ui.theme import BG, PANEL, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2


# -----------------------------
# Training Config
# -----------------------------
TRAINABLE_CATEGORIES_DEFAULT = {
    "profile", "preferences", "relationships", "events",
    "projects", "habits", "goals", "work", "school"
}

BLOCKED_KEYS_DEFAULT = {"item", "note", "misc", "stuff", "temp"}

QUESTION_TEMPLATES = {
    ("profile", "name"): "What’s your name?",
    ("profile", "major"): "What’s your major?",
    ("profile", "school"): "Where do you go to school?",
    ("profile", "workplace"): "Where do you work?",
    ("profile", "location"): "Where do you live?",
    ("work", "title"): "What is your job title?",
    ("school", "degree"): "What degree are you working toward?",
    ("preferences", "favorite_ice_cream"): "What’s your favorite ice cream flavor?",
}

LEARN_QUESTION_BANK = [
    ("profile", "location", "Where do you live?", "adaptive", 1.2),
    ("profile", "major", "What’s your major?", "adaptive", 1.3),
    ("profile", "school", "Where do you go to school?", "adaptive", 1.2),
    ("work", "title", "What is your job title?", "adaptive", 1.1),
    ("preferences", "favorite_ice_cream", "What’s your favorite ice cream flavor?", "adaptive", 1.0),
    ("preferences", "favorite_color", "What’s your favorite color?", "adaptive", 0.9),
    ("preferences", "favorite_music", "What kind of music do you like most?", "adaptive", 0.9),
    ("habits", "sleep_schedule", "What’s your usual sleep schedule like?", "adaptive", 0.9),
    ("goals", "current_goal", "What’s a goal you’re focused on right now?", "adaptive", 1.0),
    ("projects", "current_project", "What project are you working on lately?", "adaptive", 1.0),
]


def make_question(category: str, key: str) -> str:
    cat = (category or "").strip().lower()
    k = (key or "").strip().lower()
    if (cat, k) in QUESTION_TEMPLATES:
        return QUESTION_TEMPLATES[(cat, k)]
    pretty = k.replace("_", " ").strip() or "that"
    return f"What is your {pretty}?"


def _split_mkey(mkey: str):
    mkey = (mkey or "").strip()
    if "." in mkey:
        cat, k = mkey.split(".", 1)
        return cat.strip() or "notes", k.strip() or "item"
    return "notes", mkey or "item"


def _join_mkey(category: str, key: str):
    category = (category or "notes").strip() or "notes"
    key = (key or "item").strip() or "item"
    if "." in key:
        return key
    return f"{category}.{key}"


class MemoryPanel(tk.Toplevel):
    """
    Memory panel with 3 tabs:
    - Saved Memories: browse/edit/delete (NO manual category/key entry)
    - Settings: training mix controls
    - Training: recall/learn training (brain memory)
    """

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app

        self.title("Memory")
        self.configure(bg=BG)
        self.geometry("980x620")
        self.minsize(860, 520)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.selected_id = None
        self.rows_cache = []

        # training state
        self.current_question = None
        self.answer_revealed = False

        # settings
        self.trainable_categories = set(TRAINABLE_CATEGORIES_DEFAULT)
        self.blocked_keys = set(BLOCKED_KEYS_DEFAULT)
        self.recall_weight = tk.DoubleVar(value=0.60)

        # NEW: memory scope
        self.scope_var = tk.StringVar(value="BRAIN (Saved)")

        self._build_ui()
        self.refresh_saved()

    # -------------------------------------------------------
    # Scope helpers
    # -------------------------------------------------------
    def _is_brain_scope(self) -> bool:
        return self.scope_var.get().startswith("BRAIN")

    # -------------------------------------------------------
    # Data fetchers
    # -------------------------------------------------------
    def _list_brain(self, limit=2000):
        rows = store.list_saved_memories(owner=None, limit=limit)
        out = []
        for r in rows:
            cat, k = _split_mkey(r.get("mkey"))
            out.append({
                "id": int(r["id"]),
                "owner": r.get("owner", "user"),
                "category": cat,
                "key": k,
                "mkey": r.get("mkey", ""),
                "value": r.get("value", ""),
                "stability": r.get("stability", "adaptive"),
                "importance": float(r.get("importance", 1.0)),
                "confidence": float(r.get("confidence", 0.7)),
                "source": r.get("source", "manual"),
            })
        return out

    def _search_brain(self, query, limit=2000):
        rows = store.search_saved_memories(query, owner=None, limit=limit)
        out = []
        for r in rows:
            cat, k = _split_mkey(r.get("mkey"))
            out.append({
                "id": int(r["id"]),
                "owner": r.get("owner", "user"),
                "category": cat,
                "key": k,
                "mkey": r.get("mkey", ""),
                "value": r.get("value", ""),
                "stability": r.get("stability", "adaptive"),
                "importance": float(r.get("importance", 1.0)),
                "confidence": float(r.get("confidence", 0.7)),
                "source": r.get("source", "manual"),
            })
        return out

    def _list_chat(self, limit=2000):
        return store.list_chat_memories(self.app.current_chat_id, owner=None, limit=limit)

    def _search_chat(self, query, limit=2000):
        return store.search_chat_memories(self.app.current_chat_id, query, owner=None, limit=limit)

    # -------------------------------------------------------
    # UI
    # -------------------------------------------------------
    def _build_ui(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=16, pady=(16, 8))

        tk.Label(header, text="MEMORY", bg=BG, fg=TEXT, font=("Menlo", 18, "bold")).pack(side="left")
        self.status = tk.Label(header, text="● MEMORY MODE ON", bg=BG, fg=ACCENT2, font=("Menlo", 11, "bold"))
        self.status.pack(side="right")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.tab_saved = tk.Frame(self.tabs, bg=BG)
        self.tab_settings = tk.Frame(self.tabs, bg=BG)
        self.tab_training = tk.Frame(self.tabs, bg=BG)

        self.tabs.add(self.tab_saved, text="Saved Memories")
        self.tabs.add(self.tab_settings, text="Settings")
        self.tabs.add(self.tab_training, text="Training")

        self._build_saved_tab()
        self._build_settings_tab()
        self._build_training_tab()

    # ---------------- Saved Memories Tab ----------------
    def _build_saved_tab(self):
        body = tk.Frame(self.tab_saved, bg=BG)
        body.pack(fill="both", expand=True, pady=10)

        # Left panel (list)
        left = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        search_row = tk.Frame(left, bg=PANEL)
        search_row.pack(fill="x", padx=12, pady=12)

        tk.Label(search_row, text="Search", bg=PANEL, fg=MUTED, font=("Menlo", 11, "bold")).pack(side="left")

        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            search_row, textvariable=self.search_var,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12)
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(10, 10))
        self.search_entry.bind("<Return>", lambda _e: self.refresh_saved())

        self.scope_box = ttk.Combobox(
            search_row,
            textvariable=self.scope_var,
            values=["BRAIN (Saved)", "THIS CHAT (Temporary Notes)"],
            state="readonly",
            width=26
        )
        self.scope_box.pack(side="right", padx=(10, 0))
        self.scope_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh_saved())

        self.refresh_btn = tk.Button(
            search_row, text="REFRESH",
            bg=ACCENT, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.refresh_saved
        )
        self.refresh_btn.pack(side="right")

        list_wrap = tk.Frame(left, bg=PANEL)
        list_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self.mem_list = tk.Listbox(
            list_wrap,
            bg=PANEL, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#11100F",
            relief="flat",
            highlightthickness=0,
            font=("Menlo", 12),
            activestyle="none"
        )
        self.mem_list.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=self.mem_list.yview)
        sb.pack(side="right", fill="y")
        self.mem_list.configure(yscrollcommand=sb.set)

        self.mem_list.bind("<<ListboxSelect>>", self._on_select_saved)

        # Right panel (details + auto remember)
        right = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)

        right_inner = tk.Frame(right, bg=PANEL)
        right_inner.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(right_inner, text="Remember (type naturally)", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        self.auto_txt = tk.Text(
            right_inner,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=4, wrap="word"
        )
        self.auto_txt.pack(fill="x", pady=(10, 8))

        auto_row = tk.Frame(right_inner, bg=PANEL)
        auto_row.pack(fill="x", pady=(0, 12))

        self.auto_btn = tk.Button(
            auto_row,
            text="SAVE (AUTO)",
            bg=ACCENT, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.save_auto
        )
        self.auto_btn.pack(side="left")

        self.auto_hint = tk.Label(
            auto_row,
            text="(Example: “My name is Amairani Solis.”)",
            bg=PANEL, fg=MUTED, font=("Menlo", 10)
        )
        self.auto_hint.pack(side="left", padx=10)

        # Divider
        tk.Frame(right_inner, bg=BORDER, height=1).pack(fill="x", pady=(4, 12))

        tk.Label(right_inner, text="Details (edit after the fact)", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")

        form = tk.Frame(right_inner, bg=PANEL)
        form.pack(fill="x", pady=(10, 10))
        form.grid_columnconfigure(1, weight=1)

        self.owner_var = tk.StringVar(value="user")
        self.stability_var = tk.StringVar(value="adaptive")
        self.importance_var = tk.StringVar(value="1.0")

        self.label_var = tk.StringVar(value="—")  # shows profile.name etc (read-only)

        def field(row, label, widget):
            tk.Label(form, text=label, bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")).grid(
                row=row, column=0, sticky="w", pady=6
            )
            widget.grid(row=row, column=1, sticky="ew", pady=6)

        owner_box = ttk.Combobox(form, textvariable=self.owner_var, values=["user", "samuel"], state="readonly", width=20)
        field(0, "Owner", owner_box)

        label_entry = tk.Entry(form, textvariable=self.label_var, bg=PANEL, fg=MUTED, relief="flat", font=("Menlo", 12), state="readonly")
        field(1, "Label", label_entry)

        self.stability_box = ttk.Combobox(form, textvariable=self.stability_var, values=["core", "adaptive", "temporary"], state="readonly", width=20)
        field(2, "Stability", self.stability_box)

        importance_entry = tk.Entry(form, textvariable=self.importance_var, bg=CARD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=("Menlo", 12))
        field(3, "Importance", importance_entry)

        tk.Label(right_inner, text="Value", bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")).pack(anchor="w", pady=(6, 6))

        self.value_txt = tk.Text(
            right_inner,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=7, wrap="word"
        )
        self.value_txt.pack(fill="both", expand=True)

        btn_row = tk.Frame(right_inner, bg=PANEL)
        btn_row.pack(fill="x", pady=(12, 0))

        self.save_btn = tk.Button(
            btn_row, text="SAVE EDIT",
            bg=ACCENT2, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.save_edit
        )
        self.save_btn.pack(side="left")

        self.delete_btn = tk.Button(
            btn_row, text="DELETE",
            bg="#B85C5C", fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.delete_current
        )
        self.delete_btn.pack(side="left", padx=10)

        self.close_btn = tk.Button(
            btn_row, text="CLOSE",
            bg=CARD, fg=TEXT,
            relief="flat", font=("Menlo", 11, "bold"),
            command=self._on_close
        )
        self.close_btn.pack(side="right")

    def refresh_saved(self):
        store.init_db()
        q = (self.search_var.get() or "").strip()

        if self._is_brain_scope():
            rows = self._search_brain(q, 2000) if q else self._list_brain(2000)
        else:
            rows = self._search_chat(q, 2000) if q else self._list_chat(2000)

        self.rows_cache = rows
        self.mem_list.delete(0, "end")

        for r in rows:
            value_preview = (r.get("value") or "").strip().replace("\n", " ")
            if len(value_preview) > 90:
                value_preview = value_preview[:90] + "…"
            label = value_preview if value_preview else f"{r.get('category','')}.{r.get('key','')}"
            self.mem_list.insert("end", label)

        self.selected_id = None
        self._clear_editor()

        # If chat scope, lock stability to temporary
        if not self._is_brain_scope():
            self.stability_var.set("temporary")
            try:
                self.stability_box.config(state="disabled")
            except Exception:
                pass
        else:
            try:
                self.stability_box.config(state="readonly")
            except Exception:
                pass

    def _clear_editor(self):
        self.owner_var.set("user")
        self.stability_var.set("adaptive" if self._is_brain_scope() else "temporary")
        self.importance_var.set("1.0")
        self.label_var.set("—")
        self.value_txt.delete("1.0", "end")

    def _on_select_saved(self, _e=None):
        sel = self.mem_list.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self.rows_cache):
            return

        row = self.rows_cache[idx]
        self.selected_id = row.get("id")

        owner = row.get("owner", "user")
        self.owner_var.set(owner)

        stability = row.get("stability", "adaptive" if self._is_brain_scope() else "temporary")
        self.stability_var.set(stability)

        self.importance_var.set(str(row.get("importance", 1.0)))

        # label shown read-only
        if self._is_brain_scope():
            label = row.get("mkey") or _join_mkey(row.get("category"), row.get("key"))
        else:
            label = _join_mkey(row.get("category"), row.get("key"))
        self.label_var.set(label)

        self.value_txt.delete("1.0", "end")
        self.value_txt.insert("1.0", row.get("value", ""))

    # -------------------------------------------------------
    # AUTO SAVE (natural language)
    # -------------------------------------------------------
    def save_auto(self):
        text = (self.auto_txt.get("1.0", "end-1c") or "").strip()
        if not text:
            messagebox.showinfo("Empty", "Type what you want Samuel to remember.")
            return

        try:
            # Reuse your pipeline, but we decide where it saves
            rule = extract_rule_memories(text)
            events = extract_event_memories(text)
            llm = llm_suggest_memories(text, recent_context="", max_items=4)

            merged = filter_memories(rule + events + llm)

            n = 0
            for m in merged:
                # If user is browsing chat scope, force these to be chat-only notes
                if not self._is_brain_scope():
                    m.stability = "temporary"
                    store.remember(
                        m.owner,
                        m.category,
                        m.key,
                        m.value,
                        stability="temporary",
                        importance=float(m.importance),
                        chat_id=self.app.current_chat_id,
                        source="manual",
                    )
                    n += 1
                else:
                    # Brain scope: store according to extracted stability (core/adaptive/temporary)
                    store.remember(
                        m.owner,
                        m.category,
                        m.key,
                        m.value,
                        stability=m.stability,
                        importance=float(m.importance),
                        chat_id=self.app.current_chat_id,
                        source="manual",
                    )
                    n += 1

        except Exception as e:
            messagebox.showerror("Auto-save failed", str(e))
            return

        self.auto_txt.delete("1.0", "end")
        self.refresh_saved()
        self._toast(f"Saved {n} item(s).")

    # -------------------------------------------------------
    # EDIT/DELETE
    # -------------------------------------------------------
    def save_edit(self):
        if not self.selected_id:
            messagebox.showinfo("Nothing selected", "Select a memory first (or use SAVE (AUTO)).")
            return

        owner = (self.owner_var.get() or "user").strip()
        value = (self.value_txt.get("1.0", "end-1c") or "").strip()

        try:
            importance = float((self.importance_var.get() or "1.0").strip())
        except Exception:
            importance = 1.0

        if self._is_brain_scope():
            stability = (self.stability_var.get() or "adaptive").strip()
            current = store.get_saved_memory_by_id(int(self.selected_id))
            if not current:
                messagebox.showwarning("Missing", "That memory no longer exists.")
                self.refresh_saved()
                return

            # keep the existing label (mkey) so the user doesn't have to label it
            mkey = current.get("mkey") or self.label_var.get()

            store.update_saved_memory_by_id(
                mem_id=int(self.selected_id),
                owner=owner,
                category=current.get("category") or "notes",
                mkey=mkey,
                value=value,
                stability=stability,
                importance=float(importance),
                confidence=float(current.get("confidence", 0.7)),
                source=current.get("source", "manual"),
            )
        else:
            # Chat notes
            store.update_chat_memory_by_id(
                mem_id=int(self.selected_id),
                owner=owner,
                category=self.rows_cache[self.mem_list.curselection()[0]].get("category", "notes"),
                key=self.rows_cache[self.mem_list.curselection()[0]].get("key", "item"),
                value=value,
                importance=float(importance),
            )

        self.refresh_saved()
        self._toast("Saved edit.")

    def delete_current(self):
        if not self.selected_id:
            messagebox.showinfo("Nothing selected", "Select a memory first.")
            return

        ok = messagebox.askyesno("Delete memory", "Are you sure you want to delete this memory?")
        if not ok:
            return

        if self._is_brain_scope():
            store.delete_saved_memory_by_id(int(self.selected_id))
        else:
            store.delete_chat_memory_by_id(int(self.selected_id))

        self.refresh_saved()
        self._toast("Deleted.")

    # ---------------- Settings Tab ----------------
    def _build_settings_tab(self):
        wrap = tk.Frame(self.tab_settings, bg=BG)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)

        card = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=False, padx=0, pady=0)

        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill="x", padx=14, pady=14)

        tk.Label(inner, text="Training Mix", bg=PANEL, fg=TEXT, font=("Menlo", 14, "bold")).pack(anchor="w")

        tk.Label(
            inner,
            text="Controls how often Samuel quizzes from known brain memories (Recall) vs missing info (Learn).",
            bg=PANEL, fg=MUTED, font=("Menlo", 11)
        ).pack(anchor="w", pady=(6, 10))

        row = tk.Frame(inner, bg=PANEL)
        row.pack(fill="x", pady=(6, 6))

        tk.Label(row, text="Recall %", bg=PANEL, fg=MUTED, font=("Menlo", 11, "bold")).pack(side="left")
        self.recall_scale = tk.Scale(
            row,
            from_=0.0, to=1.0,
            resolution=0.05,
            orient="horizontal",
            length=320,
            variable=self.recall_weight,
            bg=PANEL, fg=TEXT,
            highlightthickness=0
        )
        self.recall_scale.pack(side="left", padx=(12, 0))

        self.mix_label = tk.Label(row, text="", bg=PANEL, fg=TEXT, font=("Menlo", 11, "bold"))
        self.mix_label.pack(side="left", padx=12)
        self._refresh_mix_label()

        def _on_scale(_v=None):
            self._refresh_mix_label()
        self.recall_scale.config(command=_on_scale)

        tk.Label(inner, text="Trainable Categories", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w", pady=(16, 6))
        tk.Label(inner, text="(Used for Recall pool filtering.)", bg=PANEL, fg=MUTED, font=("Menlo", 10)).pack(anchor="w")

        cats_row = tk.Frame(inner, bg=PANEL)
        cats_row.pack(fill="x", pady=(8, 0))

        self.cat_vars = {}
        for cat in sorted(TRAINABLE_CATEGORIES_DEFAULT):
            var = tk.BooleanVar(value=(cat in self.trainable_categories))
            self.cat_vars[cat] = var
            cb = tk.Checkbutton(
                cats_row, text=cat,
                variable=var,
                bg=PANEL, fg=TEXT, selectcolor=PANEL,
                font=("Menlo", 11),
                activebackground=PANEL, activeforeground=TEXT
            )
            cb.pack(side="left", padx=(0, 10))

        tk.Label(inner, text="Blocked Keys", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w", pady=(16, 6))
        tk.Label(inner, text="(Keys we do NOT want to quiz because they’re too generic.)", bg=PANEL, fg=MUTED, font=("Menlo", 10)).pack(anchor="w")

        self.blocked_entry = tk.Entry(inner, bg=CARD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=("Menlo", 12))
        self.blocked_entry.pack(fill="x", pady=(8, 0))
        self.blocked_entry.insert(0, ", ".join(sorted(self.blocked_keys)))

        apply_btn = tk.Button(
            inner,
            text="APPLY SETTINGS",
            bg=ACCENT, fg="#11100F",
            relief="flat",
            font=("Menlo", 11, "bold"),
            command=self._apply_settings
        )
        apply_btn.pack(anchor="w", pady=(14, 0))

    def _refresh_mix_label(self):
        r = float(self.recall_weight.get())
        self.mix_label.config(text=f"{int(r*100)}% Recall / {int((1-r)*100)}% Learn")

    def _apply_settings(self):
        self.trainable_categories = {c for c, v in self.cat_vars.items() if v.get()}
        raw = (self.blocked_entry.get() or "").strip()
        parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
        self.blocked_keys = set(parts)
        messagebox.showinfo("Saved", "Training settings applied.")

    # ---------------- Training Tab ----------------
    def _build_training_tab(self):
        wrap = tk.Frame(self.tab_training, bg=BG)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)

        card = tk.Frame(wrap, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)

        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=18, pady=18)

        tk.Label(inner, text="Active Recall Training", bg=PANEL, fg=TEXT, font=("Menlo", 18, "bold")).pack(anchor="w")

        self.q_label = tk.Label(inner, text="Question: —", bg=PANEL, fg=TEXT, font=("Menlo", 14, "bold"))
        self.q_label.pack(anchor="w", pady=(12, 10))

        self.meta_label = tk.Label(inner, text="", bg=PANEL, fg=MUTED, font=("Menlo", 11))
        self.meta_label.pack(anchor="w", pady=(0, 18))

        self.reveal_box = tk.Text(
            inner,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=3, wrap="word"
        )
        self.reveal_box.pack(fill="x", pady=(0, 12))
        self.reveal_box.insert("1.0", "Answer will appear here when you click REVEAL ANSWER.")
        self.reveal_box.config(state="disabled")

        corr_row = tk.Frame(inner, bg=PANEL)
        corr_row.pack(fill="x", pady=(6, 10))

        tk.Label(corr_row, text="Correction / Answer:", bg=PANEL, fg=MUTED, font=("Menlo", 11, "bold")).pack(side="left")

        self.correction_entry = tk.Entry(
            corr_row,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12)
        )
        self.correction_entry.pack(side="left", fill="x", expand=True, padx=(12, 0))

        btn_row = tk.Frame(inner, bg=PANEL)
        btn_row.pack(anchor="w", pady=(10, 0))

        tk.Button(
            btn_row, text="START / NEXT",
            bg=ACCENT2, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.next_question
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_row, text="REVEAL ANSWER",
            bg=CARD, fg=TEXT,
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.reveal_answer
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_row, text="✅ CORRECT",
            bg="#9AD39C", fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=lambda: self.mark(correct=True)
        ).pack(side="left", padx=(10, 10))

        tk.Button(
            btn_row, text="❌ WRONG",
            bg="#E08C8C", fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=lambda: self.mark(correct=False)
        ).pack(side="left")

    def _apply_settings_silent(self):
        if hasattr(self, "cat_vars") and self.cat_vars:
            self.trainable_categories = {c for c, v in self.cat_vars.items() if v.get()}
        if hasattr(self, "blocked_entry"):
            raw = (self.blocked_entry.get() or "").strip()
            parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
            self.blocked_keys = set(parts)

    def _get_recall_pool(self):
        rows = store.list_saved_memories(owner="user", limit=800)
        pool = []
        for r in rows:
            if (r.get("stability") or "") == "temporary":
                continue
            cat, k = _split_mkey(r.get("mkey"))
            if cat not in self.trainable_categories:
                continue
            if k.lower() in self.blocked_keys:
                continue
            pool.append({
                "id": int(r["id"]),
                "category": cat,
                "key": k,
                "value": r.get("value", ""),
                "stability": r.get("stability", "adaptive"),
                "importance": float(r.get("importance", 1.0)),
            })
        return pool

    def _get_learn_pool(self):
        pool = []
        for (cat, key, q, stab, imp) in LEARN_QUESTION_BANK:
            existing = store.get_memory_value("user", cat, key)
            if existing is None or str(existing).strip() == "":
                pool.append({"category": cat, "key": key, "question": q, "stability": stab, "importance": float(imp)})
        return pool

    def _pick_weighted(self, items, weight_fn):
        if not items:
            return None
        weights = []
        for it in items:
            try:
                w = float(weight_fn(it))
            except Exception:
                w = 1.0
            weights.append(max(0.1, w))
        return random.choices(items, weights=weights, k=1)[0]

    def next_question(self):
        self._apply_settings_silent()
        recall_pool = self._get_recall_pool()
        learn_pool = self._get_learn_pool()

        if not recall_pool and not learn_pool:
            messagebox.showinfo("No questions", "No usable memories to quiz and no learn-questions available.")
            return

        r = float(self.recall_weight.get())
        if recall_pool and learn_pool:
            use_recall = (random.random() < r)
        elif recall_pool:
            use_recall = True
        else:
            use_recall = False

        if use_recall:
            mem = self._pick_weighted(recall_pool, lambda m: float(m.get("importance", 1.0)))
            category = mem.get("category", "")
            key = mem.get("key", "")
            q = make_question(category, key)

            self.current_question = {
                "mode": "recall",
                "category": category,
                "key": key,
                "value": mem.get("value", ""),
                "stability": mem.get("stability", "adaptive"),
                "importance": float(mem.get("importance", 1.0)),
            }
            meta = f"(mode=recall | category={category} | key={key} | importance={self.current_question['importance']:.2f})"
        else:
            item = self._pick_weighted(learn_pool, lambda m: float(m.get("importance", 1.0)))
            self.current_question = {
                "mode": "learn",
                "category": item["category"],
                "key": item["key"],
                "value": "",
                "stability": item.get("stability", "adaptive"),
                "importance": float(item.get("importance", 1.0)),
                "question": item.get("question") or make_question(item["category"], item["key"]),
            }
            q = self.current_question["question"]
            meta = f"(mode=learn | category={self.current_question['category']} | key={self.current_question['key']} | importance={self.current_question['importance']:.2f})"

        self.answer_revealed = False
        self.q_label.config(text=f"Question: {q}")
        self.meta_label.config(text=meta)
        self.correction_entry.delete(0, "end")

        self.reveal_box.config(state="normal")
        self.reveal_box.delete("1.0", "end")
        self.reveal_box.insert("1.0", "Answer will appear here when you click REVEAL ANSWER.")
        self.reveal_box.config(state="disabled")

    def reveal_answer(self):
        if not self.current_question:
            return
        if self.current_question["mode"] == "recall":
            answer = self.current_question.get("value", "")
        else:
            answer = "I don’t know yet. (Type the real answer below, then click CORRECT to save it.)"

        self.reveal_box.config(state="normal")
        self.reveal_box.delete("1.0", "end")
        self.reveal_box.insert("1.0", str(answer))
        self.reveal_box.config(state="disabled")
        self.answer_revealed = True

    def mark(self, correct: bool):
        if not self.current_question:
            return

        mode = self.current_question["mode"]
        cat = self.current_question["category"]
        key = self.current_question["key"]
        stability = self.current_question.get("stability", "adaptive")
        imp = float(self.current_question.get("importance", 1.0))
        typed = (self.correction_entry.get() or "").strip()

        if mode == "learn":
            if not typed:
                messagebox.showwarning("Missing answer", "For Learn questions, type the real answer first.")
                return
            store.remember("user", cat, key, typed, stability=stability, importance=max(0.9, imp), source="quiz")
        else:
            # recall mode
            if correct:
                store.remember("user", cat, key, self.current_question.get("value", ""), stability=stability, importance=min(2.0, imp + 0.10), source="quiz")
            else:
                if typed:
                    store.remember("user", cat, key, typed, stability=stability, importance=max(0.8, imp), source="quiz")
                else:
                    store.remember("user", cat, key, self.current_question.get("value", ""), stability=stability, importance=max(0.0, imp - 0.10), source="quiz")

        try:
            self.refresh_saved()
        except Exception:
            pass

        self.next_question()

    # -------------------------------------------------------
    def _toast(self, msg: str):
        self.status.config(text=f"● {msg}", fg=ACCENT2)
        self.after(1600, lambda: self.status.config(text="● MEMORY MODE ON", fg=ACCENT2))

    def _on_close(self):
        try:
            self.app.memory_mode = False
        except Exception:
            pass
        self.destroy()


def open_memory_panel(app):
    if getattr(app, "memory_win", None) is not None:
        try:
            if app.memory_win.winfo_exists():
                app.memory_win.lift()
                return app.memory_win
        except Exception:
            pass

    win = MemoryPanel(app)
    app.memory_win = win
    return win