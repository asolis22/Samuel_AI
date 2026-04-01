# ui/clipboard.py
import sys
import tkinter as tk

def enable_clipboard_shortcuts(root: tk.Tk):
    """
    Ensures Ctrl/Cmd C/V/X work even if other bindings interfere.
    We forward the event to the currently focused widget.
    """
    is_mac = (sys.platform == "darwin")

    def _focused():
        w = root.focus_get()
        return w

    def _copy(_e=None):
        w = _focused()
        if w:
            try:
                w.event_generate("<<Copy>>")
            except Exception:
                pass
        return "break"

    def _paste(_e=None):
        w = _focused()
        if w:
            try:
                w.event_generate("<<Paste>>")
            except Exception:
                pass
        return "break"

    def _cut(_e=None):
        w = _focused()
        if w:
            try:
                w.event_generate("<<Cut>>")
            except Exception:
                pass
        return "break"

    if is_mac:
        root.bind_all("<Command-c>", _copy)
        root.bind_all("<Command-v>", _paste)
        root.bind_all("<Command-x>", _cut)
    else:
        root.bind_all("<Control-c>", _copy)
        root.bind_all("<Control-v>", _paste)
        root.bind_all("<Control-x>", _cut)