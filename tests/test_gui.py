"""Tk workflow regressions; skip cleanly on CI without a display."""

import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest
from test_library import P1, P2, FakeProvider

from spotano.gui import App
from spotano.provider import Cancelled


@pytest.fixture(scope="module")
def tk_session():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(tmp_path, tk_session):
    window = tk.Toplevel(tk_session)
    window.withdraw()
    instance = App(window, tmp_path)
    instance.library.provider = FakeProvider()
    instance.store.set_setting("musicbrainz", False)
    instance.library.import_playlist(P1)
    instance.library.import_playlist(P2)
    instance.refresh()
    yield instance
    instance.cancel.set()
    pump_until_done(instance)
    instance.progress.stop()
    for timer in window.tk.call("after", "info"):
        window.after_cancel(timer)
    window.destroy()


def test_checkbox_selection_controls_actions_and_survives_refresh(app):
    assert str(app.update_button["state"]) == "disabled"
    app.playlists.focus("1")
    app.toggle_playlist(SimpleNamespace(keysym="space"))
    assert app.checked_playlists == {1}
    assert str(app.update_button["state"]) == "normal"
    assert str(app.force_button["state"]) == "normal"
    assert app.force_button.cget("text") == "Baixar tudo"
    app.refresh()
    assert app.checked_playlists == {1}
    app.mark_playlists(True)
    assert app.checked_playlists == {1, 2}
    app.busy = True
    app.toggle_playlist(SimpleNamespace(keysym="space"))
    assert app.checked_playlists == {1, 2}
    app.busy = False
    app.mark_playlists(False)
    assert str(app.force_button["state"]) == "disabled"


def test_selected_sync_preview_and_logs_cross_thread_queue(app):
    captured = []
    app.review = lambda *args: captured.append(args)
    app.checked_playlists.add(2)
    app.sync(True)
    assert app.busy and str(app.update_button["state"]) == "disabled"
    deadline = time.monotonic() + 5
    while app.busy and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.busy and len(captured) == 1
    assert "1 playlist(s) selecionada(s)" in captured[0][1]
    assert "2 downloads" in captured[0][1]
    assert "Prévia pronta" in app.log_text.get("1.0", "end")
    assert str(app.force_button["state"]) == "normal"
    app.mark_playlists(False)
    assert str(app.force_button["state"]) == "disabled"


def test_layout_preview_and_custom_group_are_persisted(app, monkeypatch):
    monkeypatch.setattr("spotano.gui.simpledialog.askstring", lambda *args, **kwargs: "Viagem")
    app.mark_playlists(True)
    app.assign_group()
    app.layout.set("Pastas por grupo")
    app.change_layout()
    assert all(row["output_group"] == "Viagem" for row in app.store.playlists())
    assert "spoTano/Viagem/Música.mp3" in app.output_preview.get()
    assert app.store.setting("output_layout") == "groups"


def test_export_schedules_reorganization_and_preview(app, monkeypatch, tmp_path):
    calls = []
    marker = object()
    app.destination.set(str(tmp_path))
    monkeypatch.setattr(app.library, "reorganize", lambda: calls.append("reorganize"))
    monkeypatch.setattr(app.exporter, "preview", lambda path: calls.append(path) or marker)
    app.run = lambda work, done: calls.append((work, done))
    app.export()
    work, done = calls.pop()
    assert callable(done) and work() is marker
    assert calls == ["reorganize", tmp_path]


def test_removing_selected_playlist_also_clears_checkbox(app, monkeypatch):
    monkeypatch.setattr("spotano.gui.messagebox.askyesno", lambda *args, **kwargs: True)
    app.checked_playlists.add(1)
    app.remove_playlist()
    assert app.checked_playlists == set()
    assert len(app.store.playlists()) == 1
    assert str(app.update_button["state"]) == "disabled"


def test_minimum_window_shows_playlist_rows_and_export_action(app):
    app.root.title("spoTano - TESTE DE LAYOUT")
    app.root.geometry("1000x760")
    app.root.deiconify()
    app.root.update_idletasks()
    app.root.update()
    assert app.playlists.bbox("2"), (
        f"Second playlist must remain visible; tree height={app.playlists.winfo_height()}, "
        f"window height={app.root.winfo_height()}, first row={app.playlists.bbox('1')}"
    )
    app.tabs.select(app.export_tab)
    app.root.update_idletasks()
    export_button = next(
        c for c in app.controls if isinstance(c, ttk.Button) and c.cget("text") == "Conferir e exportar"
    )
    assert export_button.winfo_ismapped()
    assert export_button.winfo_rooty() + export_button.winfo_height() < app.log_text.winfo_rooty()
    app.toggle_logs()
    assert int(app.log_text["height"]) == 12
    app.toggle_logs()
    assert int(app.log_text["height"]) == 3


def test_batch_progress_stays_visible_across_track_messages_and_cancel(app):
    app.busy = True
    app.report({"kind": "batch_progress", "total": 200, "completed": 7, "failed": 1, "reused": 3})
    app.report("Outra faixa · Convertendo com FFmpeg para MP3 · 50%")
    app.pump()
    assert str(app.progress["mode"]) == "determinate"
    assert float(app.progress["maximum"]) == 200 and float(app.progress["value"]) == 7
    assert app.batch_status.get() == "7/200 faixas concluídas · 6 baixadas · falhas: 1 · 3 reutilizadas"
    assert "50%" in app.log_text.get("1.0", "end")
    app.cancel_operation()
    assert "6 baixadas" in app.batch_status.get()
    app.events.put(("error", Cancelled("Cancelado")))
    app.pump()
    assert not app.busy and float(app.progress["value"]) == 7


def test_refresh_only_then_explicit_partial_download_can_resume(app):
    reviews = []
    app.review = lambda *args: reviews.append(args)
    app.checked_playlists = {2}
    app.refresh_checks()
    app.update_button.invoke()
    pump_until_done(app)
    assert app.library.provider.downloads == []
    assert app.new_button.winfo_manager() == "pack"
    assert app.incremental_actions.winfo_manager() == "pack"
    assert "Nenhum áudio" in reviews[-1][1]
    app.library.validator = lambda path: None
    app.library.provider.fail.add("B" * 22)
    app.library.apply(app.library.preview(True, playlist_ids=[2], saved=True))
    app.refresh()
    assert app.update_button.cget("text") == "Atualizar selecionadas"
    assert str(app.new_button["state"]) == "normal"
    assert str(app.update_button["state"]) == "normal"
    app.library.provider.fail.clear()
    app.library.apply(app.library.preview(playlist_ids=[2], saved=True))
    app.refresh()
    assert app.incremental_actions.winfo_manager() == ""


def test_refresh_is_available_for_mixed_and_new_playlists(app):
    with app.store.connect() as db:
        db.execute("UPDATE playlists SET downloaded_at='2026-10-26T00:00:00+00:00' WHERE id=1")
    app.checked_playlists = {1}
    app.refresh()
    assert str(app.update_button["state"]) == "normal"
    app.mark_playlists(True)
    assert str(app.update_button["state"]) == "normal"
    assert str(app.force_button["state"]) == "normal"


def test_changed_playlist_controls_and_folder_explanation_fit_minimum_window(app):
    app.root.geometry("1000x760")
    app.root.deiconify()
    app.verified_playlists = {1, 2}
    app.mark_playlists(True)
    app.refresh()
    app.root.update()
    assert app.playlists.bbox("2")
    assert app.incremental_actions.winfo_ismapped()
    for button in (app.update_button, app.force_button, app.new_button, app.mirror_button):
        assert button.winfo_rooty() > app.playlists.winfo_rooty()
        assert button.winfo_rootx() + button.winfo_width() < app.root.winfo_rootx() + app.root.winfo_width()
        assert button.winfo_rooty() + button.winfo_height() < app.log_text.winfo_rooty()
    assert "biblioteca compartilhada" in app.folder_hint.get()
    assert "uma pasta separada por playlist" in app.folder_hint.get()
    folders = [app.playlists.set(i, "Pasta na exportação") for i in app.playlists.get_children()]
    assert folders[0] != folders[1]
    app.layout.set("Coleção unificada")
    app.change_layout()
    assert "todas as playlists ficam juntas" in app.folder_hint.get()
    assert all(
        app.playlists.set(i, "Pasta na exportação") == "Todas juntas" for i in app.playlists.get_children()
    )


def test_green_progress_and_folder_shortcuts_use_actual_download_and_export_paths(app, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr("spotano.gui.open_folder", opened.append)
    app.open_downloads_button.invoke()
    assert opened == [app.library.music]
    style = ttk.Style(app.root)
    assert style.lookup(app.progress.cget("style"), "background") == "#176548"
    app.sync_done({"downloaded": 2, "reused": 0, "failures": []})
    dialog = next(child for child in app.root.winfo_children() if isinstance(child, tk.Toplevel))

    def descendants(widget):
        return [child for item in widget.winfo_children() for child in [item, *descendants(item)]]

    widgets = descendants(dialog)
    assert any(isinstance(w, ttk.Label) and w.cget("text") == str(app.library.music) for w in widgets)
    next(w for w in widgets if isinstance(w, ttk.Button) and w.cget("text") == "Abrir pasta").invoke()
    assert opened[-1] == app.library.music
    dialog.destroy()
    destination = tmp_path / "USB" / "spoTano"
    app.show_saved_result("Exportação concluída", "Arquivos verificados.", destination)
    dialog = next(child for child in app.root.winfo_children() if isinstance(child, tk.Toplevel))
    next(
        w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "Abrir pasta"
    ).invoke()
    assert opened[-1] == destination


def descendants(widget):
    return [child for item in widget.winfo_children() for child in [item, *descendants(item)]]


def pump_until_done(app):
    deadline = time.monotonic() + 8
    while app.busy and time.monotonic() < deadline:
        app.root.update()
        time.sleep(0.01)
    assert not app.busy


def test_audio_source_search_and_explicit_download_persist_choice(app):
    track_id = next(iter(app.track_rows))
    app.tracks.selection_set(track_id)
    app.library.validator = lambda path: None
    app.library.provider.candidates = lambda metadata: [
        {
            "url": "https://www.youtube.com/watch?v=abcdefghijk",
            "name": "Recording",
            "artist": "Artist",
            "duration": 180,
            "score": 99,
        }
    ]
    app.audio_source()
    dialog = next(w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel))
    widgets = descendants(dialog)
    next(w for w in widgets if isinstance(w, ttk.Button) and w.cget("text") == "Pesquisar opções").invoke()
    pump_until_done(app)
    candidates = next(w for w in widgets if isinstance(w, ttk.Treeview))
    assert candidates.get_children() == ("0",)
    candidates.selection_set("0")
    candidates.event_generate("<<TreeviewSelect>>")
    app.root.update()
    next(
        w for w in widgets if isinstance(w, ttk.Button) and w.cget("text") == "Baixar esta gravação"
    ).invoke()
    pump_until_done(app)
    assert app.store.rows("SELECT url FROM audio_sources WHERE track_id=?", (track_id,))[0]["url"].endswith(
        "abcdefghijk"
    )
    assert len(list(app.library.music.rglob("*.mp3"))) == 1


def test_physical_copy_review_is_explicit_and_runs_off_ui_thread(app):
    copy = app.library.music / "Outros" / ("Old [" + "A" * 22 + "].mp3")
    copy.parent.mkdir()
    copy.write_bytes(b"old unreferenced copy")
    reviews = []
    app.review = lambda *args: reviews.append(args)
    app.review_copies()
    pump_until_done(app)
    assert len(reviews) == 1 and "1 arquivos" in reviews[0][1]
    assert copy.exists()  # Preview never deletes or quarantines.


def test_settings_save_optional_key_and_clear_only_correspondences(app, monkeypatch):
    app.lastfm_key.insert(0, "test-key")
    next(w for w in app.controls if isinstance(w, ttk.Button) and w.cget("text") == "Salvar chave").invoke()
    assert app.store.setting("lastfm_api_key") == "test-key"
    app.store.set_audio_source("A" * 22, "https://youtu.be/abcdefghijk")
    monkeypatch.setattr("spotano.gui.messagebox.askyesno", lambda *a, **kw: True)
    app.clear_matches()
    assert app.store.rows("SELECT * FROM audio_sources")  # Manual choice survives cache reset.
    app.conversion_workers.set("1")
    app.conversion_workers.event_generate("<<ComboboxSelected>>")
    assert app.store.setting("conversion_workers") == 1


def test_settings_scroll_reaches_actions_at_minimum_size(app):
    app.root.geometry("1000x760")
    app.root.deiconify()
    app.tabs.select(app.settings_tab)
    app.root.update()
    canvas = next(w for w in descendants(app.settings_tab) if isinstance(w, tk.Canvas))
    canvas.yview_moveto(1)
    app.root.update()
    help_button = next(
        w for w in app.controls if isinstance(w, ttk.Button) and w.cget("text") == "Ajuda e atualizações ↗"
    )
    assert help_button.winfo_rooty() + help_button.winfo_height() < app.log_text.winfo_rooty()
