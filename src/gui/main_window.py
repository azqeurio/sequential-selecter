import sys
import os
import shutil
from pathlib import Path
from collections import OrderedDict
import concurrent.futures

from PySide6.QtCore import (
    Qt, QSize, QThread, Signal, QObject, QEasingCurve, QPropertyAnimation, QRect, QPoint,
    QMetaObject, QUrl, QTimer, QEvent
)
from PySide6.QtGui import (
    QImage, QPixmap, QDrag, QPainter, QColor, QPen, QShortcut, QKeySequence, QIcon,
    QDesktopServices
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QListWidget, QListWidgetItem, QLabel,
    QMessageBox, QScrollArea, QSlider, QSplitter,
    QGraphicsOpacityEffect, QFrame, QGraphicsDropShadowEffect, QStyle, QRubberBand,
    QSizePolicy, QDialog, QDialogButtonBox, QTextEdit, QStackedWidget, QTreeWidget, QProgressBar
)
from PIL import Image

# Core imports (adjust as needed for your project structure)
from ..core.image_loader import load_pil_image
from .utils import pil_to_qimage
from .widgets import ThumbnailWidget, DropLabel, ImageListWidget, GPUImageWidget
from .organizer_dialog import OrganizerWidget
from .styles import DARK_STYLE

SUPPORTED_EXT = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.heic', '.heif', '.arw', '.cr2', '.cr3', '.nef', '.rw2', '.orf', '.raf', '.dng'}
RAW_EXT = {'.arw', '.cr2', '.cr3', '.nef', '.rw2', '.orf', '.raf', '.dng'}
PROC_EXT = {'.jpg', '.jpeg', '.png', '.heic', '.heif'}

class GridSelectorWindow(QMainWindow):
    thumbnail_loaded = Signal(str, QImage)
    preview_ready = Signal(str, int, QImage) # Path, Slot, Image

    def __init__(self):
        super().__init__()
        self.setWindowTitle("시퀀셜 셀럭터")
        try:
            icon_path = Path(__file__).resolve().parent.parent.parent / 'sqs.ico'
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
            
        self.resize(1400, 850)

        self.current_folder: Path | None = None
        self.target_folder1: Path | None = None
        self.target_folder2: Path | None = None

        self.preview_pixmaps = [None, None]
        self.zoom_factors = [1.0, 1.0]
        self.zoom_linked: bool = True

        self.preview_scroll_values: list[tuple[int, int]] = [(0, 0), (0, 0)]
        self.last_clicked_row: int | None = None
        self.target_click_mode: int | None = None
        self.key_down_target: int | None = None
        self.moved_during_key_down: bool = False

        self.thumb_thread: QThread | None = None
        # self.thumb_worker removed (deprecated)

        self.undo_stack: list[list[tuple[Path, Path]]] = []
        self.redo_stack: list[list[tuple[Path, Path]]] = []

        self._scroll_sync_guard = False

        self.language: str = 'ko'
        self.translations = {
            'ko': {
                'title': '시퀀셜 셀럭터',
                'select_folder': 'Image Folder',
                'target1': 'Target1',
                'target2': 'Target2',
                'zoom_link': '독립 줌 모드',
                'zoom_link_on': '공통 줌 모드',
                'help': '도움말',
                'dual_mode': '듀얼 모드',
                'single_mode': '단일 모드',
                'donate': '후원하기',
                'language': 'English',
                'organize': '사진 정리',
                'slot1_prompt': '썸네일 클릭 → Slot1 프리뷰 (위)',
                'slot2_prompt': 'Ctrl+클릭 → Slot2 프리뷰 (아래)',
                'empty': 'Empty'
            },
            'en': {
                'title': 'Sequential Selector',
                'select_folder': 'Image Folder',
                'target1': 'Target1',
                'target2': 'Target2',
                'zoom_link': 'Independent Zoom',
                'zoom_link_on': 'Linked Zoom',
                'help': 'Help',
                'dual_mode': 'Dual Mode',
                'single_mode': 'Single Mode',
                'donate': 'Donate',
                'language': '한국어',
                'language': '한국어',
                'organize': 'Move Photos',
                'slot1_prompt': 'Thumbnail click → Slot1 preview (upper)',
                'slot1_prompt': 'Thumbnail click → Slot1 preview (upper)',
                'slot2_prompt': 'Ctrl+Click → Slot2 preview (lower)',
                'empty': 'Empty'
            }
        }

        self.dual_mode_enabled: bool = False
        self.dual_window: QMainWindow | None = None

        self._setup_ui()
        self._setup_scroll_sync()
        
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self.undo_last_move)

        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.redo_shortcut.activated.connect(self.redo_last_move)

        self.dual_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        self.dual_shortcut.activated.connect(self.btn_dual_mode.toggle)

        self._preview_cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._cache_capacity: int = 20
        self._animations: list[QPropertyAnimation] = []

        try:
            # Limit workers to prevent UI freeze and IO saturation
            # Even on high-core CPUs, disk IO or raw processing can choke the system
            cpu = os.cpu_count() or 4
            max_workers = min(cpu, 8) 
        except Exception:
            max_workers = 4
        self.thumb_executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        self.preview_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2) # Separate high-priority executor
        self.thumb_load_version: int = 0
        self.thumbnail_loaded.connect(self._apply_thumbnail)
        self.preview_ready.connect(self._on_preview_ready)

        self.list_widget.thumbSizeChanged.connect(self.on_thumb_size_changed)

        self.last_loaded_thumb_size: int = self.list_widget._thumb_size
        self._pending_thumb_size: int | None = None
        self._thumb_reload_timer: QTimer = QTimer(self)
        self._thumb_reload_timer.setSingleShot(True)
        self._thumb_reload_timer.setInterval(250)
        self._thumb_reload_timer.timeout.connect(self._do_thumb_reload)

    def closeEvent(self, event):
        # Clean Shutdown
        self._thumb_reload_timer.stop()
        # Do not call close_organizer() here if it triggers re-scan
        # Instead, just manually ensure organizer widget is hidden or cleaned up if needed
        # self.close_organizer() - REMOVE to prevent reload
        
        self.thumb_executor.shutdown(wait=False)
        self.preview_executor.shutdown(wait=False)
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._init_layout_sizes)

    def _init_layout_sizes(self):
        if hasattr(self, 'splitter_main'):
            total_width = self.width()
            # 7:3 ratio
            left_width = int(total_width * 0.7)
            right_width = total_width - left_width
            self.splitter_main.setSizes([left_width, right_width])
        
        self.setStyleSheet(DARK_STYLE)
        
        if hasattr(self, 'list_widget'):
            thumb_size = self.list_widget._thumb_size if hasattr(self.list_widget, '_thumb_size') else 160
            grid_w = thumb_size + self.list_widget._grid_padding_w
            grid_h = thumb_size + self.list_widget._grid_padding_h
            self.list_widget.setIconSize(QSize(thumb_size, thumb_size))
            self.list_widget.setGridSize(QSize(grid_w, grid_h))


    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QHBoxLayout(central)

        self.splitter_main = QSplitter(Qt.Horizontal)
        central_layout.addWidget(self.splitter_main)

        # Left Container
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_widget.setMinimumWidth(150)
        self.splitter_main.addWidget(left_widget)

        # Right Container
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_widget.setMinimumWidth(150)
        self.splitter_main.addWidget(self.right_widget)

        self.splitter_main.setStretchFactor(0, 3)
        self.splitter_main.setStretchFactor(1, 1)
        self.splitter_main.setSizes([1200, 400])

        # Top Buttons
        top_btn_layout = QHBoxLayout()
        left_layout.addLayout(top_btn_layout)

        self.btn_select_folder = QPushButton("Image Folder")
        self.btn_select_folder.setObjectName("SelectFolderBtn") # Use Global Style
        self.btn_select_folder.clicked.connect(self.choose_folder)
        self.btn_select_folder.setFixedHeight(40) # MD3 Standard
        # Allow button to expand to show full path
        self.btn_select_folder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        top_btn_layout.addWidget(self.btn_select_folder)
        
        # Organizer Button (Primary)
        self.btn_organize = QPushButton("Move Photos")
        self.btn_organize.setCheckable(True) 
        self.btn_organize.clicked.connect(self.toggle_organizer)
        self.btn_organize.setFixedHeight(40)
        self.btn_organize.setObjectName("PrimaryButton") # Force Green
        # Inherits primary green style
        top_btn_layout.addWidget(self.btn_organize)

        self.btn_target1 = QPushButton("Target1")
        self.btn_target1.clicked.connect(self.choose_target1)
        self.btn_target1.setFixedHeight(40)
        self.btn_target1.setObjectName("TonalButton") # Secondary Style
        top_btn_layout.addWidget(self.btn_target1)

        self.btn_target2 = QPushButton("Target2")
        self.btn_target2.clicked.connect(self.choose_target2)
        self.btn_target2.setFixedHeight(40)
        self.btn_target2.setObjectName("TonalButton") # Secondary Style
        top_btn_layout.addWidget(self.btn_target2)

        self.btn_language = QPushButton()
        self.btn_language.setFixedHeight(40)
        self.btn_language.setObjectName("TonalButton")
        self.btn_language.clicked.connect(self.toggle_language)
        top_btn_layout.addWidget(self.btn_language)

        self.btn_donate = QPushButton()
        self.btn_donate.setFixedHeight(40)
        # Remove FixedWidth(90) causing clipping
        # self.btn_donate.setFixedWidth(90) 
        self.btn_donate.setMinimumWidth(80) # Flexible minimum
        self.btn_donate.setObjectName("TonalButton")
        self.btn_donate.clicked.connect(self.open_donate_link)
        top_btn_layout.addWidget(self.btn_donate)

        # --- Stack for Left Panel ---
        self.left_stack = QStackedWidget()
        
        # 0: Grid
        self.list_frame = QFrame()
        self.list_frame.setObjectName("glassPanel")
        self.list_frame.setFrameShape(QFrame.NoFrame)
        list_layout_inner = QVBoxLayout(self.list_frame)
        list_layout_inner.setContentsMargins(12, 12, 12, 12)
        
        self.list_widget = ImageListWidget()
        self.list_widget.setViewMode(QListWidget.IconMode)
        thumb_size = self.list_widget._thumb_size
        pad_w = self.list_widget._grid_padding_w
        pad_h = self.list_widget._grid_padding_h
        self.list_widget.setIconSize(QSize(thumb_size, thumb_size))
        self.list_widget.setGridSize(QSize(thumb_size + pad_w, thumb_size + pad_h))
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setResizeMode(QListWidget.Adjust)
        self.list_widget.setSpacing(8)
        self.list_widget.setMovement(QListWidget.Static)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setDragDropMode(QListWidget.DragOnly)
        self.list_widget.installEventFilter(self)
        
        # Default 'itemDoubleClicked' sends everything to Target1.
        # We replace it with custom Left/Right detection.
        # self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        
        self.list_widget.doubleClickedLeft.connect(lambda item: self.move_item_to_target(item, 1))
        self.list_widget.doubleClickedRight.connect(lambda item: self.move_item_to_target(item, 2))
        self.list_widget.clicked_with_modifiers.connect(self.on_item_clicked_with_modifiers)
        
        list_layout_inner.addWidget(self.list_widget)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(Qt.black)
        self.list_frame.setGraphicsEffect(shadow)
        
        self.left_stack.addWidget(self.list_frame)

        # 1: Organizer Settings
        self.organizer_widget = OrganizerWidget(self, self.language)
        self.organizer_widget.finished.connect(self.close_organizer)
        self.organizer_widget.setObjectName("glassPanel")
        
        org_frame = QFrame()
        org_frame.setObjectName("glassPanel")
        org_layout = QVBoxLayout(org_frame)
        org_layout.setContentsMargins(12, 12, 12, 12)
        org_layout.addWidget(self.organizer_widget)
        shadow_org = QGraphicsDropShadowEffect()
        shadow_org.setBlurRadius(24)
        shadow_org.setOffset(0, 8)
        shadow_org.setColor(Qt.black)
        org_frame.setGraphicsEffect(shadow_org)

        self.left_stack.addWidget(org_frame)

        left_layout.addWidget(self.left_stack, 1)

        # Right Splitter
        self.splitter_right = QSplitter(Qt.Vertical)
        self.splitter_right.setOrientation(Qt.Vertical)
        self.splitter_right.setHandleWidth(8)
        self.splitter_right.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding) # Ensure it expands
        self.right_layout.addWidget(self.splitter_right)

        # --- Stack for Slot 1 ---
        self.slot1_stack = QStackedWidget()
        
        slot1_wrapper = QFrame()
        slot1_wrapper.setObjectName("glassPanel")
        slot1_wrapper.setFrameShape(QFrame.NoFrame)
        slot1_wrapper_layout = QVBoxLayout(slot1_wrapper)
        slot1_wrapper_layout.setContentsMargins(12, 12, 12, 12)
        shadow1 = QGraphicsDropShadowEffect()
        shadow1.setBlurRadius(24)
        shadow1.setOffset(0, 8)
        shadow1.setColor(Qt.black)
        slot1_wrapper.setGraphicsEffect(shadow1)
        slot1_wrapper_layout.addWidget(self.slot1_stack)
        
        self.splitter_right.addWidget(slot1_wrapper)

        # Slot 1 - Page 0: Image Preview
        self.slot1_preview_widget = QWidget()
        slot1_p_layout = QVBoxLayout(self.slot1_preview_widget)
        slot1_p_layout.setContentsMargins(0, 0, 0, 0)

        # Slot 1 - Page 0: Image Preview
        self.slot1_preview_widget = QWidget()
        slot1_p_layout = QVBoxLayout(self.slot1_preview_widget)
        slot1_p_layout.setContentsMargins(0, 0, 0, 0)

        # GPU Accelerated Widget
        self.preview_widget_1 = GPUImageWidget()
        # No label needed inside, it manages its own scene
        slot1_p_layout.addWidget(self.preview_widget_1)

        slot1_ctrl_layout = QHBoxLayout()
        self.slider_zoom_1 = QSlider(Qt.Horizontal)
        self.slider_zoom_1.setRange(10, 300)
        self.slider_zoom_1.setValue(100)
        self.slider_zoom_1.setFixedHeight(14)
        self.slider_zoom_1.setMaximumWidth(300)
        self.slider_zoom_1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.slider_zoom_1.valueChanged.connect(lambda v: self.update_zoom(0, v))
        slot1_ctrl_layout.addWidget(self.slider_zoom_1)

        self.btn_clear_1 = QPushButton("Clear Slot1")
        self.btn_clear_1.clicked.connect(lambda: self.clear_slot(0))
        slot1_ctrl_layout.addWidget(self.btn_clear_1)
        slot1_p_layout.addLayout(slot1_ctrl_layout)
        
        self.slot1_stack.addWidget(self.slot1_preview_widget)

        # Slot 1 - Page 1: Organizer Tree
        self.org_tree_widget = QTreeWidget()
        self.org_tree_widget.setStyleSheet("background: transparent; border: none;")
        self.slot1_stack.addWidget(self.org_tree_widget)


        # --- Stack for Slot 2 ---
        self.slot2_stack = QStackedWidget()

        slot2_wrapper = QFrame()
        slot2_wrapper.setObjectName("glassPanel")
        slot2_wrapper.setFrameShape(QFrame.NoFrame)
        slot2_wrapper_layout = QVBoxLayout(slot2_wrapper)
        slot2_wrapper_layout.setContentsMargins(12, 12, 12, 12)
        shadow2 = QGraphicsDropShadowEffect()
        shadow2.setBlurRadius(24)
        shadow2.setOffset(0, 8)
        shadow2.setColor(Qt.black)
        slot2_wrapper.setGraphicsEffect(shadow2)
        slot2_wrapper_layout.addWidget(self.slot2_stack)
        
        self.splitter_right.addWidget(slot2_wrapper)
        
        # Slot 2 - Page 0: Image Preview
        self.slot2_preview_widget = QWidget()
        slot2_p_layout = QVBoxLayout(self.slot2_preview_widget)
        slot2_p_layout.setContentsMargins(0, 0, 0, 0)

        # Slot 2 - Page 0: Image Preview
        self.slot2_preview_widget = QWidget()
        slot2_p_layout = QVBoxLayout(self.slot2_preview_widget)
        slot2_p_layout.setContentsMargins(0, 0, 0, 0)
        
        # GPU Accelerated Widget
        self.preview_widget_2 = GPUImageWidget()
        slot2_p_layout.addWidget(self.preview_widget_2)

        slot2_ctrl_layout = QHBoxLayout()
        self.slider_zoom_2 = QSlider(Qt.Horizontal)
        self.slider_zoom_2.setRange(10, 300)
        self.slider_zoom_2.setValue(100)
        self.slider_zoom_2.setFixedHeight(14)
        self.slider_zoom_2.setMaximumWidth(300)
        self.slider_zoom_2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.slider_zoom_2.valueChanged.connect(lambda v: self.update_zoom(1, v))
        slot2_ctrl_layout.addWidget(self.slider_zoom_2)

        self.btn_clear_2 = QPushButton("Clear Slot2")
        self.btn_clear_2.clicked.connect(lambda: self.clear_slot(1))
        slot2_ctrl_layout.addWidget(self.btn_clear_2)
        slot2_p_layout.addLayout(slot2_ctrl_layout)
        
        self.slot2_stack.addWidget(self.slot2_preview_widget)

        # Slot 2 - Page 1: Organizer Log
        self.org_log_widget = QWidget()
        org_log_layout = QVBoxLayout(self.org_log_widget)
        org_log_layout.setContentsMargins(0, 0, 0, 0)
        
        self.org_log_text = QTextEdit()
        self.org_log_text.setReadOnly(True)
        self.org_log_text.setStyleSheet("background: transparent; border: none;")
        org_log_layout.addWidget(self.org_log_text)
        
        self.org_progress = QProgressBar()
        self.org_progress.setFixedHeight(16)
        org_log_layout.addWidget(self.org_progress)
        
        self.slot2_stack.addWidget(self.org_log_widget)


        self.splitter_right.setStretchFactor(0, 1)
        self.splitter_right.setStretchFactor(1, 1)

        # Wire up Organizer Targets
        self.organizer_widget.set_external_widgets(self.org_tree_widget, self.org_log_text, self.org_progress)

        # Bottom
        self.bottom_widget = QWidget()
        self.bottom_layout = QHBoxLayout(self.bottom_widget)
        self.bottom_layout.setContentsMargins(0, 8, 0, 0) # Top margin only
        
        self.right_layout.addWidget(self.bottom_widget)

        self.drop_label1 = DropLabel("Drag & Drop → Target1", self, 1)
        self.drop_label2 = DropLabel("Drag & Drop → Target2", self, 2)
        self.drop_label1.setFixedHeight(36)
        self.drop_label2.setFixedHeight(36)
        self.drop_label1.setWordWrap(True)
        self.drop_label2.setWordWrap(True)
        
        self.bottom_layout.addWidget(self.drop_label1)
        self.bottom_layout.addWidget(self.drop_label2)

        self.btn_toggle_zoom_link = QPushButton("독립 줌 모드")
        self.btn_toggle_zoom_link.setCheckable(True)
        self.btn_toggle_zoom_link.toggled.connect(self.on_toggle_zoom_link)
        self.btn_toggle_zoom_link.setFixedHeight(32)
        self.bottom_layout.addWidget(self.btn_toggle_zoom_link)

        self.btn_help = QPushButton("도움말")
        self.btn_help.clicked.connect(self.show_help)
        self.btn_help.setFixedHeight(32)
        self.bottom_layout.addWidget(self.btn_help)

        self.btn_dual_mode = QPushButton("듀얼 모드")
        self.btn_dual_mode.setCheckable(True)
        self.btn_dual_mode.setFixedHeight(32)
        self.btn_dual_mode.toggled.connect(self.toggle_dual_mode)
        self.bottom_layout.addWidget(self.btn_dual_mode)

        self.update_language()

    def _setup_scroll_sync(self):
        # Connect Sync Signals for GPU Widgets
        self.preview_widget_1.scrollChanged.connect(lambda x,y: self._sync_pan(0, x, y))
        self.preview_widget_1.zoomChanged.connect(lambda z: self._sync_zoom(0, z))
        
        self.preview_widget_2.scrollChanged.connect(lambda x,y: self._sync_pan(1, x, y))
        self.preview_widget_2.zoomChanged.connect(lambda z: self._sync_zoom(1, z))

    def _sync_pan(self, source_idx, x_pct, y_pct):
        if not self.zoom_linked: return
        target_idx = 1 - source_idx
        target = self.preview_widget_1 if target_idx == 0 else self.preview_widget_2
        target.set_scroll_pct(x_pct, y_pct)

    def _sync_zoom(self, source_idx, factor):
        # Update internal state first
        self.zoom_factors[source_idx] = factor
        
        # Sync Slider
        slider = self.slider_zoom_1 if source_idx == 0 else self.slider_zoom_2
        slider.blockSignals(True)
        slider.setValue(int(factor * 100))
        slider.blockSignals(False)

        if self.zoom_linked:
            target_idx = 1 - source_idx
            # Sync Factor
            self.zoom_factors[target_idx] = factor
            
            # Sync Other Widget
            target_widget = self.preview_widget_1 if target_idx == 0 else self.preview_widget_2
            target_widget.set_zoom_factor(factor)
            
            # Sync Other Slider
            other_slider = self.slider_zoom_2 if source_idx == 0 else self.slider_zoom_1
            other_slider.blockSignals(True)
            other_slider.setValue(int(factor * 100))
            other_slider.blockSignals(False)

    def _dummy_sync(self, src_idx: int, orientation: str, value: int):
        pass



    def on_toggle_zoom_link(self, checked):
        if checked:
            self.zoom_linked = False
        else:
            self.zoom_linked = True
            value = self.slider_zoom_1.value()
            self.slider_zoom_2.blockSignals(True)
            self.slider_zoom_2.setValue(value)
            self.slider_zoom_2.blockSignals(False)
            self.zoom_factors[0] = self.zoom_factors[1] = value / 100.0
            self.apply_zoom(0)
            self.apply_zoom(1)
        self.update_language()

    def toggle_organizer(self, checked):
        if checked:
            self.left_stack.setCurrentIndex(1)
            self.slot1_stack.setCurrentIndex(1)
            self.slot2_stack.setCurrentIndex(1)
            if self.current_folder:
                self.organizer_widget.lbl_src.setText(str(self.current_folder))
        else:
            self.left_stack.setCurrentIndex(0)
            self.slot1_stack.setCurrentIndex(0)
            self.slot2_stack.setCurrentIndex(0)
            if self.current_folder:
                 self.load_folder_grid(self.current_folder)

    def close_organizer(self):
        self.btn_organize.setChecked(False)
        self.toggle_organizer(False)

    def open_organizer(self):
        self.btn_organize.setChecked(True)
        self.toggle_organizer(True)

    def undo_last_move(self):
        if not self.undo_stack:
            QMessageBox.information(self, "Info", "되돌릴 이동이 없습니다.")
            return
        moves = self.undo_stack.pop()
        self.redo_stack.append(list(moves))
        for dest_path, src_path in moves:
            try:
                if not dest_path.exists(): continue
                target_path = src_path
                if target_path.exists():
                    base = src_path.stem
                    ext = src_path.suffix
                    target_path = src_path.with_stem(f"{{base}}_restored")
                    i = 1
                    while target_path.exists():
                        target_path = src_path.with_stem(f"{{base}}_restored_{{i}}")
                        i += 1
                shutil.move(str(dest_path), str(target_path))
            except Exception as e:
                print(f"Undo failed: {e}")
        if self.current_folder:
            self.load_folder_grid(self.current_folder)

    def redo_last_move(self):
        if not self.redo_stack:
            QMessageBox.information(self, "Info", "다시 적용할 이동이 없습니다.")
            return
        moves = self.redo_stack.pop()
        action_moves: list[tuple[Path, Path]] = []
        for dest_path, src_path in moves:
            try:
                candidate = src_path
                if not candidate.exists():
                    base = src_path.stem
                    candidate = src_path.with_stem(f"{{base}}_restored")
                if not candidate.exists(): continue
                
                new_dest = dest_path 
                shutil.move(str(candidate), str(new_dest))
                action_moves.append((new_dest, src_path))
            except Exception:
                pass
        
        if action_moves:
            self.undo_stack.append(action_moves)
        if self.current_folder:
            self.load_folder_grid(self.current_folder)

    def toggle_language(self):
        self.language = 'en' if self.language == 'ko' else 'ko'
        self.update_language()

    def update_language(self):
        lang = self.language
        tr = self.translations.get(lang, {})
        self.setWindowTitle(tr.get('title', ''))
        
        if hasattr(self, 'btn_select_folder'): self.btn_select_folder.setText(tr.get('select_folder', self.btn_select_folder.text()))
        if hasattr(self, 'btn_target1'): self.btn_target1.setText(tr.get('target1', self.btn_target1.text()))
        if hasattr(self, 'btn_target2'): self.btn_target2.setText(tr.get('target2', self.btn_target2.text()))
        if hasattr(self, 'btn_donate'): self.btn_donate.setText(tr.get('donate', self.btn_donate.text()))
        if hasattr(self, 'btn_language'): self.btn_language.setText(tr.get('language', self.btn_language.text()))
        
        if hasattr(self, 'btn_organize'):
            self.btn_organize.setText(tr.get('organize', self.btn_organize.text()))

        if hasattr(self, 'btn_toggle_zoom_link'):
            if self.zoom_linked:
                self.btn_toggle_zoom_link.setText(tr.get('zoom_link', self.btn_toggle_zoom_link.text()))
            else:
                self.btn_toggle_zoom_link.setText(tr.get('zoom_link_on', self.btn_toggle_zoom_link.text()))
        
        if hasattr(self, 'btn_dual_mode'):
            if self.dual_mode_enabled:
                self.btn_dual_mode.setText(tr.get('single_mode', self.btn_dual_mode.text()))
            else:
                self.btn_dual_mode.setText(tr.get('dual_mode', self.btn_dual_mode.text()))
            
        if hasattr(self, 'btn_help'): self.btn_help.setText(tr.get('help', self.btn_help.text()))
        
        # Labels are removed in GPU mode, prompt text handling can be added later if needed
        # if hasattr(self, 'preview_pixmaps') and self.preview_pixmaps[0] is None:
        #     self.preview_label_1.setText(tr.get('slot1_prompt', self.preview_label_1.text()))
        # if hasattr(self, 'preview_pixmaps') and self.preview_pixmaps[1] is None:
        #     self.preview_label_2.setText(tr.get('slot2_prompt', self.preview_label_2.text()))

    def open_donate_link(self):
        url = QUrl("https://buymeacoffee.com/modang")
        QDesktopServices.openUrl(url)

    def on_zoom_step(self, idx: int, steps: float):
        slider = self.slider_zoom_1 if idx == 0 else self.slider_zoom_2
        new_val = int(slider.value() + steps * 10)
        new_val = max(10, min(300, new_val))
        slider.setValue(new_val)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_1 and self.target_folder1 is not None:
            self.key_down_target = 1
            return
        if key == Qt.Key_2 and self.target_folder2 is not None:
            self.key_down_target = 2
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_1 and self.target_folder1 is not None:
            if self.key_down_target == 1:
                if self.moved_during_key_down:
                    self.target_click_mode = None
                    self.moved_during_key_down = False
                else:
                    selected = self.list_widget.selectedItems()
                    if len(selected) > 0:
                        self.move_selected_to_target(1)
                        self.target_click_mode = None
                    else:
                        self.target_click_mode = 1
            self.key_down_target = None
            super().keyReleaseEvent(event)
            return
        if event.key() == Qt.Key_2 and self.target_folder2 is not None:
            if self.key_down_target == 2:
                if self.moved_during_key_down:
                    self.target_click_mode = None
                    self.moved_during_key_down = False
                else:
                    selected = self.list_widget.selectedItems()
                    if len(selected) > 0:
                        self.move_selected_to_target(2)
                        self.target_click_mode = None
                    else:
                        self.target_click_mode = 2
            self.key_down_target = None
            super().keyReleaseEvent(event)
            return
        super().keyReleaseEvent(event)

    def choose_folder(self):
        # Auto-exit organizer mode
        self.close_organizer()
        
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not folder: return
        self.current_folder = Path(folder)
        # Show FULL path as requested
        self.btn_select_folder.setText(str(self.current_folder))
        # Ask pairing on new folder load
        self.load_folder_grid(self.current_folder, ask_pairing=True)

    # ... (skipping target choosers logic if unchanged, but they are localized) ...



    def choose_target1(self):
        self.close_organizer()
        folder = QFileDialog.getExistingDirectory(self, "Select Target1 Folder")
        if not folder: return
        self.target_folder1 = Path(folder)
        self.btn_target1.setText(os.path.basename(folder) or "Target1")

    def choose_target2(self):
        self.close_organizer()
        folder = QFileDialog.getExistingDirectory(self, "Select Target2 Folder")
        if not folder: return
        self.target_folder2 = Path(folder)
        self.btn_target2.setText(os.path.basename(folder) or "Target2")

    # Updated to accept ask_pairing flag
    def load_folder_grid(self, folder: Path, ask_pairing: bool = False):
        self.list_widget.clear()
        self.thumb_load_version += 1
        current_version = self.thumb_load_version

        # Recursive Scan
        files = []
        try:
            # os.walk for recursion
            for root, dirs, fns in os.walk(folder):
                for fn in fns:
                    path = Path(root) / fn
                    if path.suffix.lower() in SUPPORTED_EXT:
                        files.append(path)
        except Exception as e:
            print(f"Grid Error: {e}")
            return
        
        # Sort files
        files.sort(key=lambda x: x.name)

        # Detect Pairs and Ask User
        if ask_pairing:
             # Detailed Analysis using Fuzzy Logic
             # 1. Group by Stem (Case Insensitive, ignore parent)
             stem_map_temp = {}
             for f in files:
                 stem = f.stem.lower()
                 if stem not in stem_map_temp: stem_map_temp[stem] = []
                 stem_map_temp[stem].append(f)
             
             # 2. Fuzzy Match: Handle _1, _2 suffixes for RAWs
             # If we have 'img_1' (RAW) and 'img' (JPG), merge them.
             stems = list(stem_map_temp.keys())
             for s in stems:
                 if s not in stem_map_temp: continue # Already merged
                 
                 # Check if this stem looks like it has a suffix (e.g. ends with _digit)
                 if '_' in s and s[-1].isdigit():
                     base = s.rsplit('_', 1)[0]
                     if base in stem_map_temp:
                         # Merge 's' into 'base'
                         # But only if 's' is mostly RAW? Or just merge.
                         stem_map_temp[base].extend(stem_map_temp[s])
                         del stem_map_temp[s]

             count_pairs = 0
             unpaired_count = 0
             folders_with_pairs = set()

             for group in stem_map_temp.values():
                 # Check if meaningful pair (e.g. RAW+JPG)
                 has_raw = any(g.suffix.lower() in RAW_EXT for g in group)
                 has_jpg = any(g.suffix.lower() in PROC_EXT for g in group)
                 
                 if has_raw and has_jpg:
                     count_pairs += 1
                     # Identify folder names. Since we ignore parent in grouping, a pair might span folders!
                     # But usually they are in 'raw' and 'jpg' subfolders.
                     # We can list ALL parent folders involved in pairs.
                     for g in group:
                         try:
                             # Show relative folder name from root?
                             rel = g.parent.relative_to(folder)
                             folders_with_pairs.add(str(rel))
                         except ValueError:
                             folders_with_pairs.add(g.parent.name)
                 else:
                     unpaired_count += len(group)

             if count_pairs > 0:
                 # Format folder list (limit to 3)
                 folder_list = sorted(list(folders_with_pairs))
                 folder_display = ", ".join(folder_list[:3])
                 if len(folder_list) > 3:
                     folder_display += ", ..."
                 elif not folder_display or folder_display == ".":
                     folder_display = "(Root)"

                 tr = self.translations.get(self.language, {})
                 title = tr.get('pair_prompt_title', 'Group Files?')
                 # New template uses: folder_count, folder_names, pairs, unpaired
                 msg_tmpl = tr.get('pair_prompt_msg', 'Analysis:\nPairs: {pairs}\nUnpaired: {unpaired}')
                 
                 msg = msg_tmpl.format(
                     folder_count=len(folders_with_pairs),
                     folder_names=folder_display,
                     pairs=count_pairs,
                     unpaired=unpaired_count
                 )
                 
                 ret = QMessageBox.question(self, title, msg, QMessageBox.Yes | QMessageBox.No)
                 
                 # Set state based on answer
                 self.pair_mode_enabled = (ret == QMessageBox.Yes)

        # RAW+JPG Filter Logic
        if self.pair_mode_enabled:
            # Group by stem (Fuzzy)
            stem_map = {}
            for f in files:
                stem = f.stem.lower()
                if stem not in stem_map:
                    stem_map[stem] = []
                stem_map[stem].append(f)

            # Re-apply Fuzzy Merge logic
            stems = list(stem_map.keys())
            for s in stems:
                if s not in stem_map: continue
                if '_' in s and s[-1].isdigit():
                    base = s.rsplit('_', 1)[0]
                    if base in stem_map:
                        stem_map[base].extend(stem_map[s])
                        del stem_map[s]
            
            final_groups = [] # List of (representative, [siblings])
            for group in stem_map.items():
                # group is (stem, [files])
                group_files = group[1]
                
                raw_cand = None
                for g in group_files:
                    if g.suffix.lower() in RAW_EXT:
                        raw_cand = g
                        break
                
                rep = raw_cand if raw_cand else group_files[0]
                siblings = [g for g in group_files if g != rep]
                final_groups.append((rep, siblings))
            
            final_groups.sort(key=lambda x: x[0].name)
            display_data = final_groups
            
        else:
            # Normal Mode (No grouping)
            display_data = [(f, []) for f in files]

        # --- Populate List and Start Local Generation ---
        visible_paths = []
        
        for f, siblings in display_data:
            item = QListWidgetItem()
            self.list_widget.addItem(item)
            
            # Show relative path if deep, else name
            try:
                rel = f.relative_to(folder)
                display_text = str(rel) if len(rel.parts) > 1 else f.name
            except ValueError:
                display_text = f.name
            
            # Use Green Indicator for pairs
            widget = ThumbnailWidget(display_text, self.list_widget._thumb_size)
            if siblings:
                widget.set_paired(True) # Green border on thumbnail
            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)
            item.setData(Qt.UserRole, str(f))
            item.setData(Qt.UserRole + 1, [str(s) for s in siblings])
            
            visible_paths.append(str(f))

        self.list_widget.scrollToTop()
        self.preview_pixmaps = [None, None]
        # Clear Previews
        self.preview_widget_1.set_pixmap(None)
        self.preview_widget_2.set_pixmap(None)

        # Start loading thumbnails
        for p in visible_paths:
             self.thumb_executor.submit(self._load_thumbnail_task, p, self.list_widget._thumb_size, current_version)

    def _load_thumbnail_task(self, path, size, version):
        if version != self.thumb_load_version: return
        try:
            img = load_pil_image(Path(path), max_size=size)
            if img:
                qimg = pil_to_qimage(img)
                if version == self.thumb_load_version:
                    self.thumbnail_loaded.emit(path, qimg)
        except Exception:
            pass

    def _apply_thumbnail(self, path, qimg):
        pixmap = QPixmap.fromImage(qimg)
        count = self.list_widget.count()
        for i in range(count):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == path:
                widget = self.list_widget.itemWidget(item)
                if isinstance(widget, ThumbnailWidget):
                    widget.set_pixmap(pixmap)
                break

    def on_thumb_size_changed(self, new_size):
        self._pending_thumb_size = new_size
        self._thumb_reload_timer.start()

    def _do_thumb_reload(self):
        if self._pending_thumb_size is None or self.current_folder is None: return
        if abs(self._pending_thumb_size - self.last_loaded_thumb_size) > 50:
            self.last_loaded_thumb_size = self._pending_thumb_size
            self.load_folder_grid(self.current_folder)

    def on_item_clicked_with_modifiers(self, item, modifiers):
        path = Path(item.data(Qt.UserRole))
        self.last_clicked_row = self.list_widget.row(item)
        slot_idx = 1 if (modifiers & Qt.ControlModifier) else 0
        self.load_preview(path, slot_idx)

    def on_item_double_clicked(self, item):
        self.move_item_to_target(item, 1)

    def load_preview(self, path: Path, slot_idx: int):
        try:
            # 1. Check Cache
            img = self._preview_cache.get(str(path))
            if img is not None:
                # Fast Path (already loaded)
                qimg = pil_to_qimage(img)
                pixmap = QPixmap.fromImage(qimg)
                self.preview_pixmaps[slot_idx] = pixmap
                widget = self.preview_widget_1 if slot_idx == 0 else self.preview_widget_2
                widget.set_pixmap(pixmap)
                return

            # 2. Async Load
            # Show nothing or keep previous? Keeping previous is smoother, but maybe set opacity?
            # For now, we just launch the thread via PREVIEW EXECUTOR (High Priority)
            
            # Use load version logic if needed to cancel old? 
            # Ideally we'd cancel, but ThreadPool doesn't support cancel easily.
            # We'll rely on check at widget set time.
            self.preview_executor.submit(self._load_preview_task, path, slot_idx)
            
        except Exception as e:
            print(f"Preview load error: {e}")

    def _load_preview_task(self, path: Path, slot_idx: int):
        try:
            img = load_pil_image(path) # Full load
            if img:
                qimg = pil_to_qimage(img)
                # Keep QImage alive or copy deeper if needed?
                # qimg is local -> conversion to QPixmap on main thread handles data copy
                self.preview_ready.emit(str(path), slot_idx, qimg)
            else:
                print(f"Failed to load image: {path}")
        except Exception as e:
            print(f"Preview task error: {e}")

    def _on_preview_ready(self, path_str, slot_idx, qimg):
        try:
            if qimg.isNull():
                 print("Received null image for preview")
                 return

            pixmap = QPixmap.fromImage(qimg)
            self.preview_pixmaps[slot_idx] = pixmap
            
            widget = self.preview_widget_1 if slot_idx == 0 else self.preview_widget_2
            widget.set_pixmap(pixmap)
            
            # Re-apply zoom to ensure it fits/scales correctly
            self.apply_zoom(slot_idx)
            
        except Exception as e:
             print(f"Preview ready error: {e}")

    def apply_zoom(self, idx, animate=False):
        # Update GPU Widget Zoom
        factor = self.zoom_factors[idx] # e.g. 1.0 = 100%
        widget = self.preview_widget_1 if idx == 0 else self.preview_widget_2
        # set_zoom expects 10-300 int
        widget.set_zoom(int(factor * 100))
    
    def update_zoom(self, idx, value):
        factor = value / 100.0
        self.zoom_factors[idx] = factor
        if self.zoom_linked:
            other_idx = 1 - idx
            self.zoom_factors[other_idx] = factor
            # Block signals to avoid recursion
            other_slider = self.slider_zoom_2 if idx == 0 else self.slider_zoom_1
            other_slider.blockSignals(True)
            other_slider.setValue(value)
            other_slider.blockSignals(False)
            self.apply_zoom(other_idx)
        self.apply_zoom(idx)

    def clear_slot(self, idx):
        self.preview_pixmaps[idx] = None
        widget = self.preview_widget_1 if idx == 0 else self.preview_widget_2
        widget.set_pixmap(None)

    def toggle_dual_mode(self, checked):
        if checked:
            if self.dual_mode_enabled: return
            
            # Detach splitter from right layout
            if self.splitter_right is not None:
                try:
                    self.right_layout.removeWidget(self.splitter_right)
                    self.splitter_right.setParent(None)
                except Exception:
                    pass
            
            # Detach bottom controls
            if self.bottom_widget is not None:
                try:
                    self.right_layout.removeWidget(self.bottom_widget)
                    self.bottom_widget.setParent(None)
                except Exception:
                    pass

            # Create new window
            self.dual_window = QMainWindow()
            self.dual_window.setWindowTitle("Dual View")
            self.dual_window.resize(600, 800)
            self.dual_window.setStyleSheet(self.styleSheet())
            
            dual_widget = QWidget()
            self.dual_window.setCentralWidget(dual_widget)
            dual_layout = QVBoxLayout(dual_widget)
            dual_layout.setContentsMargins(0, 0, 0, 0)
            
            # Add splitter to new window
            # Set Horizontal Layout for Dual View
            self.splitter_right.setOrientation(Qt.Horizontal)
            dual_layout.addWidget(self.splitter_right, 1) # Stretch 1 to fill space
            
            # Add bottom controls to new window
            dual_layout.addWidget(self.bottom_widget, 0) # Stretch 0 (Fixed height)

            # Hide right widget in main window to expand grid
            self.right_widget.hide()

            self.dual_window.setWindowTitle(self.translations[self.language].get('dual_mode', 'Dual Mode'))
            self.dual_window.resize(1200, 800) # Default large size
            self.dual_window.showMaximized() # Maximize to fill screen
            
            original_close = self.dual_window.closeEvent
            def on_close(event):
                self.btn_dual_mode.setChecked(False)
                original_close(event)
            self.dual_window.closeEvent = on_close
            
            self.dual_mode_enabled = True
        else:
            if not self.dual_mode_enabled: return
            
            # Close window if exists
            if self.dual_window:
                self.dual_window.closeEvent = lambda e: e.accept()
                self.dual_window.close()
                self.dual_window = None
            
            # Restore to main window
            self.right_widget.show()
            
            # Reset orientation to Vertical
            self.splitter_right.setOrientation(Qt.Vertical)
            
            # We want: Splitter then Bottom Widget.
            # right_widget already has nothing (if we removed them correctly).
            # But wait, did we remove them or just reparent them?
            # When adding to dual_layout, they were reparented.
            
            self.splitter_right.setParent(self.right_widget)
            self.right_layout.addWidget(self.splitter_right, 1) # Stretch 1
            
            self.bottom_widget.setParent(self.right_widget)
            self.right_layout.addWidget(self.bottom_widget, 0) # Stretch 0
            
            # Force Layout Update
            self.splitter_right.setSizes([500, 500])
            self.splitter_right.show()
            self.bottom_widget.show()
            
            self.dual_mode_enabled = False
        
        self.update_language()

    def eventFilter(self, source, event):
        if source == self.list_widget and event.type() == QEvent.KeyPress:
            pass
        return super().eventFilter(source, event)

    def move_selected_to_target(self, target_idx):
        if target_idx == 1:
            dest_root = self.target_folder1
        else:
            dest_root = self.target_folder2
        
        if not dest_root:
            QMessageBox.warning(self, "Warning", f"Target{target_idx} is not set.")
            return

        items = self.list_widget.selectedItems()
        if not items: return
        
        # Sibling Pairing Logic
        primary_files = []
        hidden_siblings = []
        for item in items:
            primary_files.append(Path(item.data(Qt.UserRole)))
            # Get hidden siblings from data
            sibs = item.data(Qt.UserRole + 1)
            if sibs:
                hidden_siblings.extend([Path(s) for s in sibs])
        
        all_files_to_move = set(primary_files)
        
        # Add explicitly tracked siblings (from fuzzy grouping)
        all_files_to_move.update(hidden_siblings)

        # Legacy Fallback (only if NOT using Pair Mode or if logic requires it)
        # If pair logic is OFF, we still might want to move XMP sidecars.
        if not self.pair_mode_enabled:
            pass # Keep logic below?
        else:
            # If Pair Mode is ON, we rely on the grouping logic above mostly.
            # BUT, we still need to catch .xmp sidecars which are not in the group logic yet?
            # Our fuzzy logic groups RAW+JPG. But excludes XMP.
            # So we SHOULD run sidecar detection for XMPs.
            pass
            
        # Run XMP/Sidecar detection for ALL primary files (safety)
        files_to_scan = list(all_files_to_move)
        for p in files_to_scan:
             parent = p.parent
             stem = p.stem
             try:
                 # Be careful not to pick up unrelated files if fuzzy logic is used.
                 # But XMP usually matches stem exactly.
                 for cand in parent.glob(f"{stem}*"):
                     if cand.suffix.lower() in ['.xmp', '.xml'] and cand not in all_files_to_move:
                         all_files_to_move.add(cand)
             except Exception:
                 pass
        else:
            # Original logic: Ask user
            siblings_found = []
            for p in primary_files:
                parent = p.parent
                stem = p.stem
                try:
                    for cand in parent.glob(f"{stem}.*"):
                        if cand != p and cand not in all_files_to_move:
                             siblings_found.append(cand)
                except Exception:
                    pass
            
            if siblings_found:
                 msg = f"Found {len(siblings_found)} associated files (e.g. RAW/JPG pairs).\nMove them together?"
                 ret = QMessageBox.question(self, "Associated Files", msg, QMessageBox.Yes | QMessageBox.No)
                 if ret == QMessageBox.Yes:
                     all_files_to_move.update(siblings_found)

        moves = []
        for src in all_files_to_move:
            dest = dest_root / src.name
            try:
                if dest.exists():
                     base = dest.stem
                     ext = dest.suffix
                     dest = dest_root / f"{base}_copy{ext}" 
                shutil.move(str(src), str(dest))
                moves.append((dest, src))
            except Exception as e:
                print(f"Move failed: {e}")
        
        if moves:
            self.undo_stack.append(moves)
            self.load_folder_grid(self.current_folder)

    def move_item_to_target(self, item, target_idx):
        item.setSelected(True)
        self.move_selected_to_target(target_idx)

    def show_help(self):
        # Updated Help Text
        if self.language == 'en':
            text = (
                "※ Program Usage Guide\n\n"
                "■ Mode: Image Grid (Default)\n"
                "- Left Panel: Shows thumbnails of images in the selected folder.\n"
                "- Right Panel: Shows two preview slots (Slot 1 & Slot 2).\n"
                "- Click a thumbnail to view in Slot 1.\n"
                "- Ctrl + Click a thumbnail to view in Slot 2.\n"
                "- Use 'Dual Mode' to detach the right panel into a separate window.\n"
                "- Use 'Independent Zoom' to toggle linked zooming between slots.\n"
                "- Drag and Drop images to Target1/Target2 labels at bottom right.\n\n"
                "■ Mode: Organize Photos\n"
                "- Click 'Organize Photos' to switch to this mode.\n"
                "- Left Panel: Settings for sorting (Source, Destination, Grouping, Action).\n"
                "- Slot 1 (Top Right): Shows the preview tree of how files will be organized.\n"
                "- Slot 2 (Bottom Right): Shows execution logs and progress.\n"
                "- Click 'Scan' to analyze files, then 'Start' to execute the move/copy.\n"
                "- Navigating to 'Image Folder' or 'Targets' will automatically exit this mode.\n\n"
                "■ Shortcuts\n"
                "- 1 / 2 + Click: Move to Target 1 / 2\n"
                "- Ctrl+Z: Undo Move\n"
                "- Ctrl+Y: Redo Move\n"
                "- Ctrl+D: Toggle Dual Mode\n"
                "- Ctrl+Scroll: Resize Thumbnails\n"
            )
        else:
            text = (
                "※ 프로그램 사용 안내\n\n"
                "■ 모드: 이미지 그리드 (기본)\n"
                "- 왼쪽 패널: 선택된 폴더의 이미지 썸네일을 표시합니다.\n"
                "- 오른쪽 패널: 두 개의 프리뷰 슬롯(Slot 1, Slot 2)을 보여줍니다.\n"
                "- 썸네일 클릭: Slot 1 상단 프리뷰에 표시\n"
                "- Ctrl + 클릭: Slot 2 하단 프리뷰에 표시\n"
                "- '듀얼 모드' 버튼으로 오른쪽 패널을 별도 창으로 분리할 수 있습니다.\n"
                "- '독립 줌 모드'로 두 슬롯의 줌 연결을 켜고 끌 수 있습니다.\n"
                "- 우측 하단의 Target1/Target2 라벨로 이미지를 드래그하여 이동할 수 있습니다.\n\n"
                "■ 모드: 사진 정리 (Organize Photos)\n"
                "- '사진 정리' 버튼을 누르면 정리 모드로 전환됩니다.\n"
                "- 왼쪽 패널: 분류 설정 (원본/대상 폴더, 그룹 방식, 이동/복사 등).\n"
                "- Slot 1 (우측 상단): 스캔 후 파일이 어떻게 정리될지 트리 구조로 미리 보여줍니다.\n"
                "- Slot 2 (우측 하단): 실행 로그와 진행률을 표시합니다.\n"
                "- 'Scan'을 눌러 분석 후, 'Start'를 눌러 실행하세요.\n"
                "- 'Image Folder'나 타겟 폴더 버튼을 누르면 자동으로 정리 모드가 종료됩니다.\n\n"
                "■ 단축키\n"
                "- 1 / 2 + 클릭: Target 1 / 2 로 이동\n"
                "- Ctrl+Z: 이동 취소 (Undo)\n"
                "- Ctrl+Y: 다시 실행 (Redo)\n"
                "- Ctrl+D: 듀얼 모드 토글\n"
                "- Ctrl+휠: 썸네일 크기 조절\n"
            )
        
        dlg = QDialog(self)
        dlg.setWindowTitle("Help")
        dlg.resize(600, 600)
        
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setText(text)
        text_edit.setStyleSheet("background-color: #1E1E1E; color: #E0E0E0; font-size: 11pt;")
        layout.addWidget(text_edit)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(dlg.accept)
        layout.addWidget(btn_box)
        
        dlg.exec()
