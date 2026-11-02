"""Native Windows UI. All network and disk work runs outside the Tk thread."""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import ui
from .benchmark import (
    DEFAULT_PLAYLIST,
    PROTOCOLS,
    SCHEMA_VERSION,
    PerformanceTest,
    configurations_for,
    report_mode,
    report_ranking,
    report_recommendation,
    result_lines,
    sample_tracks,
    settings_match,
)
from .db import Store
from .exporter import LAYOUTS, Exporter, output_folders, usb_drives
from .library import Library, SyncPlan
from .options import OPTIONS, download_options, option_costs
from .paths import playlist_url
from .provider import Cancelled, SpotProvider
from .views import DesktopViews


def open_folder(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


class App(DesktopViews):
    def __init__(self, root, data_dir):
        self.root, self.store = root, Store(data_dir)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy, self.closing = False, False
        self.controls = []
        self.checked_playlists = set()
        self.checked_tracks = set()
        self.library = Library(self.store, SpotProvider(self.cancel, self.report), self.report, self.cancel)
        pending = self.store.rows("SELECT DISTINCT playlist_id,track_id FROM download_pending")
        self.checked_playlists = {row["playlist_id"] for row in pending}
        self.exporter = Exporter(self.library)
        self.build_shell()
        self.refresh()
        if pending:
            self.status.set(
                f"{len({row['track_id'] for row in pending})} faixas pendentes. "
                "Playlists marcadas para continuar em Baixar / retomar."
            )
        root.after(100, self.pump)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def open_downloads(self):
        open_folder(self.library.music)

    def open_data(self):
        open_folder(self.store.root)

    def open_help(self):
        webbrowser.open("https://github.com/Jvprotano/spoTano#readme")

    def report(self, message):
        kind = message.get("kind") if isinstance(message, dict) else "progress"
        self.events.put((kind, message))

    def update_batch_progress(self, value):
        completed, total, failed = value["completed"], value["total"], value["failed"]
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=max(total, 1), value=completed)
        self.batch_status.set(
            f"{completed}/{total} faixas concluídas · {completed - failed} baixadas · "
            f"falhas: {failed} · {value['reused']} reutilizadas"
        )

    def append_log(self, message):
        at_bottom = self.log_text.yview()[1] >= 0.99
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{datetime.now().astimezone():%H:%M:%S}] {message}\n")
        # Keep the UI responsive during long runs; a full session can be saved periodically.
        if int(self.log_text.index("end-1c").split(".")[0]) > 10000:
            self.log_text.delete("1.0", "1001.0")
        if at_bottom:
            self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def save_logs(self):
        target = filedialog.asksaveasfilename(
            title="Salvar logs visíveis", defaultextension=".log", filetypes=[("Log de texto", "*.log")]
        )
        if target:
            try:
                Path(target).write_text(self.log_text.get("1.0", "end-1c"), encoding="utf-8")
            except OSError as exc:
                messagebox.showerror("Não foi possível salvar", str(exc))

    def cancel_operation(self):
        self.cancel.set()
        self.status.set("Cancelamento solicitado. Aguardando encerramento seguro…")
        self.append_log("Cancelamento solicitado pelo usuário.")

    def toggle_logs(self):
        self.logs_visible = not self.logs_visible
        if self.logs_visible:
            self.logs_panel.grid(row=4, column=0, columnspan=2, sticky="ew")
        else:
            self.logs_panel.grid_remove()
        self.log_size.configure(text="Ocultar atividade" if self.logs_visible else "Ver atividade")

    def run(self, work, done=lambda result: None):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        for control in self.controls:
            control.configure(state="disabled")
        self.stop.configure(state="normal")
        self.batch_status.set("")
        self.progress.configure(mode="indeterminate", maximum=100, value=0)
        self.progress.start(12)
        self.status.set("Trabalhando…")
        self.append_log("Operação iniciada.")

        def task():
            try:
                result = work()
                self.events.put(("done", (done, result)))
            except Exception as exc:
                self.events.put(("error", exc))

        threading.Thread(target=task, daemon=True).start()

    def pump(self):
        try:
            for _ in range(200):
                kind, value = self.events.get_nowait()
                if kind == "batch_progress":
                    self.update_batch_progress(value)
                    continue
                if kind == "progress":
                    self.status.set(value)
                    self.append_log(value)
                    continue
                self.busy = False
                if str(self.progress["mode"]) == "indeterminate":
                    self.progress.stop()
                self.stop.configure(state="disabled")
                for control in self.controls:
                    control.configure(state="readonly" if isinstance(control, ttk.Combobox) else "normal")
                self.refresh()
                if self.closing:
                    self.root.destroy()
                    return
                if kind == "error":
                    self.status.set(
                        str(value) + " Use Baixar / retomar para continuar os downloads pendentes."
                    )
                    self.append_log(f"{'Cancelado' if isinstance(value, Cancelled) else 'Erro'}: {value}")
                    if not isinstance(value, Cancelled):
                        messagebox.showerror("Operação interrompida", str(value), parent=self.root)
                else:
                    self.status.set("Concluído.")
                    self.append_log("Etapa concluída.")
                    callback, result = value
                    callback(result)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def refresh(self):
        self.refresh_option_labels()
        selected = self.playlists.selection()
        position = self.playlists.yview()[0]
        self.playlists.delete(*self.playlists.get_children())
        playlists = self.store.playlists()
        self.playlist_rows = {str(p["id"]): p for p in playlists}
        self.checked_playlists.intersection_update(p["id"] for p in playlists)
        for row in playlists:
            local = self.store.rows(
                """SELECT COUNT(*) n FROM membership m JOIN tracks t ON t.id=m.track_id
                WHERE m.playlist_id=? AND t.path IS NOT NULL""",
                (row["id"],),
            )[0]["n"]
            row["local_count"] = local
            self.playlists.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    "☑" if row["id"] in self.checked_playlists else "☐",
                    row["name"],
                    f"{row['total'] if row['total'] is not None else row['count']} / {local}",
                    self.display_time(row["downloaded_at"])
                    if row["downloaded_at"]
                    else "Ainda não concluído",
                    *(icon for icon, _ in self.playlist_actions.values()),
                ),
            )
        tracks = self.store.tracks()
        self.summary.configure(
            text=f"{len(playlists)} playlists  ·  {sum(bool(t['path']) for t in tracks)} arquivos locais"
        )
        if selected and self.playlists.exists(selected[0]):
            self.playlists.selection_set(selected[0])
            self.playlists.focus(selected[0])
        self.playlists.yview_moveto(position)
        if playlists:
            self.playlist_empty.place_forget()
        else:
            self.playlist_empty.place(relx=0.5, rely=0.5, anchor="center")
        self.refresh_tracks()
        self.update_playlist_actions()
        self.refresh_output_preview()

    @staticmethod
    def display_time(value):
        return (
            datetime.fromisoformat(value).astimezone().strftime("%d/%m/%Y %H:%M")
            if value
            else "Ainda não lida"
        )

    def update_playlist_actions(self):
        count = len(self.checked_playlists)
        self.selection_summary.set(
            "1 playlist marcada"
            if count == 1
            else f"{count} playlists marcadas"
            if count
            else "Marque playlists para baixar"
        )
        for button in (self.new_button, self.force_button, self.mirror_button):
            button.configure(state="normal" if count and not self.busy else "disabled")
        total = len(self.playlists.get_children())
        self.playlists.heading("Marcar", text="☑" if total and count == total else "▣" if count else "☐")
        self.download_hint.set(
            "Baixar / retomar usa a lista salva e continua as pendências. "
            "Atualizar do Spotify consulta mudanças, sem baixar nem remover áudio."
        )

    def mark_playlists(self, mark):
        if self.busy:
            return
        self.checked_playlists = {int(i) for i in self.playlists.get_children()} if mark else set()
        self.refresh_checks()

    def refresh_checks(self):
        for item in self.playlists.get_children():
            self.playlists.set(item, "Marcar", "☑" if int(item) in self.checked_playlists else "☐")
        self.update_playlist_actions()

    def toggle_playlist(self, event):
        if self.busy:
            return "break"
        if event.keysym == "space":
            item = self.playlists.focus()
        else:
            if self.playlists.identify_column(event.x) != "#1":
                return
            item = self.playlists.identify_row(event.y)
        if item:
            playlist_id = int(item)
            if playlist_id in self.checked_playlists:
                self.checked_playlists.remove(playlist_id)
            else:
                self.checked_playlists.add(playlist_id)
            self.playlists.focus(item)
            self.playlists.selection_set(item)
            self.refresh_checks()
        return "break"

    def playlist_detail(self, _=None):
        selection = self.playlists.selection()
        if selection and selection[0] in self.playlist_rows:
            row = self.playlist_rows[selection[0]]
            self.playlist_info.set(
                f"{row['name']} · {row['count']} faixas disponíveis · "
                f"Consulta: {self.display_time(row['synced_at'])}. "
                f"{row['warning']} · {row['url']}"
            )

    def assign_group(self, playlist_id=None):
        selected = [playlist_id] if playlist_id is not None else sorted(self.checked_playlists)
        if self.busy or not selected:
            return
        rows = [self.playlist_rows[str(i)] for i in selected]
        names = ", ".join(row["name"] for row in rows)
        initial = rows[0]["output_group"] if len({row["output_group"] for row in rows}) == 1 else ""
        name = simpledialog.askstring(
            "Nome da pasta / grupo",
            f"Aplicar a {len(rows)} playlist(s): {names[:160]}\n\n"
            "No modo por playlist: nome da pasta individual.\n"
            "No modo por grupo: mesmo nome reúne as playlists.\n"
            "Vazio restaura o nome original / Sem grupo.\n"
            "Escolha o modo na área Exportar.",
            initialvalue=initial,
            parent=self.root,
        )
        if name is not None:
            self.store.set_output_group(selected, name)
            self.refresh()

    def change_layout(self, _=None):
        if self.busy:
            return
        key = next(k for k, label in LAYOUTS.items() if label == self.layout.get())
        self.store.set_setting("output_layout", key)
        self.refresh()

    def refresh_output_preview(self):
        playlists = self.store.playlists()
        layout = self.store.setting("output_layout", "playlists")
        folders = output_folders(playlists, layout)
        options = download_options(self.store)
        category = "/".join(
            label for key, label in (("categories", "Categoria"), ("artists", "Artista")) if options[key]
        )
        category = category + "/" if category else ""
        if layout == "unified":
            text = f"Todas as playlists juntas: spoTano/{category}Música.mp3"
        else:
            examples = list(dict.fromkeys(f"spoTano/{f}/{category}Música.mp3" for f in folders.values()))
            text = "\n".join(examples[:3]) or f"spoTano/Pasta/{category}Música.mp3"
            if len(examples) > 3:
                text += f"\n… mais {len(examples) - 3} pastas (a prévia mostrará todos os arquivos)."
        self.output_preview.set(text)
        description = {
            "unified": "Exportação: todas as playlists ficam juntas.",
            "playlists": "Exportação: uma pasta separada por playlist.",
            "groups": "Exportação: mesmo grupo = mesma pasta; sem grupo = Sem grupo.",
        }[layout]
        self.folder_hint.set("Downloads na biblioteca compartilhada. " + description)

    def refresh_tracks(self):
        self.search_timer = None
        if not hasattr(self, "tracks"):
            return
        selected = self.tracks.selection()
        position = self.tracks.yview()[0]
        self.tracks.delete(*self.tracks.get_children())
        search = self.search.get().casefold()
        self.track_rows = {}
        options = download_options(self.store)
        self.library_hint.set(
            "Faixa: altera só a selecionada. Artista: aplica às músicas do mesmo artista principal, "
            "inclusive futuras; correções individuais têm prioridade. "
            + (
                "Arquivos já baixados mudam de pasta agora, sem novo download. "
                if options["categories"]
                else "Pastas por categoria estão desativadas: a correção fica salva. Ative Categoria em "
                "Configurações → Downloads e aplique as opções aos arquivos para separá-los. "
            )
            + "Para atualizar cópias no pendrive, exporte novamente."
        )
        rows = self.store.tracks()
        self.track_total = len(rows)
        for row in rows:
            metadata = json.loads(row["metadata"])
            title = metadata["name"] + " / " + metadata["artist"]
            if search not in title.casefold():
                continue
            state = self.track_filter.get()
            if state == "Disponíveis" and not row["path"]:
                continue
            if state == "Pendentes" and not (row["status"] == "pending" or row["resume_pending"]):
                continue
            if state == "Com falha" and row["status"] != "error":
                continue
            category = row["override"] or (row["category"] if row["classified"] else "Não classificada")
            if self.category_filter.get() not in ("Todas as categorias", category):
                continue
            self.track_rows[row["id"]] = row
            status = {
                "ready": "Disponível",
                "pending": "Aguardando download",
                "error": "Falha · ver detalhes",
            }[row["status"]]
            if row["resume_pending"] and row["status"] != "error":
                status = "Download pendente"
            self.tracks.insert(
                "",
                "end",
                iid=row["id"],
                values=(
                    "☑" if row["id"] in self.checked_tracks else "☐",
                    title,
                    row["override"] or (row["category"] if row["classified"] else "Não classificada"),
                    status,
                    row["references_count"],
                ),
            )
        if selected and self.tracks.exists(selected[0]):
            self.tracks.selection_set(selected[0])
            self.tracks.focus(selected[0])
        self.tracks.yview_moveto(position)
        count = len(self.track_rows)
        self.checked_tracks.intersection_update(self.track_rows)
        self.refresh_track_checks()
        self.edit_track_button.configure(
            state="normal" if self.tracks.selection() and not self.busy else "disabled"
        )
        if count:
            self.track_empty.place_forget()
        else:
            self.track_empty_title.set(
                "Nenhuma música encontrada" if rows else "Sua biblioteca começa nas playlists"
            )
            self.track_empty_text.set(
                "Experimente outro termo ou mude os filtros de estado e categoria."
                if rows
                else "Importe uma playlist. As músicas aparecem aqui antes mesmo do download."
            )
            self.track_empty.place(relx=0.5, rely=0.5, anchor="center")

    def track_detail(self, _=None):
        selection = self.tracks.selection()
        self.edit_track_button.configure(state="normal" if selection and not self.busy else "disabled")
        if selection and selection[0] in self.track_rows:
            row = self.track_rows[selection[0]]
            self.detail.set(
                row["error"] or str(self.library.music / row["path"])
                if row["path"]
                else row["error"] or "Ainda não baixada."
            )
            self.category.set(row["override"] or "Automática")

    def add_playlist(self):
        url = self.url.get()

        def imported(playlist_id):
            self.url.set("")
            self.checked_playlists.add(playlist_id)
            self.refresh()
            self.status.set("Playlist importada e marcada. Clique em Baixar / retomar para baixar os áudios.")

        self.run(lambda: self.library.import_playlist(url), imported)

    def remove_playlist(self, playlist_id=None):
        selection = [playlist_id] if playlist_id is not None else sorted(self.checked_playlists)
        names = ", ".join(self.playlist_rows[str(i)]["name"] for i in selection)
        if (
            selection
            and not self.busy
            and messagebox.askyesno(
                "Remover playlist" if len(selection) == 1 else "Remover playlists",
                f"Remover do acompanhamento?\n\n{names}\n\nOs arquivos locais serão preservados.",
                parent=self.root,
            )
        ):
            for playlist_id in selection:
                self.store.remove_playlist(playlist_id)
            self.refresh()

    def review(self, title, summary, lines, action, confirm="Confirmar"):
        dialog = ui.dialog(self.root, title, 780, 550)
        dialog.grab_set()
        ttk.Label(dialog, text=title, font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=24, pady=(22, 8))
        ttk.Label(dialog, text=summary, wraplength=730, style="Muted.TLabel").pack(
            fill="x", padx=24, pady=(0, 18)
        )
        buttons = ttk.Frame(dialog, padding=24)
        buttons.pack(side="bottom", fill="x")
        panel = ttk.Frame(dialog, padding=(24, 0))
        panel.pack(fill="both", expand=True)
        text = tk.Text(
            panel, wrap="word", font=("Segoe UI", 10), padx=14, pady=14, bg="white", fg=ui.INK, relief="flat"
        )
        scroll = ttk.Scrollbar(panel, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", "\n".join(lines) or "Nenhuma alteração em arquivos.")
        text.configure(state="disabled")
        back = ttk.Button(buttons, text="Voltar", command=dialog.destroy)
        back.pack(side="left")

        def proceed():
            dialog.destroy()
            action()

        ttk.Button(buttons, text=confirm, style="Accent.TButton", command=proceed).pack(side="right")
        back.focus_set()

    def refresh_selected(self, playlist_id=None):
        selected = [playlist_id] if playlist_id is not None else sorted(self.checked_playlists)
        if not selected or self.busy:
            return

        def refreshed(plan):
            self.verified_playlists = getattr(self, "verified_playlists", set()) | set(selected)
            self.refresh()
            self.review(
                "Playlists consultadas",
                f"{len(plan.added)} inclusões · {len(plan.removed)} saídas · "
                f"{len(plan.downloads)} faixas para baixar\nNenhum áudio foi baixado ou removido.",
                [
                    *plan.warnings,
                    *[f"+ {p}: {name}" for p, name in plan.added],
                    *[f"− {p}: {name}" for p, name in plan.removed],
                ],
                lambda: None,
                "Fechar",
            )
            self.status.set("Consulta concluída. Escolha uma ação de download se houver pendências.")

        self.run(lambda: self.library.refresh_playlists(selected), refreshed)

    def sync(self, force, remove_missing=False):
        selected = sorted(self.checked_playlists)
        if not selected or self.busy:
            return

        def reviewed(plan):
            lines = ["Playlists incluídas nesta operação:"]
            lines += [
                f"• {snapshot['name']} · {len(snapshot['tracks'])} / "
                f"{snapshot.get('total', len(snapshot['tracks']))} faixas disponíveis"
                for _, snapshot in plan.snapshots
            ]
            lines += plan.warnings
            lines += ["\nDiferenças em relação aos downloads mantidos (primeira vez: todas são inclusões):"]
            lines += [f"+ {p}: {name}" for p, name in plan.added]
            lines += [f"− {p}: {name} (saiu da playlist)" for p, name in plan.removed]
            lines += [f"Download: {t['artist']} — {t['name']}" for t in plan.downloads]
            if remove_missing:
                lines += ["\nMover para a lixeira: " + t["path"] for t in plan.cleanup]
                lines += ["Arquivos compartilhados são preservados. Se houver falhas, nada será removido."]
            else:
                lines += ["As músicas que saíram serão mantidas na biblioteca."]
            lines += [
                "\nDownloads na biblioteca compartilhada: " + str(self.library.music),
                self.folder_hint.get(),
            ]
            self.review(
                "Conferir download e remoção" if remove_missing else "Conferir download",
                f"{len(selected)} playlist(s) selecionada(s)\n"
                f"{len(plan.downloads)} downloads · {plan.retained} reutilizadas · "
                f"{len(plan.added)} inclusões · {len(plan.removed)} saídas de playlists"
                + (f" · {len(plan.cleanup)} arquivos para a lixeira" if remove_missing else ""),
                lines,
                lambda: self.run(lambda: self.library.apply(plan), self.sync_done),
                "Baixar tudo"
                if force
                else "Baixar e remover excluídas"
                if remove_missing
                else "Baixar / retomar",
            )
            self.status.set("Prévia pronta. Confira as diferenças e confirme os downloads.")

        self.run(
            lambda: self.library.preview(
                force, playlist_ids=selected, saved=True, remove_missing=remove_missing
            ),
            reviewed,
        )

    def sync_done(self, result):
        self.show_saved_result(
            "Concluído com falhas" if result["failures"] else "Download finalizado",
            f"{result['downloaded']} baixadas · {result['reused']} reutilizadas · {len(result['failures'])} falhas\n"
            f"{result.get('removed', 0)} arquivos movidos para a lixeira."
            + (
                "\n\nUse Baixar / retomar para continuar. Os motivos estão no relatório e na Biblioteca."
                if result["failures"]
                else ""
            ),
            self.library.music,
            report_directory=result.get("run_directory"),
        )

    def show_saved_result(self, title, summary, path, report_directory=None):
        dialog = ui.dialog(self.root, title, 650)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0, 14))
        ttk.Label(body, text=summary, wraplength=600).pack(anchor="w")
        ttk.Label(body, text="Arquivos salvos em:", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(16, 4)
        )
        ttk.Label(body, text=str(path), wraplength=600).pack(anchor="w")
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(18, 0))
        ttk.Button(
            actions, text="Abrir pasta", style="Accent.TButton", command=lambda: open_folder(path)
        ).pack(side="left")
        if report_directory:
            ttk.Button(actions, text="Ver relatório", command=lambda: open_folder(report_directory)).pack(
                side="left", padx=(8, 0)
            )
        ttk.Button(actions, text="Fechar", command=dialog.destroy).pack(side="right", padx=(16, 0))
        dialog.bind("<Escape>", lambda _: dialog.destroy())

    def correct(self):
        selection = self.tracks.selection()
        if selection:
            category = self.category.get()
            self.run(
                lambda: self.library.correct_genre(selection[0], "" if category == "Automática" else category)
            )

    def correct_artist(self):
        selection = self.tracks.selection()
        if selection:
            category = self.category.get()
            metadata = json.loads(self.track_rows[selection[0]]["metadata"])
            if messagebox.askyesno(
                "Categoria do artista",
                f"Aplicar {category} às músicas de {metadata['artist']}?\n"
                "Vale para as faixas já importadas e futuras do mesmo artista principal. "
                "Os arquivos locais serão atualizados conforme as opções de download, sem baixar áudio.\n"
                "Correções individuais de faixa continuam tendo prioridade. Exporte novamente para atualizar o pendrive.",
            ):
                self.run(
                    lambda: self.library.correct_artist(
                        selection[0], "" if category == "Automática" else category
                    )
                )

    def open_metrics(self):
        open_folder(getattr(self.library, "last_run", self.store.root / "runs"))

    def test_performance(self, mode="quick"):
        if self.busy:
            return
        try:
            url = playlist_url(self.performance_playlist.get())
            size = 4 if mode == "quick" else int(self.performance_sample.get())
            if size not in (4, 8):
                raise ValueError("Escolha uma amostra de 4 ou 8 músicas.")
            baseline = (int(self.download_workers.get()), int(self.conversion_workers.get()))
            configs = configurations_for(mode, baseline)
            protocol = PROTOCOLS[mode]
            lots = len(configs) * protocol["repetitions"]
        except ValueError as exc:
            messagebox.showinfo("Teste de desempenho", str(exc), parent=self.root)
            return

        def work():
            self.report("Consultando a playlist de teste. A biblioteca pessoal será preservada.")
            snapshot = self.library.provider.playlist(url)
            tracks = sample_tracks(snapshot["tracks"], size)
            self.report(f"Amostra selecionada: {size} músicas da playlist {snapshot['name']}.")
            return PerformanceTest(self.library).run(tracks, source_playlist=url, mode=mode)

        def start():
            self.store.set_setting("performance_playlist", url)
            self.performance_playlist.set(url)
            self.run(work, self.performance_result)

        self.review(
            "Teste de desempenho",
            f"Teste {protocol['label']} · {lots} lotes · {lots * size} downloads reais · {size} músicas por lote.",
            [
                "Rápido: compara os perfis 1/1, 2/2, 3/3 e 4/4, mais sua configuração atual quando diferente. Duas rodadas por perfil."
                if mode == "quick"
                else "Completo: compara todas as 16 combinações de 1–4 downloads × 1–4 conversões, em três rodadas.",
                "Oferece uma recomendação inicial entre os perfis testados. Use o completo se quiser explorar outras combinações."
                if mode == "quick"
                else "Explora downloads e conversões separadamente; tem custo maior de tempo e tráfego.",
                "O rápido usa 32 a 40 downloads, contra 384 no completo com 8 músicas. O tempo depende da rede/provedor, sem duração garantida."
                if mode == "quick"
                else "Pode levar dezenas de minutos ou mais, conforme a rede/provedor.",
                "Acompanhe a atividade e use Cancelar quando precisar. O teste usa internet, CPU e disco.",
                "Prefira 8 músicas para coleções maiores. Use o computador ocioso e ligado à tomada.",
                "Usa as opções atuais de Categoria, Artistas e Metadados, com caches locais vazios.",
                "Áudios temporários são removidos; biblioteca, fontes manuais e caches originais são preservados.",
                "Ao final: ranking por mediana, variação entre rodadas e botão Aplicar configuração recomendada.",
                "As configurações só mudam se você aplicar a recomendação ao final.",
                "A playlist será consultada sem ser importada. A amostra é distribuída por duração e repetida em todos os lotes.",
                f"Playlist usada no teste: {url}",
            ],
            start,
            "Iniciar teste",
        )

    def save_performance_playlist(self):
        try:
            url = playlist_url(self.performance_playlist.get())
        except ValueError as exc:
            messagebox.showinfo("Playlist de teste", str(exc), parent=self.root)
            return
        self.store.set_setting("performance_playlist", url)
        self.performance_playlist.set(url)
        self.status.set("Playlist de teste salva. A biblioteca pessoal foi preservada.")

    def reset_performance_playlist(self):
        self.performance_playlist.set(DEFAULT_PLAYLIST)
        self.save_performance_playlist()

    def last_performance(self):
        path = self.store.setting("performance_report")
        if not path or not Path(path).is_file():
            messagebox.showinfo("Teste de desempenho", "Nenhum resultado salvo. Execute um teste primeiro.")
            return
        try:
            self.performance_result(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror("Não foi possível abrir o resultado", str(exc), parent=self.root)

    def performance_result(self, report):
        best = report_recommendation(report)
        mode = report_mode(report)
        ranking = report_ranking(report)
        if best:
            summary = (
                f"Recomendada no teste {PROTOCOLS[mode]['label']}: "
                f"{best['download_workers']} downloads e {best['conversion_workers']} conversões. "
                f"Mediana: {best['seconds']:.1f}s · {best['tracks_per_minute']:.1f} músicas/min.\n"
                "Entre resultados estáveis até 5% do mais rápido, prefere menos processos."
            )
        else:
            summary = (
                f"Teste {PROTOCOLS[mode]['label']} sem recomendação aplicável. Confira falhas e variação."
            )
        if mode == "quick":
            summary += "\nRecomendação inicial entre os perfis testados. Use o completo para explorar outras combinações."
        if report["status"] != "completed":
            summary = "Teste interrompido. Os resultados parciais não permitem aplicar uma recomendação."
        elif report.get("schema_version") not in (2, SCHEMA_VERSION):
            summary = (
                "Resultado do método antigo por etapas. Repita o teste para cobrir todas as combinações."
            )
        lines = result_lines(report)
        if report.get("schema_version") in (2, SCHEMA_VERSION) and not settings_match(self.store, report):
            lines.insert(
                0, "As opções de download mudaram desde o teste. Repita para medir as opções atuais."
            )
            best = None
            summary = "Resultado anterior: opções diferentes das atuais."

        def apply():
            if not best:
                return False
            if self.busy or not settings_match(self.store, report):
                messagebox.showinfo(
                    "Configuração não aplicada",
                    "Aguarde a operação atual e repita o teste se as opções de download mudaram.",
                    parent=self.root,
                )
                return False
            with self.store.connect() as db:
                for key in ("download_workers", "conversion_workers"):
                    db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(best[key])))
                self.store.bump(db)
            self.download_workers.set(str(best["download_workers"]))
            self.conversion_workers.set(str(best["conversion_workers"]))
            self.append_log(
                f"Configuração recomendada aplicada: {best['download_workers']} downloads / {best['conversion_workers']} conversões."
            )
            self.status.set(
                f"Configuração aplicada: {best['download_workers']} downloads / {best['conversion_workers']} conversões."
            )
            return True

        self.performance_dialog(
            summary,
            ranking,
            lines,
            best,
            apply,
            lambda: open_folder(report["directory"]),
        )

    def clear_matches(self):
        if messagebox.askyesno(
            "Limpar correspondências",
            "Pesquisar novamente as gravações nos próximos "
            "downloads? Áudios e fontes escolhidas manualmente serão preservados.",
        ):
            self.store.clear_audio_matches()
            self.status.set("Cache de correspondências limpo. Os áudios foram preservados.")

    def review_copies(self):
        def ready(rows):
            revision = self.store.setting("revision")
            self.review(
                "Revisar cópias antigas",
                f"{len(rows)} arquivos físicos sem vínculo serão movidos "
                "para a lixeira. Confira cada caminho antes de continuar.",
                [row["reason"] + ": " + row["path"] for row in rows],
                lambda: self.run(
                    lambda: self.library.files.quarantine(rows, revision),
                    lambda path: self.show_saved_result(
                        "Cópias preservadas na lixeira", "Revisão concluída.", path
                    ),
                ),
                "Mover cópias para lixeira",
            )

        self.run(self.library.files.review, ready)

    def audio_source(self):
        selection = self.tracks.selection()
        if not selection or self.busy:
            return
        track_id = selection[0]
        metadata = json.loads(self.track_rows[track_id]["metadata"])
        dialog = ui.dialog(self.root, "Fonte do áudio", 820, 550)
        body = ttk.Frame(dialog, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=metadata["artist"] + " — " + metadata["name"],
            wraplength=750,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            body,
            text=f"Duração de referência: {metadata.get('duration') or '?'} s. "
            "Confira artista, duração e versão antes de escolher.",
            wraplength=750,
        ).pack(anchor="w", pady=8)
        sources = self.store.rows("SELECT url FROM audio_sources WHERE track_id=?", (track_id,))
        cached = self.store.audio_match(metadata)
        url = tk.StringVar(value=sources[0]["url"] if sources else (cached or {}).get("url", ""))
        ttk.Label(body, text="URL do vídeo completo no YouTube:").pack(anchor="w")
        ttk.Entry(body, textvariable=url).pack(fill="x", pady=8)
        actions = ttk.Frame(body)
        actions.pack(side="bottom", fill="x", pady=(16, 0))
        candidates = self.tree(body, ("Faixa", "Artista", "Duração", "Confiança"), (310, 200, 90, 100))
        rows = []

        def received(result):
            if not dialog.winfo_exists():
                return
            rows[:] = result
            candidates.delete(*candidates.get_children())
            for index, row in enumerate(rows):
                candidates.insert(
                    "",
                    "end",
                    iid=str(index),
                    values=(row["name"], row["artist"], f"{row['duration']:.0f}s", f"{row['score']:.1f}"),
                )

        candidates.bind(
            "<<TreeviewSelect>>",
            lambda _: (
                url.set(rows[int(candidates.selection()[0])]["url"]) if candidates.selection() else None
            ),
        )
        ttk.Button(
            actions,
            text="Pesquisar opções",
            command=lambda: self.run(lambda: self.library.provider.candidates(metadata), received),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Abrir vídeo",
            command=lambda: webbrowser.open(url.get()) if url.get().startswith("https://") else None,
        ).pack(side="left", padx=8)

        def automatic():
            if not self.busy:
                self.store.set_audio_source(track_id, "")
                dialog.destroy()

        def download():
            if self.busy:
                return
            try:
                if not url.get().strip():
                    raise ValueError("Informe a URL ou selecione uma opção da pesquisa.")
                self.store.set_audio_source(track_id, url.get())
            except ValueError as exc:
                messagebox.showerror("URL inválida", str(exc), parent=dialog)
                return
            dialog.destroy()
            plan = SyncPlan(self.store.setting("revision"), [], downloads=[metadata])
            self.run(lambda: self.library.apply(plan), self.sync_done)

        ttk.Button(actions, text="Automática", command=automatic).pack(side="left")
        ttk.Button(actions, text="Baixar esta gravação", command=download, style="Accent.TButton").pack(
            side="right"
        )

    def import_local(self):
        selection = self.tracks.selection()
        if not selection:
            return
        source = filedialog.askopenfilename(title="Selecionar MP3 autorizado", filetypes=[("MP3", "*.mp3")])
        if not source:
            return
        metadata = json.loads(self.track_rows[selection[0]]["metadata"])
        outer = self.library.provider
        encoder = self.store.setting("conversion_encoder", "windows")

        class LocalProvider:
            def download(self, metadata, output):
                return outer.call(
                    "local",
                    {
                        "source": source,
                        "output": str(output),
                        "metadata": metadata,
                        "conversion_encoder": encoder,
                    },
                )

        lib = Library(self.store, LocalProvider(), self.report, self.cancel)
        plan = SyncPlan(self.store.setting("revision"), [], downloads=[metadata])
        self.run(lambda: lib.apply(plan), self.sync_done)

    def cleanup(self):
        tracks, revision = self.library.orphan_preview(), self.store.setting("revision")
        self.review(
            "Revisar limpeza",
            f"{len(tracks)} arquivos sem vínculo serão movidos para a lixeira local.",
            [str(t["path"]) for t in tracks],
            lambda: self.run(
                lambda: self.library.quarantine(tracks, revision),
                lambda path: messagebox.showinfo("Limpeza concluída", "Recuperação manual em:\n" + path),
            ),
            "Mover para lixeira",
        )

    def choose_export(self):
        path = filedialog.askdirectory(title="Selecionar destino da exportação")
        if path:
            self.destination.set(path)

    def detect_usb(self):
        def done(drives):
            self.drive_list = drives
            self.devices.configure(
                values=[
                    f"{d['path']}  {d.get('label') or 'USB'}  ·  {d.get('filesystem') or '?'}" for d in drives
                ]
            )
            if drives:
                self.devices.current(0)
                self.destination.set(drives[0]["path"])
            else:
                messagebox.showinfo(
                    "Pendrives", "Nenhum pendrive detectado. Você pode escolher uma pasta manualmente."
                )

        self.run(usb_drives, done)

    def export(self):
        destination = self.destination.get()
        if not destination:
            messagebox.showinfo("Escolha o destino", "Selecione uma pasta ou detecte seu pendrive.")
            return
        self.store.set_setting("export_destination", destination)

        def reviewed(plan):
            self.review(
                "Conferir exportação",
                f"{len(plan.copy)} cópias · {plan.reused} reutilizadas · "
                f"{len(plan.remove)} arquivos para lixeira · {plan.bytes_required / 1024 / 1024:.1f} MB\n{plan.root}",
                ["Copiar: " + r for r in plan.copy]
                + ["Mover para .spotano-trash: " + r for r in plan.remove],
                lambda: self.run(
                    lambda: self.exporter.apply(plan),
                    lambda path: self.show_saved_result(
                        "Exportação concluída", "Arquivos verificados.", path
                    ),
                ),
                "Exportar",
            )

        def preview():
            self.library.reorganize()
            return self.exporter.preview(destination)

        self.run(preview, reviewed)

    def refresh_option_labels(self):
        if not hasattr(self, "option_labels"):
            return
        costs = option_costs()
        for key in OPTIONS:
            self.option_labels[key].set(costs[key])
        selected = {key: variable.get() for key, variable in self.option_vars.items()}
        folders = (["Categoria"] if selected["categories"] else []) + (
            ["Artista"] if selected["artists"] else []
        )
        path = "/".join([*folders, "Artista - Música [ID].mp3"])
        mode = "As alterações valem no próximo download ou exportação."
        if any(selected.values()):
            chosen = [
                name
                for key, name in (
                    ("categories", "categoria"),
                    ("artists", "artistas"),
                    ("metadata", "metadados"),
                )
                if selected[key]
            ]
            self.options_caption.set("Download personalizado · " + ", ".join(chosen))
        else:
            self.options_caption.set("Download simples · músicas juntas, sem tags extras")
        self.option_summary.set(f"{mode}\nPasta: Music/{path}")

    def save_download_options(self):
        self.store.set_setting("download_options", {key: var.get() for key, var in self.option_vars.items()})
        self.refresh_option_labels()
        self.refresh_output_preview()

    def select_options(self, enabled):
        for variable in self.option_vars.values():
            variable.set(enabled)
        self.save_download_options()

    def reclassify(self):
        self.run(self.library.reclassify)

    def backup(self):
        target = filedialog.asksaveasfilename(
            title="Backup do catálogo (músicas não incluídas)",
            defaultextension=".sqlite3",
            filetypes=[("SQLite", "*.sqlite3")],
        )
        if target:
            if Path(target).resolve() == self.store.path:
                messagebox.showerror("Destino inválido", "Escolha um arquivo diferente do catálogo em uso.")
                return
            self.run(lambda: self.store.backup(Path(target)))

    def diagnostics(self):
        self.run(
            lambda: self.library.provider.call("diagnostics"),
            lambda data: messagebox.showinfo(
                "Diagnóstico",
                "\n".join(f"{k}: {v}" for k, v in data.items()) + "\n\nDados: " + str(self.store.root),
            ),
        )

    def history(self):
        rows = self.store.rows("SELECT * FROM history ORDER BY id DESC LIMIT 100")
        window = ui.dialog(self.root, "Histórico de operações · spoTano", 820, 530)
        body = ttk.Frame(window, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Histórico de operações", font=("Segoe UI", 19, "bold")).pack(
            anchor="w", pady=(0, 16)
        )
        text = tk.Text(
            body, wrap="word", padx=14, pady=14, font=("Segoe UI", 10), bg="white", fg=ui.INK, relief="flat"
        )
        scroll = ttk.Scrollbar(body, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        for row in rows:
            text.insert("end", f"{row['time']} UTC · {row['action']}\n{row['detail']}\n\n")
        text.configure(state="disabled")

    def close(self):
        if self.busy:
            self.closing = True
            self.cancel.set()
            self.status.set("Encerrando a operação com segurança…")
        else:
            self.root.destroy()
