from __future__ import annotations

from recast.engines.archive import ArchiveEngine
from recast.engines.base import Engine
from recast.engines.document import DocumentEngine
from recast.engines.image import ImageEngine
from recast.engines.media import MediaEngine

ENGINES: list[Engine] = [ImageEngine(), MediaEngine(), ArchiveEngine(), DocumentEngine()]


def engine_for(src_ext: str, target: str, target_cat: str) -> Engine | None:
    ext = src_ext.lower()
    return next((e for e in ENGINES if e.supports(ext, target, target_cat)), None)


def is_supported(src_ext: str, target: str, target_cat: str) -> bool:
    return engine_for(src_ext, target, target_cat) is not None
