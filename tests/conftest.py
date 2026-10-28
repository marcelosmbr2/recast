import os
import subprocess
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PIL import Image  # noqa: E402

from recast.engines.media import ffmpeg_exe  # noqa: E402
from recast.resources import load_fonts  # noqa: E402


@pytest.fixture(autouse=True)
def _app(qapp):
    """Document → PDF rendering needs a QGuiApplication and fonts (offscreen has none)."""
    load_fonts()
    return qapp


@pytest.fixture(scope="session")
def samples(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("samples")
    out = {}

    png = d / "photo.png"
    Image.new("RGBA", (640, 400), (238, 122, 58, 200)).save(png)
    out["png"] = png

    gif = d / "anim.gif"
    frames = [Image.new("RGB", (64, 64), c) for c in ("red", "green", "blue")]
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=100, loop=0)
    out["gif"] = gif

    ff = ffmpeg_exe()
    wav = d / "tone.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", wav], check=True)
    out["wav"] = wav
    mp4 = d / "clip.mp4"
    subprocess.run([
        ff, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15:duration=2",
        "-f", "lavfi", "-i", "sine=duration=2", "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", mp4,
    ], check=True)
    out["mp4"] = mp4

    zp = d / "bundle.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("readme.txt", "hello " * 100)
        zf.writestr("sub/data.bin", bytes(range(256)) * 40)
    out["zip"] = zp

    md = d / "notes.md"
    md.write_text("# Título\n\nUm parágrafo com **negrito** e acentuação.\n\n- item 1\n- item 2\n", encoding="utf-8")
    out["md"] = md

    txt = d / "plain.txt"
    txt.write_text("Primeira linha\n\nSegundo parágrafo <com> & símbolos.\n", encoding="utf-8")
    out["txt"] = txt
    return out
