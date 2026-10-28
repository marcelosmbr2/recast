from __future__ import annotations

import io
from pathlib import Path

import pillow_heif
from PIL import ExifTags, Image, ImageOps, ImageSequence, features
from PySide6.QtCore import QBuffer, QIODevice, QSize
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

from recast.core.models import ConversionOptions
from recast.engines.base import ConversionError, Engine, Job, JobContext

pillow_heif.register_heif_opener()

READABLE = set("jpg jpeg png webp avif heic heif gif tiff tif bmp ico svg".split())
PIL_FORMAT = {
    "JPG": "JPEG", "PNG": "PNG", "WEBP": "WEBP", "AVIF": "AVIF", "HEIC": "HEIF", "GIF": "GIF",
    "TIFF": "TIFF", "BMP": "BMP", "ICO": "ICO", "PDF": "PDF",
}
MULTI_FRAME = {"GIF", "TIFF", "WEBP", "PDF"}
NO_ALPHA = {"JPG", "PDF"}
HIGH_DEPTH = {"I;16", "I;16L", "I;16B", "I;16N", "I", "F"}
KEEP_HIGH_DEPTH = {"PNG": {"I;16", "I"}, "TIFF": {"I;16", "I", "F"}}


def can_write(target: str) -> bool:
    if target == "AVIF":
        return bool(features.check("avif"))
    return target in PIL_FORMAT


def open_image(path: Path) -> Image.Image:
    if path.suffix.lower() == ".svg":
        return _render_svg(path)
    try:
        return Image.open(path)
    except (OSError, ValueError) as e:
        raise ConversionError(f"Não foi possível abrir a imagem: {e}") from e


def _render_svg(path: Path) -> Image.Image:
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        raise ConversionError("SVG inválido")
    size = renderer.defaultSize()
    if size.isEmpty():
        size = QSize(1024, 1024)
    scale = max(1.0, 2048 / max(size.width(), size.height()))
    qimg = QImage(size * scale, QImage.Format.Format_ARGB32)
    qimg.fill(0)
    painter = QPainter(qimg)
    renderer.render(painter)
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    qimg.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data())))


def _to_8bit(img: Image.Image) -> Image.Image:
    """Scale 16/32-bit grayscale to 0..255; a plain convert() would clip it to white."""
    if img.mode == "F":
        lo, hi = img.getextrema()
        top = 1.0 if hi <= 1.0 else hi
    else:
        img = img.convert("I")
        lo, hi = img.getextrema()
        top = 65535 if hi <= 65535 else hi
    scale = 255 / top if top > 0 else 1
    return img.point(lambda v: v * scale).convert("L")


def prepare_frame(frame: Image.Image, target: str, opts: ConversionOptions) -> Image.Image:
    img = ImageOps.exif_transpose(frame)
    if img.mode in HIGH_DEPTH and img.mode not in KEEP_HIGH_DEPTH.get(target, set()):
        img = _to_8bit(img)
    if opts.resize == "50%":
        img = img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.Resampling.LANCZOS)
    elif opts.resize == "2560 px" and img.width > 2560:
        img = img.resize((2560, max(1, round(img.height * 2560 / img.width))), Image.Resampling.LANCZOS)
    if target == "PDF" and opts.compress and max(img.size) > 1754:  # A4 at 150 dpi
        img.thumbnail((1754, 1754), Image.Resampling.LANCZOS)
    if target == "ICO" and max(img.size) > 256:
        img.thumbnail((256, 256), Image.Resampling.LANCZOS)
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    if target in NO_ALPHA:
        if has_alpha:
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", rgba.size, "white")
            bg.paste(rgba, mask=rgba.getchannel("A"))
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
    elif img.mode not in ("RGB", "RGBA", "L", "LA", "P", *KEEP_HIGH_DEPTH.get(target, ())):
        img = img.convert("RGBA" if has_alpha else "RGB")
    if target in ("HEIC", "AVIF", "WEBP") and img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if has_alpha else "RGB")
    return img


def save_image(
    frames: list[Image.Image], dst: Path, target: str, opts: ConversionOptions,
    info: dict | None = None, durations: list[int] | None = None,
) -> None:
    """Save one or more frames as `target`; multi-frame only for formats that support it."""
    info = info or {}
    params: dict = {}
    q = opts.quality
    if target == "JPG":
        params.update(quality=q, optimize=True, progressive=True)
    elif target in ("WEBP", "AVIF", "HEIC"):
        params.update(quality=q)
    elif target == "PNG":
        params.update(optimize=True)
    elif target == "TIFF":
        params.update(compression="tiff_lzw")
    elif target == "PDF":
        params.update(resolution=150.0 if opts.compress else 300.0)
    if info.get("icc_profile") and target not in ("GIF", "BMP", "ICO"):
        params["icc_profile"] = info["icc_profile"]
    if not opts.strip and info.get("exif") and target in ("JPG", "WEBP", "PNG", "TIFF", "AVIF", "HEIC"):
        exif = Image.Exif()
        exif.load(info["exif"])
        exif.pop(ExifTags.Base.Orientation, None)  # prepare_frame already applied the rotation
        params["exif"] = exif.tobytes()
    if len(frames) > 1 and target in MULTI_FRAME:
        params.update(save_all=True, append_images=frames[1:])
        if target in ("GIF", "WEBP"):
            params.update(loop=0, duration=durations or 100)
    try:
        frames[0].save(dst, PIL_FORMAT[target], **params)
    except (OSError, ValueError, KeyError) as e:
        raise ConversionError(f"Falha ao salvar {target}: {e}") from e


class ImageEngine(Engine):
    name = "Pillow"

    def supports(self, src_ext: str, target: str, target_cat: str) -> bool:
        if src_ext not in READABLE:
            return False
        if target_cat == "document":
            return target == "PDF"
        return target_cat == "image" and can_write(target)

    def convert(self, job: Job, ctx: JobContext) -> None:
        img = open_image(job.src)
        ctx.progress(0.1)
        info = dict(img.info)
        want_all = job.target in MULTI_FRAME and getattr(img, "n_frames", 1) > 1
        count = img.n_frames if want_all else 1
        sources = ImageSequence.Iterator(img) if want_all else [img]
        frames, durations = [], []
        for i, frame in enumerate(sources):  # the iterator reuses one object; copy each frame
            durations.append(frame.info.get("duration", 100))
            frames.append(prepare_frame(frame.copy(), job.target, job.opts))
            ctx.progress(0.1 + 0.6 * (i + 1) / count)
        save_image(frames, job.dst, job.target, job.opts, info, durations)
        ctx.progress(1.0)
