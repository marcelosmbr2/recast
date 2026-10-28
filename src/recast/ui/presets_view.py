from __future__ import annotations

import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QLineEdit, QScrollArea, QSpinBox, QWidget,
)

from recast.core.formats import CATEGORIES, FORMATS, LOSSLESS, quality_preset_name
from recast.core.models import Preset
from recast.core.storage import PresetStore
from recast.ui import theme
from recast.ui.convert_view import header
from recast.ui.widgets import Button, hbox, text, vbox


class PresetRow(QFrame):
    apply_requested = Signal(object)
    delete_requested = Signal(str)

    def __init__(self, preset: Preset, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "row")
        self.setProperty("hoverable", True)
        self.setMinimumHeight(60)
        row = hbox(self, (20, 10, 16, 10), 16)
        texts = vbox(spacing=3)
        texts.addWidget(text(preset.name, "name"))
        texts.addWidget(text(preset.detail, "meta"))
        row.addLayout(texts, 1)
        rule = text(preset.rule, "mono")
        rule.setFixedWidth(230)
        row.addWidget(rule)
        actions = hbox(spacing=4)
        actions.addStretch(1)
        if not preset.builtin:
            delete = Button("", "icon", "close", color=theme.FAINT, hover=theme.TEXT, icon_size=14, height=28)
            delete.setFixedWidth(28)
            delete.setToolTip("Excluir predefinição")
            delete.clicked.connect(lambda: self.delete_requested.emit(preset.id))
            actions.addWidget(delete)
        apply = Button("Aplicar", "secondary", height=28)
        apply.clicked.connect(lambda: self.apply_requested.emit(preset))
        actions.addWidget(apply)
        cell = QWidget()
        cell.setFixedWidth(116)
        cell.setLayout(actions)
        row.addWidget(cell)


class NewPresetDialog(QDialog):
    """Name, source extensions, target format and quality for a user preset."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nova predefinição")
        self.setMinimumWidth(420)
        col = vbox(self, (20, 18, 20, 16), 14)
        col.addWidget(text("Nova predefinição", "title"))
        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self._name = QLineEdit()
        self._name.setProperty("role", "input")
        self._name.setPlaceholderText("Ex.: Capturas de tela para WEBP")
        self._sources = QLineEdit()
        self._sources.setProperty("role", "input")
        self._sources.setPlaceholderText("png, jpg, bmp")
        self._target = QComboBox()
        for cat, formats in FORMATS.items():
            for ext, desc in formats:
                self._target.addItem(f"{ext}  ·  {CATEGORIES[cat].label}", (ext, cat))
        self._quality = QSpinBox()
        self._quality.setRange(10, 100)
        self._quality.setValue(80)
        self._quality.setSuffix("%")
        for label, widget in [("Nome", self._name), ("Extensões de origem", self._sources),
                              ("Converter para", self._target), ("Qualidade", self._quality)]:
            form.addRow(text(label, "field"), widget)
        col.addLayout(form)
        buttons = QDialogButtonBox()
        cancel = Button("Cancelar", "ghost")
        self._save = Button("Salvar", "primary")
        buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton(self._save, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        col.addWidget(buttons)
        self._name.textChanged.connect(self._validate)
        self._sources.textChanged.connect(self._validate)
        self._validate()

    def _validate(self) -> None:
        self._save.setEnabled(bool(self._name.text().strip() and self.sources()))

    def sources(self) -> list[str]:
        raw = self._sources.text().replace(";", ",").replace(" ", ",")
        return list(dict.fromkeys(s.strip().lstrip(".").lower() for s in raw.split(",") if s.strip(" .")))

    def preset(self) -> Preset:
        target, cat = self._target.currentData()
        q = self._quality.value()
        if cat not in ("image", "video", "audio"):
            detail = CATEGORIES[cat].one
        elif target in LOSSLESS:
            detail = "Sem perdas"
        else:
            detail = f"Qualidade {q} · {quality_preset_name(q)}"
        return Preset(
            id="u" + uuid.uuid4().hex[:8], name=self._name.text().strip(), sources=self.sources(),
            target=target, target_cat=cat, quality=q, detail=detail,
        )


class PresetsView(QWidget):
    apply_requested = Signal(object)

    def __init__(self, presets: PresetStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._presets = presets
        col = vbox(self)
        bar, row, _ = header(
            "Predefinições",
            "Regras salvas de formato e qualidade. Aplique uma a todos os arquivos correspondentes na fila.",
        )
        new = Button("Nova predefinição", "secondary", "plus", color=theme.TEXT_2)
        new.clicked.connect(self._new_preset)
        row.addWidget(new)
        col.addWidget(bar)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self._list = vbox(body)
        scroll.setWidget(body)
        col.addWidget(scroll, 1)
        presets.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for preset in self._presets.presets:
            row = PresetRow(preset)
            row.apply_requested.connect(self.apply_requested)
            row.delete_requested.connect(self._presets.remove)
            self._list.addWidget(row)
        self._list.addStretch(1)

    def _new_preset(self) -> None:
        dialog = NewPresetDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._presets.add(dialog.preset())

