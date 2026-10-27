from media_converter.main_window import MainWindow


def test_main_window_title(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "Media Converter"
