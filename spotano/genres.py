"""Broad genre mapping and optional cached MusicBrainz artist tags."""

import json
import re
import time
import unicodedata

CATEGORIES = {
    "Sertanejo": ("sertanejo", "modao", "moda de viola", "country brasileiro"),
    "Pagode e Samba": ("pagode", "samba", "sambass"),
    "Forro e Piseiro": ("forro", "piseiro", "pisadinha", "baiao", "xote"),
    "Funk Brasileiro": ("funk carioca", "funk brasileiro", "baile funk", "funk paulista", "brega funk"),
    "MPB": ("mpb", "bossa nova", "tropicalia", "musica popular brasileira"),
    "Rap e Hip-Hop": ("hip hop", "hip-hop", "rap", "trap", "drill", "boom bap"),
    "Reggae": ("reggae", "ska", "dub", "dancehall"),
    "Eletronica": (
        "electronic",
        "eletronica",
        "edm",
        "house",
        "techno",
        "trance",
        "dubstep",
        "drum and bass",
    ),
    "Rock e Metal": ("rock", "metal", "punk", "grunge", "hardcore", "shoegaze"),
    "Gospel": ("gospel", "worship", "christian", "crista", "religious"),
    "Jazz e Blues": ("jazz", "blues", "swing", "bebop"),
    "Classica": ("classical", "classica", "orchestra", "opera", "baroque"),
    "Latina": ("reggaeton", "salsa", "bachata", "cumbia", "latin", "merengue"),
    "Country e Folk": ("country", "folk", "bluegrass", "americana"),
    "Soul e RnB": ("soul", "r&b", "rnb", "motown", "funk"),
    "Pop": ("pop", "dance pop", "k-pop", "j-pop", "indie pop"),
}


def normalize(text):
    return unicodedata.normalize("NFKD", text.casefold()).encode("ascii", "ignore").decode()


def classify(genres):
    values = [normalize(g) for g in (genres or [])]
    for category, terms in CATEGORIES.items():
        if any(
            re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", g)
            for g in values
            for term in terms
        ):
            return category
    return "Outros"


class GenreResolver:
    def __init__(self, store):
        self.store = store
        self.last_request = 0
        self.failures = 0

    def resolve(self, metadata):
        known = classify(metadata.get("genres"))
        if known != "Outros" or not self.store.setting("musicbrainz", True):
            return known
        artist = metadata.get("artist", "")
        if not artist:
            return known
        cached = self.store.rows("SELECT * FROM genre_cache WHERE artist=?", (artist,))
        if cached and time.time() - cached[0]["fetched_at"] < 90 * 86400:
            return next(
                (
                    category
                    for tag in json.loads(cached[0]["genres"])
                    if (category := classify([tag])) != "Outros"
                ),
                "Outros",
            )
        if self.failures >= 3:
            return "Outros"
        import requests

        try:
            time.sleep(max(0, 1.1 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            response = requests.get(
                "https://musicbrainz.org/ws/2/artist/",
                params={"query": 'artist:"' + artist.replace('"', "") + '"', "fmt": "json", "limit": 3},
                headers={"User-Agent": "spoTano/1.0 (https://github.com/Jvprotano/spoTano)"},
                timeout=12,
            )
            response.raise_for_status()
            results = response.json().get("artists", [])
            match = next(
                (
                    r
                    for r in results
                    if normalize(r["name"]) == normalize(artist) and int(r.get("score", 0)) >= 95
                ),
                {},
            )
            tags = [
                t["name"]
                for t in sorted(match.get("tags", []), key=lambda t: int(t.get("count", 0)), reverse=True)
                if int(t.get("count", 0)) > 0
            ]
            with self.store.connect() as db:
                db.execute(
                    "INSERT OR REPLACE INTO genre_cache VALUES(?,?,?)",
                    (artist, json.dumps(tags), time.time()),
                )
            return next((category for tag in tags if (category := classify([tag])) != "Outros"), "Outros")
        except (requests.RequestException, ValueError, KeyError):
            self.failures += 1
            return "Outros"
