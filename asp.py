import sys
import os
import shutil
from pathlib import Path

import rawpy
from PIL import Image
import pillow_heif

from PySide6.QtCore import (
    Qt, QSize, QThread, Signal, QObject, QEasingCurve, QPropertyAnimation, QRect, QPoint
)
from PySide6.QtGui import (
    QImage, QPixmap, QDrag, QPainter, QColor, QPen
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QListWidget, QListWidgetItem, QLabel,
    QMessageBox, QScrollArea, QSlider, QSplitter,
    QGraphicsOpacityEffect, QFrame, QGraphicsDropShadowEffect, QStyle, QRubberBand
)

from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect

from PySide6.QtCore import QTimer
from PySide6.QtCore import QEvent

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

    def __init__(self, paths, thumb_size=300, parent=None):
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
# 썸네일을 표시하는 커스텀 위젯
# ------------------------------------------------------------

class ThumbnailWidget(QWidget):
    """
    리스트에서 각 이미지 항목을 표시하기 위한 위젯입니다. 이미지와 파일명을 수직으로 배치하고,
    Material Design 가이드라인에서 권장하는 작은 타이포그래피와 색상을 사용합니다. 아이템
    제거 시 페이드 아웃 애니메이션을 적용하기 위해 QGraphicsOpacityEffect를 사용할 수 있습니다.
    """
    def __init__(self, file_name: str, thumb_size: int, parent: QWidget | None = None):
        super().__init__(parent)
        # 배경을 투명하게 하여 선택 박스가 위에 그려질 때 가려지지 않도록 합니다.
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        # 투명 배경을 설정합니다. 선택 박스나 러버 밴드가 위에 표시될 수 있도록
        self.setStyleSheet("background: transparent;")
        # 마우스 이벤트를 위젯에서 받아 처리하지 않고 부모 리스트로 전달하기 위해
        # 투명한 마우스 이벤트 속성을 설정합니다. 이렇게 하면 드래그 영역 선택
        # 및 클릭/더블클릭 이벤트가 QListWidget에 도달하여 올바르게 처리됩니다.
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.thumb_size = thumb_size
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 이미지 라벨
        self.image_label = QLabel()
        self.image_label.setFixedSize(thumb_size, thumb_size)
        self.image_label.setAlignment(Qt.AlignCenter)
        # 투명 배경을 사용하여 그리드 배경과 자연스럽게 어울립니다.
        self.image_label.setStyleSheet("background: transparent;")
        # 이미지 라벨도 마우스 이벤트를 처리하지 않고 부모로 전달합니다.
        self.image_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        layout.addWidget(self.image_label)

        # 파일명 라벨
        self.name_label = QLabel(file_name)
        self.name_label.setAlignment(Qt.AlignCenter)
        # 작은 글씨 크기와 대비가 높은 색상을 사용합니다. 줄바꿈을 방지하기 위해 elide 옵션을 활용할 수 있습니다.
        self.name_label.setStyleSheet("color: #E0E0E0; font-size: 9pt;")
        self.name_label.setWordWrap(False)
        # 파일명이 길 경우 가운데로 정렬한 채 잘립니다.
        layout.addWidget(self.name_label)

        # 이름 라벨 또한 마우스 이벤트를 부모로 전달합니다.
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_pixmap(self, pixmap: QPixmap):
        """이미지 라벨에 썸네일을 설정합니다."""
        if pixmap is not None and not pixmap.isNull():
            self.image_label.setPixmap(pixmap.scaled(
                self.thumb_size,
                self.thumb_size,
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
        # 초기 버전에서 썸네일이 너무 작게 보인다는 피드백을 받아 기본 크기를 키웠습니다.
        # 실제 사용자가 확대한 정도를 고려해 300픽셀로 설정하여 4열 배치 시 가독성을 높입니다.
        self._thumb_size = 300
        # 여백을 줄여 썸네일 사이 공간을 최소화합니다.
        # 패딩 값은 가로/세로 여백으로 적용되며, Ctrl+휠로 확대/축소 시에도 유지됩니다.
        self._grid_padding_w = 20
        # 이미지 아래에 파일명을 표시하기 위해 충분한 여백을 확보합니다.
        self._grid_padding_h = 50

        # 드래그 시작 위치를 저장하기 위한 변수입니다. 이 값이 설정되어 있으면
        # 마우스 이동 시 일정 거리 이상 이동하면 실제 드래그 작업을 시작합니다.
        self._drag_start_pos: QPoint | None = None

        # 사용자가 드래그로 영역 선택을 할 때 사용할 러버 밴드와 시작 좌표를 저장합니다.
        self._rubber_band: QRubberBand | None = None
        self._rubber_start_pos: QPoint | None = None

    def mousePressEvent(self, event):
        # 왼쪽 버튼 클릭 시 현재 위치를 기록하여 나중에 드래그 거리 판정에 사용합니다.
        if event.button() == Qt.LeftButton:
            try:
                pos = event.position().toPoint()
            except AttributeError:
                pos = event.pos()
            self._drag_start_pos = pos
            self._rubber_start_pos = pos
        # 기존 로직: modifier 정보와 함께 클릭 시그널을 전달합니다.
        try:
            pos_for_mod = event.position().toPoint()
        except AttributeError:
            pos_for_mod = event.pos()
        item = self.itemAt(pos_for_mod)
        if item is not None:
            self.clicked_with_modifiers.emit(item, event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 드래그 시작 위치가 기록되어 있고, 일정 거리 이상 이동한 경우 드래그를 시작합니다.
        # 현재 마우스 위치
        current_pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        # 드래그 이동 처리: 선택된 항목 위에서 일정 거리 이상 이동하면 드래그를 시작합니다.
        if self._drag_start_pos is not None:
            if (current_pos - self._drag_start_pos).manhattanLength() >= QApplication.startDragDistance():
                start_item = self.itemAt(self._drag_start_pos)
                if start_item is not None and start_item.isSelected():
                    # 드래그를 시작하기 전에 영역 선택 밴드를 제거합니다.
                    if self._rubber_band is not None:
                        self._rubber_band.hide()
                        self._rubber_band.deleteLater()
                        self._rubber_band = None
                        self._rubber_start_pos = None
                    self.startDrag(Qt.MoveAction)
                    self._drag_start_pos = None
                    return
        # 영역 선택 처리: 드래그 시작 위치가 설정되어 있고, 아직 드래그 작업이 시작되지 않았을 경우
        if self._rubber_start_pos is not None:
            if self._rubber_band is None:
                # 러버 밴드를 생성하여 리스트의 viewport 위에 표시합니다. 선택 박스가 썸네일 위에 나타나도록 raise_ 호출.
                self._rubber_band = QRubberBand(QRubberBand.Rectangle, self.viewport())
                # 스타일 지정: 점선 테두리와 반투명 배경을 사용합니다.
                self._rubber_band.setStyleSheet(
                    "border: 2px dashed #4CAF50; background-color: rgba(76, 175, 80, 80);"
                )
                self._rubber_band.setGeometry(QRect(self._rubber_start_pos, QSize()))
                self._rubber_band.show()
                # 선택 박스를 최상단에 표시하여 썸네일 및 텍스트 위에 나타나도록 합니다.
                self._rubber_band.raise_()
            # 러버 밴드 크기 업데이트
            rect = QRect(self._rubber_start_pos, current_pos).normalized()
            self._rubber_band.setGeometry(rect)
            # 이동 중에도 러버 밴드를 최상단에 유지합니다.
            if self._rubber_band is not None:
                self._rubber_band.raise_()
            # 기본 동작을 중단하여 내부 선택 로직이 실행되지 않도록 합니다.
            return

        # 기본 동작을 수행하여 단일 항목 선택 등이 정상 동작하도록 합니다.
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # 마우스 릴리즈 시 드래그 시작 위치를 초기화합니다.
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = None
            # 영역 선택이 진행 중이었다면 선택을 확정하고 러버 밴드를 제거합니다.
            if self._rubber_band is not None and self._rubber_start_pos is not None:
                # 현재 러버 밴드 영역과 교차하는 아이템을 선택합니다.
                selection_rect = self._rubber_band.geometry()
                self._rubber_band.hide()
                self._rubber_band.deleteLater()
                self._rubber_band = None
                # 선택 상태 초기화: Ctrl 키가 눌린 경우에는 기존 선택을 유지합니다.
                modifiers = event.modifiers() if hasattr(event, 'modifiers') else QApplication.keyboardModifiers()
                if not (modifiers & Qt.ControlModifier):
                    # 기존 선택을 해제하고 새 선택만 유지
                    self.clearSelection()
                for i in range(self.count()):
                    item = self.item(i)
                    item_rect = self.visualItemRect(item)
                    if selection_rect.intersects(item_rect):
                        item.setSelected(True)
                self._rubber_start_pos = None
                # 기본 동작으로 넘어가지 않고 선택이 완료되었음을 표시합니다.
                return
        super().mouseReleaseEvent(event)

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
            # 썸네일이 너무 작거나 너무 크게 변하지 않도록 범위를 조정합니다.
            # 기본 크기를 크게 조정한 만큼 최대값도 넉넉하게 늘려 600까지 허용합니다.
            new_size = max(80, min(600, new_size))
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

    def startDrag(self, supportedActions):
        """
        선택한 항목을 드래그할 때 표시되는 프리뷰를 꾸밈니다. 첫 번째 선택된 이미지의
        썸네일을 가져와 투명한 배경 위에 그리며, 여러 장을 선택한 경우 반투명
        오버레이와 숫자를 표시합니다. 이렇게 하면 기본 드래그 아이콘보다 세련된
        시각적 피드백을 제공합니다.
        """
        items = self.selectedItems()
        if not items:
            return
        drag = QDrag(self)
        mime = self.mimeData(items)
        drag.setMimeData(mime)

        # 드래그 프리뷰용 pixmap 생성
        size = self.iconSize()
        if size.width() <= 0 or size.height() <= 0:
            size = QSize(self._thumb_size, self._thumb_size)
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

        # 첫 번째 선택된 항목의 썸네일을 가져와 그립니다.
        first_item = items[0]
        widget = self.itemWidget(first_item)
        src_pix = None
        if widget and hasattr(widget, 'image_label'):
            src_pix = widget.image_label.pixmap()
        if src_pix is not None and not src_pix.isNull():
            scaled = src_pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (size.width() - scaled.width()) // 2
            y = (size.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)

        # 여러 장을 선택한 경우, 어두운 오버레이와 개수 표시
        if len(items) > 1:
            painter.fillRect(pixmap.rect(), QColor(0, 0, 0, 128))
            painter.setPen(QPen(Qt.white))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, str(len(items)))
        painter.end()
        drag.setPixmap(pixmap)
        # 핫스팟을 픽스맵의 하단 중앙으로 지정하여 드래그 이미지가
        # 선택한 썸네일과 파일명 위로 떠오르도록 합니다. 이렇게 하면 드래그 미리보기가
        # 실제 항목을 가리지 않고 위쪽에 위치합니다.
        drag.setHotSpot(QPoint(size.width() // 2, size.height()))

        # 드래그 실행: 이동 동작을 사용하여 드래그되는 동안 마우스 커서가 이동 모양을 보입니다.
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
        """
        마우스 휠로 줌 인/아웃을 수행합니다. 별도의 modifier 키를 누를 필요 없이
        일반 휠 동작도 확대/축소를 담당합니다. Pan 동작은 마우스 드래그로 수행합니다.
        """
        # 스크롤 변위를 계산하여 확대/축소 단계를 결정합니다.
        if self._zoom_callback is not None:
            delta_y = event.angleDelta().y()
            if delta_y != 0:
                steps = delta_y / 120.0
                self._zoom_callback(steps)
                event.accept()
                return
        # 줌 콜백이 없으면 기본 동작 수행
        super().wheelEvent(event)


# ------------------------------------------------------------
# 메인 윈도우
# ------------------------------------------------------------
class GridSelectorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 기본 제목 및 크기 설정
        # 프로그램 이름을 사용자 요구에 따라 변경합니다.
        self.setWindowTitle("시퀀셜 셀럭터")
        # 초기 창 크기를 설정합니다. 너무 큰 값 대신 적절한 비율을 사용하여 OS마다 알맞은 크기를 보장합니다.
        self.resize(1400, 850)

        self.current_folder: Path | None = None
        self.target_folder1: Path | None = None
        self.target_folder2: Path | None = None

        self.preview_pixmaps = [None, None]
        self.zoom_factors = [1.0, 1.0]
        self.zoom_linked: bool = True

        self.target_click_mode: int | None = None

        # 숫자 키를 누르고 있는 동안의 타겟. 1 또는 2. 키 릴리즈 시 처리 후 None으로 초기화됩니다.
        self.key_down_target: int | None = None

        # 키를 누르고 있는 동안 이동 동작이 발생했는지 여부. keyReleaseEvent에서 처리할 때 사용합니다.
        self.moved_during_key_down: bool = False

        self.thumb_thread: QThread | None = None
        self.thumb_worker: ThumbnailWorker | None = None

        self._scroll_sync_guard = False

        self._setup_ui()
        self._setup_scroll_sync()

        # 프리뷰 이미지 캐시: 최근에 본 이미지의 PIL 데이터를 캐싱하여 재로딩 비용을 줄입니다.
        # OrderedDict를 사용해 간단한 LRU 캐시를 구현합니다.
        self._preview_cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._cache_capacity: int = 20

        # 이동 애니메이션을 추적하기 위한 목록입니다. 애니메이션 객체를 저장해
        # 가비지 컬렉션으로 인한 조기 종료를 방지합니다.
        self._animations: list[QPropertyAnimation] = []

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

            /* 선택된 아이템을 시각적으로 강조합니다. 녹색 테두리와 반투명 배경으로 선택 영역이 뚜렷하게 보입니다. */
            QListWidget::item:selected {
                background-color: rgba(76, 175, 80, 80);
                border: 1px solid #4CAF50;
                border-radius: 4px;
            }
            /* Glass panel style to approximate Material surfaces: semi-transparent with subtle border */
            QFrame#glassPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 rgba(255, 255, 255, 10),
                                           stop:1 rgba(255, 255, 255, 5));
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 16px;
            }

            /* 드래그 박스(다중 선택 사각형)를 세련되게 꾸밉니다. */
            QRubberBand {
                border: 2px dashed #4CAF50;
                background-color: rgba(76, 175, 80, 40);
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

        # 메인 윈도우가 리스트 위젯의 키 이벤트를 처리할 수 있도록 이벤트 필터를 설치합니다.
        self.list_widget.installEventFilter(self)
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
            "- 1 키 누른 상태 + 클릭: 키를 누르고 있는 동안 클릭한 사진을 Target1 폴더로 이동 (Target1만 설정되어도 동작)\n"
            "- 2 키 누른 상태 + 클릭: 키를 누르고 있는 동안 클릭한 사진을 Target2 폴더로 이동 (Target2만 설정되어도 동작)\n"
            "- 키를 떼었을 때 선택된 사진이 없으면 다음 클릭에서 이동 (1 또는 2 키)\n"
            "- 드래그 박스: 여러 장 선택\n"
            "- 드래그 선택 후 1 키를 눌렀다 놓기: 선택된 모든 사진을 Target1 폴더로 이동\n"
            "- 드래그 선택 후 2 키를 눌렀다 놓기: 선택된 모든 사진을 Target2 폴더로 이동\n\n"
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

        # 다중 선택 시 바로 이동: 선택된 항목이 있다면 1 또는 2 키를 눌러 해당 타겟으로 이동합니다.
        # 숫자키 1 또는 2가 눌렸을 때: 키를 누르고 있는 동안의 타겟을 설정합니다.
        # 이동 동작은 keyReleaseEvent 또는 클릭 이벤트에서 처리됩니다.
        if key == Qt.Key_1 and self.target_folder1 is not None:
            self.key_down_target = 1
            return
        if key == Qt.Key_2 and self.target_folder2 is not None:
            self.key_down_target = 2
            return

        # 기타 키 이벤트는 기본 처리에 위임합니다.
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        # 숫자 키(1,2) 릴리즈 시: 선택된 항목을 이동하거나 다음 클릭에서 이동하도록 설정합니다.
        if event.key() == Qt.Key_1 and self.target_folder1 is not None:
            # 1번 키 릴리즈
            if self.key_down_target == 1:
                if self.moved_during_key_down:
                    # 키를 누른 상태에서 이미 이동이 발생했다면 추가 모드를 설정하지 않음
                    self.target_click_mode = None
                    self.moved_during_key_down = False
                else:
                    selected = self.list_widget.selectedItems()
                    if len(selected) > 0:
                        self.move_selected_to_target(1)
                        self.target_click_mode = None
                    else:
                        # 선택된 항목이 없으면 다음 클릭에서 이동하도록 설정
                        self.target_click_mode = 1
            self.key_down_target = None
            super().keyReleaseEvent(event)
            return
        if event.key() == Qt.Key_2 and self.target_folder2 is not None:
            # 2번 키 릴리즈
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
        # 새로운 폴더를 선택할 때 썸네일 리스트를 초기화하고 현재 썸네일 크기와 그리드 크기를 다시 설정합니다.
        self.list_widget.clear()
        # 현재 리스트 위젯의 썸네일 크기에 맞춰 아이콘 크기와 그리드 크기를 재설정합니다.
        thumb_size = self.list_widget._thumb_size
        pad_w = self.list_widget._grid_padding_w
        pad_h = self.list_widget._grid_padding_h
        self.list_widget.setIconSize(QSize(thumb_size, thumb_size))
        self.list_widget.setGridSize(QSize(thumb_size + pad_w, thumb_size + pad_h))

        all_files = []
        for entry in sorted(folder.iterdir()):
            if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXT:
                all_files.append(str(entry))

        if not all_files:
            QMessageBox.information(self, "Info", "지원하는 이미지 파일이 없습니다.")
            return

        for path_str in all_files:
            p = Path(path_str)
            # QListWidgetItem을 생성하고 파일 경로를 저장합니다.
            item = QListWidgetItem()
            item.setData(Qt.UserRole, path_str)
            # 파일명을 툴팁으로 설정하여 필요 시 전체 이름을 확인할 수 있습니다.
            item.setToolTip(p.name)
            # 커스텀 썸네일 위젯을 생성하여 이미지와 파일명을 표시합니다.
            thumb_widget = ThumbnailWidget(p.name, self.list_widget._thumb_size)
            # 투명한 플레이스홀더를 설정하여 초기 셀 크기가 유지되도록 합니다.
            placeholder = QPixmap(self.list_widget._thumb_size, self.list_widget._thumb_size)
            placeholder.fill(Qt.transparent)
            thumb_widget.set_pixmap(placeholder)
            self.list_widget.addItem(item)
            # 아이템에 위젯을 배치합니다.
            self.list_widget.setItemWidget(item, thumb_widget)
            # 각 항목의 추천 크기를 설정하여 커스텀 위젯이 올바르게 표시되도록 합니다.
            item.setSizeHint(QSize(thumb_size + pad_w, thumb_size + pad_h))

        # QListWidgetItem의 정렬을 수행하지 않습니다. 파일 목록은 이미 사전 정렬되어 있으며,
        # 항목을 정렬하면 인덱스와 파일 매핑이 변경되어 썸네일이 올바르게 표시되지 않을 수 있습니다.

        # 스레드를 사용하지 않고 즉시 썸네일을 생성하여 목록에 표시합니다.
        # 많은 파일을 처리할 경우 UI의 응답성을 위해 이벤트 루프를 간헐적으로 처리합니다.
        for idx, path_str in enumerate(all_files):
            # 로딩 중 사용자가 다른 폴더를 선택했을 경우 중단합니다.
            if self.current_folder != folder:
                break
            path_obj = Path(path_str)
            try:
                img = load_pil_image(path_obj, max_size=self.list_widget._thumb_size)
                qimg = pil_to_qimage(img)
                pixmap = QPixmap.fromImage(qimg)
                if not pixmap.isNull():
                    item = self.list_widget.item(idx)
                    if item is not None:
                        # 커스텀 위젯을 가져와 썸네일을 설정합니다.
                        widget = self.list_widget.itemWidget(item)
                        if isinstance(widget, ThumbnailWidget):
                            widget.set_pixmap(pixmap)
            except Exception:
                pass
            QApplication.processEvents()

        # 썸네일이 모두 설정되었으므로 리스트를 업데이트합니다.
        self.list_widget.updateGeometry()
        self.list_widget.repaint()

    def _stop_thumb_thread(self):
        # 워커와 스레드가 존재하면 안전하게 중지하고 리소스를 정리합니다.
        if self.thumb_worker is not None:
            try:
                self.thumb_worker.abort()
            except Exception:
                pass
        if self.thumb_thread is not None:
            try:
                # 이미 삭제된 스레드에 대해 quit를 호출하면 RuntimeError가 발생할 수 있으므로 예외 처리합니다.
                self.thumb_thread.quit()
            except RuntimeError:
                pass
            except Exception:
                pass
            try:
                self.thumb_thread.wait()
            except RuntimeError:
                pass
            except Exception:
                pass
            try:
                # finished 시 자동 deleteLater를 연결하지 않았으므로 직접 삭제합니다.
                self.thumb_thread.deleteLater()
            except Exception:
                pass
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

        # 키를 누르고 있는 동안 클릭: 즉시 이동
        if self.key_down_target == 1 and self.target_folder1 is not None:
            self.move_items_to_folder([item], self.target_folder1)
            # 키를 누른 상태에서 이동이 발생했음을 기록하여 keyRelease 처리 시 재이동을 방지합니다.
            self.moved_during_key_down = True
            return
        if self.key_down_target == 2 and self.target_folder2 is not None:
            self.move_items_to_folder([item], self.target_folder2)
            self.moved_during_key_down = True
            return

        # 키를 눌렀다 놓은 후 첫 클릭: pending 모드
        if self.target_click_mode == 1 and self.target_folder1 is not None:
            self.move_items_to_folder([item], self.target_folder1)
            self.target_click_mode = None
            return
        if self.target_click_mode == 2 and self.target_folder2 is not None:
            self.move_items_to_folder([item], self.target_folder2)
            self.target_click_mode = None
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
        """선택된 항목들을 지정된 폴더로 이동하고, 이동된 항목은 페이드 아웃 애니메이션으로 제거합니다."""
        for item in items:
            path_str = item.data(Qt.UserRole)
            if not path_str:
                continue
            src = Path(path_str)
            if not src.exists():
                continue

            # 대상 경로를 계산하고 이름 충돌을 회피합니다.
            dst = folder / src.name
            base = dst.stem
            ext = dst.suffix
            i = 1
            while dst.exists():
                dst = folder / f"{base}_{i}{ext}"
                i += 1

            try:
                shutil.move(str(src), str(dst))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"파일 이동 실패:\n{e}")
                return

            # 실제 파일을 이동한 후 리스트에서 항목을 페이드 아웃시키면서 제거합니다.
            self.animate_item_removal(item)

    # --------------------------------------------------------
    # 항목 제거 애니메이션
    # --------------------------------------------------------
    def animate_item_removal(self, item: QListWidgetItem):
        """
        지정된 리스트 항목에 페이드 아웃 애니메이션을 적용한 뒤 리스트에서 제거합니다.
        Material Design의 페이드 패턴에서는 UI 요소가 화면 내에서 사라질 때
        불투명도가 빠르게 감소하여 사용자에게 자연스러운 전환을 제공합니다【91608521861655†L1262-L1279】.
        또한 작은 요소에는 75~150ms 사이의 짧은 애니메이션을 사용하도록 권장합니다【91608521861655†L1348-L1352】.
        """
        # 해당 항목에 연결된 커스텀 위젯을 가져옵니다.
        widget = self.list_widget.itemWidget(item)
        if widget is None:
            # 커스텀 위젯이 없으면 즉시 제거
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
            return

        # 불투명도 효과를 적용합니다.
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        # 애니메이션 생성
        anim = QPropertyAnimation(effect, b"opacity", self)
        # 애니메이션 지속 시간을 Material Motion 가이드라인에 따라 설정합니다.
        anim.setDuration(120)  # 작은 요소에는 짧은 지속 시간을 사용
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        # 입출력 곡선: 빠르게 시작하여 서서히 사라지도록 합니다.
        anim.setEasingCurve(QEasingCurve.InQuad)

        def on_finished():
            # 애니메이션이 끝나면 리스트에서 항목을 제거하고 위젯을 삭제합니다.
            row = self.list_widget.row(item)
            if row >= 0:
                self.list_widget.takeItem(row)
            try:
                widget.deleteLater()
            except Exception:
                pass
            # 애니메이션 객체를 목록에서 제거하여 메모리를 해제합니다.
            try:
                self._animations.remove(anim)
            except ValueError:
                pass

        anim.finished.connect(on_finished)
        # 애니메이션 객체를 저장하여 가비지 컬렉션을 방지합니다.
        self._animations.append(anim)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    # --------------------------------------------------------
    # 종료 처리
    # --------------------------------------------------------
    def closeEvent(self, event):
        self._stop_thumb_thread()
        super().closeEvent(event)

    # 이벤트 필터를 통해 리스트 위젯의 키 이벤트를 메인 윈도우로 전달합니다.
    def eventFilter(self, obj, event):
        # 리스트 위젯에서 발생한 키 이벤트를 메인 윈도우의 핸들러로 전달합니다.
        if obj is self.list_widget:
            if event.type() == QEvent.KeyPress:
                # 메인 윈도우의 keyPressEvent를 호출합니다.
                self.keyPressEvent(event)
                return True
            if event.type() == QEvent.KeyRelease:
                self.keyReleaseEvent(event)
                return True
        # 그 외의 경우 기본 동작 유지
        return super().eventFilter(obj, event)

    # 중복된 _stop_thumb_thread 정의 제거: 안전한 스레드 정지 로직은 상단에 정의되어 있습니다.


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
