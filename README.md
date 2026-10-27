# Media Converter

Aplicação desktop em Python com PySide6 (Qt Widgets).

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Executar

```bash
uv sync
uv run media-converter
```

Ou como módulo: `uv run python -m media_converter`.

## Testes

```bash
uv run pytest
```

## Estrutura

```
src/media_converter/
  app.py          # ponto de entrada (QApplication)
  main_window.py  # janela principal (QMainWindow)
tests/            # testes com pytest-qt
```
