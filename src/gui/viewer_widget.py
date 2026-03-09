from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QSizePolicy, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QSize, QPropertyAnimation, QEasingCurve, QTimer, QEvent
from PySide6.QtGui import QColor, QPalette, QIcon, QAction, QPixmap
from .widgets import GPUImageWidget
from pathlib import Path

class RatingWidget(QWidget):
    rating_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(2)
        self.stars = []
        self.current_rating = 0
        
        for i in range(1, 6):
            lbl = QLabel("★")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedSize(36, 36)
            self.stars.append(lbl)
            self.layout.addWidget(lbl)
            
        self._update_ui(0)
        
    def _update_ui(self, rating):
        for i, lbl in enumerate(self.stars):
            if i < rating:
                lbl.setStyleSheet("color: #FFD700; font-size: 26pt; background: transparent; font-family: 'Segoe UI Symbol', 'Apple Color Emoji', 'Arial'; padding-bottom: 4px;")
            else:
                lbl.setStyleSheet("color: rgba(255,255,255,0.2); font-size: 26pt; background: transparent; font-family: 'Segoe UI Symbol', 'Apple Color Emoji', 'Arial'; padding-bottom: 4px;")
                
    def set_rating(self, rating):
        self.current_rating = rating
        self._update_ui(rating)

    def mousePressEvent(self, event):
        self._handle_mouse(event.position().toPoint(), is_press=True)
        
    def mouseMoveEvent(self, event):
        self._handle_mouse(event.position().toPoint(), is_press=False)
        
    def _handle_mouse(self, pos, is_press):
        new_rating = 0
        for i, lbl in enumerate(self.stars):
            if lbl.geometry().contains(pos):
                new_rating = i + 1
                break
                
        if new_rating > 0:
            if is_press and new_rating == self.current_rating:
                new_rating = 0 # Toggle off if clicking the exact same rating again
                
            if new_rating != self.current_rating:
                self.current_rating = new_rating
                self.rating_changed.emit(new_rating)
                self._update_ui(new_rating)

class FullViewerWidget(QWidget):
    request_next = Signal()
    request_prev = Signal()
    request_close = Signal()
    request_open_folder = Signal()
    rating_changed = Signal(int) # 1-5

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #0A0A0C;")
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.current_path: Path | None = None
        
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Image Widget
        self.image_widget = GPUImageWidget(self)
        self.image_widget.keyPressed.connect(self.keyPressEvent) # Forward keys
        self.layout.addWidget(self.image_widget)
        
        # State tracking for pan/zoom preservation
        self._saved_view_state = None
        
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
        # Top Bar
        self.top_bar = QFrame(self)
        self.top_bar.setStyleSheet("background-color: rgba(22, 22, 24, 0.75); border-bottom: 1px solid rgba(255,255,255,0.08); border-radius: 0px;")
        self.top_bar.setFixedHeight(50)
        
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)
        top_layout.setSpacing(15)
        
        # File Name
        self.lbl_filename = QLabel("")
        self.lbl_filename.setStyleSheet("color: #f0f0f0; font-size: 14pt; font-weight: bold;")
        top_layout.addWidget(self.lbl_filename)
        
        top_layout.addSpacing(20)
        
        # Open Folder Button
        self.btn_open = QPushButton("Open Folder")
        self.btn_open.setFixedHeight(32)
        self.btn_open.setStyleSheet("""
            QPushButton {
                background: rgba(46, 204, 113, 0.15); color: #2ECC71; font-size: 10pt; border: 1px solid rgba(46, 204, 113, 0.3); border-radius: 6px; padding: 4px 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(46, 204, 113, 0.3); color: white; }
        """)
        self.btn_open.clicked.connect(self.request_open_folder.emit)
        top_layout.addWidget(self.btn_open)

        self.btn_close = QPushButton("Exit Viewer")
        self.btn_close.setFixedHeight(32)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: rgba(200, 50, 50, 0.4); color: #f0f0f0; font-size: 10pt; border: 1px solid rgba(255,100,100,0.2); border-radius: 6px; padding: 4px 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(220, 60, 60, 0.6); color: #ffffff; }
        """)
        self.btn_close.clicked.connect(self.request_close.emit)
        top_layout.addWidget(self.btn_close)
        
        top_layout.addStretch() 
        
        # Image Index Counter
        self.lbl_counter = QLabel("")
        self.lbl_counter.setStyleSheet("color: #cccccc; font-size: 12pt;")
        top_layout.addWidget(self.lbl_counter)
        
        top_layout.addSpacing(10)

        # Custom Rating Stars Widget
        self.rating_widget = RatingWidget()
        self.rating_widget.rating_changed.connect(self.set_rating)
        top_layout.addWidget(self.rating_widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Position top bar
        self.top_bar.setGeometry(0, 0, self.width(), 50)
        self.top_bar.raise_()

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    def show_controls(self):
        self.top_bar.show()

    def hide_controls(self):
        pass

    def clear_view(self):
        self.current_path = None
        self.lbl_filename.setText("")
        self.lbl_counter.setText("")
        self.image_widget.set_pixmap(QPixmap())
        self.rating_widget.set_rating(0)
        self._saved_view_state = None

    def load_image(self, path: Path, pixmap: QPixmap, current_rating: int = 0, index_str: str = ""):
        # Save state if we are already viewing something
        if self.current_path is not None:
            self._saved_view_state = self.image_widget.get_view_state()
            
        self.current_path = path
        self.lbl_filename.setText(path.name)
        self.lbl_counter.setText(index_str)
        self.image_widget.set_pixmap(pixmap)
        
        # Restore state if available
        if self._saved_view_state:
            self.image_widget.restore_view_state(self._saved_view_state)
            
        self.rating_widget.set_rating(current_rating)
        self.setFocus() # Ensure we get keyboard events
        self.image_widget.setFocus() # Focus the view too

    def set_rating(self, rating):
        self.rating_changed.emit(rating)
        self.rating_widget.set_rating(rating)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Left:
            self.request_prev.emit()
            event.accept()
        elif key == Qt.Key_Right:
            self.request_next.emit()
            event.accept()
        elif key == Qt.Key_Escape:
            self.request_close.emit()
            event.accept()
        elif key == Qt.Key_1: 
            self.set_rating(1)
            event.accept()
        elif key == Qt.Key_2: 
            self.set_rating(2)
            event.accept()
        elif key == Qt.Key_3: 
            self.set_rating(3)
            event.accept()
        elif key == Qt.Key_4: 
            self.set_rating(4)
            event.accept()
        elif key == Qt.Key_5: 
            self.set_rating(5)
            event.accept()
        elif key == Qt.Key_0:
            self.set_rating(0)
            event.accept()
        else:
            super().keyPressEvent(event)
