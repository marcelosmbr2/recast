"""Download of YouTube/Vimeo videos with yt-dlp, then conversion with the FFmpeg engine.

This is the only module in Recast that touches the network. yt-dlp runs in-process; the
JavaScript challenges YouTube requires are solved with the bundled Deno runtime (yt-dlp-ejs).
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

from recast.engines.base import Cancelled, ConversionError, Engine, Job, JobContext
from recast.engines.media import MediaEngine, ffmpeg_exe

log = logging.getLogger(__name__)

_YT_ID = re.compile(r"^[A-Za-z0-9_-]{6,}$")
_YT_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com"}
_VIMEO_HOSTS = {"vimeo.com", "player.vimeo.com"}
SUPPORTED_SITES = ("YouTube", "Vimeo")

# yt-dlp error fragments (English) -> message shown to the user.
_ERRORS: list[tuple[str, str]] = [
    ("Private video", "Vídeo privado"),
    ("Sign in to confirm your age", "Vídeo com restrição de idade"),
    ("age-restricted", "Vídeo com restrição de idade"),
    ("Sign in to confirm you", "O YouTube pediu verificação de login; tente novamente mais tarde"),
    ("members-only", "Vídeo exclusivo para membros do canal"),
    ("Video unavailable", "Vídeo indisponível"),
    ("This video is not available", "Vídeo indisponível"),
    ("has been removed", "Vídeo removido"),
    ("not available in your country", "Vídeo indisponível na sua região"),
    ("is a live", "Transmissões ao vivo não são suportadas"),
    ("Premieres in", "O vídeo ainda não estreou"),
    ("DRM", "Vídeo protegido (DRM)"),
    ("Unsupported URL", "Link não suportado (apenas YouTube e Vimeo)"),
    ("Requested format is not available", "Nenhum formato compatível disponível para este vídeo"),
    ("getaddrinfo", "Sem conexão com a internet"),
    ("Unable to connect to proxy", "Sem conexão com a internet (proxy recusou a conexão)"),
    ("Network is unreachable", "Sem conexão com a internet"),
    ("Name or service not known", "Sem conexão com a internet"),
    ("Temporary failure in name resolution", "Sem conexão com a internet"),
    ("Unable to download webpage", "Sem conexão com a internet ou site inacessível"),
    ("Unable to download", "Falha ao baixar; verifique a conexão"),
    ("timed out", "Tempo esgotado ao conectar"),
    ("HTTP Error 403", "Acesso negado pelo site (HTTP 403)"),
    ("HTTP Error 404", "Vídeo não encontrado (HTTP 404)"),
    ("HTTP Error 429", "Muitas requisições; aguarde alguns minutos"),
]


@dataclass(frozen=True)
class VideoInfo:
    url: str
    title: str
    duration: float = 0.0
    uploader: str = ""
    filesize: int = 0

    @property
    def host(self) -> str:
        return host_label(self.url)

    def filename_stem(self) -> str:
        from yt_dlp.utils import sanitize_filename

        stem = sanitize_filename(self.title or "video").strip(" .")
        return stem[:120].rstrip(" .") or "video"


def parse_video_url(value: str) -> str | None:
    """Canonical URL for a single YouTube/Vimeo video, or None when the text is not one.

    Playlist and channel links are rejected: Recast downloads one video per queue item.
    """
    text = (value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        u = urlparse(text)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.netloc:
        return None
    host = u.hostname or ""
    host = host[4:] if host.startswith("www.") else host
    path = u.path.rstrip("/")
    query = parse_qs(u.query)

    if host == "youtu.be":
        vid = path.lstrip("/")
        return f"https://www.youtube.com/watch?v={vid}" if _YT_ID.match(vid) else None
    if host in _YT_HOSTS:
        if path == "/watch":
            vid = (query.get("v") or [""])[0]
            base = "https://music.youtube.com" if host == "music.youtube.com" else "https://www.youtube.com"
            return f"{base}/watch?v={vid}" if _YT_ID.match(vid) else None
        m = re.fullmatch(r"/(?:shorts|live|embed|v)/([A-Za-z0-9_-]{6,})", path)
        if m:
            return f"https://www.youtube.com/watch?v={m.group(1)}"
        return None
    if host in _VIMEO_HOSTS:
        m = re.fullmatch(r"/(?:video/)?(\d+)(?:/([0-9a-f]+))?", path)
        if m:
            vid, hash_ = m.groups()
            url = f"https://vimeo.com/{vid}"
            return url + (f"/{hash_}" if hash_ else "")
        m = re.fullmatch(r"/(?:channels|groups)/[^/]+/(\d+)", path)
        if m:
            return f"https://vimeo.com/{m.group(1)}"
        return None
    return None


def host_label(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return "Vimeo" if "vimeo" in host else "YouTube"


def fmt_duration(seconds: float) -> str:
    total = max(0, round(seconds))
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def deno_exe() -> str | None:
    """The bundled Deno runtime (frozen app: `_internal/tools/`), the venv's, or one on PATH."""
    name = "deno.exe" if sys.platform == "win32" else "deno"
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "tools" / name
        if bundled.is_file():
            return str(bundled)
    try:
        import deno

        return deno.find_deno_bin()
    except (ImportError, FileNotFoundError):
        pass
    return shutil.which("deno")


class _Logger:
    """Routes yt-dlp output to `logging` (the windowed exe has no stdout) and keeps the last error."""

    def __init__(self) -> None:
        self.last_error = ""

    def debug(self, msg: str) -> None:
        if not msg.startswith("[debug] "):
            log.debug("%s", msg)

    def info(self, msg: str) -> None:
        log.debug("%s", msg)

    def warning(self, msg: str) -> None:
        log.warning("%s", msg)

    def error(self, msg: str) -> None:
        self.last_error = msg
        log.error("%s", msg)


def translate_error(message: str) -> str:
    text = str(message)
    for fragment, pt in _ERRORS:
        if fragment.lower() in text.lower():
            return pt
    first = re.sub(r"^(ERROR:\s*)?(\[[^\]]+\]\s*)?([A-Za-z0-9_-]+:\s*)?", "", text.strip().splitlines()[0] if text.strip() else "")
    return f"Falha no download: {first}" if first else "Falha no download"


def base_options(cache_dir: Path | None = None) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "overwrites": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "ffmpeg_location": ffmpeg_exe(),
        "cachedir": str(cache_dir) if cache_dir else False,
    }
    deno = deno_exe()
    if deno:
        opts["js_runtimes"] = {"deno": {"path": deno}}
    else:
        log.warning("Deno not found; YouTube support will be limited")
    return opts


def _cache_dir() -> Path | None:
    try:
        from recast.core.storage import default_data_dir

        d = default_data_dir() / "yt-dlp"
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:  # no QApplication (e.g. plain scripts): yt-dlp then runs without a cache
        return None


def _format_spec(target: str, target_cat: str, res: str) -> tuple[str, str | None]:
    """(yt-dlp format selector, merge_output_format) for the wanted output."""
    h = {"1080p": "[height<=1080]", "720p": "[height<=720]"}.get(res, "")
    if target_cat == "audio":
        return "ba/b", None
    if target == "MP4":
        return f"bv*[ext=mp4]{h}+ba[ext=m4a]/b[ext=mp4]{h}/bv*{h}+ba/b", "mp4/mkv"
    if target == "WEBM":
        return f"bv*[ext=webm]{h}+ba[ext=webm]/bv*{h}+ba/b", "webm/mkv"
    return f"bv*{h}+ba/b", "mkv"


class _Scaled:
    """A JobContext view that maps progress 0..1 onto [lo, hi] for the conversion stage."""

    def __init__(self, ctx: JobContext, lo: float, hi: float) -> None:
        self._ctx, self._lo, self._hi = ctx, lo, hi
        self.tmp = ctx.tmp

    def progress(self, fraction: float) -> None:
        self._ctx.progress(self._lo + (self._hi - self._lo) * max(0.0, min(1.0, fraction)))

    def check_cancel(self) -> None:
        self._ctx.check_cancel()

    def wait_if_suspended(self) -> None:
        self._ctx.wait_if_suspended()

    def run(self, args, on_line=None) -> None:
        self._ctx.run(args, on_line)


class DownloadEngine(Engine):
    name = "yt-dlp"

    def __init__(self) -> None:
        self._media = MediaEngine()

    def supports(self, src_ext: str, target: str, target_cat: str) -> bool:
        return src_ext == "url" and self._media.supports("mp4", target, target_cat)

    # Metadata (run off the GUI thread by the dialog)

    def probe(self, url: str) -> VideoInfo:
        import yt_dlp

        logger = _Logger()
        opts = {**base_options(_cache_dir()), "logger": logger, "skip_download": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:  # yt_dlp.utils.DownloadError and friends
            raise ConversionError(translate_error(logger.last_error or str(e))) from e
        if not info:
            raise ConversionError("Vídeo indisponível")
        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise ConversionError("Links de playlist não são suportados; use o link de um vídeo")
            info = entries[0]
        if info.get("is_live"):
            raise ConversionError("Transmissões ao vivo não são suportadas")
        formats = info.get("requested_formats") or ([info] if info.get("url") or info.get("format_id") else [])
        size = sum(int(f.get("filesize") or f.get("filesize_approx") or 0) for f in formats)
        return VideoInfo(
            url=url, title=str(info.get("title") or "video"), duration=float(info.get("duration") or 0),
            uploader=str(info.get("uploader") or info.get("channel") or ""), filesize=size,
        )

    # Conversion

    def convert(self, job: Job, ctx: JobContext) -> None:
        if not job.url:
            raise ConversionError("Link do vídeo ausente")
        # MP4/WEBM/MKV usually come straight from the site (no re-encode); everything else goes
        # through the FFmpeg engine afterwards, so leave it a share of the progress bar.
        direct = job.target_cat == "video" and job.target in ("MP4", "WEBM", "MKV")
        share = 0.9 if direct else 0.6
        downloaded = self._download(job, ctx, share)
        ext = downloaded.suffix.lstrip(".").lower()
        if ext == job.target.lower() and job.target_cat == "video":
            os.replace(downloaded, job.dst)
            ctx.progress(1.0)
            return
        inner = Job(
            src=downloaded, src_ext=ext if ext in _KNOWN_SRC else "mkv", target=job.target,
            target_cat=job.target_cat, opts=job.opts, staging=job.staging, stem=job.stem, hw=job.hw,
        )
        self._media.convert(inner, _Scaled(ctx, share, 1.0))  # type: ignore[arg-type]
        downloaded.unlink(missing_ok=True)

    def _download(self, job: Job, ctx: JobContext, share: float) -> Path:
        import yt_dlp
        from yt_dlp.utils import DownloadCancelled

        logger = _Logger()
        fmt, merge = _format_spec(job.target, job.target_cat, job.opts.res)
        state = {"done": 0, "current": 0.0}

        def report(d: dict) -> None:
            expected = len((d.get("info_dict") or {}).get("requested_formats") or []) or 1
            status = d.get("status")
            if status == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                state["current"] = (d.get("downloaded_bytes") or 0) / total if total else 0.0
            elif status == "finished":
                state["done"] += 1
                state["current"] = 0.0
            frac = min(0.99, (state["done"] + state["current"]) / expected)
            ctx.progress(frac * share)
            ctx.wait_if_suspended()

        def hook(d: dict) -> None:
            try:
                report(d)
            except Cancelled as e:  # yt-dlp only lets DownloadCancelled through cleanly
                raise DownloadCancelled("cancelado") from e

        def pp_hook(d: dict) -> None:
            try:
                ctx.check_cancel()
            except Cancelled as e:
                raise DownloadCancelled("cancelado") from e

        opts = {
            **base_options(_cache_dir()),
            "logger": logger,
            "format": fmt,
            "outtmpl": {"default": str(ctx.tmp / "download.%(ext)s")},
            "progress_hooks": [hook],
            "postprocessor_hooks": [pp_hook],
        }
        if merge:
            opts["merge_output_format"] = merge
        ctx.progress(0.0)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(job.url, download=True)
        except DownloadCancelled as e:
            raise Cancelled from e
        except Cancelled:
            raise
        except Exception as e:
            raise ConversionError(translate_error(logger.last_error or str(e))) from e
        ctx.check_cancel()
        if info and info.get("_type") == "playlist":
            info = next((e for e in (info.get("entries") or []) if e), None)
        path = _downloaded_path(info, ctx.tmp)
        if path is None:
            raise ConversionError(translate_error(logger.last_error) if logger.last_error else "Nenhum arquivo foi baixado")
        return path


_KNOWN_SRC = {"mp4", "mov", "mkv", "webm", "avi", "wmv", "m4v", "3gp", "mp3", "wav", "flac", "aac", "ogg", "m4a",
              "opus", "aiff", "aif", "wma"}


def _downloaded_path(info: dict | None, tmp: Path) -> Path | None:
    for d in (info or {}).get("requested_downloads") or []:
        p = d.get("filepath") or d.get("filename")
        if p and Path(p).is_file():
            return Path(p)
    candidates = sorted((p for p in tmp.glob("download.*") if p.is_file() and not p.suffix.endswith(".part")),
                        key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0] if candidates else None
