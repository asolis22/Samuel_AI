# ui/google_panel.py
# Google Panel — Gmail, Calendar, Drive all in one place.
# Open with: Alpha.g.x0.1.G00gle
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from ui.theme import (
    BG, PANEL, CARD, BORDER,
    TEXT, MUTED, ACCENT, ACCENT2, ACCENT3,
)


class GooglePanel(tk.Toplevel):

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("GOOGLE")
        self.configure(bg=BG)
        self.geometry("1100x700")
        self.minsize(960, 560)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._auth_ok   = False
        self._user_email = ""

        self._build_ui()
        self._check_auth()

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=16, pady=(16, 6))

        tk.Label(hdr, text="GOOGLE", bg=BG, fg=TEXT,
                 font=("Menlo", 18, "bold")).pack(side="left")

        self._auth_lbl = tk.Label(hdr, text="● NOT CONNECTED",
                                   bg=BG, fg="#B85C5C",
                                   font=("Menlo", 11, "bold"))
        self._auth_lbl.pack(side="right")

        self._email_lbl = tk.Label(hdr, text="",
                                    bg=BG, fg=MUTED, font=("Menlo", 11))
        self._email_lbl.pack(side="right", padx=(0, 16))

        # Connect button (shown when not authed)
        self._connect_frame = tk.Frame(self, bg=BG)
        self._connect_frame.pack(fill="both", expand=True)
        self._build_connect_screen()

        # Main tabs (shown when authed)
        self._main_frame = tk.Frame(self, bg=BG)
        self._tabs = ttk.Notebook(self._main_frame)
        self._tabs.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._tab_gmail    = tk.Frame(self._tabs, bg=BG)
        self._tab_calendar = tk.Frame(self._tabs, bg=BG)
        self._tab_drive    = tk.Frame(self._tabs, bg=BG)
        self._tab_compose  = tk.Frame(self._tabs, bg=BG)

        self._tabs.add(self._tab_gmail,    text="  Gmail  ")
        self._tabs.add(self._tab_calendar, text="  Calendar  ")
        self._tabs.add(self._tab_drive,    text="  Drive  ")
        self._tabs.add(self._tab_compose,  text="  Compose  ")

        self._build_gmail_tab()
        self._build_calendar_tab()
        self._build_drive_tab()
        self._build_compose_tab()

        self._tabs.bind("<<NotebookTabChanged>>", lambda _: self._on_tab_change())

    def _build_connect_screen(self):
        f = self._connect_frame
        tk.Label(f, text="Connect Samuel to Google",
                 bg=BG, fg=TEXT, font=("Menlo", 16, "bold")
                 ).pack(pady=(80, 16))
        tk.Label(f,
                 text="Samuel needs your Google account to read Gmail,\n"
                      "Calendar, and Drive. Your data stays on your Mac.",
                 bg=BG, fg=MUTED, font=("Menlo", 12), justify="center"
                 ).pack(pady=(0, 32))
        tk.Button(f, text="  CONNECT GOOGLE ACCOUNT  ",
                  bg=ACCENT2, fg="#11100F",
                  relief="flat", font=("Menlo", 13, "bold"),
                  command=self._do_auth
                  ).pack()
        self._connect_status = tk.Label(f, text="",
                                         bg=BG, fg=MUTED, font=("Menlo", 11))
        self._connect_status.pack(pady=12)

    # ---- GMAIL TAB ----
    def _build_gmail_tab(self):
        p = self._tab_gmail
        top = tk.Frame(p, bg=BG)
        top.pack(fill="x", padx=12, pady=10)

        tk.Label(top, text="Show:", bg=BG, fg=MUTED,
                 font=("Menlo", 11)).pack(side="left")
        self._gmail_filter = tk.StringVar(value="unread")
        for label, val in [("Unread", "unread"), ("All Inbox", "inbox"),
                            ("Search", "search")]:
            tk.Radiobutton(top, text=label, variable=self._gmail_filter,
                           value=val, bg=BG, fg=MUTED, selectcolor=CARD,
                           activebackground=BG, activeforeground=ACCENT,
                           font=("Menlo", 11),
                           command=self._load_gmail).pack(side="left", padx=6)

        self._gmail_search_var = tk.StringVar()
        self._gmail_search_entry = tk.Entry(
            top, textvariable=self._gmail_search_var,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 11), width=24
        )
        self._gmail_search_entry.pack(side="left", padx=(8, 0))
        self._gmail_search_entry.bind("<Return>", lambda _: self._load_gmail())

        tk.Button(top, text="LOAD", bg=ACCENT, fg="#11100F",
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self._load_gmail).pack(side="left", padx=8)

        body = tk.Frame(p, bg=BG)
        body.pack(fill="both", expand=True, padx=12)

        # Email list
        left = tk.Frame(body, bg=PANEL,
                        highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        lw = tk.Frame(left, bg=PANEL)
        lw.pack(fill="both", expand=True, padx=8, pady=8)
        self._gmail_lb = tk.Listbox(lw, bg=PANEL, fg=TEXT,
                                     selectbackground=ACCENT,
                                     selectforeground="#11100F",
                                     relief="flat", highlightthickness=0,
                                     font=("Menlo", 11), activestyle="none")
        self._gmail_lb.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(lw, orient="vertical", command=self._gmail_lb.yview)
        sb.pack(side="right", fill="y")
        self._gmail_lb.configure(yscrollcommand=sb.set)
        self._gmail_lb.bind("<<ListboxSelect>>", lambda _: self._show_email())

        # Email detail
        right = tk.Frame(body, bg=PANEL,
                          highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)
        ri = tk.Frame(right, bg=PANEL)
        ri.pack(fill="both", expand=True, padx=12, pady=12)

        self._email_from_lbl = tk.Label(ri, text="", bg=PANEL, fg=ACCENT2,
                                         font=("Menlo", 11, "bold"), anchor="w")
        self._email_from_lbl.pack(fill="x")
        self._email_subj_lbl = tk.Label(ri, text="", bg=PANEL, fg=TEXT,
                                         font=("Menlo", 12, "bold"), anchor="w",
                                         wraplength=400)
        self._email_subj_lbl.pack(fill="x", pady=(2, 8))

        etw = tk.Frame(ri, bg=PANEL)
        etw.pack(fill="both", expand=True)
        self._email_body_txt = tk.Text(etw, bg=CARD, fg=TEXT,
                                        insertbackground=ACCENT,
                                        relief="flat", font=("Menlo", 11),
                                        wrap="word", state="disabled")
        self._email_body_txt.pack(side="left", fill="both", expand=True)
        esb = ttk.Scrollbar(etw, orient="vertical",
                             command=self._email_body_txt.yview)
        esb.pack(side="right", fill="y")
        self._email_body_txt.configure(yscrollcommand=esb.set)

        self._emails_cache = []

    # ---- CALENDAR TAB ----
    def _build_calendar_tab(self):
        p = self._tab_calendar
        top = tk.Frame(p, bg=BG)
        top.pack(fill="x", padx=12, pady=10)

        for label, val in [("Today", "today"), ("7 days", "7"),
                            ("30 days", "30")]:
            tk.Button(top, text=label, bg=CARD, fg=TEXT,
                      relief="flat", font=("Menlo", 11),
                      command=lambda v=val: self._load_calendar(v)
                      ).pack(side="left", padx=(0, 8))

        # Add event button
        tk.Button(top, text="+ ADD EVENT", bg=ACCENT2, fg="#11100F",
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self._add_event_dialog).pack(side="right")

        body = tk.Frame(p, bg=BG)
        body.pack(fill="both", expand=True, padx=12)

        left = tk.Frame(body, bg=PANEL,
                        highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        lw = tk.Frame(left, bg=PANEL)
        lw.pack(fill="both", expand=True, padx=8, pady=8)
        self._cal_lb = tk.Listbox(lw, bg=PANEL, fg=TEXT,
                                   selectbackground=ACCENT,
                                   selectforeground="#11100F",
                                   relief="flat", highlightthickness=0,
                                   font=("Menlo", 12), activestyle="none")
        self._cal_lb.pack(side="left", fill="both", expand=True)
        csb = ttk.Scrollbar(lw, orient="vertical", command=self._cal_lb.yview)
        csb.pack(side="right", fill="y")
        self._cal_lb.configure(yscrollcommand=csb.set)
        self._cal_lb.bind("<<ListboxSelect>>", lambda _: self._show_event())

        right = tk.Frame(body, bg=PANEL,
                          highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)
        ri = tk.Frame(right, bg=PANEL)
        ri.pack(fill="both", expand=True, padx=12, pady=12)

        self._event_title_lbl = tk.Label(ri, text="",
                                          bg=PANEL, fg=ACCENT,
                                          font=("Menlo", 13, "bold"),
                                          wraplength=380, justify="left")
        self._event_title_lbl.pack(anchor="w")
        self._event_detail_lbl = tk.Label(ri, text="",
                                           bg=PANEL, fg=TEXT,
                                           font=("Menlo", 11),
                                           wraplength=380, justify="left")
        self._event_detail_lbl.pack(anchor="w", pady=(8, 0))

        self._events_cache = []

    # ---- DRIVE TAB ----
    def _build_drive_tab(self):
        p = self._tab_drive
        top = tk.Frame(p, bg=BG)
        top.pack(fill="x", padx=12, pady=10)

        tk.Label(top, text="Search Drive:", bg=BG, fg=MUTED,
                 font=("Menlo", 11)).pack(side="left")
        self._drive_search_var = tk.StringVar()
        tk.Entry(top, textvariable=self._drive_search_var,
                 bg=CARD, fg=TEXT, insertbackground=ACCENT,
                 relief="flat", font=("Menlo", 12), width=28
                 ).pack(side="left", padx=8)
        tk.Entry.bind(
            tk.Entry(top),  # dummy — real bind below
            "<Return>", lambda _: None
        )
        tk.Button(top, text="SEARCH", bg=ACCENT, fg="#11100F",
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self._load_drive).pack(side="left")
        tk.Button(top, text="RECENT", bg=CARD, fg=TEXT,
                  relief="flat", font=("Menlo", 11),
                  command=lambda: self._load_drive(recent=True)
                  ).pack(side="left", padx=8)

        body = tk.Frame(p, bg=BG)
        body.pack(fill="both", expand=True, padx=12)

        left = tk.Frame(body, bg=PANEL,
                        highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        lw = tk.Frame(left, bg=PANEL)
        lw.pack(fill="both", expand=True, padx=8, pady=8)
        self._drive_lb = tk.Listbox(lw, bg=PANEL, fg=TEXT,
                                     selectbackground=ACCENT,
                                     selectforeground="#11100F",
                                     relief="flat", highlightthickness=0,
                                     font=("Menlo", 11), activestyle="none")
        self._drive_lb.pack(side="left", fill="both", expand=True)
        dsb = ttk.Scrollbar(lw, orient="vertical",
                             command=self._drive_lb.yview)
        dsb.pack(side="right", fill="y")
        self._drive_lb.configure(yscrollcommand=dsb.set)
        self._drive_lb.bind("<<ListboxSelect>>", lambda _: self._show_drive_file())

        right = tk.Frame(body, bg=PANEL,
                          highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)
        ri = tk.Frame(right, bg=PANEL)
        ri.pack(fill="both", expand=True, padx=12, pady=12)

        self._drive_name_lbl = tk.Label(ri, text="",
                                         bg=PANEL, fg=ACCENT,
                                         font=("Menlo", 12, "bold"),
                                         wraplength=380)
        self._drive_name_lbl.pack(anchor="w")

        dtw = tk.Frame(ri, bg=PANEL)
        dtw.pack(fill="both", expand=True, pady=(8, 0))
        self._drive_txt = tk.Text(dtw, bg=CARD, fg=TEXT,
                                   insertbackground=ACCENT,
                                   relief="flat", font=("Menlo", 11),
                                   wrap="word", state="disabled")
        self._drive_txt.pack(side="left", fill="both", expand=True)
        dtsb = ttk.Scrollbar(dtw, orient="vertical",
                              command=self._drive_txt.yview)
        dtsb.pack(side="right", fill="y")
        self._drive_txt.configure(yscrollcommand=dtsb.set)

        self._drive_files_cache = []

    # ---- COMPOSE TAB ----
    def _build_compose_tab(self):
        p  = self._tab_compose
        ri = tk.Frame(p, bg=PANEL,
                       highlightbackground=BORDER, highlightthickness=1)
        ri.pack(fill="both", expand=True, padx=12, pady=12)
        inner = tk.Frame(ri, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=16, pady=16)

        tk.Label(inner, text="COMPOSE EMAIL",
                 bg=PANEL, fg=TEXT, font=("Menlo", 14, "bold")
                 ).pack(anchor="w", pady=(0, 12))

        for label, key in [("To", "to"), ("Subject", "subject")]:
            row = tk.Frame(inner, bg=PANEL)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label, bg=PANEL, fg=MUTED,
                     font=("Menlo", 11, "bold"), width=10,
                     anchor="w").pack(side="left")
            var = tk.StringVar()
            tk.Entry(row, textvariable=var, bg=CARD, fg=TEXT,
                     insertbackground=ACCENT, relief="flat",
                     font=("Menlo", 12)).pack(side="left", fill="x", expand=True)
            setattr(self, f"_compose_{key}_var", var)

        tk.Label(inner, text="Body", bg=PANEL, fg=MUTED,
                 font=("Menlo", 11, "bold")).pack(anchor="w", pady=(12, 4))
        self._compose_body_txt = tk.Text(
            inner, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12), height=12, wrap="word"
        )
        self._compose_body_txt.pack(fill="both", expand=True)

        bb = tk.Frame(inner, bg=PANEL)
        bb.pack(fill="x", pady=(12, 0))

        tk.Button(bb, text="SEND", bg=ACCENT, fg="#11100F",
                  relief="flat", font=("Menlo", 12, "bold"),
                  command=self._send_email).pack(side="left", padx=(0, 10))
        tk.Button(bb, text="SAVE DRAFT", bg=ACCENT2, fg="#11100F",
                  relief="flat", font=("Menlo", 11, "bold"),
                  command=self._save_draft).pack(side="left", padx=(0, 10))
        tk.Button(bb, text="CLEAR", bg=CARD, fg=TEXT,
                  relief="flat", font=("Menlo", 11),
                  command=self._clear_compose).pack(side="left")

        self._compose_status = tk.Label(inner, text="",
                                         bg=PANEL, fg=ACCENT2,
                                         font=("Menlo", 11, "bold"))
        self._compose_status.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # AUTH
    # ------------------------------------------------------------------

    def _check_auth(self):
        def _check():
            try:
                from google_auth import is_authenticated, get_user_email
                if is_authenticated():
                    self._auth_ok    = True
                    self._user_email = get_user_email()
                    self.after(0, self._show_main)
                else:
                    self.after(0, self._show_connect)
            except Exception:
                self.after(0, self._show_connect)
        threading.Thread(target=_check, daemon=True).start()

    def _do_auth(self):
        self._connect_status.config(
            text="Opening browser for Google sign-in...", fg=ACCENT2
        )
        def _auth():
            try:
                from google_auth import get_credentials, get_user_email
                get_credentials()
                self._auth_ok    = True
                self._user_email = get_user_email()
                self.after(0, self._show_main)
            except Exception as e:
                self.after(0, lambda: self._connect_status.config(
                    text="Error: " + str(e)[:80], fg="#B85C5C"
                ))
        threading.Thread(target=_auth, daemon=True).start()

    def _show_connect(self):
        self._connect_frame.pack(fill="both", expand=True)
        self._main_frame.pack_forget()

    def _show_main(self):
        self._connect_frame.pack_forget()
        self._main_frame.pack(fill="both", expand=True)
        self._auth_lbl.config(text="● CONNECTED", fg="#9AD39C")
        self._email_lbl.config(text=self._user_email)
        self._load_gmail()
        self._load_calendar("today")

    # ------------------------------------------------------------------
    # GMAIL ACTIONS
    # ------------------------------------------------------------------

    def _load_gmail(self):
        filt = self._gmail_filter.get()
        self._gmail_lb.delete(0, "end")
        self._gmail_lb.insert("end", "Loading...")

        def _fetch():
            try:
                from google_gmail import get_unread, get_inbox, search_emails
                if filt == "unread":
                    emails = get_unread(max_results=20)
                elif filt == "search":
                    q = self._gmail_search_var.get().strip()
                    emails = search_emails(q) if q else get_inbox(max_results=20)
                else:
                    emails = get_inbox(max_results=20)
                self.after(0, lambda: self._populate_gmail(emails))
            except Exception as e:
                self.after(0, lambda: self._gmail_lb.delete(0, "end") or
                           self._gmail_lb.insert("end", "Error: " + str(e)[:60]))

        threading.Thread(target=_fetch, daemon=True).start()

    def _populate_gmail(self, emails):
        self._emails_cache = emails
        self._gmail_lb.delete(0, "end")
        if not emails:
            self._gmail_lb.insert("end", "No emails found.")
            return
        for e in emails:
            unread = "● " if e.get("unread") else "  "
            sender = e.get("from", "")[:28]
            subj   = e.get("subject", "")[:42]
            self._gmail_lb.insert("end", f"{unread}{sender}  —  {subj}")

    def _show_email(self):
        sel = self._gmail_lb.curselection()
        if not sel or not self._emails_cache:
            return
        idx = int(sel[0])
        if idx >= len(self._emails_cache):
            return
        e = self._emails_cache[idx]
        self._email_from_lbl.config(
            text=f"From: {e.get('from','')}   {e.get('date','')[:16]}"
        )
        self._email_subj_lbl.config(text=e.get("subject", ""))
        body = e.get("body") or e.get("snippet", "")
        self._email_body_txt.config(state="normal")
        self._email_body_txt.delete("1.0", "end")
        self._email_body_txt.insert("1.0", body)
        self._email_body_txt.config(state="disabled")

    # ------------------------------------------------------------------
    # CALENDAR ACTIONS
    # ------------------------------------------------------------------

    def _load_calendar(self, mode: str = "7"):
        self._cal_lb.delete(0, "end")
        self._cal_lb.insert("end", "Loading...")

        def _fetch():
            try:
                from google_calendar import get_todays_events, get_upcoming_events
                if mode == "today":
                    events = get_todays_events()
                else:
                    events = get_upcoming_events(days=int(mode), max_results=30)
                self.after(0, lambda: self._populate_calendar(events))
            except Exception as e:
                self.after(0, lambda: self._cal_lb.delete(0, "end") or
                           self._cal_lb.insert("end", "Error: " + str(e)[:60]))

        threading.Thread(target=_fetch, daemon=True).start()

    def _populate_calendar(self, events):
        self._events_cache = events
        self._cal_lb.delete(0, "end")
        if not events:
            self._cal_lb.insert("end", "No events found.")
            return
        for e in events:
            start = e.get("start", "")[:16].replace("T", "  ")
            title = e.get("title", "")[:50]
            self._cal_lb.insert("end", f"{start}  |  {title}")

    def _show_event(self):
        sel = self._cal_lb.curselection()
        if not sel or not self._events_cache:
            return
        idx = int(sel[0])
        if idx >= len(self._events_cache):
            return
        e = self._events_cache[idx]
        self._event_title_lbl.config(text=e.get("title", ""))
        detail = ""
        if e.get("start"):
            detail += f"Start: {e['start'][:19].replace('T',' ')}\n"
        if e.get("end"):
            detail += f"End:   {e['end'][:19].replace('T',' ')}\n"
        if e.get("location"):
            detail += f"📍 {e['location']}\n"
        if e.get("description"):
            detail += f"\n{e['description'][:300]}"
        self._event_detail_lbl.config(text=detail)

    def _add_event_dialog(self):
        win = tk.Toplevel(self)
        win.title("Add Event")
        win.configure(bg=BG)
        win.geometry("480x360")

        inner = tk.Frame(win, bg=BG)
        inner.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(inner, text="ADD CALENDAR EVENT",
                 bg=BG, fg=TEXT, font=("Menlo", 13, "bold")
                 ).pack(anchor="w", pady=(0, 12))

        fields = {}
        for label, key, default in [
            ("Title",       "title",    ""),
            ("Date",        "date",     datetime.now().strftime("%Y-%m-%d")),
            ("Start time",  "start",    "09:00"),
            ("End time",    "end",      "10:00"),
            ("Location",    "location", ""),
        ]:
            row = tk.Frame(inner, bg=BG)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=BG, fg=MUTED,
                     font=("Menlo", 11), width=12, anchor="w").pack(side="left")
            var = tk.StringVar(value=default)
            tk.Entry(row, textvariable=var, bg=CARD, fg=TEXT,
                     insertbackground=ACCENT, relief="flat",
                     font=("Menlo", 12)).pack(side="left", fill="x", expand=True)
            fields[key] = var

        status_lbl = tk.Label(inner, text="", bg=BG, fg=ACCENT2,
                               font=("Menlo", 11))
        status_lbl.pack(anchor="w", pady=(8, 0))

        def _save():
            try:
                from google_calendar import create_event
                date_str  = fields["date"].get().strip()
                start_str = fields["start"].get().strip()
                end_str   = fields["end"].get().strip()
                start_dt  = datetime.fromisoformat(f"{date_str}T{start_str}:00")
                end_dt    = datetime.fromisoformat(f"{date_str}T{end_str}:00")
                create_event(
                    title=fields["title"].get().strip(),
                    start_dt=start_dt, end_dt=end_dt,
                    location=fields["location"].get().strip(),
                )
                status_lbl.config(text="Event created!", fg="#9AD39C")
                self.after(1000, lambda: self._load_calendar("7"))
                self.after(1500, win.destroy)
            except Exception as e:
                status_lbl.config(text="Error: " + str(e)[:60], fg="#B85C5C")

        tk.Button(inner, text="SAVE EVENT", bg=ACCENT, fg="#11100F",
                  relief="flat", font=("Menlo", 12, "bold"),
                  command=_save).pack(anchor="w", pady=(12, 0))

    # ------------------------------------------------------------------
    # DRIVE ACTIONS
    # ------------------------------------------------------------------

    def _load_drive(self, recent: bool = False):
        self._drive_lb.delete(0, "end")
        self._drive_lb.insert("end", "Loading...")

        def _fetch():
            try:
                from google_drive import search_files, list_recent_files
                if recent:
                    files = list_recent_files(max_results=20)
                else:
                    q = self._drive_search_var.get().strip()
                    files = search_files(q) if q else list_recent_files(max_results=20)
                self.after(0, lambda: self._populate_drive(files))
            except Exception as e:
                self.after(0, lambda: self._drive_lb.delete(0, "end") or
                           self._drive_lb.insert("end", "Error: " + str(e)[:60]))

        threading.Thread(target=_fetch, daemon=True).start()

    def _populate_drive(self, files):
        self._drive_files_cache = files
        self._drive_lb.delete(0, "end")
        if not files:
            self._drive_lb.insert("end", "No files found.")
            return
        for f in files:
            icon = "📄" if f.get("is_google_doc") else "📁"
            name = f.get("name", "")[:55]
            date = f.get("modified", "")[:10]
            self._drive_lb.insert("end", f"{icon}  {name}  [{date}]")

    def _show_drive_file(self):
        sel = self._drive_lb.curselection()
        if not sel or not self._drive_files_cache:
            return
        idx = int(sel[0])
        if idx >= len(self._drive_files_cache):
            return
        f = self._drive_files_cache[idx]
        self._drive_name_lbl.config(text=f.get("name", ""))
        self._drive_txt.config(state="normal")
        self._drive_txt.delete("1.0", "end")
        self._drive_txt.insert("1.0", "Loading content...")
        self._drive_txt.config(state="disabled")

        def _read():
            try:
                from google_drive import read_file_text
                content = read_file_text(f["id"])
                self.after(0, lambda: self._set_drive_text(content))
            except Exception as e:
                self.after(0, lambda: self._set_drive_text("Cannot read: " + str(e)))

        threading.Thread(target=_read, daemon=True).start()

    def _set_drive_text(self, text: str):
        self._drive_txt.config(state="normal")
        self._drive_txt.delete("1.0", "end")
        self._drive_txt.insert("1.0", text)
        self._drive_txt.config(state="disabled")

    # ------------------------------------------------------------------
    # COMPOSE ACTIONS
    # ------------------------------------------------------------------

    def _send_email(self):
        to      = self._compose_to_var.get().strip()
        subject = self._compose_subject_var.get().strip()
        body    = self._compose_body_txt.get("1.0", "end-1c").strip()
        if not to or not subject or not body:
            self._compose_status.config(text="Fill in To, Subject, and Body.",
                                         fg="#B85C5C")
            return
        ok = messagebox.askyesno("Send Email",
                                  f"Send to {to}?\n\nSubject: {subject}")
        if not ok:
            return

        def _send():
            try:
                from google_gmail import send_email
                send_email(to, subject, body)
                self.after(0, lambda: self._compose_status.config(
                    text="Sent!", fg="#9AD39C"))
                self.after(0, self._clear_compose)
            except Exception as e:
                self.after(0, lambda: self._compose_status.config(
                    text="Error: " + str(e)[:60], fg="#B85C5C"))

        threading.Thread(target=_send, daemon=True).start()

    def _save_draft(self):
        to      = self._compose_to_var.get().strip()
        subject = self._compose_subject_var.get().strip()
        body    = self._compose_body_txt.get("1.0", "end-1c").strip()

        def _draft():
            try:
                from google_gmail import create_draft
                create_draft(to, subject, body)
                self.after(0, lambda: self._compose_status.config(
                    text="Draft saved.", fg=ACCENT2))
            except Exception as e:
                self.after(0, lambda: self._compose_status.config(
                    text="Error: " + str(e)[:60], fg="#B85C5C"))

        threading.Thread(target=_draft, daemon=True).start()

    def _clear_compose(self):
        self._compose_to_var.set("")
        self._compose_subject_var.set("")
        self._compose_body_txt.delete("1.0", "end")

    def _on_tab_change(self):
        pass

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _on_close(self):
        self.destroy()


# ------------------------------------------------------------------
# OPENER
# ------------------------------------------------------------------

def open_google_panel(app):
    win = getattr(app, "google_win", None)
    if win is not None:
        try:
            if win.winfo_exists():
                win.lift()
                return win
        except Exception:
            pass
    win = GooglePanel(app)
    app.google_win = win
    return win
