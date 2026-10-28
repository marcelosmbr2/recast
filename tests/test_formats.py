from datetime import datetime

import pytest

from recast.core.formats import estimate_factor, fmt_eta, fmt_size, is_same_format, target_category
from recast.core.models import ConversionOptions, HistoryEntry, Status
from recast.core.queue import make_item, split_name


@pytest.mark.parametrize(("name", "target", "cat"), [
    ("IMG_4021.HEIC", "JPG", "image"),
    ("logo.png", "WEBP", "image"),
    ("photo.jpeg", "WEBP", "image"),
    ("Contract.pdf", "DOCX", "document"),
    ("song.mp3", "WAV", "audio"),
    ("demo.mov", "MP4", "video"),
    ("backup.zip", "7Z", "archive"),
    ("book.epub", "FB2", "ebook"),  # MOBI (mockup default) has no engine
    ("scan.tiff", "PNG", "image"),
])
def test_default_target(tmp_path, name, target, cat):
    path = tmp_path / name
    path.write_bytes(b"x")
    item = make_item(path)
    assert (item.target, item.target_cat, item.status) == (target, cat, Status.READY)


def test_unsupported_source(tmp_path):
    path = tmp_path / "old.rar"
    path.write_bytes(b"x")
    assert make_item(path).status is Status.UNSUPPORTED


def test_split_name():
    assert split_name("backup.tar.gz") == ("backup", "gz")
    assert split_name("Q3 Board Review.pptx") == ("Q3 Board Review", "pptx")
    assert split_name("README") == ("README", "")


def test_same_format_aliases():
    assert is_same_format("jpeg", "JPG")
    assert is_same_format("tif", "TIFF")
    assert not is_same_format("png", "JPG")


def test_target_category_prefers_source_category():
    assert target_category("video", "GIF") == "video"
    assert target_category("image", "GIF") == "image"
    assert target_category("image", "PDF") == "document"


def test_estimate_matches_mockup():
    # Values computed with the mockup's factor() in JS.
    assert estimate_factor("WEBP", "image", ConversionOptions()) == pytest.approx(0.32 * (0.45 + 80 / 145))
    video = ConversionOptions(codec="HEVC", res="720p", quality=95)
    assert estimate_factor("MP4", "video", video) == pytest.approx(0.38 * (0.45 + 95 / 145) * 0.65 * 0.42)
    assert estimate_factor("FLAC", "audio", ConversionOptions()) == pytest.approx(0.55)
    assert estimate_factor("7Z", "archive", ConversionOptions(level="Máxima")) == pytest.approx(0.85 * 0.92)


def test_fmt_size_and_eta():
    assert fmt_size(1.24e9) == "1.24 GB"
    assert fmt_size(412.6e6) == "412.6 MB"
    assert fmt_size(240e3) == "240 KB"
    assert fmt_size(12) == "12 B"
    assert fmt_eta(12.4) == "12s restantes"
    assert fmt_eta(125) == "2m 5s restantes"


def test_history_when_label():
    now = datetime(2026, 10, 27, 12, 0)
    entry = lambda dt: HistoryEntry("a", "PNG", "WEBP", 1, 1, dt.timestamp())  # noqa: E731
    assert entry(datetime(2026, 10, 27, 11, 59, 30)).when_label(now) == "Agora mesmo"
    assert entry(datetime(2026, 10, 27, 10, 31)).when_label(now) == "Hoje, 10:31"
    assert entry(datetime(2026, 10, 26, 18, 3)).when_label(now) == "Ontem, 18:03"
    assert entry(datetime(2026, 10, 23, 16, 50)).when_label(now) == "23 out, 16:50"
