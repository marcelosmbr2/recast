from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QScrollArea, QWidget

from recast.core.storage import SettingsStore
from recast.ui import platform, theme
from recast.ui.convert_view import header
from recast.ui.widgets import Button, SegmentedControl, ToggleSwitch, frame, hbox, icon_label, text, vbox

TOGGLES = [
    ("hw", "Aceleração de hardware", "Usa a GPU e o mecanismo de mídia para vídeo quando disponível."),
    ("keep", "Manter arquivos originais", "Os originais permanecem onde estão após a conversão."),
    ("notify", "Avisar ao terminar", "Mostra uma notificação quando a fila termina."),
]


class SettingsView(QWidget):
    change_folder_requested = Signal()

    def __init__(self, store: SettingsStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        col = vbox(self)
        bar, _row, _ = header("Ajustes")
        col.addWidget(bar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        outer = vbox(body, (20, 8, 20, 24))
        content = QWidget()
        content.setMaximumWidth(700)
        self._rows = vbox(content)
        outer.addWidget(content)
        outer.addStretch(1)
        scroll.setWidget(body)
        col.addWidget(scroll, 1)

        folder_box = hbox(spacing=8)
        self._folder = text("", "mono")
        change = Button("Alterar…", "secondary", height=28)
        change.clicked.connect(self.change_folder_requested)
        folder_box.addWidget(self._folder)
        folder_box.addWidget(change)
        self._add_row("Pasta de saída", "Os arquivos convertidos são salvos aqui.", folder_box)

        self._conflict = SegmentedControl(["Renomear", "Substituir", "Ignorar"], min_width=68)
        self._conflict.changed.connect(lambda v: store.update(conflict=v))
        self._add_row("Se o arquivo já existir", "Vale quando o nome de saída já está em uso.", self._conflict)

        self._parallel = SegmentedControl(["1", "2", "4"], min_width=44)
        self._parallel.changed.connect(lambda v: store.update(parallel=int(v)))
        self._add_row("Conversões simultâneas", "Valores maiores são mais rápidos, mas usam mais memória.",
                      self._parallel)

        self._toggles: dict[str, ToggleSwitch] = {}
        for key, label, desc in TOGGLES:
            toggle = ToggleSwitch()
            toggle.toggled.connect(lambda on, k=key: store.update(**{k: on}))
            self._toggles[key] = toggle
            self._add_row(label, desc, toggle)

        network = hbox(spacing=6)
        network.addWidget(icon_label("lock", theme.GREEN, 13))
        network.addWidget(text("Desativado", "small-strong"))
        self._add_row(
            "Acesso à rede",
            "O Recast nunca se conecta à internet. Os arquivos são processados apenas "
            f"{platform.DEVICE}.", network, last=True,
        )
        store.changed.connect(self.refresh)
        self.refresh()

    def _add_row(self, label: str, desc: str, control, last: bool = False) -> None:
        row = frame(None if last else "divider-bottom")
        layout = hbox(row, (0, 16, 0, 16), 24)
        texts = vbox(spacing=3)
        texts.addWidget(text(label, "setting"))
        texts.addWidget(text(desc, "setting-desc", wrap=True))
        layout.addLayout(texts, 1)
        if isinstance(control, QWidget):
            layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            layout.addLayout(control)
        self._rows.addWidget(row)

    def refresh(self) -> None:
        s = self._store.settings
        self._folder.setText(platform.display_path(s.folder))
        self._conflict.set_current(s.conflict)
        self._parallel.set_current(str(s.parallel))
        for key, toggle in self._toggles.items():
            if toggle.isChecked() != getattr(s, key):
                toggle.set_checked_silently(getattr(s, key))
