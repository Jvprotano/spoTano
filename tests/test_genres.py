import pytest

from spotano.genres import classify


@pytest.mark.parametrize(
    "genre,expected",
    [
        ("sertanejo universitário", "Sertanejo"),
        ("pagode baiano", "Pagode e Samba"),
        ("bossa nova", "MPB"),
        ("funk carioca", "Funk Brasileiro"),
        ("indie rock", "Rock e Metal"),
        ("brazilian hip hop", "Rap e Hip-Hop"),
        ("progressive house", "Eletronica"),
        ("forró", "Forro e Piseiro"),
        ("unknown", "Outros"),
        ("dance pop", "Pop"),
    ],
)
def test_broad_categories(genre, expected):
    assert classify([genre]) == expected


def test_short_keywords_do_not_match_inside_unrelated_words():
    assert classify(["crap", "popular artist", "metallurgy"]) == "Outros"
    assert classify(["thrash metal"]) == "Rock e Metal"
