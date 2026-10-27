"""Native Windows UI. All network and disk work runs outside the Tk thread."""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .db import Store
from .exporter import Exporter, usb_drives
from .genres import CATEGORIES
from .library import Library, SyncPlan
from .options import OPTIONS, download_options, option_costs
from .provider import Cancelled, SpotProvider


def open_folder(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


class App:
    def __init__(self, root, data_dir):
        self.root, self.store = root, Store(data_dir)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy, self.closing = False, False
        self.controls = []
        self.library = Library(self.store, SpotProvider(self.cancel), self.report, self.cancel)
        self.exporter = Exporter(self.library)
        root.title("spoTano · Sua música, com você")
        root.geometry("1120x780")
        root.minsize(920, 640)
        root.configure(bg="#f4f6f4")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#f4f6f4", foreground="#16352c")
        style.configure("TButton", padding=(13, 9), background="#e5ede8")
        style.configure("Accent.TButton", background="#176548", foreground="white")
        style.map("Accent.TButton", background=[("active", "#207e5a"), ("disabled", "#a2b8ab")])
        style.configure("Treeview", rowheight=32, fieldbackground="white", background="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("TNotebook.Tab", padding=(18, 11))
        head = ttk.Frame(root, padding=(26, 20))
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="spoTano", font=("Segoe UI", 28, "bold")).pack(side="left")
        ttk.Label(head, text="SUA MÚSICA, COM VOCÊ", font=("Segoe UI", 10), foreground="#63786c").pack(
            side="left", padx=20, pady=(12, 0)
        )
        self.summary = ttk.Label(head, text="")
        self.summary.pack(side="right")
        self.tabs = ttk.Notebook(root)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=24)
        self.playlist_tab, self.library_tab, self.export_tab, self.settings_tab = [
            ttk.Frame(self.tabs, padding=18) for _ in range(4)
        ]
        for frame, title in zip(
            (self.playlist_tab, self.library_tab, self.export_tab, self.settings_tab),
            ("Playlists", "Biblioteca", "Pendrive e exportação", "Configurações"),
        ):
            self.tabs.add(frame, text=title)
        self.build_playlists()
        self.build_library()
        self.build_export()
        self.build_settings()
        bottom = ttk.Frame(root, padding=(24, 14))
        bottom.grid(row=2, column=0, sticky="ew")
        self.status = tk.StringVar(value="Pronto. Adicione uma playlist para começar.")
        ttk.Label(bottom, textvariable=self.status, wraplength=800).pack(side="left")
        self.stop = ttk.Button(bottom, text="Cancelar operação", command=self.cancel.set, state="disabled")
        self.stop.pack(side="right")
        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.grid(row=3, column=0, sticky="ew")
        self.refresh()
        root.after(100, self.pump)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def button(self, parent, text, command, accent=False):
        button = ttk.Button(
            parent, text=text, command=command, style="Accent.TButton" if accent else "TButton"
        )
        self.controls.append(button)
        return button

    def label(self, parent, title, text):
        ttk.Label(parent, text=title, font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(0, 6))
        ttk.Label(parent, text=text, foreground="#63786c", wraplength=950).pack(anchor="w", pady=(0, 18))

    def tree(self, parent, columns, widths):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True, pady=12)
        tree = ttk.Treeview(frame, columns=list(columns), show="headings", selectmode="browse")
        for name, width in zip(columns, widths):
            tree.heading(name, text=name)
            tree.column(name, width=width, minwidth=60)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True)
        return tree

    def build_playlists(self):
        parent = self.playlist_tab
        self.label(
            parent,
            "Uma biblioteca. Todas as suas playlists.",
            "1. Adicione os links   →   2. Confira as diferenças   →   3. Atualize   →   4. Exporte",
        )
        form = ttk.Frame(parent)
        form.pack(fill="x")
        self.url = tk.StringVar()
        entry = ttk.Entry(form, textvariable=self.url, font=("Segoe UI", 11))
        entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 10))
        entry.insert(0, "")
        self.controls.append(entry)
        self.button(form, "Adicionar playlist", self.add_playlist, True).pack(side="right")
        ttk.Label(parent, text="Cole uma URL https://open.spotify.com/playlist/…", foreground="#63786c").pack(
            anchor="w", pady=6
        )
        self.build_download_options(parent)
        self.playlists = self.tree(
            parent, ("Playlist", "Faixas", "Última leitura", "Observações"), (330, 70, 180, 260)
        )
        actions = ttk.Frame(parent)
        actions.pack(fill="x")
        self.button(actions, "Atualizar biblioteca", lambda: self.sync(False), True).pack(side="left")
        self.button(actions, "Baixar tudo novamente", lambda: self.sync(True)).pack(side="left", padx=8)
        self.button(actions, "Remover playlist", self.remove_playlist).pack(side="right")
        ttk.Label(
            parent,
            text="Atualizar reutiliza os arquivos existentes. Remover uma playlist preserva a biblioteca local.",
            foreground="#63786c",
        ).pack(anchor="w", pady=(14, 0))
        # Reserve the actions before giving remaining space to the growing table.
        self.playlists.master.pack_forget()
        self.playlists.master.pack(fill="both", expand=True, pady=12)

    def build_library(self):
        parent = self.library_tab
        self.label(
            parent,
            "Sua coleção local",
            "Uma cópia por faixa do Spotify. Corrija categorias e acompanhe músicas que precisam de atenção.",
        )
        bar = ttk.Frame(parent)
        bar.pack(fill="x")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.refresh_tracks())
        ttk.Label(bar, text="Buscar").pack(side="left", padx=(0, 10))
        ttk.Entry(bar, textvariable=self.search).pack(side="left", fill="x", expand=True)
        self.tracks = self.tree(
            parent, ("Música / artista", "Categoria", "Estado", "Playlists"), (460, 160, 180, 70)
        )
        self.tracks.bind("<<TreeviewSelect>>", self.track_detail)
        self.detail = tk.StringVar(value="Selecione uma música para ver o caminho ou o motivo de uma falha.")
        ttk.Label(parent, textvariable=self.detail, wraplength=950, foreground="#63786c").pack(
            anchor="w", pady=5
        )
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=8)
        self.category = ttk.Combobox(
            actions, values=["Automática", *CATEGORIES, "Outros"], state="readonly", width=21
        )
        self.category.set("Automática")
        self.category.pack(side="left")
        self.controls.append(self.category)
        self.button(actions, "Corrigir categoria", self.correct).pack(side="left", padx=8)
        self.button(actions, "Associar MP3 local", self.import_local).pack(side="left")
        self.button(actions, "Revisar faixas sem playlist", self.cleanup).pack(side="right")
        self.tracks.master.pack_forget()
        self.tracks.master.pack(fill="both", expand=True, pady=12)

    def build_export(self):
        parent = self.export_tab
        self.label(
            parent,
            "Pronto para pegar a estrada",
            "MP3 · 192 kbps · 44,1 kHz · estéreo · organização e metadados conforme suas opções em Playlists",
        )
        ttk.Label(parent, text="Destino").pack(anchor="w")
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=8)
        self.destination = tk.StringVar(value=self.store.setting("export_destination", ""))
        entry = ttk.Entry(bar, textvariable=self.destination)
        entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        self.controls.append(entry)
        self.button(bar, "Escolher pasta…", self.choose_export).pack(side="right")
        usb = ttk.Frame(parent)
        usb.pack(fill="x", pady=12)
        self.devices = ttk.Combobox(usb, state="readonly", width=58)
        self.devices.pack(side="left", padx=(0, 8))
        self.devices.bind(
            "<<ComboboxSelected>>",
            lambda _: self.destination.set(self.drive_list[self.devices.current()]["path"]),
        )
        self.controls.append(self.devices)
        self.button(usb, "Detectar pendrives", self.detect_usb).pack(side="left")
        ttk.Label(
            parent,
            text="O spoTano cria uma pasta spoTano no destino. Arquivos fora dela não são gerenciados.\n"
            "As próximas exportações conferem os hashes e copiam apenas arquivos novos ou alterados.\n\n"
            "Para rádios antigos: use pendrive FAT32. O programa não formata dispositivos.\n"
            "A compatibilidade depende da versão do rádio; teste uma pequena coleção no seu Cerato 2011.\n\n"
            "Arquivos removidos ficam em spoTano/.spotano-trash para recuperação. Esvazie essa pasta\n"
            "manualmente após conferir o resultado; ela pode ocupar espaço e aparecer em alguns rádios.",
            wraplength=930,
            foreground="#63786c",
            justify="left",
        ).pack(anchor="w", pady=18)
        self.button(parent, "Conferir e exportar", self.export, True).pack(anchor="w", pady=12)

    def build_settings(self):
        parent = self.settings_tab
        self.label(
            parent,
            "Configurações",
            "A biblioteca e o histórico ficam neste computador. Não há servidor, assinatura ou IA paga.",
        )
        self.mb = tk.BooleanVar(value=self.store.setting("musicbrainz", True))
        for text, variable, command in [
            (
                "Quando Categoria estiver marcada, consultar gêneros ausentes no MusicBrainz",
                self.mb,
                lambda: self.store.set_setting("musicbrainz", self.mb.get()),
            ),
        ]:
            check = ttk.Checkbutton(parent, text=text, variable=variable, command=command)
            check.pack(anchor="w", pady=8)
            self.controls.append(check)
        ttk.Label(
            parent,
            text="A consulta envia o nome do artista ao MusicBrainz. Resultados ficam em cache por 90 dias.\n"
            "Gêneros ausentes ou ambíguos ficam em Outros; você pode corrigir na Biblioteca.",
            foreground="#63786c",
        ).pack(anchor="w", pady=8)
        self.button(
            parent, "Aplicar opções às músicas já baixadas", lambda: self.run(self.library.reorganize)
        ).pack(anchor="w", pady=8)
        ttk.Label(parent, text="Biblioteca: " + str(self.library.music), wraplength=950).pack(
            anchor="w", pady=16
        )
        actions = ttk.Frame(parent)
        actions.pack(fill="x")
        self.button(actions, "Abrir biblioteca", lambda: open_folder(self.library.music)).pack(side="left")
        self.button(actions, "Abrir dados e lixeira", lambda: open_folder(self.store.root)).pack(
            side="left", padx=8
        )
        self.button(actions, "Backup do catálogo…", self.backup).pack(side="left")
        actions2 = ttk.Frame(parent)
        actions2.pack(fill="x", pady=14)
        self.button(
            actions2,
            "Preparar downloads (FFmpeg + Deno)",
            lambda: self.run(
                self.library.provider.setup, lambda r: messagebox.showinfo("Componentes prontos", str(r))
            ),
            True,
        ).pack(side="left")
        self.button(actions2, "Diagnóstico", self.diagnostics).pack(side="left", padx=8)
        self.button(actions2, "Reclassificar gêneros", self.reclassify).pack(side="left")
        self.button(actions2, "Histórico", self.history).pack(side="left", padx=8)
        ttk.Label(
            parent,
            text="Use downloads somente quando tiver autorização e quando o provedor permitir.\n"
            "O Spotify fornece metadados; o áudio é obtido de outros provedores pelo spotDL.\n"
            "Playlists privadas, bloqueios, limites de consulta e correspondências incorretas podem impedir downloads.",
            foreground="#63786c",
            wraplength=950,
        ).pack(anchor="w", pady=8)
        self.button(
            parent,
            "Ajuda e atualizações ↗",
            lambda: webbrowser.open("https://github.com/Jvprotano/spoTano#readme"),
        ).pack(anchor="w")
        ttk.Label(
            parent,
            text=f"spoTano {__version__} · GPL-3.0-or-later · baseado no spotDL 4.6.0",
            foreground="#63786c",
        ).pack(anchor="w", pady=15)

    def report(self, message):
        self.events.put(("progress", message))

    def run(self, work, done=lambda result: None):
        if self.busy:
            return
        self.busy = True
        self.cancel.clear()
        for control in self.controls:
            control.configure(state="disabled")
        self.stop.configure(state="normal")
        self.progress.start(12)
        self.status.set("Trabalhando…")

        def task():
            try:
                result = work()
                self.events.put(("done", (done, result)))
            except Exception as exc:
                self.events.put(("error", exc))

        threading.Thread(target=task, daemon=True).start()

    def pump(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "progress":
                    self.status.set(value)
                    continue
                self.busy = False
                self.progress.stop()
                self.stop.configure(state="disabled")
                for control in self.controls:
                    control.configure(state="readonly" if isinstance(control, ttk.Combobox) else "normal")
                self.refresh()
                if self.closing:
                    self.root.destroy()
                    return
                if kind == "error":
                    self.status.set(str(value))
                    if not isinstance(value, Cancelled):
                        messagebox.showerror("Operação interrompida", str(value), parent=self.root)
                else:
                    self.status.set("Concluído.")
                    callback, result = value
                    callback(result)
        except queue.Empty:
            pass
        self.root.after(100, self.pump)

    def refresh(self):
        self.refresh_option_labels()
        self.playlists.delete(*self.playlists.get_children())
        playlists = self.store.playlists()
        for row in playlists:
            self.playlists.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["name"],
                    row["count"],
                    (row["synced_at"] or "Ainda não lida").replace("T", " ").replace("+00:00", " UTC"),
                    row["warning"],
                ),
            )
        tracks = self.store.tracks()
        self.summary.configure(
            text=f"{len(playlists)} playlists  ·  {sum(bool(t['path']) for t in tracks)} arquivos locais"
        )
        self.refresh_tracks()

    def refresh_tracks(self):
        if not hasattr(self, "tracks"):
            return
        self.tracks.delete(*self.tracks.get_children())
        search = self.search.get().casefold()
        self.track_rows = {}
        for row in self.store.tracks():
            metadata = json.loads(row["metadata"])
            title = metadata["name"] + " / " + metadata["artist"]
            if search not in title.casefold():
                continue
            self.track_rows[row["id"]] = row
            status = {
                "ready": "Disponível",
                "pending": "Aguardando download",
                "error": "Falha · ver detalhes",
            }[row["status"]]
            self.tracks.insert(
                "",
                "end",
                iid=row["id"],
                values=(
                    title,
                    row["override"] or (row["category"] if row["classified"] else "Não classificada"),
                    status,
                    row["references_count"],
                ),
            )

    def track_detail(self, _=None):
        selection = self.tracks.selection()
        if selection:
            row = self.track_rows[selection[0]]
            self.detail.set(
                row["error"] or str(self.library.music / row["path"])
                if row["path"]
                else row["error"] or "Ainda não baixada."
            )

    def add_playlist(self):
        try:
            self.store.add_playlist(self.url.get())
            self.url.set("")
            self.refresh()
        except Exception as exc:
            messagebox.showerror("Não foi possível adicionar", str(exc))

    def remove_playlist(self):
        selection = self.playlists.selection()
        if selection and messagebox.askyesno(
            "Remover playlist",
            "Remover esta playlist do acompanhamento? Os arquivos locais serão preservados.",
        ):
            self.store.remove_playlist(int(selection[0]))
            self.refresh()

    def review(self, title, summary, lines, action, confirm="Confirmar"):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("800x560")
        dialog.geometry(f"+{max(0, self.root.winfo_rootx() + 120)}+{max(0, self.root.winfo_rooty() + 50)}")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        ttk.Label(dialog, text=summary, wraplength=740, font=("Segoe UI", 12, "bold")).pack(
            fill="x", padx=22, pady=20
        )
        text = tk.Text(
            dialog, wrap="word", font=("Segoe UI", 10), padx=12, pady=12, bg="white", relief="flat"
        )
        text.pack(fill="both", expand=True, padx=22)
        scroll = ttk.Scrollbar(text, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.insert("1.0", "\n".join(lines) or "Nenhuma alteração em arquivos.")
        text.configure(state="disabled")
        buttons = ttk.Frame(dialog, padding=20)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Voltar", command=dialog.destroy).pack(side="right")

        def proceed():
            dialog.destroy()
            action()

        ttk.Button(buttons, text=confirm, style="Accent.TButton", command=proceed).pack(side="right", padx=10)

    def sync(self, force):
        def reviewed(plan):
            lines = [f"+ {p}: {name}" for p, name in plan.added]
            lines += [f"− {p}: {name} (arquivo local preservado)" for p, name in plan.removed]
            lines += [f"Download: {t['artist']} — {t['name']}" for t in plan.downloads]
            self.review(
                "Conferir atualização",
                f"{len(plan.downloads)} downloads · {plan.retained} reutilizadas · "
                f"{len(plan.added)} inclusões · {len(plan.removed)} saídas de playlists",
                lines,
                lambda: self.run(lambda: self.library.apply(plan), self.sync_done),
                "Baixar novamente" if force else "Atualizar",
            )

        self.run(lambda: self.library.preview(force), reviewed)

    def sync_done(self, result):
        messagebox.showinfo(
            "Biblioteca atualizada",
            f"{result['downloaded']} downloads concluídos.\n"
            f"{result['reused']} arquivos reutilizados.\n{len(result['failures'])} falhas.\n\n"
            "Faixas com falha aparecem na Biblioteca. Atualizar tenta obtê-las novamente.",
        )

    def correct(self):
        selection = self.tracks.selection()
        if selection:
            category = self.category.get()
            self.run(
                lambda: self.library.correct_genre(selection[0], "" if category == "Automática" else category)
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

        class LocalProvider:
            def download(self, metadata, output):
                return outer.call("local", {"source": source, "output": str(output), "metadata": metadata})

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
                    lambda path: messagebox.showinfo(
                        "Exportação concluída", "Arquivos verificados em:\n" + path
                    ),
                ),
                "Exportar",
            )

        def preview():
            self.library.reorganize()
            return self.exporter.preview(destination)

        self.run(preview, reviewed)

    def build_download_options(self, parent):
        saved = download_options(self.store)
        self.option_vars = {key: tk.BooleanVar(value=value) for key, value in saved.items()}
        self.option_labels = {key: tk.StringVar() for key in OPTIONS}
        self.option_summary = tk.StringVar()
        self.options_caption = tk.StringVar()
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(6, 4))
        self.button(bar, "Personalizar download…", self.open_download_options).pack(side="right")
        ttk.Label(bar, textvariable=self.options_caption, foreground="#63786c", wraplength=580).pack(
            side="left", anchor="w"
        )
        self.refresh_option_labels()

    def open_download_options(self):
        if self.busy:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Personalizar download · spoTano")
        dialog.geometry("850x420")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.bind("<Escape>", lambda _: dialog.destroy())
        box = ttk.Frame(dialog, padding=20)
        box.pack(fill="both", expand=True)
        ttk.Label(box, text="Adicione só o que quiser", font=("Segoe UI", 18, "bold")).pack(anchor="w")
        ttk.Label(
            box,
            text="Tudo desmarcado = músicas juntas em uma pasta, sem classificação nem tags extras.",
            foreground="#63786c",
        ).pack(anchor="w", pady=(6, 12))
        actions = ttk.Frame(box)
        actions.pack(fill="x", pady=(0, 10))
        ttk.Button(actions, text="Marcar tudo", command=lambda: self.select_options(True)).pack(side="left")
        ttk.Button(actions, text="Desmarcar tudo", command=lambda: self.select_options(False)).pack(
            side="left", padx=8
        )
        for key in OPTIONS:
            row = ttk.Frame(box)
            row.pack(fill="x", pady=7)
            ttk.Checkbutton(
                row, text=OPTIONS[key], variable=self.option_vars[key], command=self.save_download_options
            ).pack(side="left")
            ttk.Label(row, textvariable=self.option_labels[key], foreground="#63786c").pack(side="right")
        ttk.Label(box, textvariable=self.option_summary, foreground="#63786c", wraplength=800).pack(
            anchor="w", pady=(12, 8)
        )
        ttk.Label(
            box,
            text="Estimativas fixas por música, baseadas em testes anteriores. Os tempos reais podem variar.",
            foreground="#63786c",
        ).pack(anchor="w")
        ttk.Button(box, text="Concluir", command=dialog.destroy).pack(side="right", anchor="s", pady=(10, 0))
        self.refresh_option_labels()

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
        mode = "Download simples: todas as músicas juntas, sem classificação nem tags extras."
        if any(selected.values()):
            mode = "As opções valem no próximo download ou exportação."
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
            self.options_caption.set("Download simples · músicas juntas na mesma pasta, sem tags extras.")
        self.option_summary.set(f"{mode}\nPasta: Music/{path}")

    def save_download_options(self):
        self.store.set_setting("download_options", {key: var.get() for key, var in self.option_vars.items()})
        self.refresh_option_labels()

    def select_options(self, enabled):
        for variable in self.option_vars.values():
            variable.set(enabled)
        self.save_download_options()

    def reclassify(self):
        def work():
            from .genres import GenreResolver

            resolver = GenreResolver(self.store)
            for track in self.store.tracks():
                self.library.check_cancel()
                if track["override"]:
                    continue
                metadata = json.loads(track["metadata"])
                self.report("Classificando " + metadata["artist"])
                category = resolver.resolve(metadata)
                with self.store.connect() as db:
                    db.execute(
                        "UPDATE tracks SET category=?,classified=1 WHERE id=?", (category, track["id"])
                    )
                    self.store.bump(db)
            self.library.reorganize()

        self.run(work)

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
        window = tk.Toplevel(self.root)
        window.title("Histórico de operações · spoTano")
        window.geometry("850x500")
        text = tk.Text(window, wrap="word", padx=18, pady=18, font=("Segoe UI", 10))
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
