"""Dialog that takes a YouTube/Vimeo link, looks the video up and hands a `VideoInfo` to the queue."""

from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit, QWidget

from recast.engines.base import ConversionError
from recast.engines.download import SUPPORTED_SITES, DownloadEngine, VideoInfo, parse_video_url
from recast.ui.widgets import Button, SegmentedControl, set_prop, text, vbox

CHOICES = {"Vídeo · MP4": ("MP4", "video"), "Áudio · MP3": ("MP3", "audio")}


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


class AddLinkDialog(QDialog):
    """`exec()` returns Accepted only after the link was resolved; see `info` and `target()`."""

    def __init__(self, parent: QWidget | None = None, url: str = "", probe=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Adicionar link")
        self.setMinimumWidth(460)
        self.info: VideoInfo | None = None
        self._probe = probe
        self._bridge = _ProbeBridge(self)
        self._bridge.done.connect(self._on_done)
        self._bridge.failed.connect(self._on_failed)
        self._busy = False

        col = vbox(self, (20, 18, 20, 16), 12)
        col.addWidget(text("Adicionar link", "title"))
        col.addWidget(text(f"Cole o link de um vídeo do {' ou '.join(SUPPORTED_SITES)}.", "setting-desc", wrap=True))
        self._url = QLineEdit()
        self._url.setProperty("role", "input")
        self._url.setPlaceholderText("https://www.youtube.com/watch?v=…")
        self._url.setClearButtonEnabled(True)
        col.addWidget(self._url)
        col.addWidget(text("Baixar como", "field"))
        self._choice = SegmentedControl(list(CHOICES), next(iter(CHOICES)), expand=True)
        col.addWidget(self._choice)
        self._status = text("", "small-dim", wrap=True)
        self._status.setMinimumHeight(18)
        col.addWidget(self._status)

        buttons = QDialogButtonBox()
        cancel = Button("Cancelar", "ghost")
        self._add = Button("Adicionar", "primary")
        buttons.addButton(cancel, QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton(self._add, QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)
        col.addWidget(buttons)

        self._url.textChanged.connect(self._validate)
        self._url.returnPressed.connect(self._submit)
        prefill = url or _clipboard_link()
        self._url.setText(prefill)
        self._validate()
        if url:  # dropped/pasted from outside: resolve right away
            self._submit()

    # Public

    def target(self) -> tuple[str, str]:
        return CHOICES[self._choice.current() or next(iter(CHOICES))]

    def url(self) -> str | None:
        return parse_video_url(self._url.text())

    # Internals

    def _validate(self) -> None:
        valid = self.url() is not None
        self._add.setEnabled(valid and not self._busy)
        if not self._busy:
            raw = self._url.text().strip()
            self._set_status("Link não reconhecido. Use um link de vídeo do YouTube ou do Vimeo." if raw and not valid else "",
                             error=bool(raw and not valid))

    def _submit(self) -> None:
        url = self.url()
        if self._busy or url is None:
            return
        self._busy = True
        self._url.setEnabled(False)
        self._choice.setEnabled(False)
        self._add.setEnabled(False)
        self._set_status("Consultando vídeo…")
        QThreadPool.globalInstance().start(_Probe(url, self._bridge, self._probe))

    def _on_done(self, info: object) -> None:
        self.info = info  # type: ignore[assignment]
        self.accept()

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self._url.setEnabled(True)
        self._choice.setEnabled(True)
        self._validate()
        self._set_status(message, error=True)
        self._url.setFocus(Qt.FocusReason.OtherFocusReason)

    def _set_status(self, message: str, error: bool = False) -> None:
        self._status.setText(message)
        set_prop(self._status, "t", "error" if error else "small-dim")

    def reject(self) -> None:
        if self._busy:  # a probe may still finish; make sure it cannot accept a closed dialog
            self._bridge.done.disconnect(self._on_done)
            self._bridge.failed.disconnect(self._on_failed)
        super().reject()


def _clipboard_link() -> str:
    clipboard = QApplication.clipboard()
    txt = clipboard.text().strip() if clipboard else ""
    return txt if parse_video_url(txt) else ""
