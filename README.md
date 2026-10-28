# Recast

Conversor de arquivos para desktop, 100% offline, feito em Python com PySide6 (Qt Widgets). Nada é enviado pela rede: todas as conversões rodam no próprio computador, com motores instalados junto com o app.

## Recursos

- Fila com arrastar e soltar, conversões simultâneas (1, 2 ou 4), pausar/retomar e estimativa de tempo restante.
- Inspetor por arquivo: formato de saída, qualidade, codec e resolução (vídeo), taxa de bits e canais (áudio), redimensionamento e remoção de metadados (imagem), nível de compressão (arquivos compactados).
- Seletor de formatos com busca; "Tudo para…" aplica um formato a todos os arquivos compatíveis.
- Predefinições (embutidas e criadas pelo usuário), histórico local e ajustes (pasta de saída, conflito de nomes, manter originais).

## Formatos

| Categoria | Entrada | Saída | Motor |
|---|---|---|---|
| Imagens | JPG, PNG, WEBP, AVIF, HEIC, GIF, TIFF, BMP, ICO, SVG | JPG, PNG, WEBP, AVIF, HEIC, GIF, TIFF, BMP, ICO, PDF | Pillow, pillow-heif |
| Áudio | MP3, WAV, FLAC, AAC, OGG, M4A, OPUS, AIFF, WMA | MP3, AAC, M4A, OPUS, OGG, FLAC, WAV, AIFF | FFmpeg |
| Vídeo | MP4, MOV, MKV, WEBM, AVI, WMV, M4V, 3GP | MP4, MOV, WEBM, MKV, AVI, GIF, áudio, quadro como imagem | FFmpeg |
| Documentos | DOCX, ODT, RTF, TXT, HTML, MD, PPTX, XLSX, CSV, PDF | PDF, DOCX, ODT, RTF, TXT, HTML, MD, EPUB, FB2, imagens | pandoc, Qt, pdfium |
| Compactados | ZIP, 7Z, TAR, TAR.GZ, GZ, BZ2 | ZIP, 7Z, TAR.GZ, TAR | zipfile, tarfile, py7zr |
| E-books | EPUB, FB2 | EPUB, FB2, documentos | pandoc |

Ainda não suportados: RAR, MOBI/AZW3, formatos antigos do Office (DOC, PPT, XLS), RAW de câmera e OCR. No seletor, eles aparecem como "Indisponível". De PDF para documentos editáveis, só o texto é convertido.

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Executar

```bash
uv sync
uv run recast
```

Ou, com console para ver erros: `uv run python -m recast`.

## Testes

```bash
uv run pytest
```

## Estrutura

```
src/recast/
  core/       # formatos, fila de conversão, modelos e persistência (sem widgets)
  engines/    # motores de conversão (imagem, mídia, compactados, documentos)
  ui/         # janela, telas, inspetor, seletor de formatos, tema e ícones
  resources/  # fontes Inter e JetBrains Mono (SIL OFL)
mockup/       # protótipo HTML de referência
tests/        # pytest + pytest-qt
```
