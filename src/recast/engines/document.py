"""Documents and e-books: pandoc for text formats, Qt for PDF output, pdfium for PDF input."""

from __future__ import annotations

import functools
import html
import threading
from pathlib import Path

import pypandoc
import pypdfium2 as pdfium
from PySide6.QtCore import QMarginsF, QUrl
from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument

from recast.engines.base import ConversionError, Engine, Job, JobContext
from recast.engines.image import MULTI_FRAME, can_write, prepare_frame, save_image

PANDOC_IN = {
    "docx": "docx", "odt": "odt", "rtf": "rtf", "html": "html", "htm": "html", "md": "markdown",
    "pptx": "pptx", "xlsx": "xlsx", "csv": "csv", "epub": "epub", "fb2": "fb2",
}
TEXT_IN = {"txt", "pdf"}  # read as plain text, then fed to pandoc as HTML paragraphs
# pdfium is not thread-safe; serialize every call into it.
_PDFIUM_LOCK = threading.Lock()

PANDOC_OUT = {
    "DOCX": "docx", "ODT": "odt", "RTF": "rtf", "HTML": "html", "MD": "gfm", "TXT": "plain",
    "EPUB": "epub", "FB2": "fb2",
}


@functools.cache
def pandoc_exe() -> str:
    return pypandoc.get_pandoc_path()


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _pdf_text(path: Path, ctx: JobContext) -> str:
    pages = []
    with _PDFIUM_LOCK:
        pdf = _open_pdf(path)
        for i, page in enumerate(pdf):
            pages.append(page.get_textpage().get_text_range())
            ctx.progress(0.4 * (i + 1) / len(pdf))
        pdf.close()
    return "\n\n".join(pages)


def _open_pdf(path: Path) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(str(path))
    except pdfium.PdfiumError as e:
        raise ConversionError(f"PDF inválido: {e}") from e


def _text_to_html(text: str, title: str) -> str:
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
    body = "\n".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>" for p in paragraphs)
    return f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title></head><body>{body}</body></html>"


class DocumentEngine(Engine):
    name = "Documentos"

    def supports(self, src_ext: str, target: str, target_cat: str) -> bool:
        if src_ext not in PANDOC_IN and src_ext not in TEXT_IN:
            return False
        if target_cat == "image":
            return can_write(target)
        if src_ext == "pdf" and target == "PDF":
            return False
        return target == "PDF" or target in PANDOC_OUT

    def convert(self, job: Job, ctx: JobContext) -> None:
        if job.target_cat == "image":
            pdf = job.src if job.src_ext == "pdf" else self._to_pdf(job, ctx, ctx.tmp / "render.pdf")
            self._render_pages(pdf, job, ctx)
        elif job.target == "PDF":
            self._to_pdf(job, ctx, job.dst)
        elif job.src_ext == "pdf" and job.target == "TXT":
            job.dst.write_text(_pdf_text(job.src, ctx), encoding="utf-8")
        else:
            src, fmt = self._pandoc_input(job, ctx)
            self._pandoc(src, fmt, PANDOC_OUT[job.target], job.dst, job, ctx)
        ctx.progress(1.0)

    def _pandoc_input(self, job: Job, ctx: JobContext) -> tuple[Path, str]:
        if job.src_ext in PANDOC_IN:
            return job.src, PANDOC_IN[job.src_ext]
        text = _pdf_text(job.src, ctx) if job.src_ext == "pdf" else _read_text(job.src)
        tmp = ctx.tmp / "input.html"
        tmp.write_text(_text_to_html(text, job.stem), encoding="utf-8")
        return tmp, "html"

    def _pandoc(self, src: Path, fmt: str, to: str, dst: Path, job: Job, ctx: JobContext) -> None:
        args = [pandoc_exe(), str(src), "-f", fmt, "-t", to, "-o", str(dst), "--metadata", f"title={job.stem}"]
        if to in ("html", "rtf"):
            args.append("--standalone")
        if to == "html":
            args.append("--embed-resources")
        ctx.progress(0.5)
        ctx.run(args)

    def _to_pdf(self, job: Job, ctx: JobContext, dst: Path) -> Path:
        """Render the document through pandoc → HTML → QTextDocument → QPdfWriter."""
        media = ctx.tmp / "media"
        if job.src_ext in TEXT_IN:
            text = _pdf_text(job.src, ctx) if job.src_ext == "pdf" else _read_text(job.src)
            page_html = _text_to_html(text, job.stem)
        else:
            out = ctx.tmp / "page.html"
            ctx.progress(0.2)
            ctx.run([
                pandoc_exe(), str(job.src), "-f", PANDOC_IN[job.src_ext], "-t", "html", "--standalone",
                "--extract-media", str(media), "--metadata", f"title={job.stem}", "-o", str(out),
            ])
            page_html = out.read_text(encoding="utf-8")
        ctx.progress(0.6)
        doc = QTextDocument()
        doc.setDefaultFont(QFont("Inter", 11))
        doc.setBaseUrl(QUrl.fromLocalFile(str(ctx.tmp) + "/"))
        doc.setHtml(page_html)
        writer = QPdfWriter(str(dst))
        writer.setResolution(150 if job.opts.compress else 300)
        writer.setPageLayout(QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait,
            QMarginsF(18, 18, 18, 18), QPageLayout.Unit.Millimeter,
        ))
        writer.setTitle(job.stem)
        doc.print_(writer)
        del writer  # flushes the file
        if not dst.exists():
            raise ConversionError("Falha ao gerar o PDF")
        return dst

    def _render_pages(self, pdf_path: Path, job: Job, ctx: JobContext) -> None:
        scale = 150 / 72 if job.opts.compress else 200 / 72
        frames = []
        with _PDFIUM_LOCK:
            pdf = _open_pdf(pdf_path)
            count = len(pdf)
            for i, page in enumerate(pdf):
                img = page.render(scale=scale).to_pil()
                frames.append(prepare_frame(img, job.target, job.opts))
                ctx.progress(0.6 + 0.35 * (i + 1) / count)
            pdf.close()
        if count == 0:
            raise ConversionError("PDF sem páginas")
        if job.target in MULTI_FRAME or count == 1:
            save_image(frames, job.dst, job.target, job.opts, durations=[1000] * count)
            return
        width = len(str(count))
        for i, frame in enumerate(frames, 1):
            dst = job.staging / f"{job.stem}-{i:0{width}d}.{job.target.lower()}"
            save_image([frame], dst, job.target, job.opts)
