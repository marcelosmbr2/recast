from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QScrollArea, QStackedWidget, QWidget

from recast.core.formats import fmt_size
from recast.core.models import QueueItem
from recast.core.queue import ConversionQueue
from recast.ui import platform, theme
from recast.ui.queue_row import COLUMNS, MARGINS, SPACING, QueueRow
from recast.ui.widgets import Button, CompositeButton, ElidedLabel, frame, hbox, icon_label, text, vbox


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def header(title: str, subtitle: str | None = None) -> tuple[QWidget, object, ElidedLabel | None]:
    """56px view header: title/subtitle on the left; returns (frame, row layout, subtitle label)."""
    bar = frame("header")
    bar.setFixedHeight(56)
    row = hbox(bar, (20, 0, 16, 0), 8)
    col = vbox(spacing=2)
    col.addStretch(1)
    col.addWidget(text(title, "title"))
    sub = None
    if subtitle is not None:
        sub = ElidedLabel(subtitle, "subtitle")
        col.addWidget(sub)
    col.addStretch(1)
    row.addLayout(col, 1)
    return bar, row, sub


def column_header(labels: list[str], widths: tuple[int, ...]) -> QWidget:
    bar = frame("colhead")
    bar.setFixedHeight(32)
    row = hbox(bar, MARGINS, SPACING)
    row.addWidget(text(labels[0], "colhead"), 1)
    for label, width in zip(labels[1:], widths, strict=False):
        cell = text(label, "colhead")
        cell.setFixedWidth(width)
        row.addWidget(cell)
    return bar


class ConvertView(QWidget):
    browse_requested = Signal()
    all_picker_requested = Signal(QWidget)
    row_selected = Signal(str)
    pick_requested = Signal(str, QWidget)
    reveal_requested = Signal(str)

    def __init__(self, queue: ConversionQueue, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queue = queue
        self._rows: dict[str, QueueRow] = {}
        self._selected: str | None = None
        col = vbox(self)

        bar, row, self._summary = header("Converter", "Nenhum arquivo adicionado")
        self._clear = Button("Limpar", "ghost")
        self._clear.clicked.connect(queue.clear_done)
        self._all = CompositeButton("secondary", margins=(11, 0, 9, 0))
        self._all.add_text("Tudo para", "small")
        self._all_target = self._all.add_text("", "small-strong")
        self._all.add_icon("chevron", theme.TEXT_3, 12)
        self._all.clicked.connect(lambda: self.all_picker_requested.emit(self._all))
        add = Button("Adicionar arquivos", "secondary", "plus", color=theme.TEXT_2)
        add.clicked.connect(self.browse_requested)
        self._primary = Button("Converter", "primary", "play", color=theme.ACCENT_TEXT, icon_size=12)
        self._primary.clicked.connect(queue.toggle)
        for b in (self._clear, self._all, add, self._primary):
            row.addWidget(b)
        col.addWidget(bar)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_empty())
        self._pages.addWidget(self._build_list())
        col.addWidget(self._pages, 1)

        queue.items_changed.connect(self.refresh)
        queue.item_changed.connect(self._on_item_changed)
        queue.running_changed.connect(lambda _r: self.refresh())
        self.refresh()

    def _build_list(self) -> QWidget:
        page = QWidget()
        col = vbox(page)
        col.addWidget(column_header(["Nome", "Converter para", "Status", ""], COLUMNS))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self._list = vbox(body)
        self._list.addStretch(1)
        more = Button("Adicione mais arquivos ou solte-os em qualquer lugar", "dashed", "plus",
                      color=theme.MUTED, hover=theme.TEXT, height=44)
        more.clicked.connect(self.browse_requested)
        more_wrap = QWidget()
        hbox(more_wrap, (20, 12, 20, 12)).addWidget(more)
        self._list.insertWidget(0, more_wrap)
        self._more = more_wrap
        scroll.setWidget(body)
        self._scroll = scroll
        col.addWidget(scroll, 1)
        return page

    def _build_empty(self) -> QWidget:
        page = QWidget()
        outer = vbox(page, (32, 32, 32, 32))
        outer.addStretch(1)
        zone = frame("dropzone")
        zone.setMaximumWidth(560)
        zcol = vbox(zone, (40, 48, 40, 48))
        tile = frame("icon-tile")
        tile.setFixedSize(44, 44)
        hbox(tile).addWidget(icon_label("upload", theme.ACCENT, 20), 0, Qt.AlignmentFlag.AlignCenter)
        zcol.addWidget(tile, 0, Qt.AlignmentFlag.AlignHCenter)
        zcol.addSpacing(18)
        title = text("Solte arquivos para converter", "empty-title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        zcol.addWidget(title)
        zcol.addSpacing(6)
        body = text(
            "Imagens, documentos, áudio, vídeo, arquivos compactados e e-books. "
            "Tudo é processado neste dispositivo.", "empty-body", wrap=True,
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setFixedWidth(380)  # a fixed width lets the wrapped label get its full height
        zcol.addWidget(body, 0, Qt.AlignmentFlag.AlignHCenter)
        zcol.addSpacing(20)
        actions = hbox(spacing=10)
        actions.addStretch(1)
        choose = Button("Escolher arquivos…", "primary", height=32)
        choose.setContentsMargins(14, 0, 14, 0)
        choose.clicked.connect(self.browse_requested)
        actions.addWidget(choose)
        keys = hbox(spacing=3)
        for key in (platform.SHORTCUT_MOD, "O"):
            chip = frame("kbd")
            hbox(chip, (6, 2, 6, 2)).addWidget(text(key, "mono-dim"))
            keys.addWidget(chip)
        actions.addLayout(keys)
        actions.addStretch(1)
        zcol.addLayout(actions)
        center = hbox()
        center.addStretch(1)
        center.addWidget(zone, 10)
        center.addStretch(1)
        outer.addLayout(center)
        outer.addStretch(1)
        return page

    # State

    def set_selected(self, item_id: str | None) -> None:
        self._selected = item_id
        for rid, row in self._rows.items():
            row.set_selected(rid == item_id)
        if item_id in self._rows:
            self._scroll.ensureWidgetVisible(self._rows[item_id], 0, 0)

    def refresh(self) -> None:
        q = self._queue
        items = q.items
        self._pages.setCurrentIndex(1 if items else 0)
        self._sync_rows(items)
        for item in items:
            self._rows[item.id].update_item(item, q.running)
        self._update_header()

    def _sync_rows(self, items: list[QueueItem]) -> None:
        ids = [i.id for i in items]
        for rid in list(self._rows):
            if rid not in ids:
                self._rows.pop(rid).deleteLater()
        for item in items:
            if item.id not in self._rows:
                row = QueueRow(item)
                row.selected.connect(self.row_selected)
                row.pick_requested.connect(self.pick_requested)
                row.remove_requested.connect(self._queue.remove)
                row.reveal_requested.connect(self.reveal_requested)
                row.set_selected(item.id == self._selected)
                self._rows[item.id] = row
        for i, rid in enumerate(ids):
            row = self._rows[rid]
            if self._list.indexOf(row) != i:
                self._list.insertWidget(i, row)

    def _on_item_changed(self, item_id: str) -> None:
        item = self._queue.get(item_id)
        if item and item_id in self._rows:
            self._rows[item_id].update_item(item, self._queue.running)
        self._update_header()

    def _update_header(self) -> None:
        q = self._queue
        items = q.items
        n = len(items)
        done = sum(1 for i in items if i.is_finished)
        pending, active = q.pending, q.active
        pickable = [i for i in items if i.status.value not in ("converting", "unsupported")]
        total = sum(i.size for i in items)
        summary = "Nenhum arquivo adicionado"
        if n:
            summary = f"{plural(n, 'arquivo', 'arquivos')} · {fmt_size(total)}"
            if done:
                summary += f" · {plural(done, 'concluído', 'concluídos')}"
        self._summary.setText(summary)
        self._clear.setVisible(done > 0)
        self._all.setVisible(bool(pickable))
        targets = {i.target for i in pickable}
        self._all_target.setText(targets.pop() if len(targets) == 1 else "Vários")
        self._primary.setVisible(n > 0)
        if q.running:
            label, icon_name = "Pausar", "pause"
        elif active:
            label, icon_name = "Retomar", "play"
        elif pending:
            label, icon_name = f"Converter {plural(len(pending), 'arquivo', 'arquivos')}", "play"
        else:
            label, icon_name = "Converter", "play"
        self._primary.setText(label)
        self._primary.set_icon(icon_name, theme.ACCENT_TEXT)
        self._primary.setEnabled(q.running or bool(pending))
