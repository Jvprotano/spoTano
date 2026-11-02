"""Open the redesigned desktop with an isolated catalog, without network access.

Use --empty for onboarding; --minimum for the 1000x760 layout. No personal data
is read or changed. The deterministic provider is used only by this preview.
"""

import argparse
import tempfile
import tkinter as tk
from pathlib import Path

from spotano.db import Store
from spotano.gui import App
from spotano.library import Library


class PreviewProvider:
    def playlist(self, url):
        return {
            "name": "Na estrada · As melhores para viajar"
            if "A" * 22 in url
            else "Rock, clássicos e novas descobertas",
            "total": 12,
            "tracks": [
                {"song_id": letter * 22, "name": title, "artist": artist, "genres": []}
                for letter, title, artist in zip(
                    "ABCDEFGHIJKL",
                    [
                        "Tocando em Frente",
                        "Tempo Perdido",
                        "Evidências",
                        "O Sol",
                        "Velha Infância",
                        "Pais e Filhos",
                        "Anunciação",
                        "Dias de Luta, Dias de Glória",
                        "Lanterna dos Afogados",
                        "Pra Você Guardei o Amor",
                        "Uma música com um título muito longo — edição especial ao vivo em São Paulo (versão completa)",
                        "A Estrada",
                    ],
                    [
                        "Almir Sater",
                        "Legião Urbana",
                        "Chitãozinho & Xororó",
                        "Vitor Kley",
                        "Tribalistas",
                        "Legião Urbana",
                        "Alceu Valença",
                        "Charlie Brown Jr.",
                        "Os Paralamas do Sucesso",
                        "Nando Reis & Ana Cañas",
                        "Artista com nome extenso e participações especiais",
                        "Cidade Negra",
                    ],
                )
            ],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--minimum", action="store_true")
    parser.add_argument("--page", type=int, default=0, choices=range(4))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="spotano-design-preview-") as directory:
        store = Store(Path(directory))
        provider = PreviewProvider()
        if not args.empty:
            library = Library(store, provider)
            for letter in "AB":
                library.import_playlist("https://open.spotify.com/playlist/" + letter * 22)
            with store.connect() as db:
                db.execute("INSERT INTO download_pending VALUES(1,?)", ("B" * 22,))
                db.execute(
                    "UPDATE tracks SET status='error',error=? WHERE id=?",
                    (
                        "Não foi possível localizar uma gravação compatível. Use Fonte do áudio para escolher outra.",
                        "C" * 22,
                    ),
                )
        root = tk.Tk()
        app = App(root, Path(directory))
        app.library.provider = provider
        root.title("spoTano · Prévia de interface" + (" · Vazia" if args.empty else ""))
        if args.minimum:
            root.geometry("1000x760")
        app.tabs.select(args.page)
        root.mainloop()


if __name__ == "__main__":
    main()
