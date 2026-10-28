import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

import psutil
import py7zr
import pytest
from PIL import Image

from recast.core.models import ConversionOptions
from recast.core.queue import split_name
from recast.engines.base import Cancelled, Job, JobContext
from recast.engines.media import video_codecs
from recast.engines.registry import engine_for


def convert(src: Path, target: str, target_cat: str, tmp_path: Path, **opts) -> list[Path]:
    stem, ext = split_name(src.name)
    engine = engine_for(ext, target, target_cat)
    assert engine is not None, f"no engine for {ext} → {target}"
    run = Path(tempfile.mkdtemp(dir=tmp_path))
    staging, work = run / "out", run / "work"
    staging.mkdir()
    work.mkdir()
    progress = []
    job = Job(src, ext, target, target_cat, ConversionOptions().merged(opts), staging, stem)
    engine.convert(job, JobContext(progress.append, work))
    assert progress and progress[-1] == 1.0
    assert job.dst.exists() and job.dst.stat().st_size > 0
    return sorted(staging.iterdir())


@pytest.mark.parametrize("target", ["JPG", "WEBP", "AVIF", "HEIC", "BMP", "ICO", "TIFF", "GIF"])
def test_png_to_image(samples, tmp_path, target):
    [out] = convert(samples["png"], target, "image", tmp_path)
    with Image.open(out) as img:
        assert img.size[0] > 0


def test_png_resize_half(samples, tmp_path):
    [out] = convert(samples["png"], "JPG", "image", tmp_path, resize="50%")
    assert Image.open(out).size == (320, 200)


def test_png_to_pdf(samples, tmp_path):
    [out] = convert(samples["png"], "PDF", "document", tmp_path)
    assert out.read_bytes().startswith(b"%PDF")


def test_animated_gif_to_webp_keeps_frames(samples, tmp_path):
    [out] = convert(samples["gif"], "WEBP", "image", tmp_path)
    assert Image.open(out).n_frames == 3


@pytest.mark.parametrize("target", ["MP3", "FLAC", "OPUS", "M4A", "AIFF", "OGG", "AAC"])
def test_wav_to_audio(samples, tmp_path, target):
    convert(samples["wav"], target, "audio", tmp_path, channels="Mono")


@pytest.mark.parametrize(("target", "cat"), [
    ("WEBM", "video"), ("MKV", "video"), ("MOV", "video"), ("AVI", "video"), ("GIF", "video"),
    ("MP3", "audio"), ("PNG", "image"), ("JPG", "image"),
])
def test_mp4_conversions(samples, tmp_path, target, cat):
    convert(samples["mp4"], target, cat, tmp_path, res="720p")


@pytest.mark.parametrize("target", ["7Z", "TAR.GZ", "TAR"])
def test_zip_to_archive(samples, tmp_path, target):
    [out] = convert(samples["zip"], target, "archive", tmp_path, level="Máxima")
    if target == "7Z":
        with py7zr.SevenZipFile(out) as zf:
            names = zf.getnames()
    else:
        with tarfile.open(out) as tf:
            names = tf.getnames()
    assert "readme.txt" in names and "sub/data.bin" in names


def test_archive_roundtrip_to_zip(samples, tmp_path):
    [tgz] = convert(samples["zip"], "TAR.GZ", "archive", tmp_path)
    [zp] = convert(tgz, "ZIP", "archive", tmp_path)
    with zipfile.ZipFile(zp) as zf:
        assert sorted(zf.namelist()) == ["readme.txt", "sub/data.bin"]


@pytest.mark.parametrize("target", ["DOCX", "ODT", "RTF", "HTML", "TXT", "PDF"])
def test_markdown_to_document(samples, tmp_path, target):
    convert(samples["md"], target, "document", tmp_path)


@pytest.mark.parametrize(("target", "cat"), [("EPUB", "ebook"), ("FB2", "ebook"), ("PNG", "image")])
def test_markdown_to_ebook_and_image(samples, tmp_path, target, cat):
    convert(samples["md"], target, cat, tmp_path)


def test_txt_to_pdf_then_back_to_text(samples, tmp_path):
    [pdf] = convert(samples["txt"], "PDF", "document", tmp_path)
    [txt] = convert(pdf, "TXT", "document", tmp_path)
    assert "Segundo parágrafo" in txt.read_text(encoding="utf-8")


def test_pdf_to_docx_and_png(samples, tmp_path):
    [pdf] = convert(samples["txt"], "PDF", "document", tmp_path)
    convert(pdf, "DOCX", "document", tmp_path)
    convert(pdf, "PNG", "image", tmp_path)


def test_unsupported_pairs():
    assert engine_for("png", "DOCX", "document") is None
    assert engine_for("rar", "ZIP", "archive") is None
    assert engine_for("mobi", "EPUB", "ebook") is None
    assert engine_for("pdf", "PDF", "document") is None
    assert engine_for("epub", "MOBI", "ebook") is None


def test_run_kills_child_when_on_line_raises(tmp_path):
    ctx = JobContext(lambda f: None, tmp_path)
    seen = {}

    def on_line(_line):
        seen["pid"] = ctx._proc.pid
        raise Cancelled

    script = "import time\nwhile True:\n    print('tick', flush=True)\n    time.sleep(0.05)"
    with pytest.raises(Cancelled):
        ctx.run([sys.executable, "-c", script], on_line)
    assert not psutil.pid_exists(seen["pid"])


def test_mov_never_offers_av1(samples, tmp_path):
    assert "AV1" not in video_codecs("MOV")
    convert(samples["mp4"], "MOV", "video", tmp_path, codec="AV1")  # falls back to H.264


def test_16bit_grayscale_is_scaled_not_clipped(tmp_path):
    src = tmp_path / "deep.png"
    Image.new("I;16", (8, 8), 3000).save(src)
    [jpg] = convert(src, "JPG", "image", tmp_path)
    assert Image.open(jpg).getpixel((0, 0))[0] == pytest.approx(3000 / 65535 * 255, abs=2)
    [tiff] = convert(src, "TIFF", "image", tmp_path)
    assert Image.open(tiff).getpixel((0, 0)) == 3000  # lossless targets keep 16-bit


def test_kept_exif_drops_orientation(tmp_path):
    src = tmp_path / "phone.jpg"
    img = Image.new("RGB", (40, 20), "red")
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation: rotate 90° CW
    exif[0x010F] = "Camera Co"  # Make
    img.save(src, exif=exif.tobytes())
    [kept] = convert(src, "JPG", "image", tmp_path, strip=False)
    out = Image.open(kept)
    assert out.size == (20, 40)
    assert 0x0112 not in out.getexif() and out.getexif()[0x010F] == "Camera Co"
    [stripped] = convert(src, "JPG", "image", tmp_path, strip=True)
    assert len(Image.open(stripped).getexif()) == 0


def test_documents_get_no_injected_title(samples, tmp_path):
    [odt] = convert(samples["md"], "ODT", "document", tmp_path)
    assert ">notes<" not in zipfile.ZipFile(odt).read("content.xml").decode()
    [pdf] = convert(samples["md"], "PDF", "document", tmp_path)
    [txt] = convert(pdf, "TXT", "document", tmp_path)
    assert txt.read_text(encoding="utf-8").lstrip().startswith("Título")


def test_ebook_title_falls_back_to_file_name(samples, tmp_path):
    [plain] = convert(samples["md"], "EPUB", "ebook", tmp_path)
    assert "<dc:title" in (opf := _epub_opf(plain)) and ">notes<" in opf
    titled = tmp_path / "titled.md"
    titled.write_text("---\ntitle: Meu Livro\n---\n\nTexto.\n", encoding="utf-8")
    [book] = convert(titled, "EPUB", "ebook", tmp_path)
    assert ">Meu Livro<" in _epub_opf(book)


def _epub_opf(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".opf"))
        return zf.read(name).decode("utf-8")
