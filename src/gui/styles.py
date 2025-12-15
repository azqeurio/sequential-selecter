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
    background-color: #1e1e1e;
    color: #cccccc;
}
QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
    font-size: 10pt;
}

/* --- Buttons (VS Code Style Shape + Green Accent) --- */
/* Default (Tonal/Secondary) - Targets, Lang, Donate */
QPushButton {
    background-color: #3b3b3b;
    color: #ffffff;
    border: 1px solid #3b3b3b;
    border-radius: 4px; /* VS Code Shape */
    padding: 6px 12px;
    font-weight: normal;
    text-align: center;
}
QPushButton:hover {
    background-color: #454545;
    border-color: #454545;
}
QPushButton:pressed {
    background-color: #2D2D2D;
}

/* Primary Button (Green) - Organize */
QPushButton:checked {
    background-color: #2E7D32; /* Green */
    border-color: #2E7D32;
    color: white;
}
QPushButton#PrimaryButton {
    background-color: #2E7D32; /* Green */
    border: 1px solid #2E7D32;
}
QPushButton#PrimaryButton:hover {
    background-color: #388E3C;
}

/* Tonal / Ghost Buttons */
QPushButton#TonalButton {
    background-color: transparent;
    border: 1px solid transparent;
    color: #cccccc;
}
QPushButton#TonalButton:hover {
    background-color: #2a2d2e;
    color: #ffffff;
}

/* Image Folder Button -> Standard VS Code Input look but with Green Accent if requested? 
   User said "Color highlights keep". Originally this was Title Green. 
   Let's make it a Primary Green Button but with text-align left for path visibility.
*/
QPushButton#SelectFolderBtn {
    background-color: #2E7D32; /* Green */
    border: 1px solid #1B5E20;
    border-radius: 4px;
    text-align: left;
    padding-left: 10px;
    color: #ffffff;
}
QPushButton#SelectFolderBtn:hover {
    background-color: #388E3C;
}

/* --- List Widget --- */
QListWidget {
    background-color: #252526;
    border: 1px solid #454545;
    border-radius: 0px;
    outline: none;
}
QListWidget::item {
    border-radius: 3px;
    padding: 4px;
    color: #cccccc;
}
QListWidget::item:hover {
    background-color: #2a2d2e;
}
QListWidget::item:selected {
    background-color: rgba(46, 125, 50, 0.3); /* Green Low Opacity */
    border: 1px solid #4CAF50; /* Green Border */
    color: #ffffff;
}

/* --- Scrollbar --- */
QScrollBar:vertical {
    background: #1e1e1e;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #424242;
    min-height: 20px;
    border-radius: 5px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #4f4f4f;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* --- Sliders --- */
QSlider::groove:horizontal {
    border: none;
    height: 4px;
    background: #3c3c3c;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #cccccc;
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #4CAF50; /* Green */
    border-radius: 2px;
}

/* --- Panel & Overlay --- */
QFrame#glassPanel {
    background-color: #252526;
    border: 1px solid #454545;
    border-radius: 6px;
}
QRubberBand {
    border: 1px solid #4CAF50; /* Green */
    background-color: rgba(76, 175, 80, 0.2);
}

QLabel {
    color: #cccccc;
}
"""

