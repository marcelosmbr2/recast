from __future__ import annotations

from collections import Counter

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect, QGridLayout, QLineEdit, QPushButton, QScrollArea, QWidget,
)

from recast.core.formats import CATEGORIES, COMPAT, FORMATS, is_same_format
from recast.core.models import QueueItem, Status
from recast.core.queue import can_target
from recast.ui import theme
from recast.ui.widgets import ElidedLabel, frame, hbox, icon_label, set_prop, text, vbox

W, H, SHADOW = 500, 372, 18


class FormatPicker(QWidget):
    """Popup to choose a target format for one item (`item`) or for every compatible item."""

    chosen = Signal(str, str)

    def __init__(self, items: list[QueueItem], item: QueueItem | None, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._item = item
        self._pickable = [i for i in items if i.status not in (Status.CONVERTING, Status.UNSUPPORTED)]
        if item:
            self._cats = COMPAT[item.cat]
            self._cat = item.target_cat
        else:
            self._cats = list(dict.fromkeys(c for i in self._pickable for c in COMPAT[i.cat]))
            common = Counter(i.cat for i in self._pickable).most_common(1)
            self._cat = common[0][0] if common else "image"

        self.setFixedSize(W + 2 * SHADOW, H + 2 * SHADOW)
        panel = frame("popup", self)
        panel.setGeometry(SHADOW, SHADOW, W, H)
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(50)
        shadow.setOffset(0, 20)
        shadow.setColor(QColor(0, 0, 0, 140))
        panel.setGraphicsEffect(shadow)
        col = vbox(panel)

        head = frame("popup-head")
        head.setFixedHeight(44)
        hrow = hbox(head, (14, 0, 12, 0), 9)
        hrow.addWidget(icon_label("search", theme.DIM, 15))
        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar formatos")
        self._search.textChanged.connect(self._render)
        hrow.addWidget(self._search, 1)
        hrow.addWidget(text(f"{item.ext.upper()} → …" if item else "Todos os arquivos", "meta"))
        esc = frame("esc")
        hbox(esc, (6, 1, 6, 1)).addWidget(text("esc", "mono-dim"))
        hrow.addWidget(esc, 0, Qt.AlignmentFlag.AlignVCenter)
        col.addWidget(head)

        body = hbox(spacing=0)
        cats = frame("popup-cats")
        cats.setFixedWidth(140)
        ccol = vbox(cats, (6, 6, 6, 6), 1)
        self._cat_buttons: dict[str, QPushButton] = {}
        self._cat_labels: dict[str, QWidget] = {}
        for c in self._cats:
            b = QPushButton()
            b.setProperty("role", "cat")
            b.setFixedHeight(30)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            brow = hbox(b, (9, 0, 9, 0))
            label = text(CATEGORIES[c].label, "cat")
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            count = text(str(len(FORMATS[c])), "mono-count")
            count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            brow.addWidget(label)
            brow.addStretch(1)
            brow.addWidget(count)
            b.clicked.connect(lambda _=False, cat=c: self._select_cat(cat))
            ccol.addWidget(b)
            self._cat_buttons[c] = b
            self._cat_labels[c] = label
        ccol.addStretch(1)
        body.addWidget(cats)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        self._content = vbox(content, (12, 12, 12, 12), 8)
        self._heading = text("", "colhead")
        self._heading.setContentsMargins(2, 0, 2, 0)
        self._content.addWidget(self._heading)
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(6)
        for c in range(3):
            self._grid.setColumnStretch(c, 1)
        self._content.addWidget(self._grid_host)
        self._empty = text("Nenhum formato compatível com este arquivo.", "hint")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setContentsMargins(0, 40, 0, 40)
        self._content.addWidget(self._empty)
        self._content.addStretch(1)
        scroll.setWidget(content)
        body.addWidget(scroll, 1)
        col.addLayout(body, 1)
        self._render()

    def popup_at(self, anchor: QWidget) -> None:
        """Place under `anchor`, kept inside the window (mockup's openPicker)."""
        win = self.parentWidget().window()
        wr = QRect(win.mapToGlobal(QPoint(0, 0)), win.size())
        ar = QRect(anchor.mapToGlobal(QPoint(0, 0)), anchor.size())
        left, top = ar.left(), ar.bottom() + 6
        if left + W > wr.right() - 12:
            left = wr.right() - W - 12
        left = max(left, wr.left() + 12)
        if top + H > wr.bottom() - 34:
            top = max(wr.top() + 48, ar.top() - H - 6)
        self.move(left - SHADOW, top - SHADOW)
        self.show()
        self._search.setFocus()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def _select_cat(self, cat: str) -> None:
        self._cat = cat
        self._search.blockSignals(True)
        self._search.clear()
        self._search.blockSignals(False)
        self._render()

    def _entries(self, query: str) -> list[tuple[str, str, str]]:
        if not query:
            return [(ext, desc, self._cat) for ext, desc in FORMATS[self._cat]]
        out = []
        for c in self._cats:
            for ext, desc in FORMATS[c]:
                hay = (ext + " " + desc + " " + CATEGORIES[c].label).lower()
                if query in hay:
                    out.append((ext, desc, c))
        return out

    def _render(self) -> None:
        query = self._search.text().strip().lower()
        for c, b in self._cat_buttons.items():
            on = not query and c == self._cat
            set_prop(b, "active", on)
            set_prop(self._cat_labels[c], "t", "cat-on" if on else "cat")
        self._heading.setText("Resultados" if query else CATEGORIES[self._cat].label)
        while self._grid.count():
            self._grid.takeAt(0).widget().deleteLater()
        entries = self._entries(query)
        for n, (ext, desc, cat) in enumerate(entries):
            self._grid.addWidget(self._tile(ext, desc, cat, bool(query)), n // 3, n % 3)
        self._empty.setVisible(not entries)

    def _tile(self, ext: str, desc: str, cat: str, searching: bool) -> QPushButton:
        item = self._item
        current = bool(item and item.target == ext and item.target_cat == cat)
        if item:
            same = is_same_format(item.ext, ext)
            enabled = not same and can_target(item, ext, cat)
            note = "Formato atual" if same else ("Indisponível" if not enabled else None)
        else:
            enabled = any(can_target(i, ext, cat) for i in self._pickable)
            note = None if enabled else "Indisponível"
        b = QPushButton()
        b.setProperty("role", "tile")
        b.setProperty("current", current)
        b.setProperty("available", enabled)
        b.setFixedHeight(52)
        b.setMinimumWidth(0)
        b.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ArrowCursor)
        tcol = vbox(b, (10, 0, 10, 0), 3)
        tcol.addStretch(1)
        ext_label = text(ext, "ext-tile-on" if current else "ext-tile")
        label = CATEGORIES[cat].label + " · " + desc if searching else desc
        desc_label = ElidedLabel(note or label, "tile-desc")
        for w in (ext_label, desc_label):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            tcol.addWidget(w)
        tcol.addStretch(1)
        if not enabled:
            for w in (ext_label, desc_label):
                w.setEnabled(False)
            b.setStyleSheet("QPushButton { background: rgba(31,31,34,0.4); border-color: rgba(42,42,46,0.4); }"
                            "QLabel { color: rgba(237,237,238,0.4); }")
        else:
            b.clicked.connect(lambda _=False: self._choose(ext, cat))
        return b

    def _choose(self, ext: str, cat: str) -> None:
        self.chosen.emit(ext, cat)
        self.close()
