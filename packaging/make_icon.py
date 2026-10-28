"""Write the multi-size Windows icon used by the executable and the installer."""

import io
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from recast.ui.icons import APP_ICON_SIZES, app_icon_image  # noqa: E402


def main(out: Path) -> None:
    app = QGuiApplication([])  # noqa: F841 — QSvgRenderer needs an application
    frames = []
    for size in APP_ICON_SIZES:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        app_icon_image(size).save(buf, "PNG")
        frames.append(Image.open(io.BytesIO(bytes(buf.data()))))
    out.parent.mkdir(parents=True, exist_ok=True)
    largest = frames[-1]
    largest.save(out, format="ICO", sizes=[(s, s) for s in APP_ICON_SIZES], append_images=frames[:-1])
    print(f"wrote {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
