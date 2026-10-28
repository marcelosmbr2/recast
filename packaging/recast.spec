# PyInstaller spec for the Windows build: a windowed, one-folder bundle in dist/Recast.
# Run through packaging/build.ps1, which also creates build/recast.ico.

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

ROOT = Path(SPECPATH).parent  # noqa: F821 — SPECPATH is defined by PyInstaller

datas = (
    collect_data_files("recast", includes=["resources/fonts/*"])
    + collect_data_files("imageio_ffmpeg", includes=["binaries/*.exe"])  # FFmpeg
    + collect_data_files("pypandoc", includes=["files/*"])  # pandoc.exe
)
binaries = collect_dynamic_libs("pillow_heif") + collect_dynamic_libs("pypdfium2_raw")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=["recast.selftest"],
    excludes=["tkinter", "unittest", "pydoc_data"],
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
