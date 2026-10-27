# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Desktop media converter built with Python + PySide6 (Qt Widgets). Early scaffold: only the main window shell exists so far; no conversion logic yet. User-facing UI strings are in Portuguese (pt-BR); code, identifiers and comments are in English.

## Commands

Dependencies and the virtualenv (`.venv`) are managed with **uv**; always run tools through `uv run`.

```bash
uv sync                          # create/update .venv from uv.lock (includes dev group)
uv run media-converter           # launch the app (gui-script entry point)
uv run python -m media_converter # same, but keeps a console attached (stdout/tracebacks visible)
uv run pytest                    # all tests
uv run pytest tests/test_main_window.py::test_main_window_title   # single test
uv add <pkg> / uv add --dev <pkg>  # add a runtime / dev dependency (updates pyproject.toml + uv.lock)
```

No linter/formatter is configured yet.

## Architecture

- `src/` layout, built with hatchling and installed editable into `.venv` by `uv sync`, so `import media_converter` works from tests without path hacks.
- Entry flow: `[project.gui-scripts] media-converter` → `media_converter.app:main()` creates the single `QApplication`, sets app name/version (version comes from `media_converter.__version__`; keep it in sync with `pyproject.toml`), shows `MainWindow`, and returns `app.exec()`. `__main__.py` calls the same `main()`.
- `MainWindow` (`main_window.py`) is a `QMainWindow` that builds menus, central widget and status bar in private `_create_*` helpers called from `__init__`. Follow this pattern when adding UI sections.

## Qt-specific notes

- On Windows the `gui-scripts` launcher has no console, so `print`/uncaught exceptions are invisible; use `python -m media_converter` when debugging.
- Tests use **pytest-qt**: take the `qtbot` fixture (it provides the `QApplication`) and register widgets with `qtbot.addWidget(...)`. Don't instantiate `QApplication` in tests.
- For headless runs (CI, or smoke-testing from an agent shell), set `QT_QPA_PLATFORM=offscreen`. Never call `QTimer.singleShot`/create Qt objects before the `QApplication` exists — the timer silently never fires and `exec()` hangs forever.
- Long-running work (future conversions) must not run on the GUI thread; use `QThread`/`QThreadPool` or `QProcess` and communicate back via signals.

## Agent tooling

- `.mcp.json` registers the hosted `qt-docs` MCP server for Qt API lookups.
- `.claude/skills/` and `.claude/agents/` are vendored copies of the Qt Company skills from `TheQtCompanyRnD/agent-skills` (commit `6845f02`, 2026-10-20). Don't edit them in place; to update, re-copy `skills/*` and `agents/*.md` from that repo. Most target QML/C++/CMake, not PySide6 Widgets, so apply them only where they fit (e.g. `qt-ui-design`).
