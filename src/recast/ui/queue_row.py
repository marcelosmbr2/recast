from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QProgressBar, QStackedWidget, QWidget

from recast.core.formats import CATEGORIES, fmt_eta, fmt_size
from recast.core.models import QueueItem, Status
from recast.ui import platform, theme
from recast.ui.widgets import (
    Button, CompositeButton, ElidedLabel, FileBadge, hbox, icon_label, set_prop, text, vbox,
)

COLUMNS = (150, 188, 60)  # target, status, actions — the name column stretches
MARGINS = (20, 0, 16, 0)
SPACING = 16


def item_meta(item: QueueItem) -> str:
    return f"{fmt_size(item.size)} · {platform.display_path(str(item.path.parent))}"


def size_delta(item: QueueItem) -> str:
    if not item.size:
        return ""
    delta = round((item.out_size - item.size) / item.size * 100)
    return ("−" if delta <= 0 else "+") + f"{abs(delta)}%"


class QueueRow(QFrame):
    selected = Signal(str)
    pick_requested = Signal(str, QWidget)
    remove_requested = Signal(str)
    reveal_requested = Signal(str)

    def __init__(self, item: QueueItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.item_id = item.id
        self.setProperty("role", "row")
        self.setFixedHeight(54)
        row = hbox(self, MARGINS, SPACING)

        name_box = QWidget()
        name_row = hbox(name_box, spacing=12)
        self._badge = FileBadge("row")
        name_row.addWidget(self._badge)
        texts = vbox(spacing=2)
        self._name = ElidedLabel("", "name")
        self._meta = ElidedLabel("", "meta")
        texts.addStretch(1)
        texts.addWidget(self._name)
        texts.addWidget(self._meta)
        texts.addStretch(1)
        name_row.addLayout(texts, 1)
        row.addWidget(name_box, 1)

        target_box = QWidget()
        target_box.setFixedWidth(COLUMNS[0])
        target_row = hbox(target_box)
        self._pick = CompositeButton("pick", height=26, margins=(10, 0, 7, 0), spacing=6)
        self._pick_label = self._pick.add_text("", "target")
        self._pick.add_icon("chevron", theme.MUTED, 12)
        self._pick.clicked.connect(lambda: self.pick_requested.emit(self.item_id, self._pick))
        self._static_target = text("", "target-static")
        self._static_target.setContentsMargins(11, 0, 11, 0)
        target_row.addWidget(self._pick)
        target_row.addWidget(self._static_target)
        target_row.addStretch(1)
        row.addWidget(target_box)

        self._status = QStackedWidget()
        self._status.setFixedWidth(COLUMNS[1])
        self._plain = ElidedLabel("", "small")
        self._status.addWidget(self._plain)
        active = QWidget()
        active_col = vbox(active, spacing=6)
        active_top = hbox()
        self._active_label = text("", "status-label")
        self._pct = text("", "mono-muted")
        active_top.addWidget(self._active_label)
        active_top.addStretch(1)
        active_top.addWidget(self._pct)
        self._bar = QProgressBar()
        self._bar.setRange(0, 1000)
        self._bar.setTextVisible(False)
        active_col.addStretch(1)
        active_col.addLayout(active_top)
        active_col.addWidget(self._bar)
        active_col.addStretch(1)
        self._status.addWidget(active)
        done = QWidget()
        done_row = hbox(done, spacing=7)
        self._done_icon = icon_label("check", theme.GREEN, 14)
        self._out_label = text("", "small-2")
        self._delta = text("", "mono-dim")
        done_row.addWidget(self._done_icon)
        done_row.addWidget(self._out_label)
        done_row.addWidget(self._delta)
        done_row.addStretch(1)
        self._status.addWidget(done)
        error = QWidget()
        error_row = hbox(error, spacing=7)
        error_row.addWidget(icon_label("alert", theme.RED, 14))
        self._error = ElidedLabel("", "error")
        error_row.addWidget(self._error, 1)
        self._status.addWidget(error)
        row.addWidget(self._status)

        actions = QWidget()
        actions.setFixedWidth(COLUMNS[2])
        actions_row = hbox(actions, spacing=2)
        actions_row.addStretch(1)
        self._reveal = Button("", "icon", "folder", color=theme.DIM, hover=theme.TEXT, icon_size=15, height=26)
        self._reveal.setFixedWidth(26)
        self._reveal.setToolTip(platform.REVEAL_LABEL)
        self._reveal.clicked.connect(lambda: self.reveal_requested.emit(self.item_id))
        remove = Button("", "icon", "close", color=theme.FAINT, hover=theme.TEXT, icon_size=14, height=26)
        remove.setFixedWidth(26)
        remove.setToolTip("Remover")
        remove.clicked.connect(lambda: self.remove_requested.emit(self.item_id))
        actions_row.addWidget(self._reveal)
        actions_row.addWidget(remove)
        row.addWidget(actions)

        self.update_item(item, running=False)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.item_id)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool) -> None:
        set_prop(self, "selected", selected)

    def update_item(self, item: QueueItem, running: bool) -> None:
        self._badge.set_file(item.ext, CATEGORIES[item.cat].tint)
        self._name.setText(item.name)
        self._meta.setText(item_meta(item))
        converting = item.status is Status.CONVERTING
        unsupported = item.status is Status.UNSUPPORTED
        self._pick_label.setText(item.target)
        self._pick.setVisible(not converting and not unsupported)
        self._static_target.setText("—" if unsupported else item.target)
        self._static_target.setVisible(converting or unsupported)
        self._reveal.setVisible(item.is_finished)

        if converting:
            self._status.setCurrentIndex(1)
            self._active_label.setText(fmt_eta(item.eta) if running else "Pausado")
            self._pct.setText(f"{int(item.progress * 100)}%")
            self._bar.setValue(round(item.progress * 1000))
            set_prop(self._bar, "paused", not running)
        elif item.status is Status.DONE:
            self._status.setCurrentIndex(2)
            self._out_label.setText(fmt_size(item.out_size))
            self._delta.setText(size_delta(item))
            self._delta.show()
        elif item.status is Status.SKIPPED:
            self._status.setCurrentIndex(2)
            self._out_label.setText("Ignorado · já existe")
            self._delta.hide()
        elif item.status is Status.ERROR:
            self._status.setCurrentIndex(3)
            self._error.setText(f"Falhou: {item.error}")
        else:
            self._status.setCurrentIndex(0)
            if unsupported:
                self._plain.setText("Formato não suportado")
                set_prop(self._plain, "t", "small-dim")
            else:
                self._plain.setText("Na fila" if running else "Pronto")
                set_prop(self._plain, "t", "small-dim" if running else "small")
