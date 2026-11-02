"""Download page: a link form on top of the downloads queue (YouTube/Vimeo videos saved as MP4 or MP3)."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QApplication, QLineEdit, QStackedWidget, QVBoxLayout, QWidget

from recast.engines.base import ConversionError
from recast.engines.download import SUPPORTED_SITES, DownloadEngine, VideoInfo, parse_video_url
from recast.ui import platform, theme
from recast.ui.convert_view import QueueView, empty_state, header, plural
from recast.ui.widgets import Button, SegmentedControl, frame, hbox, set_prop, text, vbox

CHOICES = {"Vídeo · MP4": ("MP4", "video"), "Áudio · MP3": ("MP3", "audio")}
HINT = f"Cole o link de um vídeo do {' ou '.join(SUPPORTED_SITES)} ({platform.SHORTCUT_MOD}+L)."


class _ProbeBridge(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Probe(QRunnable):
    def __init__(self, url: str, bridge: _ProbeBridge, probe=None) -> None:
        super().__init__()
        self._url, self._bridge, self._probe = url, bridge, probe or DownloadEngine().probe

    def run(self) -> None:
        try:
            self._bridge.done.emit(self._probe(self._url))
        except ConversionError as e:
            self._bridge.failed.emit(str(e))
        except Exception as e:  # never lose the worker silently
            self._bridge.failed.emit(f"Erro inesperado: {e}")


class DownloadView(QueueView):
    """Looks a link up off the GUI thread, then emits `link_resolved(info, target, target_cat)`."""

    link_resolved = Signal(object, str, str)

    def __init__(self, queue, parent: QWidget | None = None, probe=None) -> None:
        super().__init__(queue, parent)
        self._probe = probe
        self._bridge = _ProbeBridge(self)
        self._bridge.done.connect(self._on_done)
        self._bridge.failed.connect(self._on_failed)

    def _build(self, col: QVBoxLayout) -> None:
        self._busy = False
        bar, row, self._summary = header("Baixar vídeos", "Nenhum vídeo adicionado")
        self._clear = Button("Limpar", "ghost")
        self._clear.clicked.connect(self.queue.clear_done)
        self._primary = Button("Pausar", "primary", "pause", color=theme.ACCENT_TEXT, icon_size=12)
        self._primary.clicked.connect(self.queue.toggle)
        row.addWidget(self._clear)
        row.addWidget(self._primary)
        col.addWidget(bar)
        col.addWidget(self._build_form())

        self._pages = QStackedWidget()
        page, _ = empty_state(
            "download", "Nenhum vídeo baixado ainda",
            "Cole um link acima ou arraste-o para cá. O download começa na hora e o arquivo vai "
            "para a pasta de saída.",
        )
        self._pages.addWidget(page)
        self._pages.addWidget(self._build_list(["Vídeo", "Salvar como", "Status", ""]))
        col.addWidget(self._pages, 1)

    def _build_form(self) -> QWidget:
        form = frame("divider-bottom")
        fcol = vbox(form, (20, 14, 16, 12), 8)
        row = hbox(spacing=8)
        self._url = QLineEdit()
        self._url.setProperty("role", "input")
        self._url.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self._url.setClearButtonEnabled(True)
        self._url.textChanged.connect(self._validate)
        self._url.returnPressed.connect(self._submit)
        row.addWidget(self._url, 1)
        self._choice = SegmentedControl(list(CHOICES), next(iter(CHOICES)))
        row.addWidget(self._choice)
        self._add = Button("Baixar", "primary", "download", color=theme.ACCENT_TEXT, icon_size=13)
        self._add.clicked.connect(self._submit)
        row.addWidget(self._add)
        fcol.addLayout(row)
        self._status = text(HINT, "small-dim", wrap=True)
        fcol.addWidget(self._status)
        self._add.setEnabled(False)
        return form

    # Public

    def target(self) -> tuple[str, str]:
        return CHOICES[self._choice.current() or next(iter(CHOICES))]

    def url(self) -> str | None:
        return parse_video_url(self._url.text())

    def set_link(self, url: str = "") -> None:
        """Fill the form with `url` (dropped/pasted from outside) and look it up, or just focus it."""
        if self._busy:
            return
        if url:
            self._url.setText(url)
            self._submit()
            return
        if not self._url.text().strip():
            self._url.setText(_clipboard_link())
        self._url.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._url.selectAll()

    # Form

    def _validate(self) -> None:
        valid = self.url() is not None
        self._add.setEnabled(valid and not self._busy)
        if not self._busy:
            raw = self._url.text().strip()
            bad = bool(raw and not valid)
            self._set_status("Link não reconhecido. Use um link de vídeo do YouTube ou do Vimeo." if bad else HINT,
                             error=bad)

    def _submit(self) -> None:
        url = self.url()
        if self._busy or url is None:
            return
        self._set_busy(True)
        self._set_status("Consultando vídeo…")
        QThreadPool.globalInstance().start(_Probe(url, self._bridge, self._probe))

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._url.setEnabled(not busy)
        self._choice.setEnabled(not busy)
        self._add.setEnabled(not busy and self.url() is not None)

    def _on_done(self, info: VideoInfo) -> None:
        self._set_busy(False)
        self._url.clear()
        self.link_resolved.emit(info, *self.target())

    def _on_failed(self, message: str) -> None:
        self._set_busy(False)
        self._set_status(message, error=True)
        self._url.setFocus(Qt.FocusReason.OtherFocusReason)

    def _set_status(self, message: str, error: bool = False) -> None:
        self._status.setText(message)
        set_prop(self._status, "t", "error" if error else "small-dim")

    # Queue

    def _update_header(self) -> None:
        q = self.queue
        items = q.items
        n = len(items)
        done = sum(1 for i in items if i.is_finished)
        pending, active = q.pending, q.active
        summary = "Nenhum vídeo adicionado"
        if n:
            summary = plural(n, "vídeo", "vídeos")
            if done:
                summary += f" · {plural(done, 'concluído', 'concluídos')}"
        self._summary.setText(summary)
        self._clear.setVisible(done > 0)
        self._primary.setVisible(bool(pending))
        if q.running:
            label, icon_name = "Pausar", "pause"
        elif active:
            label, icon_name = "Retomar", "play"
        else:
            label, icon_name = f"Baixar {plural(len(pending), 'vídeo', 'vídeos')}", "play"
        self._primary.setText(label)
        self._primary.set_icon(icon_name, theme.ACCENT_TEXT)


def _clipboard_link() -> str:
    clipboard = QApplication.clipboard()
    txt = clipboard.text().strip() if clipboard else ""
    return txt if parse_video_url(txt) else ""
