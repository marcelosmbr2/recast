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

## Instalar (Windows)

Baixe `Recast-<versão>-Setup.exe` na página de [releases](https://github.com/marcelosmbr2/recast/releases) e execute. A instalação é por usuário e não pede administrador; o assistente oferece instalar para todos os usuários. O instalador não é assinado digitalmente, então o Windows SmartScreen pode mostrar "O Windows protegeu o computador": clique em **Mais informações → Executar assim mesmo**.

Requer Windows 10 ou 11, 64 bits.

## Desenvolvimento

Requisitos:

- Python 3.11+ (o build de release usa 3.14, fixado em `.python-version`)
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

## Gerar o instalador

Requer [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```bash
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

Gera `dist/Recast/` (app empacotado com PyInstaller), roda o autoteste do app empacotado (`Recast.exe --self-test`) e cria `dist/Recast-<versão>-Setup.exe`.

## Publicar uma versão

1. Atualize a versão em `pyproject.toml` e em `src/recast/__init__.py`.
2. Faça o commit, crie a tag e envie: `git tag v0.2.0 && git push origin main v0.2.0`.
3. O workflow [Release](.github/workflows/release.yml) roda os testes, gera o instalador e o publica na release da tag.

## Licença

MIT (veja [LICENSE](LICENSE)). O instalador inclui FFmpeg, pandoc, Qt e outros componentes sob as próprias licenças; veja [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## Estrutura

```
src/recast/
  core/       # formatos, fila de conversão, modelos e persistência (sem widgets)
  engines/    # motores de conversão (imagem, mídia, compactados, documentos)
  ui/         # janela, telas, inspetor, seletor de formatos, tema e ícones
  resources/  # fontes Inter e JetBrains Mono (SIL OFL)
packaging/    # PyInstaller, Inno Setup e script de build do instalador
tests/        # pytest + pytest-qt
```
