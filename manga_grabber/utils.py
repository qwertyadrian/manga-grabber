import sys
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont


def find_font(family: str, subfamily: str) -> Path | None:
    """
    Finds the font file by its name in system directories

    :param family: Font family name
    :param subfamily: Font subfamily name
    :return: Font file path if found, otherwise None
    """
    font_dirs = []

    if sys.platform == "win32":
        font_dirs.append(Path(r"C:\Windows\Fonts"))
    elif sys.platform == "darwin":  # macOS
        font_dirs.extend(
            [
                Path("/System/Library/Fonts"),
                Path("/Library/Fonts"),
                Path.home() / "Library/Fonts",
            ]
        )
    else:  # Linux and other Unix-like systems
        font_dirs.extend(
            [
                Path("/usr/share/fonts"),
                Path("/usr/local/share/fonts"),
                Path.home() / ".local/share/fonts",
            ]
        )

    # Find all font directories
    for font_dir in font_dirs:
        if not font_dir.exists():
            continue
        for ext in [".ttf", ".ttc", ".otf"]:
            for font_path in font_dir.glob(f"**/*{ext}"):
                if font_path.suffix == ".ttc":
                    collection = TTCollection(font_path)
                else:
                    collection = (TTFont(font_path),)

                for font in collection:
                    if (
                        font["name"].getDebugName(1) == family
                        and font["name"].getDebugName(2) == subfamily
                    ):
                        return font_path

    return None
