"""OS-specific wording and the "reveal in file manager" action."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

if sys.platform == "darwin":
    FILE_MANAGER, DEVICE, SHORTCUT_MOD = "Finder", "neste Mac", "⌘"
elif sys.platform == "win32":
    FILE_MANAGER, DEVICE, SHORTCUT_MOD = "Explorer", "neste PC", "Ctrl"
else:
    FILE_MANAGER, DEVICE, SHORTCUT_MOD = "gerenciador de arquivos", "neste computador", "Ctrl"

REVEAL_LABEL = f"Mostrar no {FILE_MANAGER}"


def reveal(path: Path) -> bool:
    """Select `path` in the system file manager (or open its folder). False if it no longer exists."""
    if not path.exists():
        return False
    if sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{path}"])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
    return True


def display_path(path: str) -> str:
    """'~/Documents/Recast' style path for labels."""
    home = str(Path.home())
    return "~" + path[len(home):].replace("\\", "/") if path.startswith(home) else path
