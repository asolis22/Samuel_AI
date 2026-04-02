import tkinter as tk
from tkinter import ttk, messagebox

from ui.theme import BG, PANEL, CARD, BORDER, TEXT, MUTED, ACCENT, ACCENT2
from reaction_gif_engine import (
    list_training_rows, update_training_row, delete_training_row,
    predict_reaction_and_gif, save_feedback,
)


class ReactionTrainerPanel(tk.Toplevel):
    def __init__(self, gui):
        super().__init__(gui.root)
        self.gui = gui
        self.title("Samuel — Reaction GIF Trainer")
        self.configure(bg=BG)
        self.geometry("1080x760")
        self.minsize(940, 620)
        self.selected_id = None
        self._build()
        self.refresh_rows()

    def _build(self):
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=18, pady=(16, 10))
        tk.Label(header, text="REACTION GIF TRAINER", bg=BG, fg=TEXT,
                 font=("Menlo", 16, "bold")).pack(anchor="w")
        tk.Label(header, text="Test phrases, correct reactions, and edit or delete learned rows.",
                 bg=BG, fg=MUTED, font=("Menlo", 10)).pack(anchor="w", pady=(4, 0))

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        left = tk.Frame(outer, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tk.Frame(outer, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        right.pack(side="right", fill="y", padx=(10, 0))

        # Test area
        test = tk.Frame(left, bg=PANEL)
        test.pack(fill="x", padx=12, pady=12)
        tk.Label(test, text="Test phrase", bg=PANEL, fg=TEXT, font=("Menlo", 12, "bold")).pack(anchor="w")
        self.test_input = tk.Text(test, bg=CARD, fg=TEXT, insertbackground=ACCENT,
                                  relief="flat", height=4, font=("Menlo", 11), wrap="word")
        self.test_input.pack(fill="x", pady=(6, 8))
        tk.Button(test, text="PREDICT", bg=ACCENT, fg="#11100F", relief="flat",
                  font=("Menlo", 11, "bold"), command=self.predict).pack(anchor="w")
        self.pred_lbl = tk.Label(test, text="No prediction yet.", bg=PANEL, fg=MUTED,
                                 justify="left", font=("Menlo", 11))
        self.pred_lbl.pack(anchor="w", pady=(10, 0))
        self.correct_reaction = tk.Entry(test, bg=CARD, fg=TEXT, insertbackground=ACCENT,
                                         relief="flat", font=("Menlo", 11))
        self.correct_reaction.pack(fill="x", pady=(10, 6))
        self.correct_reaction.insert(0, "correct reaction")
        self.correct_prompt = tk.Entry(test, bg=CARD, fg=TEXT, insertbackground=ACCENT,
                                       relief="flat", font=("Menlo", 11))
        self.correct_prompt.pack(fill="x", pady=(0, 8))
        self.correct_prompt.insert(0, "correct gif prompt")
        btns = tk.Frame(test, bg=PANEL)
        btns.pack(fill="x")
        tk.Button(btns, text="SAVE AS CORRECT", bg=ACCENT2, fg="#11100F", relief="flat",
                  font=("Menlo", 10, "bold"), command=self.save_correct).pack(side="left")
        tk.Button(btns, text="SAVE CORRECTION", bg=ACCENT, fg="#11100F", relief="flat",
                  font=("Menlo", 10, "bold"), command=self.save_correction).pack(side="left", padx=8)

        # List area
        cols = ("id", "text", "reaction", "gif_prompt", "timestamp")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18)
        for col, width in [("id", 60), ("text", 360), ("reaction", 130), ("gif_prompt", 220), ("timestamp", 150)]:
            self.tree.heading(col, text=col.upper())
            self.tree.column(col, width=width, stretch=(col == "text"))
        self.tree.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # Edit panel
        tk.Label(right, text="Edit selected", bg=PANEL, fg=TEXT,
                 font=("Menlo", 12, "bold")).pack(anchor="w", padx=12, pady=(12, 6))
        self.edit_reaction = tk.Entry(right, bg=CARD, fg=TEXT, insertbackground=ACCENT,
                                      relief="flat", font=("Menlo", 11), width=28)
        self.edit_reaction.pack(fill="x", padx=12, pady=(0, 6))
        self.edit_prompt = tk.Entry(right, bg=CARD, fg=TEXT, insertbackground=ACCENT,
                                    relief="flat", font=("Menlo", 11), width=28)
        self.edit_prompt.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(right, text="UPDATE", bg=ACCENT, fg="#11100F", relief="flat",
                  font=("Menlo", 10, "bold"), command=self.update_selected).pack(fill="x", padx=12)
        tk.Button(right, text="DELETE", bg="#B85C5C", fg="#11100F", relief="flat",
                  font=("Menlo", 10, "bold"), command=self.delete_selected).pack(fill="x", padx=12, pady=(8, 0))
        tk.Button(right, text="REFRESH", bg=CARD, fg=TEXT, relief="flat",
                  font=("Menlo", 10, "bold"), command=self.refresh_rows).pack(fill="x", padx=12, pady=(8, 0))

    def refresh_rows(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for row in list_training_rows(limit=500):
            reaction = row.get("corrected_reaction") or row.get("predicted_reaction")
            gif_prompt = row.get("corrected_gif_prompt") or row.get("predicted_gif_prompt")
            self.tree.insert("", "end", iid=str(row["id"]), values=(
                row["id"],
                (row["text"] or "")[:90],
                reaction or "",
                gif_prompt or "",
                row.get("timestamp") or "",
            ))

    def predict(self):
        text = self.test_input.get("1.0", "end-1c").strip()
        if not text:
            return
        pred = predict_reaction_and_gif(text)
        self._last_test_text = text
        self._last_prediction = pred
        self.pred_lbl.config(text=(
            f"Reaction: {pred['reaction']}\n"
            f"GIF prompt: {pred['gif_prompt']}\n"
            f"Confidence: {pred.get('confidence', 0):.2f}\n"
            f"Source: {pred['source']}"
        ), fg=TEXT)
        self.correct_reaction.delete(0, "end")
        self.correct_reaction.insert(0, pred["reaction"])
        self.correct_prompt.delete(0, "end")
        self.correct_prompt.insert(0, pred["gif_prompt"])

    def save_correct(self):
        if not hasattr(self, "_last_prediction"):
            return
        save_feedback(
            self._last_test_text,
            self._last_prediction["reaction"],
            self._last_prediction["gif_prompt"],
            True,
            self._last_prediction["reaction"],
            self._last_prediction["gif_prompt"],
        )
        self.refresh_rows()

    def save_correction(self):
        if not hasattr(self, "_last_prediction"):
            return
        save_feedback(
            self._last_test_text,
            self._last_prediction["reaction"],
            self._last_prediction["gif_prompt"],
            False,
            self.correct_reaction.get().strip(),
            self.correct_prompt.get().strip(),
        )
        self.refresh_rows()

    def on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        self.selected_id = int(sel[0])
        row = next((r for r in list_training_rows(limit=500) if r["id"] == self.selected_id), None)
        if not row:
            return
        reaction = row.get("corrected_reaction") or row.get("predicted_reaction") or ""
        prompt = row.get("corrected_gif_prompt") or row.get("predicted_gif_prompt") or ""
        self.edit_reaction.delete(0, "end")
        self.edit_reaction.insert(0, reaction)
        self.edit_prompt.delete(0, "end")
        self.edit_prompt.insert(0, prompt)

    def update_selected(self):
        if not self.selected_id:
            return
        update_training_row(self.selected_id, self.edit_reaction.get(), self.edit_prompt.get())
        self.refresh_rows()

    def delete_selected(self):
        if not self.selected_id:
            return
        if messagebox.askyesno("Delete", "Delete this learned reaction?", parent=self):
            delete_training_row(self.selected_id)
            self.selected_id = None
            self.refresh_rows()


def open_reaction_trainer_panel(gui):
    try:
        if getattr(gui, "_reaction_trainer", None) and gui._reaction_trainer.winfo_exists():
            gui._reaction_trainer.lift()
            return gui._reaction_trainer
    except Exception:
        pass
    gui._reaction_trainer = ReactionTrainerPanel(gui)
    return gui._reaction_trainer
