from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QMainWindow, QMessageBox, QStackedWidget, QWidget,
)

from recast.core.models import HistoryEntry, Preset, QueueItem
from recast.core.queue import ConversionQueue
from recast.core.storage import HistoryStore, PresetStore, SettingsStore, default_data_dir
from recast.engines.download import VideoInfo, parse_video_url
from recast.ui import icons, platform
from recast.ui.convert_view import ConvertView, QueueView, plural
from recast.ui.download_view import DownloadView
from recast.ui.format_picker import FormatPicker
from recast.ui.history_view import HistoryView
from recast.ui.inspector import Inspector
from recast.ui.overlays import DropOverlay, Toast
from recast.ui.presets_view import PresetsView
from recast.ui.settings_view import SettingsView
from recast.ui.sidebar import VIEWS, Sidebar
from recast.ui.status_bar import StatusBar
from recast.ui.widgets import hbox, vbox


# Toast texts when a queue finishes, keyed by "is the downloads queue":
# (all done, done with failures, saved singular/plural, failed singular/plural).
FINISHED_MESSAGES = {
    False: ("Todas as conversões concluídas", "Conversões concluídas",
            ("arquivo salvo", "arquivos salvos"), ("arquivo falhou", "arquivos falharam")),
    True: ("Todos os downloads concluídos", "Downloads concluídos",
           ("vídeo salvo", "vídeos salvos"), ("download falhou", "downloads falharam")),
}


def dropped_link(mime) -> str | None:
    """A supported video link in dragged data (a browser URL or plain text), if any."""
    for u in mime.urls() if mime.hasUrls() else []:
        if not u.isLocalFile() and (link := parse_video_url(u.toString())):
            return link
    if mime.hasText():
        return parse_video_url(mime.text())
    return None


class MainArea(QWidget):
    """Hosts the views and accepts dropped files (or video links) anywhere over them."""

    files_dropped = Signal(list)
    link_dropped = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.stack = QStackedWidget()
        vbox(self).addWidget(self.stack)
        self.overlay = DropOverlay(self)

    def dragEnterEvent(self, event) -> None:
        mime = event.mimeData()
        if (mime.hasUrls() and any(u.isLocalFile() for u in mime.urls())) or dropped_link(mime):
            event.acceptProposedAction()
            self.overlay.show_over()

    def dragLeaveEvent(self, event) -> None:
        self.overlay.hide()

    def dropEvent(self, event) -> None:
        self.overlay.hide()
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.files_dropped.emit(paths)
        elif link := dropped_link(event.mimeData()):
            event.acceptProposedAction()
            self.link_dropped.emit(link)


class MainWindow(QMainWindow):
    def __init__(self, data_dir: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Recast")
        self.setWindowIcon(icons.app_icon())
        self.resize(1320, 820)
        self.setMinimumSize(1060, 640)

        data_dir = data_dir or default_data_dir()
        self.settings = SettingsStore(data_dir, self)
        self.history = HistoryStore(data_dir, self)
        self.presets = PresetStore(data_dir, self)
        # Files and links run in separate queues, so starting one page never starts the other's items.
        self.queue = ConversionQueue(self.settings, self)
        self.downloads = ConversionQueue(self.settings, self)
        self._view = "convert"

        root = QWidget()
        root.setObjectName("Root")
        col = vbox(root)
        body = hbox()
        self.sidebar = Sidebar()
        self.main = MainArea()
        self.convert_view = ConvertView(self.queue)
        self.download_view = DownloadView(self.downloads)
        self.history_view = HistoryView(self.history)
        self.presets_view = PresetsView(self.presets)
        self.settings_view = SettingsView(self.settings)
        for view in (self.convert_view, self.download_view, self.history_view, self.presets_view,
                     self.settings_view):
            self.main.stack.addWidget(view)
        # Views that list a queue; each keeps its own selection for the inspector.
        self._lists: dict[str, QueueView] = {"convert": self.convert_view, "download": self.download_view}
        self._selection: dict[str, str | None] = dict.fromkeys(self._lists)
        self._order: dict[str, list[str]] = {view: [] for view in self._lists}
        self.inspector = Inspector()
        body.addWidget(self.sidebar)
        body.addWidget(self.main, 1)
        body.addWidget(self.inspector)
        col.addLayout(body, 1)
        self.status = StatusBar(self.queue, self.downloads)
        col.addWidget(self.status)
        self.setCentralWidget(root)
        self.toast = Toast(root)

        self._connect()
        self._shortcuts()
        self.sidebar.set_presets(self.presets.presets)
        self._on_settings()
        for view in self._lists:
            self._on_items_changed(view)

    def _connect(self) -> None:
        self.sidebar.view_selected.connect(self.set_view)
        self.sidebar.preset_clicked.connect(self.apply_preset)
        self.main.files_dropped.connect(self.add_files)
        self.main.link_dropped.connect(self.add_link)
        self.convert_view.browse_requested.connect(self.browse)
        self.convert_view.all_picker_requested.connect(lambda anchor: self.open_picker(anchor, None))
        self.download_view.link_resolved.connect(self.queue_link)
        for view, lv in self._lists.items():
            q = lv.queue
            lv.row_selected.connect(self.select)
            lv.pick_requested.connect(lambda item_id, anchor: self.open_picker(anchor, item_id))
            lv.reveal_requested.connect(self._reveal_item)
            q.items_changed.connect(lambda v=view: self._on_items_changed(v))
            q.item_changed.connect(lambda item_id, v=view: self._on_item_changed(v, item_id))
            q.item_converted.connect(lambda item: self.history.add([HistoryEntry.from_item(item)]))
        self.queue.queue_finished.connect(lambda saved, failed: self._on_finished(saved, failed, downloads=False))
        self.downloads.queue_finished.connect(lambda saved, failed: self._on_finished(saved, failed, downloads=True))
        ins = self.inspector
        ins.options_changed.connect(lambda item_id, values: self._queue_of(item_id).set_options(item_id, **values))
        ins.apply_all_requested.connect(self._apply_all)
        ins.pick_requested.connect(lambda item_id, anchor: self.open_picker(anchor, item_id))
        ins.change_folder_requested.connect(self.choose_folder)
        self.settings_view.change_folder_requested.connect(self.choose_folder)
        self.settings.changed.connect(self._on_settings)
        self.presets.changed.connect(lambda: self.sidebar.set_presets(self.presets.presets))
        self.presets_view.apply_requested.connect(self.apply_preset)
        self.history_view.reveal_requested.connect(platform.reveal)
        self.history_view.missing.connect(lambda name: self.toast.show_message("Arquivo não encontrado", name))

    def _shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self.browse)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=lambda: self.add_link())
        # Queue keys only while focus is in a queue, so the inspector's slider and
        # segmented controls (and the link field) keep their own keys.
        queue_keys = {
            Qt.Key.Key_Delete: self._remove_selected, Qt.Key.Key_Backspace: self._remove_selected,
            Qt.Key.Key_Down: lambda: self._move_selection(1), Qt.Key.Key_Up: lambda: self._move_selection(-1),
        }
        for lv in self._lists.values():
            for key, action in queue_keys.items():
                shortcut = QShortcut(QKeySequence(key), lv._pages, activated=action)
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # Views and selection

    @property
    def _selected(self) -> str | None:
        return self._selection.get(self._view)

    def _queue_of(self, item_id: str | None) -> ConversionQueue:
        return self.downloads if self.downloads.get(item_id) else self.queue

    def set_view(self, view: str) -> None:
        self._view = view
        self.main.stack.setCurrentIndex(VIEWS.index(view))
        self.sidebar.set_view(view)
        self._update_inspector()

    def select(self, item_id: str | None) -> None:
        view = self._view if item_id is None else "download" if self.downloads.get(item_id) else "convert"
        if view not in self._lists:
            return
        self._selection[view] = item_id
        self._lists[view].set_selected(item_id)
        self._update_inspector()

    def selected_item(self) -> QueueItem | None:
        lv = self._lists.get(self._view)
        return lv.queue.get(self._selected) if lv else None

    def _update_inspector(self) -> None:
        lv = self._lists.get(self._view)
        self.inspector.setVisible(bool(lv and lv.queue.items))
        self.inspector.set_item(self.selected_item())

    def _move_selection(self, step: int) -> None:
        lv = self._lists.get(self._view)
        if not lv or not lv.queue.items:
            return
        ids = [i.id for i in lv.queue.items]
        index = ids.index(self._selected) if self._selected in ids else -1
        self.select(ids[max(0, min(len(ids) - 1, index + step))])

    def _remove_selected(self) -> None:
        if (lv := self._lists.get(self._view)) and self._selected:
            lv.queue.remove(self._selected)

    def _on_items_changed(self, view: str) -> None:
        lv = self._lists[view]
        ids = [i.id for i in lv.queue.items]
        selected = self._selection[view]
        if selected and selected not in ids:
            # Like the mockup's remove(): select the next surviving item, else the previous one.
            old = self._order[view]
            idx = old.index(selected) if selected in old else len(old)
            after = [i for i in old[idx + 1:] if i in ids]
            before = [i for i in old[:idx] if i in ids]
            self._selection[view] = (after[:1] or before[-1:] or [None])[0]
        self._order[view] = ids
        lv.set_selected(self._selection[view])
        self.sidebar.set_pending(view, len(lv.queue.pending))
        self._update_inspector()

    def _on_item_changed(self, view: str, item_id: str) -> None:
        self.sidebar.set_pending(view, len(self._lists[view].queue.pending))
        if view == self._view and item_id == self._selected:
            self.inspector.set_item(self.selected_item())

    def _on_settings(self) -> None:
        s = self.settings.settings
        self.status.set_settings(s)
        self.inspector.set_folder(s.folder)

    # Actions

    def browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Escolher arquivos")
        if paths:
            self.add_files([Path(p) for p in paths])

    def add_files(self, paths: list[Path]) -> None:
        added = self.queue.add_paths(paths)
        if not added:
            self.toast.show_message("Nenhum arquivo novo", "Os arquivos já estão na fila")
            return
        self.set_view("convert")
        self.select(added[0].id)
        self.toast.show_message(plural(len(added), "arquivo adicionado", "arquivos adicionados"), "Pronto para converter")

    def add_link(self, url: str = "") -> None:
        """Open the download page; a dropped `url` is looked up right away."""
        self.set_view("download")
        self.download_view.set_link(url)

    def queue_link(self, info: VideoInfo, target: str, target_cat: str) -> None:
        item = self.downloads.add_url(info, target, target_cat)
        if item is None:
            self.toast.show_message("Esse vídeo já está na fila", info.title)
            return
        self.set_view("download")
        self.select(item.id)
        self.downloads.start()
        self.toast.show_message("Download iniciado", f"{info.title} · {target}")

    def open_picker(self, anchor: QWidget, item_id: str | None) -> None:
        queue = self._queue_of(item_id)
        item = queue.get(item_id) if item_id else None
        if item_id and (not item or item.status.value in ("converting", "unsupported")):
            return
        picker = FormatPicker(queue.items, item, self)
        picker.chosen.connect(lambda ext, cat: self._choose(item_id, ext, cat))
        picker.popup_at(anchor)

    def _choose(self, item_id: str | None, ext: str, cat: str) -> None:
        if item_id:
            self._queue_of(item_id).set_target(item_id, ext, cat)
            return
        n = self.queue.set_target_all(ext, cat)
        sub = "Arquivos incompatíveis não foram alterados" if n else "Nenhum arquivo compatível na fila"
        self.toast.show_message(f"{plural(n, 'arquivo definido', 'arquivos definidos')} como {ext}", sub)

    def apply_preset(self, preset: Preset) -> None:
        n = self.queue.apply_preset(preset)
        self.set_view("convert")
        title = (f"“{preset.name}” aplicada a {plural(n, 'arquivo', 'arquivos')}" if n
                 else f"Nenhum arquivo corresponde a “{preset.name}”")
        self.toast.show_message(title, preset.rule)

    def _apply_all(self, item_id: str) -> None:
        queue = self._queue_of(item_id)
        item = queue.get(item_id)
        if not item:
            return
        n = queue.apply_to_category(item)
        self.toast.show_message(f"Configurações aplicadas a {plural(n, 'arquivo', 'arquivos')}",
                                f"{item.target} · {item.opts.preset}")

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta de saída", self.settings.settings.folder)
        if folder:
            self.settings.update(folder=str(Path(folder)))

    def _reveal_item(self, item_id: str) -> None:
        item = self._queue_of(item_id).get(item_id)
        if item and item.out_path and not platform.reveal(item.out_path):
            self.toast.show_message("Arquivo não encontrado", item.out_path.name)

    def _on_finished(self, saved: int, failed: int, downloads: bool) -> None:
        if not self.settings.settings.notify:
            return
        all_done, done, saved_words, failed_words = FINISHED_MESSAGES[downloads]
        folder = platform.display_path(self.settings.settings.folder)
        sub = f"{plural(saved, *saved_words)} em {folder}"
        if failed:
            self.toast.show_message(
                f"{done} com {plural(failed, 'falha', 'falhas')}",
                f"{sub} · {plural(failed, *failed_words)}", ok=False,
            )
        else:
            self.toast.show_message(all_done, sub)
        QApplication.alert(self)

    def closeEvent(self, event) -> None:
        if self.queue.active or self.downloads.active:
            answer = QMessageBox.question(
                self, "Recast", "Há conversões ou downloads em andamento. Cancelar e sair?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.queue.shutdown()
        self.downloads.shutdown()
        super().closeEvent(event)
