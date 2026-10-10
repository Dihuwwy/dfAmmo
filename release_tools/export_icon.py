from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
ICON_SIZES = [(size, size) for size in (16, 24, 32, 48, 64, 128, 256)]


def main() -> None:
    """Export the selected artwork to a multi-resolution Windows icon."""
    target = ROOT / "assets" / "app-icon.ico"
    with Image.open(ROOT / "assets" / "app-icon.png") as source:
        source.convert("RGBA").save(target, format="ICO", sizes=ICON_SIZES)
    with Image.open(target) as icon:
        if icon.ico.sizes() != set(ICON_SIZES):
            raise RuntimeError("Windows icon is missing required resolutions")
    print(target)


if __name__ == "__main__":
    main()
