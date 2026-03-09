# VS Code Styled Dark Theme
# Colors:
# Bg: #1e1e1e
# Sidebar/Panel: #252526
# Button (Secondary): #3c3c3c
# Button (Primary): #0e639c (VS Code Blue) -> We keep Green #2E7D32 but softer
# Hover: #2a2d2e
# Border: #454545

DARK_STYLE = """
/* Global Reset */
QMainWindow {
    background-color: #121212; /* Darker background to let panels stand out */
    color: #e0e0e0;
}
QWidget {
    font-family: '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Malgun Gothic', sans-serif;
    font-size: 10pt;
    color: #e0e0e0;
}

/* --- Buttons (macOS / Liquid Glass Style) --- */
QPushButton {
    background-color: rgba(60, 60, 60, 0.4); /* Translucent */
    color: #f0f0f0;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px; /* Softer, rounder */
    padding: 6px 14px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: rgba(80, 80, 80, 0.6);
    border-color: rgba(255, 255, 255, 0.2);
}
QPushButton:pressed {
    background-color: rgba(40, 40, 40, 0.8);
}

/* Primary Button */
QPushButton:checked {
    background-color: rgba(46, 125, 50, 0.8); /* Translucent Green */
    border-color: rgba(76, 175, 80, 0.5);
    color: white;
}
QPushButton#PrimaryButton {
    background-color: rgba(46, 125, 50, 0.7);
    border: 1px solid rgba(76, 175, 80, 0.4);
}
QPushButton#PrimaryButton:hover {
    background-color: rgba(56, 142, 60, 0.9);
}

/* Tonal / Ghost Buttons */
QPushButton#TonalButton {
    background-color: transparent;
    border: 1px solid transparent;
    color: #d0d0d0;
}
QPushButton#TonalButton:hover {
    background-color: rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    color: #ffffff;
}

/* Folder Selection */
QPushButton#SelectFolderBtn {
    background-color: rgba(46, 125, 50, 0.6); 
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 8px;
    text-align: left;
    padding-left: 12px;
    color: #ffffff;
}
QPushButton#SelectFolderBtn:hover {
    background-color: rgba(56, 142, 60, 0.8);
}

/* --- List Widget --- */
QListWidget {
    background-color: transparent; /* Let the glass panel behind it show */
    border: none;
    outline: none;
}
QListWidget::item {
    border-radius: 6px;
    padding: 4px;
    color: #e0e0e0;
}
QListWidget::item:hover {
    background-color: rgba(255, 255, 255, 0.08); /* Soft highlight */
}
QListWidget::item:selected {
    background-color: rgba(76, 175, 80, 0.3); /* Soft Green */
    border: 1px solid rgba(76, 175, 80, 0.6);
    color: #ffffff;
}

/* --- Scrollbar --- */
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: rgba(120, 120, 120, 0.4); /* Translucent handle */
    min-height: 24px;
    border-radius: 6px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: rgba(150, 150, 150, 0.6);
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: none;
    border: none;
    height: 0px;
}

/* --- Sliders --- */
QSlider::groove:horizontal {
    border: none;
    height: 4px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #e0e0e0;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: rgba(76, 175, 80, 0.8);
    border-radius: 2px;
}

/* --- Glass Panel & Overlay --- */
QFrame#glassPanel, QWidget#glassPanel {
    background-color: rgba(30, 30, 32, 0.65); /* Deep translucent */
    border: 1px solid rgba(255, 255, 255, 0.08); /* Frosted edge */
    border-radius: 12px; /* Smooth corners */
}
QRubberBand {
    border: 1px solid rgba(76, 175, 80, 0.8);
    background-color: rgba(76, 175, 80, 0.2);
    border-radius: 2px;
}

QLabel {
    color: #e0e0e0;
}
"""

