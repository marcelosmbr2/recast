from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QPushButton

from recast.core.models import Status
from recast.core.presets import BUILTIN_PRESETS
from recast.ui import theme
from recast.ui.format_picker import FormatPicker
from recast.ui.history_view import HistoryRow
from recast.ui.main_window import MainWindow
from recast.ui.sidebar import VIEWS
from recast.ui.widgets import SegmentedControl


@pytest.fixture
def window(qtbot, tmp_path) -> MainWindow:
    QApplication.instance().setStyleSheet(theme.STYLESHEET)
    w = MainWindow(tmp_path / "data")
    w.settings.update(folder=str(tmp_path / "out"))
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture
def files(tmp_path) -> list[Path]:
    src = tmp_path / "in"
    src.mkdir()
    paths = []
    for name in ("a.png", "b.png", "c.jpg"):
        p = src / name
        Image.new("RGB", (64, 48), "orange").save(p)
        paths.append(p)
    return paths


def tile(picker: FormatPicker, ext: str) -> QPushButton:
    for b in picker.findChildren(QPushButton):
        if b.property("role") == "tile" and any(lbl.text() == ext for lbl in b.findChildren(type(picker._heading))):
            return b
    raise LookupError(ext)


def test_empty_state_then_rows(window, files):
    cv = window.convert_view
    assert cv._pages.currentIndex() == 0 and not window.inspector.isVisible()
    window.add_files(files)
    assert cv._pages.currentIndex() == 1 and len(cv._rows) == 3
    assert window.inspector.isVisible()
    assert window.inspector._name.text() == "a.png"
    assert window.toast._title.text() == "3 arquivos adicionados"
    assert window.sidebar._count.text() == "3"


def test_click_row_selects_and_keyboard_navigation(window, files, qtbot):
    window.add_files(files)
    items = list(window.queue.items)
    qtbot.mouseClick(window.convert_view._rows[items[2].id], Qt.MouseButton.LeftButton)
    assert window.inspector._name.text() == "c.jpg"
    window._move_selection(-1)
    assert window._selected == items[1].id
    window._remove_selected()
    assert [i.name for i in window.queue.items] == ["a.png", "c.jpg"]
    assert window._selected == items[2].id  # the next item takes the removed one's place


def test_picker_sets_target_for_one_item(window, files):
    window.add_files(files)
    item = window.queue.items[0]
    window.open_picker(window.convert_view._rows[item.id]._pick, item.id)
    picker = window.findChild(FormatPicker)
    assert tile(picker, "PNG").property("available") is False  # same as the source format
    tile(picker, "JPG").click()
    assert item.target == "JPG"
    assert window.convert_view._rows[item.id]._pick_label.text() == "JPG"


def test_picker_search_spans_categories(window, files):
    window.add_files(files)
    item = window.queue.items[0]
    window.open_picker(window.inspector._controls["pick"], item.id)
    picker = window.findChild(FormatPicker)
    picker._search.setText("pdf")
    assert picker._heading.text() == "Resultados"
    tile(picker, "PDF").click()
    assert (item.target, item.target_cat) == ("PDF", "document")


def test_all_picker_and_presets(window, files):
    window.add_files(files)
    window.open_picker(window.convert_view._all, None)
    tile(window.findChild(FormatPicker), "PNG").click()
    assert window.toast._title.text() == "1 arquivo definido como PNG"  # only c.jpg; PNGs keep their target
    web = next(p for p in BUILTIN_PRESETS if p.id == "p2")
    window.apply_preset(web)
    assert all(i.target == "WEBP" for i in window.queue.items)
    assert window.toast._title.text() == "“Imagens para web” aplicada a 3 arquivos"


def test_inspector_options_update_item(window, files):
    window.add_files(files)
    item = window.queue.items[0]
    resize = window.inspector._controls["resize"]
    assert isinstance(resize, SegmentedControl)
    before = window.inspector._est.text()
    resize._buttons["50%"].click()
    assert item.opts.resize == "50%"
    assert window.inspector._est.text() != before
    window.inspector._controls["quality_seg"]._buttons["Menor"].click()
    assert (item.opts.quality, item.opts.preset) == (55, "Menor")
    assert window.inspector._controls["quality_slider"].value() == 55


def test_view_switching(window, files):
    window.add_files(files)
    for view in VIEWS:
        window.sidebar._nav[view].click()
        assert window.main.stack.currentIndex() == VIEWS.index(view)
        assert window.inspector.isVisible() == (view == "convert")


def test_settings_view_persists(window, tmp_path):
    view = window.settings_view
    view._parallel._buttons["4"].click()
    view._toggles["notify"].click()
    assert window.settings.settings.parallel == 4 and not window.settings.settings.notify
    assert "4 simultâneas" in window.status._threads.text()
    reloaded = MainWindow(tmp_path / "data")
    assert reloaded.settings.settings.parallel == 4
    reloaded.deleteLater()


def test_end_to_end_conversion_records_history(window, files, qtbot, tmp_path):
    window.add_files(files)
    with qtbot.waitSignal(window.queue.queue_finished, timeout=20000):
        window.convert_view._primary.click()
    assert all(i.status is Status.DONE for i in window.queue.items)
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a.webp", "b.webp", "c.webp"]
    assert window.toast._title.text() == "Todas as conversões concluídas"
    assert len(window.history.entries) == 3
    assert window.convert_view._primary.text() == "Converter" and not window.convert_view._primary.isEnabled()
    window.convert_view._clear.click()
    assert window.queue.items == [] and window.convert_view._pages.currentIndex() == 0
    window.set_view("history")
    rows = [window.history_view._list.itemAt(i).widget() for i in range(window.history_view._list.count())]
    assert sum(isinstance(r, HistoryRow) for r in rows) == 3
    reloaded = MainWindow(tmp_path / "data")
    assert sorted(e.name for e in reloaded.history.entries) == ["a.png", "b.png", "c.jpg"]
    reloaded.deleteLater()
