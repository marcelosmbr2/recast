from __future__ import annotations

import itertools
import time
from dataclasses import asdict, dataclass, field, fields, replace
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path


class Status(str, Enum):
    READY = "ready"
    CONVERTING = "converting"
    DONE = "done"
    SKIPPED = "skipped"
    ERROR = "error"
    UNSUPPORTED = "unsupported"


@dataclass
class ConversionOptions:
    preset: str = "Equilibrado"
    quality: int = 80
    codec: str = "H.264"
    res: str = "Original"
    bitrate: str = "320 kbps"
    channels: str = "Estéreo"
    resize: str = "Original"
    strip: bool = True
    compress: bool = True
    level: str = "Normal"

    def merged(self, overrides: dict) -> ConversionOptions:
        known = {f.name for f in fields(self)}
        return replace(self, **{k: v for k, v in overrides.items() if k in known})


_ids = itertools.count(1)


@dataclass
class QueueItem:
    path: Path
    ext: str
    cat: str
    size: int
    target: str
    target_cat: str
    status: Status = Status.READY
    progress: float = 0.0  # 0..1
    out_size: int = 0
    out_path: Path | None = None
    error: str = ""
    eta: float | None = None
    opts: ConversionOptions = field(default_factory=ConversionOptions)
    id: str = field(default_factory=lambda: f"f{next(_ids)}")

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def is_pending(self) -> bool:
        return self.status in (Status.READY, Status.CONVERTING)

    @property
    def is_finished(self) -> bool:
        return self.status in (Status.DONE, Status.SKIPPED)

    def reset(self) -> None:
        self.status = Status.READY
        self.progress = 0.0
        self.out_size = 0
        self.out_path = None
        self.error = ""
        self.eta = None


@dataclass
class HistoryEntry:
    name: str
    src: str
    target: str
    in_size: int
    out_size: int
    timestamp: float
    out_path: str = ""

    def when_label(self, now: datetime | None = None) -> str:
        now = now or datetime.now()
        when = datetime.fromtimestamp(self.timestamp)
        if (now - when).total_seconds() < 60:
            return "Agora mesmo"
        if when.date() == now.date():
            return f"Hoje, {when:%H:%M}"
        if when.date() == (now - timedelta(days=1)).date():
            return f"Ontem, {when:%H:%M}"
        months = "jan fev mar abr mai jun jul ago set out nov dez".split()
        return f"{when.day} {months[when.month - 1]}, {when:%H:%M}"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> HistoryEntry:
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})

    @classmethod
    def from_item(cls, item: QueueItem) -> HistoryEntry:
        return cls(
            name=item.name, src=item.ext.upper(), target=item.target, in_size=item.size,
            out_size=item.out_size, timestamp=time.time(), out_path=str(item.out_path or ""),
        )


@dataclass
class Preset:
    id: str
    name: str
    sources: list[str]
    target: str
    target_cat: str
    quality: int
    detail: str
    opts: dict = field(default_factory=dict)
    builtin: bool = False

    @property
    def rule(self) -> str:
        return ", ".join(s.upper() for s in self.sources) + " → " + self.target

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Preset:
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


@dataclass
class Settings:
    folder: str = ""
    conflict: str = "Renomear"  # Renomear | Substituir | Ignorar
    parallel: int = 2
    hw: bool = True
    keep: bool = True
    notify: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Settings:
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})
