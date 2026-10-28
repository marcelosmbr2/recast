"""Engine interface and the per-job context engines use to report progress and run tools."""

from __future__ import annotations

import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import psutil

from recast.core.models import ConversionOptions

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class ConversionError(Exception):
    """Conversion failed; the message is shown to the user (pt-BR)."""


class Cancelled(Exception):
    pass


@dataclass
class Job:
    src: Path
    src_ext: str
    target: str
    target_cat: str
    opts: ConversionOptions
    staging: Path  # engines write every output file here
    stem: str
    hw: bool = True

    @property
    def dst(self) -> Path:
        """Main output file inside the staging dir."""
        return self.staging / (self.stem + "." + self.target.lower())


class JobContext:
    """Created by the queue for each job; shared between the worker thread and the GUI thread."""

    def __init__(self, on_progress: Callable[[float], None], tmp: Path) -> None:
        self._on_progress = on_progress
        self.tmp = tmp
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._suspended = False

    # Called from the worker thread.

    def progress(self, fraction: float) -> None:
        self.check_cancel()
        self._on_progress(max(0.0, min(1.0, fraction)))

    def check_cancel(self) -> None:
        if self._cancel.is_set():
            raise Cancelled

    def run(self, args: list[str], on_line: Callable[[str], None] | None = None) -> None:
        """Run a tool, feeding stdout lines to `on_line`; raise ConversionError on failure."""
        self.check_cancel()
        proc = subprocess.Popen(
            [str(a) for a in args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
        )
        stderr_tail: deque[str] = deque(maxlen=20)
        reader = threading.Thread(target=lambda: stderr_tail.extend(proc.stderr), daemon=True)
        reader.start()
        with self._lock:
            self._proc = proc
            if self._suspended:
                self._set_suspended(proc, True)
        try:
            for line in proc.stdout:
                if on_line:
                    on_line(line.strip())
            proc.wait()
        except BaseException:
            # on_line raised (e.g. Cancelled): cancel() may have found no process to kill, so do it here.
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            raise
        finally:
            with self._lock:
                self._proc = None
        reader.join(timeout=2)
        self.check_cancel()
        if proc.returncode != 0:
            detail = [line.strip() for line in stderr_tail if line.strip()]
            raise ConversionError(detail[0] if detail else f"Código de saída {proc.returncode}")

    # Called from the GUI thread.

    def cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            if self._proc and self._proc.poll() is None:
                if self._suspended:
                    self._set_suspended(self._proc, False)
                self._proc.kill()

    def set_suspended(self, suspended: bool) -> None:
        with self._lock:
            self._suspended = suspended
            if self._proc and self._proc.poll() is None:
                self._set_suspended(self._proc, suspended)

    @staticmethod
    def _set_suspended(proc: subprocess.Popen, suspended: bool) -> None:
        try:
            p = psutil.Process(proc.pid)
            p.suspend() if suspended else p.resume()
        except psutil.Error:
            pass


class Engine:
    name = ""

    def supports(self, src_ext: str, target: str, target_cat: str) -> bool:
        raise NotImplementedError

    def convert(self, job: Job, ctx: JobContext) -> None:
        """Write the output(s) into `job.staging`; raise ConversionError or Cancelled."""
        raise NotImplementedError
