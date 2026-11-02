"""Structured PDF import: text lines, paragraphs, headings, lists and images via pdfium.

pdfium exposes characters with boxes, font sizes and names, plus image objects. This module turns
that into blocks (paragraphs, headings, lists, images) that the document engine renders as HTML for
pandoc / QTextDocument, or as plain text. Tables, columns and page breaks are not reconstructed.
"""

from __future__ import annotations

import ctypes
import html
import re
import statistics
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw

from recast.engines.base import ConversionError, JobContext

# pdfium is not thread-safe; serialize every call into it.
PDFIUM_LOCK = threading.Lock()

_BULLETS = "•◦▪▫‣●○■□–—-*·"
_LIST_RE = re.compile(rf"^(?:[{re.escape(_BULLETS)}]|\(?\d{{1,3}}[.)]|[a-zA-Z][.)])\s+(?=\S)")
_ORDERED_RE = re.compile(r"^\(?(?:\d{1,3}|[a-zA-Z])[.)]\s")
_PAGE_NUMBER_RE = re.compile(r"^(?:p(?:ág(?:ina)?|age)?\.?\s*)?[-–—]?\s*\d{1,4}\s*(?:[/de]+\s*\d{1,4})?\s*[-–—]?$", re.I)
_FORCE_BOLD = 1 << 18  # PDF font descriptor flag 19
_MARGIN = 0.10  # share of the page height where repeated lines count as headers/footers
_NUMBER_MARGIN = 0.13  # wider zone for bare page numbers (Qt prints them ~3.5 cm from the edge)
_MAX_IMAGES_PER_PAGE = 40
_MIN_IMAGE_PX = 24


@dataclass
class Line:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float
    size: float  # rendered font size (full glyph box height), in PDF points
    bold: bool
    bullet: bool = False  # a drawn (non-text) bullet sits to the left of the line

    @property
    def height(self) -> float:
        return self.top - self.bottom


@dataclass
class Block:
    kind: str  # "p", "h1", "h2", "h3", "ul", "ol", "img"
    text: str = ""
    items: list[str] = field(default_factory=list)
    src: str = ""  # img: path relative to the media dir's parent
    bold: bool = False
    top: float = 0.0
    bottom: float = 0.0
    lines: int = 0


def open_pdf(path: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as e:
        raise ConversionError(f"PDF inválido: {e}") from e


def pdf_to_blocks(
    path: Path, ctx: JobContext, media_dir: Path | None, span: tuple[float, float] = (0.0, 0.4),
) -> list[list[Block]]:
    """Extract every page as a list of blocks. Images are written to `media_dir` when given."""
    lo, hi = span
    pages: list[tuple[list[Line], float]] = []
    images: list[list[tuple[tuple, int, Path]]] = []
    with PDFIUM_LOCK:
        pdf = open_pdf(path)
        try:
            count = len(pdf)
            if count == 0:
                raise ConversionError("PDF sem páginas")
            for i in range(count):
                page = pdf[i]
                try:
                    pages.append((_page_lines(page), page.get_height()))
                    images.append(_page_images(page, i, media_dir) if media_dir else [])
                finally:
                    page.close()
                ctx.progress(lo + (hi - lo) * (i + 1) / count)
        finally:
            pdf.close()
    _drop_running_lines(pages)
    kept_images = _drop_repeated_images(images)
    body = _body_size([line for lines, _ in pages for line in lines])
    result = []
    for (lines, _), page_images in zip(pages, kept_images, strict=True):
        blocks = _blocks(lines, body)
        for bounds, _, file in page_images:
            _insert_image(blocks, bounds, file, media_dir)
        result.append(blocks)
    if not any(result):
        raise ConversionError("O PDF não tem texto selecionável (parece digitalizado). OCR não é suportado.")
    return result


def blocks_to_html(pages: list[list[Block]]) -> str:
    parts = []
    for blocks in pages:
        for b in blocks:
            if b.kind == "img":
                parts.append(f'<p><img src="{html.escape(b.src)}"></p>')
            elif b.kind in ("ul", "ol"):
                items = "".join(f"<li>{html.escape(item)}</li>" for item in b.items)
                parts.append(f"<{b.kind}>{items}</{b.kind}>")
            else:
                text = html.escape(b.text)
                if b.kind == "p" and b.bold:
                    text = f"<strong>{text}</strong>"
                parts.append(f"<{b.kind}>{text}</{b.kind}>")
    body = "\n".join(parts)
    return f"<!doctype html><html><head><meta charset='utf-8'></head><body>\n{body}\n</body></html>"


def blocks_to_text(pages: list[list[Block]]) -> str:
    parts = []
    for blocks in pages:
        for b in blocks:
            if b.kind == "img":
                continue
            if b.kind == "ul":
                parts.append("\n".join("- " + item for item in b.items))
            elif b.kind == "ol":
                parts.append("\n".join(f"{i}. {item}" for i, item in enumerate(b.items, 1)))
            else:
                parts.append(b.text)
    return "\n\n".join(parts) + "\n"


# --- pdfium access -------------------------------------------------------------------------------


def _page_lines(page: pdfium.PdfPage) -> list[Line]:
    """Characters in pdfium's reading order, grouped into lines."""
    bbox = page.get_bbox()  # text drawn outside it is clipped away (Qt repeats page-edge lines there)
    textpage = page.get_textpage()
    try:
        lines: list[Line] = []
        chars: list[str] = []
        boxes: list[tuple[float, float, float, float]] = []  # tight glyph boxes
        extents: list[tuple[float, float]] = []  # loose (font-height) bottom/top
        bold_flags: list[bool] = []

        def flush() -> None:
            text = " ".join("".join(chars).split())
            if text and boxes:
                lines.append(Line(
                    text=text,
                    x0=min(b[0] for b in boxes), x1=max(b[2] for b in boxes),
                    top=max(e[1] for e in extents), bottom=min(e[0] for e in extents),
                    size=statistics.median(e[1] - e[0] for e in extents),
                    bold=sum(bold_flags) >= 0.9 * len(bold_flags),
                ))
            chars.clear()
            boxes.clear()
            extents.clear()
            bold_flags.clear()

        for i in range(textpage.count_chars()):
            code = pdfium_raw.FPDFText_GetUnicode(textpage, i)
            if code == 2 and pdfium_raw.FPDFText_IsHyphen(textpage, i):
                code = 0x2D  # pdfium marks a line-end hyphen this way; _join removes it again
            ch = chr(code) if 0 < code < 0x110000 else ""
            if ch in ("\r", "\n"):
                flush()
                continue
            if not ch or ch.isspace():
                chars.append(" ")
                continue
            left, bottom, right, top = textpage.get_charbox(i)
            if top - bottom <= 0 and right - left <= 0:
                continue
            if not _inside(bbox, (left, bottom, right, top)):
                continue
            _, loose_bottom, _, loose_top = textpage.get_charbox(i, loose=True)
            if loose_top - loose_bottom <= 0:
                loose_bottom, loose_top = bottom, top
            if boxes and not _same_line(boxes[-1], (left, bottom, right, top)):
                flush()
            elif boxes and chars and chars[-1] != " " and left - boxes[-1][2] > 0.25 * (loose_top - loose_bottom):
                chars.append(" ")  # visible gap without a generated space
            chars.append(ch)
            boxes.append((left, bottom, right, top))
            extents.append((loose_bottom, loose_top))
            bold_flags.append(_is_bold(textpage, i))
        flush()
    finally:
        textpage.close()
    _mark_drawn_bullets(page, lines)
    return lines


def _inside(bbox: tuple[float, float, float, float], box: tuple[float, float, float, float]) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3]


def _same_line(prev: tuple[float, float, float, float], box: tuple[float, float, float, float]) -> bool:
    overlap = min(prev[3], box[3]) - max(prev[1], box[1])
    height = min(prev[3] - prev[1], box[3] - box[1])
    return overlap > 0.3 * height


def _is_bold(textpage: pdfium.PdfTextPage, index: int) -> bool:
    buf = ctypes.create_string_buffer(128)
    flags = ctypes.c_int(0)
    n = pdfium_raw.FPDFText_GetFontInfo(textpage, index, buf, len(buf), ctypes.byref(flags))
    name = buf.value.decode("latin-1", errors="replace").lower() if n else ""
    if flags.value & _FORCE_BOLD or any(k in name for k in ("bold", "black", "heavy", "semibold", "extrabold")):
        return True
    weight = pdfium_raw.FPDFText_GetFontWeight(textpage, index)
    return weight >= 600


def _mark_drawn_bullets(page: pdfium.PdfPage, lines: list[Line]) -> None:
    """Bullets drawn as small paths (Qt, Word) carry no character; detect them by position."""
    if not lines:
        return
    dots = []
    for obj in page.get_objects(max_depth=1):
        if obj.type != pdfium_raw.FPDF_PAGEOBJ_PATH:
            continue
        left, bottom, right, top = obj.get_bounds()
        w, h = right - left, top - bottom
        if 0.5 < w < 12 and 0.5 < h < 12 and abs(w - h) < 6:
            dots.append((left, bottom, right, top))
    if not dots:
        return
    for line in lines:
        for left, bottom, right, top in dots:
            cy = (top + bottom) / 2
            if line.bottom - 1 <= cy <= line.top + 1 and line.x0 - 3 * line.size <= right <= line.x0 + 1:
                line.bullet = True
                break


def _page_images(page: pdfium.PdfPage, index: int, media_dir: Path) -> list[tuple[tuple, int, Path]]:
    found = []
    n = 0
    for obj in page.get_objects(max_depth=2):
        if not isinstance(obj, pdfium.PdfImage):
            continue
        left, bottom, right, top = obj.get_bounds()
        if right - left < 8 or top - bottom < 8:
            continue
        try:
            w, h = obj.get_px_size()
            if min(w, h) < _MIN_IMAGE_PX:
                continue
            pil = obj.get_bitmap(render=True).to_pil()
        except pdfium.PdfiumError:
            continue
        n += 1
        if n > _MAX_IMAGES_PER_PAGE:
            break
        media_dir.mkdir(parents=True, exist_ok=True)
        file = media_dir / f"p{index + 1}-{n}.png"
        pil.save(file, "PNG")
        key = (round(left), round(bottom), round(right), round(top), w, h)
        found.append((key, w * h, file))
    return found


# --- layout heuristics -----------------------------------------------------------------------------


def _drop_running_lines(pages: list[tuple[list[Line], float]]) -> None:
    """Remove page numbers and headers/footers repeated on at least half of the pages."""
    seen: Counter[str] = Counter()
    if len(pages) >= 3:
        for lines, height in pages:
            seen.update({_running_key(ln) for ln in lines if _in_margin(ln, height, _MARGIN)})
    threshold = len(pages) / 2

    def running(ln: Line, height: float) -> bool:
        if _in_margin(ln, height, _NUMBER_MARGIN) and _PAGE_NUMBER_RE.match(ln.text):
            return True
        return len(pages) >= 3 and _in_margin(ln, height, _MARGIN) and seen[_running_key(ln)] >= threshold

    for lines, height in pages:
        lines[:] = [ln for ln in lines if not running(ln, height)]


def _in_margin(line: Line, page_height: float, margin: float) -> bool:
    center = (line.top + line.bottom) / 2
    return len(line.text) <= 100 and (center > page_height * (1 - margin) or center < page_height * margin)


def _running_key(line: Line) -> str:
    return re.sub(r"\d+", "#", line.text).strip().lower()


def _drop_repeated_images(images: list[list[tuple[tuple, int, Path]]]) -> list[list[tuple[tuple, int, Path]]]:
    """Logos repeated at the same place on most pages are decoration, not content."""
    if len(images) < 3:
        return images
    seen: Counter[tuple] = Counter()
    for page in images:
        seen.update({key for key, _, _ in page})
    threshold = len(images) / 2
    kept = []
    for page in images:
        kept.append([(key, area, file) for key, area, file in page if seen[key] < threshold])
    return kept


def _body_size(lines: list[Line]) -> float:
    if not lines:
        return 0.0
    weighted: Counter[float] = Counter()
    for ln in lines:
        weighted[round(ln.size, 1)] += len(ln.text)
    total = sum(weighted.values())
    acc = 0
    for size in sorted(weighted):
        acc += weighted[size]
        if acc * 2 >= total:
            return size
    return max(weighted)


def _line_pitch(lines: list[Line]) -> float:
    """Typical top-to-top distance between consecutive lines on the page."""
    steps = []
    for prev, line in zip(lines, lines[1:]):
        d = prev.top - line.top
        if 0 < d < 3 * max(prev.height, line.height) and abs(prev.size - line.size) < 0.15 * prev.size:
            steps.append(d)
    if steps:
        return statistics.median(steps)
    return 1.2 * statistics.median(ln.height for ln in lines) if lines else 1.0


def _blocks(lines: list[Line], body: float) -> list[Block]:
    pitch = _line_pitch(lines)
    groups: list[list[Line]] = []
    for line in lines:
        if groups and not _starts_block(groups[-1][-1], line, pitch):
            groups[-1].append(line)
        else:
            groups.append([line])
    blocks: list[Block] = []
    for group in groups:
        block = _make_block(group, body)
        if block.kind in ("ul", "ol") and blocks and blocks[-1].kind == block.kind:
            blocks[-1].items += block.items
            blocks[-1].bottom = block.bottom
        else:
            blocks.append(block)
    return blocks


def _starts_block(prev: Line, line: Line, pitch: float) -> bool:
    step = prev.top - line.top
    if step > 1.35 * max(pitch, prev.height) or step < -0.5 * line.height:
        return True  # blank space, or a jump upwards (new column/page region)
    if abs(line.size - prev.size) > 0.15 * max(prev.size, line.size):
        return True
    if line.bullet or _LIST_RE.match(line.text):
        return True
    if prev.bullet or _LIST_RE.match(prev.text):
        return line.x0 < prev.x0 + 0.5 * line.size  # continuation of an item is indented
    return line.x0 > prev.x0 + 1.5 * line.size  # first-line indent


def _make_block(group: list[Line], body: float) -> Block:
    text = _join(group)
    first = group[0]
    top, bottom = max(ln.top for ln in group), min(ln.bottom for ln in group)
    if first.bullet or _LIST_RE.match(first.text):
        kind = "ol" if _ORDERED_RE.match(first.text) else "ul"
        return Block(kind, items=[_LIST_RE.sub("", text, count=1)], top=top, bottom=bottom, lines=len(group))
    size = statistics.median(ln.size for ln in group)
    bold = all(ln.bold for ln in group)
    kind = "p"
    if body and len(group) <= 2 and len(text) <= 120:
        ratio = size / body
        if ratio >= 1.7:
            kind = "h1"
        elif ratio >= 1.35:
            kind = "h2"
        elif ratio >= 1.15 or (bold and len(text) <= 80 and not text.endswith((".", ":", ";"))):
            kind = "h3"
    return Block(kind, text=text, bold=bold and kind == "p", top=top, bottom=bottom, lines=len(group))


def _join(group: list[Line]) -> str:
    out = group[0].text
    for ln in group[1:]:
        if out.endswith("-") and len(out) > 1 and out[-2].isalpha() and ln.text[:1].islower():
            out = out[:-1] + ln.text
        else:
            out += " " + ln.text
    return out


def _insert_image(blocks: list[Block], bounds: tuple, file: Path, media_dir: Path) -> None:
    left, bottom, right, top, _, _ = bounds
    img = Block("img", src=f"{media_dir.name}/{file.name}", top=top, bottom=bottom)
    for i, block in enumerate(blocks):
        if block.kind != "img" and block.top < top:
            blocks.insert(i, img)
            return
    blocks.append(img)
