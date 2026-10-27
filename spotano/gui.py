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

from . import __version__
from .db import Store
from .exporter import LAYOUTS, Exporter, output_folders, usb_drives
from .genres import CATEGORIES
from .library import Library, SyncPlan
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
        self.checked_playlists = set()
        self.library = Library(self.store, SpotProvider(self.cancel, self.report), self.report, self.cancel)
        self.exporter = Exporter(self.library)
        root.title("spoTano · Sua música, com você")
        root.geometry("1200x900")
        root.minsize(1000, 760)
        root.configure(bg="#f4f6f4")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background="#f4f6f4", foreground="#16352c")
        style.configure("TButton", padding=(13, 7), background="#e5ede8")
        style.configure("Accent.TButton", background="#176548", foreground="white")
        style.map("Accent.TButton", background=[("active", "#207e5a"), ("disabled", "#a2b8ab")])
        style.configure("Treeview", rowheight=32, fieldbackground="white", background="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=8)
        style.configure("TNotebook.Tab", padding=(18, 11))
        style.configure(
            "Download.Horizontal.TProgressbar",
            background="#176548",
            troughcolor="#e5ede8",
            lightcolor="#176548",
            darkcolor="#176548",
            bordercolor="#a2b8ab",
        )
        head = ttk.Frame(root, padding=(26, 12))
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
            ttk.Frame(self.tabs, padding=14) for _ in range(4)
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
        logs = ttk.LabelFrame(root, text="Progresso em tempo real", padding=8)
        logs.grid(row=2, column=0, sticky="ew", padx=24, pady=(10, 0))
        self.batch_status = tk.StringVar(value="")
        progress_actions = ttk.Frame(logs)
        progress_actions.pack(side="top", fill="x", pady=(0, 4))
        ttk.Label(progress_actions, textvariable=self.batch_status, font=("Segoe UI", 10, "bold")).pack(
            side="left"
        )
        self.open_downloads_button = ttk.Button(
            progress_actions,
            text="Abrir pasta dos downloads",
            command=lambda: open_folder(self.library.music),
        )
        self.open_downloads_button.pack(side="right")
        self.log_text = tk.Text(
            logs, height=4, wrap="word", state="disabled", font=("Consolas", 9), bg="#ffffff", relief="flat"
        )
        scroll = ttk.Scrollbar(logs, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)
        log_actions = ttk.Frame(logs)
        log_actions.pack(side="right", padx=8)
        ttk.Button(log_actions, text="Salvar logs…", command=self.save_logs).pack(side="left")
        self.log_size = ttk.Button(log_actions, text="Ampliar logs", command=self.toggle_logs)
        self.log_size.pack(side="left", padx=(4, 0))
        bottom = ttk.Frame(root, padding=(24, 10))
        bottom.grid(row=3, column=0, sticky="ew")
        self.status = tk.StringVar(value="Pronto. Adicione uma playlist para começar.")
        ttk.Label(bottom, textvariable=self.status, wraplength=800).pack(side="left")
        self.stop = ttk.Button(
            bottom, text="Cancelar operação", command=self.cancel_operation, state="disabled"
        )
        self.stop.pack(side="right")
        self.progress = ttk.Progressbar(root, mode="indeterminate", style="Download.Horizontal.TProgressbar")
        self.progress.grid(row=4, column=0, sticky="ew")
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
        ttk.Label(parent, text=text, foreground="#63786c", wraplength=880).pack(anchor="w", pady=(0, 10))

    def tree(self, parent, columns, widths, pack=True):
        frame = ttk.Frame(parent)
        if pack:
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
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(4, weight=1)
        heading = ttk.Frame(parent)
        heading.grid(row=0, column=0, sticky="ew")
        self.label(
            heading,
            "Importe. Selecione. Baixe.",
            "Atualizar consulta o Spotify e verifica mudanças. Depois, escolha o que baixar nas playlists marcadas.",
        )
        form = ttk.Frame(parent)
        form.grid(row=1, column=0, sticky="ew")
        ttk.Label(form, text="Link Spotify").pack(side="left", padx=(0, 10))
        self.url = tk.StringVar()
        entry = ttk.Entry(form, textvariable=self.url, font=("Segoe UI", 11))
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 10))
        entry.insert(0, "")
        self.controls.append(entry)
        self.button(form, "Importar playlist", self.add_playlist, True).pack(side="right")
        entry.bind("<Return>", lambda _: self.add_playlist())
        selection_bar = ttk.Frame(parent)
        selection_bar.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.button(selection_bar, "Marcar todas", lambda: self.mark_playlists(True)).pack(side="left")
        self.button(selection_bar, "Desmarcar", lambda: self.mark_playlists(False)).pack(side="left", padx=6)
        self.selection_summary = tk.StringVar(value="Nenhuma playlist marcada")
        ttk.Label(selection_bar, textvariable=self.selection_summary).pack(side="left", padx=10)
        self.button(selection_bar, "Organizar exportação…", lambda: self.tabs.select(self.export_tab)).pack(
            side="right"
        )
        self.group_button = self.button(selection_bar, "Pasta / grupo…", self.assign_group)
        self.group_button.pack(side="right", padx=8)
        self.playlists = self.tree(
            parent,
            ("Marcar", "Playlist", "Faixas / locais", "Último download", "Pasta na exportação"),
            (60, 320, 120, 190, 170),
            pack=False,
        )
        self.playlists.master.grid(row=4, column=0, sticky="nsew", pady=8)
        self.playlists.column("Marcar", width=60, minwidth=60, stretch=False, anchor="center")
        self.playlists.bind("<Button-1>", self.toggle_playlist)
        self.playlists.bind("<space>", self.toggle_playlist)
        self.playlists.bind("<<TreeviewSelect>>", self.playlist_detail)
        self.playlist_info = tk.StringVar(
            value="Clique na caixa ou pressione Espaço para marcar uma playlist."
        )
        ttk.Label(parent, textvariable=self.playlist_info, foreground="#63786c", wraplength=880).grid(
            row=5, column=0, sticky="w"
        )
        actions = ttk.Frame(parent)
        actions.grid(row=6, column=0, sticky="ew", pady=(6, 0))
        self.force_button = self.button(actions, "Baixar tudo", lambda: self.sync(True), True)
        self.force_button.pack(side="left")
        self.update_button = self.button(actions, "Atualizar selecionadas", self.refresh_selected)
        self.update_button.pack(side="left", padx=8)
        self.remove_button = self.button(actions, "Remover selecionadas", self.remove_playlist)
        self.remove_button.pack(side="right")
        self.incremental_actions = ttk.Frame(actions)
        self.new_button = self.button(self.incremental_actions, "Baixar novas", lambda: self.sync(False))
        self.new_button.pack(side="left")
        self.mirror_button = self.button(
            self.incremental_actions, "Baixar e remover excluídas", lambda: self.sync(False, remove_missing=True)
        )
        self.mirror_button.pack(side="left", padx=8)
        self.download_hint = tk.StringVar()
        ttk.Label(
            parent,
            textvariable=self.download_hint,
            foreground="#63786c",
            wraplength=880,
        ).grid(row=7, column=0, sticky="w", pady=(6, 0))
        self.folder_hint = tk.StringVar()
        ttk.Label(parent, textvariable=self.folder_hint, foreground="#63786c", wraplength=880).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )

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
        extra = ttk.Frame(parent)
        extra.pack(fill="x")
        self.button(extra, "Corrigir artista", self.correct_artist).pack(side="left")
        self.button(extra, "Fonte do áudio…", self.audio_source).pack(side="left", padx=8)
        self.button(extra, "Revisar cópias antigas…", self.review_copies).pack(side="right")
        self.tracks.master.pack_forget()
        self.tracks.master.pack(fill="both", expand=True, pady=12)

    def build_export(self):
        # Keep the primary action reachable at smaller window heights.
        self.button(self.export_tab, "Conferir e exportar", self.export, True).pack(
            side="bottom", anchor="w", pady=(8, 0)
        )
        viewport = ttk.Frame(self.export_tab)
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, bg="#f4f6f4", highlightthickness=0, width=1)
        scrollbar = ttk.Scrollbar(viewport, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        parent = ttk.Frame(canvas)
        content = canvas.create_window(0, 0, window=parent, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(content, width=event.width))
        parent.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        self.label(
            parent,
            "Escolha como sua coleção será salva",
            "Exporte para uma pasta no computador ou pendrive. A saída inclui todas as playlists importadas; "
            "os botões de download na aba Playlists operam somente nas marcadas.",
        )
        layout_bar = ttk.Frame(parent)
        layout_bar.pack(fill="x")
        ttk.Label(layout_bar, text="Organização da saída:").pack(side="left", padx=(0, 8))
        self.layout = ttk.Combobox(layout_bar, values=list(LAYOUTS.values()), state="readonly", width=28)
        self.layout.set(LAYOUTS[self.store.setting("output_layout", "playlists")])
        self.layout.pack(side="left")
        self.layout.bind("<<ComboboxSelected>>", self.change_layout)
        self.controls.append(self.layout)
        self.output_preview = tk.StringVar()
        ttk.Label(
            parent, textvariable=self.output_preview, foreground="#63786c", wraplength=1050, justify="left"
        ).pack(anchor="w", pady=12)
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
            text="A biblioteca interna guarda uma cópia por faixa e reutiliza o áudio nas exportações.\n"
            "Por playlist: faixas compartilhadas aparecem em cada pasta. Por grupo: uma vez em cada grupo.\n"
            "Só a pasta spoTano é gerenciada; arquivos antigos vão para .spotano-trash para recuperação.\n"
            "Para rádio antigo, prefira FAT32 e teste uma coleção pequena. Esvazie a lixeira após conferir.",
            wraplength=880,
            foreground="#63786c",
            justify="left",
        ).pack(anchor="w", pady=8)

        def wheel(event):
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

        def bind_scroll(widget):
            widget.bind("<MouseWheel>", wheel)
            for child in widget.winfo_children():
                bind_scroll(child)

        bind_scroll(parent)
        canvas.bind("<MouseWheel>", wheel)

    def build_settings(self):
        viewport = ttk.Frame(self.settings_tab)
        viewport.pack(fill="both", expand=True)
        canvas = tk.Canvas(viewport, bg="#f4f6f4", highlightthickness=0)
        scroll = ttk.Scrollbar(viewport, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        parent = ttk.Frame(canvas)
        content = canvas.create_window(0, 0, window=parent, anchor="nw")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(content, width=event.width))
        parent.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        self.label(
            parent,
            "Configurações",
            "A biblioteca e o histórico ficam neste computador. Não há servidor, assinatura ou IA paga.",
        )
        self.by_genre = tk.BooleanVar(value=self.store.setting("by_genre", True))
        self.mb = tk.BooleanVar(value=self.store.setting("musicbrainz", True))
        parallel = ttk.Frame(parent)
        parallel.pack(fill="x", pady=(0, 8))
        ttk.Label(parallel, text="Downloads em paralelo:").pack(side="left", padx=(0, 8))
        self.download_workers = ttk.Combobox(parallel, values=["1", "2", "3", "4"], state="readonly", width=4)
        self.download_workers.set(str(self.store.setting("download_workers", 2)))
        self.download_workers.pack(side="left")
        self.download_workers.bind(
            "<<ComboboxSelected>>",
            lambda _: self.store.set_setting("download_workers", int(self.download_workers.get())),
        )
        self.controls.append(self.download_workers)
        ttk.Label(
            parallel, text="2 por padrão; reduza se a conexão ou o provedor limitar.", foreground="#63786c"
        ).pack(side="left", padx=8)
        conversions = ttk.Frame(parent)
        conversions.pack(fill="x", pady=(0, 8))
        ttk.Label(conversions, text="Conversões MP3 em paralelo:").pack(side="left", padx=(0, 8))
        self.conversion_workers = ttk.Combobox(conversions, values=["1", "2", "3", "4"],
                                              state="readonly", width=4)
        self.conversion_workers.set(str(self.store.setting("conversion_workers", 2)))
        self.conversion_workers.pack(side="left")
        self.conversion_workers.bind("<<ComboboxSelected>>", lambda _: self.store.set_setting(
            "conversion_workers", int(self.conversion_workers.get())))
        self.controls.append(self.conversion_workers)
        ttk.Label(conversions, text="2 por padrão; limite separado para reduzir disputa de CPU.",
                  foreground="#63786c").pack(side="left", padx=8)
        for text, variable, command in [
            (
                "Organizar por gênero (desativado: pastas por artista)",
                self.by_genre,
                self.change_organization,
            ),
            (
                "Consultar gêneros online quando faltarem metadados",
                self.mb,
                lambda: self.store.set_setting("musicbrainz", self.mb.get()),
            ),
        ]:
            check = ttk.Checkbutton(parent, text=text, variable=variable, command=command)
            check.pack(anchor="w", pady=8)
            self.controls.append(check)
        ttk.Label(
            parent,
            text="Confere faixas no iTunes/Deezer e complementa com MusicBrainz/Wikidata.\n"
            "Usa cache e limite de tempo. Last.fm é opcional. Não precisa de chave para o fluxo padrão.",
            foreground="#63786c",
        ).pack(anchor="w", pady=8)
        lastfm = ttk.Frame(parent)
        lastfm.pack(fill="x", pady=8)
        ttk.Label(lastfm, text="Chave de API Last.fm (opcional):").pack(side="left")
        self.lastfm_key = ttk.Entry(lastfm, width=30, show="*")
        self.lastfm_key.insert(0, self.store.setting("lastfm_api_key", ""))
        self.lastfm_key.pack(side="left", padx=8)
        self.controls.append(self.lastfm_key)
        self.button(lastfm, "Salvar chave", lambda: self.store.set_setting(
            "lastfm_api_key", self.lastfm_key.get().strip())).pack(side="left")
        ttk.Label(parent, text="Last.fm complementa categorias sem evidência nas fontes principais. "
                  "Deixe vazio para usar somente as fontes gratuitas sem chave.",
                  foreground="#63786c", wraplength=900).pack(anchor="w")
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
        self.button(parent, "Abrir métricas das execuções", self.open_metrics).pack(anchor="w", pady=4)
        self.button(parent, "Limpar cache de correspondências…", self.clear_matches).pack(anchor="w", pady=4)
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

        def wheel(event):
            canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"

        def bind_wheel(widget):
            widget.bind("<MouseWheel>", wheel)
            for child in widget.winfo_children():
                bind_wheel(child)

        bind_wheel(parent)

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
        expanded = int(self.log_text["height"]) == 4
        self.log_text.configure(height=12 if expanded else 4)
        self.log_size.configure(text="Reduzir logs" if expanded else "Ampliar logs")

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
                    self.status.set(str(value))
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
        self.playlists.delete(*self.playlists.get_children())
        playlists = self.store.playlists()
        self.playlist_rows = {str(p["id"]): p for p in playlists}
        self.checked_playlists.intersection_update(p["id"] for p in playlists)
        folders = output_folders(playlists, self.store.setting("output_layout", "playlists"))
        for row in playlists:
            local = self.store.rows(
                """SELECT COUNT(*) n FROM membership m JOIN tracks t ON t.id=m.track_id
                WHERE m.playlist_id=? AND t.path IS NOT NULL""",
                (row["id"],),
            )[0]["n"]
            row["local_count"] = local
            current = {r["track_id"] for r in self.store.rows(
                "SELECT track_id FROM membership WHERE playlist_id=?", (row["id"],))}
            baseline = {r["track_id"] for r in self.store.rows(
                "SELECT track_id FROM download_membership WHERE playlist_id=?", (row["id"],))}
            row["changes"] = current != baseline or local < row["count"] or bool(self.store.rows(
                """SELECT 1 FROM membership m JOIN tracks t ON t.id=m.track_id
                WHERE m.playlist_id=? AND t.status='pending' LIMIT 1""", (row["id"],)))
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
                    folders[row["id"]] or "Todas juntas",
                ),
            )
        tracks = self.store.tracks()
        self.summary.configure(
            text=f"{len(playlists)} playlists  ·  {sum(bool(t['path']) for t in tracks)} arquivos locais"
        )
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
        self.selection_summary.set(f"{count} playlist(s) marcada(s)" if count else "Nenhuma playlist marcada")
        for button in (self.force_button, self.update_button, self.remove_button, self.group_button):
            button.configure(state="normal" if count and not self.busy else "disabled")
        selected = [self.playlist_rows[str(i)] for i in self.checked_playlists]
        changed = any(row["changes"] and (row["downloaded_at"] or row["local_count"]
                      or row["id"] in getattr(self, "verified_playlists", set())) for row in selected)
        for button in (self.new_button, self.mirror_button):
            button.configure(state="normal" if changed and not self.busy else "disabled")
        if changed:
            self.incremental_actions.pack(side="left")
            hint = ("Baixar novas mantém as excluídas na biblioteca. Ambas as ações retomam pendências.\n"
                    "Baixar e remover excluídas também move as saídas para a lixeira; "
                    "músicas compartilhadas são preservadas.")
        else:
            self.incremental_actions.pack_forget()
            hint = ("Atualizar apenas consulta e verifica; não baixa nem remove áudios. "
                    "Baixar tudo baixa novamente todas as faixas da lista salva.")
        self.download_hint.set(hint)

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

    def assign_group(self):
        if self.busy or not self.checked_playlists:
            return
        rows = [self.playlist_rows[str(i)] for i in sorted(self.checked_playlists)]
        names = ", ".join(row["name"] for row in rows)
        initial = rows[0]["output_group"] if len({row["output_group"] for row in rows}) == 1 else ""
        name = simpledialog.askstring(
            "Nome da pasta / grupo",
            f"Aplicar a {len(rows)} playlist(s): {names[:160]}\n\n"
            "No modo por playlist: nome da pasta individual.\n"
            "No modo por grupo: mesmo nome reúne as playlists.\n"
            "Vazio restaura o nome original / Sem grupo.\n"
            "Escolha o modo em Organizar exportação.",
            initialvalue=initial,
            parent=self.root,
        )
        if name is not None:
            self.store.set_output_group(sorted(self.checked_playlists), name)
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
        category = "Categoria" if self.store.setting("by_genre", True) else "Artista"
        if layout == "unified":
            text = f"Todas as playlists juntas: spoTano/{category}/Música.mp3"
        else:
            examples = list(dict.fromkeys(f"spoTano/{f}/{category}/Música.mp3" for f in folders.values()))
            text = "\n".join(examples[:3]) or f"spoTano/Pasta/{category}/Música.mp3"
            if len(examples) > 3:
                text += f"\n… mais {len(examples) - 3} pastas (a prévia mostrará todos os arquivos)."
        self.output_preview.set(
            text + "\nPersonalize em Pasta / grupo na aba Playlists (aplica às marcadas)."
        )
        description = {
            "unified": "Exportação: todas as playlists ficam juntas. Use Organizar exportação para separar.",
            "playlists": "Exportação: uma pasta separada por playlist. Altere em Organizar exportação.",
            "groups": "Exportação: mesmo grupo = mesma pasta; sem grupo = Sem grupo.",
        }[layout]
        self.folder_hint.set(
            "Downloads juntos na biblioteca compartilhada. " + description
        )

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
                values=(title, row["override"] or row["category"], status, row["references_count"]),
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
        url = self.url.get()

        def imported(playlist_id):
            self.url.set("")
            self.checked_playlists.add(playlist_id)
            self.refresh()
            self.status.set("Playlist importada e marcada. Clique em Baixar tudo para baixar os áudios.")

        self.run(lambda: self.library.import_playlist(url), imported)

    def remove_playlist(self):
        selection = sorted(self.checked_playlists)
        if (
            selection
            and not self.busy
            and messagebox.askyesno(
                "Remover playlists selecionadas",
                f"Remover {len(selection)} playlist(s) do acompanhamento? Os arquivos locais serão preservados.",
            )
        ):
            for playlist_id in selection:
                self.store.remove_playlist(playlist_id)
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

    def refresh_selected(self):
        selected = sorted(self.checked_playlists)
        if not selected or self.busy:
            return

        def refreshed(plan):
            self.verified_playlists = getattr(self, "verified_playlists", set()) | set(selected)
            self.refresh()
            self.review(
                "Playlists consultadas",
                f"{len(plan.added)} inclusões · {len(plan.removed)} saídas · "
                f"{len(plan.downloads)} faixas para baixar\nNenhum áudio foi baixado ou removido.",
                [*plan.warnings, *[f"+ {p}: {name}" for p, name in plan.added],
                 *[f"− {p}: {name}" for p, name in plan.removed]],
                lambda: None, "Fechar",
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
            lines += ["\nDownloads na biblioteca compartilhada: " + str(self.library.music), self.folder_hint.get()]
            self.review(
                "Conferir download e remoção" if remove_missing else "Conferir download",
                f"{len(selected)} playlist(s) selecionada(s)\n"
                f"{len(plan.downloads)} downloads · {plan.retained} reutilizadas · "
                f"{len(plan.added)} inclusões · {len(plan.removed)} saídas de playlists"
                + (f" · {len(plan.cleanup)} arquivos para a lixeira" if remove_missing else ""),
                lines,
                lambda: self.run(lambda: self.library.apply(plan), self.sync_done),
                "Baixar tudo" if force else "Baixar e remover excluídas" if remove_missing else "Baixar novas",
            )
            self.status.set("Prévia pronta. Confira as diferenças e confirme os downloads.")

        self.run(lambda: self.library.preview(
            force, playlist_ids=selected, saved=True, remove_missing=remove_missing), reviewed)

    def sync_done(self, result):
        self.show_saved_result(
            "Concluído com falhas" if result["failures"] else "Download finalizado",
            f"{result['downloaded']} downloads concluídos.\n"
            f"{result['reused']} arquivos reutilizados.\n{len(result['failures'])} falhas.\n\n"
            f"{result.get('removed', 0)} arquivos movidos para a lixeira.\n"
            "Faixas com falha aparecem na Biblioteca. Use Baixar novas para repetir apenas pendências.\n"
            + ("\nMétricas: " + result["run_directory"] if result.get("run_directory") else ""),
            self.library.music,
        )

    def show_saved_result(self, title, summary, path):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=22)
        body.pack(fill="both", expand=True)
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
            if messagebox.askyesno("Categoria do artista", f"Aplicar {category} a {metadata['artist']}?\n"
                                   "Correções individuais de faixa continuam tendo prioridade."):
                self.run(lambda: self.library.correct_artist(
                    selection[0], "" if category == "Automática" else category))

    def open_metrics(self):
        open_folder(getattr(self.library, "last_run", self.store.root / "runs"))

    def clear_matches(self):
        if messagebox.askyesno("Limpar correspondências", "Pesquisar novamente as gravações nos próximos "
                               "downloads? Áudios e fontes escolhidas manualmente serão preservados."):
            self.store.clear_audio_matches()
            self.status.set("Cache de correspondências limpo. Os áudios foram preservados.")

    def review_copies(self):
        def ready(rows):
            revision = self.store.setting("revision")
            self.review("Revisar cópias antigas", f"{len(rows)} arquivos físicos sem vínculo serão movidos "
                        "para a lixeira. Confira cada caminho antes de continuar.",
                        [row["reason"] + ": " + row["path"] for row in rows],
                        lambda: self.run(lambda: self.library.files.quarantine(rows, revision),
                                         lambda path: self.show_saved_result("Cópias preservadas na lixeira",
                                                                           "Revisão concluída.", path)),
                        "Mover cópias para lixeira")

        self.run(self.library.files.review, ready)

    def audio_source(self):
        selection = self.tracks.selection()
        if not selection or self.busy:
            return
        track_id = selection[0]
        metadata = json.loads(self.track_rows[track_id]["metadata"])
        dialog = tk.Toplevel(self.root)
        dialog.title("Fonte do áudio")
        dialog.geometry("800x500")
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=metadata["artist"] + " — " + metadata["name"],
                  wraplength=750, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(body, text=f"Duração de referência: {metadata.get('duration') or '?'} s. "
                  "Confira artista, duração e versão antes de escolher.", wraplength=750).pack(anchor="w", pady=8)
        sources = self.store.rows("SELECT url FROM audio_sources WHERE track_id=?", (track_id,))
        cached = self.store.audio_match(metadata)
        url = tk.StringVar(value=sources[0]["url"] if sources else (cached or {}).get("url", ""))
        ttk.Label(body, text="URL do vídeo completo no YouTube:").pack(anchor="w")
        ttk.Entry(body, textvariable=url).pack(fill="x", pady=8)
        candidates = ttk.Treeview(body, columns=("Faixa", "Artista", "Duração", "Confiança"),
                                  show="headings", height=5)
        for name, width in (("Faixa", 350), ("Artista", 180), ("Duração", 80), ("Confiança", 90)):
            candidates.heading(name, text=name)
            candidates.column(name, width=width, stretch=True)
        candidates.pack(fill="both", expand=True)
        rows = []

        def received(result):
            if not dialog.winfo_exists():
                return
            rows[:] = result
            candidates.delete(*candidates.get_children())
            for index, row in enumerate(rows):
                candidates.insert("", "end", iid=str(index), values=(row["name"], row["artist"],
                                  f"{row['duration']:.0f}s", f"{row['score']:.1f}"))

        candidates.bind("<<TreeviewSelect>>", lambda _: url.set(rows[int(candidates.selection()[0])]["url"])
                        if candidates.selection() else None)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=12)
        ttk.Button(actions, text="Pesquisar opções", command=lambda: self.run(
            lambda: self.library.provider.candidates(metadata), received)).pack(side="left")
        ttk.Button(actions, text="Abrir vídeo", command=lambda: webbrowser.open(url.get())
                   if url.get().startswith("https://") else None).pack(side="left", padx=8)

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
        ttk.Button(actions, text="Baixar esta gravação", command=download, style="Accent.TButton").pack(side="right")

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
                    lambda path: self.show_saved_result(
                        "Exportação concluída", "Arquivos verificados.", path
                    ),
                ),
                "Exportar",
            )

        self.run(lambda: self.exporter.preview(destination), reviewed)

    def change_organization(self):
        self.store.set_setting("by_genre", self.by_genre.get())
        self.refresh_output_preview()
        self.run(self.library.reorganize)

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
