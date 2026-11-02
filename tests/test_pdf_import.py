"""Structured PDF import (engines/pdf_import.py) and the document engine paths built on it."""

import re
import threading
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from test_engines import convert

from recast.engines.base import Cancelled, ConversionError, JobContext
from recast.engines.pdf_import import (
    PDFIUM_LOCK, Line, _drop_running_lines, _join, blocks_to_text, pdf_to_blocks,
)

PARAGRAPH = (
    "Este é um parágrafo bastante longo, escrito para quebrar em várias linhas quando for renderizado "
    "na página A4, de modo que a reconstrução de parágrafos possa ser verificada de ponta a ponta. "
) * 3
PAGE_BREAK = '\n\n<div style="page-break-before: always"></div>\n\n'


@pytest.fixture(scope="module")
def structured_pdf(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("pdfimport")
    Image.new("RGB", (200, 120), (200, 30, 30)).save(d / "fig.png")
    md = d / "artigo.md"
    md.write_text(
        "# Título Principal\n\n"
        f"{PARAGRAPH}\n\n"
        "## Seção dois\n\n"
        "Outro parágrafo, curto.\n\n"
        "- primeiro item\n- segundo item\n- terceiro item\n\n"
        "1. um\n2. dois\n\n"
        "![figura](fig.png)\n\n"
        "Texto depois da figura.\n"
        f"{PAGE_BREAK}"
        "Segunda página.\n"
        f"{PAGE_BREAK}"
        "Terceira página.\n",
        encoding="utf-8",
    )
    [pdf] = convert(md, "PDF", "document", d)
    return pdf


def _blocks(pdf: Path, tmp_path: Path, media: bool = True):
    return pdf_to_blocks(pdf, JobContext(lambda f: None, tmp_path), tmp_path / "media" if media else None)


def test_blocks_reconstruct_structure(structured_pdf, tmp_path):
    pages = _blocks(structured_pdf, tmp_path)
    assert len(pages) == 3
    first = pages[0]
    kinds = [b.kind for b in first]
    assert kinds[:2] == ["h1", "p"]
    assert first[0].text == "Título Principal"
    paragraph = first[1]
    assert paragraph.lines > 3 and "\n" not in paragraph.text
    assert paragraph.text.startswith(PARAGRAPH[:60])
    assert "  " not in paragraph.text
    h2 = next(b for b in first if b.kind == "h2")
    assert h2.text == "Seção dois"
    ul = next(b for b in first if b.kind == "ul")
    assert ul.items == ["primeiro item", "segundo item", "terceiro item"]
    ol = next(b for b in first if b.kind == "ol")
    assert ol.items == ["um", "dois"]
    img = next(b for b in first if b.kind == "img")
    assert img.src.startswith("media/") and (tmp_path / img.src).exists()
    assert kinds.index("img") > kinds.index("ol")
    assert [b.text for b in pages[1]] == ["Segunda página."]
    assert [b.text for b in pages[2]] == ["Terceira página."]


def test_blocks_without_media_dir_skip_images(structured_pdf, tmp_path):
    pages = _blocks(structured_pdf, tmp_path, media=False)
    assert all(b.kind != "img" for page in pages for b in page)
    assert not (tmp_path / "media").exists()


def test_pdf_to_docx_keeps_headings_lists_and_images(structured_pdf, tmp_path):
    [docx] = convert(structured_pdf, "DOCX", "document", tmp_path)
    with zipfile.ZipFile(docx) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
        media = [n for n in zf.namelist() if n.startswith("word/media/")]
    assert 'w:val="Heading1"' in xml and 'w:val="Heading2"' in xml
    assert PARAGRAPH[:80] in xml  # one paragraph, not one run per PDF line
    assert "numPr" in xml  # list items
    assert len(media) == 1


def test_pdf_to_txt_joins_lines(structured_pdf, tmp_path):
    [txt] = convert(structured_pdf, "TXT", "document", tmp_path)
    text = txt.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "Título Principal" and lines[1] == ""
    assert any(line.startswith(PARAGRAPH[:60]) and PARAGRAPH[-30:].strip() in line for line in lines)
    assert "- primeiro item\n- segundo item\n- terceiro item" in text
    assert "1. um\n2. dois" in text
    assert "Segunda página." in text and "Terceira página." in text


@pytest.mark.parametrize("target", ["HTML", "MD", "ODT"])
def test_pdf_to_other_documents(structured_pdf, tmp_path, target):
    [out] = convert(structured_pdf, target, "document", tmp_path)
    if target in ("HTML", "MD"):
        text = out.read_text(encoding="utf-8")
        assert "Título Principal" in text and ("data:image" in text or "media/p1-1.png" in text)


def test_multi_page_pdf_to_png_names_pages(structured_pdf, tmp_path):
    outs = convert(structured_pdf, "PNG", "image", tmp_path)
    assert [o.name for o in outs] == ["artigo-1.png", "artigo-2.png", "artigo-3.png"]


def test_scanned_pdf(samples, tmp_path):
    [pdf] = convert(samples["png"], "PDF", "document", tmp_path)  # image-only PDF, no text
    [docx] = convert(pdf, "DOCX", "document", tmp_path)
    with zipfile.ZipFile(docx) as zf:
        assert len([n for n in zf.namelist() if n.startswith("word/media/")]) == 1
    with pytest.raises(ConversionError, match="digitalizado"):
        convert(pdf, "TXT", "document", tmp_path)


def test_cancel_inside_pdfium_releases_lock(structured_pdf, tmp_path):
    def progress(fraction: float) -> None:
        raise Cancelled

    with pytest.raises(Cancelled):
        pdf_to_blocks(structured_pdf, JobContext(progress, tmp_path), None)
    assert PDFIUM_LOCK.acquire(blocking=False)
    PDFIUM_LOCK.release()
    assert _blocks(structured_pdf, tmp_path, media=False)


def test_concurrent_imports_do_not_interfere(structured_pdf, tmp_path):
    results = []

    def work(i: int) -> None:
        d = tmp_path / str(i)
        d.mkdir()
        results.append(blocks_to_text(_blocks(structured_pdf, d)))

    threads = [threading.Thread(target=work, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 1


def _line(text: str, top: float, size: float = 12, x0: float = 72) -> Line:
    return Line(text, x0, x0 + 6 * len(text), top, top - size, size, False)


def test_running_headers_footers_and_page_numbers_are_dropped():
    pages = []
    for n in range(1, 5):
        pages.append(([
            _line("Relatório anual", 830), _line(f"Conteúdo da página {n}", 600), _line(f"Página {n}", 30),
        ], 842.0))
    _drop_running_lines(pages)
    assert [[ln.text for ln in lines] for lines, _ in pages] == [[f"Conteúdo da página {n}"] for n in range(1, 5)]


def test_page_number_dropped_even_in_short_documents():
    pages = [([_line("Texto", 600), _line("3", 30)], 842.0), ([_line("Mais texto", 600), _line("- 4 -", 30)], 842.0)]
    _drop_running_lines(pages)
    assert [[ln.text for ln in lines] for lines, _ in pages] == [["Texto"], ["Mais texto"]]


def test_join_dehyphenates_line_breaks():
    assert _join([_line("reconstru-", 100), _line("ção de linhas", 88)]) == "reconstrução de linhas"
    assert _join([_line("Rio -", 100), _line("Niterói", 88)]) == "Rio - Niterói"
    assert _join([_line("auto-", 100), _line("Suficiente", 88)]) == "auto- Suficiente"
    assert re.sub(r"\s+", " ", _join([_line("a", 100), _line("b", 88)])) == "a b"


def _handmade_pdf(path: Path) -> None:
    """Minimal PDF written by hand: non-embedded Helvetica, `Tf 1` with the size in the text matrix
    (so font sizes must come from glyph boxes), text bullets, a running header and page numbers."""

    def page_stream(n: int) -> bytes:
        word = {1: "alfa", 2: "bravo", 3: "charlie"}[n]
        rows = [
            ("F2", 24, 72, 720, f"Relatorio {word}"),
            ("F1", 11, 72, 670, f"Primeira linha {word} de um paragrafo que continua na linha seguinte sem inter-"),
            ("F1", 11, 72, 656, "rupcao e termina aqui."),
            ("F1", 11, 72, 630, "Segundo paragrafo, separado por espaco maior."),
            ("F2", 14, 72, 600, "Lista de itens"),
            ("F1", 11, 80, 580, "\u2022 primeiro item"),
            ("F1", 11, 80, 566, "\u2022 segundo item"),
            ("F1", 11, 72, 540, "1. um"),
            ("F1", 11, 72, 526, "2. dois"),
            ("F1", 9, 72, 770, "Cabecalho corrido"),
            ("F1", 9, 300, 30, f"Pagina {n}"),
        ]
        ops = [f"BT /{font} 1 Tf {size} 0 0 {size} {x} {y} Tm ({text}) Tj ET" for font, size, x, y, text in rows]
        return "\n".join(ops).encode("cp1252")

    objs: list[bytes] = []

    def add(obj: bytes) -> int:
        objs.append(obj)
        return len(objs)

    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    contents = []
    for n in (1, 2, 3):
        stream = page_stream(n)
        contents.append(add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
    pages_id = len(objs) + len(contents) + 1
    kids = [
        add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
            b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> >>" % (pages_id, c, f1, f2))
        for c in contents
    ]
    assert add(b"<< /Type /Pages /Kids [" + b" ".join(b"%d 0 R" % k for k in kids) + b"] /Count 3 >>") == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, catalog, xref)
    path.write_bytes(out)


def test_handmade_pdf_structure_and_running_lines(tmp_path):
    pdf = tmp_path / "hand.pdf"
    _handmade_pdf(pdf)
    pages = _blocks(pdf, tmp_path)
    assert len(pages) == 3
    for n, word in enumerate(("alfa", "bravo", "charlie")):
        blocks = pages[n]
        assert [b.kind for b in blocks] == ["h1", "p", "p", "h3", "ul", "ol"]
        assert blocks[0].text == f"Relatorio {word}"
        assert blocks[1].text == f"Primeira linha {word} de um paragrafo que continua na linha seguinte sem interrupcao e termina aqui."
        assert blocks[4].items == ["primeiro item", "segundo item"]
        assert blocks[5].items == ["um", "dois"]
    text = blocks_to_text(pages)
    assert "Cabecalho" not in text and "Pagina" not in text
    [docx] = convert(pdf, "DOCX", "document", tmp_path)
    assert docx.stat().st_size > 0
