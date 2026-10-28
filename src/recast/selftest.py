"""`recast --self-test [report.txt]`: convert generated samples with every engine and report.

Used to check a packaged build (PyInstaller bundle, installed app, CI), where a missing
bundled tool or DLL only shows up at conversion time.
"""

from __future__ import annotations

import subprocess
import tempfile
import traceback
import zipfile
from pathlib import Path

from PIL import Image

from recast.core.models import ConversionOptions
from recast.core.queue import split_name
from recast.engines.base import _NO_WINDOW, Job, JobContext
from recast.engines.media import ffmpeg_exe
from recast.engines.registry import engine_for

CASES = [
    ("photo.png", "WEBP", "image"), ("photo.png", "HEIC", "image"), ("photo.png", "AVIF", "image"),
    ("photo.png", "PDF", "document"), ("tone.wav", "MP3", "audio"), ("clip.mp4", "WEBM", "video"),
    ("clip.mp4", "PNG", "image"), ("notes.md", "DOCX", "document"), ("notes.md", "PDF", "document"),
    ("notes.md", "EPUB", "ebook"), ("bundle.zip", "7Z", "archive"),
]


def _samples(d: Path) -> None:
    Image.new("RGBA", (320, 200), (238, 122, 58, 200)).save(d / "photo.png")
    ff = ffmpeg_exe()
    for args in (
        ["-f", "lavfi", "-i", "sine=duration=1", d / "tone.wav"],
        ["-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1", "-pix_fmt", "yuv420p", d / "clip.mp4"],
    ):
        subprocess.run([ff, "-y", "-loglevel", "error", *map(str, args)], check=True, creationflags=_NO_WINDOW)
    (d / "notes.md").write_text("# Recast\n\nTeste de conversão com acentuação.\n", encoding="utf-8")
    with zipfile.ZipFile(d / "bundle.zip", "w") as zf:
        zf.writestr("a.txt", "recast " * 200)


def _convert(src: Path, target: str, target_cat: str, root: Path) -> Path:
    stem, ext = split_name(src.name)
    engine = engine_for(ext, target, target_cat)
    if engine is None:
        raise RuntimeError("no engine")
    run = Path(tempfile.mkdtemp(dir=root))
    (run / "out").mkdir()
    (run / "work").mkdir()
    job = Job(src, ext, target, target_cat, ConversionOptions(), run / "out", stem)
    engine.convert(job, JobContext(lambda _f: None, run / "work"))
    if not job.dst.exists() or job.dst.stat().st_size == 0:
        raise RuntimeError("empty output")
    return job.dst


def run(report: Path | None) -> int:
    lines, failed = [], 0
    with tempfile.TemporaryDirectory(prefix="recast-selftest-") as tmp:
        root = Path(tmp)
        try:
            _samples(root)
        except Exception:
            lines.append("FAIL samples\n" + traceback.format_exc())
            failed += 1
        else:
            outputs = {}
            for name, target, cat in CASES:
                try:
                    outputs[(name, target)] = _convert(root / name, target, cat, root)
                    lines.append(f"OK   {name} -> {target}")
                except Exception as e:
                    failed += 1
                    lines.append(f"FAIL {name} -> {target}: {e!r}")
            pdf = outputs.get(("notes.md", "PDF"))
            if pdf:  # PDF text proves the bundled fonts were found
                try:
                    txt = _convert(pdf, "TXT", "document", root)
                    ok = "Teste de conversão" in txt.read_text(encoding="utf-8")
                    failed += not ok
                    lines.append(f"{'OK  ' if ok else 'FAIL'} notes.pdf -> TXT (text round trip)")
                except Exception as e:
                    failed += 1
                    lines.append(f"FAIL notes.pdf -> TXT: {e!r}")
    lines.append(f"{len(lines) - failed} ok, {failed} failed")
    text = "\n".join(lines) + "\n"
    if report:
        report.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 1 if failed else 0
