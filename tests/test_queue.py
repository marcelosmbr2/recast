import time
from pathlib import Path

import pytest
from PIL import Image

from recast.core import queue as queue_mod
from recast.core.models import Status
from recast.core.presets import BUILTIN_PRESETS
from recast.core.queue import ConversionQueue
from recast.core.storage import SettingsStore
from recast.engines.base import Engine


class SlowEngine(Engine):
    """Writes the output after ~`steps` × 20 ms, checking for cancellation on every step."""

    def __init__(self, steps: int = 25) -> None:
        self.steps = steps

    def supports(self, src_ext, target, target_cat):
        return True

    def convert(self, job, ctx):
        for i in range(self.steps):
            time.sleep(0.02)
            ctx.progress((i + 1) / self.steps)
        job.dst.write_bytes(b"converted")


@pytest.fixture
def store(tmp_path) -> SettingsStore:
    s = SettingsStore(tmp_path / "data")
    s.update(folder=str(tmp_path / "out"), parallel=2)
    return s


@pytest.fixture
def images(tmp_path) -> list[Path]:
    paths = []
    for i in range(3):
        p = tmp_path / "in" / f"img{i}.png"
        p.parent.mkdir(exist_ok=True)
        Image.new("RGB", (40, 30), (i * 80, 10, 10)).save(p)
        paths.append(p)
    return paths


def run_to_end(qtbot, q: ConversionQueue) -> int:
    with qtbot.waitSignal(q.queue_finished, timeout=20000) as blocker:
        q.start()
    return blocker.args[0]


def test_converts_and_moves_outputs(qtbot, store, images, tmp_path):
    q = ConversionQueue(store)
    added = q.add_paths(images)
    assert [i.target for i in added] == ["WEBP"] * 3
    converted = []
    q.item_converted.connect(converted.append)
    assert run_to_end(qtbot, q) == 3
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["img0.webp", "img1.webp", "img2.webp"]
    assert all(i.status is Status.DONE and i.out_size > 0 for i in q.items)
    assert len(converted) == 3 and not q.running


def test_respects_parallel_limit(qtbot, store, images, monkeypatch):
    monkeypatch.setattr(queue_mod, "engine_for", lambda *a: SlowEngine(5))
    store.update(parallel=1)
    q = ConversionQueue(store)
    q.add_paths(images)
    peak = []
    q.item_changed.connect(lambda _id: peak.append(len(q.active)))
    run_to_end(qtbot, q)
    assert max(peak) == 1


def test_pause_stops_dispatching(qtbot, store, images, monkeypatch):
    monkeypatch.setattr(queue_mod, "engine_for", lambda *a: SlowEngine(10))
    store.update(parallel=1)
    q = ConversionQueue(store)
    first, second, _ = q.add_paths(images)
    q.start()
    q.pause()
    qtbot.waitUntil(lambda: first.status is Status.DONE, timeout=5000)
    qtbot.wait(150)
    assert second.status is Status.READY and not q.running
    assert run_to_end(qtbot, q) == 3


def test_remove_while_converting_cancels(qtbot, store, images, monkeypatch, tmp_path):
    monkeypatch.setattr(queue_mod, "engine_for", lambda *a: SlowEngine(50))
    q = ConversionQueue(store)
    [item] = q.add_paths(images[:1])
    q.start()
    qtbot.waitUntil(lambda: item.progress > 0.1, timeout=5000)
    q.remove(item.id)
    q._pool.waitForDone(5000)
    qtbot.wait(50)
    assert q.items == [] and not q.running
    assert not (tmp_path / "out").exists() or not any((tmp_path / "out").iterdir())


@pytest.mark.parametrize(("policy", "expected", "status"), [
    ("Renomear", ["img0 (1).webp", "img0.webp"], Status.DONE),
    ("Substituir", ["img0.webp"], Status.DONE),
    ("Ignorar", ["img0.webp"], Status.SKIPPED),
])
def test_conflict_policy(qtbot, store, images, tmp_path, policy, expected, status):
    out = tmp_path / "out"
    out.mkdir()
    (out / "img0.webp").write_bytes(b"old")
    store.update(conflict=policy)
    q = ConversionQueue(store)
    [item] = q.add_paths(images[:1])
    with qtbot.waitSignal(q.running_changed, timeout=10000, check_params_cb=lambda r: not r):
        q.start()
    assert sorted(p.name for p in out.iterdir()) == expected
    assert item.status is status
    if policy == "Substituir":
        assert (out / "img0.webp").read_bytes() != b"old"


def test_targets_presets_and_apply_all(store, images, tmp_path):
    heic = tmp_path / "in" / "IMG_1.HEIC"
    heic.write_bytes(b"x")
    q = ConversionQueue(store)
    pngs = q.add_paths(images)
    [photo] = q.add_paths([heic])

    assert q.set_target_all("PNG", "image") == 1  # only the HEIC; PNG → PNG is skipped
    assert photo.target == "PNG"

    web = next(p for p in BUILTIN_PRESETS if p.id == "p2")
    assert q.apply_preset(web) == 3
    assert all(i.target == "WEBP" and i.opts.resize == "2560 px" for i in pngs)

    q.set_target(pngs[0].id, "JPG", "image")
    q.set_options(pngs[0].id, quality=55, preset="Menor")
    assert q.apply_to_category(pngs[0]) == 4
    assert all(i.target == "JPG" and i.opts.quality == 55 for i in q.items)


def test_word_pdf_presets(store, tmp_path):
    docx, pdf = tmp_path / "report.docx", tmp_path / "scan.pdf"
    for p in (docx, pdf):
        p.write_bytes(b"x")
    q = ConversionQueue(store)
    word, pdf_item = q.add_paths([docx, pdf])
    presets = {p.id: p for p in BUILTIN_PRESETS}
    assert q.apply_preset(presets["p6"]) == 1
    assert (word.target, pdf_item.target) == ("PDF", "DOCX")
    pdf_item.target = "TXT"
    assert q.apply_preset(presets["p7"]) == 1
    assert pdf_item.target == "DOCX"


def test_ogg_to_mp3_preset(store, tmp_path):
    ogg = tmp_path / "track.ogg"
    ogg.write_bytes(b"x")
    q = ConversionQueue(store)
    [item] = q.add_paths([ogg])
    assert q.apply_preset(next(p for p in BUILTIN_PRESETS if p.id == "p8")) == 1
    assert (item.target, item.target_cat, item.opts.bitrate) == ("MP3", "audio", "192 kbps")


def test_duplicate_pending_paths_are_ignored(store, images):
    q = ConversionQueue(store)
    q.add_paths(images)
    assert q.add_paths(images) == []
    assert len(q.items) == 3


def test_eta_recovers_after_pause_and_resume(store, images, monkeypatch):
    clock = iter(range(100, 200))
    monkeypatch.setattr(queue_mod.time, "monotonic", lambda: next(clock))
    q = ConversionQueue(store)
    [item] = q.add_paths(images[:1])
    item.status = Status.CONVERTING  # simulate a job in flight without starting a worker
    q.running = True
    q._on_progress(item.id, 0.1)
    q._on_progress(item.id, 0.2)
    assert item.eta is not None
    q.pause()
    q.start()
    q._on_progress(item.id, 0.3)
    q._on_progress(item.id, 0.4)
    assert item.eta is not None


def test_finish_reports_this_runs_saved_and_failed(qtbot, store, images, tmp_path):
    q = ConversionQueue(store)
    q.add_paths(images[:1])
    with qtbot.waitSignal(q.queue_finished, timeout=20000) as first:
        q.start()
    assert first.args == [1, 0]
    broken = tmp_path / "in" / "broken.png"
    broken.write_bytes(b"not an image")
    q.add_paths([images[1], broken])
    with qtbot.waitSignal(q.queue_finished, timeout=20000) as second:
        q.start()
    assert second.args == [1, 1]  # the file saved in the first run is not counted again
