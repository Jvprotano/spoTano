"""Shared desktop surfaces, typography and native widget styling."""

import tkinter as tk
from tkinter import ttk

BG = "#f5f6f2"
INK = "#203b31"
MUTED = "#56675f"
ACCENT = "#186449"
SIDEBAR = "#18392d"
LINE = "#dce3dc"


class TreeTooltip:
    """Describe icon cells without adding permanent text to the table."""

    def __init__(self, tree, describe):
        self.tree, self.describe = tree, describe
        self.timer = self.window = None
        self.text = ""
        tree.bind("<Motion>", self.motion, add="+")
        for event in ("<Leave>", "<ButtonPress>", "<MouseWheel>", "<KeyPress>", "<Destroy>"):
            tree.bind(event, self.hide, add="+")

    def motion(self, event):
        text = self.describe(event.x, event.y)
        self.tree.configure(cursor="hand2" if text else "")
        if text == self.text:
            return
        self.hide()
        self.text = text
        if text:
            self.timer = self.tree.after(450, lambda: self.show(event.x_root, event.y_root))

    def show(self, x, y):
        self.timer = None
        self.window = tk.Toplevel(self.tree)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        ttk.Label(self.window, text=self.text, padding=(9, 6), relief="solid", borderwidth=1).pack()
        self.window.update_idletasks()
        x = min(x + 12, self.window.winfo_screenwidth() - self.window.winfo_reqwidth() - 8)
        self.window.geometry(f"+{max(0, x)}+{y + 20}")

    def hide(self, _=None):
        if self.timer:
            self.tree.after_cancel(self.timer)
            self.timer = None
        if self.window:
            self.window.destroy()
            self.window = None
        self.text = ""


def configure(root):
    root.configure(bg=BG)
    root.option_add("*Toplevel.background", BG)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=("Segoe UI", 10), background=BG, foreground=INK)
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("Title.TLabel", font=("Segoe UI", 25, "bold"))
    style.configure("Section.TLabel", font=("Segoe UI", 12, "bold"))
    style.configure("TButton", padding=(14, 9), background="#e8ede6", borderwidth=0)
    style.map("TButton", background=[("active", "#dbe5dc")], foreground=[("disabled", "#78867e")])
    style.configure("Accent.TButton", background=ACCENT, foreground="white")
    style.map(
        "Accent.TButton",
        background=[("disabled", "#dce3dc"), ("active", "#115137")],
        foreground=[("disabled", "#6b7a70"), ("!disabled", "white")],
    )
    style.configure("Quiet.TButton", background=BG, foreground=ACCENT)
    style.map("Quiet.TButton", background=[("active", "#e6ece4")])
    style.configure("Nav.TButton", background=SIDEBAR, foreground="#dce9df", anchor="w", padding=(18, 13))
    style.map("Nav.TButton", background=[("active", "#254c3b")])
    style.configure(
        "Selected.Nav.TButton", background="#315b44", foreground="white", font=("Segoe UI", 10, "bold")
    )
    style.map("Selected.Nav.TButton", background=[("active", "#38694e")])
    style.configure("TEntry", padding=8, fieldbackground="white", bordercolor=LINE)
    style.configure("TCombobox", padding=7, fieldbackground="white", bordercolor=LINE, arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", "white")])
    style.configure("TCheckbutton", padding=(0, 5))
    style.configure("Treeview", rowheight=40, background="white", fieldbackground="white", borderwidth=0)
    style.configure(
        "Treeview.Heading",
        background="#eaf0e8",
        foreground=MUTED,
        font=("Segoe UI", 9, "bold"),
        padding=(10, 10),
        relief="flat",
    )
    style.map("Treeview", background=[("selected", "#d8eadc")], foreground=[("selected", INK)])
    style.configure("TNotebook", borderwidth=0, tabmargins=0)
    style.configure("Shell.TNotebook", bordercolor=BG, lightcolor=BG, darkcolor=BG)
    style.layout("Shell.TNotebook.Tab", [])
    style.configure("TNotebook.Tab", padding=(16, 9))
    style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", ACCENT)])
    style.configure("TLabelframe", bordercolor=LINE, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", font=("Segoe UI", 11, "bold"))
    style.configure(
        "Download.Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor="#e0e7de",
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        borderwidth=0,
        thickness=4,
    )


def scroll_page(parent):
    """Scrollable desktop page; bind only this page's descendants, never globally."""
    frame = ttk.Frame(parent)
    frame.pack(fill="both", expand=True)
    canvas = tk.Canvas(frame, bg=BG, highlightthickness=0, width=1)
    scroll = ttk.Scrollbar(frame, command=canvas.yview)
    scroll.pack(side="right", fill="y")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    body = ttk.Frame(canvas, padding=(0, 0, 16, 12))
    content = canvas.create_window(0, 0, window=body, anchor="nw")
    canvas.bind("<Configure>", lambda event: canvas.itemconfigure(content, width=event.width))
    body.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))

    def wheel(event):
        if canvas.bbox("all") and canvas.bbox("all")[3] > canvas.winfo_height():
            canvas.yview_scroll(
                -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1),
                "units",
            )
        return "break"

    def attach():
        def reveal(event):
            top = event.widget.winfo_rooty() - body.winfo_rooty()
            bottom = top + event.widget.winfo_height()
            visible_top = canvas.canvasy(0)
            if top < visible_top:
                canvas.yview_moveto(max(0, top - 8) / max(1, body.winfo_height()))
            elif bottom > visible_top + canvas.winfo_height():
                canvas.yview_moveto((bottom - canvas.winfo_height() + 8) / max(1, body.winfo_height()))

        def bind(widget):
            # Combobox wheel changes choices accidentally while scrolling a page.
            widget.bind("<MouseWheel>", wheel)
            widget.bind("<FocusIn>", reveal, add="+")
            for child in widget.winfo_children():
                bind(child)

        bind(body)
        canvas.bind("<MouseWheel>", wheel)

    body.after_idle(attach)
    return body


def section(parent, title, description=""):
    frame = ttk.Frame(parent, padding=(0, 12, 0, 18))
    frame.pack(fill="x")
    ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 6))
    if description:
        ttk.Label(frame, text=description, style="Muted.TLabel", wraplength=670).pack(
            anchor="w", pady=(0, 10)
        )
    return frame


def dialog(root, title, width=620, height=None):
    window = tk.Toplevel(root)
    window.title(title)
    window.configure(bg=BG)
    window.transient(root)
    window.resizable(True, bool(height))
    x = max(0, root.winfo_rootx() + (root.winfo_width() - width) // 2)
    y = max(0, root.winfo_rooty() + 60)
    if height:
        window.geometry(f"{width}x{height}+{x}+{y}")
    else:
        window.geometry(f"+{x}+{y}")

        def fit():
            window.update_idletasks()
            window.geometry(f"{width}x{window.winfo_reqheight()}+{x}+{y}")

        window.after_idle(fit)
    window.bind("<Escape>", lambda _: window.destroy())
    return window
