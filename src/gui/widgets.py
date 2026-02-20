from pathlib import Path

from PySide6.QtCore import (
    Qt, QSize, QThread, Signal, QObject, QRect, QPoint, QTimer
)
from PySide6.QtGui import (
    QPixmap, QDrag, QPainter, QColor, QPen, QTransform
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem, QScrollArea, QApplication, QStyle, QRubberBand,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QAbstractItemView
)
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from ..core.image_loader import load_pil_image
from .utils import pil_to_qimage

# ------------------------------------------------------------
# 썸네일 생성 워커
# ------------------------------------------------------------
# ------------------------------------------------------------
# 썸네일 생성 워커 (Deprecated - Using ThreadPool in MainWindow)
# ------------------------------------------------------------
# (Removed unused ThumbnailWorker class)


# ------------------------------------------------------------
# 썸네일을 표시하는 커스텀 위젯
# ------------------------------------------------------------
class ThumbnailWidget(QWidget):
    def __init__(self, file_name: str, thumb_size: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.thumb_size = thumb_size
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0) # Reduced from 4 to 0 to bring text closer

        # Image Label
        self.image_label = QLabel()
        self.image_label.setFixedSize(thumb_size, thumb_size)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent;")
        self.image_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.image_label)

        # Name Label
        self.name_label = QLabel(file_name)
        self.name_label.setAlignment(Qt.AlignCenter)
        self.name_label.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        self.name_label.setWordWrap(False)
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.name_label)
        
        # Star Rating Label
        self.rating_label = QLabel("")
        self.rating_label.setAlignment(Qt.AlignCenter)
        self.rating_label.setStyleSheet("color: #FFD700; font-size: 14pt; font-weight: bold;")
        self.rating_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # self.rating_label.hide() # Hide until rated
        layout.addWidget(self.rating_label)

        self.is_paired = False

    def set_rating(self, rating: int):
        if rating > 0:
            stars = "★" * rating
            self.rating_label.setText(stars)
            self.rating_label.show()
        else:
            self.rating_label.setText("")
            self.rating_label.hide()

    def set_paired(self, paired: bool):
        self.is_paired = paired
        self._update_style()

    def _update_style(self):
        if self.is_paired:
            # Green line at the bottom of the name label
            self.name_label.setStyleSheet("color: #E0E0E0; font-size: 9pt; border-bottom: 3px solid #4CAF50; padding-bottom: 2px;")
        else:
            self.name_label.setStyleSheet("color: #E0E0E0; font-size: 9pt; border-bottom: none; padding-bottom: 2px;")

    def set_pixmap(self, pixmap: QPixmap):
        if pixmap is not None and not pixmap.isNull():
            self._current_pixmap = pixmap # Store original/current source if possible? 
            # Storing full res pixmap for every item might be heavy if we had it?
            # Actually set_pixmap receives the processed/loaded pixmap.
            # If we store it, we can rescale from it without quality loss relative to "loaded" quality.
            
            # Use SmoothTransformation for high quality
            scale_mode = Qt.SmoothTransformation
            if self.thumb_size < 100: scale_mode = Qt.FastTransformation
            
            self.image_label.setPixmap(pixmap.scaled(
                self.thumb_size,
                self.thumb_size,
                Qt.KeepAspectRatio,
                scale_mode
            ))
            
    def update_thumb_size(self, size: int):
        self.thumb_size = size
        self.image_label.setFixedSize(size, size)
        
        # Rescale current content if available to prevent "Small Image in Big Box"
        if self.image_label.pixmap() and not self.image_label.pixmap().isNull():
            # We rescale the *currently displayed* pixmap. 
            # Note: This might cause blurriness if upscaling significantly, 
            # but it maintains layout until the high-res reload kicks in.
            # Ideally we'd store the source pixmap, but we can just use the label's pixmap for now.
            # Wait, label.pixmap() returns the scaled version.
            # If we scale up from that, it gets blurry. That's fine for transition.
            
            current = self.image_label.pixmap()
            self.image_label.setPixmap(current.scaled(
                size,
                size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            ))


# ------------------------------------------------------------
# 드롭용 라벨
# ------------------------------------------------------------
class DropLabel(QLabel):
    def __init__(self, text: str, main_window, target_index: int, parent=None):
        super().__init__(text, parent)
        self.main_window = main_window
        self.target_index = target_index
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            """
            QLabel {
                border: 2px dashed #666666;
                border-radius: 6px;
                padding: 8px;
                color: #E0E0E0;
                background-color: #3A3A3A;
            }
            QLabel:hover {
                background-color: #444444;
            }
            """
        )

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        self.main_window.move_selected_to_target(self.target_index)
        event.acceptProposedAction()


# ------------------------------------------------------------
# 개선된 리스트 위젯 (sqs.py 기반)
# ------------------------------------------------------------
class ImageListWidget(QListWidget):
    clicked_with_modifiers = Signal(QListWidgetItem, Qt.KeyboardModifiers)
    thumbSizeChanged = Signal(int)
    doubleClickedLeft = Signal(QListWidgetItem)
    doubleClickedRight = Signal(QListWidgetItem)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumb_size = 300
        self._grid_padding_w = 20
        self._grid_padding_h = 50
        self._drag_start_pos: QPoint | None = None
        self._rubber_band: QRubberBand | None = None
        self._rubber_start_pos: QPoint | None = None
        
        # Optimize Scrolling (User Request: Scroll was too jumpy)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setUniformItemSizes(True) # Better performance for fixed size grids

        # Resize Throttling
        self._target_thumb_size = self._thumb_size
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(100) # 100ms delay
        self._resize_timer.timeout.connect(self._apply_delayed_resize)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if hasattr(event, 'position'):
                pos = event.position().toPoint()
            else:
                pos = QPoint(event.x(), event.y())
            
            item = self.itemAt(pos)
            
            # Logic Separation:
            # Item Clicked -> Potential Drag (No RubberBand)
            # Empty Space -> Potential RubberBand (No Drag)
            if item is not None:
                self._drag_start_pos = pos
                self._rubber_start_pos = None
            else:
                self._drag_start_pos = None
                self._rubber_start_pos = pos
                # Optional: Clear selection on background click if control not pressed
                if not (event.modifiers() & Qt.ControlModifier):
                    self.clearSelection()

        if hasattr(event, 'position'):
            pos_for_mod = event.position().toPoint()
        else:
            pos_for_mod = QPoint(event.x(), event.y())

        item = self.itemAt(pos_for_mod)
        if item is not None:
            self.clicked_with_modifiers.emit(item, event.modifiers())
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            count = self.count()
            if count == 0: return
            current = self.currentRow()
            if current < 0: current = 0
            
            try:
                grid_w = self.gridSize().width()
            except Exception:
                grid_w = self._thumb_size + self._grid_padding_w
            
            viewport_width = self.viewport().width()
            columns = max(1, viewport_width // grid_w)
            new_index = current
            
            if key == Qt.Key_Left: new_index = max(0, current - 1)
            elif key == Qt.Key_Right: new_index = min(count - 1, current + 1)
            elif key == Qt.Key_Up: new_index = max(0, current - columns)
            elif key == Qt.Key_Down: new_index = min(count - 1, current + columns)
            
            if new_index != current:
                item = self.item(new_index)
                if item:
                    self.setCurrentRow(new_index)
                    self.clearSelection()
                    item.setSelected(True)
                    self.clicked_with_modifiers.emit(item, Qt.NoModifier)
                self.scrollToItem(self.item(new_index))
            return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            current = self.currentRow()
            if current >= 0:
                item = self.item(current)
                if item:
                    self.clicked_with_modifiers.emit(item, event.modifiers())
            return

        # Let parent handle numbers 1, 2
        if key in (Qt.Key_1, Qt.Key_2):
            event.ignore()
            return

        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        current_pos = event.position().toPoint() if hasattr(event, 'position') else QPoint(event.x(), event.y())

        # Drag start logic
        if self._drag_start_pos is not None:
            # Increase threshold to prevent accidental drags (User Request)
            threshold = max(QApplication.startDragDistance(), 20) 
            if (current_pos - self._drag_start_pos).manhattanLength() >= threshold:
                start_item = self.itemAt(self._drag_start_pos)
                if start_item is not None and start_item.isSelected():
                    if self._rubber_band is not None:
                        self._rubber_band.hide()
                        self._rubber_band = None
                    self.startDrag(Qt.MoveAction)
                    self._drag_start_pos = None
                    return

        # Rubber band logic
        if self._rubber_start_pos is not None:
            if self._rubber_band is None:
                self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
                self._rubber_band.setStyleSheet("border: 2px dashed #4CAF50; background-color: rgba(76, 175, 80, 80);")
                self._rubber_band.show()
                self._rubber_band.raise_()
            
            rect = QRect(self._rubber_start_pos, current_pos).normalized()
            self._rubber_band.setGeometry(rect)
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = None
            if self._rubber_band is not None and self._rubber_start_pos is not None:
                selection_rect = self._rubber_band.geometry()
                self._rubber_band.hide()
                self._rubber_band.deleteLater()
                self._rubber_band = None

                modifiers = event.modifiers()
                if not (modifiers & Qt.ControlModifier):
                    self.clearSelection()

                for i in range(self.count()):
                    item = self.item(i)
                    if selection_rect.intersects(self.visualItemRect(item)):
                        item.setSelected(True)
                
                self._rubber_start_pos = None
                return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta_y = event.angleDelta().y()
            if delta_y == 0: return

            factor = 1.1 if delta_y > 0 else 0.9
            new_size = int(self._target_thumb_size * factor)
            new_size = max(80, min(5000, new_size))
            
            self._target_thumb_size = new_size
            
            # Update Grid Size immediately for responsiveness (lightweight)
            grid_w = new_size + self._grid_padding_w
            grid_h = new_size + self._grid_padding_h
            self.setGridSize(QSize(grid_w, grid_h))
            
            # Debounce expensive content resize
            self._resize_timer.start()
            
            event.accept()
        else:
            # User Request: "Too jumpy" -> Reduce sensitivity manually
            # Standard mouse wheel delta is 120.
            # Let's scroll fewer pixels per tick (e.g. 40px)
            delta = event.angleDelta().y()
            if delta == 0: return
            
            # Factor: 0.5 means 60px move per click (if delta is 120)
            # Adjust '0.4' to make it smoother/slower as requested
            step = -int(delta * 0.4) 
            
            sb = self.verticalScrollBar()
            sb.setValue(sb.value() + step)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if hasattr(event, 'position'):
            pos = event.position().toPoint()
        else:
            pos = QPoint(event.x(), event.y())
        
        item = self.itemAt(pos)
        if item:
            if event.button() == Qt.LeftButton:
                self.doubleClickedLeft.emit(item)
            elif event.button() == Qt.RightButton:
                self.doubleClickedRight.emit(item)
        super().mouseDoubleClickEvent(event)

    def set_thumb_size(self, size: int):
        self._thumb_size = size
        self._target_thumb_size = size
        self._apply_delayed_resize()

    def _apply_delayed_resize(self):
        # Commit the target size
        self._thumb_size = self._target_thumb_size
        
        icon_size = QSize(self._thumb_size, self._thumb_size)
        grid_w = self._thumb_size + self._grid_padding_w
        grid_h = self._thumb_size + self._grid_padding_h
        
        self.setIconSize(icon_size)
        self.setGridSize(QSize(grid_w, grid_h))

        # Expensive loop (run only once after scrolling stops)
        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            if isinstance(widget, ThumbnailWidget):
                widget.update_thumb_size(self._thumb_size)
            item.setSizeHint(QSize(grid_w, grid_h))
            
        self.thumbSizeChanged.emit(self._thumb_size)

    def startDrag(self, supportedActions):
        items = self.selectedItems()
        if not items: return
        drag = QDrag(self)
        mime = self.mimeData(items)
        drag.setMimeData(mime)

        size = self.iconSize()
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        
        # Draw first item
        widget = self.itemWidget(items[0])
        if widget and hasattr(widget, 'image_label') and widget.image_label.pixmap():
            scaled = widget.image_label.pixmap().scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (size.width() - scaled.width()) // 2
            y = (size.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        if len(items) > 1:
            painter.fillRect(pixmap.rect(), QColor(0,0,0,128))
            painter.setPen(QPen(Qt.white))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, str(len(items)))
        painter.end()

        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(size.width()//2, size.height()))
        drag.exec(Qt.MoveAction)


# ------------------------------------------------------------
# 패닝 + Ctrl+휠 줌 가능한 스크롤 영역
# ------------------------------------------------------------
class PannableScrollArea(QScrollArea):
    def __init__(self, zoom_callback=None, parent=None):
        super().__init__(parent)
        self._dragging = False
        self._last_pos = None
        self._zoom_callback = zoom_callback

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            if hasattr(event, 'position'):
                self._last_pos = event.position().toPoint()
            else:
                self._last_pos = QPoint(event.x(), event.y())
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._last_pos is not None:
            if hasattr(event, 'position'):
                current_pos = event.position().toPoint()
            else:
                current_pos = QPoint(event.x(), event.y())
            delta = current_pos - self._last_pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            self._last_pos = current_pos
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if self._zoom_callback is not None:
            delta = event.angleDelta().y()
            if delta == 0: return
            steps = delta / 120.0
            self._zoom_callback(steps)
            event.accept()
        else:
            super().wheelEvent(event)

# ------------------------------------------------------------
# GPU 가속 이미지 위젯 (QGraphicsView + OpenGL Viewport)
# ------------------------------------------------------------
class GPUImageWidget(QGraphicsView):
    # Signals for Sync
    zoomChanged = Signal(float)
    scrollChanged = Signal(float, float) # x_pct, y_pct

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # GPU Viewport (Hardware Acceleration)
        # Note: If experiencing lag, try commenting this out to use software rendering
        # User reported lag -> Switching to Software Raster (often smoother for 2D Pan/Zoom on Windows)
        # self.setViewport(QOpenGLWidget())
        
        # Scene
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        
        # Optimization Flags
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.SmoothPixmapTransform, False) # Bilinear is slow on CPU? Let's keep it off for speed for now.
        self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        
        # UX: Anchor Under Mouse (CRITICAL for User Request "Zoom at Mouse Position")
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        
        # Hide scrollbars for cleaner look (User can pan with mouse drag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self.setStyleSheet("background: transparent; border: none;")
        self._current_zoom = 1.0
        self._syncing = False
        self._last_scroll_time = 0

        # Connect Scrollbars for Sync Signal
        self.horizontalScrollBar().valueChanged.connect(self._emit_scroll)
        self.verticalScrollBar().valueChanged.connect(self._emit_scroll)

    def _emit_scroll(self, force=False):
        if self._syncing: return
        
        # Throttle (e.g. max 60fps ~ 16ms)
        import time
        now = time.time() * 1000
        if not force and now - self._last_scroll_time < 16:
            return
        self._last_scroll_time = now

        # Calculate percentage
        h = self.horizontalScrollBar()
        v = self.verticalScrollBar()
        
        x_pct = h.value() / h.maximum() if h.maximum() > 0 else 0
        y_pct = v.value() / v.maximum() if v.maximum() > 0 else 0
        
        self.scrollChanged.emit(x_pct, y_pct)

    def set_scroll_pct(self, x_pct, y_pct):
        self._syncing = True
        h = self.horizontalScrollBar()
        v = self.verticalScrollBar()
        
        if h.maximum() > 0:
            h.setValue(int(x_pct * h.maximum()))
        if v.maximum() > 0:
            v.setValue(int(y_pct * v.maximum()))
        self._syncing = False

    def set_pixmap(self, pixmap: QPixmap | None):
        if pixmap is None:
            self.pixmap_item.setPixmap(QPixmap())
            return
            
        self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        # Capture the actual scale applied by fitInView
        self._current_zoom = self.transform().m11()

    def wheelEvent(self, event):
        # Zoom Logic
        # Standard Wheel Zoom
        delta = event.angleDelta().y()
        if delta == 0: return
        
        factor = 1.1 if delta > 0 else 0.9
        
        self.scale(factor, factor)
        
        # Update internal state with REAL scale
        self._current_zoom = self.transform().m11()
        
        if not self._syncing:
             self.zoomChanged.emit(self._current_zoom)
             # Force scroll sync immediately because wheel zoom (AnchorUnderMouse) changes scroll position
             self._emit_scroll(force=True)
        
        event.accept()

    def set_zoom(self, value: int):
        # value is 10 to 300 (percentage)
        # Check current scale
        current_level = self.transform().m11()
        target_level = value / 100.0
        
        if current_level == 0: return

        # Apply relative scale
        ratio = target_level / current_level
        self.scale(ratio, ratio)
        
        self._current_zoom = target_level
    
    def set_zoom_factor(self, factor):
        # Sync Helper to match exact zoom factor from another widget
        self._syncing = True
        
        # User Feedback: "Common Zoom not working properly"
        # Fix: Switch anchor to ViewCenter during programmatic zoom to prevent jumping 
        # based on arbitrary mouse position in the target widget.
        old_anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        
        current_level = self.transform().m11()
        if current_level > 0:
            ratio = factor / current_level
            self.scale(ratio, ratio)
            self._current_zoom = factor
        
        # Restore Anchor
        self.setTransformationAnchor(old_anchor)
        self._syncing = False
