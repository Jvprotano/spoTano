"""The automotive audio contract and cheap ID3 category updates."""


def validate_mp3(path):
    from mutagen.mp3 import MP3, BitrateMode

    audio = MP3(path)
    info = audio.info
    if info.length <= 0 or info.bitrate <= 0:
        raise ValueError("O arquivo obtido não é um MP3 válido.")
    if info.sample_rate != 44100 or info.channels != 2:
        raise ValueError("MP3 fora do perfil automotivo (44,1 kHz / estéreo).")
    if abs(info.bitrate - 192000) > 1000 or info.bitrate_mode != BitrateMode.CBR:
        raise ValueError("MP3 fora do perfil automotivo (CBR 192 kbps).")
    if audio.tags is not None and (audio.tags.version[1] != 3 or audio.tags.getall("APIC")):
        raise ValueError("MP3 fora do perfil automotivo (ID3v2.3 / sem capas).")
    return info


class DurationMismatch(ValueError):
    pass


def validate_duration(actual, expected):
    expected = float(expected or 0)
    if expected and abs(actual - expected) > max(12, expected * 0.08):
        raise DurationMismatch(
            f"Duração incompatível: áudio {actual:.1f}s, faixa {expected:.1f}s. "
            "Revise a gravação em Fonte do áudio."
        )


def write_genre(path, category):
    from mutagen.id3 import ID3, TCON

    tags = ID3(path)
    if str(tags.get("TCON", "")) == category and tags.version[1] == 3:
        return False
    tags.setall("TCON", [TCON(encoding=1, text=[category])])
    tags.delall("APIC")
    tags.save(path, v2_version=3)
    return True


def needs_genre(path, category):
    from mutagen.id3 import ID3

    tags = ID3(path)
    return str(tags.get("TCON", "")) != category or tags.version[1] != 3


def write_tags(path, metadata, enabled):
    from mutagen.id3 import ID3, TALB, TDRC, TIT2, TPE1, TPE2, TRCK, ID3NoHeaderError, delete

    if not enabled:
        # Also removes ID3v1 or inherited provider tags; audio frames stay intact.
        delete(path, delete_v1=True, delete_v2=True)
        return
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.clear()
    tags.add(TIT2(encoding=1, text=[metadata["name"]]))
    tags.add(TPE1(encoding=1, text=metadata.get("artists") or [metadata["artist"]]))
    if metadata.get("album_name"):
        tags.add(TALB(encoding=1, text=[metadata["album_name"]]))
    if metadata.get("album_artist"):
        tags.add(TPE2(encoding=1, text=[metadata["album_artist"]]))
    if metadata.get("date") or metadata.get("year"):
        tags.add(TDRC(encoding=1, text=[str(metadata.get("date") or metadata["year"])]))
    if metadata.get("track_number"):
        tags.add(TRCK(encoding=1, text=[str(metadata["track_number"])]))
    tags.save(path, v2_version=3, v1=0)
