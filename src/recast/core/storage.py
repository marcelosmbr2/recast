"""Persistent app state: settings, history and user presets as JSON in the app data dir."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, Signal

from recast.core.models import HistoryEntry, Preset, Settings
from recast.core.presets import BUILTIN_PRESETS

log = logging.getLogger(__name__)

HISTORY_LIMIT = 500


def default_data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


def default_output_folder() -> str:
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return str(Path(docs or Path.home()) / "Recast")


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        log.exception("Could not read %s", path)
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class SettingsStore(QObject):
    changed = Signal()

    def __init__(self, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = data_dir / "settings.json"
        self.settings = Settings.from_dict(_read_json(self._path, {}))
        if not self.settings.folder:
            self.settings.folder = default_output_folder()

    def update(self, **values) -> None:
        for key, value in values.items():
            setattr(self.settings, key, value)
        _write_json(self._path, self.settings.to_dict())
        self.changed.emit()


class HistoryStore(QObject):
    changed = Signal()

    def __init__(self, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = data_dir / "history.json"
        self.entries = [HistoryEntry.from_dict(d) for d in _read_json(self._path, [])]

    def add(self, entries: list[HistoryEntry]) -> None:
        self.entries = (entries + self.entries)[:HISTORY_LIMIT]
        self._save()

    def clear(self) -> None:
        self.entries = []
        self._save()

    def _save(self) -> None:
        _write_json(self._path, [e.to_dict() for e in self.entries])
        self.changed.emit()


class PresetStore(QObject):
    changed = Signal()

    def __init__(self, data_dir: Path, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._path = data_dir / "presets.json"
        self.user_presets = [Preset.from_dict(d) for d in _read_json(self._path, [])]

    @property
    def presets(self) -> list[Preset]:
        return BUILTIN_PRESETS + self.user_presets

    def add(self, preset: Preset) -> None:
        self.user_presets.append(preset)
        self._save()

    def remove(self, preset_id: str) -> None:
        self.user_presets = [p for p in self.user_presets if p.id != preset_id]
        self._save()

    def _save(self) -> None:
        _write_json(self._path, [p.to_dict() for p in self.user_presets])
        self.changed.emit()
