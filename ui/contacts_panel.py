# ui/contacts_panel.py
# Contacts Panel — view, add, edit, delete Samuel's contact list.
# Auto-populated from conversation. Open with: Alpha.c.x0.1.C0ntacts
import tkinter as tk
from tkinter import ttk, messagebox
import time
from typing import Optional

import Samuel_AI.features.contacts_store as cs
from ui.theme import (
    BG, PANEL, CARD, BORDER,
    TEXT, MUTED, ACCENT, ACCENT2, ACCENT3,
)


def _ts(ts: int) -> str:
    try:
        return time.strftime("%b %d, %Y", time.localtime(int(ts)))
    except Exception:
        return ""


# Relationship tag colours
_TAG_COLORS = {
    "school":   ("#4A7C59", "#9AD39C"),
    "work":     ("#4A5C7C", "#9AB3D3"),
    "family":   ("#7C4A5C", "#D39AB3"),
    "personal": ("#7C6A4A", "#D3C09A"),
}


class ContactsPanel(tk.Toplevel):

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("CONTACTS")
        self.configure(bg=BG)
        self.geometry("1040x660")
        self.minsize(900, 540)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._selected_id: Optional[int] = None
        self._all_rows: list = []

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=16, pady=(16, 6))

        tk.Label(
            hdr, text="CONTACTS",
            bg=BG, fg=TEXT, font=("Menlo", 18, "bold")
        ).pack(side="left")

        self._stats_lbl = tk.Label(
            hdr, text="",
            bg=BG, fg=MUTED, font=("Menlo", 11)
        )
        self._stats_lbl.pack(side="right")

        # Main body — left list + right editor
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._build_left(body)
        self._build_right(body)

    # ---- LEFT: contact list ----
    def _build_left(self, parent):
        left = tk.Frame(parent, bg=PANEL,
                        highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))

        # Search
        sr = tk.Frame(left, bg=PANEL)
        sr.pack(fill="x", padx=12, pady=12)

        tk.Label(sr, text="Search", bg=PANEL, fg=MUTED,
                 font=("Menlo", 11, "bold")).pack(side="left")

        self._search_var = tk.StringVar()
        se = tk.Entry(sr, textvariable=self._search_var,
                      bg=CARD, fg=TEXT, insertbackground=ACCENT,
                      relief="flat", font=("Menlo", 12))
        se.pack(side="left", fill="x", expand=True, padx=(10, 10))
        se.bind("<Return>", lambda _: self.refresh())

        tk.Button(sr, text="SEARCH", bg=ACCENT, fg="#11100F",
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self.refresh).pack(side="right")

        # Filter row
        fr = tk.Frame(left, bg=PANEL)
        fr.pack(fill="x", padx=12, pady=(0, 8))

        tk.Label(fr, text="Filter:", bg=PANEL, fg=MUTED,
                 font=("Menlo", 10)).pack(side="left")

        self._filter_var = tk.StringVar(value="all")
        for label, val in [("All", "all"), ("School", "school"),
                            ("Work", "work"), ("Family", "family"),
                            ("Personal", "personal"), ("Auto", "auto")]:
            tk.Radiobutton(
                fr, text=label, variable=self._filter_var, value=val,
                bg=PANEL, fg=MUTED, selectcolor=CARD,
                activebackground=PANEL, activeforeground=ACCENT,
                font=("Menlo", 10), command=self.refresh
            ).pack(side="left", padx=4)

        # Listbox
        lw = tk.Frame(left, bg=PANEL)
        lw.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._listbox = tk.Listbox(
            lw, bg=PANEL, fg=TEXT,
            selectbackground=ACCENT, selectforeground="#11100F",
            relief="flat", highlightthickness=0,
            font=("Menlo", 12), activestyle="none"
        )
        self._listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lw, orient="vertical", command=self._listbox.yview)
        sb.pack(side="right", fill="y")
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.bind("<<ListboxSelect>>", lambda _: self._on_select())

        # Bottom buttons
        bb = tk.Frame(left, bg=PANEL)
        bb.pack(fill="x", padx=12, pady=(0, 12))

        tk.Button(bb, text="+ NEW CONTACT",
                  bg=ACCENT2, fg="#11100F",
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self._new_contact).pack(side="left", padx=(0, 8))

        tk.Button(bb, text="DELETE",
                  bg="#B85C5C", fg="#11100F",
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self._delete_contact).pack(side="left")

    # ---- RIGHT: editor ----
    def _build_right(self, parent):
        right = tk.Frame(parent, bg=PANEL,
                         highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)

        inner = tk.Frame(right, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(inner, text="CONTACT DETAILS",
                 bg=PANEL, fg=ACCENT, font=("Menlo", 13, "bold")
                 ).pack(anchor="w", pady=(0, 12))

        # Form grid
        fields_frame = tk.Frame(inner, bg=PANEL)
        fields_frame.pack(fill="x")

        self._fields = {}
        form_rows = [
            ("Name *",       "name"),
            ("Nickname",     "nickname"),
            ("Relationship", "relationship"),
            ("Phone",        "phone"),
            ("Email",        "email"),
        ]

        for label, key in form_rows:
            row = tk.Frame(fields_frame, bg=PANEL)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=PANEL, fg=MUTED,
                     font=("Menlo", 10, "bold"), width=14,
                     anchor="w").pack(side="left")
            var = tk.StringVar()
            entry = tk.Entry(row, textvariable=var,
                             bg=CARD, fg=TEXT, insertbackground=ACCENT,
                             relief="flat", font=("Menlo", 12))
            entry.pack(side="left", fill="x", expand=True)
            self._fields[key] = var

        # Tags
        tk.Label(inner, text="Tags  (comma separated)",
                 bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")
                 ).pack(anchor="w", pady=(12, 4))
        self._tags_var = tk.StringVar()
        tk.Entry(inner, textvariable=self._tags_var,
                 bg=CARD, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", font=("Menlo", 12)
                 ).pack(fill="x")

        # Notes
        tk.Label(inner, text="Notes",
                 bg=PANEL, fg=MUTED, font=("Menlo", 10, "bold")
                 ).pack(anchor="w", pady=(12, 4))
        self._notes_txt = tk.Text(
            inner, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12), height=5, wrap="word"
        )
        self._notes_txt.pack(fill="both", expand=True)

        # Source + date
        self._meta_lbl = tk.Label(
            inner, text="", bg=PANEL, fg=MUTED, font=("Menlo", 9),
            anchor="w"
        )
        self._meta_lbl.pack(anchor="w", pady=(8, 0))

        # Buttons
        bb = tk.Frame(inner, bg=PANEL)
        bb.pack(fill="x", pady=(12, 0))

        tk.Button(bb, text="SAVE",
                  bg=ACCENT, fg="#11100F",
                  relief="flat", font=("Menlo", 12, "bold"),
                  command=self._save_contact).pack(side="left", padx=(0, 10))

        tk.Button(bb, text="CLEAR",
                  bg=CARD, fg=TEXT,
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self._clear_form).pack(side="left", padx=(0, 10))

        tk.Button(bb, text="CLOSE",
                  bg=CARD, fg=TEXT,
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self._on_close).pack(side="right")

        self._status_lbl = tk.Label(
            inner, text="", bg=PANEL, fg=ACCENT2, font=("Menlo", 11, "bold")
        )
        self._status_lbl.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # DATA
    # ------------------------------------------------------------------

    def refresh(self):
        cs.init_contacts_db()
        self._refresh_stats()
        self._refresh_list()

    def _refresh_stats(self):
        try:
            s = cs.get_contact_stats()
            self._stats_lbl.config(
                text=(f"Total: {s['total']}   "
                      f"Auto-detected: {s['auto_detected']}   "
                      f"Manual: {s['manual']}")
            )
        except Exception:
            pass

    def _refresh_list(self):
        q      = self._search_var.get().strip()
        filt   = self._filter_var.get()
        rows   = cs.list_contacts(search=q, limit=500)

        if filt == "auto":
            rows = [r for r in rows if r.get("source") == "auto"]
        elif filt != "all":
            rows = [r for r in rows if filt in r.get("tags", [])]

        self._all_rows = rows
        self._listbox.delete(0, "end")

        for r in rows:
            name = r.get("name", "?")
            rel  = r.get("relationship", "")
            tags = r.get("tags", [])
            src  = "🤖" if r.get("source") == "auto" else "👤"
            tag_str = (" [" + ", ".join(tags) + "]") if tags else ""
            rel_str = (" · " + rel) if rel else ""
            self._listbox.insert("end", f"{src}  {name}{rel_str}{tag_str}")

    # ------------------------------------------------------------------
    # SELECTION
    # ------------------------------------------------------------------

    def _on_select(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._all_rows):
            return

        r = self._all_rows[idx]
        self._selected_id = int(r["id"])
        self._populate_form(r)

    def _populate_form(self, r: dict):
        self._fields["name"].set(r.get("name", ""))
        self._fields["nickname"].set(r.get("nickname", ""))
        self._fields["relationship"].set(r.get("relationship", ""))
        self._fields["phone"].set(r.get("phone", ""))
        self._fields["email"].set(r.get("email", ""))
        self._tags_var.set(", ".join(r.get("tags", [])))

        self._notes_txt.delete("1.0", "end")
        self._notes_txt.insert("1.0", r.get("notes", ""))

        src     = "Auto-detected" if r.get("source") == "auto" else "Added manually"
        added   = _ts(r.get("created_ts", 0))
        updated = _ts(r.get("updated_ts", 0))
        self._meta_lbl.config(
            text=f"{src}  ·  Added: {added}  ·  Updated: {updated}"
        )

    # ------------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------------

    def _new_contact(self):
        self._selected_id = None
        self._clear_form()
        self._fields["name"].set("")
        self._toast("Fill in the form and press SAVE.")

    def _clear_form(self):
        for var in self._fields.values():
            var.set("")
        self._tags_var.set("")
        self._notes_txt.delete("1.0", "end")
        self._meta_lbl.config(text="")
        self._selected_id = None

    def _save_contact(self):
        name = self._fields["name"].get().strip()
        if not name:
            messagebox.showwarning("Missing Name", "Name is required.")
            return

        nickname     = self._fields["nickname"].get().strip()
        relationship = self._fields["relationship"].get().strip()
        phone        = self._fields["phone"].get().strip()
        email        = self._fields["email"].get().strip()
        notes        = self._notes_txt.get("1.0", "end-1c").strip()
        tags_raw     = self._tags_var.get().strip()
        tags         = [t.strip().lower() for t in tags_raw.split(",") if t.strip()]

        if self._selected_id is not None:
            # Update existing
            cs.update_contact(
                self._selected_id,
                name=name, nickname=nickname, relationship=relationship,
                phone=phone, email=email, notes=notes,
            )
            # Sync tags
            conn = cs._connect()
            try:
                with conn:
                    conn.execute(
                        "DELETE FROM contact_tags WHERE contact_id=?;",
                        (self._selected_id,)
                    )
                    for tag in tags:
                        conn.execute(
                            "INSERT OR IGNORE INTO contact_tags(contact_id,tag) VALUES(?,?);",
                            (self._selected_id, tag)
                        )
            finally:
                conn.close()
            self._toast("Contact updated.")
        else:
            # New contact
            cs.add_contact(
                name=name, nickname=nickname, phone=phone, email=email,
                relationship=relationship, notes=notes, tags=tags,
                source="manual",
            )
            self._toast("Contact saved.")

        self.refresh()

    def _delete_contact(self):
        if self._selected_id is None:
            messagebox.showinfo("Nothing selected", "Select a contact first.")
            return
        name = self._fields["name"].get() or "this contact"
        ok = messagebox.askyesno("Delete", f"Delete {name}?")
        if not ok:
            return
        cs.delete_contact(self._selected_id)
        self._selected_id = None
        self._clear_form()
        self.refresh()
        self._toast("Deleted.")

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _toast(self, msg: str):
        self._status_lbl.config(text="● " + msg, fg=ACCENT)
        self.after(2500, lambda: self._status_lbl.config(text="", fg=ACCENT2))

    def _on_close(self):
        self.destroy()


# ------------------------------------------------------------------
# OPENER
# ------------------------------------------------------------------

def open_contacts_panel(app):
    win = getattr(app, "contacts_win", None)
    if win is not None:
        try:
            if win.winfo_exists():
                win.lift()
                return win
        except Exception:
            pass
    win = ContactsPanel(app)
    app.contacts_win = win
    return win
