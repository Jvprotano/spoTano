"""Cached genre evidence, recording catalogues and disambiguated artist identities."""

import json
import os
import re
import threading
import time
import unicodedata
from collections import Counter

GENRE_VERSION = 4

CATEGORIES = {
    "Sertanejo": ("sertanejo", "sertaneja", "modao", "moda de viola", "country brasileiro"),
    "Pagode e Samba": ("pagode", "samba", "sambass"),
    "Forro e Piseiro": ("forro", "piseiro", "pisadinha", "baiao", "xote"),
    "Funk Brasileiro": ("funk carioca", "funk brasileiro", "baile funk", "funk paulista", "brega funk",
                         "agrofunk", "funknejo", "mandelao", "funk de bh"),
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
        "dance",
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
    scores = {}
    broad = {"latin", "pop", "rock", "funk", "folk", "electronic", "dance"}
    for value in genres or []:
        genre = normalize(value.get("name", "") if isinstance(value, dict) else value)
        weight = max(0, float(value.get("count", value.get("weight", 1)))) if isinstance(value, dict) else 1
        matches = []
        for category, terms in CATEGORIES.items():
            terms = [term for term in terms if re.search(r"(?<![a-z0-9])" + re.escape(term)
                                                       + r"(?![a-z0-9])", genre)]
            if terms:
                matches.append((category, max(1 if term in broad else 2 for term in terms)))
        # A specific Brazilian style beats an incidental broad family tag.
        if matches:
            maximum = max(specificity for _, specificity in matches)
            for category, specificity in matches:
                if specificity == maximum:
                    scores[category] = scores.get(category, 0) + weight * specificity
    for category, terms in CATEGORIES.items():
        if scores.get(category, 0) and scores[category] == max(scores.values()):
            return category
    return "Outros"


def artist_key(value):
    value = re.sub(r"(?<=\w)\s+(?:and|e)\s+(?=\w)|\s*&\s*", " ", normalize(value))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def claim_values(entity, prop):
    return [
        claim["mainsnak"]["datavalue"]["value"]
        for claim in entity.get("claims", {}).get(prop, [])
        if claim.get("rank") != "deprecated" and "datavalue" in claim.get("mainsnak", {})
    ]


class GenreResolver:
    def __init__(self, store, progress=lambda message: None, cancel=None, force=False):
        self.store, self.progress = store, progress
        self.cancel = cancel or threading.Event()
        self.lock = threading.Lock()
        self.last_request = {}
        self.failures = {}
        self.memory = {}
        self.memory_failures = {}
        self.genre_labels = {}
        self.artist_id = ""
        self.local = threading.local()
        self.key_locks, self.source_locks = {}, {}
        self.force = force

    @property
    def artist_id(self):
        return getattr(getattr(self, "local", None), "artist_id", "")

    @artist_id.setter
    def artist_id(self, value):
        if hasattr(self, "local"):
            self.local.artist_id = value

    def artist_identity(self, metadata):
        return "spotify:" + metadata["artist_id"] if metadata.get("artist_id") else artist_key(metadata["artist"])

    def wait(self, seconds):
        from .provider import Cancelled

        if self.cancel.wait(max(0, seconds)):
            raise Cancelled("Operação cancelada durante a consulta de gêneros.")

    def request(self, source, url, params):
        with self.lock:
            source_lock = self.source_locks.setdefault(source, threading.Lock())
        with source_lock:
            return self._request(source, url, params)

    def _request(self, source, url, params):
        import requests

        if self.failures.get(source, 0) >= 3:
            raise requests.RequestException(
                f"{source}: consultas suspensas após falhas consecutivas neste lote"
            )
        interval = 3.1 if source == "iTunes" else 1.1
        for attempt in range(1 if source == "iTunes" else 2):
            self.wait(interval - (time.monotonic() - self.last_request.get(source, 0)))
            self.last_request[source] = time.monotonic()
            try:
                response = requests.get(
                    url,
                    params=params,
                    timeout=5 if source == "iTunes" else 8,
                    headers={
                        "User-Agent": "spoTano/1.2 (https://github.com/Jvprotano/spoTano)",
                    },
                )
                if source != "iTunes" and response.status_code in (429, 502, 503, 504) and attempt == 0:
                    self.progress(
                        f"Gêneros · {source}: HTTP {response.status_code}; aguardando para tentar uma vez mais."
                    )
                    self.wait(1.1)
                    continue
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict) or "error" in data:
                    raise ValueError(f"Resposta inválida de {source}")
                self.failures[source] = 0
                return data
            except (requests.RequestException, ValueError):
                self.failures[source] = self.failures.get(source, 0) + 1
                raise

    def musicbrainz(self, artist):
        self.artist_id = ""
        data = self.request(
            "MusicBrainz",
            "https://musicbrainz.org/ws/2/artist/",
            {
                "query": 'artist:"' + artist.replace('"', "") + '"',
                "fmt": "json",
                "limit": 10,
            },
        )
        candidates = []
        for row in data.get("artists", []):
            names = [row.get("name", ""), *[a.get("name", "") for a in row.get("aliases", [])]]
            if any(
                artist_key(name) == artist_key(artist) for name in names
            ):
                candidates.append(row)
        # Search score measures popularity/relevance, not identity. A lower-scored
        # namesake (e.g. the Brazilian BK) must participate in disambiguation.
        short_name = len(artist_key(artist).replace(" ", "")) <= 3
        if len(candidates) != 1 or short_name:
            spotify_id = getattr(self.local, "spotify_id", None)
            if not spotify_id or not re.fullmatch(r"[A-Za-z0-9]{22}", spotify_id):
                return []
            import requests

            try:
                relation = self.request("MusicBrainz", "https://musicbrainz.org/ws/2/url/",
                                        {"resource": "https://open.spotify.com/artist/" + spotify_id,
                                         "inc": "artist-rels", "fmt": "json"})
            except requests.HTTPError as exc:
                if exc.response is None or exc.response.status_code != 404:
                    raise
                return []
            identities = {row["artist"]["id"] for row in relation.get("relations", [])
                          if row.get("artist", {}).get("id")}
            if len(identities) != 1:
                return []
            self.artist_id = identities.pop()
            selected = self.request("MusicBrainz", "https://musicbrainz.org/ws/2/artist/" + self.artist_id,
                                    {"inc": "tags", "fmt": "json"})
        elif int(candidates[0].get("score", 0)) >= 95:
            selected = candidates[0]
            self.artist_id = selected.get("id", "")
        else:
            return []
        return [{"name": tag["name"], "count": int(tag.get("count", 0))}
                for tag in selected.get("tags", []) if int(tag.get("count", 0)) > 0]

    def wikidata(self, artist, spotify_id):
        endpoint = "https://www.wikidata.org/w/api.php"
        search = self.request(
            "Wikidata",
            endpoint,
            {
                "action": "wbsearchentities",
                "search": artist,
                "language": "pt",
                "format": "json",
                "limit": 5,
            },
        )
        ids = [row["id"] for row in search.get("search", []) if re.fullmatch(r"Q\d+", row.get("id", ""))]
        if not ids:
            return []
        entities = self.request(
            "Wikidata",
            endpoint,
            {
                "action": "wbgetentities",
                "ids": "|".join(ids),
                "props": "claims|labels|aliases",
                "languages": "pt|en",
                "format": "json",
            },
        ).get("entities", {})
        candidates = []
        for entity in entities.values():
            names = [label["value"] for label in entity.get("labels", {}).values()]
            names += [label["value"] for group in entity.get("aliases", {}).values() for label in group]
            if not any(artist_key(name) == artist_key(artist) for name in names):
                continue
            mb_ids, sp_ids = claim_values(entity, "P434"), claim_values(entity, "P1902")
            if (self.artist_id and mb_ids and self.artist_id not in mb_ids) or (
                spotify_id and sp_ids and spotify_id not in sp_ids
            ):
                continue
            if len(artist_key(artist).replace(" ", "")) <= 3 and not (
                (self.artist_id and self.artist_id in mb_ids) or (spotify_id and spotify_id in sp_ids)
            ):
                continue
            kinds = [value.get("id") for value in claim_values(entity, "P31") if isinstance(value, dict)]
            if "Q215380" in kinds or mb_ids or sp_ids:
                candidates.append(entity)
        if len(candidates) != 1:
            return []
        genre_ids = [
            value["id"]
            for value in claim_values(candidates[0], "P136")
            if isinstance(value, dict) and re.fullmatch(r"Q\d+", value.get("id", ""))
        ]
        missing = [genre for genre in genre_ids if genre not in self.genre_labels]
        if missing:
            labels = self.request(
                "Wikidata",
                endpoint,
                {
                    "action": "wbgetentities",
                    "ids": "|".join(missing),
                    "props": "labels",
                    "languages": "pt|en",
                    "format": "json",
                },
            ).get("entities", {})
            for genre, entity in labels.items():
                self.genre_labels[genre] = [label["value"] for label in entity.get("labels", {}).values()]
        return [label for genre in genre_ids for label in self.genre_labels.get(genre, [])]

    def lastfm(self, metadata, track=False):
        params = {"method": "track.getTopTags" if track else "artist.getTopTags",
                  "artist": metadata["artist"], "format": "json",
                  "api_key": self.store.setting("lastfm_api_key", "") or os.environ.get("LASTFM_API_KEY", "")}
        if not params["api_key"]:
            return []
        if track:
            params["track"] = metadata["name"]
        data = self.request("Last.fm", "https://ws.audioscrobbler.com/2.0/", params)
        tags = data.get("toptags", {}).get("tag", [])
        return [{"name": tag.get("name", ""), "count": int(tag.get("count", 0))}
                for tag in tags if int(tag.get("count", 0)) > 0]

    def resolve(self, metadata):
        known = classify(metadata.get("track_genres") or metadata.get("genres"))
        artist = metadata.get("artist", "")
        if not artist:
            return known
        override = self.store.rows("SELECT category FROM artist_categories WHERE artist=?",
                                   (self.artist_identity(metadata),))
        if override:
            self.track_evidence(metadata, override[0]["category"], "correção por artista")
            return override[0]["category"]
        if known != "Outros" or not self.store.setting("musicbrainz", True):
            self.track_evidence(metadata, known, "metadados")
            return known
        from .matching import fingerprint

        prior = self.store.rows("SELECT evidence FROM genre_evidence WHERE track_id=?",
                                (metadata.get("song_id", ""),))
        if prior and not self.force:
            data = json.loads(prior[0]["evidence"])
            ttl = 86400 if data.get("category") == "Outros" else 90 * 86400
            if (data.get("scope") == "track" and data.get("version") == GENRE_VERSION
                    and data.get("fingerprint") == fingerprint(metadata)
                    and time.time() - data.get("fetched_at", 0) < ttl):
                return data["category"]
        category = self.resolve_artist(metadata)
        source = "artista"
        failed = getattr(self.local, "lookup_failed", False)
        if category == "Outros":
            try:
                result = self.itunes(metadata)
                if result:
                    category, source = result["category"], "iTunes faixa"
                    self.progress(f"Gênero · {metadata['name']}: {category} ({source}).")
                    self.track_evidence(metadata, category, source,
                                        **{key: value for key, value in result.items() if key != "category"})
                    return category
            except Exception as exc:
                from .provider import Cancelled
                from .telemetry import sanitize

                if isinstance(exc, Cancelled):
                    raise
                failed = True
                self.progress(f"Gênero · iTunes indisponível: {sanitize(str(exc))[:180]}")
        if category == "Outros":
            # Limit fallback work. Do not assign a multi-artist recording to the
            # first recognizable collaborator when evidence disagrees.
            collaborators = metadata.get("artist_details", [])[1:]
            votes, seen = Counter(), {self.artist_identity(metadata)}
            for other in collaborators[:3]:
                if other.get("name"):
                    identity = {**metadata, "artist": other["name"], "artist_id": other.get("id")}
                    key = self.artist_identity(identity)
                    if key in seen:
                        continue
                    seen.add(key)
                    vote = self.resolve_artist(identity)
                    failed |= getattr(self.local, "lookup_failed", False)
                    if vote != "Outros":
                        votes[vote] += 1
            if len(votes) == 1 and (sum(votes.values()) >= 2 or len(collaborators) == 1):
                category = next(iter(votes))
                source = "colaboradores concordantes"
        if category == "Outros" and (self.store.setting("lastfm_api_key", "") or os.environ.get("LASTFM_API_KEY")):
            try:
                tags = self.lastfm(metadata, track=True)
                category = classify(tags)
                source = "Last.fm faixa"
            except Exception as exc:
                from .provider import Cancelled
                from .telemetry import sanitize

                if isinstance(exc, Cancelled):
                    raise
                failed = True
                self.progress(f"Gênero · Last.fm faixa indisponível: {sanitize(str(exc))}")
        if category != "Outros" or not failed:
            self.track_evidence(metadata, category, source)
        return category

    def track_evidence(self, metadata, category, source, **data):
        from .matching import fingerprint

        self.evidence(metadata, {**data, "source": source, "category": category, "scope": "track",
                                 "fingerprint": fingerprint(metadata), "fetched_at": time.time()})

    def needs_refresh(self, metadata):
        from .matching import fingerprint

        rows = self.store.rows("SELECT evidence FROM genre_evidence WHERE track_id=?",
                               (metadata.get("song_id", ""),))
        if not rows:
            return True
        data = json.loads(rows[0]["evidence"])
        return data.get("version") != GENRE_VERSION or data.get("fingerprint") != fingerprint(metadata)

    def itunes(self, metadata):
        from .catalogue import catalogue_match
        from .matching import clean_title, fingerprint

        if not metadata.get("name") or not metadata.get("duration"):
            return None
        key = "itunes-track:" + fingerprint(metadata)
        artist_key_ = "itunes-artist:" + self.artist_identity(metadata)
        with self.lock:
            query_lock = self.key_locks.setdefault(artist_key_, threading.Lock())
        while not query_lock.acquire(timeout=0.1):
            self.wait(0)
        try:
            catalogue = []
            if not self.force:
                for row in self.store.rows("SELECT * FROM genre_queries WHERE key IN (?,?)", (key, artist_key_)):
                    ttl = 86400 if row["key"] == key else 30 * 86400
                    if time.time() - row["fetched_at"] < ttl:
                        if row["key"] == key:
                            return catalogue_match(metadata, json.loads(row["payload"]))
                        catalogue = json.loads(row["payload"])
                match = catalogue_match(metadata, catalogue)
                if match:
                    return match
            self.progress(f"Gênero · consultando iTunes para a faixa: {metadata['name']}…")
            data = self.request("iTunes", "https://itunes.apple.com/search",
                                {"term": metadata["artist"] + " " + clean_title(metadata["name"]),
                                 "entity": "song", "media": "music", "country": "br", "limit": 25})
            rows = data.get("results")
            if not isinstance(rows, list):
                raise ValueError("Resposta inválida do catálogo iTunes")
            # Retain only classification fields, never previews or artwork.
            fields = ("trackId", "kind", "artistName", "trackName", "trackTimeMillis", "primaryGenreName")
            rows = [{field: row.get(field) for field in fields} for row in rows if isinstance(row, dict)]
            merged = {row["trackId"]: row for row in catalogue + rows if row.get("trackId")}
            with self.store.connect() as db:
                db.executemany("INSERT OR REPLACE INTO genre_queries VALUES(?,?,?)",
                               [(key, json.dumps(rows), time.time()),
                                (artist_key_, json.dumps(list(merged.values())[-200:]), time.time())])
            return catalogue_match(metadata, rows)
        finally:
            query_lock.release()

    def evidence(self, metadata, data):
        if metadata.get("song_id"):
            with self.store.connect() as db:
                db.execute("INSERT OR REPLACE INTO genre_evidence VALUES(?,?)",
                           (metadata["song_id"], json.dumps({"version": GENRE_VERSION, **data})))

    def resolve_artist(self, metadata):
        artist = metadata["artist"]
        key = self.artist_identity(metadata)
        with self.lock:
            artist_lock = self.key_locks.setdefault(key, threading.Lock())
        # Only identical artists wait for each other. Cache hits for other artists stay immediate.
        while not artist_lock.acquire(timeout=0.1):
            self.wait(0)
        try:
            self.local.spotify_id = metadata.get("artist_id")
            self.artist_id = ""
            self.local.lookup_failed = False
            if key in self.memory:
                self.local.lookup_failed = self.memory_failures.get(key, False)
                return self.memory[key]
            cached = self.store.rows(
                "SELECT * FROM genre_cache WHERE artist IN (?,?) ORDER BY fetched_at DESC", (key, artist)
            )
            for row in cached:
                data = json.loads(row["genres"])
                tags = data.get("tags", []) if isinstance(data, dict) else data
                category = classify(tags)
                # Old empty caches had a 90-day TTL. Retry them with the improved sources.
                version_ok = isinstance(data, dict) and data.get("version") == GENRE_VERSION
                ttl = 90 * 86400 if category != "Outros" else 86400 if isinstance(data, dict) else 0
                if not self.force and version_ok and time.time() - row["fetched_at"] < ttl:
                    self.progress(f"Gênero · {artist}: {category} (cache).")
                    self.memory[key] = category
                    self.evidence(metadata, {"source": "cache", "tags": tags, "category": category})
                    return category
            import requests

            tags, sources, failed = [], [], False
            for source, lookup in (
                ("MusicBrainz", lambda: self.musicbrainz(artist)),
                ("Wikidata", lambda: self.wikidata(artist, metadata.get("artist_id"))),
                ("Last.fm", lambda: self.lastfm(metadata)),
            ):
                if source == "Last.fm" and not (self.store.setting("lastfm_api_key", "")
                                                 or os.environ.get("LASTFM_API_KEY")):
                    continue
                self.progress(f"Gênero · consultando {source}: {artist}…")
                try:
                    tags = lookup()
                except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
                    failed = True
                    from .telemetry import sanitize

                    self.progress(f"Gênero · {artist}: falha em {source}: {sanitize(str(exc))[:180]}.")
                    continue
                category = classify(tags)
                if category != "Outros":
                    sources.append(source)
                    break
            category = classify(tags)
            if category != "Outros" or not failed:
                with self.store.connect() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO genre_cache VALUES(?,?,?)",
                        (
                            key,
                            json.dumps({"version": GENRE_VERSION, "tags": tags, "sources": sources,
                                        "artist_id": metadata.get("artist_id"), "mbid": self.artist_id}),
                            time.time(),
                        ),
                    )
            self.memory[key] = category
            self.memory_failures[key] = failed
            self.local.lookup_failed = failed
            origin = (
                ", ".join(sources)
                if sources
                else "consultas indisponíveis"
                if failed
                else "sem evidência suficiente"
            )
            self.progress(f"Gênero · {artist}: {category} ({origin}).")
            self.evidence(metadata, {"source": origin, "tags": tags, "category": category,
                                     "artist_id": metadata.get("artist_id"), "mbid": self.artist_id})
            return category
        finally:
            artist_lock.release()
