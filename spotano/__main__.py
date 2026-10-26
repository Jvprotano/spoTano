"""Desktop entry and subprocess entry share the same frozen binary."""

import argparse
import os
import sys
from pathlib import Path


class InstanceLock:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.stream = (root / ".instance.lock").open("a+b")
        self.stream.seek(0)
        self.stream.write(b"0")
        self.stream.flush()
        self.stream.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def close(self):
        self.stream.close()


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "--worker":
        # Windowed PyInstaller has no stdout/stderr streams. SDKs expect real streams.
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")
        from .provider import worker

        worker(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    parser = argparse.ArgumentParser(description="spoTano — biblioteca musical local")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "spoTano",
    )
    args = parser.parse_args()
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        lock = InstanceLock(args.data_dir.resolve())
    except OSError:
        messagebox.showerror(
            "spoTano já está aberto", "Feche a outra janela que usa esta biblioteca antes de continuar."
        )
        root.destroy()
        return
    try:
        from .gui import App

        App(root, args.data_dir)
        root.deiconify()
        root.mainloop()
    except Exception as exc:
        messagebox.showerror("Falha ao iniciar spoTano", str(exc))
    finally:
        lock.close()


if __name__ == "__main__":
    main()
