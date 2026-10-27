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
    value = "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))
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
    identity = {key: metadata.get(key) for key in
                ("song_id", "name", "artist", "artist_id", "artists", "duration", "isrc", "album_name")}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def editions(title):
    text = words(title)
    groups = {
        "live": ("ao vivo", "live", "concert"),
        "acoustic": ("acustico", "acustica", "acoustic", "unplugged"),
        "remix": ("remix",), "remaster": ("remaster", "remastered"),
        "cover": ("cover", "karaoke", "instrumental", "tribute"),
        "speed": ("slowed", "reverb", "sped up", "speed up", "8d"),
    }
    return {kind for kind, terms in groups.items()
            if any(re.search(r"\b" + re.escape(term) + r"\b", text) for term in terms)}


def clean_title(title):
    title = re.sub(r"\s[-–]\s(?:ao vivo|live|from)\b.*$", "", title, flags=re.I)
    title = re.sub(r"\((?:feat|ft|with|com)\b.*?\)", "", title, flags=re.I)
    text = words(title)
    if "remaster" in text:
        text = re.sub(r"\b(?:19|20)\d{2}\b", "", text)
    for term in ("official music video", "official video", "official audio", "video oficial", "audio oficial",
                 "videoclipe oficial", "clipe oficial", "lyric video", "lyrics", "oficial", "official",
                 "ao vivo", "live", "remastered", "remaster", "acustico", "acoustic", "pot pourri"):
        text = re.sub(r"\b" + term + r"\b", " ", text)
    return " ".join(text.split())


def similarity(left, right):
    return SequenceMatcher(None, left, right).ratio() * 100 if left and right else 0


def rank_candidate(metadata, result):
    """Hard identity/version gates plus a score; popularity cannot override them."""
    wanted, found = editions(metadata["name"]), editions(result.name + " " + (result.album or ""))
    if (found - wanted) & {"cover", "speed", "remix", "acoustic", "live"}:
        return None
    if wanted & {"live", "acoustic", "remix"} - found:
        return None
    if ("remaster" in wanted) != ("remaster" in found):
        return None
    years = set(re.findall(r"\b(?:19|20)\d{2}\b", metadata["name"]))
    if years and wanted & {"live", "remaster"}:
        candidate_years = set(re.findall(r"\b(?:19|20)\d{2}\b", result.name + " " + (result.album or "")))
        if not years.intersection(candidate_years):
            return None
    target_duration = float(metadata.get("duration") or 0)
    candidate_duration = float(result.duration or 0)
    delta = abs(target_duration - candidate_duration) if target_duration and candidate_duration else None
    if delta is not None and delta > max(12, target_duration * 0.08):
        return None
    artist = words(metadata["artist"])
    authors = [words(a) for a in (result.artists or (result.author,))]
    authors = [re.sub(r"\b(topic|vevo|oficial|official)\b", "", a).strip() for a in authors]
    artist_score = max((similarity(artist, a) for a in authors), default=0)
    title = clean_title(result.name)
    # Normal video titles often contain the artist; remove only a complete prefix.
    if title.startswith(artist + " "):
        title = title[len(artist) + 1:]
        artist_score = max(artist_score, 95)
    wanted_title = clean_title(metadata["name"])
    title_score = similarity(wanted_title, title)
    if artist_score < 78 or title_score < 78:
        return None
    duration_score = max(0, 100 - (delta or 0) * 3) if delta is not None else 55
    score = title_score * 0.50 + artist_score * 0.35 + duration_score * 0.15
    if score < 85:
        return None
    credits = [words(value) for value in (metadata.get("artists") or [metadata["artist"]])]
    coverage = sum(any(similarity(credit, author) >= 78 for author in authors) for credit in credits) / len(credits)
    album_score = similarity(words(metadata.get("album_name") or ""), words(result.album or ""))
    return {"url": canonical_youtube(result.url), "name": result.name, "artist": result.author,
            "duration": candidate_duration, "duration_delta": delta, "score": round(score, 2),
            "album": result.album, "album_score": round(album_score, 2), "artist_coverage": coverage,
            "verified": bool(result.verified), "source": result.source, "version": MATCH_VERSION}


class MatchError(ValueError):
    pass


def match_order(row):
    return row["score"], row["artist_coverage"], row["album_score"], row["verified"]


class FastMatcher:
    def __init__(self, providers, progress=lambda message: None):
        self.providers, self.progress = providers, progress
        self.stats = {"queries": 0, "candidates": 0, "view_extractions": 0}
        self.last_candidates = []

    def candidates(self, metadata, limit=3, exclude=()):
        started = time.monotonic()
        self.last_candidates = []
        query = metadata["artist"] + " " + metadata["name"]
        collected, errors = {}, []
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
                        ranked = rank_candidate(metadata, row)
                        if ranked and ranked["url"] not in exclude:
                            collected[ranked["url"]] = ranked
                    if collected:
                        self.last_candidates = sorted(collected.values(), key=match_order,
                                                      reverse=True)[:limit]
                        if self.last_candidates[0]["score"] >= 94:
                            return self.last_candidates
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
        # First page usually contains the recording. Expand only if confidence is insufficient.
        for size in (10, 30):
            for provider in self.providers:
                if time.monotonic() - started > 55:
                    break
                for kind in ("songs", "videos") if hasattr(provider, "client") else ("youtube",):
                    if time.monotonic() - started > 55:
                        break
                    self.stats["queries"] += 1
                    try:
                        if kind == "youtube":
                            results = self.youtube_results(provider, query, min(size, 10))
                        else:
                            provider.SEARCH_ATTEMPTS = 1
                            results = provider.get_results(query, filter=kind, limit=size, ignore_spelling=True)
                        self.stats["candidates"] += len(results)
                        for result in results[:size]:
                            ranked = rank_candidate(metadata, result)
                            if ranked and ranked["url"] not in exclude:
                                collected[ranked["url"]] = ranked
                    except Exception as exc:
                        errors.append(f"{type(exc).__name__}: {exc}")
                    ranked = sorted(collected.values(), key=match_order, reverse=True)
                    self.last_candidates = ranked[:limit]
                    if ranked and ranked[0]["score"] >= 94 and ranked[0]["verified"]:
                        self.progress(f"Correspondência de alta confiança · {ranked[0]['score']:.1f} pontos.")
                        return self.last_candidates
                if collected and collected[max(collected, key=lambda u: collected[u]["score"])]["score"] >= 94:
                    return self.last_candidates
            if collected:
                break
        if not collected:
            reason = "nenhum candidato compatível com artista, título, duração e edição"
            if errors:
                reason += "; " + errors[-1]
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

        options = {**provider.audio_handler.params, "extract_flat": True, "skip_download": True,
                   "socket_timeout": 10, "retries": 1, "extractor_retries": 1}
        with YoutubeDL(options) as client:
            info = client.extract_info(f"ytsearch{limit}:{query}", download=False)
        return [Result(source="YouTube", url="https://www.youtube.com/watch?v=" + entry["id"],
                       verified=False, name=entry.get("title", ""), duration=entry.get("duration") or 0,
                       author=entry.get("channel") or entry.get("uploader") or "", result_id=entry["id"])
                for entry in (info or {}).get("entries", []) if entry and entry.get("id")]
