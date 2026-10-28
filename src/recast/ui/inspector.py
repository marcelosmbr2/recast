from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QScrollArea, QSlider, QStackedWidget, QWidget

from recast.core.formats import (
    CATEGORIES, LOSSLESS, QUALITY_PRESETS, estimate_factor, fmt_size, format_description, has_quality,
    quality_preset_name,
)
from recast.core.models import QueueItem, Status
from recast.engines.media import video_codecs
from recast.ui import icons, platform, theme
from recast.ui.widgets import (
    Button, CompositeButton, ElidedLabel, FileBadge, SegmentedControl, ToggleSwitch, frame, hbox, text, vbox,
)


def _fields_for(item: QueueItem) -> list[tuple]:
    """(kind, key, label, options-or-description) for the target category (mockup's inspector())."""
    tc, target = item.target_cat, item.target
    fields: list[tuple] = []
    if tc == "video":
        codecs = video_codecs(target)
        if codecs:
            fields.append(("seg", "codec", "Codec", codecs))
        fields.append(("seg", "res", "Resolução", ["Original", "1080p", "720p"]))
    elif tc == "audio":
        if target not in LOSSLESS:
            fields.append(("seg", "bitrate", "Taxa de bits", ["128 kbps", "192 kbps", "320 kbps"]))
        fields.append(("seg", "channels", "Canais", ["Estéreo", "Mono"]))
    elif tc == "image":
        fields.append(("seg", "resize", "Redimensionar", ["Original", "50%", "2560 px"]))
        fields.append(("toggle", "strip", "Remover metadados", "Remove localização e dados da câmera"))
    elif tc == "document":
        fields.append(("toggle", "compress", "Comprimir imagens", "Reduz imagens incorporadas para 150 dpi"))
    elif tc == "archive":
        fields.append(("seg", "level", "Compressão", ["Rápida", "Normal", "Máxima"]))
    return fields


def estimate_label(item: QueueItem) -> tuple[str, str]:
    if item.status is Status.DONE:
        return "Tamanho final", fmt_size(item.out_size)
    return "Tamanho estimado", "≈ " + fmt_size(round(item.size * estimate_factor(item.target, item.target_cat, item.opts)))


class Inspector(QFrame):
    pick_requested = Signal(str, QWidget)
    options_changed = Signal(str, dict)
    apply_all_requested = Signal(str)
    change_folder_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "inspector")
        self.setFixedWidth(300)
        self._item: QueueItem | None = None
        self._key = None
        self._controls: dict[str, QWidget] = {}
        col = vbox(self)
        self._pages = QStackedWidget()
        col.addWidget(self._pages)

        empty = text("Selecione um arquivo para ajustar as configurações de saída.", "hint", wrap=True)
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setContentsMargins(24, 24, 24, 24)
        self._pages.addWidget(empty)

        page = QWidget()
        pcol = vbox(page)
        head = frame("divider-bottom")
        head_row = hbox(head, (18, 18, 18, 16), 12)
        self._badge = FileBadge("inspector")
        head_row.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignTop)
        names = vbox(spacing=3)
        names.setContentsMargins(0, 2, 0, 0)
        self._name = text("", "inspector-name", wrap=True)
        self._meta = text("", "meta")
        names.addWidget(self._name)
        names.addWidget(self._meta)
        head_row.addLayout(names, 1)
        pcol.addWidget(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self._body = vbox(body, (18, 16, 18, 16), 18)
        scroll.setWidget(body)
        pcol.addWidget(scroll, 1)

        foot = frame("divider-top")
        fcol = vbox(foot, (18, 14, 18, 14), 10)
        est = hbox()
        self._est_label = text("", "setting-desc")
        self._est = text("", "estimate")
        est.addWidget(self._est_label)
        est.addStretch(1)
        est.addWidget(self._est)
        fcol.addLayout(est)
        self._apply = Button("", "secondary")
        self._apply.clicked.connect(lambda: self._item and self.apply_all_requested.emit(self._item.id))
        fcol.addWidget(self._apply)
        pcol.addWidget(foot)
        self._pages.addWidget(page)
        self._folder = ""

    def set_folder(self, folder: str) -> None:
        self._folder = folder
        if label := self._controls.get("folder"):
            label.setText(platform.display_path(folder))

    def set_item(self, item: QueueItem | None) -> None:
        self._item = item
        if item is None:
            self._key = None
            self._pages.setCurrentIndex(0)
            return
        self._pages.setCurrentIndex(1)
        key = (item.id, item.target, item.target_cat)
        if key != self._key:
            self._key = key
            self._rebuild(item)
        self._refresh(item)

    # Building

    def _section(self, label: str) -> object:
        box = vbox(spacing=7)
        box.addWidget(text(label, "field"))
        self._body.addLayout(box)
        return box

    def _rebuild(self, item: QueueItem) -> None:
        while self._body.count():
            child = self._body.takeAt(0)
            _clear_layout(child)
        self._controls = {}
        cat = CATEGORIES[item.cat]
        self._badge.set_file(item.ext, cat.tint)
        self._name.setText(item.name)
        self._meta.setText(f"{fmt_size(item.size)} · {cat.one} {item.ext.upper()}")
        self._apply.setText("Aplicar a " + cat.plural)

        box = self._section("Formato de saída")
        pick = CompositeButton("field", height=34, margins=(12, 0, 10, 0), spacing=10)
        pick.add_text(item.target, "inspector-ext")
        pick.add_text(format_description(item.target_cat, item.target), "small-dim", elided=True)
        pick.row.setStretch(1, 1)
        pick.add_icon("chevron", theme.MUTED, 13)
        pick.clicked.connect(lambda: self._item and self.pick_requested.emit(self._item.id, pick))
        box.addWidget(pick)
        self._controls["pick"] = pick

        if has_quality(item.target, item.target_cat):
            qbox = vbox(spacing=9)
            top = hbox()
            top.addWidget(text("Qualidade", "field"))
            top.addStretch(1)
            qlabel = text("", "mono-2")
            top.addWidget(qlabel)
            qbox.addLayout(top)
            seg = SegmentedControl(list(QUALITY_PRESETS), expand=True)
            seg.changed.connect(lambda v: self._emit(preset=v, quality=QUALITY_PRESETS[v]))
            qbox.addWidget(seg)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(10, 100)
            slider.setCursor(Qt.CursorShape.PointingHandCursor)
            slider.valueChanged.connect(lambda q: self._emit(quality=q, preset=quality_preset_name(q)))
            qbox.addWidget(slider)
            self._body.addLayout(qbox)
            self._controls.update(quality_label=qlabel, quality_seg=seg, quality_slider=slider)

        for kind, key, label, extra in _fields_for(item):
            if kind == "seg":
                box = self._section(label)
                seg = SegmentedControl(extra, expand=True)
                seg.changed.connect(lambda v, k=key: self._emit(**{k: v}))
                box.addWidget(seg)
                self._controls[key] = seg
            else:
                row = hbox(spacing=12)
                texts = vbox(spacing=2)
                texts.addWidget(text(label, "body-strong"))
                texts.addWidget(text(extra, "meta", wrap=True))
                row.addLayout(texts, 1)
                toggle = ToggleSwitch()
                toggle.toggled.connect(lambda on, k=key: self._emit(**{k: on}))
                row.addWidget(toggle, 0, Qt.AlignmentFlag.AlignVCenter)
                self._body.addLayout(row)
                self._controls[key] = toggle

        box = self._section("Salvar em")
        save = frame("savebox")
        save.setFixedHeight(34)
        srow = hbox(save, (10, 0, 6, 0), 8)
        folder_icon = text()
        folder_icon.setPixmap(icons.pixmap("folder", theme.MUTED, 14))
        srow.addWidget(folder_icon)
        folder = ElidedLabel(platform.display_path(self._folder), "mono-2")
        srow.addWidget(folder, 1)
        change = Button("Alterar", "link", height=24)
        change.clicked.connect(self.change_folder_requested)
        srow.addWidget(change)
        box.addWidget(save)
        self._controls["folder"] = folder
        self._body.addStretch(1)

    def _refresh(self, item: QueueItem) -> None:
        o = item.opts
        self._controls["pick"].setEnabled(item.status is not Status.CONVERTING)
        if slider := self._controls.get("quality_slider"):
            self._controls["quality_label"].setText(f"{o.quality}%")
            self._controls["quality_seg"].set_current(o.preset)
            slider.blockSignals(True)
            slider.setValue(o.quality)
            slider.blockSignals(False)
        for kind, key, _label, extra in _fields_for(item):
            control = self._controls.get(key)
            if kind == "seg":
                value = getattr(o, key)
                control.set_current(value if value in extra else extra[0])
            elif control:
                control.set_checked_silently(getattr(o, key))
        label, value = estimate_label(item)
        self._est_label.setText(label)
        self._est.setText(value)

    def _emit(self, **values) -> None:
        if self._item:
            self.options_changed.emit(self._item.id, values)


def _clear_layout(child) -> None:
    if widget := child.widget():
        widget.deleteLater()
    elif layout := child.layout():
        while layout.count():
            _clear_layout(layout.takeAt(0))
        layout.deleteLater()
