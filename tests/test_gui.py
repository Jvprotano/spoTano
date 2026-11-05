"""Tk workflow regressions; skip cleanly on CI without a display."""

import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import pytest
from test_library import P1, P2, FakeProvider

from spotano import ui
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
    # Let callbacks registered by child widgets clean up their own Tcl commands.
    window.update_idletasks()
    for timer in window.tk.call("after", "info"):
        window.after_cancel(timer)
    window.destroy()


def test_checkbox_selection_controls_actions_and_survives_refresh(app):
    assert str(app.force_button["state"]) == "disabled"
    app.playlists.focus("1")
    app.toggle_playlist(SimpleNamespace(keysym="space"))
    assert app.checked_playlists == {1}
    assert str(app.mirror_button["state"]) == "normal"
    assert str(app.force_button["state"]) == "normal"
    assert str(app.new_button["state"]) == "normal"
    assert app.new_button.cget("text") == "Atualizar (Apenas Adiciona novos)"
    assert app.mirror_button.cget("text") == "Atualizar (Adiciona e Remove)"
    assert not app.resume_button.winfo_manager()
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
    assert str(app.new_button["state"]) == "disabled"


def test_header_checkbox_toggles_all_and_shows_partial_state(app):
    app.root.deiconify()
    app.root.update()
    assert app.playlists.heading("Marcar", "text") == "☐"
    app.playlists.focus("1")
    app.toggle_playlist(SimpleNamespace(keysym="space"))
    assert app.playlists.heading("Marcar", "text") == "▣"
    # Exercise the native heading binding, not just the callback.
    _, first_y, _, _ = app.playlists.bbox("1")
    for expected in ({1, 2}, set()):
        app.playlists.event_generate("<ButtonPress-1>", x=22, y=first_y // 2)
        app.playlists.event_generate("<ButtonRelease-1>", x=22, y=first_y // 2)
        app.root.update()
        assert app.checked_playlists == expected
    app.playlists.event_generate("<Control-a>")
    app.root.update()
    assert app.checked_playlists == {1, 2}
    assert app.playlists.heading("Marcar", "text") == "☑"
    app.mark_playlists(False)
    app.run(lambda: None)
    app.toggle_all_playlists()
    assert not app.checked_playlists
    assert all(str(b["state"]) == "disabled" for b in (app.new_button, app.force_button, app.mirror_button))
    pump_until_done(app)
    for row in app.store.playlists():
        app.store.remove_playlist(row["id"])
    app.refresh()
    app.toggle_all_playlists()
    assert not app.checked_playlists and app.playlists.heading("Marcar", "text") == "☐"


@pytest.mark.parametrize("action", ["Atualizar", "Detalhes", "Pasta", "Remover"])
def test_row_icons_target_clicked_playlist_and_preserve_batch_selection(app, monkeypatch, action):
    calls = []
    monkeypatch.setattr(app, "refresh_selected", lambda row: calls.append(("Atualizar", row)))
    monkeypatch.setattr(app, "assign_group", lambda row: calls.append(("Pasta", row)))
    monkeypatch.setattr(app, "remove_playlist", lambda row: calls.append(("Remover", row)))
    monkeypatch.setattr(app, "playlist_details_dialog", lambda: calls.append(("Detalhes", 2)))
    app.checked_playlists = {1}
    app.refresh_checks()
    app.root.deiconify()
    app.root.update()
    x, y, width, height = app.playlists.bbox("2", action)
    x, y = x + width // 2, y + height // 2
    assert app.playlist_tooltip(x, y)
    app.playlists.event_generate("<Button-1>", x=x, y=y)
    assert calls == [(action, 2)]
    assert app.playlists.selection() == ("2",)
    assert app.checked_playlists == {1}
    app.busy = True
    app.playlist_row_action(action, "1")
    assert calls == [(action, 2)]
    app.busy = False


def test_row_group_and_removal_do_not_modify_other_marked_playlists(app, monkeypatch):
    app.mark_playlists(True)
    monkeypatch.setattr("spotano.gui.simpledialog.askstring", lambda *args, **kwargs: "Viagem")
    app.playlist_row_action("Pasta", "2")
    assert [p["output_group"] for p in app.store.playlists()] == ["", "Viagem"]
    prompts = []
    monkeypatch.setattr(
        "spotano.gui.messagebox.askyesno", lambda title, text, **kw: prompts.append(text) or False
    )
    app.playlist_row_action("Remover", "2")
    assert len(app.store.playlists()) == 2
    assert app.playlist_rows["2"]["name"] in prompts[0]
    monkeypatch.setattr("spotano.gui.messagebox.askyesno", lambda *args, **kwargs: True)
    app.playlist_row_action("Remover", "2")
    assert [p["id"] for p in app.store.playlists()] == [1]
    assert app.checked_playlists == {1}


@pytest.mark.parametrize(
    "button, force, remove",
    [("new_button", False, False), ("force_button", True, False), ("mirror_button", False, True)],
)
def test_download_buttons_are_visible_and_keep_their_operation(app, monkeypatch, button, force, remove):
    app.root.deiconify()
    app.root.update()
    control = getattr(app, button)
    assert control.winfo_ismapped() and str(control["state"]) == "disabled"
    calls = []
    monkeypatch.setattr(
        app, "sync", lambda force, remove_missing=False: calls.append((force, remove_missing))
    )
    app.mark_playlists(True)
    control.invoke()
    assert calls == [(force, remove)]
    labels = [w.cget("text") for w in descendants(app.playlist_tab) if isinstance(w, ttk.Button)]
    assert not any(text in labels for text in ("Mais ações", "Marcar todas", "Desmarcar", "Personalizar…"))


def test_library_explains_correction_scope_and_shows_tracks_before_download(app):
    assert len(app.tracks.get_children()) == 2
    assert "Pastas por categoria estão desativadas" in app.library_hint.get()
    assert all(row["path"] is None for row in app.store.tracks())
    app.store.set_setting("download_options", {"categories": True})
    app.refresh_tracks()
    assert "mudam de pasta agora" in app.library_hint.get()
    calls = []
    app.library.correct_genre = lambda *args: calls.append(args)
    app.run = lambda work: work()
    app.tracks.selection_set("A" * 22)
    app.track_detail()
    app.track_editor()
    dialog = next(w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel))
    app.category.set("Pop")
    next(
        w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "Aplicar à faixa"
    ).invoke()
    assert calls == [("A" * 22, "Pop")]


def test_category_filter_combines_with_search_and_state(app):
    app.library.correct_genre("A" * 22, "Pop")
    app.category_filter.set("Pop")
    app.refresh_tracks()
    assert app.tracks.get_children() == ("A" * 22,)
    app.track_filter.set("Disponíveis")
    app.refresh_tracks()
    assert not app.tracks.get_children()
    app.track_filter.set("Todas")
    app.category_filter.set("Não classificada")
    app.refresh_tracks()
    assert app.tracks.get_children() == ("B" * 22,)
    app.search.set("no matching track")
    app.refresh_tracks()
    assert not app.tracks.get_children()


def test_track_checks_filter_scope_and_busy_guard(app):
    app.tracks.focus("A" * 22)
    app.toggle_track()
    assert app.checked_tracks == {"A" * 22}
    assert app.tracks.heading("Marcar", "text") == "▣"
    app.refresh_tracks()
    assert app.checked_tracks == {"A" * 22}
    app.toggle_all_tracks()
    assert app.checked_tracks == {"A" * 22, "B" * 22}
    app.busy = True
    app.toggle_all_tracks()
    app.toggle_track()
    assert len(app.checked_tracks) == 2
    app.busy = False
    app.library.correct_genre("A" * 22, "Pop")
    app.category_filter.set("Pop")
    app.refresh_tracks()
    assert app.checked_tracks == {"A" * 22}
    app.toggle_all_tracks()
    assert not app.checked_tracks
    assert str(app.bulk_track_button["state"]) == "disabled"


def test_bulk_editor_applies_explicit_checked_snapshot(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app.library, "correct_categories", lambda *args, **kw: calls.append((args, kw)))
    app.run = lambda work: work()
    app.toggle_all_tracks()
    app.bulk_track_editor()
    dialog = next(w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel))
    combo = next(w for w in descendants(dialog) if isinstance(w, ttk.Combobox))
    button = next(
        w for w in descendants(dialog) if isinstance(w, ttk.Button) and w.cget("text") == "Aplicar às faixas"
    )
    assert str(button["state"]) == "disabled"
    combo.set("Pop")
    combo.event_generate("<<ComboboxSelected>>")
    button.invoke()
    assert calls == [((("A" * 22, "B" * 22), "Pop"), {"artists": False})]


def test_library_native_checkboxes_and_minimum_layout(app):
    app.root.deiconify()
    app.root.geometry("1000x760")
    app.tabs.select(app.library_tab)
    app.root.update()
    x, y, width, height = app.tracks.bbox("A" * 22, "Marcar")
    app.tracks.event_generate("<ButtonPress-1>", x=x + width // 2, y=y + height // 2)
    app.tracks.event_generate("<ButtonRelease-1>", x=x + width // 2, y=y + height // 2)
    app.root.update()
    assert app.checked_tracks == {"A" * 22}
    app.tracks.event_generate("<ButtonPress-1>", x=x + width // 2, y=y // 2)
    app.tracks.event_generate("<ButtonRelease-1>", x=x + width // 2, y=y // 2)
    app.root.update()
    assert len(app.checked_tracks) == 2
    assert app.category_filter.winfo_ismapped()
    assert app.bulk_track_button.winfo_ismapped()
    for control in (app.category_filter, app.bulk_track_button, app.edit_track_button):
        assert (
            control.winfo_rootx() + control.winfo_width() <= app.root.winfo_rootx() + app.root.winfo_width()
        )


def test_reopening_marks_playlists_with_saved_downloads_for_resume(app):
    with app.store.connect() as db:
        db.execute("INSERT INTO download_pending VALUES(2,?)", ("B" * 22,))
    window = tk.Toplevel(app.root)
    window.withdraw()
    restarted = App(window, app.store.root)
    try:
        assert restarted.checked_playlists == {2}
        assert "1 faixas pendentes" in restarted.status.get()
        assert str(restarted.new_button["state"]) == "normal"
        assert restarted.resume_button.winfo_manager() == "pack"
        assert str(restarted.resume_button["state"]) == "normal"
        assert "Use Retomar" in restarted.status.get()
        assert restarted.tracks.set("B" * 22, "Estado") == "Download pendente"
    finally:
        window.destroy()


def test_resume_appears_after_interruption_and_targets_pending_playlists(app, monkeypatch):
    reviews = []
    app.review = lambda *args: reviews.append(args)
    app.show_saved_result = lambda *args, **kwargs: None
    app.mark_playlists(True)
    assert not app.resume_button.winfo_manager()  # Importing alone is not an interrupted run.
    app.library.validator = lambda path: None
    app.library.apply(app.library.preview(playlist_ids=[2], saved=True))
    app.library.provider.downloads.clear()
    with app.store.connect() as db:
        db.execute("INSERT INTO download_pending VALUES(2,?)", ("B" * 22,))
    app.busy = True
    app.events.put(("error", Cancelled("Cancelado")))
    app.pump()
    assert app.resume_button.winfo_manager() == "pack"
    assert "Use Retomar" in app.status.get()
    app.checked_playlists = {1}  # Resume must not download an unrelated checked playlist.
    app.refresh_checks()
    monkeypatch.setattr(
        app.library.provider, "playlist", lambda url: pytest.fail("Resume must use saved metadata")
    )
    app.resume_button.invoke()
    assert str(app.resume_button["state"]) == "disabled"
    pump_until_done(app)
    assert reviews[-1][0] == "Conferir retomada"
    assert reviews[-1][-1] == "Retomar"
    assert app.library.provider.downloads == []  # A preview still requires confirmation.
    reviews[-1][3]()
    pump_until_done(app)
    assert app.library.provider.downloads == ["B" * 22]
    assert app.checked_playlists == {1}
    assert not app.resume_button.winfo_manager()
    app.resume_button.invoke()
    assert not app.busy


def performance_report(app):
    from spotano.benchmark import CONFIGURATIONS, REPETITIONS, report_recommendation
    from spotano.options import download_options

    report = {
        "schema_version": 2,
        "status": "completed",
        "created_at": "2026-10-30",
        "repetitions": REPETITIONS,
        "sample": [dict(song_id=str(i)) for i in range(4)],
        "options": download_options(app.store),
        "workload": {
            "musicbrainz": False,
            "lastfm_enabled": False,
            "output_layout": "playlists",
            "conversion_encoder": app.store.setting("conversion_encoder", "windows"),
        },
        "rows": [
            dict(
                download_workers=d,
                conversion_workers=c,
                round=r,
                seconds=10 if (d, c) == (3, 1) else 20,
                downloaded=4,
                total=4,
                failures=[],
            )
            for d, c in CONFIGURATIONS
            for r in range(1, REPETITIONS + 1)
        ],
        "directory": str(app.store.root),
    }
    report["recommendation"] = report_recommendation(report)
    return report


def test_performance_suggestion_only_changes_both_fields_when_applied(app, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        app,
        "performance_dialog",
        lambda summary, ranking, lines, best, action, open_report: captured.update(
            action=action,
            best=best,
            ranking=ranking,
            summary=summary,
        ),
    )
    before = app.store.setting("download_workers")
    app.performance_result(performance_report(app))
    assert captured["best"]["download_workers"] == 3
    assert captured["ranking"][0]["seconds"] == 10
    assert app.store.setting("download_workers") == before
    captured["action"]()
    assert app.store.setting("download_workers") == 3 and app.download_workers.get() == "3"
    assert app.store.setting("conversion_workers") == 1 and app.conversion_workers.get() == "1"
    assert "Configuração aplicada" in app.status.get()


def test_performance_stale_workload_blocks_applying_even_after_dialog_opened(app, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        app,
        "performance_dialog",
        lambda summary, ranking, lines, best, action, open_report: captured.update(best=best, action=action),
    )
    monkeypatch.setattr("spotano.gui.messagebox.showinfo", lambda *args, **kwargs: None)
    report = performance_report(app)
    app.performance_result(report)
    before = app.store.setting("download_workers")
    app.store.set_setting("musicbrainz", True)
    assert captured["action"]() is False
    assert app.store.setting("download_workers") == before
    app.performance_result(report)
    assert captured["best"] is None


def test_performance_dialog_displays_ranked_results_and_explicit_apply_button(app):
    report = performance_report(app)
    app.performance_result(report)
    window = next(w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel))

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    widgets = list(descendants(window))
    table = next(w for w in widgets if isinstance(w, ttk.Treeview))
    assert len(table.get_children()) == 16
    assert table.item(table.get_children()[0], "values")[1:3] == ("3", "1")
    button = next(
        w
        for w in widgets
        if isinstance(w, ttk.Button) and w.cget("text") == "Aplicar configuração recomendada"
    )
    assert str(button.cget("state")) == "normal"
    button.invoke()
    assert app.store.setting("download_workers") == 3
    assert app.store.setting("conversion_workers") == 1
    assert not window.winfo_exists()


@pytest.mark.parametrize("mode, size, downloads", [("quick", 4, 32), ("complete", 8, 384)])
def test_performance_uses_default_playlist_without_imported_playlists(
    app, monkeypatch, mode, size, downloads
):
    from spotano.benchmark import DEFAULT_PLAYLIST

    for playlist in app.store.playlists():
        app.store.remove_playlist(playlist["id"])
    app.checked_playlists.clear()
    before_tracks = app.store.tracks()
    tracks = [dict(song_id=f"{i:022d}", name=str(i), artist="Own") for i in range(12)]
    calls = []
    app.library.provider.playlist = lambda url: calls.append(url) or {"name": "Test", "tracks": tracks}
    monkeypatch.setattr(
        "spotano.gui.PerformanceTest.run",
        lambda self, sample, source_playlist, mode: calls.append((sample, source_playlist, mode)) or {},
    )
    captured = {}
    monkeypatch.setattr(
        app,
        "review",
        lambda title, summary, lines, action, confirm: captured.update(action=action, summary=summary),
    )
    monkeypatch.setattr(app, "run", lambda work, done: work())
    assert app.performance_playlist.get() == DEFAULT_PLAYLIST
    app.test_performance() if mode == "quick" else app.test_performance("complete")
    assert not calls
    assert f"{downloads} downloads" in captured["summary"]
    captured["action"]()
    assert calls[0] == DEFAULT_PLAYLIST
    assert len(calls[1][0]) == size and calls[1][1:] == (DEFAULT_PLAYLIST, mode)
    assert not app.store.playlists() and app.store.tracks() == before_tracks
    app.performance_playlist.set(P1 + "?si=tracking")
    app.save_performance_playlist()
    assert app.store.setting("performance_playlist") == P1
    app.reset_performance_playlist()
    assert app.store.setting("performance_playlist") == DEFAULT_PLAYLIST


def test_performance_quick_result_is_identified_and_can_be_applied(app, monkeypatch):
    from spotano.benchmark import SCHEMA_VERSION, configurations_for

    report = performance_report(app)
    report.update(schema_version=SCHEMA_VERSION, mode="quick", repetitions=2, baseline=[3, 1])
    report["rows"] = [
        r
        for r in report["rows"]
        if (r["download_workers"], r["conversion_workers"]) in configurations_for("quick", [3, 1])
        and r["round"] <= 2
    ]
    captured = {}
    monkeypatch.setattr(
        app,
        "performance_dialog",
        lambda summary, ranking, lines, best, action, open_report: captured.update(
            summary=summary, ranking=ranking, best=best, action=action
        ),
    )
    app.performance_result(report)
    assert "teste rápido" in captured["summary"] and "Recomendação inicial" in captured["summary"]
    assert len(captured["ranking"]) == 5
    assert captured["ranking"][0]["initial_configuration"] is True
    assert captured["action"]() is True
    assert app.store.setting("download_workers") == 3 and app.store.setting("conversion_workers") == 1


def test_selected_sync_preview_and_logs_cross_thread_queue(app):
    captured = []
    app.review = lambda *args: captured.append(args)
    app.checked_playlists.add(2)
    app.sync(True)
    assert app.busy and str(app.force_button["state"]) == "disabled"
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
    assert calls == ["reorganize", str(tmp_path)]


def test_removing_selected_playlist_also_clears_checkbox(app, monkeypatch):
    monkeypatch.setattr("spotano.gui.messagebox.askyesno", lambda *args, **kwargs: True)
    app.checked_playlists.add(1)
    app.remove_playlist()
    assert app.checked_playlists == set()
    assert len(app.store.playlists()) == 1
    assert str(app.force_button["state"]) == "disabled"


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
    assert export_button.winfo_rooty() + export_button.winfo_height() <= app.activity.winfo_rooty()
    app.toggle_logs()
    app.root.update_idletasks()
    assert app.logs_panel.winfo_ismapped()
    app.toggle_logs()
    app.root.update_idletasks()
    assert not app.logs_panel.winfo_ismapped()


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
    app.playlist_row_action("Atualizar", "2")
    pump_until_done(app)
    assert app.library.provider.downloads == []
    assert app.new_button.winfo_manager() == "pack"
    assert app.mirror_button.winfo_manager() == "pack"
    assert "Nenhum áudio" in reviews[-1][1]
    app.library.validator = lambda path: None
    app.library.provider.fail.add("B" * 22)
    app.library.apply(app.library.preview(True, playlist_ids=[2], saved=True))
    app.refresh()
    assert str(app.new_button["state"]) == "normal"
    assert str(app.mirror_button["state"]) == "normal"
    app.library.provider.fail.clear()
    assert app.resume_button.winfo_manager() == "pack"
    app.library.apply(app.library.preview(playlist_ids=[2], saved=True))
    app.refresh()
    assert app.mirror_button.winfo_manager() == "pack"
    assert str(app.new_button["state"]) == "normal"
    assert not app.resume_button.winfo_manager()


def test_refresh_is_available_for_mixed_and_new_playlists_without_marking(app, monkeypatch):
    calls = []
    monkeypatch.setattr(app.library, "refresh_playlists", lambda ids: calls.append(ids))
    monkeypatch.setattr(app, "run", lambda work, done: work())
    with app.store.connect() as db:
        db.execute("UPDATE playlists SET downloaded_at='2026-10-26T00:00:00+00:00' WHERE id=1")
    app.checked_playlists.clear()
    app.refresh()
    app.playlist_row_action("Atualizar", "1")
    app.playlist_row_action("Atualizar", "2")
    assert calls == [[1], [2]]
    assert not app.checked_playlists


def test_changed_playlist_controls_and_folder_explanation_fit_minimum_window(app):
    app.root.geometry("1000x760")
    app.root.deiconify()
    app.verified_playlists = {1, 2}
    with app.store.connect() as db:
        db.execute("INSERT INTO download_pending VALUES(2,?)", ("B" * 22,))
    app.mark_playlists(True)
    app.refresh()
    app.root.update()
    assert app.playlists.bbox("2")
    for button in (app.force_button, app.new_button, app.mirror_button, app.resume_button):
        assert button.winfo_ismapped()
        assert button.winfo_rootx() >= app.playlists.winfo_rootx()
        assert button.winfo_rooty() > app.playlists.winfo_rooty()
        assert button.winfo_rootx() + button.winfo_width() < app.root.winfo_rootx() + app.root.winfo_width()
        assert button.winfo_rooty() + button.winfo_height() <= app.activity.winfo_rooty()
    assert "biblioteca compartilhada" in app.folder_hint.get()
    assert "uma pasta separada por playlist" in app.folder_hint.get()
    for column in app.playlist_actions:
        x, y, width, height = app.playlists.bbox("2", column)
        assert x + width <= app.playlists.winfo_width()
        assert height > 0
    app.layout.set("Coleção unificada")
    app.change_layout()
    assert "todas as playlists ficam juntas" in app.folder_hint.get()


def test_green_progress_and_folder_shortcuts_use_actual_download_and_export_paths(app, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr("spotano.gui.open_folder", opened.append)
    app.open_downloads_button.invoke()
    assert opened == [app.library.music]
    style = ttk.Style(app.root)
    assert style.lookup(app.progress.cget("style"), "background") == ui.ACCENT
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


def test_download_result_opens_run_report_without_changing_music_shortcut(app, monkeypatch, tmp_path):
    opened = []
    monkeypatch.setattr("spotano.gui.open_folder", opened.append)
    directory = str(tmp_path / "runs" / "test")
    app.sync_done(
        {"downloaded": 1, "reused": 0, "failures": [("Song", "No match")], "run_directory": directory}
    )
    dialog = next(child for child in app.root.winfo_children() if isinstance(child, tk.Toplevel))
    buttons = {w.cget("text"): w for w in descendants(dialog) if isinstance(w, ttk.Button)}
    buttons["Ver relatório"].invoke()
    assert opened[-1] == directory
    buttons["Abrir pasta"].invoke()
    assert opened[-1] == app.library.music


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


def test_inline_download_options_save_and_lock_during_operations(app):
    checks = [
        w
        for w in descendants(app.settings_tab)
        if isinstance(w, ttk.Checkbutton)
        and w.cget("text").startswith(("Categoria ·", "Artistas ·", "Metadados ·"))
    ]
    assert len(checks) == 3
    assert not any("Personalizar download" in str(w.cget("text")) for w in app.controls)
    checks[0].invoke()
    assert app.store.setting("download_options") == {
        "categories": True,
        "artists": False,
        "metadata": False,
    }
    assert "Music/Categoria/" in app.option_summary.get()
    assert "categoria" in app.options_caption.get()
    assert "/Categoria/Música.mp3" in app.output_preview.get()
    select_all = next(
        w
        for w in descendants(app.settings_tab)
        if isinstance(w, ttk.Button) and w.cget("text") == "Marcar tudo"
    )
    select_all.invoke()
    assert all(app.store.setting("download_options").values())
    app.run(lambda: None)
    assert all(str(w["state"]) == "disabled" for w in [*checks, select_all])
    checks[0].invoke()
    assert all(app.store.setting("download_options").values())
    pump_until_done(app)
    assert all(str(w["state"]) == "normal" for w in [*checks, select_all])
    next(
        w
        for w in descendants(app.settings_tab)
        if isinstance(w, ttk.Button) and w.cget("text") == "Desmarcar tudo"
    ).invoke()
    assert not any(app.store.setting("download_options").values())
    assert "Download simples" in app.options_caption.get()


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


def test_conversion_encoder_choice_is_persisted(app):
    app.conversion_encoder.set("Tradicional · LAME")
    app.conversion_encoder.event_generate("<<ComboboxSelected>>")
    app.root.update()
    assert app.store.setting("conversion_encoder") == "lame"
    app.conversion_encoder.set("Rápida · Windows")
    app.conversion_encoder.event_generate("<<ComboboxSelected>>")
    app.root.update()
    assert app.store.setting("conversion_encoder") == "windows"
