# ui/knowledge_panel.py
# Knowledge Panel — shows everything Samuel is learning autonomously.
# User can approve, reject, edit, and delete nuggets.
# Open with: Alpha.k.x0.1.Kn0wledge

import tkinter as tk
from tkinter import ttk, messagebox
import time

import knowledge_store as ks
from ui.theme import (
    BG, PANEL, CARD, BORDER,
    TEXT, MUTED, ACCENT, ACCENT2, ACCENT3,
)


def _ts_label(ts: int) -> str:
    try:
        return time.strftime("%b %d  %I:%M %p", time.localtime(int(ts)))
    except Exception:
        return ""


class KnowledgePanel(tk.Toplevel):
    """
    Three-tab panel:
      - Pending   : nuggets waiting for your review  (approve / reject / edit)
      - Approved  : nuggets Samuel is actively using  (edit / delete)
      - Activity  : recent autonomous queries + stats
    """

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app

        self.title("KNOWLEDGE")
        self.configure(bg=BG)
        self.geometry("1020x640")
        self.minsize(880, 520)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._rows_cache: list = []
        self._selected_id: int = None

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # UI BUILD
    # ------------------------------------------------------------------

    def _build_ui(self):
        # ---- Header ----
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=16, pady=(16, 8))

        tk.Label(
            hdr, text="KNOWLEDGE BASE",
            bg=BG, fg=TEXT, font=("Menlo", 18, "bold")
        ).pack(side="left")

        self._status_lbl = tk.Label(
            hdr, text="● LEARNING ACTIVE",
            bg=BG, fg=ACCENT2, font=("Menlo", 11, "bold")
        )
        self._status_lbl.pack(side="right")

        # ---- Stats bar ----
        self._stats_lbl = tk.Label(
            self, text="",
            bg=BG, fg=MUTED, font=("Menlo", 11)
        )
        self._stats_lbl.pack(anchor="w", padx=18, pady=(0, 6))

        # ---- Tabs ----
        self._tabs = ttk.Notebook(self)
        self._tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._tab_pending  = tk.Frame(self._tabs, bg=BG)
        self._tab_approved = tk.Frame(self._tabs, bg=BG)
        self._tab_activity = tk.Frame(self._tabs, bg=BG)

        self._tabs.add(self._tab_pending,  text="  Pending Review  ")
        self._tabs.add(self._tab_approved, text="  Approved  ")
        self._tabs.add(self._tab_activity, text="  Activity Log  ")

        self._build_nugget_tab(self._tab_pending,  mode="pending")
        self._build_nugget_tab(self._tab_approved, mode="approved")
        self._build_activity_tab()

        self._tabs.bind("<<NotebookTabChanged>>", lambda _e: self.refresh())

    # ------------------------------------------------------------------
    # NUGGET TAB  (shared by Pending + Approved)
    # ------------------------------------------------------------------

    def _build_nugget_tab(self, parent: tk.Frame, mode: str):
        body = tk.Frame(parent, bg=BG)
        body.pack(fill="both", expand=True, pady=10)

        # ---- Left: list ----
        left = tk.Frame(body, bg=PANEL,
                        highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # Search row
        search_row = tk.Frame(left, bg=PANEL)
        search_row.pack(fill="x", padx=12, pady=12)

        tk.Label(
            search_row, text="Search",
            bg=PANEL, fg=MUTED, font=("Menlo", 11, "bold")
        ).pack(side="left")

        sv = tk.StringVar()
        entry = tk.Entry(
            search_row, textvariable=sv,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12)
        )
        entry.pack(side="left", fill="x", expand=True, padx=(10, 10))
        entry.bind("<Return>", lambda _e: self.refresh())

        tk.Button(
            search_row, text="REFRESH",
            bg=ACCENT, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.refresh
        ).pack(side="right")

        # List box
        list_wrap = tk.Frame(left, bg=PANEL)
        list_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        lb = tk.Listbox(
            list_wrap,
            bg=PANEL, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#11100F",
            relief="flat", highlightthickness=0,
            font=("Menlo", 12), activestyle="none"
        )
        lb.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.configure(yscrollcommand=sb.set)

        # ---- Right: detail editor ----
        right = tk.Frame(body, bg=PANEL,
                         highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)

        inner = tk.Frame(right, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            inner, text="Topic",
            bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")
        ).pack(anchor="w")

        topic_var = tk.StringVar()
        topic_entry = tk.Entry(
            inner, textvariable=topic_var,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 13, "bold")
        )
        topic_entry.pack(fill="x", pady=(4, 12))

        tk.Label(
            inner, text="Summary",
            bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")
        ).pack(anchor="w")

        summary_txt = tk.Text(
            inner,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            height=6, wrap="word"
        )
        summary_txt.pack(fill="both", expand=True, pady=(4, 10))

        tk.Label(
            inner, text="Source",
            bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")
        ).pack(anchor="w")

        source_lbl = tk.Label(
            inner, text="—",
            bg=PANEL, fg=MUTED, font=("Menlo", 10),
            anchor="w", wraplength=340, justify="left"
        )
        source_lbl.pack(anchor="w", pady=(2, 12))

        # Button row
        btn_row = tk.Frame(inner, bg=PANEL)
        btn_row.pack(fill="x", pady=(4, 0))

        if mode == "pending":
            tk.Button(
                btn_row, text="✅ APPROVE",
                bg="#9AD39C", fg="#11100F",
                relief="flat", font=("Menlo", 11, "bold"),
                command=lambda: self._approve()
            ).pack(side="left", padx=(0, 8))

            tk.Button(
                btn_row, text="❌ REJECT",
                bg="#B85C5C", fg="#11100F",
                relief="flat", font=("Menlo", 11, "bold"),
                command=lambda: self._reject()
            ).pack(side="left", padx=(0, 8))

            tk.Button(
                btn_row, text="APPROVE ALL",
                bg=ACCENT2, fg="#11100F",
                relief="flat", font=("Menlo", 11, "bold"),
                command=self._approve_all
            ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row, text="SAVE EDIT",
            bg=ACCENT, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=lambda: self._save_edit(topic_var, summary_txt)
        ).pack(side="left", padx=(0, 8))

        tk.Button(
            btn_row, text="DELETE",
            bg="#B85C5C", fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self._delete
        ).pack(side="left")

        tk.Button(
            btn_row, text="CLOSE",
            bg=CARD, fg=TEXT,
            relief="flat", font=("Menlo", 11, "bold"),
            command=self._on_close
        ).pack(side="right")

        # Store refs on self keyed by mode
        setattr(self, f"_{mode}_search_var",  sv)
        setattr(self, f"_{mode}_listbox",     lb)
        setattr(self, f"_{mode}_topic_var",   topic_var)
        setattr(self, f"_{mode}_summary_txt", summary_txt)
        setattr(self, f"_{mode}_source_lbl",  source_lbl)
        setattr(self, f"_{mode}_rows",        [])

        lb.bind("<<ListboxSelect>>",
                lambda e, m=mode: self._on_select(m))

    # ------------------------------------------------------------------
    # ACTIVITY TAB
    # ------------------------------------------------------------------

    def _build_activity_tab(self):
        parent = self._tab_activity
        body   = tk.Frame(parent, bg=BG)
        body.pack(fill="both", expand=True, pady=10)

        card = tk.Frame(body, bg=PANEL,
                        highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="both", expand=True)

        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            inner, text="Recent Autonomous Searches",
            bg=PANEL, fg=TEXT, font=("Menlo", 14, "bold")
        ).pack(anchor="w", pady=(0, 10))

        list_wrap = tk.Frame(inner, bg=PANEL)
        list_wrap.pack(fill="both", expand=True)

        self._activity_lb = tk.Listbox(
            list_wrap,
            bg=PANEL, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#11100F",
            relief="flat", highlightthickness=0,
            font=("Menlo", 12), activestyle="none"
        )
        self._activity_lb.pack(side="left", fill="both", expand=True)

        sb2 = ttk.Scrollbar(list_wrap, orient="vertical",
                             command=self._activity_lb.yview)
        sb2.pack(side="right", fill="y")
        self._activity_lb.configure(yscrollcommand=sb2.set)

        btn_row = tk.Frame(inner, bg=PANEL)
        btn_row.pack(fill="x", pady=(12, 0))

        tk.Button(
            btn_row, text="PURGE ALL REJECTED",
            bg="#B85C5C", fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self._purge_rejected
        ).pack(side="left", padx=(0, 10))

        tk.Button(
            btn_row, text="REFRESH",
            bg=ACCENT, fg="#11100F",
            relief="flat", font=("Menlo", 11, "bold"),
            command=self.refresh
        ).pack(side="left")

    # ------------------------------------------------------------------
    # DATA REFRESH
    # ------------------------------------------------------------------

    def refresh(self):
        ks.init_knowledge_db()
        self._refresh_stats()
        self._refresh_nugget_tab("pending",  approved_val=0)
        self._refresh_nugget_tab("approved", approved_val=1)
        self._refresh_activity()

    def _refresh_stats(self):
        try:
            s = ks.get_knowledge_stats()
            self._stats_lbl.config(
                text=(
                    f"Pages fetched: {s['pages_fetched']}   "
                    f"Pending: {s['nuggets_pending']}   "
                    f"Approved: {s['nuggets_approved']}   "
                    f"Rejected: {s['nuggets_rejected']}   "
                    f"Searches run: {s['queries_run']}"
                )
            )
        except Exception:
            pass

    def _refresh_nugget_tab(self, mode: str, approved_val: int):
        lb:  tk.Listbox  = getattr(self, f"_{mode}_listbox")
        sv:  tk.StringVar = getattr(self, f"_{mode}_search_var")

        q = (sv.get() or "").strip()
        if q:
            rows = ks.search_nuggets(q, approved_only=(approved_val == 1), limit=500)
            rows = [r for r in rows if r.get("approved") == approved_val]
        else:
            rows = ks.list_nuggets(approved=approved_val, limit=500)

        setattr(self, f"_{mode}_rows", rows)

        lb.delete(0, "end")
        for r in rows:
            topic   = (r.get("topic") or "—")[:40]
            summary = (r.get("summary") or "").replace("\n", " ")[:60]
            lb.insert("end", f"{topic}  —  {summary}")

    def _refresh_activity(self):
        self._activity_lb.delete(0, "end")
        try:
            queries = ks.recent_queries(limit=100)
            if not queries:
                self._activity_lb.insert("end", "No autonomous searches yet.")
            for q in queries:
                self._activity_lb.insert("end", "  🔍  " + q)
        except Exception as e:
            self._activity_lb.insert("end", "Error: " + str(e))

    # ------------------------------------------------------------------
    # SELECTION
    # ------------------------------------------------------------------

    def _on_select(self, mode: str):
        lb:   tk.Listbox   = getattr(self, f"_{mode}_listbox")
        rows: list         = getattr(self, f"_{mode}_rows")
        tv:   tk.StringVar = getattr(self, f"_{mode}_topic_var")
        st:   tk.Text      = getattr(self, f"_{mode}_summary_txt")
        sl:   tk.Label     = getattr(self, f"_{mode}_source_lbl")

        sel = lb.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(rows):
            return

        row = rows[idx]
        self._selected_id   = row.get("id")
        self._selected_mode = mode

        tv.set(row.get("topic") or "")

        st.delete("1.0", "end")
        st.insert("1.0", row.get("summary") or "")

        url   = (row.get("source_url") or "")[:80]
        query = row.get("query_origin") or ""
        ts    = _ts_label(row.get("created_ts") or 0)
        sl.config(text=f"{url}\nQuery: {query}\nLearned: {ts}")

    def _current_row(self):
        if self._selected_id is None:
            return None
        mode = getattr(self, "_selected_mode", "pending")
        rows = getattr(self, f"_{mode}_rows", [])
        for r in rows:
            if r.get("id") == self._selected_id:
                return r
        return None

    # ------------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------------

    def _approve(self):
        if self._selected_id is None:
            messagebox.showinfo("Nothing selected", "Select a nugget first.")
            return
        ks.approve_nugget(self._selected_id)
        self._selected_id = None
        self.refresh()
        self._toast("Approved.")

    def _reject(self):
        if self._selected_id is None:
            messagebox.showinfo("Nothing selected", "Select a nugget first.")
            return
        ks.reject_nugget(self._selected_id)
        self._selected_id = None
        self.refresh()
        self._toast("Rejected.")

    def _approve_all(self):
        ok = messagebox.askyesno(
            "Approve All",
            "Approve ALL pending nuggets? Samuel will start using them immediately."
        )
        if not ok:
            return
        rows = getattr(self, "_pending_rows", [])
        for r in rows:
            ks.approve_nugget(r["id"])
        self.refresh()
        self._toast(f"Approved {len(rows)} nuggets.")

    def _save_edit(self, topic_var: tk.StringVar, summary_txt: tk.Text):
        if self._selected_id is None:
            messagebox.showinfo("Nothing selected", "Select a nugget first.")
            return

        new_topic   = (topic_var.get() or "").strip()
        new_summary = (summary_txt.get("1.0", "end-1c") or "").strip()

        if not new_topic or not new_summary:
            messagebox.showwarning("Empty fields", "Topic and summary cannot be empty.")
            return

        conn = ks._connect()
        try:
            with conn:
                conn.execute(
                    "UPDATE knowledge_nuggets SET topic=?, summary=? WHERE id=?;",
                    (new_topic, new_summary, int(self._selected_id))
                )
        finally:
            conn.close()

        self.refresh()
        self._toast("Saved edit.")

    def _delete(self):
        if self._selected_id is None:
            messagebox.showinfo("Nothing selected", "Select a nugget first.")
            return
        ok = messagebox.askyesno("Delete", "Delete this nugget permanently?")
        if not ok:
            return
        ks.delete_nugget(self._selected_id)
        self._selected_id = None
        self.refresh()
        self._toast("Deleted.")

    def _purge_rejected(self):
        ok = messagebox.askyesno(
            "Purge Rejected",
            "Permanently delete ALL rejected nuggets?"
        )
        if not ok:
            return
        n = ks.delete_all_rejected()
        self.refresh()
        self._toast(f"Purged {n} rejected nuggets.")

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _toast(self, msg: str):
        self._status_lbl.config(text="● " + msg, fg=ACCENT)
        self.after(2000, lambda: self._status_lbl.config(
            text="● LEARNING ACTIVE", fg=ACCENT2
        ))

    def _on_close(self):
        self.destroy()


# ------------------------------------------------------------------
# OPENER  (called from gui_app.py)
# ------------------------------------------------------------------

def open_knowledge_panel(app):
    win = getattr(app, "knowledge_win", None)
    if win is not None:
        try:
            if win.winfo_exists():
                win.lift()
                return win
        except Exception:
            pass
    win = KnowledgePanel(app)
    app.knowledge_win = win
    return win
