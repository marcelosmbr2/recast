"""Design tokens taken from the mockup and the global stylesheet built from them."""

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

SANS = "Inter"
MONO = "JetBrains Mono"

# Surfaces
WINDOW = "#151516"
SIDEBAR = "#111112"
BAR = "#121213"
INSPECTOR = "#131314"
CARD = "#141415"
CONTROL = "#1c1c1e"
CONTROL_HOVER = "#232326"
FIELD = "#1a1a1c"
FIELD_DARK = "#161618"
SEG_TRACK = "#0f0f10"
SEG_BORDER = "#232326"
SEG_ON = "#2a2a2e"
NAV_ON = "#1f1f22"
ROW_SELECTED = "#1c1c1f"
ROW_HOVER = "#18181a"
POPUP = "#1a1a1c"
TILE = "#1f1f22"
TOAST = "#1f1f22"
PROGRESS_TRACK = "#26262a"

# Lines
BORDER = "#222224"
BORDER_SOFT = "#1e1e20"
ROW_LINE = "#1c1c1e"
CONTROL_BORDER = "#2a2a2d"
CONTROL_BORDER_HOVER = "#38383d"
POPUP_BORDER = "#2e2e32"
DASHED = "#2c2c30"

# Text
TEXT = "#ededee"
TEXT_2 = "#d6d6da"
TEXT_3 = "#a0a0a8"
MUTED = "#8a8a93"
DIM = "#7c7c85"
FAINT = "#6b6b73"
ARROW = "#55555c"

# Accents
ACCENT = "#ee7a3a"
ACCENT_HOVER = "#f38a4d"
ACCENT_TEXT = "#1a0d05"
ACCENT_SOFT = "#f59a62"
GREEN = "#5bbf8a"
RED = "#e5636b"
PAUSED = "#5a5a62"
TOGGLE_OFF = "#2e2e33"
KNOB = "#f4f4f5"


def pt(px: float) -> str:
    """Qt rounds px font sizes; points keep the mockup's fractional sizes (96 dpi)."""
    return f"{px * 0.75:g}pt"


def alpha(hex_color: str, a: float) -> str:
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"


# Text roles used as QLabel[t="..."]: (px size, weight, color, mono)
TEXT_ROLES: dict[str, tuple[float, int, str, bool]] = {
    "title": (14, 600, TEXT, False),
    "subtitle": (11.5, 400, DIM, False),
    "name": (13, 500, TEXT, False),
    "name-plain": (13, 400, TEXT, False),
    "meta": (11.5, 400, DIM, False),
    "colhead": (11, 500, DIM, False),
    "section": (11, 500, DIM, False),
    "field": (11.5, 500, MUTED, False),
    "setting": (13, 500, TEXT, False),
    "setting-desc": (12, 400, MUTED, False),
    "body-strong": (12.5, 500, TEXT, False),
    "small": (12, 400, TEXT_3, False),
    "small-dim": (12, 400, DIM, False),
    "small-2": (12, 400, TEXT_2, False),
    "small-strong": (12, 500, TEXT, False),
    "hint": (12.5, 400, DIM, False),
    "status-label": (11.5, 400, TEXT_2, False),
    "mono": (11.5, 400, TEXT_3, True),
    "mono-dim": (11, 400, DIM, True),
    "mono-muted": (11.5, 400, MUTED, True),
    "mono-2": (11.5, 400, TEXT_2, True),
    "mono-count": (10.5, 400, FAINT, True),
    "empty-title": (16, 600, TEXT, False),
    "empty-body": (12.5, 400, MUTED, False),
    "drop-title": (15, 600, TEXT, False),
    "card-title": (12, 600, TEXT, False),
    "card-body": (11.5, 400, MUTED, False),
    "brand": (13, 600, TEXT, False),
    "status": (11, 400, DIM, False),
    "status-strong": (11, 400, TEXT_3, False),
    "error": (12, 400, RED, False),
    "ext-tile": (13, 600, TEXT, False),
    "ext-tile-on": (13, 600, ACCENT_SOFT, False),
    "tile-desc": (11, 400, DIM, False),
    "toast-title": (12.5, 500, TEXT, False),
    "toast-sub": (11.5, 400, MUTED, False),
    "target": (12, 600, TEXT, False),
    "target-static": (12, 600, TEXT_3, False),
    "inspector-name": (13, 600, TEXT, False),
    "inspector-ext": (13, 600, TEXT, False),
    "estimate": (12, 500, TEXT, False),
    "cat": (12.5, 500, MUTED, False),
    "cat-on": (12.5, 500, TEXT, False),
}


def _text_rules() -> str:
    rules = []
    for role, (size, weight, color, mono) in TEXT_ROLES.items():
        family = f'font-family: "{MONO}";' if mono else ""
        rules.append(
            f'QLabel[t="{role}"] {{ font-size: {pt(size)}; font-weight: {weight}; color: {color}; {family} }}'
        )
    return "\n".join(rules)


STYLESHEET = f"""
* {{ font-family: "{SANS}"; outline: 0; }}
QMainWindow, QWidget#Root {{ background: {WINDOW}; }}
QToolTip {{ background: {TOAST}; color: {TEXT}; border: 1px solid {POPUP_BORDER}; padding: 4px 6px; }}
QLabel {{ background: transparent; color: {TEXT}; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: 0; }}
QScrollBar:vertical {{ width: 10px; background: transparent; margin: 0; }}
QScrollBar::handle:vertical {{ background: {CONTROL_BORDER}; border-radius: 2px; min-height: 30px; margin: 3px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}

/* Partial borders only render when the rule also sets a background. */
QFrame[role="sidebar"] {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QFrame[role="inspector"] {{ background: {INSPECTOR}; border-left: 1px solid {BORDER}; }}
QFrame[role="statusbar"] {{ background: {BAR}; border-top: 1px solid {BORDER}; }}
QFrame[role="header"] {{ background: transparent; border-bottom: 1px solid {BORDER}; }}
QFrame[role="colhead"] {{ background: transparent; border-bottom: 1px solid {BORDER_SOFT}; }}
QFrame[role="divider-top"] {{ background: transparent; border-top: 1px solid {BORDER_SOFT}; }}
QFrame[role="divider-bottom"] {{ background: transparent; border-bottom: 1px solid {BORDER_SOFT}; }}
QFrame[role="row"] {{ border-bottom: 1px solid {ROW_LINE}; background: transparent; }}
QFrame[role="row"][hoverable="true"]:hover {{ background: {ROW_HOVER}; }}
QFrame[role="row"][selected="true"] {{ background: {ROW_SELECTED}; }}
QFrame[role="card"] {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame[role="pill"] {{ border: 1px solid #26262a; border-radius: 11px; }}
QFrame[role="segmented"] {{ background: {SEG_TRACK}; border: 1px solid {SEG_BORDER}; border-radius: 7px; }}
QFrame[role="savebox"] {{ background: {FIELD_DARK}; border: 1px solid {SEG_BORDER}; border-radius: 7px; }}
QFrame[role="popup"] {{ background: {POPUP}; border: 1px solid {POPUP_BORDER}; border-radius: 10px; }}
QFrame[role="popup-head"] {{ border-bottom: 1px solid #26262a; }}
QFrame[role="popup-cats"] {{ border-right: 1px solid #26262a; }}
QFrame[role="toast"] {{ background: {TOAST}; border: 1px solid {POPUP_BORDER}; border-radius: 8px; }}
QFrame[role="kbd"] {{ background: {FIELD}; border: 1px solid {SEG_ON}; border-radius: 4px; }}
QFrame[role="dropzone"] {{ border: 1px dashed #2e2e33; border-radius: 12px; }}
QFrame[role="icon-tile"] {{ background: {CONTROL}; border: 1px solid #2a2a2e; border-radius: 10px; }}
QFrame[role="esc"] {{ border: 1px solid #2a2a2e; border-radius: 4px; }}

QPushButton {{ border: 0; border-radius: 6px; background: transparent; color: {TEXT_3};
    font-size: {pt(12.5)}; font-weight: 500; padding: 0 10px; text-align: center; }}
QPushButton:disabled {{ color: {FAINT}; }}
QPushButton[role="nav"] {{ text-align: left; font-size: {pt(13)}; color: {TEXT_3}; padding: 0 10px; }}
QPushButton[role="nav"]:hover {{ color: {TEXT}; }}
QPushButton[role="nav"][active="true"] {{ background: {NAV_ON}; color: {TEXT}; }}
QPushButton[role="quick"]:hover {{ background: {ROW_HOVER}; }}
QPushButton[role="ghost"] {{ color: {TEXT_3}; }}
QPushButton[role="ghost"]:hover {{ color: {TEXT}; background: {CONTROL}; }}
QPushButton[role="secondary"] {{ background: {CONTROL}; border: 1px solid {CONTROL_BORDER}; color: {TEXT_2}; }}
QPushButton[role="secondary"]:hover {{ background: {CONTROL_HOVER}; }}
QPushButton[role="secondary"]:disabled {{ color: {FAINT}; background: {CONTROL}; }}
QPushButton[role="primary"] {{ background: {ACCENT}; color: {ACCENT_TEXT}; font-weight: 600; }}
QPushButton[role="primary"]:hover {{ background: {ACCENT_HOVER}; }}
QPushButton[role="primary"]:disabled {{ background: rgba(238,122,58,0.4); color: rgba(26,13,5,0.6); }}
QPushButton[role="pick"] {{ background: {CONTROL}; border: 1px solid #2a2a2e; padding: 0 7px 0 10px; }}
QPushButton[role="pick"]:hover {{ background: {CONTROL_HOVER}; border-color: {CONTROL_BORDER_HOVER}; }}
QPushButton[role="pick"]:disabled {{ background: {CONTROL}; }}
QPushButton[role="field"] {{ background: {FIELD}; border: 1px solid #2a2a2e; border-radius: 7px; padding: 0 10px 0 12px; }}
QPushButton[role="field"]:hover {{ border-color: #3a3a3f; }}
QPushButton[role="icon"] {{ padding: 0; color: {DIM}; }}
QPushButton[role="icon"]:hover {{ background: {CONTROL_HOVER}; }}
QPushButton[role="dashed"] {{ border: 1px dashed {DASHED}; border-radius: 8px; color: {MUTED}; }}
QPushButton[role="dashed"]:hover {{ border-color: #3d3d42; color: {TEXT}; }}
QPushButton[role="link"] {{ color: {TEXT_3}; font-size: {pt(12)}; padding: 0 8px; border-radius: 5px; }}
QPushButton[role="link"]:hover {{ color: {TEXT}; background: {CONTROL_HOVER}; }}
QPushButton[role="seg"] {{ border-radius: 5px; font-size: {pt(12)}; color: {MUTED}; padding: 0 10px; }}
QPushButton[role="seg"]:checked {{ background: {SEG_ON}; color: {TEXT}; }}
QPushButton[role="seg"]:disabled {{ color: #4a4a50; }}
QPushButton[role="cat"] {{ text-align: left; font-size: {pt(12.5)}; color: {MUTED}; padding: 0 9px; }}
QPushButton[role="cat"]:hover {{ color: {TEXT}; }}
QPushButton[role="cat"][active="true"] {{ background: #26262a; color: {TEXT}; }}
QPushButton[role="tile"] {{ background: {TILE}; border: 1px solid #2a2a2e; border-radius: 7px; }}
QPushButton[role="tile"]:hover {{ border-color: #3d3d42; }}
QPushButton[role="tile"][current="true"] {{ background: rgba(238,122,58,0.12); border-color: rgba(238,122,58,0.55); }}

QLineEdit {{ background: transparent; border: 0; color: {TEXT}; font-size: {pt(13)};
    selection-background-color: {alpha(ACCENT, 0.45)}; }}
QLineEdit[role="input"] {{ background: {FIELD}; border: 1px solid #2a2a2e; border-radius: 6px; padding: 0 8px; min-height: 28px; }}
QLineEdit[role="input"]:focus {{ border-color: #3a3a3f; }}

QSlider::groove:horizontal {{ height: 4px; background: {PROGRESS_TRACK}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ height: 4px; background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: {KNOB}; }}

QProgressBar {{ background: {PROGRESS_TRACK}; border: 0; border-radius: 1px; max-height: 3px; min-height: 3px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 1px; }}
QProgressBar[paused="true"]::chunk {{ background: {PAUSED}; }}

QDialog {{ background: {WINDOW}; }}
QComboBox {{ background: {FIELD}; border: 1px solid #2a2a2e; border-radius: 6px; padding: 0 8px; min-height: 28px;
    color: {TEXT}; font-size: {pt(12.5)}; }}
QComboBox QAbstractItemView {{ background: {POPUP}; color: {TEXT}; border: 1px solid {POPUP_BORDER};
    selection-background-color: {SEG_ON}; }}
QSpinBox {{ background: {FIELD}; border: 1px solid #2a2a2e; border-radius: 6px; padding: 0 6px; min-height: 28px;
    color: {TEXT}; font-size: {pt(12.5)}; }}

{_text_rules()}
"""


def apply(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in [
        (QPalette.ColorRole.Window, WINDOW), (QPalette.ColorRole.Base, FIELD),
        (QPalette.ColorRole.AlternateBase, CONTROL), (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.WindowText, TEXT), (QPalette.ColorRole.Button, CONTROL),
        (QPalette.ColorRole.ButtonText, TEXT_2), (QPalette.ColorRole.Highlight, ACCENT),
        (QPalette.ColorRole.HighlightedText, ACCENT_TEXT), (QPalette.ColorRole.ToolTipBase, TOAST),
        (QPalette.ColorRole.ToolTipText, TEXT), (QPalette.ColorRole.PlaceholderText, DIM),
    ]:
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
