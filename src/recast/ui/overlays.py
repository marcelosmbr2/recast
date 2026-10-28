from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QWidget

from recast.ui import theme
from recast.ui.widgets import hbox, icon_label, text, vbox


class Toast(QFrame):
    """Bottom-right confirmation that hides itself after 3.6 s."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setProperty("role", "toast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(32)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 115))
        self.setGraphicsEffect(shadow)
        row = hbox(self, (12, 10, 14, 10), 10)
        row.addWidget(icon_label("check", theme.GREEN, 15))
        col = vbox(spacing=1)
        self._title = text("", "toast-title")
        self._sub = text("", "toast-sub")
        col.addWidget(self._title)
        col.addWidget(self._sub)
        row.addLayout(col)
        self._timer = QTimer(self, singleShot=True, interval=3600, timeout=self.hide)
        host.installEventFilter(self)
        self.hide()

    def show_message(self, title: str, sub: str = "") -> None:
        self._title.setText(title)
        self._sub.setText(sub)
        self._sub.setVisible(bool(sub))
        self.show()  # polish the labels first so adjustSize() sees the styled fonts
        self.adjustSize()
        self._place()
        self.raise_()
        self._timer.start()

    def _place(self) -> None:
        host = self.parentWidget()
        self.move(host.width() - self.width() - 16, host.height() - self.height() - 40)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize and self.isVisible():
            self._place()
        return False


class DropOverlay(QWidget):
    """Dashed orange frame shown while files are dragged over the main area."""

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        col = vbox(self, spacing=6)
        col.addStretch(1)
        title = text("Solte para adicionar arquivos", "drop-title")
        sub = text("Eles ficam neste dispositivo", "setting-desc")
        for label in (title, sub):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(label)
        col.addStretch(1)
        host.installEventFilter(self)
        self.hide()

    def show_over(self) -> None:
        self.setGeometry(self.parentWidget().rect().adjusted(10, 10, -10, -10))
        self.show()
        self.raise_()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize and self.isVisible():
            self.setGeometry(self.parentWidget().rect().adjusted(10, 10, -10, -10))
        return False

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(theme.ACCENT), 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(21, 21, 22, 224))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75), 10, 10)
