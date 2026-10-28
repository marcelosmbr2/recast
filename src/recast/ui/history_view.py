from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QScrollArea, QWidget

from recast.core.formats import CATEGORIES, category_of, fmt_size
from recast.core.models import HistoryEntry
from recast.core.storage import HistoryStore
from recast.ui import platform, theme
from recast.ui.convert_view import column_header, header
from recast.ui.queue_row import MARGINS, SPACING
from recast.ui.widgets import Button, ElidedLabel, FileBadge, hbox, icon_label, text, vbox

COLUMNS = (150, 190, 130, 40)


class HistoryRow(QFrame):
    reveal_requested = Signal(object)

    def __init__(self, entry: HistoryEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "row")
        self.setProperty("hoverable", True)
        self.setFixedHeight(48)
        row = hbox(self, MARGINS, SPACING)
        name = hbox(spacing=12)
        badge = FileBadge("history")
        badge.set_file("", CATEGORIES[category_of(entry.src.lower())].tint)
        name.addWidget(badge)
        name.addWidget(ElidedLabel(entry.name, "name-plain"), 1)
        row.addLayout(name, 1)

        conv = QWidget()
        conv.setFixedWidth(COLUMNS[0])
        crow = hbox(conv, spacing=7)
        crow.addWidget(text(entry.src, "mono-muted"))
        crow.addWidget(icon_label("arrow", theme.ARROW, 11))
        crow.addWidget(text(entry.target, "mono-2"))
        crow.addStretch(1)
        row.addWidget(conv)

        sizes = text(f"{fmt_size(entry.in_size)}  →  {fmt_size(entry.out_size)}", "small")
        sizes.setFixedWidth(COLUMNS[1])
        row.addWidget(sizes)
        when = text(entry.when_label(), "small-dim")
        when.setFixedWidth(COLUMNS[2])
        row.addWidget(when)
        reveal = Button("", "icon", "folder", color=theme.DIM, hover=theme.TEXT, icon_size=15, height=26)
        reveal.setFixedWidth(26)
        reveal.setToolTip(platform.REVEAL_LABEL)
        reveal.setEnabled(bool(entry.out_path))
        reveal.clicked.connect(lambda: self.reveal_requested.emit(entry))
        cell = QWidget()
        cell.setFixedWidth(COLUMNS[3])
        hbox(cell).addWidget(reveal, 0, Qt.AlignmentFlag.AlignLeft)
        row.addWidget(cell)


class HistoryView(QWidget):
    reveal_requested = Signal(Path)
    missing = Signal(str)

    def __init__(self, history: HistoryStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history = history
        col = vbox(self)
        bar, row, _ = header("Histórico", "Armazenado localmente. O Recast não guarda cópias dos seus arquivos.")
        clear = Button("Limpar histórico", "secondary")
        clear.clicked.connect(history.clear)
        row.addWidget(clear)
        col.addWidget(bar)
        col.addWidget(column_header(["Nome", "Conversão", "Tamanho", "Data", ""], COLUMNS))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self._list = vbox(body)
        scroll.setWidget(body)
        col.addWidget(scroll, 1)
        history.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for entry in self._history.entries:
            row = HistoryRow(entry)
            row.reveal_requested.connect(self._reveal)
            self._list.addWidget(row)
        if not self._history.entries:
            empty = text("Nenhuma conversão ainda.", "hint")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setContentsMargins(20, 48, 20, 48)
            self._list.addWidget(empty)
        self._list.addStretch(1)

    def showEvent(self, event) -> None:
        self.refresh()  # keeps "Agora mesmo" / "Hoje" labels current
        super().showEvent(event)

    def _reveal(self, entry: HistoryEntry) -> None:
        path = Path(entry.out_path)
        if path.exists():
            self.reveal_requested.emit(path)
        else:
            self.missing.emit(path.name)
