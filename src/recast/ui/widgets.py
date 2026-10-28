"""Small reusable widgets that reproduce the mockup's controls."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from recast.ui import icons, theme


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_prop(widget: QWidget, name: str, value) -> None:
    if widget.property(name) != value:
        widget.setProperty(name, value)
        repolish(widget)


def text(value: str = "", role: str = "name", wrap: bool = False, parent: QWidget | None = None) -> QLabel:
    label = QLabel(value, parent)
    label.setProperty("t", role)
    label.setWordWrap(wrap)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return label


class ElidedLabel(QLabel):
    """Single-line label that elides with "…" instead of growing its parent."""

    def __init__(self, value: str = "", role: str = "name", parent: QWidget | None = None) -> None:
        super().__init__(value, parent)
        self.setProperty("t", role)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setFont(self.font())
        elided = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.width())
        painter.drawText(self.rect(), int(self.alignment() | Qt.AlignmentFlag.AlignVCenter), elided)
        tip = self.text() if elided != self.text() else ""
        if self.toolTip() != tip:
            self.setToolTip(tip)


def icon_label(name: str, color: str, size: int = 16) -> QLabel:
    label = QLabel()
    label.setPixmap(icons.pixmap(name, color, size))
    label.setFixedSize(size, size)
    return label


class Button(QPushButton):
    """QPushButton with a role from the stylesheet and an icon that recolors on hover."""

    def __init__(
        self, label: str = "", role: str = "secondary", icon: str | None = None,
        color: str = theme.TEXT_2, hover: str | None = None, icon_size: int = 14, height: int = 30,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(label, parent)
        self.setProperty("role", role)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if height:
            self.setFixedHeight(height)
        self._icon_name, self._color, self._hover = icon, color, hover or color
        self._icon_size = icon_size
        if icon:
            self.setIconSize(QSize(icon_size, icon_size))
            self._apply_icon(self._color)

    def set_icon(self, name: str, color: str | None = None, hover: str | None = None) -> None:
        self._icon_name = name
        self._color = color or self._color
        self._hover = hover or self._color
        self.setIconSize(QSize(self._icon_size, self._icon_size))
        self._apply_icon(self._hover if self.underMouse() else self._color)

    def _apply_icon(self, color: str) -> None:
        if self._icon_name:
            self.setIcon(icons.icon(self._icon_name, color, self._icon_size, disabled_color=theme.FAINT))

    def enterEvent(self, event) -> None:
        self._apply_icon(self._hover)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._apply_icon(self._color)
        super().leaveEvent(event)


class CompositeButton(QPushButton):
    """A button whose content is a row of labels/icons (for mixed colors and trailing chevrons)."""

    def __init__(self, role: str = "secondary", height: int = 30, margins=(10, 0, 10, 0), spacing: int = 6,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", role)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if height:
            self.setFixedHeight(height)
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(*margins)
        self.row.setSpacing(spacing)

    def _own(self, widget: QWidget) -> QWidget:
        widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.row.addWidget(widget)
        return widget

    def add_text(self, value: str, role: str, elided: bool = False) -> QLabel:
        return self._own(ElidedLabel(value, role) if elided else text(value, role))

    def add_icon(self, name: str, color: str, size: int = 12) -> QLabel:
        return self._own(icon_label(name, color, size))

    def add_stretch(self) -> None:
        self.row.addStretch(1)

    def sizeHint(self) -> QSize:
        return self.row.sizeHint()

    def minimumSizeHint(self) -> QSize:
        return self.row.minimumSize()


class SegmentedControl(QFrame):
    """Pill-shaped exclusive choice (mockup's seg())."""

    changed = Signal(str)

    def __init__(self, options: Sequence[str] = (), current: str | None = None, min_width: int = 0,
                 expand: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "segmented")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.buttonClicked.connect(lambda b: self.changed.emit(b.property("value")))
        self._min_width, self._expand = min_width, expand
        self._buttons: dict[str, QPushButton] = {}
        self.set_options(options, current)

    def set_options(self, options: Sequence[str], current: str | None = None) -> None:
        if list(options) == list(self._buttons) and current is not None:
            self.set_current(current)
            return
        for b in self._buttons.values():
            self._group.removeButton(b)
            b.deleteLater()
        self._buttons = {}
        for option in options:
            b = QPushButton(option)
            b.setProperty("role", "seg")
            b.setProperty("value", option)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFixedHeight(24)
            if self._min_width:
                b.setMinimumWidth(self._min_width)
            if self._expand:
                b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._group.addButton(b)
            self._layout.addWidget(b)
            self._buttons[option] = b
        self.set_current(current)

    def set_current(self, value: str | None) -> None:
        # An exclusive group ignores setChecked(False), so lift it to allow "nothing selected".
        self._group.setExclusive(False)
        for option, b in self._buttons.items():
            b.setChecked(option == value)
        self._group.setExclusive(True)

    def set_enabled_options(self, enabled: Sequence[str]) -> None:
        for option, b in self._buttons.items():
            b.setEnabled(option in enabled)

    def current(self) -> str | None:
        b = self._group.checkedButton()
        return b.property("value") if b else None


class ToggleSwitch(QAbstractButton):
    """30×18 switch with an animated knob."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(30, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.toggled.connect(self._animate)

    def set_checked_silently(self, checked: bool) -> None:
        self.blockSignals(True)
        self.setChecked(checked)
        self.blockSignals(False)
        self._pos = 1.0 if checked else 0.0
        self.update()

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_knob(self) -> float:
        return self._pos

    def _set_knob(self, value: float) -> None:
        self._pos = value
        self.update()

    knob = Property(float, _get_knob, _set_knob)

    def sizeHint(self) -> QSize:
        return QSize(30, 18)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        off, on = QColor(theme.TOGGLE_OFF), QColor(theme.ACCENT)
        t = self._pos
        track = QColor(
            round(off.red() + (on.red() - off.red()) * t), round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, 30, 18), 9, 9)
        p.setBrush(QColor(theme.KNOB))
        p.drawEllipse(QRectF(2 + 12 * t, 2, 14, 14))


class FileBadge(QWidget):
    """Tinted document icon with the extension at the bottom (mockup's file icon)."""

    SIZES = {"row": (26, 32, 7.5, 4), "inspector": (34, 42, 8.5, 5), "history": (22, 28, 0, 0)}

    def __init__(self, variant: str = "row", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._w, self._h, self._font_px, self._pad = self.SIZES[variant]
        self.setFixedSize(self._w, self._h)
        self._ext, self._tint = "", theme.MUTED
        self._border_alpha = 0.3 if variant != "row" else 0.28

    def set_file(self, ext: str, tint: str) -> None:
        self._ext, self._tint = ext.upper(), tint
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tint = QColor(self._tint)
        bg, border = QColor(tint), QColor(tint)
        bg.setAlphaF(0.08)
        border.setAlphaF(self._border_alpha)
        radius = 5 if self._w > 30 else 4
        p.setPen(QPen(border, 1))
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(0.5, 0.5, self._w - 1, self._h - 1), radius, radius)
        if self._font_px and self._ext:
            font = QFont(theme.SANS)
            font.setPointSizeF(self._font_px * 0.75)
            font.setWeight(QFont.Weight.Bold)
            p.setFont(font)
            p.setPen(tint)
            rect = QRectF(1, 0, self._w - 2, self._h - self._pad)
            ext = self._ext if len(self._ext) <= 4 else self._ext[:4]
            p.drawText(rect, int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom), ext)


class Dot(QWidget):
    def __init__(self, color: str = theme.GREEN, size: int = 6, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = color
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self._color))
        p.drawEllipse(self.rect())


def frame(role: str | None = None, parent: QWidget | None = None) -> QFrame:
    f = QFrame(parent)
    if role:
        f.setProperty("role", role)
    return f


def hbox(widget: QWidget | None = None, margins=(0, 0, 0, 0), spacing: int = 0) -> QHBoxLayout:
    layout = QHBoxLayout(widget) if widget is not None else QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout


def vbox(widget: QWidget | None = None, margins=(0, 0, 0, 0), spacing: int = 0) -> QVBoxLayout:
    layout = QVBoxLayout(widget) if widget is not None else QVBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return layout
