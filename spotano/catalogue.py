"""Conservative recording identity for genre evidence from public catalogues."""

import re

from .genres import artist_key, classify
from .matching import clean_title, editions


def catalogue_match(metadata, rows, include_unknown=False):
    """A catalogue hit is evidence only when recording and credits agree."""
    duration = float(metadata.get("duration") or 0)
    if not duration:
        return None
    wanted = clean_title(metadata["name"])
    artists = metadata.get("artists") or [metadata["artist"]]
    credits = {artist_key(name).replace(" ", "") for name in artists}
    primary = artist_key(metadata["artist"]).replace(" ", "")
    if not primary:
        return None
    matched = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("kind") != "song"
            or not row.get("trackId")
            or not all(
                isinstance(row.get(key), str) for key in ("trackName", "artistName", "primaryGenreName")
            )
        ):
            continue
        if clean_title(row.get("trackName", "")) != wanted:
            continue
        # Versions matter even when the genre happens to be the same.
        if editions(row["trackName"]) != editions(metadata["name"]):
            continue
        try:
            delta = abs(float(row.get("trackTimeMillis") or 0) / 1000 - duration)
        except (TypeError, ValueError):
            continue
        if delta > max(5, duration * 0.02):
            continue
        author = artist_key(row.get("artistName", "")).replace(" ", "")
        if not author:
            continue
        # Delimit credits before normalization: '&' can also belong to a duo's name.
        names = re.split(r"\s*(?:,|\s&\s|\sfeat\.\s)\s*", row.get("artistName", ""), flags=re.I)
        found = {artist_key(name).replace(" ", "") for name in names}
        primary_words = artist_key(metadata["artist"])
        artist_words = artist_key(row.get("artistName", ""))
        main_match = (
            primary == author
            or primary in found
            or (
                " " in primary_words
                and bool(
                    re.search(r"(?<![a-z0-9])" + re.escape(primary_words) + r"(?![a-z0-9])", artist_words)
                )
            )
        )
        coverage = credits & found
        if not main_match and len(coverage) < 2:
            continue
        category = classify([row.get("primaryGenreName", "")])
        if category != "Outros" or include_unknown:
            matched.append(
                {
                    "category": category,
                    "tags": [row["primaryGenreName"]],
                    "catalogue_id": row["trackId"],
                    "artist": row["artistName"],
                    "title": row["trackName"],
                    "duration_delta": round(delta, 3),
                }
            )
    # Conflicting editions/catalogue entries are not a license to guess.
    return (
        min(matched, key=lambda row: row["duration_delta"])
        if matched and len({row["category"] for row in matched}) == 1
        else None
    )
