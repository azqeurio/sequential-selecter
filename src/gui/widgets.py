import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QLineEdit, QSizePolicy,
    QCheckBox
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QEvent, QPoint, Property, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QBrush, QWheelEvent, QMouseEvent

class ThumbnailWidget(QWidget):
    """
    Thumbnail widget to display image and name in the grid.
    Supports pairing (green border) and ratings (stars).
    """
    def __init__(self, display_text, size=160, parent=None):
        super().__init__(parent)
        self._size = size
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        self.layout.setSpacing(2)
        
        self.lbl_img = QLabel(self)
        self.lbl_img.setAlignment(Qt.AlignCenter)
        self.lbl_img.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.lbl_text = QLabel(display_text, self)
        self.lbl_text.setAlignment(Qt.AlignCenter)
        self.lbl_text.setStyleSheet("color: white; font-size: 11px;")
        
        self.layout.addWidget(self.lbl_img, 1)
        self.layout.addWidget(self.lbl_text)
        
        # Overlay Checkbox
        self.checkbox = QCheckBox(self.lbl_img)
        self.checkbox.setStyleSheet("""
            QCheckBox::indicator {
                width: 24px;
                height: 24px;
                background-color: rgba(0, 0, 0, 150);
                border: 2px solid white;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                background-color: #4CAF50;
                image: url(); /* Assuming a checkmark is rendered by OS or can be added later */
            }
        """)
        self.checkbox.move(10, 10)
        self.checkbox.hide() # Hidden by default until in selection mode or explicitly shown
        # Click transparently triggers selection via listwidget handled in main_window instead of directly 
        self.checkbox.setAttribute(Qt.WA_TransparentForMouseEvents)
        
        self.is_paired = False
        self.rating = 0
        self.pixmap = None

    def sizeHint(self):
        return QSize(self._size, self._size)

    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
        if pixmap:
            # We must use self.size() or rely on layout to scale it. 
            self.lbl_img.setPixmap(pixmap.scaled(self._size, self._size - 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_img.clear()
            
    def set_paired(self, is_paired):
        self.is_paired = is_paired
        self.update()
        
    def set_selected(self, is_selected):
        self.checkbox.setChecked(is_selected)
        
    def show_checkbox(self, show):
        if show:
            self.checkbox.show()
        else:
            self.checkbox.hide()
        
    def set_rating(self, rating):
        self.rating = rating
        self.update()
        
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw border for paired items
        if self.is_paired:
            pen = QPen(QColor("#4CAF50"), 2)
            painter.setPen(pen)
            painter.drawRect(1, 1, self.width()-2, self.height()-2)
            
        # Draw rating stars
        if self.rating > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor("#FFD700")) # Gold stars
            star_size = 8
            padding = 2
            start_x = self.width() - (self.rating * (star_size + padding)) - 5
            start_y = 5
            for i in range(self.rating):
                painter.drawEllipse(start_x + i*(star_size+padding), start_y, star_size, star_size)

class ImageListWidget(QListWidget):
    """
    Custom QListWidget to handle Ctrl+Scroll zooming and specialized double clicks.
    """
    thumbSizeChanged = Signal(int)
    doubleClickedLeft = Signal(QListWidgetItem)
    doubleClickedRight = Signal(QListWidgetItem)
    clicked_with_modifiers = Signal(QListWidgetItem, Qt.KeyboardModifiers)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumb_size = 160
        self._grid_padding_w = 20
        self._grid_padding_h = 40
        self.setMouseTracking(True)
        self.viewport().installEventFilter(self)
        
    def eventFilter(self, source, event):
        if source == self.viewport() and event.type() == QEvent.Wheel:
            if event.modifiers() == Qt.ControlModifier:
                delta = event.angleDelta().y()
                if delta > 0:
                    self._thumb_size = min(600, self._thumb_size + 20)
                else:
                    self._thumb_size = max(80, self._thumb_size - 20)
                self.thumbSizeChanged.emit(self._thumb_size)
                return True
        return super().eventFilter(source, event)
            
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        item = self.itemAt(event.pos())
        if item:
            if event.button() == Qt.LeftButton:
                self.doubleClickedLeft.emit(item)
            elif event.button() == Qt.RightButton:
                self.doubleClickedRight.emit(item)
        super().mouseDoubleClickEvent(event)
        
    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        item = self.itemAt(event.pos())
        if item and event.modifiers() != Qt.NoModifier:
            self.clicked_with_modifiers.emit(item, event.modifiers())

class DropLabel(QLabel):
    """
    A QLabel that accepts drag-and-drop operations for files/folders.
    """
    dropped = Signal(int, list)
    
    def __init__(self, text, parent=None, target_id=0):
        super().__init__(text, parent)
        self.target_id = target_id
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background-color: #333; color: #ccc; border: 2px dashed #555; border-radius: 5px;")
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet("background-color: #4CAF50; color: white; border: 2px dashed #fff; border-radius: 5px;")
            
    def dragLeaveEvent(self, event):
        self.setStyleSheet("background-color: #333; color: #ccc; border: 2px dashed #555; border-radius: 5px;")
        
    def dropEvent(self, event):
        self.setStyleSheet("background-color: #333; color: #ccc; border: 2px dashed #555; border-radius: 5px;")
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if paths:
            self.dropped.emit(self.target_id, paths)

class GPUImageWidget(QGraphicsView):
    """
    High-performance image viewer using QGraphicsView.
    Emits pan/zoom events to sync with other views.
    """
    keyPressed = Signal(QEvent)
    scrollChanged = Signal(float, float)
    zoomChanged = Signal(float)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)
        
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        
        self.zoom_factor = 1.0
        
    def set_pixmap(self, pixmap):
        if pixmap:
            self.pixmap_item.setPixmap(pixmap)
            self.setSceneRect(self.pixmap_item.boundingRect())
            # Only auto-fit if not user-zoomed
            if self.zoom_factor == 1.0:
                self.resetTransform()
                self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        else:
            self.pixmap_item.setPixmap(QPixmap())
    
    def reset_zoom_to_fit(self):
        """Reset zoom to fit and update state."""
        self.zoom_factor = 1.0
        self.resetTransform()
        if self.pixmap_item.pixmap() and not self.pixmap_item.pixmap().isNull():
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
            
    def wheelEvent(self, event):
        if event.modifiers() == Qt.ControlModifier:
            zoom_in = event.angleDelta().y() > 0
            factor = 1.15 if zoom_in else 1 / 1.15
            new_zoom = self.zoom_factor * factor
            # Clamp zoom range
            if 0.1 <= new_zoom <= 10.0:
                self.zoom_factor = new_zoom
                self.scale(factor, factor)
                self.zoomChanged.emit(self.zoom_factor)
            event.accept()
        else:
            super().wheelEvent(event)
            
    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        x = hbar.value() / max(1, hbar.maximum())
        y = vbar.value() / max(1, vbar.maximum())
        self.scrollChanged.emit(x, y)
        
    def get_view_state(self):
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        return {
            'zoom': self.zoom_factor,
            'x_ratio': hbar.value() / max(1, hbar.maximum()),
            'y_ratio': vbar.value() / max(1, vbar.maximum())
        }
        
    def restore_view_state(self, state):
        if not state: return
        self.zoom_factor = state.get('zoom', 1.0)
        self.setTransform(self.transform().fromScale(self.zoom_factor, self.zoom_factor))
        
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        hbar.setValue(int(state.get('x_ratio', 0) * hbar.maximum()))
        vbar.setValue(int(state.get('y_ratio', 0) * vbar.maximum()))
        
    def set_scroll_pct(self, x_pct, y_pct):
        """Set scroll position by percentage (0.0-1.0) for sync with other views."""
        hbar = self.horizontalScrollBar()
        vbar = self.verticalScrollBar()
        hbar.setValue(int(x_pct * max(1, hbar.maximum())))
        vbar.setValue(int(y_pct * max(1, vbar.maximum())))

    def set_zoom_factor(self, factor):
        """Set zoom factor and apply transform for sync with other views."""
        if abs(self.zoom_factor - factor) < 0.001:
            return
        self.zoom_factor = factor
        self.resetTransform()
        self.scale(factor, factor)

    def keyPressEvent(self, event):
        self.keyPressed.emit(event)
        super().keyPressEvent(event)

class ProSliderWidget(QWidget):
    """
    Custom premium slider widget matching professional photo editors.
    Features: smooth animations, double click to reset, and text-input toggling.
    """
    valueChanged = Signal(int)
    sliderPressed = Signal()
    sliderReleased = Signal()
    
    def __init__(self, name, min_val=-100, max_val=100, default_val=0, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        
        self.name = name
        self._min = min_val
        self._max = max_val
        self._default = default_val
        self._value = default_val
        
        self._hovered = False
        self._pressed = False
        self._handle_radius = 6
        self._hover_radius = 6
        
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.lbl_name = QLabel(name)
        self.lbl_name.setFixedWidth(70)
        self.lbl_name.setStyleSheet("font-size: 11px; color: #bbbbbb; font-weight: bold;")
        self.lbl_name.mouseDoubleClickEvent = self._on_label_double_click
        
        self.slider_area = QWidget()
        self.slider_area.setMouseTracking(True)
        self.slider_area.installEventFilter(self)
        
        self.lbl_val = QLabel(str(default_val))
        self.lbl_val.setFixedWidth(35)
        self.lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.lbl_val.setStyleSheet("font-size: 11px; color: #ffffff;")
        self.lbl_val.mousePressEvent = self._on_val_click
        self.lbl_val.mouseDoubleClickEvent = self._on_label_double_click
        
        self.edit_val = QLineEdit()
        self.edit_val.setFixedWidth(35)
        self.edit_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.edit_val.setStyleSheet("background: #333; color: white; border: 1px solid #555; border-radius: 2px; font-size: 11px;")
        self.edit_val.hide()
        self.edit_val.returnPressed.connect(self._on_edit_finish)
        self.edit_val.editingFinished.connect(self._on_edit_finish)
        
        self.layout.addWidget(self.lbl_name)
        self.layout.addWidget(self.slider_area, 1)
        self.layout.addWidget(self.lbl_val)
        self.layout.addWidget(self.edit_val)
        
        self.anim_val = QPropertyAnimation(self, b"anim_value")
        self.anim_val.setDuration(250)
        self.anim_val.setEasingCurve(QEasingCurve.OutCubic)
        
        self.anim_hover = QPropertyAnimation(self, b"hover_radius")
        self.anim_hover.setDuration(150)

    @Property(float)
    def anim_value(self):
        return self._value
        
    @anim_value.setter
    def anim_value(self, val):
        self._set_value_internal(int(round(val)))

    @Property(float)
    def hover_radius(self):
        return self._hover_radius
        
    @hover_radius.setter
    def hover_radius(self, val):
        self._hover_radius = val
        self.slider_area.update()

    def value(self):
        return self._value
        
    def setValue(self, val):
        self.anim_val.stop()
        self._set_value_internal(val)
        
    def _set_value_internal(self, val):
        val = max(self._min, min(self._max, val))
        if self._value != val:
            self._value = val
            self.lbl_val.setText(str(val))
            self.slider_area.update()
            self.valueChanged.emit(val)

    def _on_label_double_click(self, event):
        self._reset_to_default()

    def _reset_to_default(self):
        if self._value == self._default:
            return
        self.anim_val.stop()
        self.anim_val.setStartValue(self._value)
        self.anim_val.setEndValue(self._default)
        self.anim_val.start()

    def _on_val_click(self, event):
        if event.button() == Qt.LeftButton:
            self.lbl_val.hide()
            self.edit_val.setText(str(self._value))
            self.edit_val.show()
            self.edit_val.setFocus()
            self.edit_val.selectAll()

    def _on_edit_finish(self):
        try:
            val = int(self.edit_val.text())
        except ValueError:
            val = self._value
            
        self.edit_val.hide()
        self.lbl_val.show()
        self.setValue(val)

    def eventFilter(self, obj, event):
        if obj == self.slider_area:
            if event.type() == QEvent.Paint:
                self._paint_slider()
                return True
            elif event.type() == QEvent.Enter:
                self._hovered = True
                self.anim_hover.stop()
                self.anim_hover.setStartValue(self._hover_radius)
                self.anim_hover.setEndValue(8.0)
                self.anim_hover.start()
            elif event.type() == QEvent.Leave:
                self._hovered = False
                self.anim_hover.stop()
                self.anim_hover.setStartValue(self._hover_radius)
                self.anim_hover.setEndValue(6.0)
                self.anim_hover.start()
            elif event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self._pressed = True
                    self.sliderPressed.emit()
                    self._update_value_from_pos(event.pos())
            elif event.type() == QEvent.MouseMove:
                if self._pressed:
                    self._update_value_from_pos(event.pos())
            elif event.type() == QEvent.MouseButtonRelease:
                if event.button() == Qt.LeftButton:
                    self._pressed = False
                    self.sliderReleased.emit()
            elif event.type() == QEvent.MouseButtonDblClick:
                if event.button() == Qt.LeftButton:
                    self._reset_to_default()
                    
        return super().eventFilter(obj, event)

    def _update_value_from_pos(self, pos):
        w = self.slider_area.width()
        margin = 10
        eff_w = w - (margin * 2)
        if eff_w <= 0: return
        
        x = pos.x() - margin
        ratio = max(0.0, min(1.0, x / eff_w))
        
        val = self._min + ratio * (self._max - self._min)
        self.setValue(int(round(val)))

    def _paint_slider(self):
        painter = QPainter(self.slider_area)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.slider_area.width()
        h = self.slider_area.height()
        margin = 10
        eff_w = w - (margin * 2)
        
        cy = h / 2
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#333333"))
        painter.drawRoundedRect(margin, cy - 2, eff_w, 4, 2, 2)
        
        ratio = (self._value - self._min) / (self._max - self._min)
        hx = margin + ratio * eff_w
        
        zero_ratio = (0 - self._min) / (self._max - self._min)
        zx = margin + zero_ratio * eff_w
        
        fill_x = min(zx, hx)
        fill_w = abs(hx - zx)
        if fill_w > 0:
            painter.setBrush(QColor("#4CAF50"))
            painter.drawRoundedRect(int(fill_x), int(cy - 2), int(fill_w), 4, 2, 2)
            
        painter.setBrush(QColor("#777777"))
        painter.drawEllipse(QPoint(int(zx), int(cy)), 3, 3)
            
        painter.setBrush(QColor("#FFFFFF") if self._hovered or self._pressed else QColor("#CCCCCC"))
        r = int(self._hover_radius)
        painter.drawEllipse(QPoint(int(hx), int(cy)), r, r)
        
        painter.end()
