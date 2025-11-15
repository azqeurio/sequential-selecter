import sys
import os
import shutil
from pathlib import Path

import rawpy
from PIL import Image
import pillow_heif

from PySide6.QtCore import (
    Qt, QSize, QThread, Signal, QObject
)
from PySide6.QtGui import (
    QImage, QPixmap
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QListWidget, QListWidgetItem, QLabel,
    QMessageBox, QScrollArea, QSlider, QSplitter
)
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QStyle

from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect

from PySide6.QtCore import QTimer

from collections import OrderedDict


# ------------------------------------------------------------
# 지원 확장자
# ------------------------------------------------------------
SUPPORTED_EXT = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp",
    ".heic", ".heif",
    ".arw", ".cr2", ".cr3", ".nef", ".rw2", ".orf", ".raf", ".dng"
}


# ------------------------------------------------------------
# 이미지 로딩 유틸
# ------------------------------------------------------------
def load_pil_image(path: Path, max_size: int | None = None) -> Image.Image:
    ext = path.suffix.lower()

    if ext in {".heif", ".heic"}:
        heif_file = pillow_heif.read_heif(str(path))
        img = Image.frombytes(
            heif_file.mode,
            heif_file.size,
            heif_file.data,
            "raw"
        )
    elif ext in {".arw", ".cr2", ".cr3", ".nef", ".rw2", ".orf", ".raf", ".dng"}:
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=True,
                output_bps=8,
                half_size=True
            )
        img = Image.fromarray(rgb)
    else:
        img = Image.open(str(path))
        img.load()

    if max_size is not None:
        img = img.copy()
        img.thumbnail((max_size, max_size), Image.LANCZOS)

    return img


def pil_to_qimage(img: Image.Image) -> QImage:
    if img.mode in ("P", "RGBA"):
        img = img.convert("RGBA")
        fmt = QImage.Format_RGBA8888
        bpp = 4
    elif img.mode != "RGB":
        img = img.convert("RGB")
        fmt = QImage.Format_RGB888
        bpp = 3
    else:
        fmt = QImage.Format_RGB888
        bpp = 3

    w, h = img.size
    data = img.tobytes("raw", img.mode)
    qimg = QImage(data, w, h, w * bpp, fmt)
    return qimg.copy()


# ------------------------------------------------------------
# 썸네일 생성 워커
# ------------------------------------------------------------
class ThumbnailWorker(QObject):
    thumbnail_ready = Signal(str, QPixmap)
    finished = Signal()

    def __init__(self, paths, thumb_size=160, parent=None):
        super().__init__(parent)
        self._paths = list(paths)
        self._thumb_size = thumb_size
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        for path in self._paths:
            if self._abort:
                break
            try:
                img = load_pil_image(Path(path), max_size=self._thumb_size)
                qimg = pil_to_qimage(img)
                pixmap = QPixmap.fromImage(qimg)
                if not pixmap.isNull():
                    self.thumbnail_ready.emit(path, pixmap)
            except Exception as e:
                print(f"썸네일 생성 실패: {path} - {e}")
                continue
        self.finished.emit()


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
        # 드래그 앤 드롭 대상 라벨의 스타일을 업데이트하여 전반적인 UI와 조화를 이룹니다.
        self.setStyleSheet(
            """
            QLabel {
                border: 2px dashed #555555;
                border-radius: 6px;
                padding: 8px;
                color: #E0E0E0;
                background-color: #2A2A2A;
            }
            QLabel:hover {
                background-color: #333333;
            }
            """
        )

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        self.main_window.move_selected_to_target(self.target_index)
        event.acceptProposedAction()


# ------------------------------------------------------------
# 클릭 + modifier용 리스트 위젯
# ------------------------------------------------------------
class ImageListWidget(QListWidget):
    clicked_with_modifiers = Signal(QListWidgetItem, Qt.KeyboardModifiers)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 기본 썸네일 크기를 추적합니다. Ctrl+휠을 통해 변경됩니다.
        self._thumb_size = 160
        # 여백을 줄여 썸네일 사이 공간을 최소화합니다.
        # 패딩 값은 가로/세로 여백으로 적용되며, Ctrl+휠로 확대/축소 시에도 유지됩니다.
        self._grid_padding_w = 20
        self._grid_padding_h = 30

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())
        if item is not None:
            self.clicked_with_modifiers.emit(item, event.modifiers())
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        """
        Ctrl 키를 누른 상태에서 휠을 움직이면 썸네일 크기를 확대/축소합니다.
        일반 스크롤 동작은 기본 동작을 따릅니다.
        """
        if event.modifiers() & Qt.ControlModifier:
            delta_y = event.angleDelta().y()
            if delta_y == 0:
                return
            # 한 스텝 당 10% 크기 변화
            factor = 1.1 if delta_y > 0 else 0.9
            new_size = int(self._thumb_size * factor)
            # 최소/최대 크기 제한
            new_size = max(80, min(320, new_size))
            self._thumb_size = new_size
            icon_size = QSize(self._thumb_size, self._thumb_size)
            # 그리드 크기는 여백을 고려하여 조정합니다.
            grid_w = self._thumb_size + self._grid_padding_w
            # 이미지 아래에 텍스트 라인이 없어도 여유 공간을 확보합니다.
            grid_h = self._thumb_size + self._grid_padding_h
            self.setIconSize(icon_size)
            self.setGridSize(QSize(grid_w, grid_h))
            # 레이아웃을 다시 계산하도록 요청합니다.
            self.updateGeometry()
            event.accept()
        else:
            super().wheelEvent(event)


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
            self._last_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._last_pos is not None:
            delta = event.pos() - self._last_pos
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(hbar.value() - delta.x())
            vbar.setValue(vbar.value() - delta.y())
            self._last_pos = event.pos()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            self._last_pos = None
            self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier and self._zoom_callback is not None:
            delta_y = event.angleDelta().y()
            if delta_y != 0:
                steps = delta_y / 120.0
                self._zoom_callback(steps)
            event.accept()
        else:
            super().wheelEvent(event)


# ------------------------------------------------------------
# 메인 윈도우
# ------------------------------------------------------------
class GridSelectorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 기본 제목 및 크기 설정
        # 프로그램 이름을 사용자 요구에 따라 변경합니다.
        self.setWindowTitle("sequential selecter")
        # 초기 창 크기를 설정합니다. 너무 큰 값 대신 적절한 비율을 사용하여 OS마다 알맞은 크기를 보장합니다.
        self.resize(1400, 850)

        self.current_folder: Path | None = None
        self.target_folder1: Path | None = None
        self.target_folder2: Path | None = None

        self.preview_pixmaps = [None, None]
        self.zoom_factors = [1.0, 1.0]
        self.zoom_linked: bool = True

        self.target_click_mode: int | None = None

        self.thumb_thread: QThread | None = None
        self.thumb_worker: ThumbnailWorker | None = None

        self._scroll_sync_guard = False

        self._setup_ui()
        self._setup_scroll_sync()

        # 프리뷰 이미지 캐시: 최근에 본 이미지의 PIL 데이터를 캐싱하여 재로딩 비용을 줄입니다.
        # OrderedDict를 사용해 간단한 LRU 캐시를 구현합니다.
        self._preview_cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._cache_capacity: int = 20

    # --------------------------------------------------------
    # 창 표시 이벤트 처리
    # --------------------------------------------------------
    def showEvent(self, event):
        """
        창이 처음 나타날 때 스플리터 크기 및 그리드 레이아웃을 다시 설정하여
        초기 표시 문제를 방지합니다.
        """
        super().showEvent(event)
        # 다음 프레임에서 스플리터 크기를 재설정
        QTimer.singleShot(0, self._init_layout_sizes)

    def _init_layout_sizes(self):
        # 스플리터 크기를 재설정하여 분할 비율이 초기화되도록 합니다.
        # 최대화하지 않아도 올바른 레이아웃이 보이도록 함
        if hasattr(self, 'splitter_main'):
            total_width = self.width()
            # 왼쪽 패널이 오른쪽보다 넓게 설정되도록 3:1 비율 유지
            left_width = int(total_width * 0.7)
            right_width = total_width - left_width
            self.splitter_main.setSizes([left_width, right_width])
        # 리스트 위젯의 아이콘/그리드 크기를 다시 설정하여 레이아웃을 최신 상태로 반영
        if hasattr(self, 'list_widget'):
            # 현재 썸네일 크기에 기반하여 그리드 크기 계산
            thumb_size = self.list_widget._thumb_size if hasattr(self.list_widget, '_thumb_size') else 160
            grid_w = thumb_size + self.list_widget._grid_padding_w
            grid_h = thumb_size + self.list_widget._grid_padding_h
            self.list_widget.setIconSize(QSize(thumb_size, thumb_size))
            self.list_widget.setGridSize(QSize(grid_w, grid_h))

        # 전역 UI 스타일 시트를 적용하여 깔끔하고 통일된 느낌을 제공합니다.
        # 어두운 배경과 대비되는 강조 색상을 사용하며, 버튼과 슬라이더의 모양을 현대적으로 꾸몄습니다.
        dark_style = """
            QWidget {
                background-color: #121212;
                color: #E0E0E0;
                font-family: 'Segoe UI', sans-serif;
                font-size: 11pt;
            }
            QPushButton {
                background-color: #2C2C2C;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 10pt;
            }
            QPushButton:hover {
                background-color: #363636;
            }
            QPushButton:pressed {
                background-color: #2A2A2A;
            }
            QLabel {
                border: none;
            }
            QSlider::groove:horizontal {
                border: 1px solid #444444;
                height: 4px;
                background: #3A3A3A;
                margin: 0px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #4CAF50;
                border: 1px solid #4CAF50;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #4CAF50;
            }
            QSplitter::handle {
                background-color: #3A3A3A;
            }
            QListWidget {
                border: none;
                background-color: transparent;
            }
            QListWidget::item {
                border: none;
                padding: 4px;
            }
            /* Glass panel style to approximate Material surfaces: semi-transparent with subtle border */
            QFrame#glassPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 rgba(255, 255, 255, 10),
                                           stop:1 rgba(255, 255, 255, 5));
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 16px;
            }
        """
        self.setStyleSheet(dark_style)

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------
    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QHBoxLayout(central)

        self.splitter_main = QSplitter(Qt.Horizontal)
        central_layout.addWidget(self.splitter_main)

        # 왼쪽
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        # 최소 폭을 줄여 스플리터를 더 자유롭게 이동할 수 있도록 합니다.
        left_widget.setMinimumWidth(150)
        self.splitter_main.addWidget(left_widget)

        # 오른쪽
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_widget.setMinimumWidth(150)
        self.splitter_main.addWidget(right_widget)

        # 초기 3:1 비율
        self.splitter_main.setStretchFactor(0, 3)
        self.splitter_main.setStretchFactor(1, 1)
        self.splitter_main.setSizes([1200, 400])

        # 왼쪽 상단 버튼
        top_btn_layout = QHBoxLayout()
        left_layout.addLayout(top_btn_layout)

        self.btn_select_folder = QPushButton("Image Folder")
        self.btn_select_folder.clicked.connect(self.choose_folder)
        # 버튼 크기를 줄입니다.
        self.btn_select_folder.setFixedHeight(32)
        top_btn_layout.addWidget(self.btn_select_folder)

        self.btn_target1 = QPushButton("Target1")
        self.btn_target1.clicked.connect(self.choose_target1)
        self.btn_target1.setFixedHeight(32)
        top_btn_layout.addWidget(self.btn_target1)

        self.btn_target2 = QPushButton("Target2")
        self.btn_target2.clicked.connect(self.choose_target2)
        self.btn_target2.setFixedHeight(32)
        top_btn_layout.addWidget(self.btn_target2)

        # 타겟 폴더 경로 라벨을 제거하여 상단 버튼만 배치합니다.
        # 선택된 폴더 이름은 해당 버튼의 텍스트로 표시됩니다.

        # 썸네일 리스트
        self.list_widget = ImageListWidget()
        # 썸네일 리스트 설정
        self.list_widget.setViewMode(QListWidget.IconMode)
        # 썸네일 기본 크기와 패딩에 기반하여 아이콘 및 그리드 크기를 설정합니다.
        thumb_size = self.list_widget._thumb_size
        pad_w = self.list_widget._grid_padding_w
        pad_h = self.list_widget._grid_padding_h
        self.list_widget.setIconSize(QSize(thumb_size, thumb_size))
        self.list_widget.setGridSize(QSize(thumb_size + pad_w, thumb_size + pad_h))
        # 항목 크기가 동일함을 명시하여 성능을 향상합니다.
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setResizeMode(QListWidget.Adjust)
        self.list_widget.setSpacing(8)
        self.list_widget.setMovement(QListWidget.Static)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setDragDropMode(QListWidget.DragOnly)

        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.list_widget.clicked_with_modifiers.connect(self.on_item_clicked_with_modifiers)

        # 리스트를 글래스 패널로 감싸 레이어 및 그림자 효과 제공
        list_frame = QFrame()
        list_frame.setObjectName("glassPanel")
        list_frame.setFrameShape(QFrame.NoFrame)
        list_layout_inner = QVBoxLayout(list_frame)
        list_layout_inner.setContentsMargins(12, 12, 12, 12)
        list_layout_inner.addWidget(self.list_widget)
        # 그림자 효과 추가
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 8)
        shadow.setColor(Qt.black)
        list_frame.setGraphicsEffect(shadow)
        left_layout.addWidget(list_frame, 1)

        # 오른쪽: 수직 스플리터
        splitter_right = QSplitter(Qt.Vertical)
        right_layout.addWidget(splitter_right)

        # Slot1 패널: 프리뷰 영역과 컨트롤을 글래스 패널로 감쌉니다.
        slot1_frame = QFrame()
        slot1_frame.setObjectName("glassPanel")
        slot1_frame.setFrameShape(QFrame.NoFrame)
        slot1_layout = QVBoxLayout(slot1_frame)
        slot1_layout.setContentsMargins(12, 12, 12, 12)
        # 그림자 효과
        shadow1 = QGraphicsDropShadowEffect()
        shadow1.setBlurRadius(24)
        shadow1.setOffset(0, 8)
        shadow1.setColor(Qt.black)
        slot1_frame.setGraphicsEffect(shadow1)
        splitter_right.addWidget(slot1_frame)

        self.preview_scroll_1 = PannableScrollArea(
            zoom_callback=lambda steps: self.on_zoom_step(0, steps)
        )
        self.preview_label_1 = QLabel("썸네일 클릭 → Slot1 프리뷰 (위)")
        self.preview_label_1.setAlignment(Qt.AlignCenter)
        # 투명한 배경과 흰색 글씨를 사용하여 패널 배경이 비칠 수 있도록 함
        self.preview_label_1.setStyleSheet("background: transparent; color: #ffffff;")
        self.preview_scroll_1.setWidget(self.preview_label_1)
        self.preview_scroll_1.setWidgetResizable(True)
        # 배경색을 투명하게 하여 글래스 패널의 효과를 반영합니다.
        self.preview_scroll_1.setFrameShape(QFrame.NoFrame)
        self.preview_scroll_1.setStyleSheet("background: transparent; border: none;")
        slot1_layout.addWidget(self.preview_scroll_1)

        slot1_ctrl_layout = QHBoxLayout()
        # 슬롯 줌 라벨을 제거하고 슬라이더만 배치합니다.
        self.slider_zoom_1 = QSlider(Qt.Horizontal)
        self.slider_zoom_1.setRange(10, 300)
        self.slider_zoom_1.setValue(100)
        # 슬라이더 높이를 줄여 더 컴팩트하게 만듭니다.
        from PySide6.QtWidgets import QSizePolicy
        self.slider_zoom_1.setFixedHeight(14)
        # 슬라이더 폭은 레이아웃에 따라 조정되지만 너무 길지 않도록 최대폭을 설정합니다.
        self.slider_zoom_1.setMaximumWidth(300)
        # 레이아웃에서 적절히 공간을 사용하도록 크기 정책을 설정합니다.
        self.slider_zoom_1.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.slider_zoom_1.valueChanged.connect(lambda v: self.update_zoom(0, v))
        slot1_ctrl_layout.addWidget(self.slider_zoom_1)

        self.btn_clear_1 = QPushButton("Clear Slot1")
        self.btn_clear_1.clicked.connect(lambda: self.clear_slot(0))
        slot1_ctrl_layout.addWidget(self.btn_clear_1)
        slot1_layout.addLayout(slot1_ctrl_layout)

        # Slot2 패널
        slot2_frame = QFrame()
        slot2_frame.setObjectName("glassPanel")
        slot2_frame.setFrameShape(QFrame.NoFrame)
        slot2_layout = QVBoxLayout(slot2_frame)
        slot2_layout.setContentsMargins(12, 12, 12, 12)
        shadow2 = QGraphicsDropShadowEffect()
        shadow2.setBlurRadius(24)
        shadow2.setOffset(0, 8)
        shadow2.setColor(Qt.black)
        slot2_frame.setGraphicsEffect(shadow2)
        splitter_right.addWidget(slot2_frame)

        self.preview_scroll_2 = PannableScrollArea(
            zoom_callback=lambda steps: self.on_zoom_step(1, steps)
        )
        self.preview_label_2 = QLabel("Ctrl+클릭 → Slot2 프리뷰 (아래)")
        self.preview_label_2.setAlignment(Qt.AlignCenter)
        self.preview_label_2.setStyleSheet("background: transparent; color: #ffffff;")
        self.preview_scroll_2.setWidget(self.preview_label_2)
        self.preview_scroll_2.setWidgetResizable(True)
        self.preview_scroll_2.setFrameShape(QFrame.NoFrame)
        self.preview_scroll_2.setStyleSheet("background: transparent; border: none;")
        slot2_layout.addWidget(self.preview_scroll_2)

        slot2_ctrl_layout = QHBoxLayout()
        # 슬롯2 줌 라벨을 제거하고 슬라이더만 배치합니다.
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
        slot2_layout.addLayout(slot2_ctrl_layout)

        splitter_right.setStretchFactor(0, 1)
        splitter_right.setStretchFactor(1, 1)

        # 아래쪽: 드롭 타겟 + 줌 링크 + 단축키 안내
        bottom_layout = QHBoxLayout()
        right_layout.addLayout(bottom_layout)

        self.drop_label1 = DropLabel("Drag & Drop → Target1", self, 1)
        self.drop_label2 = DropLabel("Drag & Drop → Target2", self, 2)
        # 드래그 라벨 높이를 줄여 버튼과 균형을 맞춥니다.
        self.drop_label1.setFixedHeight(36)
        self.drop_label2.setFixedHeight(36)
        bottom_layout.addWidget(self.drop_label1)
        bottom_layout.addWidget(self.drop_label2)

        self.btn_toggle_zoom_link = QPushButton("독립 줌 모드")
        self.btn_toggle_zoom_link.setCheckable(True)
        self.btn_toggle_zoom_link.toggled.connect(self.on_toggle_zoom_link)
        self.btn_toggle_zoom_link.setFixedHeight(32)
        bottom_layout.addWidget(self.btn_toggle_zoom_link)

        self.btn_shortcuts = QPushButton("단축키 안내")
        self.btn_shortcuts.clicked.connect(self.show_shortcuts)
        self.btn_shortcuts.setFixedHeight(32)
        bottom_layout.addWidget(self.btn_shortcuts)

    # --------------------------------------------------------
    # 스크롤 동기화
    # --------------------------------------------------------
    def _setup_scroll_sync(self):
        self.preview_scroll_1.horizontalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(0, 'h', v)
        )
        self.preview_scroll_1.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(0, 'v', v)
        )
        self.preview_scroll_2.horizontalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(1, 'h', v)
        )
        self.preview_scroll_2.verticalScrollBar().valueChanged.connect(
            lambda v: self._sync_scroll(1, 'v', v)
        )

    def _sync_scroll(self, src_idx: int, orientation: str, value: int):
        if self.preview_pixmaps[0] is None or self.preview_pixmaps[1] is None:
            return
        if self._scroll_sync_guard:
            return

        self._scroll_sync_guard = True

        src_scroll = self.preview_scroll_1 if src_idx == 0 else self.preview_scroll_2
        dst_scroll = self.preview_scroll_2 if src_idx == 0 else self.preview_scroll_1

        if orientation == 'h':
            src_bar = src_scroll.horizontalScrollBar()
            dst_bar = dst_scroll.horizontalScrollBar()
        else:
            src_bar = src_scroll.verticalScrollBar()
            dst_bar = dst_scroll.verticalScrollBar()

        src_max = src_bar.maximum()
        dst_max = dst_bar.maximum()

        if src_max > 0 and dst_max > 0:
            ratio = value / src_max
            dst_bar.setValue(int(ratio * dst_max))

        self._scroll_sync_guard = False

    # --------------------------------------------------------
    # 줌 링크 토글
    # --------------------------------------------------------
    def on_toggle_zoom_link(self, checked: bool):
        if checked:
            self.zoom_linked = False
            self.btn_toggle_zoom_link.setText("공통 줌 모드")
        else:
            self.zoom_linked = True
            self.btn_toggle_zoom_link.setText("독립 줌 모드")
            value = self.slider_zoom_1.value()
            self.slider_zoom_2.blockSignals(True)
            self.slider_zoom_2.setValue(value)
            self.slider_zoom_2.blockSignals(False)
            self.zoom_factors[0] = self.zoom_factors[1] = value / 100.0
            self.apply_zoom(0)
            self.apply_zoom(1)

    # --------------------------------------------------------
    # 단축키 안내
    # --------------------------------------------------------
    def show_shortcuts(self):
        text = (
            "■ 썸네일 / 선택\n"
            "- 클릭: Slot1 프리뷰에 표시\n"
            "- Ctrl + 클릭: Slot2 프리뷰에 표시\n"
            "- 더블클릭: 해당 사진을 Target1 폴더로 이동\n"
            "- 1 키 누른 상태 + 클릭: 클릭한 사진만 Target1 폴더로 이동\n"
            "- 2 키 누른 상태 + 클릭: 클릭한 사진만 Target2 폴더로 이동\n"
            "- 드래그 박스: 여러 장 선택\n"
            "- 드래그 선택 후 1: 선택된 모든 사진을 Target1 폴더로 이동\n"
            "- 드래그 선택 후 2: 선택된 모든 사진을 Target2 폴더로 이동\n\n"
            "■ 프리뷰 창\n"
            "- 마우스 왼쪽 드래그: 이미지 패닝(이동)\n"
            "- Ctrl + 마우스 휠: 줌 인/아웃\n"
            "- Slot1/Slot2 줌 슬라이더: 확대/축소 조절\n"
            "- 공통 줌 모드: 두 슬롯 줌 비율 연동\n"
            "- 독립 줌 모드: 각 슬롯 줌 비율 개별 조절\n\n"
            "■ 파일 이동\n"
            "- 선택 후 Target1/Target2 라벨로 드래그&드롭: 해당 폴더로 이동\n"
            "- 썸네일 더블클릭: 단일 사진을 Target1으로 바로 이동"
        )
        QMessageBox.information(self, "단축키 안내", text)

    # --------------------------------------------------------
    # 줌 스텝 (Ctrl+휠)
    # --------------------------------------------------------
    def on_zoom_step(self, idx: int, steps: float):
        slider = self.slider_zoom_1 if idx == 0 else self.slider_zoom_2
        new_val = int(slider.value() + steps * 10)
        new_val = max(10, min(300, new_val))
        slider.setValue(new_val)

    # --------------------------------------------------------
    # 키 이벤트
    # --------------------------------------------------------
    def keyPressEvent(self, event):
        key = event.key()
        selected = self.list_widget.selectedItems()

        # 새 단축키: 드래그 선택 후 1/2만 눌러서 이동 (선택 개수 2장 이상일 때)
        if key == Qt.Key_1 and self.target_folder1 is not None and len(selected) >= 2:
            self.move_items_to_folder(selected, self.target_folder1)
            return
        if key == Qt.Key_2 and self.target_folder2 is not None and len(selected) >= 2:
            self.move_items_to_folder(selected, self.target_folder2)
            return

        # 그 외에는 기존 1+클릭 / 2+클릭 모드 유지
        if key == Qt.Key_1:
            self.target_click_mode = 1
        elif key == Qt.Key_2:
            self.target_click_mode = 2

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() in (Qt.Key_1, Qt.Key_2):
            self.target_click_mode = None
        super().keyReleaseEvent(event)

    # --------------------------------------------------------
    # 폴더 / 타겟 선택
    # --------------------------------------------------------
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Folder")
        if not folder:
            return
        self.current_folder = Path(folder)
        # 선택된 폴더 이름을 버튼에 표시하고 아이콘을 설정합니다.
        folder_name = os.path.basename(folder)
        self.btn_select_folder.setText(folder_name if folder_name else "Image Folder")
        try:
            icon = self.style().standardIcon(QStyle.SP_DirIcon)
            self.btn_select_folder.setIcon(icon)
        except Exception:
            pass
        self.load_folder_grid(self.current_folder)

    def choose_target1(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Target1 Folder")
        if not folder:
            return
        self.target_folder1 = Path(folder)
        # 버튼 텍스트를 폴더명으로 변경하고 아이콘을 설정합니다.
        folder_name = os.path.basename(folder)
        self.btn_target1.setText(folder_name if folder_name else "Target1")
        try:
            icon = self.style().standardIcon(QStyle.SP_DirIcon)
            self.btn_target1.setIcon(icon)
        except Exception:
            pass

    def choose_target2(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Target2 Folder")
        if not folder:
            return
        self.target_folder2 = Path(folder)
        folder_name = os.path.basename(folder)
        self.btn_target2.setText(folder_name if folder_name else "Target2")
        try:
            icon = self.style().standardIcon(QStyle.SP_DirIcon)
            self.btn_target2.setIcon(icon)
        except Exception:
            pass

    # --------------------------------------------------------
    # 폴더 로딩
    # --------------------------------------------------------
    def load_folder_grid(self, folder: Path):
        self._stop_thumb_thread()
        self.list_widget.clear()

        all_files = []
        for entry in sorted(folder.iterdir()):
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXT:
                all_files.append(str(entry))

        if not all_files:
            QMessageBox.information(self, "Info", "지원하는 이미지 파일이 없습니다.")
            return

        for path_str in all_files:
            p = Path(path_str)
            # 아이템 텍스트를 제거하여 썸네일이 전면에 보이도록 합니다.
            item = QListWidgetItem("")
            item.setData(Qt.UserRole, path_str)
            # 파일명을 툴팁으로 제공하여 필요시 표시할 수 있도록 합니다.
            item.setToolTip(p.name)
            # 텍스트 중앙 정렬은 필요 없으므로 제거합니다.
            self.list_widget.addItem(item)

        # 이름순으로 정렬하여 원하는 사진을 더 쉽게 찾을 수 있도록 합니다.
        self.list_widget.sortItems(Qt.AscendingOrder)

        self.thumb_thread = QThread()
        self.thumb_worker = ThumbnailWorker(all_files, thumb_size=160)
        self.thumb_worker.moveToThread(self.thumb_thread)
        self.thumb_thread.started.connect(self.thumb_worker.run)
        self.thumb_worker.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumb_worker.finished.connect(self.thumb_thread.quit)
        self.thumb_worker.finished.connect(self.thumb_worker.deleteLater)
        self.thumb_thread.finished.connect(self.thumb_thread.deleteLater)
        self.thumb_thread.start()

    def _stop_thumb_thread(self):
        if self.thumb_worker is not None:
            self.thumb_worker.abort()
        if self.thumb_thread is not None:
            self.thumb_thread.quit()
            self.thumb_thread.wait()
        self.thumb_worker = None
        self.thumb_thread = None

    def on_thumbnail_ready(self, path_str: str, pixmap: QPixmap):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.data(Qt.UserRole) == path_str:
                item.setIcon(pixmap)
                break

    # --------------------------------------------------------
    # 더블클릭: Target1으로 이동
    # --------------------------------------------------------
    def on_item_double_clicked(self, item: QListWidgetItem):
        if self.target_folder1 is None:
            QMessageBox.warning(self, "Warning", "먼저 Target1 폴더를 설정해 주세요.")
            return
        self.move_items_to_folder([item], self.target_folder1)

    # --------------------------------------------------------
    # 클릭 + modifiers
    # --------------------------------------------------------
    def on_item_clicked_with_modifiers(self, item: QListWidgetItem, modifiers: Qt.KeyboardModifiers):
        path_str = item.data(Qt.UserRole)
        if not path_str:
            return

        # 1+클릭 / 2+클릭
        if self.target_folder1 and self.target_folder2 and self.target_click_mode in (1, 2):
            if self.target_click_mode == 1:
                self.move_items_to_folder([item], self.target_folder1)
            elif self.target_click_mode == 2:
                self.move_items_to_folder([item], self.target_folder2)
            return

        # Ctrl + 클릭 → Slot2
        if modifiers & Qt.ControlModifier:
            self.set_preview_slot(1, path_str)
            return

        # 그냥 클릭 → Slot1
        self.set_preview_slot(0, path_str)

    # --------------------------------------------------------
    # 프리뷰 슬롯
    # --------------------------------------------------------
    def set_preview_slot(self, idx: int, path_str: str | None):
        if idx not in (0, 1):
            return

        label = self.preview_label_1 if idx == 0 else self.preview_label_2
        scroll = self.preview_scroll_1 if idx == 0 else self.preview_scroll_2
        slider = self.slider_zoom_1 if idx == 0 else self.slider_zoom_2

        if path_str is None:
            label.setPixmap(QPixmap())
            label.setText("Empty")
            self.preview_pixmaps[idx] = None
            self.zoom_factors[idx] = 1.0
            slider.blockSignals(True)
            slider.setValue(100)
            slider.blockSignals(False)
            return

        path = Path(path_str)
        if not path.exists():
            QMessageBox.warning(self, "Warning", f"파일이 존재하지 않습니다:\n{path}")
            return

        try:
            # 프리뷰 이미지 캐시 활용
            cache_key = str(path)
            if cache_key in self._preview_cache:
                # 최근에 사용한 이미지의 순서를 갱신
                img = self._preview_cache.pop(cache_key)
                self._preview_cache[cache_key] = img
            else:
                img = load_pil_image(path, max_size=None)
                # 캐시 공간이 초과될 경우 가장 오래된 항목 제거
                if len(self._preview_cache) >= self._cache_capacity:
                    self._preview_cache.popitem(last=False)
                self._preview_cache[cache_key] = img

            qimg = pil_to_qimage(img)
            pixmap = QPixmap.fromImage(qimg)
            if pixmap.isNull():
                raise ValueError("QPixmap 생성 실패")

            self.preview_pixmaps[idx] = pixmap

            # fit-to-window 비율 계산
            vp_size = scroll.viewport().size()
            if vp_size.width() > 0 and vp_size.height() > 0:
                fx = vp_size.width() / pixmap.width()
                fy = vp_size.height() / pixmap.height()
                factor = min(fx, fy)
            else:
                factor = 1.0

            slider_value = int(factor * 100)
            slider_value = max(10, min(300, slider_value))
            factor = slider_value / 100.0

            if self.zoom_linked:
                self.zoom_factors[0] = self.zoom_factors[1] = factor

                self.slider_zoom_1.blockSignals(True)
                self.slider_zoom_1.setValue(slider_value)
                self.slider_zoom_1.blockSignals(False)

                self.slider_zoom_2.blockSignals(True)
                self.slider_zoom_2.setValue(slider_value)
                self.slider_zoom_2.blockSignals(False)

                self.apply_zoom(0)
                self.apply_zoom(1)
            else:
                self.zoom_factors[idx] = factor
                slider.blockSignals(True)
                slider.setValue(slider_value)
                slider.blockSignals(False)
                self.apply_zoom(idx)

            label.setText("")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"프리뷰 로딩 실패:\n{e}")

        scroll.ensureVisible(0, 0)

    def clear_slot(self, idx: int):
        self.set_preview_slot(idx, None)

    # --------------------------------------------------------
    # 줌 적용
    # --------------------------------------------------------
    def update_zoom(self, idx: int, value: int):
        if self.zoom_linked:
            factor = value / 100.0
            self.zoom_factors[0] = self.zoom_factors[1] = factor

            self.slider_zoom_1.blockSignals(True)
            self.slider_zoom_1.setValue(value)
            self.slider_zoom_1.blockSignals(False)

            self.slider_zoom_2.blockSignals(True)
            self.slider_zoom_2.setValue(value)
            self.slider_zoom_2.blockSignals(False)

            self.apply_zoom(0)
            self.apply_zoom(1)
        else:
            self.zoom_factors[idx] = value / 100.0
            self.apply_zoom(idx)

    def apply_zoom(self, idx: int):
        pixmap = self.preview_pixmaps[idx]
        if pixmap is None:
            return

        factor = self.zoom_factors[idx]
        w = int(pixmap.width() * factor)
        h = int(pixmap.height() * factor)
        if w <= 0 or h <= 0:
            return

        scaled = pixmap.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label = self.preview_label_1 if idx == 0 else self.preview_label_2
        label.setPixmap(scaled)

    # --------------------------------------------------------
    # 선택된 아이템 타겟으로 이동
    # --------------------------------------------------------
    def move_selected_to_target(self, target_index: int):
        if target_index == 1:
            folder = self.target_folder1
        else:
            folder = self.target_folder2

        if folder is None:
            QMessageBox.warning(self, "Warning", f"Target{target_index} 폴더가 설정되지 않았습니다.")
            return

        items = self.list_widget.selectedItems()
        if not items:
            return

        self.move_items_to_folder(items, folder)

    def move_items_to_folder(self, items, folder: Path):
        remove_rows = []
        for item in items:
            path_str = item.data(Qt.UserRole)
            if not path_str:
                continue
            src = Path(path_str)
            if not src.exists():
                continue

            dst = folder / src.name
            try:
                base = dst.stem
                ext = dst.suffix
                i = 1
                while dst.exists():
                    dst = folder / f"{base}_{i}{ext}"
                    i += 1

                shutil.move(str(src), str(dst))
                row = self.list_widget.row(item)
                remove_rows.append(row)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"파일 이동 실패:\n{e}")
                return

        for row in sorted(remove_rows, reverse=True):
            self.list_widget.takeItem(row)

    # --------------------------------------------------------
    # 종료 처리
    # --------------------------------------------------------
    def closeEvent(self, event):
        self._stop_thumb_thread()
        super().closeEvent(event)

    def _stop_thumb_thread(self):
        if self.thumb_worker is not None:
            self.thumb_worker.abort()
        if self.thumb_thread is not None:
            self.thumb_thread.quit()
            self.thumb_thread.wait()
        self.thumb_worker = None
        self.thumb_thread = None


# ------------------------------------------------------------
# main
# ------------------------------------------------------------
def main():
    if os.name == "nt":
        os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    win = GridSelectorWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
