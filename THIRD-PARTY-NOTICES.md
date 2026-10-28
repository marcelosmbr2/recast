# Third-party software

Recast is MIT-licensed (see `LICENSE`). The Windows installer also ships the
components below, each under its own license. FFmpeg and pandoc are separate
programs that Recast runs as child processes; they are not linked into Recast.

| Component | Version | License | Source |
|---|---|---|---|
| FFmpeg (gyan.dev "essentials" build, via imageio-ffmpeg) | 7.1 | GPL-3.0-or-later | https://ffmpeg.org/download.html · build: https://www.gyan.dev/ffmpeg/builds/ |
| pandoc (via pypandoc-binary) | 3.9 | GPL-2.0-or-later | https://github.com/jgm/pandoc |
| Qt for Python (PySide6, shiboken6) | 6.12 | LGPL-3.0 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Python | 3.14 | PSF License | https://www.python.org/downloads/source/ |
| Pillow | 13.0 | MIT-CMU | https://github.com/python-pillow/Pillow |
| pillow-heif (libheif, libde265, x265) | 1.8 | BSD-3-Clause; bundled libheif LGPL-3.0, libde265 LGPL-3.0, x265 GPL-2.0 | https://github.com/bigcat88/pillow_heif |
| pypdfium2 (PDFium) | 5.14 | Apache-2.0 / BSD-3-Clause | https://github.com/pypdfium2-team/pypdfium2 |
| py7zr and its codecs | 1.1 | LGPL-2.1-or-later | https://github.com/miurahr/py7zr |
| imageio-ffmpeg | 0.6 | BSD-2-Clause | https://github.com/imageio/imageio-ffmpeg |
| pypandoc | 1.17 | MIT | https://github.com/JessicaTegner/pypandoc |
| psutil | 7.2 | BSD-3-Clause | https://github.com/giampaolo/psutil |
| Inter font | 4.1 | SIL Open Font License 1.1 | https://github.com/rsms/inter |
| JetBrains Mono font | 2.304 | SIL Open Font License 1.1 | https://github.com/JetBrains/JetBrainsMono |

The full license texts of the fonts are installed next to them
(`_internal/recast/resources/fonts`). The GNU GPL and LGPL texts are available
at https://www.gnu.org/licenses/. The source code of every GPL/LGPL component
listed above, at the version shipped, is available from the linked projects;
if you cannot obtain it there, open an issue at
https://github.com/marcelosmbr2/recast/issues and it will be provided.
