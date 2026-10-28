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
from recast.ui import icons, platform
from recast.ui.convert_view import ConvertView, plural
from recast.ui.format_picker import FormatPicker
from recast.ui.history_view import HistoryView
from recast.ui.inspector import Inspector
from recast.ui.overlays import DropOverlay, Toast
from recast.ui.presets_view import PresetsView
from recast.ui.settings_view import SettingsView
from recast.ui.sidebar import VIEWS, Sidebar
from recast.ui.status_bar import StatusBar
from recast.ui.widgets import hbox, vbox


class MainArea(QWidget):
    """Hosts the views and accepts dropped files anywhere over them."""

    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.stack = QStackedWidget()
        vbox(self).addWidget(self.stack)
        self.overlay = DropOverlay(self)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls() and any(u.isLocalFile() for u in event.mimeData().urls()):
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
        self.queue = ConversionQueue(self.settings, self)
        self._selected: str | None = None
        self._order: list[str] = []
        self._view = "convert"

        root = QWidget()
        root.setObjectName("Root")
        col = vbox(root)
        body = hbox()
        self.sidebar = Sidebar()
        self.main = MainArea()
        self.convert_view = ConvertView(self.queue)
        self.history_view = HistoryView(self.history)
        self.presets_view = PresetsView(self.presets)
        self.settings_view = SettingsView(self.settings)
        for view in (self.convert_view, self.history_view, self.presets_view, self.settings_view):
            self.main.stack.addWidget(view)
        self.inspector = Inspector()
        body.addWidget(self.sidebar)
        body.addWidget(self.main, 1)
        body.addWidget(self.inspector)
        col.addLayout(body, 1)
        self.status = StatusBar(self.queue)
        col.addWidget(self.status)
        self.setCentralWidget(root)
        self.toast = Toast(root)

        self._connect()
        self._shortcuts()
        self.sidebar.set_presets(self.presets.presets)
        self._on_settings()
        self._on_items_changed()

    def _connect(self) -> None:
        q = self.queue
        self.sidebar.view_selected.connect(self.set_view)
        self.sidebar.preset_clicked.connect(self.apply_preset)
        self.main.files_dropped.connect(self.add_files)
        cv = self.convert_view
        cv.browse_requested.connect(self.browse)
        cv.all_picker_requested.connect(lambda anchor: self.open_picker(anchor, None))
        cv.row_selected.connect(self.select)
        cv.pick_requested.connect(lambda item_id, anchor: self.open_picker(anchor, item_id))
        cv.reveal_requested.connect(self._reveal_item)
        q.items_changed.connect(self._on_items_changed)
        q.item_changed.connect(self._on_item_changed)
        q.item_converted.connect(lambda item: self.history.add([HistoryEntry.from_item(item)]))
        q.queue_finished.connect(self._on_finished)
        ins = self.inspector
        ins.options_changed.connect(lambda item_id, values: q.set_options(item_id, **values))
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
        # Queue keys only while focus is in the queue, so the inspector's slider and
        # segmented controls keep their own arrow keys.
        queue_keys = {
            Qt.Key.Key_Delete: self._remove_selected, Qt.Key.Key_Backspace: self._remove_selected,
            Qt.Key.Key_Down: lambda: self._move_selection(1), Qt.Key.Key_Up: lambda: self._move_selection(-1),
        }
        for key, action in queue_keys.items():
            shortcut = QShortcut(QKeySequence(key), self.convert_view, activated=action)
            shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    # Views and selection

    def set_view(self, view: str) -> None:
        self._view = view
        self.main.stack.setCurrentIndex(VIEWS.index(view))
        self.sidebar.set_view(view)
        self._update_inspector()

    def select(self, item_id: str | None) -> None:
        self._selected = item_id
        self.convert_view.set_selected(item_id)
        self._update_inspector()

    def selected_item(self) -> QueueItem | None:
        return self.queue.get(self._selected)

    def _update_inspector(self) -> None:
        self.inspector.setVisible(self._view == "convert" and bool(self.queue.items))
        self.inspector.set_item(self.selected_item())

    def _move_selection(self, step: int) -> None:
        items = self.queue.items
        if self._view != "convert" or not items:
            return
        ids = [i.id for i in items]
        index = ids.index(self._selected) if self._selected in ids else -1
        self.select(ids[max(0, min(len(ids) - 1, index + step))])

    def _remove_selected(self) -> None:
        if self._view == "convert" and self._selected:
            self.queue.remove(self._selected)

    def _on_items_changed(self) -> None:
        ids = [i.id for i in self.queue.items]
        if self._selected and self._selected not in ids:
            # Like the mockup's remove(): select the next surviving item, else the previous one.
            old = self._order
            idx = old.index(self._selected) if self._selected in old else len(old)
            after = [i for i in old[idx + 1:] if i in ids]
            before = [i for i in old[:idx] if i in ids]
            self._selected = (after[:1] or before[-1:] or [None])[0]
        self._order = ids
        self.convert_view.set_selected(self._selected)
        self.sidebar.set_pending(len(self.queue.pending))
        self._update_inspector()

    def _on_item_changed(self, item_id: str) -> None:
        self.sidebar.set_pending(len(self.queue.pending))
        if item_id == self._selected:
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

    def open_picker(self, anchor: QWidget, item_id: str | None) -> None:
        item = self.queue.get(item_id) if item_id else None
        if item_id and (not item or item.status.value in ("converting", "unsupported")):
            return
        picker = FormatPicker(self.queue.items, item, self)
        picker.chosen.connect(lambda ext, cat: self._choose(item_id, ext, cat))
        picker.popup_at(anchor)

    def _choose(self, item_id: str | None, ext: str, cat: str) -> None:
        if item_id:
            self.queue.set_target(item_id, ext, cat)
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
        item = self.queue.get(item_id)
        if not item:
            return
        n = self.queue.apply_to_category(item)
        self.toast.show_message(f"Configurações aplicadas a {plural(n, 'arquivo', 'arquivos')}",
                                f"{item.target} · {item.opts.preset}")

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pasta de saída", self.settings.settings.folder)
        if folder:
            self.settings.update(folder=str(Path(folder)))

    def _reveal_item(self, item_id: str) -> None:
        item = self.queue.get(item_id)
        if item and item.out_path and not platform.reveal(item.out_path):
            self.toast.show_message("Arquivo não encontrado", item.out_path.name)

    def _on_finished(self, saved: int, failed: int) -> None:
        if not self.settings.settings.notify:
            return
        folder = platform.display_path(self.settings.settings.folder)
        sub = f"{plural(saved, 'arquivo salvo', 'arquivos salvos')} em {folder}"
        if failed:
            self.toast.show_message(
                f"Conversões concluídas com {plural(failed, 'falha', 'falhas')}",
                f"{sub} · {plural(failed, 'arquivo falhou', 'arquivos falharam')}", ok=False,
            )
        else:
            self.toast.show_message("Todas as conversões concluídas", sub)
        QApplication.alert(self)

    def closeEvent(self, event) -> None:
        if self.queue.active:
            answer = QMessageBox.question(
                self, "Recast", "Há conversões em andamento. Cancelar e sair?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.queue.shutdown()
        super().closeEvent(event)

