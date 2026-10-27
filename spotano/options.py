"""Optional download work and fixed, approximate per-track costs."""

OPTIONS = {
    "categories": "Categoria: classificar e criar pastas por gênero",
    "artists": "Artistas: criar pastas por artista",
    "metadata": "Metadados: título, artistas, álbum e ano (sem capa)",
}
SIMPLE = dict.fromkeys(OPTIONS, False)

# Reference logs reviewed on 2026-10-27, not measurements from user catalogs.
# Genre work: about 84 seconds across 10 tracks, including a multi-artist case.
# Folder work is a coarse sub-second estimate; tags historically averaged 0.119s.
OPTION_COSTS = {
    "categories": "+~8 s/música",
    "artists": "+<1 s/música",
    "metadata": "+~0,1 s/música",
}


def download_options(store):
    saved = store.setting("download_options", SIMPLE)
    return {key: bool(saved.get(key, False)) for key in OPTIONS}


def option_costs():
    """Return display estimates without opening databases or execution logs."""
    return OPTION_COSTS.copy()
