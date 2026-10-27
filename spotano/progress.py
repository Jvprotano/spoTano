"""Translate real transfer/conversion counters without inventing search progress."""

import time


def format_bytes(value):
    value = float(value)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{value:.2f} {unit}".replace(".", ",")
        value /= 1024


def download_progress(report, stage_callback=lambda stage: None, error_callback=lambda message: None):
    # Keep the SDK out of the GUI process. Its simple TUI discards percentages,
    # so capture the original counters before forwarding to its existing hooks.
    from spotdl.download.progress_handler import ProgressHandler, SongTracker

    class Tracker(SongTracker):
        detail = ""
        detail_stage = ""
        final_update = False

        def notify_error(self, message, traceback, finish=False):
            from .telemetry import sanitize

            causes, visited, cause = [], set(), traceback
            while cause is not None and id(cause) not in visited and len(causes) < 6:
                visited.add(id(cause))
                causes.append(f"{type(cause).__name__}: {cause}")
                cause = getattr(cause, "__cause__", None) or getattr(cause, "__context__", None)
            error_callback(sanitize(" ← ".join(reversed(causes))))
            super().notify_error(message, traceback, finish)

        def yt_dlp_progress_hook(self, data):
            if data.get("status") == "downloading":
                received = data.get("downloaded_bytes")
                total = data.get("total_bytes") or data.get("total_bytes_estimate")
                self.detail_stage, self.detail = "Downloading", ""
                self.final_update = False
                if received is not None:
                    self.detail = format_bytes(received) + " recebidos"
                    if total and total > 0:
                        estimated = not data.get("total_bytes")
                        percentage = max(0, min(100, received / total * 100))
                        self.detail = (
                            f"{format_bytes(received)} de {'~' if estimated else ''}{format_bytes(total)} "
                            f"({'~' if estimated else ''}{percentage:.0f}%)"
                        )
                        self.final_update = received >= total
            super().yt_dlp_progress_hook(data)

        def ffmpeg_progress_hook(self, progress):
            self.detail_stage = "Converting"
            self.detail = f"{max(0, min(100, progress)):.0f}%"
            self.final_update = progress >= 100
            super().ffmpeg_progress_hook(progress)

    stages = {
        "Searching for song": "Buscando correspondência nos provedores de áudio",
        "Getting audio meta": "Obtendo informações do áudio",
        "Downloading": "Recebendo áudio do provedor",
        "Converting": "Convertendo com FFmpeg para MP3",
        "Embedding metadata": "Gravando tags do MP3",
        "Done": "Áudio recebido; aguardando validação local",
        "Error": "O provedor informou falha nesta faixa",
    }
    last_stage, last_text, last_update = "", "", 0.0

    def on_update(tracker, message):
        nonlocal last_stage, last_text, last_update
        current = time.monotonic()
        stage_callback(message)
        text = stages.get(message, "Processando áudio")
        if getattr(tracker, "detail_stage", "") == message and tracker.detail:
            text += " · " + tracker.detail
        final = getattr(tracker, "final_update", False) and text != last_text
        if message == last_stage and current - last_update < 1 and not final:
            return
        last_stage, last_text, last_update = message, text, current
        report(text)

    class Handler(ProgressHandler):
        def get_new_tracker(self, song):
            return Tracker(self, song)

    return Handler(simple_tui=True, update_callback=on_update)
