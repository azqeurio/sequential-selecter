from pathlib import Path
from fractions import Fraction
import json

try:
    import exifread
    EXIFREAD_OK = True
except Exception:
    exifread = None
    EXIFREAD_OK = False
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSpinBox,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsTextItem,
    QFileDialog, QMessageBox, QFrame, QGraphicsRectItem, QComboBox, QColorDialog,
    QSlider, QProgressBar, QLineEdit, QScrollArea, QApplication, QSplitter, QTabWidget
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer, QThread
from PySide6.QtGui import QPixmap, QColor, QFont, QPen, QBrush, QImage, QPainter, QFontDatabase

from ..core.image_loader import load_pil_image
from .utils import pil_to_qimage

# Common Free/Standard Fonts
CURATED_FONTS = [
    "Arial", "Helvetica", "Times New Roman", "Courier New", "Verdana",
    "Georgia", "Palatino", "Garamond", "Bookman", "Comic Sans MS", "Trebuchet MS",
    "Arial Black", "Impact", "Consolas"
]

class SnappingTextItem(QGraphicsTextItem):
    def __init__(self, text, parent=None, scene_rect_func=None):
        super().__init__(text, parent)
        self.setFlags(
            QGraphicsTextItem.ItemIsMovable |
            QGraphicsTextItem.ItemIsSelectable |
            QGraphicsTextItem.ItemSendsGeometryChanges
        )
        self.setFont(QFont("Arial", 50))
        self.setDefaultTextColor(QColor("black"))
        self.scene_rect_func = scene_rect_func

    def itemChange(self, change, value):
        if change == QGraphicsTextItem.ItemPositionChange and self.scene()\
                and self.scene_rect_func and QApplication.mouseButtons() == Qt.LeftButton:
            
            new_pos = value
            rect = self.scene_rect_func()
            snap_margin = 30
            item_w = self.boundingRect().width()
            item_h = self.boundingRect().height()
            rw, rh = rect.width(), rect.height()
            
            # Snap X positions: left edge, 1/3, center, 2/3, right edge
            snap_x_targets = [
                0,                           # Left edge
                20,                          # Left margin
                rw / 3 - item_w / 2,         # 1/3
                rw / 2 - item_w / 2,         # Center
                2 * rw / 3 - item_w / 2,     # 2/3
                rw - item_w - 20,            # Right margin
                rw - item_w,                 # Right edge
            ]
            for sx in snap_x_targets:
                if abs(new_pos.x() - sx) < snap_margin:
                    new_pos.setX(sx)
                    break
            
            # Snap Y positions: top edge, 1/3, center, 2/3, bottom edge
            snap_y_targets = [
                0,                           # Top edge
                20,                          # Top margin
                rh / 3 - item_h / 2,         # 1/3
                rh / 2 - item_h / 2,         # Center
                2 * rh / 3 - item_h / 2,     # 2/3
                rh - item_h - 20,            # Bottom margin
                rh - item_h,                 # Bottom edge
            ]
            for sy in snap_y_targets:
                if abs(new_pos.y() - sy) < snap_margin:
                    new_pos.setY(sy)
                    break
            
            # Constrain within frame
            new_pos.setX(max(0, min(new_pos.x(), rw - item_w)))
            new_pos.setY(max(0, min(new_pos.y(), rh - item_h)))
                
            return new_pos
        return super().itemChange(change, value)

class SnappingPixmapItem(QGraphicsPixmapItem):
    def __init__(self, parent=None, scene_rect_func=None):
        super().__init__(parent)
        self.setFlags(
            QGraphicsPixmapItem.ItemIsMovable |
            QGraphicsPixmapItem.ItemIsSelectable |
            QGraphicsPixmapItem.ItemSendsGeometryChanges
        )
        self.scene_rect_func = scene_rect_func

    def itemChange(self, change, value):
        if change == QGraphicsPixmapItem.ItemPositionChange and self.scene()\
                and self.scene_rect_func and QApplication.mouseButtons() == Qt.LeftButton:
            new_pos = value
            rect = self.scene_rect_func()
            snap_margin = 30
            item_w = self.pixmap().width()
            item_h = self.pixmap().height()
            rw, rh = rect.width(), rect.height()
            
            # Snap X: left, margin, 1/3, center, 2/3, margin, right
            snap_x_targets = [
                0, 20,
                rw / 3 - item_w / 2,
                rw / 2 - item_w / 2,
                2 * rw / 3 - item_w / 2,
                rw - item_w - 20,
                rw - item_w,
            ]
            for sx in snap_x_targets:
                if abs(new_pos.x() - sx) < snap_margin:
                    new_pos.setX(sx)
                    break
            
            # Snap Y: top, margin, 1/3, center, 2/3, margin, bottom
            snap_y_targets = [
                0, 20,
                rh / 3 - item_h / 2,
                rh / 2 - item_h / 2,
                2 * rh / 3 - item_h / 2,
                rh - item_h - 20,
                rh - item_h,
            ]
            for sy in snap_y_targets:
                if abs(new_pos.y() - sy) < snap_margin:
                    new_pos.setY(sy)
                    break
            
            # Constrain within frame
            new_pos.setX(max(0, min(new_pos.x(), rw - item_w)))
            new_pos.setY(max(0, min(new_pos.y(), rh - item_h)))
                
            return new_pos
        return super().itemChange(change, value)

class TemplateScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame_item = QGraphicsRectItem()
        self.frame_item.setBrush(QBrush(QColor("white")))
        self.frame_item.setPen(QPen(Qt.NoPen))
        self.addItem(self.frame_item)
        
        self.pixmap_item = SnappingPixmapItem(self.frame_item, self._get_frame_rect)
        self.text_items = []
        self.logo_item = None
        
        self.margin_top = 100
        self.margin_bottom = 100
        self.margin_left = 100
        self.margin_right = 100
        
        self.current_font = QFont("Arial", 50)
        self.current_text_color = QColor("black")
        self.preview_pil_image = None

    def _get_frame_rect(self):
        return self.frame_item.rect()

    def add_text_item(self, text, position="center", reference_pixmap=None, x=None, y=None):        
        item = SnappingTextItem(text, self.frame_item, self._get_frame_rect)
        item.setFont(self.current_font)
        item.setDefaultTextColor(self.current_text_color)
        
        if reference_pixmap:
            font_size = max(20, int(reference_pixmap.height() * 0.02))
            font = item.font()
            font.setPointSize(font_size)
            item.setFont(font)
            
        if x is not None and y is not None:
            item.setPos(x, y)
        elif reference_pixmap:
            rect = item.boundingRect()
            fw = self.frame_item.rect().width()
            fh = self.frame_item.rect().height()
            
            if position == "bottom-center":
                px = (fw - rect.width()) / 2
                py = fh - (self.margin_bottom / 2) - (rect.height() / 2)
            elif position == "top-left":
                px = self.margin_left / 2
                py = (self.margin_top / 2) - (rect.height() / 2)
            elif position == "top-right":
                px = fw - rect.width() - (self.margin_right / 2)
                py = (self.margin_top / 2) - (rect.height() / 2)
            else:
                px = (fw - rect.width()) / 2
                py = (fh - rect.height()) / 2
                
            px = max(0, px)
            py = max(0, py)
            item.setPos(px, py)
            
        self.text_items.append(item)
        return item

    def add_logo(self, path: str, restore_x=None, restore_y=None):
        if self.logo_item:
            self.removeItem(self.logo_item)
            
        img = QPixmap(path)
        if img.isNull(): return
        
        scaled = img.scaledToHeight(max(50, int(self.margin_bottom * 0.8)), Qt.SmoothTransformation)
        self.logo_item = SnappingPixmapItem(self.frame_item, self._get_frame_rect)
        self.logo_item.setPixmap(scaled)
        
        if restore_x is not None and restore_y is not None:
            self.logo_item.setPos(restore_x, restore_y)
            self.logo_item.source_path = path 
            return

        fw = self.frame_item.rect().width()
        fh = self.frame_item.rect().height()
        
        px = fw - scaled.width() - (self.margin_right / 2)
        py = fh - scaled.height() - (self.margin_bottom / 2)
        
        self.logo_item.setPos(px, py)
        self.logo_item.source_path = path

    def export_preset(self):
        preset = {
            "margin": {
                "top": self.margin_top, "bottom": self.margin_bottom,
                "left": self.margin_left, "right": self.margin_right
            },
            "frame_color": self.frame_item.brush().color().name(),
            "text_color": self.current_text_color.name(),
            "font": self.current_font.family(),
            "texts": [],
            "image_pos": {"x": self.pixmap_item.pos().x(), "y": self.pixmap_item.pos().y()}
        }
        for txt in self.text_items:
            preset["texts"].append({
                "text": txt.toPlainText(),
                "x": txt.pos().x(),
                "y": txt.pos().y()
            })
            
        if self.logo_item and hasattr(self.logo_item, 'source_path'):
            preset["logo"] = {
                "path": self.logo_item.source_path,
                "x": self.logo_item.pos().x(),
                "y": self.logo_item.pos().y()
            }
        return preset

    def load_preset(self, preset: dict):
        self.margin_top = preset.get("margin", {}).get("top", 100)
        self.margin_bottom = preset.get("margin", {}).get("bottom", 100)
        self.margin_left = preset.get("margin", {}).get("left", 100)
        self.margin_right = preset.get("margin", {}).get("right", 100)
        
        self.frame_item.setBrush(QBrush(QColor(preset.get("frame_color", "#FFFFFF"))))
        self.current_text_color = QColor(preset.get("text_color", "#000000"))
        
        font_name = preset.get("font", "Arial")
        self.current_font = QFont(font_name, 50)
        
        for t in self.text_items:
            self.removeItem(t)
        self.text_items.clear()
        
        if self.logo_item:
            self.removeItem(self.logo_item)
            self.logo_item = None
            
        for txt_data in preset.get("texts", []):
            item = self.add_text_item(txt_data["text"], x=txt_data["x"], y=txt_data["y"])
            item.setFont(self.current_font)
            item.setDefaultTextColor(self.current_text_color)
            
        logo_data = preset.get("logo")
        if logo_data and Path(logo_data["path"]).exists():
            self.add_logo(logo_data["path"], restore_x=logo_data["x"], restore_y=logo_data["y"])
            
        img_pos = preset.get("image_pos")
        if img_pos:
            self.pixmap_item.setPos(img_pos["x"], img_pos["y"])


class BatchExportThread(QThread):
    progress = Signal(int, int) 
    finished = Signal(int, int) 
    
    def __init__(self, images_data, templates, export_params, parent=None):
        super().__init__(parent)
        self.images_data = images_data 
        self.templates = templates 
        self.export_params = export_params 
        
    def run(self):
        success = 0
        fail = 0
        total = len(self.images_data)
        
        for i, img_data in enumerate(self.images_data):
            try:
                path = img_data['path']
                orientation = img_data['orientation']
                template = self.templates.get(orientation)
                
                if not template:
                    template = self.templates.get('landscape') or self.templates.get('portrait')
                
                img = load_pil_image(path, max_size=None)
                if not img:
                    fail += 1
                    continue
                    
                # No image edits applied here, only framing
                
                qimg = pil_to_qimage(img)
                pixmap = QPixmap.fromImage(qimg)
                
                temp_scene = QGraphicsScene()
                frame = QGraphicsRectItem()
                frame.setBrush(template.frame_item.brush())
                frame.setPen(Qt.NoPen)
                temp_scene.addItem(frame)
                
                pm_item = QGraphicsPixmapItem(frame)
                pm_item.setPixmap(pixmap)
                
                mt = template.margin_top
                mb = template.margin_bottom
                ml = template.margin_left
                mr = template.margin_right
                
                frame.setRect(0, 0, pixmap.width() + ml + mr, pixmap.height() + mt + mb)
                
                tmpl_img = template.pixmap_item
                tmpl_fw = template.frame_item.rect().width()
                tmpl_fh = template.frame_item.rect().height()
                rel_img_x = tmpl_img.pos().x() / tmpl_fw if tmpl_fw > 0 else 0
                rel_img_y = tmpl_img.pos().y() / tmpl_fh if tmpl_fh > 0 else 0
                
                pm_item.setPos(rel_img_x * frame.rect().width(), rel_img_y * frame.rect().height())
                
                for src_txt in template.text_items:
                    txt = QGraphicsTextItem(src_txt.toPlainText(), frame)
                    txt.setFont(src_txt.font())
                    txt.setDefaultTextColor(src_txt.defaultTextColor())
                    
                    ref_w = template.frame_item.rect().width()
                    ref_h = template.frame_item.rect().height()
                    if ref_w > 0 and ref_h > 0:
                        rel_x = src_txt.pos().x() / ref_w
                        rel_y = src_txt.pos().y() / ref_h
                        txt.setPos(rel_x * frame.rect().width(), rel_y * frame.rect().height())

                if template.logo_item:
                    logo = QGraphicsPixmapItem(template.logo_item.pixmap(), frame)
                    ref_w = template.frame_item.rect().width()
                    ref_h = template.frame_item.rect().height()
                    if ref_w > 0 and ref_h > 0:
                        rel_x = template.logo_item.pos().x() / ref_w
                        rel_y = template.logo_item.pos().y() / ref_h
                        logo.setPos(rel_x * frame.rect().width(), rel_y * frame.rect().height())

                temp_scene.setSceneRect(frame.rect())
                
                out_img = QImage(frame.rect().size().toSize(), QImage.Format_ARGB32)
                out_img.fill(Qt.transparent)
                painter = QPainter(out_img)
                painter.setRenderHint(QPainter.Antialiasing)
                painter.setRenderHint(QPainter.TextAntialiasing)
                painter.setRenderHint(QPainter.SmoothPixmapTransform)
                temp_scene.render(painter, QRectF(out_img.rect()), frame.rect())
                painter.end()
                
                out_path = self.export_params['dir'] / f"{path.stem}_frame.{self.export_params['format']}"
                
                fmt = self.export_params['format'].upper()
                if fmt == "JPG": fmt = "JPEG"
                qual = self.export_params['quality'] if fmt != "PNG" else -1
                
                if out_img.save(str(out_path), fmt, qual):
                    success += 1
                else:
                    fail += 1
                
            except Exception as e:
                print(f"Batch export error on {path.name}: {e}")
                fail += 1
                
            self.progress.emit(i + 1, total)
            
        self.finished.emit(success, fail)

class ExifEditorWidget(QWidget):
    request_close = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #1a1a1c;")
        
        self.images = [] 
        self.templates = {} 
        self.views = {}
        self.active_orientation = None
        self._syncing_edits = False # Keep for now, might be used in other contexts
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self._setup_top_bar()
        
        work_layout = QHBoxLayout()
        self.layout.addLayout(work_layout)
        
        self.preview_tabs = QTabWidget()
        self.preview_tabs.setStyleSheet("""
            QTabBar::tab { background: #333; color: #ccc; padding: 10px 20px; font-weight: bold; border-top-left-radius: 6px; border-top-right-radius: 6px; }
            QTabBar::tab:selected { background: #2ECC71; color: black; }
            QTabWidget::pane { border: none; }
        """)
        self.preview_tabs.currentChanged.connect(self._on_tab_changed)
        
        work_layout.addWidget(self.preview_tabs, 1)
        self._setup_right_panel(work_layout)

    def _on_tab_changed(self, index):
        if index >= 0:
            orientation = self.preview_tabs.tabText(index).split()[0].lower()
            if self.active_orientation != orientation:
                self.set_active_view(orientation)

    def _setup_top_bar(self):
        self.top_bar = QFrame(self)
        self.top_bar.setStyleSheet("background-color: rgba(30, 30, 32, 0.7); border-bottom: 1px solid rgba(255,255,255,0.1);")
        self.top_bar.setFixedHeight(50)
        
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)
        
        self.btn_close = QPushButton("Exit Frame Editor")
        self.btn_close.setFixedHeight(32)
        self.btn_close.setStyleSheet("QPushButton { background: rgba(200, 50, 50, 0.4); color: white; border-radius: 6px; padding: 4px 12px; }")
        self.btn_close.clicked.connect(self.request_close.emit)
        top_layout.addWidget(self.btn_close)
        
        top_layout.addStretch()
        
        self.btn_load_preset = QPushButton("Load Preset")
        self.btn_load_preset.setFixedHeight(32)
        self.btn_load_preset.setStyleSheet("QPushButton { background: #0277bd; color: white; border-radius: 6px; padding: 4px 12px; }")
        self.btn_load_preset.clicked.connect(self.load_preset)
        top_layout.addWidget(self.btn_load_preset)
        
        self.btn_save_preset = QPushButton("Save Preset")
        self.btn_save_preset.setFixedHeight(32)
        self.btn_save_preset.setStyleSheet("QPushButton { background: #00838f; color: white; border-radius: 6px; padding: 4px 12px; }")
        self.btn_save_preset.clicked.connect(self.save_preset)
        top_layout.addWidget(self.btn_save_preset)
        
        # Logo Option
        self.btn_logo = QPushButton("Add Camera Logo")
        self.btn_logo.setFixedHeight(32)
        self.btn_logo.setStyleSheet("QPushButton { background: #555; color: white; border-radius: 6px; padding: 4px 12px; }")
        self.btn_logo.clicked.connect(self.add_logo)
        top_layout.addWidget(self.btn_logo)
        
        self.layout.addWidget(self.top_bar)

    def _create_margin_spinbox(self):
        sb = QSpinBox()
        sb.setRange(0, 5000)
        sb.setValue(100)
        sb.valueChanged.connect(self.update_current_frame)
        return sb
        
    def _setup_right_panel(self, parent_layout):
        self.tools_panel = QFrame()
        self.tools_panel.setFixedWidth(320)
        self.tools_panel.setStyleSheet("background-color: #252526; border-left: 1px solid rgba(255,255,255,0.1); color: #E0E0E0;")
        parent_layout.addWidget(self.tools_panel)
        
        self.tool_layout = QVBoxLayout(self.tools_panel)
        self.tool_layout.setSpacing(10)
        
        # Active Status Label
        self.lbl_active_status = QLabel("<b>ACTIVE: None</b>")
        self.lbl_active_status.setStyleSheet("color: #2ECC71; font-size: 14px;")
        self.tool_layout.addWidget(self.lbl_active_status)
        
        # 1. Independent Margins
        self.tool_layout.addWidget(QLabel("<b>FRAME MARGINS:</b>"))
        grid_margin = QHBoxLayout()
        vbox_m1 = QVBoxLayout()
        vbox_m1.addWidget(QLabel("Top:"))
        self.spin_m_top = self._create_margin_spinbox()
        vbox_m1.addWidget(self.spin_m_top)
        vbox_m1.addWidget(QLabel("Bottom:"))
        self.spin_m_bot = self._create_margin_spinbox()
        vbox_m1.addWidget(self.spin_m_bot)
        grid_margin.addLayout(vbox_m1)
        
        vbox_m2 = QVBoxLayout()
        vbox_m2.addWidget(QLabel("Left:"))
        self.spin_m_left = self._create_margin_spinbox()
        vbox_m2.addWidget(self.spin_m_left)
        vbox_m2.addWidget(QLabel("Right:"))
        self.spin_m_right = self._create_margin_spinbox()
        vbox_m2.addWidget(self.spin_m_right)
        grid_margin.addLayout(vbox_m2)
        self.tool_layout.addLayout(grid_margin)
        
        btn_no_frame = QPushButton("No Frame (Original Image)")
        btn_no_frame.setStyleSheet("QPushButton { background: #333; color: white; border-radius: 4px; padding: 4px 10px; font-weight: bold; } QPushButton:hover { background: #555; }")
        btn_no_frame.clicked.connect(self.set_no_frame)
        self.tool_layout.addWidget(btn_no_frame)
        
        # 2. Colors
        self.tool_layout.addWidget(QFrame(frameShape=QFrame.HLine))
        self.tool_layout.addWidget(QLabel("<b>COLORS:</b>"))
        color_layout = QHBoxLayout()
        btn_wb = QPushButton("W / B")
        btn_wb.clicked.connect(lambda: self.set_simple_colors("white", "black"))
        color_layout.addWidget(btn_wb)
        btn_bw = QPushButton("B / W")
        btn_bw.clicked.connect(lambda: self.set_simple_colors("black", "white"))
        color_layout.addWidget(btn_bw)
        self.hex_input = QLineEdit()
        self.hex_input.setPlaceholderText("Hex Frame #FFFFFF")
        self.hex_input.textChanged.connect(self.apply_hex_color)
        color_layout.addWidget(self.hex_input)
        self.tool_layout.addLayout(color_layout)
        
        # 3. Font
        self.tool_layout.addWidget(QFrame(frameShape=QFrame.HLine))
        self.tool_layout.addWidget(QLabel("<b>FONT:</b>"))
        self.combo_font = QComboBox()
        db = QFontDatabase.families()
        available = [f for f in CURATED_FONTS if f in db]
        if not available: available = db[:10]
        self.combo_font.addItems(available)
        self.combo_font.setCurrentText(available[0] if available else "")
        self.combo_font.currentTextChanged.connect(self.update_font)
        self.tool_layout.addWidget(self.combo_font)
        
        # 4. Text Additions
        self.tool_layout.addWidget(QFrame(frameShape=QFrame.HLine))
        self.tool_layout.addWidget(QLabel("<b>TEXT FIELDS:</b>"))
        
        self.text_scroll = QScrollArea()
        self.text_scroll.setWidgetResizable(True)
        self.text_scroll.setStyleSheet("border: none;")
        self.text_container = QWidget()
        self.text_layout = QVBoxLayout(self.text_container)
        self.text_layout.setAlignment(Qt.AlignTop)
        self.text_scroll.setWidget(self.text_container)
        self.tool_layout.addWidget(self.text_scroll, 1)
        
        self.btn_add_text = QPushButton("+ Add Text")
        self.btn_add_text.clicked.connect(lambda: self.add_text_input("New Text"))
        self.tool_layout.addWidget(self.btn_add_text)
        
        self.tool_layout.addStretch()
        
        # 6. Export Settings
        self.tool_layout.addWidget(QLabel("<b>EXPORT SETTINGS:</b>"))
        fmt_layout = QHBoxLayout()
        fmt_layout.addWidget(QLabel("Format:"))
        self.combo_format = QComboBox()
        self.combo_format.addItems(["JPG", "PNG", "WEBP"])
        fmt_layout.addWidget(self.combo_format)
        self.tool_layout.addLayout(fmt_layout)
        
        qual_layout = QHBoxLayout()
        qual_layout.addWidget(QLabel("Quality:"))
        self.lbl_qual = QLabel("90%")
        self.lbl_qual.setFixedWidth(30)
        self.slider_quality = QSlider(Qt.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(90)
        self.slider_quality.valueChanged.connect(lambda v: self.lbl_qual.setText(f"{v}%"))
        qual_layout.addWidget(self.slider_quality)
        qual_layout.addWidget(self.lbl_qual)
        self.tool_layout.addLayout(qual_layout)
        
        self.btn_export = QPushButton("Export All Selected")
        self.btn_export.setFixedHeight(40)
        self.btn_export.setStyleSheet("QPushButton { background: #2ECC71; color: black; border-radius: 6px; padding: 4px 12px; font-weight: bold; } QPushButton:hover { background: #27AE60; }")
        self.btn_export.clicked.connect(self.run_batch_export)
        self.tool_layout.addWidget(self.btn_export)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        self.tool_layout.addWidget(self.progress_bar)

    def _active_scene(self) -> TemplateScene:
        if not self.active_orientation: return None
        return self.templates.get(self.active_orientation)

    def set_active_view(self, orientation):
        self.active_orientation = orientation
        self.lbl_active_status.setText(f"<b>ACTIVE: {orientation.upper()}</b>")
        
        for o, v in self.views.items():
            if hasattr(v, 'setStyleSheet'):
                pass # Border no longer needed with tabs
                
        self._sync_sidebar_texts()
        self._sync_sidebar_margins()
        
        scene = self._active_scene()
        if scene:
            self.combo_font.setCurrentText(scene.current_font.family())

    def set_no_frame(self):
        self.spin_m_top.setValue(0)
        self.spin_m_bot.setValue(0)
        self.spin_m_left.setValue(0)
        self.spin_m_right.setValue(0)
        
        scene = self._active_scene()
        if scene:
            # Set background to purely transparent
            scene.frame_item.setBrush(QBrush(Qt.transparent))
            # Remove all text/logo elements for a clean export
            for item in list(scene.text_items):
                scene.removeItem(item)
            scene.text_items.clear()
            
            if scene.logo_item:
                scene.removeItem(scene.logo_item)
                scene.logo_item = None
            
            self._sync_sidebar_texts()
            self._apply_frame_layout(scene)

    def _render_scene_image(self, scene):
        if not scene.preview_pil_image: return
        pm = QPixmap.fromImage(pil_to_qimage(scene.preview_pil_image))
        scene.pixmap_item.setPixmap(pm)
        self._apply_frame_layout(scene)

        self._syncing_edits = False

    def set_simple_colors(self, frame_color, text_color):
        scene = self._active_scene()
        if not scene: return
        scene.frame_item.setBrush(QBrush(QColor(frame_color)))
        scene.current_text_color = QColor(text_color)
        for txt in scene.text_items:
            txt.setDefaultTextColor(QColor(text_color))

    def apply_hex_color(self, hex_str):
        if len(hex_str) == 7 and hex_str.startswith("#"):
            scene = self._active_scene()
            if scene:
                color = QColor(hex_str)
                if color.isValid():
                    scene.frame_item.setBrush(QBrush(color))

    def update_font(self, font_name):
        scene = self._active_scene()
        if not scene: return
        scene.current_font = QFont(font_name, 50)
        for txt in scene.text_items:
            f = txt.font()
            f.setFamily(font_name)
            txt.setFont(f)

    def add_logo(self):
        scene = self._active_scene()
        if not scene: return
        path, _ = QFileDialog.getOpenFileName(self, "Select Logo", "", "Images (*.png *.jpg *.webp *.svg)")
        if path: scene.add_logo(path)

    def save_preset(self):
        scene = self._active_scene()
        if not scene: return
        
        preset = scene.export_preset()
        path, _ = QFileDialog.getSaveFileName(self, "Save Preset", "frame_preset.json", "JSON (*.json)")
        if path:
            with open(path, 'w') as f:
                json.dump(preset, f, indent=4)
            QMessageBox.information(self, "Saved", "Preset saved successfully.")
            
    def load_preset(self):
        scene = self._active_scene()
        if not scene:
            return

        path, _ = QFileDialog.getOpenFileName(self, "Load Preset", "", "JSON (*.json)")
        if path:
            try:
                with open(path, 'r') as f:
                    preset = json.load(f)
                scene.load_preset(preset)
                self._apply_frame_layout(scene)
                self._sync_sidebar_texts()
                self._sync_sidebar_margins()
                self.combo_font.setCurrentText(preset.get("font", "Arial"))
                self._render_scene_image(scene)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load preset: {e}")

    def add_text_input(self, text, position="center"):
        scene = self._active_scene()
        item = None
        if scene and scene.pixmap_item.pixmap():
            item = scene.add_text_item(text, position, reference_pixmap=scene.pixmap_item.pixmap())
        self._add_sidebar_input_for_item(item, text)
            
    def _add_sidebar_input_for_item(self, item, text):
        container = QHBoxLayout()
        line = QLineEdit(text)
        
        def on_text_changed(txt):
            if item: item.setPlainText(txt)
                
        line.textChanged.connect(on_text_changed)
        
        btn_del = QPushButton("X")
        btn_del.setFixedWidth(30)
        
        def on_delete():
            if item and item.scene():
                item.scene().removeItem(item)
                if item in self._active_scene().text_items:
                    self._active_scene().text_items.remove(item)
            for i in reversed(range(container.count())): 
                container.itemAt(i).widget().setParent(None)
            container.setParent(None)
            
        btn_del.clicked.connect(on_delete)
        container.addWidget(line)
        container.addWidget(btn_del)
        self.text_layout.addLayout(container)

    def _sync_sidebar_texts(self):
        while self.text_layout.count():
            item = self.text_layout.takeAt(0)
            if item.layout():
                for i in reversed(range(item.layout().count())):
                    w = item.layout().itemAt(i).widget()
                    if w: w.setParent(None)
            elif item.widget():
                item.widget().deleteLater()
                
        scene = self._active_scene()
        if not scene: return
        for txt_item in scene.text_items:
            self._add_sidebar_input_for_item(txt_item, txt_item.toPlainText())

    def _sync_sidebar_margins(self):
        scene = self._active_scene()
        if not scene: return
        
        self.spin_m_top.blockSignals(True)
        self.spin_m_bot.blockSignals(True)
        self.spin_m_left.blockSignals(True)
        self.spin_m_right.blockSignals(True)
        
        self.spin_m_top.setValue(scene.margin_top)
        self.spin_m_bot.setValue(scene.margin_bottom)
        self.spin_m_left.setValue(scene.margin_left)
        self.spin_m_right.setValue(scene.margin_right)
        
        self.spin_m_top.blockSignals(False)
        self.spin_m_bot.blockSignals(False)
        self.spin_m_left.blockSignals(False)
        self.spin_m_right.blockSignals(False)

    def load_images(self, paths: list[Path]):
        self.images.clear()
        
        while self.preview_tabs.count() > 0:
            w = self.preview_tabs.widget(0)
            self.preview_tabs.removeTab(0)
            if w:
                w.deleteLater()
            
        self.templates.clear()
        self.views.clear()
        self.active_orientation = None
        
        landscape_sample = None
        portrait_sample = None
        
        for p in paths:
            try:
                from PIL import Image, ImageOps
                with Image.open(str(p)) as im:
                    im = ImageOps.exif_transpose(im)
                    w, h = im.size
                    orientation = "landscape" if w >= h else "portrait"
                    
                exif = self.extract_exif_data(p)
                self.images.append({'path': p, 'orientation': orientation, 'exif': exif})
                
                if orientation == "landscape" and not landscape_sample: landscape_sample = p
                if orientation == "portrait" and not portrait_sample: portrait_sample = p
            except Exception as e:
                try:
                    import rawpy
                    with rawpy.imread(str(p)) as raw:
                        sizes = raw.sizes
                        w, h = sizes.raw_width, sizes.raw_height
                        if sizes.flip >= 5:
                            w, h = h, w
                        orientation = "landscape" if w >= h else "portrait"
                        
                    exif = self.extract_exif_data(p)
                    self.images.append({'path': p, 'orientation': orientation, 'exif': exif})
                    if orientation == "landscape" and not landscape_sample: landscape_sample = p
                    if orientation == "portrait" and not portrait_sample: portrait_sample = p
                except:
                    print(f"Failed to categorize {p}")

        if landscape_sample:
            self._create_template_view("landscape", landscape_sample)
        if portrait_sample:
            self._create_template_view("portrait", portrait_sample)
            
        if self.views:
            first_key = list(self.views.keys())[0]
            self.set_active_view(first_key)
            
        self._sync_sidebar_texts()
        self._sync_sidebar_margins()

    def _create_template_view(self, orientation, sample_path):
        view = QGraphicsView()
        scene = TemplateScene()
        view.setScene(scene)
        view.setBackgroundBrush(QBrush(QColor("#2c2c2e")))
        view.setRenderHint(QPainter.Antialiasing)
        view.setDragMode(QGraphicsView.ScrollHandDrag) 
        
        original_press = view.mousePressEvent
        def custom_press(event, o=orientation, v=view):
            self.set_active_view(o)
            original_press(event) # call original
        view.mousePressEvent = custom_press
        
        container = QWidget()
        l = QVBoxLayout(container)
        l.setContentsMargins(0,0,0,0)
        l.addWidget(view, 1)
        
        self.templates[orientation] = scene
        self.views[orientation] = container
        self.preview_tabs.addTab(container, orientation.capitalize() + " Template")
        
        img = load_pil_image(sample_path, max_size=2000)
        if img:
            scene.preview_pil_image = img.copy()
            scene.preview_pil_image.thumbnail((1000, 1000))
            self._render_scene_image(scene)
            
            exifs = self.extract_exif_data(sample_path)
            pm = scene.pixmap_item.pixmap()
            if exifs.get("camera"): scene.add_text_item(exifs["camera"], "top-left", pm)
            if exifs.get("lens"): scene.add_text_item(exifs["lens"], "top-right", pm)
            if exifs.get("settings"): scene.add_text_item(exifs["settings"], "bottom-center", pm)
            
            view.fitInView(scene.frame_item, Qt.KeepAspectRatio)

    def extract_exif_data(self, path: Path):
        data = {}
        if not EXIFREAD_OK:
            return data

        def _to_float(value):
            if value is None:
                return None
            s = str(value).strip()
            if not s:
                return None
            try:
                return float(Fraction(s))
            except Exception:
                try:
                    return float(s)
                except Exception:
                    return None

        try:
            with open(path, 'rb') as f:
                tags = exifread.process_file(f, details=False)

            camera = str(tags.get('Image Model', tags.get('Image Make', ''))).strip()
            lens = str(tags.get('EXIF LensModel', '')).strip()
            focal = tags.get('EXIF FocalLength')
            aperture = tags.get('EXIF FNumber')
            iso = str(tags.get('EXIF ISOSpeedRatings', '')).strip()
            shutter = str(tags.get('EXIF ExposureTime', '')).strip()

            focal_val = _to_float(focal)
            aperture_val = _to_float(aperture)
            focal_str = f"{focal_val:g}mm" if focal_val is not None else ""
            aperture_str = f"f/{aperture_val:g}" if aperture_val is not None else ""
            settings_str = f"{focal_str}  {aperture_str}  {shutter}s  ISO {iso}".strip()

            if camera:
                data["camera"] = camera
            if lens:
                data["lens"] = lens
            if settings_str:
                data["settings"] = settings_str

        except Exception:
            pass
        return data

    def update_current_frame(self, _):
        scene = self._active_scene()
        if scene:
            scene.margin_top = self.spin_m_top.value()
            scene.margin_bottom = self.spin_m_bot.value()
            scene.margin_left = self.spin_m_left.value()
            scene.margin_right = self.spin_m_right.value()
            self._apply_frame_layout(scene)

    def _apply_frame_layout(self, scene: TemplateScene):
        if not scene.pixmap_item.pixmap(): return
        
        pw = scene.pixmap_item.pixmap().width()
        ph = scene.pixmap_item.pixmap().height()
        
        frame_w = pw + scene.margin_left + scene.margin_right
        frame_h = ph + scene.margin_top + scene.margin_bottom
        
        scene.frame_item.setRect(0, 0, frame_w, frame_h)
        
        scene.pixmap_item.setPos(scene.margin_left, scene.margin_top)
        scene.setSceneRect(scene.frame_item.rect())

    def run_batch_export(self):
        if not self.images: return
        export_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not export_dir: return
        export_params = {
            'dir': Path(export_dir),
            'format': self.combo_format.currentText().lower(),
            'quality': self.slider_quality.value()
        }
        self.btn_export.setEnabled(False)
        self.progress_bar.setRange(0, len(self.images))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        
        self.thread = BatchExportThread(self.images, self.templates, export_params)
        self.thread.progress.connect(self._on_export_progress)
        self.thread.finished.connect(self._on_export_finished)
        self.thread.start()

    def _on_export_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def _on_export_finished(self, success, fail):
        self.progress_bar.hide()
        self.btn_export.setEnabled(True)
        QMessageBox.information(self, "Export Complete", f"Successfully exported {success} images.\nFailed: {fail}")



