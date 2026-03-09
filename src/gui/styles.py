"""Shared application stylesheet."""

DARK_STYLE = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E1E1E, stop:1 #141414);
    color: #e9edf5;
}

QWidget {
    font-family: 'Segoe UI', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
    font-size: 10pt;
    color: #e9edf5;
}

QToolTip {
    background: #111111;
    color: #dce5f2;
    border: 1px solid #333333;
    padding: 6px 8px;
    border-radius: 6px;
}

QPushButton {
    background: rgba(255, 255, 255, 0.08);
    color: #f3f6fb;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 10px;
    padding: 6px 14px;
    font-weight: 600;
}
QPushButton:hover {
    background: rgba(255, 255, 255, 0.14);
    border-color: rgba(255, 255, 255, 0.26);
}
QPushButton:pressed {
    background: rgba(255, 255, 255, 0.05);
}
QPushButton:disabled {
    color: #76839a;
    border-color: rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.04);
}

QPushButton#PrimaryButton {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(46, 204, 113, 0.9),
        stop:1 rgba(39, 174, 96, 0.92)
    );
    border: 1px solid rgba(88, 214, 141, 0.65);
    color: white;
}
QPushButton#PrimaryButton:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(46, 204, 113, 0.98),
        stop:1 rgba(39, 174, 96, 0.98)
    );
}

QPushButton#TonalButton {
    background: transparent;
    border: 1px solid transparent;
    color: #d8e3f4;
}
QPushButton#TonalButton:hover {
    background: rgba(255, 255, 255, 0.08);
    border-color: rgba(255, 255, 255, 0.16);
}

QPushButton#SelectFolderBtn {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(39, 174, 96, 0.92),
        stop:1 rgba(30, 132, 73, 0.92)
    );
    border: 1px solid rgba(88, 214, 141, 0.55);
    border-radius: 11px;
    text-align: left;
    padding-left: 12px;
}
QPushButton#SelectFolderBtn:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(46, 204, 113, 0.95),
        stop:1 rgba(39, 174, 96, 0.95)
    );
}

QFrame#glassPanel, QWidget#glassPanel {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(34, 38, 41, 0.85),
        stop:1 rgba(26, 28, 30, 0.9)
    );
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
}

QListWidget {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    border-radius: 8px;
    padding: 4px;
}
QListWidget::item:hover {
    background: rgba(255, 255, 255, 0.08);
}
QListWidget::item:selected {
    background: rgba(46, 204, 113, 0.24);
    border: 1px solid rgba(46, 204, 113, 0.56);
}

QTreeWidget, QTextEdit, QLineEdit {
    background: rgba(15, 15, 15, 0.42);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
}

QProgressBar {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 7px;
    text-align: center;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #58D68D, stop:1 #2ECC71);
    border-radius: 7px;
}

QSlider::groove:horizontal {
    border: none;
    height: 5px;
    background: rgba(255, 255, 255, 0.14);
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: #2ECC71;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #F0FDF4;
    border: 1px solid #2ECC71;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: rgba(100, 100, 100, 0.38);
    border-radius: 6px;
    min-height: 22px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(150, 150, 150, 0.58);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0px;
}

QSplitter::handle {
    background: rgba(255, 255, 255, 0.08);
}
QSplitter::handle:hover {
    background: rgba(46, 204, 113, 0.45);
}

QRubberBand {
    border: 1px solid rgba(88, 214, 141, 0.9);
    background: rgba(46, 204, 113, 0.25);
}
"""
