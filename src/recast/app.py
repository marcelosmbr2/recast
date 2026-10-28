import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from recast import __version__
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


def main() -> int:
    app = create_app()
    window = MainWindow()
    window.show()
    return app.exec()
