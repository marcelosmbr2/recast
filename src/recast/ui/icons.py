"""Inline SVG icons from the mockup, rendered in any color."""

from __future__ import annotations

import functools

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

# name -> (svg body, stroke width or None for filled shapes)
ICONS: dict[str, tuple[str, float | None]] = {
    "convert": ('<path d="M4 8h14l-3.5-3.5"/><path d="M20 16H6l3.5 3.5"/>', 1.6),
    "history": ('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>', 1.6),
    "presets": ('<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/>'
                '<circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>', 1.6),
    "settings": ('<circle cx="12" cy="12" r="3"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 '
                 '1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>', 1.6),
    "shield": ('<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>', 1.8),
    "lock": ('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>', 1.8),
    "lock-bold": ('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>', 2),
    "arrow": ('<path d="M5 12h14M13 6l6 6-6 6"/>', 2),
    "chevron": ('<path d="M6 9l6 6 6-6"/>', 2),
    "plus": ('<path d="M12 5v14M5 12h14"/>', 1.8),
    "check": ('<path d="M5 12.5l4.5 4.5L19 7.5"/>', 2.2),
    "folder": ('<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>', 1.6),
    "close": ('<path d="M7 7l10 10M17 7L7 17"/>', 1.8),
    "upload": ('<path d="M12 15V4M7.5 8.5L12 4l4.5 4.5"/><path d="M4 15v3.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 '
               '1.5-1.5V15"/>', 1.7),
    "search": ('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>', 1.8),
    "alert": ('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5.5M12 16.2v.3"/>', 1.8),
    "pause": ('<rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/>',
              None),
    "play": ('<path d="M7 4.5v15l12.5-7.5z"/>', None),
}


def svg(name: str, color: str) -> bytes:
    body, stroke = ICONS[name]
    if stroke is None:
        attrs = f'fill="{color}"'
    else:
        attrs = (f'fill="none" stroke="{color}" stroke-width="{stroke}" '
                 'stroke-linecap="round" stroke-linejoin="round"')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" {attrs}>{body}</svg>'.encode()


@functools.cache
def pixmap(name: str, color: str, size: int) -> QPixmap:
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if app else 1.0
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg(name, color)))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str, size: int = 16, disabled_color: str | None = None) -> QIcon:
    result = QIcon(pixmap(name, color, size))
    if disabled_color:
        result.addPixmap(pixmap(name, disabled_color, size), QIcon.Mode.Disabled)
    return result


APP_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def app_icon_image(size: int) -> QImage:
    """The app icon: the orange convert arrows on a dark rounded tile."""
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    inset = size * 0.04
    tile = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    painter.setPen(QPen(QColor("#2a2a2e"), max(1.0, size / 64)))
    painter.setBrush(QColor("#1c1c1e"))
    painter.drawRoundedRect(tile, size * 0.22, size * 0.22)
    glyph = size * 0.62
    offset = (size - glyph) / 2
    QSvgRenderer(QByteArray(svg("convert", "#ee7a3a"))).render(painter, QRectF(offset, offset, glyph, glyph))
    painter.end()
    return img


def app_icon() -> QIcon:
    result = QIcon()
    for size in APP_ICON_SIZES:
        result.addPixmap(QPixmap.fromImage(app_icon_image(size)))
    return result
