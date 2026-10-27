"""Optional ID3 tags, with no artwork or remote metadata lookup."""


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
