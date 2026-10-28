"""Audio/video conversion with the FFmpeg binary bundled by imageio-ffmpeg."""

from __future__ import annotations

import functools
import re
import subprocess

import imageio_ffmpeg
from PIL import Image

from recast.engines.base import _NO_WINDOW, ConversionError, Engine, Job, JobContext
from recast.engines.image import can_write, prepare_frame, save_image

AUDIO_SRC = set("mp3 wav flac aac ogg m4a opus aiff aif wma".split())
VIDEO_SRC = set("mp4 mov mkv webm avi wmv m4v 3gp".split())

AUDIO_CODEC = {
    "MP3": "libmp3lame", "AAC": "aac", "M4A": "aac", "OPUS": "libopus", "OGG": "libvorbis",
    "FLAC": "flac", "WAV": "pcm_s16le", "AIFF": "pcm_s16be",
}
LOSSLESS_AUDIO = {"FLAC", "WAV", "AIFF"}
VIDEO_CODEC = {"H.264": "libx264", "HEVC": "libx265", "AV1": "libaom-av1", "VP9": "libvpx-vp9"}
DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


@functools.cache
def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


@functools.cache
def encoders() -> frozenset[str]:
    out = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-encoders"], capture_output=True, text=True, creationflags=_NO_WINDOW,
    ).stdout
    return frozenset(line.split()[1] for line in out.splitlines() if len(line.split()) > 1 and line.startswith(" "))


def video_codecs(target: str) -> list[str]:
    """Codec choices offered in the inspector for a video target."""
    if target == "WEBM":
        names = ["VP9", "AV1"]
    elif target in ("MP4", "MKV"):
        names = ["H.264", "HEVC", "AV1"]
    elif target == "MOV":
        names = ["H.264", "HEVC"]  # FFmpeg's MOV muxer rejects AV1
    else:
        return []
    return [n for n in names if VIDEO_CODEC[n] in encoders()]


def probe_duration(path) -> float:
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", creationflags=_NO_WINDOW,
    )
    m = DURATION_RE.search(proc.stderr)
    if not m:
        if "Invalid data" in proc.stderr or "No such file" in proc.stderr:
            raise ConversionError("Arquivo de mídia inválido ou corrompido")
        return 0.0
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def crf(quality: int, codec: str) -> int:
    if codec in ("libaom-av1", "libvpx-vp9"):
        return round(55 - quality * 0.3)
    return round(40 - quality * 0.2)


class MediaEngine(Engine):
    name = "FFmpeg"

    def supports(self, src_ext: str, target: str, target_cat: str) -> bool:
        if src_ext in AUDIO_SRC:
            return target_cat == "audio"
        if src_ext in VIDEO_SRC:
            if target_cat == "image":
                return target == "GIF" or can_write(target)
            return target_cat in ("audio", "video")
        return False

    def convert(self, job: Job, ctx: JobContext) -> None:
        duration = probe_duration(job.src)
        ctx.progress(0.01)
        is_video = job.src_ext in VIDEO_SRC
        args = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
        if job.hw and is_video:
            args += ["-hwaccel", "auto"]
        if job.target_cat == "image" and job.target != "GIF":
            self._still(job, ctx, args, duration)
            return
        args += ["-i", job.src, "-progress", "pipe:1", "-nostats"]
        if job.target == "GIF":
            args += self._gif_args(job)
        elif job.target_cat == "audio":
            args += ["-vn"] + self._audio_args(job.target, job.opts)
        else:
            args += self._video_args(job)
        args.append(job.dst)

        def on_line(line: str) -> None:
            key, _, value = line.partition("=")
            if key == "out_time_us" and duration > 0 and value.isdigit():
                ctx.progress(min(0.99, int(value) / 1e6 / duration))

        ctx.run(args, on_line)
        ctx.progress(1.0)

    @staticmethod
    def _audio_args(target: str, opts) -> list[str]:
        codec = AUDIO_CODEC[target]
        if codec not in encoders():
            raise ConversionError(f"Codificador {codec} indisponível")
        channels = 1 if opts.channels == "Mono" else 2
        args = ["-c:a", codec, "-ac", str(channels)]
        if target not in LOSSLESS_AUDIO:
            kbps = int(opts.bitrate.split()[0])
            # Encoder limits: libopus 256 kbps per channel, libvorbis mono tops out below 240 kbps.
            kbps = min(kbps, {"OPUS": 256 * channels, "OGG": 192 if channels == 1 else 500}.get(target, kbps))
            args += ["-b:a", f"{kbps}k"]
        if target == "M4A":
            args += ["-f", "ipod"]
        elif target == "AAC":
            args += ["-f", "adts"]
        return args

    @staticmethod
    def _video_args(job: Job) -> list[str]:
        o, target = job.opts, job.target
        filters = []
        if o.res in ("1080p", "720p"):
            h = o.res[:-1]
            filters.append(f"scale=-2:'min(ih,{h})'")
        if target == "AVI":
            vargs = ["-c:v", "mpeg4", "-q:v", str(max(2, round(31 - o.quality * 0.29)))]
            aargs = ["-c:a", "libmp3lame", "-b:a", "192k"]
        else:
            name = o.codec if o.codec in video_codecs(target) else (video_codecs(target) or ["H.264"])[0]
            codec = VIDEO_CODEC[name]
            vargs = ["-c:v", codec, "-crf", str(crf(o.quality, codec)), "-pix_fmt", "yuv420p"]
            if codec == "libx264":
                vargs += ["-preset", "medium"]
            elif codec == "libx265":
                vargs += ["-preset", "medium", "-tag:v", "hvc1"]
            elif codec == "libaom-av1":
                vargs += ["-b:v", "0", "-cpu-used", "6", "-row-mt", "1"]
            elif codec == "libvpx-vp9":
                vargs += ["-b:v", "0", "-deadline", "good", "-cpu-used", "4", "-row-mt", "1"]
            aargs = ["-c:a", "libopus", "-b:a", "128k"] if target == "WEBM" else ["-c:a", "aac", "-b:a", "192k"]
            if target in ("MP4", "MOV"):
                vargs += ["-movflags", "+faststart"]
        if filters:
            vargs += ["-vf", ",".join(filters)]
        return vargs + aargs

    @staticmethod
    def _gif_args(job: Job) -> list[str]:
        width = {"1080p": 720, "720p": 480}.get(job.opts.res, 480)
        graph = f"fps=12,scale='min(iw,{width})':-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse"
        return ["-an", "-filter_complex", graph, "-loop", "0"]

    def _still(self, job: Job, ctx: JobContext, args: list[str], duration: float) -> None:
        frame = ctx.tmp / "frame.png"
        at = min(1.0, duration * 0.1) if duration else 0
        ctx.run(args + ["-ss", f"{at:.2f}", "-i", job.src, "-frames:v", "1", frame])
        ctx.progress(0.7)
        with Image.open(frame) as img:
            img.load()
            save_image([prepare_frame(img, job.target, job.opts)], job.dst, job.target, job.opts)
        ctx.progress(1.0)
