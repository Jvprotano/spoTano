"""Keep SDK child processes hidden inside an isolated Windows worker."""

import os
import subprocess
import time
from contextlib import contextmanager


@contextmanager
def background_subprocesses():
    if os.name != "nt":
        yield
        return
    # Patch the constructor, retaining the class itself: Windows asyncio's Popen
    # subclass may already exist and must inherit this policy too. Worker only.
    original = subprocess.Popen.__init__

    def hidden_init(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        original(self, *args, **kwargs)

    subprocess.Popen.__init__ = hidden_init
    try:
        yield
    finally:
        subprocess.Popen.__init__ = original


@contextmanager
def conversion_slot(directory, slots=2):
    """OS locks are released even if a worker is killed; no stale semaphore files."""
    directory.mkdir(parents=True, exist_ok=True)
    acquired = None
    started = time.monotonic()
    while acquired is None:
        for number in range(max(1, min(4, slots))):
            stream = (directory / f"{number}.lock").open("a+b")
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt

                    if not stream.read(1):
                        stream.write(b"0")
                        stream.flush()
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = stream
                break
            except OSError:
                stream.close()
        if acquired is None:
            if time.monotonic() - started > 120:
                raise TimeoutError("Fila de conversão excedeu 120 segundos.")
            time.sleep(0.05)
    try:
        yield time.monotonic() - started
    finally:
        acquired.close()
