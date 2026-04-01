# ui/chats_panel.py
import tkinter as tk
from .theme import BG, TEXT, MUTED, CARD, ACCENT, ACCENT2, ACCENT3, DEFAULT_CHAT
from .text_utils import clean_chat_name

def open_chats_panel(gui):
    top = tk.Toplevel(gui.root)
    top.title("Chats")
    top.configure(bg=BG)
    top.geometry("420x440")
    top.resizable(False, False)

    title = tk.Label(top, text="CHATS", bg=BG, fg=TEXT, font=("Menlo", 16, "bold"))
    title.pack(pady=(16, 10))

    info = tk.Label(
        top,
        text="Click a chat to open it.\nOr type a name and press Create.",
        bg=BG, fg=MUTED, font=("Menlo", 11)
    )
    info.pack(pady=(0, 12))

    listbox = tk.Listbox(
        top, bg=CARD, fg=TEXT, font=("Menlo", 12),
        height=12, selectbackground=ACCENT, selectforeground="#11100F"
    )
    listbox.pack(fill="x", padx=18)

    def refresh_list():
        listbox.delete(0, "end")
        names = gui.list_chats()
        for n in names:
            listbox.insert("end", n)
        return names

    names = refresh_list()

    if gui.current_chat_name in names:
        idx = names.index(gui.current_chat_name)
        listbox.selection_set(idx)
        listbox.activate(idx)

    entry = tk.Entry(top, bg=CARD, fg=TEXT, insertbackground=ACCENT, relief="flat", font=("Menlo", 12))
    entry.pack(fill="x", padx=18, pady=(14, 8))

    btn_row = tk.Frame(top, bg=BG)
    btn_row.pack(fill="x", padx=18, pady=(8, 0))

    def open_selected():
        sel = listbox.curselection()
        if not sel:
            return
        name = listbox.get(sel[0])
        gui._switch_chat(name)
        top.destroy()

    def create_chat():
        name = clean_chat_name(entry.get())
        if not name:
            return
        gui.get_or_create_chat(name)
        refresh_list()
        gui._switch_chat(name)
        top.destroy()

    def delete_selected():
        sel = listbox.curselection()
        if not sel:
            return

        name = listbox.get(sel[0])
        deleting_current = (name == gui.current_chat_name)

        try:
            gui.delete_chat(name)
        except Exception as e:
            print("Delete chat failed:", e)
            return

        names2 = refresh_list()

        if deleting_current:
            fallback = DEFAULT_CHAT if DEFAULT_CHAT in names2 else (names2[0] if names2 else DEFAULT_CHAT)
            gui._switch_chat(fallback)

        if names2:
            listbox.selection_set(0)
            listbox.activate(0)

    tk.Button(btn_row, text="OPEN", bg=ACCENT, fg="#11100F",
              relief="flat", font=("Menlo", 12, "bold"), command=open_selected
    ).pack(side="left", fill="x", padx=(0, 6))

    tk.Button(btn_row, text="CREATE", bg=ACCENT2, fg="#11100F",
              relief="flat", font=("Menlo", 12, "bold"), command=create_chat
    ).pack(side="left", fill="x", padx=6)

    tk.Button(btn_row, text="DELETE", bg=ACCENT3, fg="#11100F",
              relief="flat", font=("Menlo", 12, "bold"), command=delete_selected
    ).pack(side="left", fill="x", padx=(6, 0))

    listbox.bind("<Double-Button-1>", lambda _e: open_selected())