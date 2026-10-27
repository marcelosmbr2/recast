import sys

from PySide6.QtWidgets import QApplication

from media_converter import __version__
from media_converter.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Media Converter")
    app.setApplicationVersion(__version__)

    window = MainWindow()
    window.show()

    return app.exec()
