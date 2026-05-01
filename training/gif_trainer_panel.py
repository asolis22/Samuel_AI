"""
GIF Trainer Panel for Samuel.

Triggered by: Alpha.e.x0.1.eXpr3ss

This version does NOT use fixed GIF file paths.
Instead it trains:
- sentence
- predicted reaction
- predicted GIF prompt
- yes/no feedback
- corrected reaction
- corrected GIF prompt

It can preview a random GIPHY GIF for the current prompt.
"""

import tkinter as tk
from tkinter import ttk, messagebox

try:
    from ui.theme import BG, PANEL, CARD, ACCENT, ACCENT2, ACCENT3, TEXT, MUTED, BORDER
except Exception:
    BG = "#141210"; PANEL = "#1A1714"; CARD = "#201D1A"
    ACCENT = "#7FB5AF"; ACCENT2 = "#B07F5F"; ACCENT3 = "#6A8F8A"
    TEXT = "#E8E0D5"; MUTED = "#5A5550"; BORDER = "#2A2520"


def open_gif_trainer(app) -> tk.Toplevel:
    win = GIFTrainerPanel(app)
    return win.root


class GIFTrainerPanel:
    def __init__(self, app):
        self.app = app
        self._tracker = getattr(app, "_gif_engine", None)

        self.current_prediction = None
        self.current_gif_result = None
        self.learned_rows = []

        self.root = tk.Toplevel(app.root)
        self.root.title("GIF Reaction Trainer — SAMUEL")
        self.root.configure(bg=BG)
        self.root.geometry("980x650")
        self.root.minsize(820, 540)
        self.root.transient(app.root)

        self._build()
        self._refresh_learned()

    # --------------------------------------------------
    # Layout
    # --------------------------------------------------
    def _build(self):
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=18, pady=(16, 8))

        tk.Label(
            hdr,
            text="GIF REACTION TRAINER",
            bg=BG,
            fg=ACCENT,
            font=("Menlo", 18, "bold")
        ).pack(side="left")

        tk.Label(
            hdr,
            text="train Samuel to predict reactions + GIF prompts",
            bg=BG,
            fg=MUTED,
            font=("Menlo", 11)
        ).pack(side="left", padx=(14, 0), pady=(4, 0))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=4)

        # ---------------- LEFT: learned data ----------------
        left = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        tk.Label(
            left,
            text="LEARNED REACTIONS",
            bg=PANEL,
            fg=MUTED,
            font=("Menlo", 11, "bold"),
            padx=10,
            pady=8
        ).pack(anchor="w")

        list_wrap = tk.Frame(left, bg=PANEL)
        list_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._listbox = tk.Listbox(
            list_wrap,
            bg=CARD,
            fg=TEXT,
            font=("Menlo", 11),
            selectbackground=ACCENT3,
            selectforeground=TEXT,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0
        )
        self._listbox.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(list_wrap, orient="vertical", command=self._listbox.yview)
        sb.pack(side="right", fill="y")
        self._listbox.configure(yscrollcommand=sb.set)

        btn_row = tk.Frame(left, bg=PANEL)
        btn_row.pack(fill="x", padx=8, pady=(0, 8))

        tk.Button(
            btn_row,
            text="DELETE",
            bg=BG,
            fg=ACCENT2,
            relief="flat",
            font=("Menlo", 11, "bold"),
            cursor="hand2",
            command=self._delete_selected
        ).pack(side="left")

        tk.Button(
            btn_row,
            text="LOAD",
            bg=BG,
            fg=ACCENT,
            relief="flat",
            font=("Menlo", 11, "bold"),
            cursor="hand2",
            command=self._load_selected
        ).pack(side="left", padx=(10, 0))

        # ---------------- RIGHT: trainer ----------------
        right = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="both", expand=True)

        tk.Label(
            right,
            text="TRAIN A REACTION",
            bg=PANEL,
            fg=MUTED,
            font=("Menlo", 11, "bold"),
            padx=10,
            pady=8
        ).pack(anchor="w")

        form = tk.Frame(right, bg=PANEL)
        form.pack(fill="both", expand=True, padx=10, pady=4)

        # Sentence
        tk.Label(form, text="Input sentence", bg=PANEL, fg=MUTED, font=("Menlo", 11)).grid(
            row=0, column=0, sticky="nw", pady=4
        )
        self._sentence_txt = tk.Text(
            form, bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12), height=4, wrap="word",
            highlightbackground=BORDER, highlightthickness=1
        )
        self._sentence_txt.grid(row=0, column=1, sticky="ew", pady=4)

        # Predicted reaction
        tk.Label(form, text="Predicted reaction", bg=PANEL, fg=MUTED, font=("Menlo", 11)).grid(
            row=1, column=0, sticky="w", pady=4
        )
        self._pred_reaction_var = tk.StringVar()
        tk.Entry(
            form, textvariable=self._pred_reaction_var,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            highlightbackground=BORDER, highlightthickness=1
        ).grid(row=1, column=1, sticky="ew", pady=4)

        # Predicted GIF prompt
        tk.Label(form, text="Predicted GIF prompt", bg=PANEL, fg=MUTED, font=("Menlo", 11)).grid(
            row=2, column=0, sticky="w", pady=4
        )
        self._pred_prompt_var = tk.StringVar()
        tk.Entry(
            form, textvariable=self._pred_prompt_var,
            bg=CARD, fg=TEXT, insertbackground=ACCENT,
            relief="flat", font=("Menlo", 12),
            highlightbackground=BORDER, highlightthickness=1
        ).grid(row=2, column=1, sticky="ew", pady=4)

        # Controls
        ctrl = tk.Frame(form, bg=PANEL)
        ctrl.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 8))

        tk.Button(
            ctrl,
            text="PREDICT + PREVIEW",
            bg=ACCENT,
            fg="#11100F",
            relief="flat",
            font=("Menlo", 11, "bold"),
            cursor="hand2",
            command=self._predict_and_preview
        ).pack(side="left", ipadx=8, ipady=4)

        tk.Button(
            ctrl,
            text="YES / SAVE",
            bg=BG,
            fg=ACCENT,
            relief="flat",
            font=("Menlo", 11, "bold"),
            cursor="hand2",
            command=self._save_correct
        ).pack(side="left", padx=(10, 0))

        tk.Button(
            ctrl,
            text="NO / SAVE CORRECTION",
            bg=BG,
            fg=ACCENT2,
            relief="flat",
            font=("Menlo", 11, "bold"),
            cursor="hand2",
            command=self._save_correction
        ).pack(side="left", padx=(10, 0))

        tk.Button(
            ctrl,
            text="SHOW AGAIN",
            bg=BG,
            fg=ACCENT3,
            relief="flat",
            font=("Menlo", 11, "bold"),
            cursor="hand2",
            command=self._show_preview_again
        ).pack(side="left", padx=(10, 0))

        # Status
        self._status = tk.Label(
            self.root,
            text="Ready.",
            bg=BG,
            fg=MUTED,
            font=("Menlo", 11),
            anchor="w"
        )
        self._status.pack(fill="x", padx=18, pady=(4, 10))

        form.columnconfigure(1, weight=1)

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def _set_status(self, msg: str, color=None):
        self._status.config(text=msg, fg=color or MUTED)

    def _refresh_learned(self):
        self._listbox.delete(0, "end")
        self.learned_rows = []

        if not self._tracker:
            self._listbox.insert("end", "(GIF engine not loaded)")
            return

        try:
            rows = self._tracker.list_examples()
        except Exception as e:
            self._listbox.insert("end", f"(could not load learned rows: {e})")
            return

        self.learned_rows = rows
        for r in rows:
            text = (r.get("text") or "").strip().replace("\n", " ")
            final_reaction = r.get("final_reaction") or r.get("predicted_reaction") or "?"
            final_prompt = r.get("final_gif_prompt") or r.get("predicted_gif_prompt") or "?"
            short_text = text[:38] + ("..." if len(text) > 38 else "")
            self._listbox.insert("end", f"{final_reaction}  ·  {final_prompt}  ·  {short_text}")

    def _predict_and_preview(self):
        if not self._tracker:
            self._set_status("GIF engine not loaded.", ACCENT2)
            return

        text = self._sentence_txt.get("1.0", "end-1c").strip()
        if not text:
            self._set_status("Enter a sentence first.", ACCENT2)
            return

        try:
            prediction = self._tracker.predict_reaction_and_gif(text)
        except Exception as e:
            self._set_status(f"Prediction failed: {e}", ACCENT2)
            return

        self.current_prediction = prediction
        self._pred_reaction_var.set(prediction["reaction"])
        self._pred_prompt_var.set(prediction["gif_prompt"])

        try:
            gif_result = self._tracker.giphy_search_one_gif(prediction["gif_prompt"])
            self.current_gif_result = gif_result
        except Exception as e:
            self.current_gif_result = None
            self._set_status(f"GIPHY search failed: {e}", ACCENT2)
            return

        if not self.current_gif_result:
            self._set_status("No GIF found for that prompt.", ACCENT2)
            return

        self._show_preview_again()
        self._set_status("Prediction generated. Approve or correct it.", ACCENT)

    def _show_preview_again(self):
        if not self.current_gif_result:
            self._set_status("No preview GIF available yet.", ACCENT2)
            return

        try:
            gif_url = self.current_gif_result["gif_url"]
            title = self.current_gif_result.get("title", "GIF preview")
            self.app.add_gif_bubble_from_url(gif_url, label=f"GIF PREVIEW · {title}")
            self._set_status("Previewed GIF in main chat.", ACCENT)
        except Exception as e:
            self._set_status(f"Preview failed: {e}", ACCENT2)

    def _save_correct(self):
        if not self._tracker:
            self._set_status("GIF engine not loaded.", ACCENT2)
            return
        if not self.current_prediction:
            self._set_status("Run a prediction first.", ACCENT2)
            return

        text = self._sentence_txt.get("1.0", "end-1c").strip()
        try:
            self._tracker.save_feedback(
                text=text,
                predicted_reaction=self.current_prediction["reaction"],
                predicted_gif_prompt=self.current_prediction["gif_prompt"],
                correct=True,
                corrected_reaction=self.current_prediction["reaction"],
                corrected_gif_prompt=self.current_prediction["gif_prompt"]
            )
        except Exception as e:
            self._set_status(f"Save failed: {e}", ACCENT2)
            return

        self._set_status("Saved as correct.", ACCENT)
        self._refresh_learned()

    def _save_correction(self):
        if not self._tracker:
            self._set_status("GIF engine not loaded.", ACCENT2)
            return
        if not self.current_prediction:
            self._set_status("Run a prediction first.", ACCENT2)
            return

        text = self._sentence_txt.get("1.0", "end-1c").strip()
        corrected_reaction = self._pred_reaction_var.get().strip()
        corrected_prompt = self._pred_prompt_var.get().strip()

        if not corrected_reaction:
            self._set_status("Corrected reaction required.", ACCENT2)
            return
        if not corrected_prompt:
            self._set_status("Corrected GIF prompt required.", ACCENT2)
            return

        try:
            self._tracker.save_feedback(
                text=text,
                predicted_reaction=self.current_prediction["reaction"],
                predicted_gif_prompt=self.current_prediction["gif_prompt"],
                correct=False,
                corrected_reaction=corrected_reaction,
                corrected_gif_prompt=corrected_prompt
            )
        except Exception as e:
            self._set_status(f"Correction save failed: {e}", ACCENT2)
            return

        self._set_status("Saved correction.", ACCENT)
        self._refresh_learned()

    def _delete_selected(self):
        sel = self._listbox.curselection()
        if not sel:
            self._set_status("Select a learned row first.", ACCENT2)
            return

        idx = sel[0]
        try:
            row = self.learned_rows[idx]
        except Exception:
            self._set_status("Invalid selection.", ACCENT2)
            return

        row_id = row.get("id")
        if row_id is None:
            self._set_status("Selected row has no id.", ACCENT2)
            return

        if not messagebox.askyesno("Delete", "Delete this learned example?", parent=self.root):
            return

        try:
            self._tracker.delete_example(row_id)
        except Exception as e:
            self._set_status(f"Delete failed: {e}", ACCENT2)
            return

        self._set_status("Deleted learned example.", MUTED)
        self._refresh_learned()

    def _load_selected(self):
        sel = self._listbox.curselection()
        if not sel:
            self._set_status("Select a learned row first.", ACCENT2)
            return

        idx = sel[0]
        try:
            row = self.learned_rows[idx]
        except Exception:
            self._set_status("Invalid selection.", ACCENT2)
            return

        self._sentence_txt.delete("1.0", "end")
        self._sentence_txt.insert("1.0", row.get("text", ""))

        self._pred_reaction_var.set(row.get("final_reaction") or row.get("predicted_reaction") or "")
        self._pred_prompt_var.set(row.get("final_gif_prompt") or row.get("predicted_gif_prompt") or "")

        self.current_prediction = {
            "reaction": row.get("predicted_reaction") or "",
            "gif_prompt": row.get("predicted_gif_prompt") or "",
            "source": "loaded_example"
        }

        self.current_gif_result = None
        self._set_status("Loaded learned example into editor.", ACCENT)