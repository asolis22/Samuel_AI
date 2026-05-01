# ui/expression_trainer.py
# Three-tab panel:
#   EDITOR   — sliders to design robot eye expressions live
#   LIBRARY  — browse all expressions, preview, edit, delete custom ones
#   TRAINING — write a sentence, Samuel guesses, you correct, he learns

import math
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Optional

from ui.theme import BG, PANEL, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2, ACCENT3
from expression_store import (
    init_expression_db, save_expression, get_expression,
    list_expressions, delete_expression,
    save_training_sample, predict_from_training,
    get_training_stats,
)
from samuel_eyes import EXPRESSIONS, SamuelEyes, EMOTION_MAP


# -------------------------------------------------------
# SEED BUILTINS INTO DB ON FIRST RUN
# -------------------------------------------------------

def _seed_builtins():
    existing = {e["name"] for e in list_expressions()}
    for name, params in EXPRESSIONS.items():
        if name not in existing:
            desc = _builtin_descriptions.get(name, "")
            keys = _builtin_keywords.get(name, "")
            save_expression(name, params, desc, keys, builtin=True)

_builtin_descriptions = {
    "neutral":   "Default resting state. Calm, attentive.",
    "happy":     "Curved upward, glowing green. Warm and pleased.",
    "curious":   "One eye slightly squinted, pupils up. Interested.",
    "concerned":  "Inner slant raised. Gentle worry.",
    "amused":    "Soft squint from below. Finding something funny.",
    "confident": "Heavy top lid, rect shape. Self-assured.",
    "shy":       "Half closed, pupils down-left. Bashful.",
    "hmph":      "Heavy lids, strong inner slant. Unimpressed.",
    "surprised": "Wide open, huge pupils, bright glow. Startled.",
    "evil":      "Heavy top slant inward, rect shape. Mischievous.",
}
_builtin_keywords = {
    "happy":     "happy glad pleased love amazing great yay wonderful",
    "curious":   "how why what wonder curious interesting explain question",
    "concerned":  "worried scared nervous anxious help stressed overwhelmed",
    "amused":    "haha funny lol joke hilarious amusing entertaining",
    "confident": "sure certain definitely absolutely confident know",
    "shy":       "embarrassed blush shy awkward sorry oops",
    "hmph":      "whatever boring unimpressed ugh fine okay sure",
    "surprised": "wow whoa really omg no way shocked surprised",
    "evil":      "mischievous sneaky plan scheme trick clever devious",
}


# -------------------------------------------------------
# ROBOT EYE PREVIEW  (static, matches samuel_eyes.py style)
# -------------------------------------------------------

def _rounded_rect_preview(canvas, x1, y1, x2, y2, r, **kwargs):
    r = min(r, max(1,(x2-x1)//2), max(1,(y2-y1)//2))
    pts = [
        x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
        x2,y2-r, x2,y2, x2-r,y2, x1+r,y2,
        x1,y2, x1,y2-r, x1,y1+r, x1,y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kwargs)


def draw_eye_preview(canvas: tk.Canvas, params: Dict, bg: str = "#0A0A0A"):
    canvas.delete("all")
    canvas.update_idletasks()
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    if w < 20: w = 300
    if h < 20: h = 120

    color = params.get("color", params.get("glow", "#4DCFCF"))
    shape = params.get("shape", "oval")

    eye_w = int(min(w * 0.32, h * 0.68))
    eye_h = int(eye_w * 0.58)
    gap   = int(eye_w * 0.26)
    cy    = h // 2
    lx    = w // 2 - gap // 2 - eye_w // 2
    rx    = w // 2 + gap // 2 + eye_w // 2

    for side in ("left", "right"):
        cx      = lx if side == "left" else rx
        open_   = params.get("open_l" if side=="left" else "open_r", 1.0)
        cut_top = params.get("cut_top_l" if side=="left" else "cut_top_r", 0.0)
        cut_bot = params.get("cut_bot_l" if side=="left" else "cut_bot_r", 0.0)
        slant   = params.get("slant_l" if side=="left" else "slant_r", 0.0)
        oy      = params.get("offset_y_l" if side=="left" else "offset_y_r", 0.0)

        ah  = max(3, int(eye_h * open_))
        acy = cy + int(eye_h * oy * 0.4)

        x1, x2 = cx - eye_w//2, cx + eye_w//2
        y1, y2 = acy - ah//2, acy + ah//2
        rad = min(ah//2, eye_w//5)

        # solid fill
        if shape == "rect":
            _rounded_rect_preview(canvas, x1, y1, x2, y2, rad, fill=color, outline="")
        else:
            canvas.create_oval(x1, y1, x2, y2, fill=color, outline="")

        # slant cut
        if abs(slant) > 0.02:
            sh = int(ah * 0.6 * abs(slant))
            if side == "left":
                yi = y1 + (sh if slant > 0 else -sh)
            else:
                yi = y1 + (-sh if slant < 0 else sh)
            canvas.create_polygon(x1-1, y1-1, (x1+x2)//2, yi, x2+1, y1-1,
                                   fill="#0A0A0A", outline="")

        # top cut
        if cut_top > 0.01:
            ch = int(ah * cut_top)
            canvas.create_rectangle(x1-1, y1-1, x2+1, y1+ch, fill="#0A0A0A", outline="")

        # bottom cut
        if cut_bot > 0.01:
            ch = int(ah * cut_bot)
            canvas.create_rectangle(x1-1, y2-ch, x2+1, y2+1, fill="#0A0A0A", outline="")




# -------------------------------------------------------
# SLIDER ROW HELPER
# -------------------------------------------------------

def _slider_row(parent, label, from_, to, resolution, var, bg, update_fn):
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=2)
    tk.Label(row, text=label, bg=bg, fg=MUTED,
             font=("Menlo", 9), width=14, anchor="w").pack(side="left")
    tk.Scale(row, from_=from_, to=to, resolution=resolution,
             orient="horizontal", variable=var,
             bg=bg, fg=TEXT, troughcolor=CARD,
             highlightthickness=0, showvalue=True,
             font=("Menlo", 8), length=160,
             command=lambda _: update_fn()).pack(side="left")


# -------------------------------------------------------
# MAIN PANEL
# -------------------------------------------------------

class ExpressionTrainerPanel(tk.Toplevel):

    def __init__(self, gui):
        super().__init__(gui.root)
        self.gui = gui
        self.title("Samuel — Expression Studio")
        self.configure(bg=BG)
        self.geometry("1020x740")
        self.minsize(900, 640)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        init_expression_db()
        _seed_builtins()

        # Slider vars — matching samuel_eyes.py parameter names
        self._pv = {}
        defaults = {
            "open_l": 1.0,      "open_r": 1.0,
            "cut_top_l": 0.0,   "cut_top_r": 0.0,
            "cut_bot_l": 0.0,   "cut_bot_r": 0.0,
            "slant_l": 0.0,     "slant_r": 0.0,
            "offset_y_l": 0.0,  "offset_y_r": 0.0,
            "blink_speed": 4.5,
        }
        for k, v in defaults.items():
            self._pv[k] = tk.DoubleVar(value=v)

        self._glow_var  = tk.StringVar(value="#4DCFCF")
        self._shape_var = tk.StringVar(value="oval")
        self._name_var  = tk.StringVar(value="")
        self._desc_var  = tk.StringVar(value="")
        self._keys_var  = tk.StringVar(value="")

        self._train_predicted = None
        self._train_text      = ""

        self._build()
        self._refresh_library()

    # ------------------------------------------------------------------
    # BUILD
    # ------------------------------------------------------------------

    def _build(self):
        hdr = tk.Frame(self, bg=BG)
        hdr.pack(fill="x", padx=18, pady=(14,6))
        tk.Label(hdr, text="EXPRESSION STUDIO",
                 bg=BG, fg=TEXT, font=("Menlo",15,"bold")).pack(side="left")

        tab_bar = tk.Frame(self, bg=PANEL,
                            highlightbackground=BORDER, highlightthickness=1)
        tab_bar.pack(fill="x", padx=18, pady=(0,10))

        self._tab_btns   = {}
        self._tab_frames = {}
        for name in ("EDITOR","LIBRARY","TRAINING"):
            btn = tk.Button(tab_bar, text=name,
                            bg=CARD, fg=MUTED, relief="flat",
                            font=("Menlo",11,"bold"), padx=18, pady=6,
                            command=lambda n=name: self._switch_tab(n))
            btn.pack(side="left")
            self._tab_btns[name] = btn

        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True, padx=18, pady=(0,14))

        self._build_editor()
        self._build_library()
        self._build_training()
        self._switch_tab("EDITOR")

    def _switch_tab(self, name):
        for n, f in self._tab_frames.items():
            f.pack_forget()
        for n, b in self._tab_btns.items():
            b.config(bg=ACCENT if n==name else CARD,
                     fg="#11100F" if n==name else MUTED)
        self._tab_frames[name].pack(fill="both", expand=True)
        if name == "LIBRARY":  self._refresh_library()
        if name == "TRAINING": self._refresh_training_stats()

    # ------------------------------------------------------------------
    # EDITOR TAB
    # ------------------------------------------------------------------

    def _build_editor(self):
        f = tk.Frame(self._content, bg=BG)
        self._tab_frames["EDITOR"] = f

        # Left: sliders
        left = tk.Frame(f, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1, width=320)
        left.pack(side="left", fill="y", padx=(0,10))
        left.pack_propagate(False)

        inner = tk.Frame(left, bg=PANEL)
        inner.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(inner, text="EYE PARAMETERS",
                 bg=PANEL, fg=TEXT, font=("Menlo",11,"bold")).pack(anchor="w")
        tk.Frame(inner, bg=BORDER, height=1).pack(fill="x", pady=6)

        sliders = [
            ("Open L",       "open_l",     0.0, 1.0,  0.01),
            ("Open R",       "open_r",     0.0, 1.0,  0.01),
            ("Cut top L",    "cut_top_l",  0.0, 1.0,  0.01),
            ("Cut top R",    "cut_top_r",  0.0, 1.0,  0.01),
            ("Cut bottom L", "cut_bot_l",  0.0, 1.0,  0.01),
            ("Cut bottom R", "cut_bot_r",  0.0, 1.0,  0.01),
            ("Slant L",      "slant_l",   -0.6, 0.6,  0.01),
            ("Slant R",      "slant_r",   -0.6, 0.6,  0.01),
            ("Offset Y L",   "offset_y_l",-1.0, 1.0,  0.01),
            ("Offset Y R",   "offset_y_r",-1.0, 1.0,  0.01),
            ("Blink speed",  "blink_speed",1.0, 10.0, 0.1),
        ]
        for label, key, lo, hi, res in sliders:
            _slider_row(inner, label, lo, hi, res,
                        self._pv[key], PANEL, self._update_preview)

        # Shape toggle
        sr = tk.Frame(inner, bg=PANEL)
        sr.pack(fill="x", pady=(6,2))
        tk.Label(sr, text="Eye shape", bg=PANEL, fg=MUTED,
                 font=("Menlo",9), width=14, anchor="w").pack(side="left")
        for s in ("oval","rect"):
            tk.Radiobutton(sr, text=s, variable=self._shape_var, value=s,
                           bg=PANEL, fg=TEXT, selectcolor=CARD,
                           activebackground=PANEL, font=("Menlo",10),
                           command=self._update_preview).pack(side="left", padx=4)

        # Glow color row
        crow = tk.Frame(inner, bg=PANEL)
        crow.pack(fill="x", pady=(4,0))
        tk.Label(crow, text="Glow color", bg=PANEL, fg=MUTED,
                 font=("Menlo",9), width=14, anchor="w").pack(side="left")
        ge = tk.Entry(crow, textvariable=self._glow_var,
                      bg=CARD, fg=TEXT, relief="flat",
                      font=("Menlo",10), width=10, insertbackground=ACCENT)
        ge.pack(side="left", padx=(0,6))
        ge.bind("<Return>", lambda _: self._update_preview())

        crow2 = tk.Frame(inner, bg=PANEL)
        crow2.pack(fill="x", pady=2)
        glow_presets = [
            "#4DCFCF","#80FFFF","#7FFFB0","#A0C8FF",
            "#FFD080","#FFB0C8","#FF4060","#C8A0FF","#A0A0A0",
        ]
        for col in glow_presets:
            tk.Button(crow2, bg=col, width=2, height=1, relief="flat",
                      cursor="hand2",
                      command=lambda c=col: self._set_glow(c)).pack(side="left", padx=1)

        # Right: preview + save
        right = tk.Frame(f, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        prev_frame = tk.Frame(right, bg=PANEL,
                               highlightbackground=BORDER, highlightthickness=1)
        prev_frame.pack(fill="both", expand=True, pady=(0,10))

        self._preview = tk.Canvas(prev_frame, bg="#0A0A0A", highlightthickness=0)
        self._preview.pack(fill="both", expand=True, padx=16, pady=16)
        self._preview.bind("<Configure>", lambda _: self._update_preview())

        # Load row
        load_row = tk.Frame(right, bg=BG)
        load_row.pack(fill="x", pady=(0,6))
        tk.Label(load_row, text="Load:", bg=BG, fg=MUTED,
                 font=("Menlo",10)).pack(side="left", padx=(0,6))
        self._load_var  = tk.StringVar(value="neutral")
        self._load_menu = tk.OptionMenu(load_row, self._load_var, "neutral")
        self._load_menu.config(bg=CARD, fg=TEXT, relief="flat",
                                font=("Menlo",10), activebackground=PANEL)
        self._load_menu.pack(side="left")
        tk.Button(load_row, text="LOAD", bg=CARD, fg=TEXT, relief="flat",
                  font=("Menlo",10,"bold"),
                  command=self._load_expression).pack(side="left", padx=6)
        tk.Button(load_row, text="RESET", bg=CARD, fg=MUTED, relief="flat",
                  font=("Menlo",10),
                  command=self._reset_params).pack(side="left")

        # Save fields
        sf_frame = tk.Frame(right, bg=PANEL,
                             highlightbackground=BORDER, highlightthickness=1)
        sf_frame.pack(fill="x")
        sf = tk.Frame(sf_frame, bg=PANEL)
        sf.pack(fill="x", padx=12, pady=10)

        for i, (lbl, var) in enumerate([
            ("Name",        self._name_var),
            ("Description", self._desc_var),
            ("Keywords",    self._keys_var),
        ]):
            tk.Label(sf, text=lbl, bg=PANEL, fg=MUTED,
                     font=("Menlo",9)).grid(row=i, column=0, sticky="w", pady=2)
            tk.Entry(sf, textvariable=var, bg=CARD, fg=TEXT, relief="flat",
                     font=("Menlo",10), insertbackground=ACCENT,
                     width=24).grid(row=i, column=1, sticky="ew", padx=6)
        sf.columnconfigure(1, weight=1)
        tk.Label(sf, text="(space-separated trigger words)",
                 bg=PANEL, fg=MUTED,
                 font=("Menlo",8)).grid(row=3, column=1, sticky="w", padx=6)

        btn_row = tk.Frame(sf_frame, bg=PANEL)
        btn_row.pack(fill="x", padx=12, pady=(0,10))
        tk.Button(btn_row, text="SAVE EXPRESSION",
                  bg=ACCENT, fg="#11100F", relief="flat",
                  font=("Menlo",11,"bold"),
                  command=self._save_expression).pack(side="left", padx=(0,8))
        tk.Button(btn_row, text="TEST IN VOICE PANEL",
                  bg=ACCENT2, fg="#11100F", relief="flat",
                  font=("Menlo",10,"bold"),
                  command=self._test_expression).pack(side="left")

        self._update_load_menu()

    def _get_current_params(self):
        p = {k: round(v.get(), 3) for k, v in self._pv.items()}
        p["color"] = self._glow_var.get()
        p["shape"] = self._shape_var.get()
        return p

    def _update_preview(self):
        try:
            draw_eye_preview(self._preview, self._get_current_params())
        except Exception:
            pass

    def _set_glow(self, color):
        self._glow_var.set(color)
        self._update_preview()

    def _reset_params(self):
        defaults = {
            "open_l":1.0,"open_r":1.0,
            "cut_top_l":0.0,"cut_top_r":0.0,
            "cut_bot_l":0.0,"cut_bot_r":0.0,
            "slant_l":0.0,"slant_r":0.0,
            "offset_y_l":0.0,"offset_y_r":0.0,
            "blink_speed":4.5,
        }
        for k, v in defaults.items():
            self._pv[k].set(v)
        self._glow_var.set("#4DCFCF")
        self._shape_var.set("oval")
        self._update_preview()

    def _load_expression(self):
        name = self._load_var.get()
        expr = get_expression(name)
        if not expr and name in EXPRESSIONS:
            expr = {"params": EXPRESSIONS[name],
                    "description": _builtin_descriptions.get(name,""),
                    "keywords": _builtin_keywords.get(name,"")}
        if not expr:
            return
        p = expr["params"]
        for k in self._pv:
            if k in p:
                self._pv[k].set(p[k])
        self._glow_var.set(p.get("color", p.get("glow","#4DCFCF")))
        self._shape_var.set(p.get("shape","oval"))
        self._name_var.set(name)
        self._desc_var.set(expr.get("description",""))
        self._keys_var.set(expr.get("keywords",""))
        self._update_preview()

    def _save_expression(self):
        name = self._name_var.get().strip().lower()
        if not name:
            messagebox.showwarning("Name required",
                                   "Please give this expression a name.",
                                   parent=self)
            return
        params = self._get_current_params()
        save_expression(name, params, self._desc_var.get(), self._keys_var.get())
        from samuel_eyes import EXPRESSIONS as EXP
        EXP[name] = params
        messagebox.showinfo("Saved", f"Expression '{name}' saved!", parent=self)
        self._update_load_menu()
        self._refresh_library()

    def _test_expression(self):
        params = self._get_current_params()
        vw = getattr(self.gui, "voice_win", None)
        if not vw:
            messagebox.showinfo("Voice panel not open",
                                "Open the voice panel first.",
                                parent=self)
            return
        try:
            name = self._name_var.get().strip() or "_preview"
            from samuel_eyes import EXPRESSIONS as EXP
            EXP[name] = params
            ew = getattr(vw, "eyes_win", None)
            if ew and ew.winfo_exists():
                self.gui.root.after(
                    0, lambda: ew.samuel_eyes.set_expression(name)
                )
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _update_load_menu(self):
        names = [e["name"] for e in list_expressions()]
        menu  = self._load_menu["menu"]
        menu.delete(0,"end")
        for n in names:
            menu.add_command(label=n, command=lambda v=n: self._load_var.set(v))
        if names:
            self._load_var.set(names[0])

    # ------------------------------------------------------------------
    # LIBRARY TAB
    # ------------------------------------------------------------------

    def _build_library(self):
        f = tk.Frame(self._content, bg=BG)
        self._tab_frames["LIBRARY"] = f

        left = tk.Frame(f, bg=PANEL, highlightbackground=BORDER,
                         highlightthickness=1, width=220)
        left.pack(side="left", fill="y", padx=(0,10))
        left.pack_propagate(False)

        tk.Label(left, text="EXPRESSIONS", bg=PANEL, fg=TEXT,
                 font=("Menlo",11,"bold"), padx=12, pady=8).pack(anchor="w")

        self._lib_listbox = tk.Listbox(
            left, bg=CARD, fg=TEXT, relief="flat",
            font=("Menlo",11), selectbackground=ACCENT,
            selectforeground="#11100F", activestyle="none",
            borderwidth=0, highlightthickness=0
        )
        self._lib_listbox.pack(fill="both", expand=True, padx=8, pady=(0,8))
        self._lib_listbox.bind("<<ListboxSelect>>", self._on_lib_select)

        right = tk.Frame(f, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        prev = tk.Frame(right, bg=PANEL,
                         highlightbackground=BORDER, highlightthickness=1)
        prev.pack(fill="both", expand=True, pady=(0,10))
        self._lib_preview = tk.Canvas(prev, bg="#0A0A0A", highlightthickness=0)
        self._lib_preview.pack(fill="both", expand=True, padx=16, pady=16)
        self._lib_preview.bind("<Configure>", lambda _: self._refresh_lib_preview())

        det = tk.Frame(right, bg=PANEL,
                        highlightbackground=BORDER, highlightthickness=1)
        det.pack(fill="x")
        di = tk.Frame(det, bg=PANEL)
        di.pack(fill="x", padx=12, pady=10)

        self._lib_name_lbl = tk.Label(di, text="",
                                       bg=PANEL, fg=TEXT,
                                       font=("Menlo",13,"bold"))
        self._lib_name_lbl.pack(anchor="w")
        self._lib_desc_lbl = tk.Label(di, text="",
                                       bg=PANEL, fg=MUTED,
                                       font=("Menlo",10),
                                       wraplength=380, justify="left")
        self._lib_desc_lbl.pack(anchor="w", pady=(2,4))
        self._lib_keys_lbl = tk.Label(di, text="",
                                       bg=PANEL, fg=ACCENT2,
                                       font=("Menlo",9))
        self._lib_keys_lbl.pack(anchor="w")

        btn_row = tk.Frame(det, bg=PANEL)
        btn_row.pack(fill="x", padx=12, pady=(0,10))
        tk.Button(btn_row, text="EDIT IN EDITOR",
                  bg=ACCENT, fg="#11100F", relief="flat",
                  font=("Menlo",10,"bold"),
                  command=self._edit_in_editor).pack(side="left", padx=(0,8))
        self._del_btn = tk.Button(btn_row, text="DELETE",
                                   bg=CARD, fg="#B85C5C", relief="flat",
                                   font=("Menlo",10,"bold"),
                                   command=self._delete_selected)
        self._del_btn.pack(side="left")

        self._selected_expr = None

    def _refresh_library(self):
        self._lib_listbox.delete(0,"end")
        self._lib_data = list_expressions()
        for e in self._lib_data:
            tag = "•" if e["builtin"] else "+"
            self._lib_listbox.insert("end", f" {tag} {e['name']}")

    def _on_lib_select(self, _e=None):
        sel = self._lib_listbox.curselection()
        if not sel:
            return
        self._selected_expr = self._lib_data[sel[0]]
        e = self._selected_expr
        self._lib_name_lbl.config(
            text=e["name"].upper() + ("  [built-in]" if e["builtin"] else "  [custom]")
        )
        self._lib_desc_lbl.config(text=e["description"] or "(no description)")
        self._lib_keys_lbl.config(text="Keywords: " + (e["keywords"] or "none"))
        self._del_btn.config(state="disabled" if e["builtin"] else "normal")
        self._refresh_lib_preview()

    def _refresh_lib_preview(self):
        if not self._selected_expr:
            return
        draw_eye_preview(self._lib_preview, self._selected_expr["params"])

    def _edit_in_editor(self):
        if not self._selected_expr:
            return
        e = self._selected_expr
        p = e["params"]
        for k in self._pv:
            if k in p:
                self._pv[k].set(p[k])
        self._glow_var.set(p.get("color", p.get("glow","#4DCFCF")))
        self._shape_var.set(p.get("shape","oval"))
        self._name_var.set(e["name"])
        self._desc_var.set(e.get("description",""))
        self._keys_var.set(e.get("keywords",""))
        self._switch_tab("EDITOR")
        self._update_preview()

    def _delete_selected(self):
        if not self._selected_expr or self._selected_expr["builtin"]:
            return
        name = self._selected_expr["name"]
        if messagebox.askyesno("Delete", f"Delete expression '{name}'?", parent=self):
            delete_expression(name)
            from samuel_eyes import EXPRESSIONS as EXP
            EXP.pop(name, None)
            self._refresh_library()
            self._selected_expr = None

    # ------------------------------------------------------------------
    # TRAINING TAB
    # ------------------------------------------------------------------

    def _build_training(self):
        f = tk.Frame(self._content, bg=BG)
        self._tab_frames["TRAINING"] = f

        left = tk.Frame(f, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0,10))

        tk.Label(left, text="EMOTION TRAINING",
                 bg=BG, fg=TEXT, font=("Menlo",13,"bold")).pack(anchor="w", pady=(0,6))
        tk.Label(left,
                 text="Write something — Samuel will guess the emotion.\n"
                      "Tell him if he's right or pick the correct one.",
                 bg=BG, fg=MUTED, font=("Menlo",10),
                 justify="left").pack(anchor="w", pady=(0,10))

        # Input
        inf = tk.Frame(left, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        inf.pack(fill="x", pady=(0,8))
        fi = tk.Frame(inf, bg=PANEL)
        fi.pack(fill="x", padx=12, pady=10)
        tk.Label(fi, text="Your message:", bg=PANEL, fg=MUTED,
                 font=("Menlo",10)).pack(anchor="w")
        self._train_input = tk.Text(fi, bg=CARD, fg=TEXT,
                                     insertbackground=ACCENT, relief="flat",
                                     font=("Menlo",11), height=3, wrap="word")
        self._train_input.pack(fill="x", pady=(4,8))
        tk.Button(fi, text="▶  GUESS MY EMOTION",
                  bg=ACCENT, fg="#11100F", relief="flat",
                  font=("Menlo",11,"bold"),
                  command=self._do_guess).pack(anchor="w")

        # Result
        gf_outer = tk.Frame(left, bg=PANEL,
                             highlightbackground=BORDER, highlightthickness=1)
        gf_outer.pack(fill="x", pady=(0,8))
        gf = tk.Frame(gf_outer, bg=PANEL)
        gf.pack(fill="x", padx=12, pady=10)

        tk.Label(gf, text="Samuel thinks you feel:",
                 bg=PANEL, fg=MUTED, font=("Menlo",10)).pack(anchor="w")
        self._guess_lbl = tk.Label(gf, text="—",
                                    bg=PANEL, fg=ACCENT,
                                    font=("Menlo",20,"bold"))
        self._guess_lbl.pack(anchor="w", pady=(2,8))

        self._guess_preview = tk.Canvas(gf, bg="#0A0A0A",
                                         highlightthickness=0,
                                         width=280, height=90)
        self._guess_preview.pack(anchor="w", pady=(0,8))

        fb = tk.Frame(gf, bg=PANEL)
        fb.pack(anchor="w")
        tk.Button(fb, text="✓  CORRECT",
                  bg="#3A6B3A", fg=TEXT, relief="flat",
                  font=("Menlo",11,"bold"),
                  command=self._mark_correct).pack(side="left", padx=(0,8))
        tk.Button(fb, text="✗  WRONG",
                  bg="#6B3A3A", fg=TEXT, relief="flat",
                  font=("Menlo",11,"bold"),
                  command=self._mark_wrong).pack(side="left")

        # Correction picker
        cf_outer = tk.Frame(left, bg=PANEL,
                             highlightbackground=BORDER, highlightthickness=1)
        cf_outer.pack(fill="x", pady=(0,8))
        cf = tk.Frame(cf_outer, bg=PANEL)
        cf.pack(fill="x", padx=12, pady=10)

        tk.Label(cf, text="Correct expression was:",
                 bg=PANEL, fg=MUTED, font=("Menlo",10)).pack(anchor="w", pady=(0,6))
        self._correction_var = tk.StringVar(value="neutral")
        grid = tk.Frame(cf, bg=PANEL)
        grid.pack(anchor="w")
        for i, name in enumerate(list(EXPRESSIONS.keys())):
            tk.Radiobutton(grid, text=name,
                           variable=self._correction_var, value=name,
                           bg=PANEL, fg=TEXT, selectcolor=CARD,
                           activebackground=PANEL, font=("Menlo",10),
                           command=self._preview_correction
                           ).grid(row=i//3, column=i%3, sticky="w", padx=8, pady=1)

        tk.Button(cf, text="SAVE CORRECTION",
                  bg=ACCENT2, fg="#11100F", relief="flat",
                  font=("Menlo",11,"bold"),
                  command=self._save_correction).pack(anchor="w", pady=(8,0))

        # Stats panel
        right = tk.Frame(f, bg=PANEL,
                          highlightbackground=BORDER, highlightthickness=1,
                          width=240)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        ri = tk.Frame(right, bg=PANEL)
        ri.pack(fill="both", expand=True, padx=12, pady=12)
        tk.Label(ri, text="TRAINING STATS",
                 bg=PANEL, fg=TEXT, font=("Menlo",11,"bold")).pack(anchor="w")
        tk.Frame(ri, bg=BORDER, height=1).pack(fill="x", pady=6)
        self._stats_lbl = tk.Label(ri, text="",
                                    bg=PANEL, fg=TEXT,
                                    font=("Menlo",10), justify="left")
        self._stats_lbl.pack(anchor="w")
        tk.Label(ri, text="\nRECENT",
                 bg=PANEL, fg=MUTED, font=("Menlo",10,"bold")).pack(anchor="w")
        self._recent_lbl = tk.Label(ri, text="",
                                     bg=PANEL, fg=MUTED,
                                     font=("Menlo",9), justify="left",
                                     wraplength=200)
        self._recent_lbl.pack(anchor="w")

    def _do_guess(self):
        text = self._train_input.get("1.0","end-1c").strip()
        if not text:
            return
        self._train_text = text
        def _predict():
            learned = predict_from_training(text)
            if not learned:
                try:
                    from Samuel_AI.features.emotion_detector import detect_text_emotion
                    result  = detect_text_emotion(text)
                    learned = EMOTION_MAP.get(result.get("emotion","neutral"), "neutral")
                except Exception:
                    learned = "neutral"
            self._train_predicted = learned
            self.after(0, lambda: self._show_guess(learned))
        threading.Thread(target=_predict, daemon=True).start()
        self._guess_lbl.config(text="thinking...", fg=MUTED)

    def _show_guess(self, expr_name):
        self._guess_lbl.config(text=expr_name.upper(), fg=ACCENT)
        expr   = get_expression(expr_name)
        params = expr["params"] if expr else EXPRESSIONS.get(expr_name, EXPRESSIONS["neutral"])
        self._guess_preview.config(width=280, height=90)
        self._guess_preview.update()
        draw_eye_preview(self._guess_preview, params)
        vw = getattr(self.gui, "voice_win", None)
        if vw:
            try:
                ew = getattr(vw, "eyes_win", None)
                if ew and ew.winfo_exists():
                    self.gui.root.after(
                        0, lambda: ew.samuel_eyes.set_expression(expr_name)
                    )
            except Exception:
                pass

    def _mark_correct(self):
        if not self._train_predicted:
            return
        save_training_sample(self._train_text, self._train_predicted,
                              self._train_predicted, was_right=True)
        self._guess_lbl.config(text="✓ "+self._train_predicted.upper(), fg="#9AD39C")
        self._refresh_training_stats()
        self._train_input.delete("1.0","end")
        self._train_predicted = None

    def _mark_wrong(self):
        if not self._train_predicted:
            return
        self._guess_lbl.config(text="✗ wrong — pick correct →", fg="#B85C5C")

    def _preview_correction(self):
        name   = self._correction_var.get()
        expr   = get_expression(name)
        params = expr["params"] if expr else EXPRESSIONS.get(name, EXPRESSIONS["neutral"])
        draw_eye_preview(self._guess_preview, params)

    def _save_correction(self):
        if not self._train_predicted or not self._train_text:
            return
        correct = self._correction_var.get()
        save_training_sample(self._train_text, self._train_predicted,
                              correct, was_right=False)
        self._guess_lbl.config(text=f"Saved: {correct.upper()}", fg=ACCENT2)
        self._refresh_training_stats()
        self._train_input.delete("1.0","end")
        self._train_predicted = None

    def _refresh_training_stats(self):
        stats = get_training_stats()
        self._stats_lbl.config(
            text=f"Total samples:  {stats['total']}\n"
                 f"Correct:        {stats['correct']}\n"
                 f"Accuracy:       {stats['accuracy']}%"
        )
        lines = []
        for r in stats["recent"]:
            mark = "✓" if r["was_right"] else "✗"
            lines.append(f"{mark} \"{r['text'][:20]}...\"\n   → {r['correct']}")
        self._recent_lbl.config(text="\n".join(lines) or "No data yet.")


# -------------------------------------------------------
# OPEN
# -------------------------------------------------------

def open_expression_trainer(gui):
    try:
        if getattr(gui, "_expr_trainer", None) and gui._expr_trainer.winfo_exists():
            gui._expr_trainer.lift()
            return gui._expr_trainer
    except Exception:
        pass
    win = ExpressionTrainerPanel(gui)
    gui._expr_trainer = win
    return win