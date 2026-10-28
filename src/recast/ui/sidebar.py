from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QWidget

from recast.core.models import Preset
from recast.ui import platform, theme
from recast.ui.widgets import Button, CompositeButton, frame, hbox, icon_label, set_prop, text, vbox

VIEWS = ("convert", "history", "presets", "settings")


class Sidebar(QFrame):
    view_selected = Signal(str)
    preset_clicked = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "sidebar")
        self.setFixedWidth(220)
        col = vbox(self, (8, 12, 8, 12), 0)

        brand = hbox(margins=(10, 2, 2, 12), spacing=6)
        brand.addWidget(text("Recast", "brand"))
        brand.addStretch(1)
        pill = frame("pill")
        pill.setFixedHeight(22)
        pill_row = hbox(pill, (7, 0, 9, 0), 6)
        pill_row.addWidget(icon_label("shield", theme.GREEN, 13))
        pill_row.addWidget(text("Offline", "status-strong"))
        brand.addWidget(pill)
        col.addLayout(brand)

        self._nav: dict[str, Button] = {}
        nav = vbox(spacing=2)
        for view, label, icon in [
            ("convert", "Converter", "convert"), ("history", "Histórico", "history"),
            ("presets", "Predefinições", "presets"),
        ]:
            nav.addWidget(self._nav_button(view, label, icon))
        col.addLayout(nav)
        self._count = text("", "mono-dim")
        self._count.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        count_row = hbox(self._nav["convert"], (0, 0, 10, 0))
        count_row.addStretch(1)
        count_row.addWidget(self._count)

        col.addSpacing(22)
        heading = text("Predefinições rápidas", "section")
        heading.setContentsMargins(10, 0, 10, 6)
        col.addWidget(heading)
        self._quick = vbox(spacing=1)
        col.addLayout(self._quick)

        col.addStretch(1)
        col.addWidget(self._nav_button("settings", "Ajustes", "settings"))
        col.addSpacing(10)
        card = frame("card")
        card_col = vbox(card, (12, 10, 12, 10), 4)
        title = hbox(spacing=7)
        title.addWidget(icon_label("lock", theme.GREEN, 13))
        title.addWidget(text(f"Processado {platform.DEVICE}", "card-title"))
        title.addStretch(1)
        card_col.addLayout(title)
        card_col.addWidget(text("O Recast não tem acesso à rede. Seus arquivos nunca são enviados.", "card-body", wrap=True))
        wrap = hbox(margins=(4, 0, 4, 0))
        wrap.addWidget(card)
        col.addLayout(wrap)
        self.set_view("convert")

    def _nav_button(self, view: str, label: str, icon: str) -> Button:
        b = Button(label, "nav", icon, color=theme.TEXT_3, hover=theme.TEXT, icon_size=16, height=32)
        b.clicked.connect(lambda: self.view_selected.emit(view))
        self._nav[view] = b
        return b

    def set_view(self, view: str) -> None:
        for name, b in self._nav.items():
            active = name == view
            set_prop(b, "active", active)
            b.set_icon(b._icon_name, theme.TEXT if active else theme.TEXT_3, theme.TEXT)

    def set_pending(self, count: int) -> None:
        self._count.setText(str(count) if count else "")

    def set_presets(self, presets: list[Preset]) -> None:
        while self._quick.count():
            w = self._quick.takeAt(0).widget()
            if w:
                w.deleteLater()
        for preset in presets[:4]:
            b = CompositeButton("quick", height=30, margins=(10, 0, 10, 0), spacing=8)
            b.setToolTip(preset.name)
            src = b.add_text(preset.sources[0].upper(), "mono-muted")
            src.setMinimumWidth(34)
            b.add_icon("arrow", theme.ARROW, 12)
            b.add_text(preset.target, "mono-2")
            b.add_stretch()
            b.clicked.connect(lambda _=False, p=preset: self.preset_clicked.emit(p))
            self._quick.addWidget(b)
