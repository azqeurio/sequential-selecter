from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPalette, QIcon, QAction, QPixmap
from .widgets import GPUImageWidget
from pathlib import Path

class FullViewerWidget(QWidget):
    request_next = Signal()
    request_prev = Signal()
    request_close = Signal()
    request_open_folder = Signal()
    rating_changed = Signal(int) # 1-5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #000000;")
        
        self.current_path: Path | None = None
        
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Image Widget
        self.image_widget = GPUImageWidget(self)
        self.layout.addWidget(self.image_widget)
        
        # --- Overlays ---
        self._setup_overlays()
        
        # Mouse Tracking for Auto-Hide Controls
        self.setMouseTracking(True)
        # Mouse Tracking for Auto-Hide Controls (Disabled based on feedback)
        self.setMouseTracking(True)
        self.image_widget.setMouseTracking(True)
        
        # self.hide_timer = QTimer(self)
        # self.hide_timer.setInterval(2500)
        # self.hide_timer.timeout.connect(self.hide_controls)
        # self.hide_timer.start() 
        # User requested constant visibility.


    def _setup_overlays(self):
        # Top Bar (Filename, Close)
        self.top_bar = QFrame(self)
        self.top_bar.setStyleSheet("background-color: rgba(0, 0, 0, 150); border-bottom: 1px solid #444;")
        self.top_bar.setFixedHeight(50)
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)
        
        self.lbl_filename = QLabel("")
        self.lbl_filename.setStyleSheet("color: white; font-size: 14pt; font-weight: bold;")
        top_layout.addWidget(self.lbl_filename)
        
        # Open Folder Button
        self.btn_open = QPushButton("Open Folder")
        self.btn_open.setFixedHeight(40)
        self.btn_open.setStyleSheet("""
            QPushButton {
                background: transparent; color: #CCCCCC; font-size: 11pt; border: 1px solid #555; border-radius: 4px; padding: 5px 10px;
            }
            QPushButton:hover { background-color: #333; color: white; border-color: #888; }
        """)
        self.btn_open.clicked.connect(self.request_open_folder.emit)
        top_layout.addWidget(self.btn_open)

        top_layout.addStretch()
        
        self.btn_close = QPushButton("Exit Viewer") # Clearer Text
        self.btn_close.setFixedHeight(40)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: transparent; color: #CCCCCC; font-size: 11pt; border: none; font-weight: bold;
            }
            QPushButton:hover { color: #FF5555; }
        """)
        self.btn_close.clicked.connect(self.request_close.emit)
        top_layout.addWidget(self.btn_close)

        # Bottom Bar (Navigation, Rating)
        self.bottom_bar = QFrame(self)
        self.bottom_bar.setStyleSheet("background-color: rgba(0, 0, 0, 150); border-top: 1px solid #444;")
        self.bottom_bar.setFixedHeight(80)
        bot_layout = QHBoxLayout(self.bottom_bar)
        bot_layout.setContentsMargins(20, 0, 20, 0)
        
        bot_layout.addStretch()

        # Rating Stars
        self.star_buttons = []
        star_container = QWidget()
        star_layout = QHBoxLayout(star_container)
        for i in range(1, 6):
            btn = QPushButton("★")
            btn.setCheckable(True)
            btn.setFixedSize(50, 50)
            btn.setStyleSheet(self._get_star_style(False))
            btn.clicked.connect(lambda checked, r=i: self.set_rating(r))
            self.star_buttons.append(btn)
            star_layout.addWidget(btn)
        
        bot_layout.addWidget(star_container)
        bot_layout.addStretch()

        bot_layout.addStretch()



    def _get_star_style(self, active):
        if active:
            return "color: #FFD700; font-size: 24pt; background: transparent; border: none;"
        else:
            return "color: #555555; font-size: 24pt; background: transparent; border: none;"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Reposition Overlays
        self.top_bar.setGeometry(0, 0, self.width(), 50)
        self.bottom_bar.setGeometry(0, self.height() - 80, self.width(), 80)
        # Ensure they are on top
        self.top_bar.raise_()
        self.bottom_bar.raise_()

    def mouseMoveEvent(self, event):
        # self.show_controls()
        super().mouseMoveEvent(event)

    def show_controls(self):
        self.top_bar.show()
        self.bottom_bar.show()
        # self.hide_timer.start() # Restart timer

    def hide_controls(self):
        pass
        # Optional: Add animation for smooth fade out
        # self.top_bar.hide()
        # self.bottom_bar.hide()

    def load_image(self, path: Path, pixmap: QPixmap, current_rating: int = 0):
        self.current_path = path
        self.lbl_filename.setText(path.name)
        self.image_widget.set_pixmap(pixmap)
        self._update_star_ui(current_rating)
        self.setFocus() # Ensure we get keyboard events

    def set_rating(self, rating):
        self.rating_changed.emit(rating)
        self._update_star_ui(rating)

    def _update_star_ui(self, rating):
        for i, btn in enumerate(self.star_buttons):
            # Index 0 is 1 star.
            if i < rating:
                btn.setStyleSheet(self._get_star_style(True))
            else:
                btn.setStyleSheet(self._get_star_style(False))

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Left:
            self.request_prev.emit()
        elif key == Qt.Key_Right:
            self.request_next.emit()
        elif key == Qt.Key_Escape:
            self.request_close.emit()
        elif key == Qt.Key_1: self.set_rating(1)
        elif key == Qt.Key_2: self.set_rating(2)
        elif key == Qt.Key_3: self.set_rating(3)
        elif key == Qt.Key_4: self.set_rating(4)
        elif key == Qt.Key_5: self.set_rating(5)
        else:
            super().keyPressEvent(event)
