"""Bounded metadata-only matching. Never extract videos to count views."""

import hashlib
import json
import re
import time
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlparse

MATCH_VERSION = 1


def words(value):
    value = "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    )
    return " ".join(re.findall(r"[^\W_]+", value, re.UNICODE))


def canonical_youtube(value):
    parsed = urlparse(value.strip())
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("Use uma URL https do YouTube para a gravação completa.")
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        video = parsed.path.strip("/")
    elif host in {"youtube.com", "www.youtube.com", "music.youtube.com", "m.youtube.com"}:
        video = parse_qs(parsed.query).get("v", [""])[0] if parsed.path == "/watch" else ""
    else:
        video = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video):
        raise ValueError("Use o link de um vídeo do YouTube, com identificador válido.")
    return "https://www.youtube.com/watch?v=" + video


def fingerprint(metadata):
    identity = {
        key: metadata.get(key)
        for key in ("song_id", "name", "artist", "artist_id", "artists", "duration", "isrc", "album_name")
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def editions(title):
    text = words(title)
    groups = {
        "live": ("ao vivo", "live", "concert"),
        "acoustic": ("acustico", "acustica", "acoustic", "unplugged"),
        "remix": ("remix",),
        "remaster": ("remaster", "remastered"),
        "cover": ("cover", "karaoke", "instrumental", "tribute"),
        "speed": ("slowed", "reverb", "sped up", "speed up", "8d"),
    }
    return {
        kind
        for kind, terms in groups.items()
        if any(re.search(r"\b" + re.escape(term) + r"\b", text) for term in terms)
    }


def clean_title(title):
    title = re.sub(r"\s[-–]\s(?:ao vivo|live|from)\b.*$", "", title, flags=re.I)
    title = re.sub(r"\((?:feat|ft|with|com)\b[^)]*\)|\[(?:feat|ft|with|com)\b[^]]*\]", "", title, flags=re.I)
    title = re.sub(r"\((?:ao vivo|live|acústico|acustico|acoustic)\b[^)]*\)", "", title, flags=re.I)
    text = words(title)
    if "remaster" in text:
        text = re.sub(r"\b(?:19|20)\d{2}\b", "", text)
    for term in (
        "official music video",
        "official video",
        "official audio",
        "video oficial",
        "audio oficial",
        "videoclipe oficial",
        "clipe oficial",
        "lyric video",
        "lyrics",
        "oficial",
        "official",
        "ao vivo",
        "live",
        "remastered",
        "remaster",
        "acustico",
        "acoustic",
        "pot pourri",
    ):
        text = re.sub(r"\b" + term + r"\b", " ", text)
    return " ".join(text.split())


def similarity(left, right):
    return SequenceMatcher(None, left, right).ratio() * 100 if left and right else 0


def artist_words(value):
    # Catalogues spell duos with &, e, and, or two separate artist credits.
    return " ".join(
        word
        for word in words(value).split()
        if word not in {"e", "and", "topic", "vevo", "oficial", "official"}
    )


def title_variants(value):
    # Multiword parenthetical alternate titles (e.g. Be With You) may be omitted
    # by one catalogue. Keep single event labels such as Nopelo360 significant.
    def omit_alias(match):
        text = words(match[1])
        version_label = re.search(
            r"\b(?:part|parte|pt|vol|volume|version|versao|edition|edicao|edit|mix|dvd|ep)\b|\d", text
        )
        return "" if len(text.split()) > 1 and not editions(match[1]) and not version_label else match[0]

    without_aliases = re.sub(r"\(([^()]+)\)", omit_alias, value)
    return {clean_title(value), clean_title(without_aliases)}


def rank_candidate(metadata, result, *, rejected=None):
    """Hard identity/version gates plus a score; popularity cannot override them."""

    def decline(reason):
        if rejected is not None:
            rejected["reason"] = reason
        return None

    wanted = editions(metadata["name"] + " " + (metadata.get("album_name") or ""))
    found = editions(result.name + " " + (result.album or ""))
    if (found - wanted) & {"cover", "speed", "remix", "acoustic", "live"}:
        return decline("Edição diferente: cover, velocidade, remix, acústico ou ao vivo não solicitado")
    if wanted & {"live", "acoustic", "remix"} - found:
        return decline("Edição solicitada não identificada no candidato")
    if ("remaster" in wanted) != ("remaster" in found):
        return decline("Remasterização diferente da solicitada")
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", metadata["name"]))
    if years and wanted & {"live", "remaster"}:
        candidate_years = set(re.findall(r"\b(?:19|20)\d{2}\b", result.name + " " + (result.album or "")))
        if not years.intersection(candidate_years):
            return decline("Ano da gravação ausente ou diferente do solicitado")
    target_duration = float(metadata.get("duration") or 0)
    candidate_duration = float(result.duration or 0)
    delta = abs(target_duration - candidate_duration) if target_duration and candidate_duration else None
    if delta is not None and delta > max(12, target_duration * 0.08):
        return decline(
            f"Duração incompatível: esperado {target_duration:.0f}s, candidato {candidate_duration:.0f}s"
        )
    artist = artist_words(metadata["artist"])
    raw_authors = result.artists or (result.author,)
    authors = [artist_words(a) for a in (*raw_authors, result.author, " ".join(raw_authors))]
    artist_score = max((similarity(artist, a) for a in authors), default=0)
    title = clean_title(result.name)
    # Normal video titles often contain the artist; remove only a complete prefix.
    prefix = words(metadata["artist"])
    if title.startswith(prefix + " "):
        title = title[len(prefix) + 1 :]
        artist_score = max(artist_score, 95)
    # An upload can credit all collaborators before the title.
    parts = re.split(r"\s[-–|]\s", result.name, maxsplit=1)
    if len(parts) == 2:
        credited_prefix = artist_words(parts[0])
        credits = [artist_words(name) for name in metadata.get("artists", [metadata["artist"]])]
        combined = " ".join(credits)
        if credited_prefix == combined:
            title = clean_title(parts[1])
            artist_score = max(artist_score, 95)
    title_score = max(
        similarity(left, right)
        for left in title_variants(metadata["name"])
        for right in {title, *title_variants(result.name)}
    )
    if artist_score < 78 or title_score < 78:
        return decline(f"Identidade insuficiente: artista {artist_score:.0f}%, título {title_score:.0f}%")
    duration_score = max(0, 100 - (delta or 0) * 3) if delta is not None else 55
    score = title_score * 0.50 + artist_score * 0.35 + duration_score * 0.15
    if score < 85:
        return decline(f"Confiança insuficiente: {score:.1f} pontos")
    credits = [artist_words(value) for value in (metadata.get("artists") or [metadata["artist"]])]
    coverage = sum(any(similarity(credit, author) >= 78 for author in authors) for credit in credits) / len(
        credits
    )
    album_score = similarity(words(metadata.get("album_name") or ""), words(result.album or ""))
    return {
        "url": canonical_youtube(result.url),
        "name": result.name,
        "artist": result.author,
        "duration": candidate_duration,
        "duration_delta": delta,
        "score": round(score, 2),
        "album": result.album,
        "album_score": round(album_score, 2),
        "artist_coverage": coverage,
        "verified": bool(result.verified),
        "source": result.source,
        "version": MATCH_VERSION,
    }


class MatchError(ValueError):
    pass


def match_order(row):
    return row["score"], row["artist_coverage"], row["album_score"], row["verified"]


class FastMatcher:
    def __init__(self, providers, progress=lambda message: None):
        self.providers, self.progress = providers, progress
        self.stats = {"queries": 0, "candidates": 0, "view_extractions": 0}
        self.last_candidates = []
        self.rejected_candidates = []
        self.query_errors = []

    def candidates(self, metadata, limit=3, exclude=()):
        started = time.monotonic()
        self.last_candidates = []
        self.rejected_candidates = []
        self.query_errors = []
        query = metadata["artist"] + " " + metadata["name"]
        collected, errors = {}, []
        seen_rejections, searched_youtube = set(), set()
        evaluated = set()

        def consider(result):
            # Expanded pages repeat results. Skip only identical metadata: another
            # provider can supply the album/edition missing from the first result.
            identity = (
                result.url, result.name, result.author, tuple(result.artists or ()),
                result.album, result.duration, result.verified, result.source,
            )
            if identity in evaluated:
                self.stats["duplicate_candidates_skipped"] = self.stats.get("duplicate_candidates_skipped", 0) + 1
                return
            evaluated.add(identity)
            rejection = {}
            ranked = rank_candidate(metadata, result, rejected=rejection)
            if ranked and ranked["url"] not in exclude:
                collected[ranked["url"]] = ranked
            elif rejection and result.url not in seen_rejections:
                seen_rejections.add(result.url)
                self.rejected_candidates.append(
                    {
                        "url": result.url,
                        "name": result.name,
                        "artist": result.author,
                        "artists": result.artists,
                        "album": result.album,
                        "duration": result.duration,
                        **rejection,
                    }
                )
                # Keep the closest titles first, rather than a page of unrelated results.
                self.rejected_candidates.sort(
                    key=lambda row: similarity(clean_title(metadata["name"]), clean_title(row["name"])),
                    reverse=True,
                )
                del self.rejected_candidates[10:]

        def query_error(exc):
            from .telemetry import sanitize

            errors.append(sanitize(f"{type(exc).__name__}: {exc}")[:700])
            self.query_errors = errors[-5:]

        isrc = metadata.get("isrc") or ""
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{3}\d{7}", isrc):
            for provider in self.providers:
                if not hasattr(provider, "client"):
                    continue
                self.stats["queries"] += 1
                try:
                    provider.SEARCH_ATTEMPTS = 1
                    rows = provider.get_results(isrc, filter="songs", limit=5, ignore_spelling=True)
                    self.stats["candidates"] += len(rows)
                    for row in rows[:5]:
                        consider(row)
                    if collected:
                        self.last_candidates = sorted(collected.values(), key=match_order, reverse=True)[
                            :limit
                        ]
                        if self.last_candidates[0]["score"] >= 94:
                            return self.last_candidates
                except Exception as exc:
                    query_error(exc)
        # First page usually contains the recording. Expand only if confidence is insufficient.
        compact = metadata["artist"] + " " + clean_title(metadata["name"])
        markers = editions(metadata["name"])
        if "live" in markers:
            compact += " ao vivo"
        if "acoustic" in markers:
            compact += " acoustic"
        searches = [(query, 10), (query, 30)]
        if words(compact) != words(query):
            searches.append((compact, 10))
        for query, size in searches:
            for provider in self.providers:
                if time.monotonic() - started > 55:
                    break
                for kind in ("songs", "videos") if hasattr(provider, "client") else ("youtube",):
                    # ytsearch10 has no larger page here; repeating it cannot expand results.
                    if kind == "youtube" and (id(provider), query) in searched_youtube:
                        continue
                    if time.monotonic() - started > 55:
                        break
                    self.stats["queries"] += 1
                    try:
                        if kind == "youtube":
                            searched_youtube.add((id(provider), query))
                            results = self.youtube_results(provider, query, min(size, 10))
                        else:
                            provider.SEARCH_ATTEMPTS = 1
                            results = provider.get_results(
                                query, filter=kind, limit=size, ignore_spelling=True
                            )
                        self.stats["candidates"] += len(results)
                        for result in results[:size]:
                            consider(result)
                    except Exception as exc:
                        query_error(exc)
                    ranked = sorted(collected.values(), key=match_order, reverse=True)
                    self.last_candidates = ranked[:limit]
                    if ranked and ranked[0]["score"] >= 94 and ranked[0]["verified"]:
                        self.progress(f"Correspondência de alta confiança · {ranked[0]['score']:.1f} pontos.")
                        return self.last_candidates
                if (
                    collected
                    and collected[max(collected, key=lambda u: collected[u]["score"])]["score"] >= 94
                ):
                    return self.last_candidates
            if collected:
                break
        if not collected:
            reason = "nenhum candidato compatível com artista, título, duração e edição"
            if errors:
                reason += "; " + errors[-1]
            if self.rejected_candidates:
                reason += ". Candidato mais próximo: " + self.rejected_candidates[0]["reason"]
            raise MatchError("Busca de correspondência: " + reason)
        best = self.last_candidates
        # Two close metadata-identical entries are often alternate uploads of one recording.
        if len(best) > 1 and best[0]["score"] < 94 and best[0]["score"] - best[1]["score"] < 2:
            raise MatchError("Correspondência ambígua. Escolha a gravação em Biblioteca → Fonte do áudio.")
        return best

    @staticmethod
    def youtube_results(provider, query, limit):
        from spotdl.types.result import Result
        from yt_dlp import YoutubeDL

        options = {
            **provider.audio_handler.params,
            "extract_flat": True,
            "skip_download": True,
            "socket_timeout": 10,
            "retries": 1,
            "extractor_retries": 1,
        }
        with YoutubeDL(options) as client:
            info = client.extract_info(f"ytsearch{limit}:{query}", download=False)
        return [
            Result(
                source="YouTube",
                url="https://www.youtube.com/watch?v=" + entry["id"],
                verified=False,
                name=entry.get("title", ""),
                duration=entry.get("duration") or 0,
                author=entry.get("channel") or entry.get("uploader") or "",
                result_id=entry["id"],
            )
            for entry in (info or {}).get("entries", [])
            if entry and entry.get("id")
        ]
