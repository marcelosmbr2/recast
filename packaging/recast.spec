# PyInstaller spec for the Windows build: a windowed, one-folder bundle in dist/Recast.
# Run through packaging/build.ps1, which also creates build/recast.ico.

from pathlib import Path

import deno
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent  # noqa: F821 — SPECPATH is defined by PyInstaller

datas = (
    collect_data_files("recast", includes=["resources/fonts/*"])
    + collect_data_files("imageio_ffmpeg", includes=["binaries/*.exe"])  # FFmpeg
    + collect_data_files("pypandoc", includes=["files/*"])  # pandoc.exe
    + [(deno.find_deno_bin(), "tools")]  # Deno runtime for yt-dlp's YouTube JS challenges (engines/download.py)
)
# yt-dlp registers its own PyInstaller hook (lazy extractors, yt_dlp_ejs scripts, networking extras).
binaries = collect_dynamic_libs("pillow_heif") + collect_dynamic_libs("pypdfium2_raw")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=["recast.selftest", "yt_dlp.extractor.youtube", "yt_dlp.extractor.vimeo"],
    # mutagen is an optional yt-dlp dependency (GPL) that Recast never uses: keep it out of the bundle.
    excludes=["tkinter", "unittest", "pydoc_data", "mutagen"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Recast",
    console=False,
    icon=str(ROOT / "build" / "recast.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Recast", upx=False)  # noqa: F821
