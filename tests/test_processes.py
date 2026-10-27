import os
import subprocess
import sys

import pytest

from spotano.processes import background_subprocesses


@pytest.mark.skipif(os.name != "nt", reason="Windows console policy")
def test_hidden_policy_covers_sync_and_existing_asyncio_subclasses_and_restores_constructor(monkeypatch):
    # Import before applying the worker policy, as may happen in a frozen app.
    import asyncio.windows_utils

    original = subprocess.Popen.__init__
    calls = []

    def record(self, *args, **kwargs):
        calls.append(kwargs.get("creationflags", 0))
        original(self, *args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", record)
    command = [sys.executable, "-c", "import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())"]

    async def child():
        process = await asyncio.create_subprocess_exec(
            *command, stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
        stdout, _ = await process.communicate()
        assert process.returncode == 0 and stdout.strip() == b"0"

    with background_subprocesses():
        result = subprocess.run(command, capture_output=True, check=True)
        assert result.stdout.strip() == b"0"
        asyncio.run(child())
    assert subprocess.Popen.__init__ is record
    assert len(calls) == 2 and all(flags & subprocess.CREATE_NO_WINDOW for flags in calls)
    assert calls[-1] & subprocess.CREATE_NEW_PROCESS_GROUP
