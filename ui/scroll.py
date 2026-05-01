# ui/scroll.py
import sys
import tkinter as tk

def is_near_bottom(chat_canvas: tk.Canvas) -> bool:
    try:
        _, last = chat_canvas.yview()
        return last > 0.98
    except Exception:
        return True

def refresh_scrollregion(root: tk.Tk, chat_canvas: tk.Canvas):
    root.update_idletasks()
    bbox = chat_canvas.bbox("all")
    if bbox:
        chat_canvas.configure(scrollregion=bbox)

def scroll_to_bottom(root: tk.Tk, chat_canvas: tk.Canvas):
    try:
        root.update_idletasks()
        chat_canvas.configure(scrollregion=chat_canvas.bbox("all"))
        chat_canvas.yview_moveto(1.0)
    except tk.TclError:
        pass

def bind_mousewheel(root: tk.Tk, canvas: tk.Canvas, inside_widget: tk.Widget):
    """
    macOS: trackpad MouseWheel events often route to the focused widget (like the input Text),
    so "inside chat" filtering can kill scrolling. This version always scrolls the chat canvas.
    """
    def _on_mousewheel(event):
        delta = getattr(event, "delta", 0) or 0
        if delta == 0:
            return

        if sys.platform == "darwin":
            # mac trackpad: delta is small; scroll 1 unit per event
            step = -1 if delta > 0 else 1
            canvas.yview_scroll(step, "units")
        else:
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")

        return "break"

    def _on_linux_up(_event):
        canvas.yview_scroll(-1, "units")
        return "break"

    def _on_linux_down(_event):
        canvas.yview_scroll(1, "units")
        return "break"

    # Bind globally so it works even when focus is in the input box
    root.bind_all("<MouseWheel>", _on_mousewheel, add="+")
    root.bind_all("<Shift-MouseWheel>", _on_mousewheel, add="+")  # mac safety
    root.bind_all("<Button-4>", _on_linux_up, add="+")
    root.bind_all("<Button-5>", _on_linux_down, add="+")
    
def bind_keyboard_scroll(root: tk.Tk, canvas: tk.Canvas):
    def pgup(_e=None):
        canvas.yview_scroll(-1, "pages"); return "break"
    def pgdn(_e=None):
        canvas.yview_scroll(1, "pages"); return "break"
    def home(_e=None):
        canvas.yview_moveto(0.0); return "break"
    def end(_e=None):
        canvas.yview_moveto(1.0); return "break"

    # keep global for convenience, but do add="+"
    root.bind_all("<Prior>", pgup, add="+")
    root.bind_all("<Next>", pgdn, add="+")
    root.bind_all("<Home>", home, add="+")
    root.bind_all("<End>", end, add="+")
