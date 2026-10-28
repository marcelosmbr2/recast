# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Recast**: an offline desktop file converter (images, documents, audio, video, archives, e-books) built with Python + PySide6 (Qt Widgets). The UI was ported from an HTML mockup that is no longer in the repo; the code is now the source of truth (format tables, `estimate_factor`, queue states, theme tokens). User-facing strings are pt-BR; code, identifiers and comments are English. No code may touch the network.

## Commands

Dependencies and `.venv` are managed with **uv**; run everything through `uv run`.

```bash
uv sync                          # create/update .venv from uv.lock (includes dev group)
uv run recast                    # launch the app (gui-script, no console)
uv run python -m recast          # same, with a console (tracebacks visible)
uv run pytest                    # all tests (~25 s; generates media with the bundled FFmpeg)
uv run pytest tests/test_queue.py::test_pause_stops_dispatching   # single test
uv add <pkg> / uv add --dev <pkg>
```

Packaging (Windows): `powershell -ExecutionPolicy Bypass -File packaging/build.ps1` → `dist/Recast/` (PyInstaller one-folder, windowed) + `dist/Recast-<version>-Setup.exe` (Inno Setup 6, per-user install). It runs `Recast.exe --self-test <report>` on the bundle (`recast/selftest.py` converts generated samples through every engine); use that after touching engines or `packaging/recast.spec`, since a tool or DLL missing from the bundle only fails at conversion time. Releases: bump `pyproject.toml` + `recast.__version__`, push tag `vX.Y.Z`; `.github/workflows/release.yml` builds and attaches the installer.

No linter/formatter is configured. If Qt DLLs fail to load after changing PySide6 packages, run `uv sync --reinstall-package pyside6-essentials --reinstall-package shiboken6` (uninstalling PySide6 add-ons deletes shared files).

## Architecture

Three layers under `src/recast/`; dependencies point downward only (`ui` → `core` → `engines`).

- **`core/`**: no widgets.
  - `formats.py`: format tables (`FORMATS`, `COMPAT`, `DEFAULT_TARGET`, `FACTOR`...) and `estimate_factor()`; `tests/test_formats.py` pins the expected values.
  - `queue.py` / `ConversionQueue` owns `QueueItem`s and is the single source of truth for the UI (signals `item_changed(id)`, `items_changed`, `running_changed`, `item_converted`, `queue_finished`). Jobs run as `QRunnable`s on a `QThreadPool`; workers report back through `_Bridge` signals (queued to the GUI thread). Concurrency is enforced by `_dispatch()` using `settings.parallel`, not by the pool size. Each job writes into a temp staging dir; `_finalize()` then moves outputs into the output folder under `_FINALIZE_LOCK`, applying the conflict policy (Renomear/Substituir/Ignorar).
  - Pause stops dispatching and suspends running tool processes (`psutil`); in-process engines finish their current file.
  - `storage.py`: settings, history and user presets as JSON in `QStandardPaths.AppDataLocation`. `MainWindow(data_dir)` takes an override, which tests use.
- **`engines/`**: `Engine.supports(src_ext, target, target_cat)` + `convert(job, ctx)`.
  - `registry.engine_for()` picks the first engine that supports a pair. The format picker, `default_target()` and the queue all use it, so a pair with no engine is shown as "Indisponível".
  - Engines: `image` (Pillow + pillow-heif; SVG via QtSvg), `media` (FFmpeg from imageio-ffmpeg; progress from `-progress pipe:1`), `archive` (zipfile/tarfile/py7zr), `document` (pypandoc-binary; PDF *output* via pandoc → HTML → `QTextDocument` → `QPdfWriter`; PDF *input* via pypdfium2, serialized by `_PDFIUM_LOCK` because pdfium isn't thread-safe).
  - Engines must call `ctx.progress()` (it also checks cancellation) and run external tools through `ctx.run()` so cancel/pause work. Raise `ConversionError` with a pt-BR message for user-facing failures.
  - Not supported, by design: RAR input, MOBI/AZW3, legacy Office (doc/ppt/xls/key/pages), camera RAW, OCR.
- **`ui/`**: `main_window.py` wires the views to the queue and stores.
  - Styling is one global stylesheet in `theme.py`. Widgets opt in with `setProperty("role", ...)` (frames/buttons) or `QLabel[t="..."]` text roles from `TEXT_ROLES`; use `widgets.text()`/`set_prop()` instead of per-widget `setStyleSheet`.
  - Icons are inline SVGs in `icons.py`, recolored at render time.

## Packaging notes

- The packaged app is windowed (no console): logging goes to `recast.log` in the app data dir, and every subprocess must pass `creationflags=_NO_WINDOW` (from `engines/base.py`) or a console window flashes. `pandoc_exe()` deliberately avoids `pypandoc.get_pandoc_path()` for that reason.
- Bundled tools are collected as data files in `packaging/recast.spec` (FFmpeg from `imageio_ffmpeg/binaries`, pandoc from `pypandoc/files`); new engines that ship binaries need an entry there and a case in `selftest.py`.
- Keep `THIRD-PARTY-NOTICES.md` in sync when adding bundled components (FFmpeg and pandoc are GPL; they run as separate processes).

## Qt gotchas found here

- Font sizes go through `theme.pt()`: QSS rounds fractional `px` but keeps fractional `pt`.
- A QSS rule with only a partial border (e.g. `border-bottom`) on a `QFrame` is ignored unless it also sets `background`.
- The `offscreen` platform has no system fonts. `recast.resources.load_fonts()` registers the bundled Inter / JetBrains Mono (tests' `conftest.py` does this), otherwise generated PDFs contain no text.
- Tests run with `QT_QPA_PLATFORM=offscreen` (set in `conftest.py`); use `qtbot`, never a second `QApplication`. Don't create Qt timers/objects before the `QApplication` exists.
- In Qt 6 `app.quit()` closes windows, so `MainWindow.closeEvent`'s "conversions running" prompt blocks headless scripts that quit mid-conversion.
- Wrapped `QLabel`s need a fixed width (not just a max width) to get their full height.

## Agent tooling

- `.mcp.json` registers the hosted `qt-docs` MCP server for Qt API lookups.
- `.claude/skills/` and `.claude/agents/` are vendored copies of the Qt Company skills from `TheQtCompanyRnD/agent-skills` (commit `6845f02`, 2026-10-20). Don't edit them in place; to update, re-copy `skills/*` and `agents/*.md` from that repo. Most target QML/C++/CMake, not PySide6 Widgets, so apply them only where they fit (e.g. `qt-ui-design`).
