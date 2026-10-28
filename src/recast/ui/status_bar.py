from __future__ import annotations

from PySide6.QtWidgets import QFrame, QWidget

from recast.core.models import Settings
from recast.core.queue import ConversionQueue
from recast.ui import theme
from recast.ui.widgets import Dot, hbox, icon_label, text


class StatusBar(QFrame):
    def __init__(self, queue: ConversionQueue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queue = queue
        self.setProperty("role", "statusbar")
        self.setFixedHeight(26)
        row = hbox(self, (12, 0, 12, 0), 18)
        engine = hbox(spacing=6)
        self._dot = Dot()
        self._label = text("Pronto", "status-strong")
        engine.addWidget(self._dot)
        engine.addWidget(self._label)
        row.addLayout(engine)
        self._threads = text("", "status")
        row.addWidget(self._threads)
        row.addStretch(1)
        sent = hbox(spacing=6)
        sent.addWidget(icon_label("lock-bold", theme.DIM, 11))
        sent.addWidget(text("0 bytes enviados", "status"))
        row.addLayout(sent)
        for signal in (queue.items_changed, queue.item_changed, queue.running_changed):
            signal.connect(self.refresh)

    def set_settings(self, settings: Settings) -> None:
        accel = "Aceleração de hardware ativa" if settings.hw else "Somente CPU"
        self._threads.setText(f"{settings.parallel} simultâneas · {accel}")

    def refresh(self, *_args) -> None:
        q = self._queue
        active, pending = q.active, q.pending
        if q.running:
            self._dot.set_color(theme.ACCENT)
            self._label.setText(f"Convertendo {len(active)} de {len(pending)}")
        elif active:
            self._dot.set_color(theme.MUTED)
            self._label.setText("Pausado")
        else:
            self._dot.set_color(theme.GREEN)
            self._label.setText("Pronto")
