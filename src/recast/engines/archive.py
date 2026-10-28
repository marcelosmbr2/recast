from __future__ import annotations

import bz2
import gzip
import shutil
import tarfile
import zipfile
from pathlib import Path

import py7zr

from recast.engines.base import ConversionError, Engine, Job, JobContext

READABLE = set("zip 7z tar gz tgz bz2".split())
TARGETS = {"ZIP", "7Z", "TAR.GZ", "TAR"}
ZIP_LEVEL = {"Rápida": 1, "Normal": 6, "Máxima": 9}
LZMA_PRESET = {"Rápida": 1, "Normal": 5, "Máxima": 9}


class ArchiveEngine(Engine):
    name = "Compactação"

    def supports(self, src_ext: str, target: str, target_cat: str) -> bool:
        return src_ext in READABLE and target_cat == "archive" and target in TARGETS

    def convert(self, job: Job, ctx: JobContext) -> None:
        root = ctx.tmp / "contents"
        root.mkdir()
        try:
            self._extract(job.src, job.src_ext, root, job.stem)
        except (OSError, zipfile.BadZipFile, tarfile.TarError, py7zr.exceptions.ArchiveError, EOFError) as e:
            raise ConversionError(f"Arquivo compactado inválido: {e}") from e
        ctx.progress(0.5)
        files = sorted(p for p in root.rglob("*") if p.is_file())
        total = sum(p.stat().st_size for p in files) or 1
        done = 0

        def step(p: Path) -> None:
            nonlocal done
            done += p.stat().st_size
            ctx.progress(0.5 + 0.5 * done / total)

        level = job.opts.level
        if job.target == "ZIP":
            with zipfile.ZipFile(job.dst, "w", zipfile.ZIP_DEFLATED, compresslevel=ZIP_LEVEL.get(level, 6)) as zf:
                for p in files:
                    zf.write(p, p.relative_to(root).as_posix())
                    step(p)
        elif job.target == "7Z":
            filters = [{"id": py7zr.FILTER_LZMA2, "preset": LZMA_PRESET.get(level, 5)}]
            with py7zr.SevenZipFile(job.dst, "w", filters=filters) as zf:
                for p in files:
                    zf.write(p, p.relative_to(root).as_posix())
                    step(p)
        else:
            mode, kwargs = ("w:gz", {"compresslevel": ZIP_LEVEL.get(level, 6)}) if job.target == "TAR.GZ" else ("w", {})
            with tarfile.open(job.dst, mode, **kwargs) as tf:
                for p in files:
                    tf.add(p, p.relative_to(root).as_posix())
                    step(p)
        ctx.progress(1.0)

    @staticmethod
    def _extract(src: Path, ext: str, root: Path, stem: str) -> None:
        if ext == "zip":
            with zipfile.ZipFile(src) as zf:
                zf.extractall(root)  # zipfile strips absolute paths and ".." components
        elif ext == "7z":
            with py7zr.SevenZipFile(src, "r") as zf:
                zf.extractall(root)
        elif tarfile.is_tarfile(src):
            with tarfile.open(src) as tf:
                tf.extractall(root, filter="data")
        elif ext in ("gz", "bz2"):
            opener = gzip.open if ext == "gz" else bz2.open
            with opener(src, "rb") as fin, open(root / stem, "wb") as fout:
                shutil.copyfileobj(fin, fout)
        else:
            raise ConversionError("Formato de arquivo compactado não suportado")
