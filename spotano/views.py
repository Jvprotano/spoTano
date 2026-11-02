"""Desktop views. Library and file operations remain in the application controller."""

import json
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__, ui
from .benchmark import DEFAULT_PLAYLIST
from .branding import apply_icon
from .exporter import LAYOUTS
from .genres import CATEGORIES
from .options import OPTIONS, download_options


class DesktopViews:
    # Separate cells keep each row action a single click, even after scrolling.
    playlist_actions = {
        "Atualizar": ("↻", "Atualizar do Spotify · F5"),
        "Detalhes": ("ⓘ", "Detalhes da playlist · Enter"),
        "Pasta": ("📁", "Pasta / grupo na exportação · Ctrl+G"),
        "Remover": ("×", "Remover playlist · Delete"),
    }

    def build_shell(self):
        root = self.root
        ui.configure(root)
        apply_icon(root)
        root.title("spoTano · Sua música, com você")
        root.geometry("1180x800")
        root.minsize(1000, 760)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)
        sidebar = tk.Frame(root, bg=ui.SIDEBAR, width=174)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="spoTano", font=("Segoe UI", 23, "bold"), bg=ui.SIDEBAR, fg="white").pack(
            anchor="w", padx=22, pady=(25, 0)
        )
        tk.Label(
            sidebar, text="Sua música, com você.", font=("Segoe UI", 9), bg=ui.SIDEBAR, fg="#c3d3c7"
        ).pack(anchor="w", padx=22, pady=(4, 32))
        self.tabs = ttk.Notebook(root, style="Shell.TNotebook", takefocus=False)
        self.tabs.grid(row=0, column=1, sticky="nsew", padx=28, pady=(24, 0))
        self.playlist_tab, self.library_tab, self.export_tab, self.settings_tab = [
            ttk.Frame(self.tabs) for _ in range(4)
        ]
        pages = [self.playlist_tab, self.library_tab, self.export_tab, self.settings_tab]
        self.nav_buttons = []
        for index, (page, title) in enumerate(
            zip(pages, ("Playlists", "Biblioteca", "Exportar", "Configurações"))
        ):
            self.tabs.add(page, text=title)
            button = ttk.Button(
                sidebar, text=title, style="Nav.TButton", command=lambda p=page: self.tabs.select(p)
            )
            if index == 3:
                button.pack(side="bottom", fill="x", padx=10, pady=(0, 12))
            else:
                button.pack(fill="x", padx=10, pady=3)
            self.nav_buttons.append(button)
        tk.Label(
            sidebar, text=f"VERSÃO {__version__}", bg=ui.SIDEBAR, fg="#c3d3c7", font=("Segoe UI", 8)
        ).pack(side="bottom", anchor="w", padx=26, pady=(0, 18))
        self.tabs.bind("<<NotebookTabChanged>>", self.update_navigation)
        self.build_playlists()
        self.build_library()
        self.build_export()
        self.build_settings()
        self.build_activity()
        root.bind("<Control-Key-1>", lambda _: self.tabs.select(self.playlist_tab))
        root.bind("<Control-Key-2>", lambda _: self.tabs.select(self.library_tab))
        root.bind("<Control-Key-3>", lambda _: self.tabs.select(self.export_tab))
        root.bind("<Control-comma>", lambda _: self.tabs.select(self.settings_tab))
        root.bind("<Control-f>", self.focus_search)
        root.bind("<Control-n>", lambda _: self.add_playlist_dialog() if not self.busy else None)

    def update_navigation(self, _=None):
        selected = self.tabs.index("current")
        for index, button in enumerate(self.nav_buttons):
            button.configure(style="Selected.Nav.TButton" if index == selected else "Nav.TButton")

    def focus_search(self, _=None):
        self.tabs.select(self.library_tab)
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")
        return "break"

    def heading(self, parent, title, description):
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(0, 22))
        text = ttk.Frame(bar)
        text.pack(side="left", fill="x", expand=True)
        ttk.Label(text, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(text, text=description, style="Muted.TLabel", wraplength=620).pack(anchor="w", pady=(4, 0))
        return bar

    def button(self, parent, text, command, accent=False):
        button = ttk.Button(
            parent, text=text, command=command, style="Accent.TButton" if accent else "TButton"
        )
        self.controls.append(button)
        return button

    def tree(self, parent, columns, widths, pack=True):
        frame = ttk.Frame(parent)
        if pack:
            frame.pack(fill="both", expand=True, pady=(12, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        tree = ttk.Treeview(frame, columns=list(columns), show="headings", selectmode="browse", height=6)
        for name, width in zip(columns, widths):
            tree.heading(name, text=name, anchor="w")
            tree.column(name, width=width, minwidth=60)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)

        def horizontal_scroll(first, last):
            horizontal.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                horizontal.grid_remove()
            else:
                horizontal.grid(row=1, column=0, sticky="ew")

        tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal_scroll)
        tree.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        return tree

    def empty_state(self, parent, title, description, action=None, caption=""):
        frame = ttk.Frame(parent, padding=26)
        ttk.Label(frame, text=title, font=("Segoe UI", 17, "bold")).pack(pady=(0, 8))
        ttk.Label(frame, text=description, style="Muted.TLabel", wraplength=430, justify="center").pack()
        if action:
            self.button(frame, caption, action, True).pack(pady=(20, 0))
        return frame

    def build_playlists(self):
        parent = self.playlist_tab
        head = self.heading(parent, "Playlists", "Marque as playlists e escolha o que baixar.")
        self.button(head, "+ Adicionar playlist", self.add_playlist_dialog).pack(side="right", padx=(12, 0))
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(0, 10))
        self.summary = ttk.Label(bar, style="Muted.TLabel")
        self.summary.pack(side="left")
        footer = ttk.Frame(parent)
        footer.pack(side="bottom", fill="x")
        self.playlists = self.tree(
            parent,
            ("Marcar", "Playlist", "Faixas / locais", "Último download", *self.playlist_actions),
            (44, 260, 110, 150, 38, 38, 38, 38),
        )
        self.playlists.column("Marcar", width=44, minwidth=44, stretch=False, anchor="center")
        self.playlists.column("Playlist", minwidth=140)
        for column, width in (("Faixas / locais", 110), ("Último download", 150)):
            self.playlists.column(column, width=width, minwidth=width, stretch=False)
        self.playlists.heading("Marcar", text="☐", anchor="center")
        for column in self.playlist_actions:
            self.playlists.heading(column, text="")
            self.playlists.column(column, width=38, minwidth=38, stretch=False, anchor="center")
        self.playlists.bind("<Button-1>", self.playlist_click)
        self.playlists.bind("<space>", self.toggle_playlist)
        self.playlists.bind("<Control-a>", lambda _: self.toggle_all_playlists())
        self.playlists.bind("<<TreeviewSelect>>", self.playlist_detail)
        self.playlists.bind("<Double-1>", self.playlist_details_dialog)
        for key, action in (
            ("<F5>", "Atualizar"),
            ("<Return>", "Detalhes"),
            ("<Control-g>", "Pasta"),
            ("<Delete>", "Remover"),
        ):
            self.playlists.bind(key, lambda _, a=action: self.playlist_row_action(a))
        ui.TreeTooltip(self.playlists, self.playlist_tooltip)
        self.playlist_empty = self.empty_state(
            self.playlists,
            "Adicione sua primeira playlist",
            "Cole um link público do Spotify. Depois, escolha o que baixar.",
            self.add_playlist_dialog,
            "Adicionar playlist",
        )
        self.playlist_info = tk.StringVar()
        self.download_hint = tk.StringVar()
        self.folder_hint = tk.StringVar()
        self.url = tk.StringVar()
        self.options_caption = tk.StringVar()
        ttk.Separator(footer).pack(fill="x", pady=14)
        actions = ttk.Frame(footer)
        actions.pack(fill="x", pady=(0, 16))
        self.selection_summary = tk.StringVar()
        ttk.Label(actions, textvariable=self.selection_summary, style="Muted.TLabel").pack(side="left")
        self.new_button = self.button(actions, "Baixar / retomar", lambda: self.sync(False), True)
        self.new_button.pack(side="right")
        self.mirror_button = self.button(
            actions, "Baixar e remover", lambda: self.sync(False, remove_missing=True)
        )
        self.mirror_button.pack(side="right", padx=8)
        self.force_button = self.button(actions, "Baixar tudo", lambda: self.sync(True))
        self.force_button.pack(side="right")

    def add_playlist_dialog(self):
        if self.busy:
            return
        window = ui.dialog(self.root, "Adicionar playlist")
        window.grab_set()
        body = ttk.Frame(window, padding=26)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Uma playlist para sua biblioteca", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="Cole um link público do Spotify. O áudio será baixado depois.",
            style="Muted.TLabel",
            wraplength=540,
        ).pack(anchor="w", pady=(6, 22))
        ttk.Label(body, text="Link da playlist").pack(anchor="w", pady=(0, 6))
        entry = ttk.Entry(body, textvariable=self.url)
        entry.pack(fill="x")
        ttk.Label(body, text="https://open.spotify.com/playlist/…", style="Muted.TLabel").pack(
            anchor="w", pady=(6, 22)
        )
        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(actions, text="Voltar", command=window.destroy).pack(side="left")

        def import_playlist():
            if not self.url.get().strip():
                entry.focus_set()
                return
            window.destroy()
            self.tabs.select(self.playlist_tab)
            self.add_playlist()

        ttk.Button(actions, text="Importar playlist", style="Accent.TButton", command=import_playlist).pack(
            side="right"
        )
        entry.bind("<Return>", lambda _: import_playlist())
        entry.focus_set()

    def playlist_details_dialog(self, event=None):
        if event and self.playlists.identify_region(event.x, event.y) == "heading":
            if self.playlists.identify_column(event.x) == "#1":
                return self.toggle_all_playlists()
            return "break"
        if event and self.playlists.identify_column(event.x) != "#2":
            return "break"
        self.playlist_detail()
        if self.playlists.selection():
            messagebox.showinfo("Detalhes da playlist", self.playlist_info.get(), parent=self.root)
        return "break"

    def toggle_all_playlists(self):
        items = self.playlists.get_children()
        self.mark_playlists(bool(items) and len(self.checked_playlists) != len(items))
        return "break"

    def playlist_click(self, event):
        column = self.playlists.identify_column(event.x)
        item = self.playlists.identify_row(event.y)
        if column == "#1":
            if self.playlists.identify_region(event.x, event.y) == "heading":
                self.playlists.focus_set()
                return self.toggle_all_playlists()
            return self.toggle_playlist(event)
        if item and column:
            name = self.playlists["columns"][int(column[1:]) - 1]
            if name in self.playlist_actions:
                return self.playlist_row_action(name, item)

    def playlist_row_action(self, action, item=None):
        item = item or self.playlists.focus()
        if self.busy or not item or not self.playlists.exists(item):
            return "break"
        self.playlists.focus_set()
        self.playlists.focus(item)
        self.playlists.selection_set(item)
        callbacks = {
            "Atualizar": lambda: self.refresh_selected(int(item)),
            "Detalhes": self.playlist_details_dialog,
            "Pasta": lambda: self.assign_group(int(item)),
            "Remover": lambda: self.remove_playlist(int(item)),
        }
        callbacks[action]()
        return "break"

    def playlist_tooltip(self, x, y):
        column = self.playlists.identify_column(x)
        if not column:
            return ""
        name = self.playlists["columns"][int(column[1:]) - 1]
        if name == "Marcar":
            return (
                "Marcar / desmarcar todas · Ctrl+A"
                if self.playlists.identify_region(x, y) == "heading"
                else "Marcar / desmarcar playlist · Espaço"
            )
        item = self.playlists.identify_row(y)
        if not item:
            return ""
        if name in self.playlist_actions:
            return "Aguarde a operação terminar" if self.busy else self.playlist_actions[name][1]
        if name == "Playlist":
            return self.playlist_rows[item]["name"]
        return ""

    def build_library(self):
        parent = self.library_tab
        head = self.heading(parent, "Biblioteca", "Suas músicas, arquivos e ajustes em um só lugar.")
        self.button(head, "Abrir pasta", self.open_downloads).pack(side="right", padx=(12, 0))
        bar = ttk.Frame(parent)
        bar.pack(fill="x")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *_: self.schedule_track_search())
        ttk.Label(bar, text="Buscar música ou artista").pack(side="left", padx=(0, 10))
        self.search_entry = ttk.Entry(bar, textvariable=self.search)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.track_filter = ttk.Combobox(
            bar, values=["Todas", "Disponíveis", "Pendentes", "Com falha"], state="readonly", width=16
        )
        self.track_filter.set("Todas")
        self.track_filter.pack(side="right", padx=(12, 0))
        self.track_filter.bind("<<ComboboxSelected>>", lambda _: self.refresh_tracks())
        filters = ttk.Frame(parent)
        filters.pack(fill="x", pady=(8, 0))
        ttk.Label(filters, text="Categoria").pack(side="left", padx=(0, 10))
        self.category_filter = ttk.Combobox(
            filters,
            values=["Todas as categorias", *CATEGORIES, "Outros", "Não classificada"],
            state="readonly",
            width=25,
        )
        self.category_filter.set("Todas as categorias")
        self.category_filter.pack(side="left")
        self.category_filter.bind("<<ComboboxSelected>>", lambda _: self.refresh_tracks())
        footer = ttk.Frame(parent)
        footer.pack(side="bottom", fill="x", pady=(16, 16))
        self.tracks = self.tree(
            parent,
            ("Marcar", "Música / artista", "Categoria", "Estado", "Playlists"),
            (44, 340, 145, 175, 78),
        )
        self.tracks.column("Marcar", width=44, minwidth=44, stretch=False, anchor="center")
        self.tracks.heading("Marcar", text="☐", anchor="center", command=self.toggle_all_tracks)
        self.tracks.bind("<Button-1>", self.track_check_click)
        self.tracks.bind("<space>", self.toggle_track)
        self.tracks.bind("<Control-a>", lambda _: self.toggle_all_tracks())
        self.tracks.bind("<<TreeviewSelect>>", self.track_detail)
        self.tracks.bind("<Double-1>", lambda _: self.track_editor())
        self.tracks.bind("<Return>", lambda _: self.track_editor())
        self.track_empty_title = tk.StringVar()
        self.track_empty_text = tk.StringVar()
        self.track_empty = ttk.Frame(self.tracks, padding=22)
        ttk.Label(self.track_empty, textvariable=self.track_empty_title, style="Section.TLabel").pack(
            pady=(0, 8)
        )
        ttk.Label(
            self.track_empty,
            textvariable=self.track_empty_text,
            style="Muted.TLabel",
            wraplength=430,
            justify="center",
        ).pack()
        self.detail = tk.StringVar()
        self.library_hint = tk.StringVar()
        self.category = tk.StringVar(value="Automática")
        bar = ttk.Frame(footer)
        bar.pack(fill="x")
        self.track_count = tk.StringVar()
        ttk.Label(bar, textvariable=self.track_count, style="Muted.TLabel").pack(side="left")
        self.edit_track_button = self.button(bar, "Detalhes e ajustes", self.track_editor)
        self.edit_track_button.pack(side="right")
        self.bulk_track_button = self.button(bar, "Ajustar marcadas…", self.bulk_track_editor)
        self.bulk_track_button.pack(side="right", padx=(0, 8))

    def refresh_track_checks(self):
        items = self.tracks.get_children()
        for item in items:
            self.tracks.set(item, "Marcar", "☑" if item in self.checked_tracks else "☐")
        count = len(self.checked_tracks)
        self.tracks.heading("Marcar", text="☑" if items and count == len(items) else "▣" if count else "☐")
        self.bulk_track_button.configure(state="normal" if count and not self.busy else "disabled")
        self.track_count.set(f"{len(items)} de {self.track_total} músicas · {count} marcadas")

    def toggle_all_tracks(self):
        if not self.busy:
            items = set(self.tracks.get_children())
            self.checked_tracks = set() if items == self.checked_tracks else items
            self.refresh_track_checks()
        return "break"

    def track_check_click(self, event):
        if (
            self.tracks.identify_region(event.x, event.y) == "cell"
            and self.tracks.identify_column(event.x) == "#1"
        ):
            item = self.tracks.identify_row(event.y)
            if item:
                self.tracks.focus(item)
                self.toggle_track()
            return "break"

    def toggle_track(self, _=None):
        item = self.tracks.focus()
        if not self.busy and item in self.track_rows:
            self.checked_tracks.symmetric_difference_update({item})
            self.refresh_track_checks()
        return "break"

    def bulk_track_editor(self):
        if self.busy or not self.checked_tracks:
            return
        selected = tuple(sorted(self.checked_tracks))
        window = ui.dialog(self.root, "Ajustar músicas marcadas")
        window.grab_set()
        body = ttk.Frame(window, padding=26)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"{len(selected)} músicas marcadas", style="Section.TLabel").pack(anchor="w")
        category = tk.StringVar(value="Escolha uma categoria")
        ttk.Label(body, text="Categoria").pack(anchor="w", pady=(18, 6))
        combo = ttk.Combobox(
            body, textvariable=category, values=["Automática", *CATEGORIES, "Outros"], state="readonly"
        )
        combo.pack(fill="x")
        ttk.Label(body, text=self.library_hint.get(), style="Muted.TLabel", wraplength=550).pack(
            anchor="w", pady=14
        )
        ttk.Label(
            body,
            text="Por artista também afeta outras músicas e futuras importações do mesmo artista principal.\nFonte do áudio e MP3 local continuam nos detalhes de cada música.",
            wraplength=550,
        ).pack(anchor="w", pady=(0, 14))
        actions = ttk.Frame(body)
        actions.pack(fill="x")

        def apply(artists=False):
            from tkinter import messagebox

            value = category.get()
            if artists and not messagebox.askyesno(
                "Categoria dos artistas",
                f"Aplicar {value} aos artistas principais das {len(selected)} músicas marcadas?\n"
                "Outras músicas desses artistas e futuras importações também serão afetadas. "
                "Correções individuais continuam tendo prioridade.",
                parent=window,
            ):
                return
            window.destroy()
            self.run(
                lambda: self.library.correct_categories(
                    selected, "" if value == "Automática" else value, artists=artists
                )
            )

        buttons = [
            ttk.Button(
                actions, text="Aplicar às faixas", style="Accent.TButton", command=apply, state="disabled"
            ),
            ttk.Button(actions, text="Aplicar aos artistas", command=lambda: apply(True), state="disabled"),
        ]
        for button in buttons:
            button.pack(side="left", padx=(0, 8))
        combo.bind("<<ComboboxSelected>>", lambda _: [button.configure(state="normal") for button in buttons])
        ttk.Button(body, text="Cancelar", command=window.destroy).pack(anchor="e", pady=(20, 0))
        window.bind("<Escape>", lambda _: window.destroy())

    def schedule_track_search(self):
        if getattr(self, "search_timer", None):
            self.root.after_cancel(self.search_timer)
        self.search_timer = self.root.after(180, self.refresh_tracks)

    def track_editor(self):
        selection = self.tracks.selection()
        if not selection or self.busy:
            return
        self.track_detail()
        row = self.track_rows[selection[0]]
        metadata = json.loads(row["metadata"])
        window = ui.dialog(self.root, "Detalhes e ajustes")
        window.grab_set()
        body = ttk.Frame(window, padding=26)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=metadata["name"], font=("Segoe UI", 18, "bold"), wraplength=560).pack(anchor="w")
        ttk.Label(body, text=metadata["artist"], style="Muted.TLabel", wraplength=560).pack(
            anchor="w", pady=(4, 18)
        )
        ttk.Label(body, textvariable=self.detail, wraplength=550, style="Muted.TLabel").pack(anchor="w")
        ttk.Separator(body).pack(fill="x", pady=18)
        ttk.Label(body, text="Categoria", style="Section.TLabel").pack(anchor="w")
        combo = ttk.Combobox(
            body, textvariable=self.category, values=["Automática", *CATEGORIES, "Outros"], state="readonly"
        )
        combo.pack(fill="x", pady=(8, 10))
        ttk.Label(body, text=self.library_hint.get(), style="Muted.TLabel", wraplength=550).pack(
            anchor="w", pady=(0, 12)
        )
        actions = ttk.Frame(body)
        actions.pack(fill="x")

        def action(callback):
            window.destroy()
            callback()

        ttk.Button(
            actions, text="Aplicar à faixa", style="Accent.TButton", command=lambda: action(self.correct)
        ).pack(side="left")
        ttk.Button(actions, text="Aplicar ao artista", command=lambda: action(self.correct_artist)).pack(
            side="left", padx=8
        )
        ttk.Separator(body).pack(fill="x", pady=18)
        audio = ttk.Frame(body)
        audio.pack(fill="x")
        ttk.Button(audio, text="Fonte do áudio…", command=lambda: action(self.audio_source)).pack(side="left")
        ttk.Button(audio, text="Associar MP3 local", command=lambda: action(self.import_local)).pack(
            side="left", padx=8
        )
        ttk.Button(body, text="Fechar", command=window.destroy).pack(anchor="e", pady=(20, 0))

    def build_export(self):
        parent = self.export_tab
        self.heading(parent, "Exportar", "Leve sua biblioteca para um pendrive ou outra pasta.")
        footer = ttk.Frame(parent)
        footer.pack(side="bottom", fill="x", pady=(16, 16))
        ttk.Label(footer, text="Você confere os arquivos antes de confirmar.", style="Muted.TLabel").pack(
            side="left"
        )
        self.export_button = self.button(footer, "Conferir e exportar", self.export, True)
        self.export_button.pack(side="right")
        body = ui.scroll_page(parent)
        destination = ui.section(body, "1. Destino", "Escolha uma pasta ou conecte um pendrive.")
        self.destination = tk.StringVar(value=self.store.setting("export_destination", ""))
        bar = ttk.Frame(destination)
        bar.pack(fill="x")
        entry = ttk.Entry(bar, textvariable=self.destination)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.controls.append(entry)
        self.button(bar, "Escolher pasta…", self.choose_export).pack(side="right")
        usb = ttk.Frame(destination)
        usb.pack(fill="x", pady=(12, 0))
        self.devices = ttk.Combobox(usb, state="readonly", width=35)
        self.devices.set("Nenhum dispositivo consultado")
        self.devices.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.devices.bind(
            "<<ComboboxSelected>>",
            lambda _: (
                self.destination.set(self.drive_list[self.devices.current()]["path"])
                if self.devices.current() >= 0
                else None
            ),
        )
        self.controls.append(self.devices)
        self.button(usb, "Detectar pendrives", self.detect_usb).pack(side="right")
        ttk.Separator(body).pack(fill="x")
        organization = ui.section(
            body,
            "2. Organização",
            "Inclui todas as playlists importadas. Conclua os downloads antes de exportar.",
        )
        self.layout = ttk.Combobox(organization, values=list(LAYOUTS.values()), state="readonly", width=30)
        self.layout.set(LAYOUTS[self.store.setting("output_layout", "playlists")])
        self.layout.pack(anchor="w")
        self.layout.bind("<<ComboboxSelected>>", self.change_layout)
        self.controls.append(self.layout)
        self.button(organization, "Editar pastas / grupos…", self.export_groups_dialog).pack(
            anchor="w", pady=(10, 0)
        )
        self.output_preview = tk.StringVar()
        preview = ui.section(body, "Prévia das pastas")
        ttk.Label(
            preview, textvariable=self.output_preview, style="Muted.TLabel", wraplength=670, justify="left"
        ).pack(anchor="w")
        ttk.Label(
            body,
            text="Só a pasta spoTano é gerenciada. Cópias antigas conhecidas vão para a lixeira do destino.",
            style="Muted.TLabel",
            wraplength=670,
        ).pack(anchor="w", pady=(0, 12))

    def export_groups_dialog(self):
        if self.busy:
            return
        window = ui.dialog(self.root, "Pastas e grupos da exportação", 660, 460)
        window.grab_set()
        body = ttk.Frame(window, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Escolha uma playlist para definir sua pasta ou grupo.", wraplength=600).pack(
            anchor="w"
        )
        tree = self.tree(body, ("Playlist", "Pasta / grupo"), (340, 210))
        for row in self.store.playlists():
            tree.insert("", "end", iid=str(row["id"]), values=(row["name"], row["output_group"] or "Padrão"))

        def edit():
            selected = tree.selection()
            if not selected:
                return
            previous = set(self.checked_playlists)
            window.destroy()
            self.checked_playlists = {int(selected[0])}
            self.assign_group()
            self.checked_playlists = previous
            self.refresh()

        ttk.Button(body, text="Editar pasta / grupo…", command=edit).pack(anchor="e", pady=(14, 0))

    def show_settings(self, index=0):
        self.tabs.select(self.settings_tab)
        self.settings_pages.select(index)

    def build_settings(self):
        parent = self.settings_tab
        self.heading(parent, "Configurações", "Deixe do seu jeito. As preferências são salvas ao alterar.")
        self.settings_pages = ttk.Notebook(parent)
        self.settings_pages.pack(fill="both", expand=True, pady=(0, 16))
        pages = []
        for title in ("Downloads", "Desempenho", "Manutenção", "Sobre"):
            page = ttk.Frame(self.settings_pages, padding=(12, 18, 0, 0))
            self.settings_pages.add(page, text=title)
            pages.append(ui.scroll_page(page))
        downloads, performance, maintenance, about = pages
        prepare = ui.section(
            downloads, "Componentes de download", "No primeiro uso, prepare FFmpeg e Deno. Requer internet."
        )
        self.button(prepare, "Preparar downloads", self.setup_downloads, True).pack(anchor="w")
        ttk.Separator(downloads).pack(fill="x")
        self.build_download_options(
            ui.section(
                downloads,
                "Personalizar download",
                "O modo simples mantém todas as músicas juntas, sem classificação ou tags extras.",
            )
        )
        self.build_performance_settings(performance)
        self.build_maintenance_settings(maintenance)
        self.build_about(about)

    def build_download_options(self, parent):
        self.option_vars = {
            key: tk.BooleanVar(value=value) for key, value in download_options(self.store).items()
        }
        self.option_labels = {key: tk.StringVar() for key in OPTIONS}
        self.option_summary = tk.StringVar()
        descriptions = {
            "categories": "Pastas por gênero",
            "artists": "Pastas por artista",
            "metadata": "Título, artista e álbum no MP3",
        }
        for key in OPTIONS:
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=6)
            check = ttk.Checkbutton(
                row,
                text=f"{ {'categories': 'Categoria', 'artists': 'Artistas', 'metadata': 'Metadados'}[key] } · {descriptions[key]}",
                variable=self.option_vars[key],
                command=self.save_download_options,
            )
            check.pack(side="left")
            self.controls.append(check)
            ttk.Label(row, textvariable=self.option_labels[key], style="Muted.TLabel").pack(side="right")
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=12)
        self.button(bar, "Marcar tudo", lambda: self.select_options(True)).pack(side="left")
        self.button(bar, "Desmarcar tudo", lambda: self.select_options(False)).pack(side="left", padx=8)
        ttk.Label(parent, textvariable=self.option_summary, style="Muted.TLabel", wraplength=670).pack(
            anchor="w", pady=(4, 10)
        )
        ttk.Label(
            parent,
            text="Tempos extras aproximados por música. Estimativas fixas; podem variar.",
            style="Muted.TLabel",
            wraplength=670,
        ).pack(anchor="w")
        self.button(
            parent, "Aplicar opções às músicas já baixadas", lambda: self.run(self.library.reorganize)
        ).pack(anchor="w", pady=(18, 0))
        self.refresh_option_labels()

    def build_performance_settings(self, parent):
        from .conversion import ENCODERS

        section = ui.section(
            parent,
            "Conversão MP3",
            "Rápida usa o encoder do Windows; Tradicional mantém o LAME. "
            "Ambos geram MP3 192 kbps, 44,1 kHz e estéreo, com codificação de áudio diferente.",
        )
        self.conversion_encoder = ttk.Combobox(
            section, values=list(ENCODERS.values()), state="readonly", width=30
        )
        self.conversion_encoder.set(
            ENCODERS.get(self.store.setting("conversion_encoder", "windows"), ENCODERS["windows"])
        )
        self.conversion_encoder.pack(anchor="w", pady=6)
        self.conversion_encoder.bind(
            "<<ComboboxSelected>>",
            lambda _: self.store.set_setting(
                "conversion_encoder",
                next(key for key, value in ENCODERS.items() if value == self.conversion_encoder.get()),
            ),
        )
        self.controls.append(self.conversion_encoder)
        ttk.Label(
            section,
            text="Se a conversão rápida falhar, o LAME assume automaticamente. Vale para os próximos downloads.",
            style="Muted.TLabel",
            wraplength=670,
        ).pack(anchor="w")
        section = ui.section(
            parent, "Paralelismo", "Ajuste quantas músicas podem baixar e converter ao mesmo tempo."
        )
        for name, title in (
            ("download_workers", "Downloads em paralelo"),
            ("conversion_workers", "Conversões MP3 em paralelo"),
        ):
            bar = ttk.Frame(section)
            bar.pack(fill="x", pady=6)
            ttk.Label(bar, text=title, width=31).pack(side="left")
            combo = ttk.Combobox(bar, values=["1", "2", "3", "4"], state="readonly", width=4)
            combo.set(str(self.store.setting(name, 2)))
            combo.pack(side="left")
            combo.bind(
                "<<ComboboxSelected>>", lambda _, k=name, c=combo: self.store.set_setting(k, int(c.get()))
            )
            setattr(self, name, combo)
            self.controls.append(combo)
        section = ui.section(
            parent,
            "Encontrar uma configuração",
            "Usa uma playlist de teste padrão, sem precisar importar músicas. Você pode trocar o endereço abaixo. "
            "Comece pelo rápido; use o completo para explorar todas as combinações. "
            "Só altera as preferências se você aplicar a configuração recomendada.",
        )
        bar = ttk.Frame(section)
        bar.pack(fill="x", pady=(0, 16))
        self.button(bar, "Teste rápido…", self.test_performance, True).pack(side="left")
        self.button(bar, "Teste completo…", lambda: self.test_performance("complete")).pack(
            side="left", padx=8
        )
        self.button(bar, "Último resultado", self.last_performance).pack(side="left", padx=8)
        ttk.Label(section, text="Playlist usada no teste").pack(anchor="w")
        self.performance_playlist = tk.StringVar(
            value=self.store.setting("performance_playlist", DEFAULT_PLAYLIST)
        )
        entry = ttk.Entry(section, textvariable=self.performance_playlist)
        entry.pack(fill="x", pady=(6, 8))
        self.controls.append(entry)
        bar = ttk.Frame(section)
        bar.pack(fill="x", pady=(0, 16))
        self.button(bar, "Salvar playlist de teste", self.save_performance_playlist).pack(side="left")
        self.button(bar, "Usar playlist padrão", self.reset_performance_playlist).pack(side="left", padx=8)
        bar = ttk.Frame(section)
        bar.pack(fill="x")
        ttk.Label(bar, text="Músicas por lote no teste completo").pack(side="left", padx=(0, 12))
        self.performance_sample = ttk.Combobox(bar, values=["4", "8"], state="readonly", width=4)
        self.performance_sample.set("8")
        self.performance_sample.pack(side="left")
        self.controls.append(self.performance_sample)
        ttk.Label(
            section,
            text="Rápido: 4 músicas, 2 rodadas por perfil, 8 a 10 lotes (32 a 40 downloads).\n"
            "Completo: 16 combinações, 3 rodadas, 48 lotes (192 ou 384 downloads).",
            style="Muted.TLabel",
            wraplength=670,
        ).pack(anchor="w", pady=(12, 0))

    def performance_dialog(self, summary, ranking, lines, best, apply, open_report):
        dialog = ui.dialog(self.root, "Resultado do teste de desempenho", 940, 640)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Resultado do teste de desempenho", font=("Segoe UI", 19, "bold")).pack(
            anchor="w"
        )
        ttk.Label(body, text=summary, wraplength=885).pack(fill="x", pady=(12, 8))
        ttk.Label(
            body,
            text="Ordem: menor tempo mediano primeiro. Resultados instáveis não sustentam a recomendação.",
            style="Muted.TLabel",
            wraplength=885,
        ).pack(anchor="w", pady=(0, 12))
        actions = ttk.Frame(body)
        actions.pack(side="bottom", fill="x", pady=(18, 0))
        ttk.Button(actions, text="Fechar", command=dialog.destroy).pack(side="left")
        ttk.Button(actions, text="Abrir relatório", command=open_report).pack(side="left", padx=8)
        ttk.Button(
            actions,
            text="Medições por rodada",
            command=lambda: self.review(
                "Medições do teste",
                "Tempos, falhas e método de comparação.",
                lines,
                open_report,
                "Abrir relatório",
            ),
        ).pack(side="left")

        def applied():
            if apply():
                dialog.destroy()

        button = ttk.Button(
            actions,
            text="Aplicar configuração recomendada",
            style="Accent.TButton",
            command=applied,
            state="normal" if best else "disabled",
        )
        button.pack(side="right")
        panel = ttk.Frame(body)
        panel.pack(fill="both", expand=True)
        columns = ("#", "Downloads", "Conversões", "Mediana", "Músicas/min", "Variação", "Resultado")
        table = ttk.Treeview(panel, columns=columns, show="headings", height=7)
        scroll = ttk.Scrollbar(panel, command=table.yview)
        scroll.pack(side="right", fill="y")
        table.configure(yscrollcommand=scroll.set)
        table.pack(fill="both", expand=True)
        for column, width in zip(columns, (40, 85, 95, 95, 105, 85, 340)):
            table.heading(column, text=column)
            table.column(column, width=width, minwidth=35, anchor="w" if column == "Resultado" else "center")
        position = 0
        selected = None
        for index, row in enumerate(ranking):
            eligible = row["eligible"]
            if eligible:
                position += 1
            recommended = best and (row["download_workers"], row["conversion_workers"]) == (
                best["download_workers"],
                best["conversion_workers"],
            )
            state = (
                ("Recomendada" if recommended else "Estável" if row["stable"] else "Instável")
                if eligible
                else row["reason"]
            )
            if row.get("initial_configuration"):
                state = "Inicial · " + state
            table.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    position if eligible else "—",
                    row["download_workers"],
                    row["conversion_workers"],
                    f"{row['seconds']:.1f}s" if eligible else "—",
                    f"{row['tracks_per_minute']:.1f}" if eligible else "—",
                    f"{row['spread']:.0%}" if eligible else "—",
                    state,
                ),
            )
            if recommended:
                selected = str(index)
        if selected is not None:
            table.selection_set(selected)
            table.see(selected)
        button.focus_set() if best else table.focus_set()

    def build_maintenance_settings(self, parent):
        section = ui.section(
            parent,
            "Biblioteca e backup",
            "O backup salva o catálogo e as preferências; os arquivos de áudio ficam separados.",
        )
        ttk.Label(section, text=str(self.library.music), style="Muted.TLabel", wraplength=670).pack(
            anchor="w", pady=(0, 12)
        )
        bar = ttk.Frame(section)
        bar.pack(fill="x")
        self.button(bar, "Abrir dados e lixeira", self.open_data).pack(side="left")
        self.button(bar, "Backup do catálogo…", self.backup).pack(side="left", padx=8)
        section = ui.section(parent, "Organizar a biblioteca")
        for text, callback in (
            ("Reclassificar gêneros", self.reclassify),
            ("Revisar faixas sem playlist", self.cleanup),
            ("Revisar cópias antigas…", self.review_copies),
        ):
            self.button(section, text, callback).pack(anchor="w", pady=4)
        section = ui.section(parent, "Diagnóstico e histórico")
        bar = ttk.Frame(section)
        bar.pack(fill="x")
        self.button(bar, "Diagnóstico", self.diagnostics).pack(side="left")
        self.button(bar, "Histórico", self.history).pack(side="left", padx=8)
        self.button(section, "Abrir métricas das execuções", self.open_metrics).pack(anchor="w", pady=(10, 0))
        self.button(section, "Limpar cache de correspondências…", self.clear_matches).pack(
            anchor="w", pady=(10, 0)
        )
        section = ui.section(
            parent,
            "Fontes de categorias · opcional",
            "A classificação funciona sem chave de API. As fontes só são usadas com Categoria habilitada.",
        )
        self.mb = tk.BooleanVar(value=self.store.setting("musicbrainz", True))
        check = ttk.Checkbutton(
            section,
            text="Complementar gêneros com MusicBrainz",
            variable=self.mb,
            command=lambda: self.store.set_setting("musicbrainz", self.mb.get()),
        )
        check.pack(anchor="w")
        self.controls.append(check)
        ttk.Label(section, text="Chave de API Last.fm", style="Muted.TLabel").pack(anchor="w", pady=(12, 6))
        bar = ttk.Frame(section)
        bar.pack(fill="x")
        self.lastfm_key = ttk.Entry(bar, show="*")
        self.lastfm_key.insert(0, self.store.setting("lastfm_api_key", ""))
        self.lastfm_key.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.controls.append(self.lastfm_key)
        self.button(bar, "Salvar chave", self.save_lastfm).pack(side="right")
        ttk.Label(
            section,
            text="Para remover, limpe o campo e salve. A chave fica no catálogo local e em seu backup.",
            style="Muted.TLabel",
            wraplength=670,
        ).pack(anchor="w", pady=(8, 0))

    def save_lastfm(self):
        self.store.set_setting("lastfm_api_key", self.lastfm_key.get().strip())
        self.status.set(
            "Chave Last.fm salva." if self.lastfm_key.get().strip() else "Chave Last.fm removida."
        )

    def build_about(self, parent):
        ui.section(
            parent,
            f"spoTano {__version__}",
            "Sua música, com você. Biblioteca local para acompanhar playlists e levar seus MP3s.",
        )
        ui.section(
            parent,
            "Áudio",
            "MP3 · 192 kbps · 44,1 kHz · estéreo · sem capa.\nTags ID3v2.3 quando Metadados estiver habilitado.",
        )
        ui.section(
            parent,
            "Fontes",
            "O Spotify fornece os dados das músicas; o áudio vem de outros provedores. Baixe somente com autorização e quando o provedor permitir.",
        )
        ui.section(
            parent,
            "Atalhos",
            "Ctrl+1 Playlists · Ctrl+2 Biblioteca · Ctrl+3 Exportar\nCtrl+N Adicionar playlist · Ctrl+F Buscar · Ctrl+, Configurações\nEspaço marca a playlist · Enter abre os ajustes da música",
        )
        self.button(parent, "Ajuda e atualizações ↗", self.open_help).pack(anchor="w", pady=10)
        ttk.Label(parent, text="GPL-3.0-or-later · baseado no spotDL 4.6.0", style="Muted.TLabel").pack(
            anchor="w", pady=12
        )

    def setup_downloads(self):
        self.run(
            self.library.provider.setup,
            lambda result: messagebox.showinfo("Componentes prontos", str(result), parent=self.root),
        )

    def build_activity(self):
        self.activity = ttk.Frame(self.root, padding=(28, 14, 28, 16))
        self.activity.grid(row=1, column=1, sticky="ew")
        self.activity.columnconfigure(0, weight=1)
        ttk.Separator(self.activity).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.status = tk.StringVar(value="Pronto para sua próxima playlist.")
        self.status_label = ttk.Label(self.activity, textvariable=self.status, wraplength=620)
        self.status_label.grid(row=1, column=0, sticky="w")
        actions = ttk.Frame(self.activity)
        actions.grid(row=1, column=1, rowspan=2, sticky="ne", padx=(12, 0))
        self.stop = ttk.Button(actions, text="Cancelar", command=self.cancel_operation, state="disabled")
        self.stop.pack(side="left")
        self.log_size = ttk.Button(actions, text="Ver atividade", command=self.toggle_logs)
        self.log_size.pack(side="left", padx=(6, 0))
        self.batch_status = tk.StringVar()
        ttk.Label(self.activity, textvariable=self.batch_status, style="Muted.TLabel", wraplength=620).grid(
            row=2, column=0, sticky="w", pady=(5, 8)
        )
        self.progress = ttk.Progressbar(
            self.activity, mode="determinate", style="Download.Horizontal.TProgressbar"
        )
        self.progress.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.logs_panel = ttk.Frame(self.activity)
        self.logs_panel.columnconfigure(0, weight=1)
        self.logs_panel.rowconfigure(1, weight=1)
        bar = ttk.Frame(self.logs_panel)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(12, 8))
        self.open_downloads_button = ttk.Button(
            bar, text="Abrir pasta dos downloads", command=self.open_downloads
        )
        self.open_downloads_button.pack(side="left")
        ttk.Button(bar, text="Salvar logs…", command=self.save_logs).pack(side="right")
        self.log_text = tk.Text(
            self.logs_panel,
            height=7,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            bg="white",
            fg=ui.INK,
            relief="flat",
            padx=10,
            pady=8,
            selectbackground="#d8eadc",
        )
        self.log_text.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.logs_panel, command=self.log_text.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)
        self.logs_visible = False
        self.activity.bind(
            "<Configure>", lambda event: self.status_label.configure(wraplength=max(240, event.width - 280))
        )
