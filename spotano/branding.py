"""Application identity and bundled icons for source and frozen installations."""

import os
import tkinter as tk
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
APP_ID = "Jvprotano.spoTano"


def set_app_id():
    """Keep Windows taskbar grouping independent of the Python interpreter."""
    if os.name == "nt":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def apply_icon(root):
    """Set the main window icon and the default inherited by new dialogs."""
    images = [
        tk.PhotoImage(master=root, file=str(ASSETS / f"spotano-{size}.png")) for size in (16, 32, 48, 256)
    ]
    root.iconphoto(True, *images)
    root._spotano_icons = images
    if os.name == "nt":
        root.iconbitmap(default=str(ASSETS / "spotano.ico"))
        root.iconbitmap(str(ASSETS / "spotano.ico"))
