from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QVBoxLayout, QWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Media Converter")
        self.resize(900, 600)

        self._create_menu()
        self._create_central_widget()
        self.statusBar().showMessage("Pronto")

    def _create_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Arquivo")
        quit_action = QAction("&Sair", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("A&juda")
        about_action = QAction("&Sobre", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _create_central_widget(self) -> None:
        label = QLabel("Media Converter")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = label.font()
        font.setPointSize(20)
        label.setFont(font)

        layout = QVBoxLayout()
        layout.addWidget(label)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    def _show_about(self) -> None:
        QMessageBox.about(self, "Sobre", "Media Converter\nPySide6 (Qt Widgets)")
