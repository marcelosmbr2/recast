"""Conversion queue: owns the items, schedules jobs on a thread pool and moves results into place."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
from collections.abc import Iterable
from pathlib import Path

from PySide6.QtCore import QFile, QObject, QRunnable, QThreadPool, Signal

from recast.core.formats import (
    CAT_DEFAULT, COMPAT, DEFAULT_TARGET, FORMATS, category_of, is_same_format, quality_preset_name,
    target_category,
)
from recast.core.models import Preset, QueueItem, Status
from recast.core.storage import SettingsStore
from recast.engines.base import Cancelled, ConversionError, Job, JobContext
from recast.engines.registry import engine_for, is_supported

log = logging.getLogger(__name__)

# Serializes "pick a free output name + move" across workers.
_FINALIZE_LOCK = threading.Lock()


def split_name(name: str) -> tuple[str, str]:
    """('backup', 'gz') for 'backup.tar.gz'; ('photo', 'heic') for 'photo.HEIC'."""
    lower = name.lower()
    if lower.endswith(".tar.gz"):
        return name[:-7], "gz"
    if "." not in name.strip("."):
        return name, ""
    stem, _, ext = name.rpartition(".")
    return stem, ext.lower()


def default_target(ext: str, cat: str) -> tuple[str, str] | None:
    """Mockup's makeFile target choice, falling back to the first format an engine supports."""
    target = DEFAULT_TARGET.get(ext) or CAT_DEFAULT[cat]
    if is_same_format(ext, target):
        target = next(t for t, _ in FORMATS[cat] if not is_same_format(ext, t))
    tcat = target_category(cat, target)
    if is_supported(ext, target, tcat):
        return target, tcat
    for c in COMPAT[cat]:
        for t, _ in FORMATS[c]:
            if not is_same_format(ext, t) and is_supported(ext, t, c):
                return t, c
    return None


def make_item(path: Path) -> QueueItem:
    _, ext = split_name(path.name)
    cat = category_of(ext)
    choice = default_target(ext, cat)
    target, tcat = choice or (CAT_DEFAULT[cat], cat)
    item = QueueItem(path=path, ext=ext, cat=cat, size=path.stat().st_size, target=target, target_cat=tcat)
    if choice is None:
        item.status = Status.UNSUPPORTED
    return item


def can_target(item: QueueItem, target: str, target_cat: str) -> bool:
    return (
        target_cat in COMPAT[item.cat]
        and not is_same_format(item.ext, target)
        and is_supported(item.ext, target, target_cat)
    )


def _unique(dest: Path) -> Path:
    name = dest.name
    base, suffix = (name[:-7], name[-7:]) if name.lower().endswith(".tar.gz") else (dest.stem, dest.suffix)
    n = 1
    while dest.exists():
        dest = dest.with_name(f"{base} ({n}){suffix}")
        n += 1
    return dest


def _move(src: Path, dest: Path) -> None:
    try:
        os.replace(src, dest)
    except OSError:  # different drive
        tmp = dest.with_name(dest.name + ".recast-tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
        src.unlink()


class _Bridge(QObject):
    progress = Signal(str, float)
    finished = Signal(str, str, int, bool)  # id, out_path, out_size, skipped
    failed = Signal(str, str)
    cancelled = Signal(str)


class _Worker(QRunnable):
    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        self._fn()


class ConversionQueue(QObject):
    item_changed = Signal(str)
    items_changed = Signal()
    running_changed = Signal(bool)
    item_converted = Signal(object)
    queue_finished = Signal(int, int)  # files saved, files failed in this run

    def __init__(self, settings: SettingsStore, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.items: list[QueueItem] = []
        self.running = False
        self._jobs: dict[str, JobContext] = {}
        self._rates: dict[str, tuple[float, float, float | None]] = {}
        self._run_saved = self._run_failed = 0
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(4)
        self._bridge = _Bridge(self)
        self._bridge.progress.connect(self._on_progress)
        self._bridge.finished.connect(self._on_finished)
        self._bridge.failed.connect(self._on_failed)
        settings.changed.connect(self._dispatch)

    # Queries

    def get(self, item_id: str | None) -> QueueItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    @property
    def pending(self) -> list[QueueItem]:
        return [i for i in self.items if i.is_pending]

    @property
    def active(self) -> list[QueueItem]:
        return [i for i in self.items if i.status is Status.CONVERTING]

    # Editing

    def add_paths(self, paths: Iterable[Path]) -> list[QueueItem]:
        queued = {i.path for i in self.items if i.is_pending}
        added = []
        for path in self._expand(paths):
            if path in queued:
                continue
            try:
                added.append(make_item(path))
            except OSError:
                log.warning("Skipping unreadable file %s", path)
        if added:
            self.items.extend(added)
            self.items_changed.emit()
        return added

    @staticmethod
    def _expand(paths: Iterable[Path]) -> list[Path]:
        out = []
        for p in map(Path, paths):
            if p.is_dir():
                out.extend(sorted(c for c in p.rglob("*") if c.is_file() and not c.name.startswith(".")))
            elif p.is_file():
                out.append(p)
        return out

    def remove(self, item_id: str) -> None:
        item = self.get(item_id)
        if not item:
            return
        if ctx := self._jobs.pop(item_id, None):
            ctx.cancel()
        self.items.remove(item)
        self.items_changed.emit()
        self._dispatch()
        self._check_finished(notify=False)

    def clear_done(self) -> None:
        self.items = [i for i in self.items if not i.is_finished]
        self.items_changed.emit()

    def set_target(self, item_id: str, target: str, target_cat: str) -> None:
        item = self.get(item_id)
        if not item or item.status is Status.CONVERTING:
            return
        self._retarget(item, target, target_cat)
        self.item_changed.emit(item_id)

    def set_target_all(self, target: str, target_cat: str) -> int:
        n = 0
        for item in self.items:
            if item.status is not Status.CONVERTING and can_target(item, target, target_cat):
                self._retarget(item, target, target_cat)
                n += 1
        self.items_changed.emit()
        return n

    def set_options(self, item_id: str, **values) -> None:
        item = self.get(item_id)
        if not item:
            return
        item.opts = item.opts.merged(values)
        self.item_changed.emit(item_id)

    def apply_preset(self, preset: Preset) -> int:
        n = 0
        for item in self.items:
            if item.status is Status.CONVERTING or item.ext not in preset.sources:
                continue
            if not can_target(item, preset.target, preset.target_cat):
                continue
            self._retarget(item, preset.target, preset.target_cat, force_reset=True)
            item.opts = item.opts.merged(
                {"quality": preset.quality, "preset": quality_preset_name(preset.quality), **preset.opts}
            )
            n += 1
        self.items_changed.emit()
        return n

    def apply_to_category(self, source: QueueItem) -> int:
        """Copy the target and options of `source` to every item of the same category."""
        n = 0
        for item in self.items:
            if item.cat != source.cat or item.status is Status.CONVERTING:
                continue
            if item is not source and not can_target(item, source.target, source.target_cat):
                continue
            if item is not source:
                self._retarget(item, source.target, source.target_cat)
                item.opts = source.opts.merged({})
            n += 1
        self.items_changed.emit()
        return n

    @staticmethod
    def _retarget(item: QueueItem, target: str, target_cat: str, force_reset: bool = False) -> None:
        item.target, item.target_cat = target, target_cat
        if force_reset or item.status in (Status.DONE, Status.SKIPPED, Status.ERROR, Status.UNSUPPORTED):
            item.reset()

    # Running

    def start(self) -> None:
        if not self.pending:
            return
        self.running = True
        for ctx in self._jobs.values():
            ctx.set_suspended(False)
        for item in self.active:  # measure the rate again from here; pause dropped it
            self._rates[item.id] = (time.monotonic(), item.progress, None)
        self.running_changed.emit(True)
        self._dispatch()

    def pause(self) -> None:
        if not self.running:
            return
        self.running = False
        for ctx in self._jobs.values():
            ctx.set_suspended(True)
        for item in self.active:
            item.eta = None
            self._rates.pop(item.id, None)
        self.running_changed.emit(False)
        self.items_changed.emit()

    def toggle(self) -> None:
        self.pause() if self.running else self.start()

    def shutdown(self) -> None:
        self.running = False
        for ctx in self._jobs.values():
            ctx.cancel()
        self._pool.waitForDone(5000)

    def _dispatch(self) -> None:
        if not self.running:
            return
        slots = self._settings.settings.parallel - len(self.active)
        for item in [i for i in self.items if i.status is Status.READY][: max(0, slots)]:
            self._start_job(item)

    def _start_job(self, item: QueueItem) -> None:
        engine = engine_for(item.ext, item.target, item.target_cat)
        if engine is None:
            item.status = Status.UNSUPPORTED
            self.item_changed.emit(item.id)
            return
        settings = self._settings.settings
        staging = Path(tempfile.mkdtemp(prefix="recast-"))
        (staging / "out").mkdir()
        (staging / "work").mkdir()
        stem, _ = split_name(item.name)
        job = Job(
            src=item.path, src_ext=item.ext, target=item.target, target_cat=item.target_cat,
            opts=item.opts.merged({}), staging=staging / "out", stem=stem, hw=settings.hw,
        )
        item_id = item.id
        last = [0.0, -1.0]

        def on_progress(fraction: float) -> None:
            now = time.monotonic()
            if fraction >= 1 or fraction - last[1] >= 0.005 or now - last[0] >= 0.25:
                last[:] = [now, fraction]
                self._bridge.progress.emit(item_id, fraction)

        ctx = JobContext(on_progress, staging / "work")
        self._jobs[item_id] = ctx
        folder, conflict, keep = Path(settings.folder), settings.conflict, settings.keep
        bridge = self._bridge

        def run() -> None:
            try:
                engine.convert(job, ctx)
                ctx.check_cancel()
                out, size, skipped = self._finalize(job, folder, conflict)
                if not keep and not skipped:
                    QFile.moveToTrash(str(job.src))
                bridge.finished.emit(item_id, str(out), size, skipped)
            except Cancelled:
                bridge.cancelled.emit(item_id)
            except ConversionError as e:
                bridge.failed.emit(item_id, str(e))
            except Exception as e:  # engines wrap third-party code; never kill the worker
                log.exception("Conversion of %s failed", job.src)
                bridge.failed.emit(item_id, f"Erro inesperado: {e}")
            finally:
                shutil.rmtree(staging, ignore_errors=True)

        item.status = Status.CONVERTING
        item.progress = 0.0
        item.eta = None
        self._rates[item_id] = (time.monotonic(), 0.0, None)
        self.item_changed.emit(item_id)
        self._pool.start(_Worker(run))

    @staticmethod
    def _finalize(job: Job, folder: Path, conflict: str) -> tuple[Path, int, bool]:
        files = sorted(job.staging.iterdir())
        if not files:
            raise ConversionError("Nenhum arquivo foi gerado")
        if job.dst in files:
            files.remove(job.dst)
            files.insert(0, job.dst)
        folder.mkdir(parents=True, exist_ok=True)
        main: Path | None = None
        total = 0
        with _FINALIZE_LOCK:
            for f in files:
                dest = folder / f.name
                if dest.exists():
                    if conflict == "Ignorar":
                        if main is None:
                            return dest, dest.stat().st_size, True
                        continue
                    if conflict == "Renomear":
                        dest = _unique(dest)
                _move(f, dest)
                total += dest.stat().st_size
                main = main or dest
        return main, total, False

    # Worker callbacks (GUI thread)

    def _on_progress(self, item_id: str, fraction: float) -> None:
        item = self.get(item_id)
        if not item or item.status is not Status.CONVERTING:
            return
        now = time.monotonic()
        rate = None
        if item_id not in self._rates:
            self._rates[item_id] = (now, fraction, None)
        else:
            t0, p0, rate = self._rates[item_id]
            if self.running and now > t0 and fraction > p0:
                inst = (fraction - p0) / (now - t0)
                rate = inst if rate is None else 0.3 * inst + 0.7 * rate
                self._rates[item_id] = (now, fraction, rate)
        item.progress = fraction
        item.eta = (1 - fraction) / rate if rate else None
        self.item_changed.emit(item_id)

    def _on_finished(self, item_id: str, out: str, size: int, skipped: bool) -> None:
        self._jobs.pop(item_id, None)
        self._rates.pop(item_id, None)
        item = self.get(item_id)
        if item:
            item.status = Status.SKIPPED if skipped else Status.DONE
            item.progress, item.out_path, item.out_size, item.eta = 1.0, Path(out), size, None
            self.item_changed.emit(item_id)
            if not skipped:
                self._run_saved += 1
                self.item_converted.emit(item)
        self._dispatch()
        self._check_finished()

    def _on_failed(self, item_id: str, message: str) -> None:
        self._jobs.pop(item_id, None)
        self._rates.pop(item_id, None)
        item = self.get(item_id)
        if item:
            item.status, item.error, item.eta = Status.ERROR, message, None
            self._run_failed += 1
            self.item_changed.emit(item_id)
        self._dispatch()
        self._check_finished()

    def _check_finished(self, notify: bool = True) -> None:
        if self.pending:
            return
        was_running = self.running
        self.running = False
        if was_running:
            self.running_changed.emit(False)
            if notify:
                self.queue_finished.emit(self._run_saved, self._run_failed)
        self._run_saved = self._run_failed = 0  # nothing pending: the run is over
