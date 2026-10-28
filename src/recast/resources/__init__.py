from pathlib import Path

from PySide6.QtGui import QFontDatabase

FONTS_DIR = Path(__file__).parent / "fonts"

_loaded = False


def load_fonts() -> None:
    """Register the bundled Inter and JetBrains Mono fonts (call once, on the GUI thread)."""
    global _loaded
    if _loaded:
        return
    for ttf in sorted(FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(ttf))
    _loaded = True
