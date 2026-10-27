from spotano.downloads import saved_song
from spotano.progress import download_progress


def tracker(events):
    handler = download_progress(events.append)
    handler.set_song_count(1)
    return handler.get_new_tracker(saved_song({"song_id": "A" * 22, "artist": "Test", "name": "Test"}))


def test_transfer_reports_actual_bytes_and_distinguishes_unknown_and_estimated_totals(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("spotano.progress.time.monotonic", lambda: clock[0])
    events = []
    progress = tracker(events)
    progress.notify_searching()
    assert "%" not in events[-1]
    progress.yt_dlp_progress_hook({"status": "downloading", "downloaded_bytes": 1024})
    assert events[-1].endswith("1,00 KiB recebidos") and "%" not in events[-1]
    clock[0] += 2
    progress.yt_dlp_progress_hook(
        {"status": "downloading", "downloaded_bytes": 2048, "total_bytes_estimate": 4096}
    )
    assert events[-1].endswith("2,00 KiB de ~4,00 KiB (~50%)")
    clock[0] += 2
    progress.yt_dlp_progress_hook({"status": "downloading", "downloaded_bytes": 3072, "total_bytes": 4096})
    assert events[-1].endswith("3,00 KiB de 4,00 KiB (75%)")
    progress.yt_dlp_progress_hook({"status": "downloading", "downloaded_bytes": 4096, "total_bytes": 4096})
    assert events[-1].endswith("4,00 KiB de 4,00 KiB (100%)")


def test_conversion_uses_ffmpeg_percentage_and_does_not_mark_file_as_saved(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("spotano.progress.time.monotonic", lambda: clock[0])
    events = []
    progress = tracker(events)
    progress.ffmpeg_progress_hook(0)
    assert events[-1].endswith("MP3 · 0%")
    progress.ffmpeg_progress_hook(10)
    assert len(events) == 1  # Throttle frequent callbacks, but never hide completion.
    clock[0] += 2
    progress.ffmpeg_progress_hook(50)
    assert events[-1].endswith("MP3 · 50%")
    progress.ffmpeg_progress_hook(100)
    assert events[-1].endswith("MP3 · 100%")
    progress.notify_conversion_complete()
    assert events[-1] == "Gravando tags do MP3"
    progress.notify_complete()
    assert events[-1] == "Áudio recebido; aguardando validação local"


def test_sdk_error_preserves_root_cause_without_credentials_or_signed_urls():
    errors = []
    handler = download_progress(lambda message: None, error_callback=errors.append)
    progress = handler.get_new_tracker(saved_song({"song_id": "A" * 22, "artist": "Test", "name": "Test"}))
    root = ValueError("HTTP 403 api_key=fake-private https://cdn.invalid/audio?signature=fake-signed")
    wrapped = RuntimeError("Opaque audio provider error")
    wrapped.__cause__ = root
    progress.notify_error("internal traceback", wrapped, True)
    assert errors[0].startswith("ValueError: HTTP 403")
    assert "fake-private" not in errors[0] and "fake-signed" not in errors[0]
