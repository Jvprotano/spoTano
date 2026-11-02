"""Derive Windows ICO and Tk PNG sizes from the original generated artwork."""

from pathlib import Path

from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "spotano" / "assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main():
    with Image.open(ASSETS / "spotano.png") as original:
        image = original.convert("RGBA")
        if image.width != image.height:
            raise ValueError("O ícone original deve ser quadrado.")
        # Tk's Windows ICO reader expects DIB frames, including the small sizes.
        image.save(ASSETS / "spotano.ico", sizes=[(size, size) for size in SIZES], bitmap_format="bmp")
        for size in (16, 32, 48, 256):
            image.resize((size, size), Image.Resampling.LANCZOS).save(ASSETS / f"spotano-{size}.png")
    print(f"Icons generated in {ASSETS}")


if __name__ == "__main__":
    main()
