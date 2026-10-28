"""Format catalog, compatibility rules and size estimates (ported from the mockup)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    label: str
    one: str
    plural: str
    tint: str


CATEGORIES: dict[str, Category] = {
    "image": Category("Imagens", "Imagem", "todas as imagens", "#8fb0f5"),
    "document": Category("Documentos", "Documento", "todos os documentos", "#c9ccd3"),
    "audio": Category("Áudio", "Áudio", "todos os arquivos de áudio", "#b89cf3"),
    "video": Category("Vídeo", "Vídeo", "todos os vídeos", "#f08a9c"),
    "archive": Category("Compactados", "Arquivo compactado", "todos os arquivos compactados", "#e2b46e"),
    "ebook": Category("E-books", "E-book", "todos os e-books", "#7fd3c4"),
}

FORMATS: dict[str, list[tuple[str, str]]] = {
    "image": [
        ("JPG", "Com perdas · universal"), ("PNG", "Sem perdas"), ("WEBP", "Leve · web"),
        ("AVIF", "Mínimo · moderno"), ("HEIC", "Fotos da Apple"), ("GIF", "Animado"),
        ("TIFF", "Impressão · sem perdas"), ("BMP", "Sem compressão"), ("ICO", "Ícone de app"),
    ],
    "document": [
        ("PDF", "Documento portátil"), ("DOCX", "Microsoft Word"), ("ODT", "OpenDocument"),
        ("RTF", "Texto formatado"), ("TXT", "Texto simples"), ("HTML", "Página web"), ("MD", "Markdown"),
    ],
    "audio": [
        ("MP3", "Com perdas · universal"), ("AAC", "Com perdas · eficiente"), ("M4A", "Áudio da Apple"),
        ("OPUS", "Voz · mínimo"), ("OGG", "Vorbis"), ("FLAC", "Sem perdas"), ("WAV", "Sem compressão"),
        ("AIFF", "Sem compressão · Apple"),
    ],
    "video": [
        ("MP4", "H.264 · HEVC"), ("MOV", "QuickTime"), ("WEBM", "VP9 · AV1"), ("MKV", "Matroska"),
        ("AVI", "Legado"), ("GIF", "Loop animado"),
    ],
    "archive": [
        ("ZIP", "Universal"), ("7Z", "Melhor compressão"), ("TAR.GZ", "Unix · compactado"),
        ("TAR", "Unix · sem compressão"),
    ],
    "ebook": [("EPUB", "Padrão aberto"), ("MOBI", "Kindle legado"), ("AZW3", "Kindle"), ("FB2", "FictionBook")],
}

COMPAT: dict[str, list[str]] = {
    "image": ["image", "document"],
    "document": ["document", "image", "ebook"],
    "audio": ["audio"],
    "video": ["video", "audio", "image"],
    "archive": ["archive"],
    "ebook": ["ebook", "document"],
}

SRC_CAT: dict[str, str] = {}
for _cat, _exts in [
    ("image", "jpg jpeg png webp avif heic heif gif tiff tif bmp ico svg dng cr2 nef"),
    ("document", "pdf doc docx odt rtf txt html htm md pptx ppt key xlsx xls csv pages"),
    ("audio", "mp3 wav flac aac ogg m4a opus aiff aif wma"),
    ("video", "mp4 mov mkv webm avi wmv m4v 3gp"),
    ("archive", "zip 7z rar tar gz tgz bz2"),
    ("ebook", "epub mobi azw3 fb2"),
]:
    for _ext in _exts.split():
        SRC_CAT[_ext] = _cat

DEFAULT_TARGET: dict[str, str] = {
    "heic": "JPG", "heif": "JPG", "png": "WEBP", "jpg": "WEBP", "jpeg": "WEBP", "webp": "PNG",
    "pdf": "DOCX", "mp3": "WAV", "mp4": "WEBM", "zip": "7Z", "epub": "MOBI", "mov": "MP4", "wav": "MP3",
}

CAT_DEFAULT: dict[str, str] = {
    "image": "PNG", "document": "PDF", "audio": "MP3", "video": "MP4", "archive": "ZIP", "ebook": "EPUB",
}

FACTOR: dict[str, float] = {
    "JPG": .55, "PNG": 1.3, "WEBP": .32, "AVIF": .24, "HEIC": .4, "GIF": .9, "TIFF": 2, "BMP": 3, "ICO": .05,
    "PDF": .42, "DOCX": .6, "ODT": .6, "RTF": .8, "TXT": .05, "HTML": .3, "MD": .04,
    "MP3": .12, "AAC": .1, "M4A": .11, "OPUS": .07, "OGG": .1, "FLAC": .55, "WAV": 4, "AIFF": 4,
    "MP4": .38, "MOV": 1.1, "WEBM": .3, "MKV": .9, "AVI": 1.2,
    "ZIP": 1.05, "7Z": .85, "TAR.GZ": .95, "TAR": 1.1,
    "EPUB": .6, "MOBI": .9, "AZW3": .9, "FB2": .5,
}

LOSSLESS = {"PNG", "TIFF", "BMP", "ICO", "GIF", "FLAC", "WAV", "AIFF"}

QUALITY_PRESETS: dict[str, int] = {"Menor": 55, "Equilibrado": 80, "Melhor": 95}

# Source extensions that are spellings of the same format as a target.
_ALIASES = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "aif": "aiff", "heif": "heic", "tgz": "tar.gz"}


def category_of(ext: str) -> str:
    return SRC_CAT.get(ext.lower(), "document")


def is_same_format(src_ext: str, target: str) -> bool:
    ext = src_ext.lower()
    return _ALIASES.get(ext, ext) == target.lower()


def target_category(src_cat: str, target: str) -> str:
    """First category compatible with `src_cat` that offers `target` (mockup's findCat)."""
    for cat in COMPAT[src_cat]:
        if any(ext == target for ext, _ in FORMATS[cat]):
            return cat
    return src_cat


def format_description(cat: str, target: str) -> str:
    return next((desc for ext, desc in FORMATS[cat] if ext == target), "")


def output_suffix(target: str) -> str:
    return "." + target.lower()


def quality_preset_name(quality: int) -> str:
    return next((name for name, q in QUALITY_PRESETS.items() if q == quality), "Personalizado")


def has_quality(target: str, target_cat: str) -> bool:
    return target_cat in ("image", "video", "audio") and target not in LOSSLESS


def estimate_factor(target: str, target_cat: str, opts) -> float:
    """Output/input size ratio estimate (mockup's factor())."""
    lossless = target in LOSSLESS
    k = FACTOR.get(target, .8)
    if target_cat in ("image", "video", "audio") and not lossless:
        k *= 0.45 + opts.quality / 145
    if target_cat == "video":
        k *= {"H.264": 1, "HEVC": .65, "AV1": .5, "VP9": .7}.get(opts.codec, 1)
        k *= {"Original": 1, "1080p": .7, "720p": .42}.get(opts.res, 1)
    if target_cat == "audio" and not lossless:
        k *= {"128 kbps": .4, "192 kbps": .6, "320 kbps": 1}.get(opts.bitrate, 1)
    if target_cat == "image":
        k *= {"Original": 1, "50%": .3, "2560 px": .7}.get(opts.resize, 1)
    if target_cat == "document" and opts.compress:
        k *= .7
    if target_cat == "archive":
        k *= {"Rápida": 1.08, "Normal": 1, "Máxima": .92}.get(opts.level, 1)
    return k


def fmt_size(b: float) -> str:
    if b >= 1e9:
        return f"{b / 1e9:.2f} GB"
    if b >= 1e6:
        return f"{b / 1e6:.1f} MB"
    if b >= 1e3:
        return f"{round(b / 1e3)} KB"
    return f"{round(b)} B"


def fmt_eta(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "Calculando…"
    if seconds < 60:
        return f"{max(1, round(seconds))}s restantes"
    return f"{int(seconds // 60)}m {round(seconds % 60)}s restantes"
