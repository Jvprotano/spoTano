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
    if not audio.tags or audio.tags.version[1] != 3 or audio.tags.getall("APIC"):
        raise ValueError("MP3 fora do perfil automotivo (ID3v2.3 / sem capas).")
    return info


class DurationMismatch(ValueError):
    pass


def validate_duration(actual, expected):
    expected = float(expected or 0)
    if expected and abs(actual - expected) > max(12, expected * 0.08):
        raise DurationMismatch(f"Duração incompatível: áudio {actual:.1f}s, faixa {expected:.1f}s. "
                         "Revise a gravação em Fonte do áudio.")


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
