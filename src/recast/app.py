import logging
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from recast import __version__
from recast.core.storage import default_data_dir
from recast.resources import load_fonts
from recast.ui import theme
from recast.ui.main_window import MainWindow


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Recast")
    app.setOrganizationName("Recast")
    app.setApplicationVersion(__version__)
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)  # dark native title bar
    load_fonts()
    font = QFont(theme.SANS)
    font.setPointSizeF(13 * 0.75)
    app.setFont(font)
    theme.apply(app)
    return app


def _setup_logging() -> None:
    """The packaged app has no console, so warnings and tracebacks go to recast.log."""
    log_dir = default_data_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=log_dir / "recast.log", level=logging.WARNING, encoding="utf-8",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> int:
    app = create_app()
    _setup_logging()
    if "--self-test" in sys.argv:
        from recast.selftest import run

        rest = sys.argv[sys.argv.index("--self-test") + 1:]
        return run(Path(rest[0]) if rest else None)
    window = MainWindow()
    window.show()
    return app.exec()
