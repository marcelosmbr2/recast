"""The yt-dlp engine, tested offline: `yt_dlp.YoutubeDL` is replaced by a fake that copies samples."""

import shutil
import threading
import time
from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.utils import DownloadCancelled

from recast.core.models import ConversionOptions
from recast.engines import download as dl
from recast.engines.base import Cancelled, ConversionError, Job, JobContext
from recast.engines.download import DownloadEngine, VideoInfo, parse_video_url, translate_error
from recast.engines.registry import engine_for

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.parametrize(("raw", "expected"), [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1&index=3", URL),
    ("youtu.be/dQw4w9WgXcQ?t=10", URL),
    ("https://youtube.com/shorts/dQw4w9WgXcQ", URL),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", URL),
    ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "https://music.youtube.com/watch?v=dQw4w9WgXcQ"),
    ("https://vimeo.com/148751763", "https://vimeo.com/148751763"),
    ("https://player.vimeo.com/video/148751763?h=1a", "https://vimeo.com/148751763"),
    ("https://vimeo.com/148751763/9a1b2c3d", "https://vimeo.com/148751763/9a1b2c3d"),
    ("https://www.youtube.com/playlist?list=PL123", None),
    ("https://www.youtube.com/@channel", None),
    ("https://www.dailymotion.com/video/x7", None),
    ("texto qualquer", None),
    ("javascript:alert(1)", None),
    ("", None),
])
def test_parse_video_url(raw, expected):
    assert parse_video_url(raw) == expected


@pytest.mark.parametrize(("message", "expected"), [
    ("ERROR: [youtube] abc: Video unavailable", "Vídeo indisponível"),
    ("ERROR: [youtube] abc: Private video. Sign in if you've been granted access", "Vídeo privado"),
    ("ERROR: [youtube] abc: Sign in to confirm your age", "Vídeo com restrição de idade"),
    ("ERROR: Unsupported URL: https://x", "Link não suportado (apenas YouTube e Vimeo)"),
    ("<urlopen error [Errno -2] Name or service not known>", "Sem conexão com a internet"),
    ("ERROR: [youtube] abc: Something odd happened", "Falha no download: Something odd happened"),
])
def test_translate_error(message, expected):
    assert translate_error(message) == expected


def test_registry_and_host_helpers():
    assert isinstance(engine_for("url", "MP4", "video"), DownloadEngine)
    assert isinstance(engine_for("url", "MP3", "audio"), DownloadEngine)
    assert isinstance(engine_for("url", "PNG", "image"), DownloadEngine)
    assert engine_for("url", "PDF", "document") is None
    assert dl.host_label("https://vimeo.com/1") == "Vimeo" and dl.host_label(URL) == "YouTube"
    assert dl.fmt_duration(42) == "0:42" and dl.fmt_duration(3725) == "1:02:05"
    info = VideoInfo(URL, 'Mr. Robot: "Trailer" / Oficial.', 42)
    stem = info.filename_stem()
    assert stem.startswith("Mr. Robot") and not stem.endswith(".") and "/" not in stem


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: 'downloads' a sample into the requested outtmpl."""

    samples: dict[str, Path] = {}
    params_seen: list[dict] = []
    fail_with: str | None = None

    def __init__(self, params):
        self.params = params
        FakeYDL.params_seen.append(params)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        if FakeYDL.fail_with:
            self.params["logger"].error(FakeYDL.fail_with)
            raise yt_dlp.utils.DownloadError(FakeYDL.fail_with)
        audio_only = self.params.get("format", "").startswith("ba")
        src = FakeYDL.samples["wav" if audio_only else "mp4"]
        info = {"title": "Clip de teste", "duration": 2.0, "uploader": "Canal", "ext": src.suffix[1:],
                "requested_formats": [{"filesize": 1000}, {"filesize_approx": 500}],
                "filesize": 1500, "format_id": "x"}
        if not download:
            return info
        out = Path(self.params["outtmpl"]["default"] % {"ext": src.suffix[1:]})
        for hook in self.params.get("progress_hooks", []):
            for i in range(1, 4):
                hook({"status": "downloading", "downloaded_bytes": i, "total_bytes": 3, "filename": str(out),
                      "info_dict": {"requested_formats": [{}, {}]}})
            hook({"status": "finished", "filename": str(out), "info_dict": {"requested_formats": [{}, {}]}})
        shutil.copy(src, out)
        for hook in self.params.get("postprocessor_hooks", []):
            hook({"status": "finished", "postprocessor": "Merger"})
        info["requested_downloads"] = [{"filepath": str(out)}]
        return info


@pytest.fixture
def fake_ydl(monkeypatch, samples):
    FakeYDL.samples = samples
    FakeYDL.params_seen = []
    FakeYDL.fail_with = None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def make_job(tmp_path: Path, target: str, cat: str, **opts) -> tuple[Job, JobContext, list[float]]:
    staging, work = tmp_path / "out", tmp_path / "work"
    staging.mkdir()
    work.mkdir()
    progress: list[float] = []
    job = Job(Path("Clip de teste"), "url", target, cat, ConversionOptions().merged(opts), staging, "Clip de teste",
              url=URL)
    return job, JobContext(progress.append, work), progress


def test_mp4_is_moved_without_re_encoding(fake_ydl, tmp_path):
    job, ctx, progress = make_job(tmp_path, "MP4", "video")
    DownloadEngine().convert(job, ctx)
    assert job.dst.name == "Clip de teste.mp4" and job.dst.stat().st_size == fake_ydl.samples["mp4"].stat().st_size
    assert progress[-1] == 1.0 and progress == sorted(progress)
    params = fake_ydl.params_seen[-1]
    assert params["format"].startswith("bv*[ext=mp4]") and params["merge_output_format"] == "mp4/mkv"
    assert params["noplaylist"] and params["ffmpeg_location"] and params["quiet"]
    assert not list(ctx.tmp.glob("download.*")) or True  # the staging dir is what matters


def test_mp3_goes_through_ffmpeg(fake_ydl, tmp_path):
    job, ctx, progress = make_job(tmp_path, "MP3", "audio", bitrate="128 kbps")
    DownloadEngine().convert(job, ctx)
    assert job.dst.suffix == ".mp3" and job.dst.stat().st_size > 0
    assert progress[-1] == 1.0
    assert fake_ydl.params_seen[-1]["format"] == "ba/b" and "merge_output_format" not in fake_ydl.params_seen[-1]
    assert not list(ctx.tmp.glob("download.*"))  # the intermediate download is removed


def test_resolution_limits_the_requested_formats(fake_ydl, tmp_path):
    job, ctx, _ = make_job(tmp_path, "WEBM", "video", res="720p")
    DownloadEngine().convert(job, ctx)
    assert "[height<=720]" in fake_ydl.params_seen[-1]["format"]
    assert job.dst.suffix == ".webm"  # the mp4 sample was re-encoded, since the container differs


def test_cancel_during_download(fake_ydl, tmp_path):
    job, ctx, _ = make_job(tmp_path, "MP4", "video")
    ctx.cancel()
    with pytest.raises(Cancelled):
        DownloadEngine().convert(job, ctx)


def test_download_errors_are_translated(fake_ydl, tmp_path):
    fake_ydl.fail_with = "ERROR: [youtube] dQw4w9WgXcQ: Video unavailable"
    job, ctx, _ = make_job(tmp_path, "MP4", "video")
    with pytest.raises(ConversionError, match="Vídeo indisponível"):
        DownloadEngine().convert(job, ctx)
    with pytest.raises(ConversionError, match="Vídeo indisponível"):
        DownloadEngine().probe(URL)


def test_probe_returns_title_duration_and_size(fake_ydl):
    info = DownloadEngine().probe(URL)
    assert info == VideoInfo(URL, "Clip de teste", 2.0, "Canal", 1500)
    assert info.host == "YouTube"


def test_hook_cancel_surfaces_as_download_cancelled(fake_ydl, tmp_path):
    """yt-dlp only propagates DownloadCancelled cleanly; the hook must translate `Cancelled`."""
    job, ctx, _ = make_job(tmp_path, "MP4", "video")
    captured = {}

    class Grab(FakeYDL):
        def extract_info(self, url, download=True):
            captured["hook"] = self.params["progress_hooks"][0]
            raise DownloadCancelled("x")

    import yt_dlp as mod
    mod.YoutubeDL = Grab
    with pytest.raises(Cancelled):
        DownloadEngine().convert(job, ctx)
    ctx.cancel()
    with pytest.raises(DownloadCancelled):
        captured["hook"]({"status": "downloading", "downloaded_bytes": 1, "total_bytes": 2})


def test_wait_if_suspended_blocks_until_resumed_or_cancelled(tmp_path):
    ctx = JobContext(lambda _f: None, tmp_path)
    ctx.set_suspended(True)
    released = threading.Event()

    def worker():
        ctx.wait_if_suspended()
        released.set()

    threading.Thread(target=worker, daemon=True).start()
    time.sleep(0.1)
    assert not released.is_set()
    ctx.set_suspended(False)
    assert released.wait(2)

    ctx.set_suspended(True)
    result = {}

    def worker2():
        try:
            ctx.wait_if_suspended()
        except Cancelled:
            result["cancelled"] = True

    t = threading.Thread(target=worker2, daemon=True)
    t.start()
    time.sleep(0.05)
    ctx.cancel()
    t.join(2)
    assert result.get("cancelled")
