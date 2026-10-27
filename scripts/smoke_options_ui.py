"""Open an isolated, disposable UI for optional-download visual QA."""

import tempfile
import tkinter as tk
from pathlib import Path

from spotano.gui import App

root = tk.Tk()
app = App(root, Path(tempfile.mkdtemp(prefix="spotano-options-ui-")))
root.title("spoTano · Opções de download · QA")
root.geometry("920x640")
root.mainloop()
