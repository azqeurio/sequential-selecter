import sys
import os
import shutil
from pathlib import Path

import rawpy
import io
from PIL import Image, ImageOps
import pillow_heif

from PySide6.QtCore import (
    Qt, QSize, QThread, Signal, QObject, QEasingCurve, QPropertyAnimation, QRect, QPoint,
    QMetaObject, QUrl
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
    QSizePolicy
)

from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect

from PySide6.QtCore import QTimer
from PySide6.QtCore import QEvent

from collections import OrderedDict
import concurrent.futures


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
        """
        RAW 포맷은 여러 단계를 거쳐 로드합니다.

        1. 니콘 NEF의 경우 VibeCulling과 동일하게 먼저 내장 썸네일을 추출합니다. 이는
           고효율(★) 압축 NEF에서 rawpy의 postprocess가 실패하는 경우에도 프리뷰를
           표시하기 위한 방법입니다.
        2. 그 외의 RAW는 rawpy.postprocess를 통해 디코딩을 시도하고, 실패하면 썸네일을
           추출합니다.
        3. rawpy 자체가 파일을 열지 못하면 HEIF 및 일반 Pillow 로더를 차례로 시도합니다.
        """
        # 먼저 NIikon NEF에 특화된 처리: 썸네일 우선 추출.
        if ext == ".nef":
            try:
                with rawpy.imread(str(path)) as raw:
                    try:
                        thumb = raw.extract_thumb()
                        if thumb.format == rawpy.ThumbFormat.JPEG:
                            img = Image.open(io.BytesIO(thumb.data))
                        elif thumb.format == rawpy.ThumbFormat.BITMAP:
                            img = Image.fromarray(thumb.data)
                        else:
                            img = None
                        if img is not None:
                            # orientation 등의 추가 처리가 필요하다면 여기서 수행할 수 있습니다.
                            pass
                        else:
                            # 썸네일 형식을 지원하지 않으면 postprocess로 시도합니다.
                            rgb = raw.postprocess(
                                use_camera_wb=True,
                                no_auto_bright=True,
                                output_bps=8,
                                half_size=True
                            )
                            img = Image.fromarray(rgb)
                    except Exception:
                        # 썸네일 추출 또는 postprocess 실패 시 예외 발생 시 다음 단계로 넘어갑니다.
                        raise
            except Exception:
                # rawpy에서 파일을 읽지 못한 경우 아래 일반 RAW 처리 루틴으로 넘어갑니다.
                img = None
        else:
            img = None
        # NEF에서 내장 썸네일을 추출했거나 기타 RAW에서 postprocess를 수행한 경우 img가 설정됩니다.
        if img is None:
            try:
                with rawpy.imread(str(path)) as raw:
                    try:
                        rgb = raw.postprocess(
                            use_camera_wb=True,
                            no_auto_bright=True,
                            output_bps=8,
                            half_size=True
                        )
                        img = Image.fromarray(rgb)
                    except Exception:
                        # 일반 RAW에서도 postprocess가 실패하면 썸네일을 추출합니다.
                        try:
                            thumb = raw.extract_thumb()
                            if thumb.format == rawpy.ThumbFormat.JPEG:
                                img = Image.open(io.BytesIO(thumb.data))
                            elif thumb.format == rawpy.ThumbFormat.BITMAP:
                                img = Image.fromarray(thumb.data)
                            else:
                                img = None
                        except Exception:
                            img = None
            except Exception:
                img = None
        # rawpy 경로에서 img를 얻지 못한 경우 HEIF나 Pillow 로더를 시도합니다.
        if img is None:
            try:
                heif_file = pillow_heif.read_heif(str(path))
                img = Image.frombytes(
                    heif_file.mode,
                    heif_file.size,
                    heif_file.data,
                    "raw"
                )
            except Exception:
                try:
                    img = Image.open(str(path))
                    img.load()
                except Exception:
                    raise
    else:
        img = Image.open(str(path))
        img.load()

    # --- EXIF 방향 자동 회전 ---
    try:
        # Pillow의 ImageOps.exif_transpose는 EXIF Orientation 태그를 읽어
        # 이미지의 실제 방향에 맞게 회전/반전합니다. Orientation이 없으면
        # 원본 이미지를 그대로 반환합니다.
        img = ImageOps.exif_transpose(img)
    except Exception:
        # exif 정보를 읽을 수 없거나 오류가 발생해도 무시하고 원본 사용
        pass
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
                /* 드래그 대상 라벨을 더 밝은 색상으로 조정하여 배경과 구분됩니다 */
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
# 클릭 + modifier용 리스트 위젯
# ------------------------------------------------------------
class ImageListWidget(QListWidget):
    clicked_with_modifiers = Signal(QListWidgetItem, Qt.KeyboardModifiers)

    # Signal emitted whenever the thumbnail size changes via zoom. The new
    # thumbnail size (int) is passed as an argument. The main window
    # listens to this signal to reload thumbnails at a higher resolution
    # when the user zooms in so that image quality is maintained.
    thumbSizeChanged = Signal(int)

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
            # Record the starting position for drag/selection. Use event.position() if
            # available; otherwise compute from x/y coordinates to avoid the deprecated
            # pos() method. This avoids DeprecationWarning on newer PySide versions.
            if hasattr(event, 'position'):
                pos = event.position().toPoint()
            else:
                # Fall back to x() and y() rather than pos() to prevent deprecation
                pos = QPoint(event.x(), event.y())
            self._drag_start_pos = pos
            self._rubber_start_pos = pos
        # 기존 로직: modifier 정보와 함께 클릭 시그널을 전달합니다.
        # Determine the position used for emitting the click-with-modifier signal.
        if hasattr(event, 'position'):
            pos_for_mod = event.position().toPoint()
        else:
            pos_for_mod = QPoint(event.x(), event.y())
        item = self.itemAt(pos_for_mod)
        if item is not None:
            self.clicked_with_modifiers.emit(item, event.modifiers())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # 드래그 시작 위치가 기록되어 있고, 일정 거리 이상 이동한 경우 드래그를 시작합니다.
        # 현재 마우스 위치
        # Use position() if available; otherwise derive from x/y to avoid deprecated pos()
        current_pos = event.position().toPoint() if hasattr(event, 'position') else QPoint(event.x(), event.y())
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

    def keyPressEvent(self, event):
        """
        화살표 키로 썸네일 간 이동 및 Enter 키를 이용한 키보드 기반 분류를 지원합니다.
        좌우 화살표는 한 칸씩 이동하고, 상하 화살표는 현재 뷰포트 폭을 기준으로
        계산된 열 수만큼 이동합니다. Enter 또는 Return 키를 누르면 현재 항목을
        클릭한 것과 동일한 동작을 수행합니다.
        """
        key = event.key()
        # 화살표 키 처리
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            count = self.count()
            if count == 0:
                return
            current = self.currentRow()
            if current < 0:
                current = 0
            # 셀 폭을 이용하여 현재 뷰포트에서 몇 개의 열이 표시되는지 계산
            try:
                grid_w = self.gridSize().width()
            except Exception:
                grid_w = self._thumb_size + self._grid_padding_w
            viewport_width = self.viewport().width()
            columns = max(1, viewport_width // grid_w)
            new_index = current
            if key == Qt.Key_Left:
                new_index = max(0, current - 1)
            elif key == Qt.Key_Right:
                new_index = min(count - 1, current + 1)
            elif key == Qt.Key_Up:
                new_index = max(0, current - columns)
            elif key == Qt.Key_Down:
                new_index = min(count - 1, current + columns)
            if new_index != current:
                item = self.item(new_index)
                if item:
                    # 선택 및 커서 이동
                    self.setCurrentRow(new_index)
                    # 단순 선택으로 변경 (Ctrl/Shift 없이)
                    self.clearSelection()
                    item.setSelected(True)
                    # 항목 클릭과 동일하게 신호를 발행하여 프리뷰 및 기타 처리를 수행합니다.
                    self.clicked_with_modifiers.emit(item, Qt.NoModifier)
                self.scrollToItem(self.item(new_index))
            return
        # Enter 키를 클릭 동작으로 처리
        if key in (Qt.Key_Return, Qt.Key_Enter):
            current = self.currentRow()
            if current >= 0:
                item = self.item(current)
                if item:
                    # 현재 선택을 유지하고 클릭 신호를 보냅니다.
                    self.clicked_with_modifiers.emit(item, event.modifiers())
            return
        # 숫자키(1, 2)는 부모 윈도우에서 처리하도록 무시하여 이벤트가 버블되게 합니다.
        if key in (Qt.Key_1, Qt.Key_2):
            event.ignore()
            return
        # 기타 키는 기본 처리
        super().keyPressEvent(event)

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
            # 최대값을 1600까지 늘려 더 큰 배율로 확대할 수 있습니다.
            # 그리드 뷰 확대 한계를 높여 사용자가 더 크게 볼 수 있게 합니다.
            new_size = max(80, min(1600, new_size))
            self._thumb_size = new_size
            icon_size = QSize(self._thumb_size, self._thumb_size)
            # 그리드 크기는 여백을 고려하여 조정합니다.
            grid_w = self._thumb_size + self._grid_padding_w
            # 이미지 아래에 텍스트 라인이 없어도 여유 공간을 확보합니다.
            grid_h = self._thumb_size + self._grid_padding_h
            self.setIconSize(icon_size)
            self.setGridSize(QSize(grid_w, grid_h))
            # 썸네일 위젯의 크기를 동적으로 업데이트합니다. 기존 위젯의 이미지 라벨을
            # 새로운 썸네일 크기에 맞춰 조정하여 확대 시 이미지가 작게 보이지 않도록 합니다.
            for i in range(self.count()):
                item = self.item(i)
                widget = self.itemWidget(item)
                if isinstance(widget, ThumbnailWidget):
                    widget.thumb_size = self._thumb_size
                    widget.image_label.setFixedSize(self._thumb_size, self._thumb_size)
                    # 이미지가 이미 설정되어 있다면 재설정하여 새 크기로 스케일링
                    pix = widget.image_label.pixmap()
                    if pix is not None and not pix.isNull():
                        widget.set_pixmap(pix)
                    # 항목의 힌트 크기도 업데이트
                    item.setSizeHint(QSize(self._thumb_size + self._grid_padding_w,
                                           self._thumb_size + self._grid_padding_h))
            # 레이아웃을 다시 계산하도록 요청합니다.
            self.updateGeometry()
            # 썸네일 크기 변경 시그널을 발행하여 메인 윈도우에서 고해상도
            # 썸네일을 다시 로드할 수 있도록 합니다. 이렇게 하면 사용자가
            # 확대했을 때 더 선명한 이미지를 볼 수 있습니다.
            self.thumbSizeChanged.emit(self._thumb_size)
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
            # Record the last mouse position for panning. Use event.position() when
            # available; otherwise derive from x/y to avoid deprecated pos().
            if hasattr(event, 'position'):
                self._last_pos = event.position().toPoint()
            else:
                self._last_pos = QPoint(event.x(), event.y())
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._last_pos is not None:
            # Use event.position() when available; otherwise compute from x/y
            if hasattr(event, 'position'):
                current_pos = event.position().toPoint()
            else:
                current_pos = QPoint(event.x(), event.y())
            delta = current_pos - self._last_pos
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(hbar.value() - delta.x())
            vbar.setValue(vbar.value() - delta.y())
            self._last_pos = current_pos
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
    # 비동기 로딩된 썸네일을 메인 스레드에서 처리하기 위한 시그널
    thumbnail_loaded = Signal(str, QImage)
    def __init__(self):
        super().__init__()
        # 기본 제목 및 크기 설정
        # 프로그램 이름을 사용자 요구에 따라 변경합니다.
        self.setWindowTitle("시퀀셜 셀럭터")
        # 애플리케이션 아이콘 설정: exe로 빌드했을 때에도 아이콘이 적용되도록
        # 현재 스크립트와 같은 폴더에 'sqs.ico' 파일이 있는 경우 사용합니다.
        try:
            icon_path = Path(__file__).resolve().parent / 'sqs.ico'
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
        except Exception:
            pass
        # 초기 창 크기를 설정합니다. 너무 큰 값 대신 적절한 비율을 사용하여 OS마다 알맞은 크기를 보장합니다.
        self.resize(1400, 850)

        self.current_folder: Path | None = None
        self.target_folder1: Path | None = None
        self.target_folder2: Path | None = None

        self.preview_pixmaps = [None, None]
        # 확대/축소 배율을 각 프리뷰 슬롯에 저장합니다.
        self.zoom_factors = [1.0, 1.0]
        self.zoom_linked: bool = True

        # 프리뷰 슬롯의 스크롤 위치를 저장합니다. (h_scroll, v_scroll)
        # 새 이미지를 로드할 때 이전 확대/스크롤 상태를 유지하기 위해 사용됩니다.
        self.preview_scroll_values: list[tuple[int, int]] = [(0, 0), (0, 0)]

        # 목록에서 마지막으로 클릭한 행의 인덱스를 저장하여 Shift+클릭 범위 선택에 사용합니다.
        self.last_clicked_row: int | None = None

        self.target_click_mode: int | None = None

        # 숫자 키를 누르고 있는 동안의 타겟. 1 또는 2. 키 릴리즈 시 처리 후 None으로 초기화됩니다.
        self.key_down_target: int | None = None

        # 키를 누르고 있는 동안 이동 동작이 발생했는지 여부. keyReleaseEvent에서 처리할 때 사용합니다.
        self.moved_during_key_down: bool = False

        self.thumb_thread: QThread | None = None
        self.thumb_worker: ThumbnailWorker | None = None

        # Undo stack for file moves. Each entry is a list of (src, dst) tuples recorded when moving files.
        self.undo_stack: list[list[tuple[Path, Path]]] = []

        # Redo stack for undone moves. Ctrl+Y will reapply the last undone operation.
        self.redo_stack: list[list[tuple[Path, Path]]] = []

        self._scroll_sync_guard = False

        # Initialize language and translations before setting up UI. This ensures
        # that update_language() has access to self.language and self.translations
        # when called within _setup_ui().
        self.language: str = 'ko'
        self.translations = {
            'ko': {
                'title': '시퀀셜 셀럭터',
                'select_folder': 'Image Folder',  # Use English term as per user preference
                'target1': 'Target1',
                'target2': 'Target2',
                'zoom_link': '독립 줌 모드',
                'zoom_link_on': '공통 줌 모드',
                'help': '도움말',
                'dual_mode': '듀얼 모드',
                'single_mode': '단일 모드',
                'donate': '후원하기',
                'language': 'English',
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
                'slot1_prompt': 'Thumbnail click → Slot1 preview (upper)',
                'slot2_prompt': 'Ctrl+Click → Slot2 preview (lower)',
                'empty': 'Empty'
            }
        }

        # Define dual mode state before UI setup. This ensures update_language()
        # can reference self.dual_mode_enabled safely during initial UI construction.
        self.dual_mode_enabled: bool = False
        self.dual_window: QMainWindow | None = None

        # Set up the user interface. update_language() will be called within
        # _setup_ui(), and since self.language and dual_mode_enabled are now defined,
        # it will work correctly.
        self._setup_ui()
        self._setup_scroll_sync()

        # Ctrl+Z to undo last move
        self.undo_shortcut = QShortcut(QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self.undo_last_move)

        # Ctrl+Y to redo last undone move
        self.redo_shortcut = QShortcut(QKeySequence("Ctrl+Y"), self)
        self.redo_shortcut.activated.connect(self.redo_last_move)

        # Ctrl+D로 듀얼 모드를 토글할 수 있도록 단축키를 등록합니다.
        self.dual_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        # 토글 상태를 전환하기 위해 버튼의 toggle 슬롯을 호출합니다.
        self.dual_shortcut.activated.connect(self.btn_dual_mode.toggle)

        # 프리뷰 이미지 캐시: 최근에 본 이미지의 PIL 데이터를 캐싱하여 재로딩 비용을 줄입니다.
        # OrderedDict를 사용해 간단한 LRU 캐시를 구현합니다.
        self._preview_cache: OrderedDict[str, Image.Image] = OrderedDict()
        self._cache_capacity: int = 20

        # 이동 애니메이션을 추적하기 위한 목록입니다. 애니메이션 객체를 저장해
        # 가비지 컬렉션으로 인한 조기 종료를 방지합니다.
        self._animations: list[QPropertyAnimation] = []

        # 스레드 풀을 사용하여 썸네일을 병렬로 로딩합니다. CPU 코어 수에 따라 워커 수를 결정합니다.
        # 폴더 로드 버전을 추적하여 이전 로딩 작업이 완료되어도 최신 폴더에 영향을 주지 않도록 합니다.
        try:
            max_workers = os.cpu_count() or 4
        except Exception:
            max_workers = 4
        self.thumb_executor: concurrent.futures.ThreadPoolExecutor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        )
        self.thumb_load_version: int = 0

        # 스레드풀에서 로딩된 썸네일을 UI에 적용하기 위한 시그널 연결
        self.thumbnail_loaded.connect(self._apply_thumbnail)

        # 듀얼 모드 상태는 __init__ 초기에 정의되므로 여기서는 다시 정의하지 않음

        # Connect the thumbnail size changed signal from the list widget to
        # reload thumbnails at a higher resolution when the user zooms the grid.
        # The slot on_thumb_size_changed will handle reloading while
        # preserving the current selection.
        self.list_widget.thumbSizeChanged.connect(self.on_thumb_size_changed)


        # --- Thumbnail reload throttling ---
        # To avoid reloading thumbnails on every incremental zoom step (which can
        # cause many slow disk I/O operations), we throttle reloads using a
        # single-shot QTimer. When a new thumbnail size comes in from the
        # list widget, we record the pending size and start/restart the
        # timer. When the timer fires, we perform the reload only if the
        # requested size differs significantly from the last loaded size.
        # The last loaded size is recorded in self.last_loaded_thumb_size.
        # The pending size awaiting reload is stored in self._pending_thumb_size.
        self.last_loaded_thumb_size: int = self.list_widget._thumb_size
        self._pending_thumb_size: int | None = None
        self._thumb_reload_timer: QTimer = QTimer(self)
        self._thumb_reload_timer.setSingleShot(True)
        # 250ms delay – reload after user stops zooming
        self._thumb_reload_timer.setInterval(250)
        self._thumb_reload_timer.timeout.connect(self._do_thumb_reload)

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
                /* 버튼 배경과 테두리를 조금 더 밝게 조정하여 시각적인 대비를 높입니다 */
                background-color: #3A3A3A;
                border: 1px solid #666666;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 10pt;
            }
            QPushButton:hover {
                /* 호버 시 더 밝은 회색 */
                background-color: #555555;
            }
            QPushButton:pressed {
                /* 눌린 상태는 조금 더 어둡게 */
                background-color: #2E2E2E;
            }
            QLabel {
                border: none;
            }
            QSlider::groove:horizontal {
                /* 슬라이더 홈을 살짝 밝게 조정 */
                border: 1px solid #666666;
                height: 4px;
                background: #505050;
                margin: 0px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                /* 핸들을 Material 색상보다 조금 밝은 녹색으로 변경 */
                background: #81C784;
                border: 1px solid #81C784;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #81C784;
            }
            QSplitter::handle {
                /* 스플리터 핸들을 조금 더 밝게 */
                background-color: #4A4A4A;
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
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_widget.setMinimumWidth(150)
        self.splitter_main.addWidget(self.right_widget)

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

        # 언어 토글 버튼: UI와 도움말 언어를 한국어와 영어로 전환합니다.
        self.btn_language = QPushButton()
        self.btn_language.setFixedHeight(32)
        self.btn_language.clicked.connect(self.toggle_language)
        top_btn_layout.addWidget(self.btn_language)

        # 후원하기 버튼: BuyMeACoffee 링크로 연결됩니다. 작은 크기로 설정합니다.
        self.btn_donate = QPushButton()
        self.btn_donate.setFixedHeight(32)
        # 후원하기 버튼은 폭을 줄여 다른 버튼보다 작게 만듭니다.
        self.btn_donate.setFixedWidth(90)
        self.btn_donate.clicked.connect(self.open_donate_link)
        top_btn_layout.addWidget(self.btn_donate)

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
        # 수직 스플리터를 속성으로 저장하여 듀얼 모드에서 재배치할 수 있도록 합니다.
        self.splitter_right = QSplitter(Qt.Vertical)
        self.right_layout.addWidget(self.splitter_right)

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
        self.splitter_right.addWidget(slot1_frame)

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
        self.splitter_right.addWidget(slot2_frame)

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

        self.splitter_right.setStretchFactor(0, 1)
        self.splitter_right.setStretchFactor(1, 1)

        # 아래쪽: 드롭 타겟 + 줌 링크 + 단축키 안내
        bottom_layout = QHBoxLayout()
        self.right_layout.addLayout(bottom_layout)

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

        # 도움말 버튼: 프로그램 사용 설명서를 표시합니다.
        self.btn_help = QPushButton("도움말")
        self.btn_help.clicked.connect(self.show_help)
        self.btn_help.setFixedHeight(32)
        bottom_layout.addWidget(self.btn_help)

        # 듀얼 모드 토글 버튼: 그리드와 프리뷰를 별도 창으로 분리/합치기
        self.btn_dual_mode = QPushButton("듀얼 모드")
        self.btn_dual_mode.setCheckable(True)
        self.btn_dual_mode.setFixedHeight(32)
        self.btn_dual_mode.toggled.connect(self.toggle_dual_mode)
        bottom_layout.addWidget(self.btn_dual_mode)

        # After UI components are created, apply the initial language setting.
        # This ensures that buttons like language toggle and donate are labeled correctly.
        self.update_language()

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
        else:
            self.zoom_linked = True
            value = self.slider_zoom_1.value()
            self.slider_zoom_2.blockSignals(True)
            self.slider_zoom_2.setValue(value)
            self.slider_zoom_2.blockSignals(False)
            self.zoom_factors[0] = self.zoom_factors[1] = value / 100.0
            self.apply_zoom(0)
            self.apply_zoom(1)
        # Update button text according to language
        self.update_language()

    # --------------------------------------------------------
    # 도움말: 프로그램 사용 설명서
    # --------------------------------------------------------
    def show_help(self):
        """
        표시되는 도움말 창이 너무 길어 한 화면에 보이지 않는 문제를 해결하기 위해,
        스크롤 가능한 대화상자를 생성하여 프로그램 사용 설명서를 보여줍니다. 이
        창은 사용자가 드래그하여 크기를 조절할 수 있으며, 텍스트 내용을 선택하거나
        복사할 수 있습니다.
        """
        # 도움말 텍스트를 언어에 따라 선택합니다.
        if self.language == 'en':
            text = (
                "※ Program Usage Guide\n\n"
                "■ Folder setup\n"
                "- Use the Image Folder button to select the folder containing your original images.\n"
                "- Use the Target1 and Target2 buttons to choose destination folders for classification.\n\n"
                "■ Image selection and movement\n"
                "- Click: show the selected photo in the Slot1 preview.\n"
                "- Ctrl + click: show the selected photo in the Slot2 preview.\n"
                "- Shift + click: select all items between the last clicked and the current item.\n"
                "- Ctrl + Shift + click: add a contiguous range to your current selection.\n"
                "- Drag box: draw a rectangle to select multiple photos at once.\n"
                "- Hold the 1 key and click: move the clicked photo to the Target1 folder.\n"
                "- Hold the 2 key and click: move the clicked photo to the Target2 folder.\n"
                "- Press 1 or 2 and release: the next click will move a photo to that target.\n"
                "- Double-click: immediately move that photo to the Target1 folder.\n"
                "- Select multiple photos and press 1 or 2: move all selected photos to the respective target.\n\n"
                "■ Preview windows\n"
                "- Two preview slots are available: Slot1 (top) and Slot2 (bottom).\n"
                "- Drag with the mouse to pan the image.\n"
                "- Use the mouse wheel to zoom in/out (no modifier needed).\n"
                "- Use the zoom slider to adjust the zoom factor.\n"
                "- Independent Zoom Mode toggles whether zoom is linked between slots.\n"
                "- Zoom and scroll positions are preserved when changing images.\n\n"
                "■ Grid (thumbnail) view\n"
                "- Ctrl + mouse wheel: resize thumbnails up to 1600px. Larger sizes automatically reload higher resolution thumbnails.\n"
                "- Filenames are displayed below thumbnails.\n"
                "- Use Shift for range selection and Ctrl to add to the selection.\n\n"
                "■ Keyboard shortcuts\n"
                "- Ctrl + Z: undo the last move.\n"
                "- Ctrl + Y: redo the last undo.\n"
                "- Arrow keys: move the selection in the grid.\n"
                "- Enter: show the current selection in the preview.\n"
                "- Hold 1 or 2 and press Enter: move the current selection to Target1 or Target2.\n\n"
                "■ File movement\n"
                "- Drag selected photos onto the Target1 or Target2 labels to move them.\n"
                "- You must set target folders before moving.\n\n"
                "■ Other features\n"
                "- Clear Slot buttons clear each preview.\n"
                "- Dual Mode splits the grid and previews into separate windows; toggle it again to merge.\n"
                "- Help opens this guide.\n"
                "- Language toggles between Korean and English.\n"
                "- Donate opens the Buy Me a Coffee page to support development.\n"
            )
        else:
            text = (
                "※ 프로그램 사용 안내\n\n"
                "■ 폴더 설정\n"
                "- Image Folder 버튼으로 원본 이미지가 있는 폴더를 선택합니다.\n"
                "- Target1, Target2 버튼으로 분류 대상 폴더를 설정합니다.\n\n"
                "■ 이미지 선택 및 이동\n"
                "- 클릭: 선택한 사진을 Slot1 프리뷰에 표시합니다.\n"
                "- Ctrl + 클릭: 선택한 사진을 Slot2 프리뷰에 표시합니다.\n"
                "- Shift + 클릭: 마지막 선택과 현재 클릭한 항목 사이의 모든 항목을 선택합니다.\n"
                "- Ctrl + Shift + 클릭: 기존 선택에 연속 범위를 추가합니다.\n"
                "- 드래그 박스: 마우스로 영역을 끌어 여러 장을 선택합니다.\n"
                "- 1 키를 누른 채 클릭: 선택된 사진을 Target1 폴더로 이동합니다.\n"
                "- 2 키를 누른 채 클릭: 선택된 사진을 Target2 폴더로 이동합니다.\n"
                "- 1 또는 2 키를 눌렀다 놓으면: 다음 클릭에서 해당 폴더로 이동이 예약됩니다.\n"
                "- 더블클릭: 해당 사진을 즉시 Target1 폴더로 이동합니다.\n"
                "- 드래그 선택 후 1 또는 2 키: 선택된 모든 사진을 한 번에 Target1/Target2로 이동합니다.\n\n"
                "■ 프리뷰 창\n"
                "- Slot1과 Slot2의 두 프리뷰 영역이 있습니다.\n"
                "- 마우스 드래그: 이미지 패닝(이동)\n"
                "- 마우스 휠: 줌 인/아웃 (Ctrl 키 없이 사용)\n"
                "- 줌 슬라이더: 확대/축소 배율을 조절합니다.\n"
                "- 독립 줌 모드 버튼을 통해 두 프리뷰의 줌을 연동하거나 각각 조절할 수 있습니다.\n"
                "- 프리뷰 창에서 줌과 스크롤 위치는 새 이미지를 선택해도 유지됩니다.\n\n"
                "■ 격자(썸네일) 보기\n"
                "- Ctrl + 마우스 휠: 썸네일 크기를 확대/축소합니다. 최대 1600px까지 확대 가능합니다.\n"
                "  확대 시에는 자동으로 더 큰 해상도의 썸네일을 불러와 품질을 유지합니다.\n"
                "- 썸네일 아래에는 파일명이 표시됩니다.\n"
                "- Shift 키로 연속 선택, Ctrl 키로 개별 선택을 추가할 수 있습니다.\n\n"
                "■ 키보드 단축 기능\n"
                "- Ctrl + Z: 마지막 이동 작업을 취소합니다.\n"
                "- Ctrl + Y: 이전에 취소한 이동을 다시 적용합니다.\n"
                "- 방향키: 격자에서 선택된 항목을 이동합니다.\n"
                "- Enter: 현재 선택된 항목을 클릭한 것처럼 프리뷰에 표시합니다.\n"
                "- 1 또는 2 키 + Enter: 키를 누른 채 Enter를 누르면 해당 타겟 폴더로 이동합니다.\n\n"
                "■ 파일 이동\n"
                "- 선택된 사진을 Target1/Target2 라벨로 드래그&드롭하여 이동할 수 있습니다.\n"
                "- Target1/Target2를 지정하지 않으면 이동할 수 없습니다.\n\n"
                "■ 기타 기능\n"
                "- Clear Slot 버튼으로 각 프리뷰를 비울 수 있습니다.\n"
                "- 듀얼 모드 버튼을 사용하여 격자와 프리뷰를 별도 창으로 분리하거나 다시 합칠 수 있습니다.\n"
                "- 도움말 버튼을 통해 이 안내를 언제든 확인할 수 있습니다.\n"
                "- 언어 버튼을 눌러 한국어와 영어 간 전환할 수 있습니다.\n"
                "- 후원하기 버튼을 눌러 개발자를 후원할 수 있습니다.\n"
            )
        # 대화상자 생성
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextEdit
        dlg = QDialog(self)
        dlg.setWindowTitle("도움말")
        dlg.resize(600, 600)
        layout = QVBoxLayout(dlg)
        # 스크롤 가능한 텍스트 영역
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(text)
        text_edit.setMinimumSize(500, 500)
        layout.addWidget(text_edit)
        # 닫기 버튼
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(dlg.accept)
        layout.addWidget(buttons)
        dlg.exec()

    def undo_last_move(self):
        """
        Ctrl+Z 핫키를 통해 마지막 파일 이동 작업을 취소합니다. undo_stack에 저장된
        각 항목은 (dest_path, src_path) 튜플로 구성되어 있으며, 파일을 원래 위치로
        이동합니다. 원본 경로에 같은 이름의 파일이 존재하는 경우 ``_restored`` 접미사와
        번호를 붙여 충돌을 방지합니다. 작업 후 현재 폴더를 다시 로드하여 화면을 갱신합니다.
        """
        if not self.undo_stack:
            QMessageBox.information(self, "Info", "되돌릴 이동이 없습니다.")
            return
        moves = self.undo_stack.pop()
        # Save moves to redo stack so that Ctrl+Y can reapply them
        # Copy the list to avoid modifications
        self.redo_stack.append(list(moves))
        for dest_path, src_path in moves:
            try:
                if not dest_path.exists():
                    continue
                target_path = src_path
                # 충돌 방지를 위해 원본 이름이 존재하면 _restored 접미사 사용
                if target_path.exists():
                    base = src_path.stem
                    ext = src_path.suffix
                    target_path = src_path.with_stem(f"{base}_restored")
                    i = 1
                    while target_path.exists():
                        target_path = src_path.with_stem(f"{base}_restored_{i}")
                        i += 1
                shutil.move(str(dest_path), str(target_path))
            except Exception as e:
                print(f"Undo move failed for {dest_path} -> {src_path}: {e}")
        # 현재 폴더가 설정되어 있으면 다시 로드
        if self.current_folder is not None:
            self.load_folder_grid(self.current_folder)

    def redo_last_move(self):
        """
        Ctrl+Y를 사용하여 마지막으로 취소한 이동을 다시 적용합니다. redo_stack에 저장된
        각 항목은 (dest_path, src_path) 튜플로 구성되어 있으며, src_path에서 dest_path로
        다시 이동합니다. 이동 시 이름 충돌이 있으면 접미사를 붙여 처리합니다. 작업 후
        현재 폴더를 다시 로드하여 화면을 갱신합니다.
        """
        if not self.redo_stack:
            QMessageBox.information(self, "Info", "다시 적용할 이동이 없습니다.")
            return
        moves = self.redo_stack.pop()
        # moves: list of (dest_path, src_path) originally recorded when the file was moved.
        # After undo, files reside at src_path (or a _restored variant). We need to move
        # them back to dest_path (or a new unique name in the destination folder).
        action_moves: list[tuple[Path, Path]] = []
        for dest_path, src_path in moves:
            try:
                # Determine the actual current source file: it could be at src_path or with
                # a _restored suffix if a conflict occurred during undo. We pick the first
                # existing file among possible restored names.
                candidate = src_path
                if not candidate.exists():
                    # Try with _restored suffixes
                    base = src_path.stem
                    ext = src_path.suffix
                    candidate = src_path.with_stem(f"{base}_restored")
                    idx = 1
                    while not candidate.exists() and idx < 10:
                        candidate = src_path.with_stem(f"{base}_restored_{idx}")
                        idx += 1
                    if not candidate.exists():
                        continue  # no file to move
                src_file = candidate
                # Compute destination path avoiding conflicts in target folder
                folder = dest_path.parent
                base = dest_path.stem
                ext = dest_path.suffix
                new_dest = folder / f"{base}{ext}"
                i = 1
                while new_dest.exists():
                    new_dest = folder / f"{base}_{i}{ext}"
                    i += 1
                shutil.move(str(src_file), str(new_dest))
                # record the move for undo stack
                action_moves.append((new_dest, src_path))
            except Exception as e:
                print(f"Redo move failed for {src_path} -> {dest_path}: {e}")
        # If any moves occurred, push to undo stack for possible undo again.
        if action_moves:
            self.undo_stack.append(action_moves)
        # After redoing, reload folder
        if self.current_folder is not None:
            self.load_folder_grid(self.current_folder)

    def toggle_language(self):
        """
        Toggle between Korean ('ko') and English ('en') UI. When toggled, update
        all UI element texts and the help content. The language button itself
        displays the target language name.
        """
        self.language = 'en' if self.language == 'ko' else 'ko'
        self.update_language()

    def update_language(self):
        """
        Apply the current language to all UI elements. This method updates
        button texts, labels, window title, preview prompts, zoom link button
        text based on the current state, and donate/language buttons. It should
        be called after the UI is constructed and whenever the language is
        toggled.
        """
        lang = self.language
        tr = self.translations.get(lang, {})
        # Update window title
        self.setWindowTitle(tr.get('title', ''))
        # Update top buttons
        self.btn_select_folder.setText(tr.get('select_folder', self.btn_select_folder.text()))
        self.btn_target1.setText(tr.get('target1', self.btn_target1.text()))
        self.btn_target2.setText(tr.get('target2', self.btn_target2.text()))
        # Donate button text
        self.btn_donate.setText(tr.get('donate', self.btn_donate.text()))
        # Language button text should display the name of the other language
        self.btn_language.setText(tr.get('language', self.btn_language.text()))
        # Zoom link button text depends on whether linked or independent
        if self.zoom_linked:
            self.btn_toggle_zoom_link.setText(tr.get('zoom_link', self.btn_toggle_zoom_link.text()))
        else:
            self.btn_toggle_zoom_link.setText(tr.get('zoom_link_on', self.btn_toggle_zoom_link.text()))
        # Dual mode toggle button text depends on state
        if self.dual_mode_enabled:
            self.btn_dual_mode.setText(tr.get('single_mode', self.btn_dual_mode.text()))
        else:
            self.btn_dual_mode.setText(tr.get('dual_mode', self.btn_dual_mode.text()))
        # Help button text
        self.btn_help.setText(tr.get('help', self.btn_help.text()))
        # Update preview prompt labels if no image loaded
        if self.preview_pixmaps[0] is None:
            self.preview_label_1.setText(tr.get('slot1_prompt', self.preview_label_1.text()))
        if self.preview_pixmaps[1] is None:
            self.preview_label_2.setText(tr.get('slot2_prompt', self.preview_label_2.text()))
        # Ensure drop labels remain in English as they describe actions; optionally you can localize them

    def open_donate_link(self):
        """Open the Buy Me a Coffee link in the default browser."""
        url = QUrl("https://buymeacoffee.com/modang")
        QDesktopServices.openUrl(url)

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
        # 이전 버전의 썸네일 로딩을 중단합니다.
        self._stop_thumb_thread()
        # 새 로딩 세션을 위한 버전 번호를 증가시킵니다. 이렇게 하면 오래된 로딩 결과가
        # 최신 폴더에 적용되는 것을 방지할 수 있습니다.
        self.thumb_load_version += 1
        load_version = self.thumb_load_version

        # 썸네일 리스트를 초기화하고 현재 썸네일 크기와 그리드 크기를 재설정합니다.
        self.list_widget.clear()
        thumb_size = self.list_widget._thumb_size
        pad_w = self.list_widget._grid_padding_w
        pad_h = self.list_widget._grid_padding_h
        self.list_widget.setIconSize(QSize(thumb_size, thumb_size))
        self.list_widget.setGridSize(QSize(thumb_size + pad_w, thumb_size + pad_h))

        # Update last_loaded_thumb_size when starting a new folder load. This
        # ensures that subsequent throttle calculations compare against the
        # current actual loaded size rather than the previous folder's size.
        self.last_loaded_thumb_size = thumb_size

        # 지원되는 이미지 파일 목록을 가져옵니다. 이름순으로 정렬하여 일관된 순서를 유지합니다.
        all_files: list[str] = []
        try:
            for entry in sorted(folder.iterdir()):
                if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXT:
                    all_files.append(str(entry))
        except Exception:
            pass

        if not all_files:
            QMessageBox.information(self, "Info", "지원하는 이미지 파일이 없습니다.")
            return

        # 각 항목에 대한 리스트 아이템과 플레이스홀더 위젯을 추가합니다.
        for path_str in all_files:
            p = Path(path_str)
            item = QListWidgetItem()
            item.setData(Qt.UserRole, path_str)
            item.setToolTip(p.name)
            thumb_widget = ThumbnailWidget(p.name, thumb_size)
            # 초기에는 빈 썸네일을 설정하여 그리드 크기를 유지합니다.
            placeholder = QPixmap(thumb_size, thumb_size)
            placeholder.fill(Qt.transparent)
            thumb_widget.set_pixmap(placeholder)
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, thumb_widget)
            item.setSizeHint(QSize(thumb_size + pad_w, thumb_size + pad_h))

        # 비동기적으로 썸네일을 로딩합니다. 각 작업은 스레드 풀에서 실행되며, 완료 시
        # 메인 스레드에서 업데이트를 수행합니다.
        current_folder = self.current_folder

        def load_qimage(path_str: str, size: int) -> QImage | None:
            """
            백그라운드 스레드에서 이미지 파일을 로딩하여 QImage로 변환합니다.
            QPixmap은 GUI 스레드에서만 안전하게 생성될 수 있으므로 여기서 QImage만 생성합니다.
            로딩에 실패하면 None을 반환합니다.
            """
            try:
                path_obj = Path(path_str)
                img = load_pil_image(path_obj, max_size=size)
                qimg = pil_to_qimage(img)
                return qimg
            except Exception:
                return None

        # 콜백 함수: 로딩된 썸네일을 메인 스레드에서 적용합니다.
        def on_loaded(path_str: str, qimage: QImage | None, version: int):
            # 버전 또는 현재 폴더가 변경되었다면 무시합니다.
            if self.thumb_load_version != version or self.current_folder != folder:
                return
            if qimage is None:
                return
            # 메인 스레드에서 처리되도록 시그널을 발생시킵니다.
            self.thumbnail_loaded.emit(path_str, qimage)

        # 스레드 풀에 로딩 작업을 제출합니다.
        for path_str in all_files:
            # 로딩 함수와 콜백을 캡처하여 비동기 실행합니다.
            future = self.thumb_executor.submit(load_qimage, path_str, thumb_size)
            future.add_done_callback(
                lambda f, p=path_str, v=load_version: on_loaded(p, f.result(), v)
            )

        # 썸네일 추가 후 레이아웃을 갱신합니다.
        self.list_widget.updateGeometry()
        self.list_widget.repaint()

        # 만약 썸네일 크기 변경 전 선택 항목을 복원할 필요가 있다면, 여기서 재선택합니다.
        restore_paths = getattr(self, '_restore_selection_paths', None)
        if restore_paths:
            selected_rows = []
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item is not None and item.data(Qt.UserRole) in restore_paths:
                    item.setSelected(True)
                    selected_rows.append(i)
            # 지연된 신호 방지: 현재 행을 복원된 목록에서 첫 번째 항목으로 설정합니다.
            if selected_rows:
                self.list_widget.setCurrentRow(selected_rows[0])
            # 항목 클릭과 동일하게 프리뷰를 갱신합니다.
            # (마지막 선택된 항목을 보여주도록 한다)
            if selected_rows:
                item = self.list_widget.item(selected_rows[-1])
                if item:
                    # emit clicked_with_modifiers with NoModifier to update preview
                    self.list_widget.clicked_with_modifiers.emit(item, Qt.NoModifier)
            # 클린업: 속성을 삭제하여 다음 호출에서 재사용되지 않도록 합니다.
            delattr(self, '_restore_selection_paths')

    def _apply_thumbnail(self, path_str: str, qimage: QImage):
        """
        비동기 로딩된 이미지(QImage)를 받아 현재 표시 중인 리스트 항목에 썸네일을 적용합니다.
        이 메서드는 항상 GUI 스레드에서 호출됩니다.
        """
        # 현재 폴더가 변경되었거나 버전이 맞지 않으면 무시
        # (버전 체크는 로딩 함수에서 이미 수행되므로 여기서 추가 확인은 선택적입니다.)
        if qimage is None:
            return
        pixmap = QPixmap.fromImage(qimage)
        if pixmap.isNull():
            return
        count = self.list_widget.count()
        for i in range(count):
            item = self.list_widget.item(i)
            if item is not None and item.data(Qt.UserRole) == path_str:
                widget = self.list_widget.itemWidget(item)
                if isinstance(widget, ThumbnailWidget):
                    widget.set_pixmap(pixmap)
                break

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

        # Shift + 클릭: 연속 구간 선택
        # 마지막 클릭된 인덱스(self.last_clicked_row)를 기준으로 현재 클릭한 항목까지 범위를 선택합니다.
        # Ctrl과 같이 누를 경우 기존 선택에 추가하고, 그렇지 않으면 선택을 초기화한 후 범위를 선택합니다.
        try:
            row = self.list_widget.row(item)
        except Exception:
            row = -1
        if modifiers & Qt.ShiftModifier and row >= 0:
            if self.last_clicked_row is not None:
                start = min(self.last_clicked_row, row)
                end = max(self.last_clicked_row, row)
                # 범위를 선택합니다. Ctrl이 눌린 경우에는 기존 선택을 유지하고 추가, 아니면 초기화 후 선택
                if modifiers & Qt.ControlModifier:
                    for r in range(start, end + 1):
                        it = self.list_widget.item(r)
                        if it is not None:
                            it.setSelected(True)
                else:
                    self.list_widget.clearSelection()
                    for r in range(start, end + 1):
                        it = self.list_widget.item(r)
                        if it is not None:
                            it.setSelected(True)
                # Shift 선택 시 프리뷰를 변경하지 않고 선택만 조정하고 리턴합니다.
                return
        else:
            # Shift가 아닌 일반 클릭이면 현재 클릭 위치를 앵커로 저장합니다.
            if row >= 0:
                self.last_clicked_row = row

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
            # Use language-specific empty prompt
            empty_text = self.translations.get(self.language, {}).get('empty', 'Empty')
            label.setText(empty_text)
            self.preview_pixmaps[idx] = None
            self.zoom_factors[idx] = 1.0
            # 초기화 시 스크롤 위치도 초기화합니다.
            self.preview_scroll_values[idx] = (0, 0)
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

            # 이전 이미지의 확대/스크롤 상태를 저장합니다.
            prev_pix = self.preview_pixmaps[idx]
            if prev_pix is not None:
                # 현재 스크롤 위치 저장
                h_val = scroll.horizontalScrollBar().value()
                v_val = scroll.verticalScrollBar().value()
                self.preview_scroll_values[idx] = (h_val, v_val)
            else:
                # 초기 스크롤 값
                self.preview_scroll_values[idx] = (0, 0)

            # 새 pixmap 저장
            self.preview_pixmaps[idx] = pixmap

            # 확대 비율 결정: 기존 확대가 있으면 유지, 없으면 화면에 맞춤
            if prev_pix is not None:
                # 기존 배율을 유지합니다.
                factor = self.zoom_factors[idx]
                slider_value = int(factor * 100)
                slider_value = max(10, min(300, slider_value))
            else:
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
                # 두 슬롯을 동시에 조정합니다.
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
                # 개별 슬롯만 조정
                self.zoom_factors[idx] = factor
                slider.blockSignals(True)
                slider.setValue(slider_value)
                slider.blockSignals(False)
                self.apply_zoom(idx)

            label.setText("")

            # 확대/스크롤 복원: 이전 이미지가 있었으면 저장된 위치로 스크롤을 복원합니다.
            # 복원 시점은 apply_zoom 이후로, scroll 영역의 크기가 설정된 후입니다.
            prev_h, prev_v = self.preview_scroll_values[idx]
            # 스크롤 값을 복원하되, 범위를 벗어나면 clamp됩니다.
            hbar = scroll.horizontalScrollBar()
            vbar = scroll.verticalScrollBar()
            hbar.setValue(min(max(prev_h, hbar.minimum()), hbar.maximum()))
            vbar.setValue(min(max(prev_v, vbar.minimum()), vbar.maximum()))

            # 처음 로드한 이미지라면 기본 위치로 스크롤합니다.
            if prev_pix is None:
                scroll.ensureVisible(0, 0)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"프리뷰 로딩 실패:\n{e}")

    def clear_slot(self, idx: int):
        self.set_preview_slot(idx, None)

    # --------------------------------------------------------
    # 썸네일 크기 변경 처리
    # --------------------------------------------------------
    def on_thumb_size_changed(self, new_size: int):
        """
        Handle thumbnail size change events from the ImageListWidget. When the user
        zooms in or out of the grid (Ctrl+wheel), this slot is triggered and
        quality. Instead of reloading immediately, we record the size and
        schedule a reload after a short delay. If multiple size changes
        occur in quick succession (e.g., during continuous wheel scrolling),
        only the final size will trigger a reload, avoiding redundant work.
        """
        # No folder loaded: nothing to do
        if self.current_folder is None:
            return
        # Update pending thumbnail size
        self._pending_thumb_size = new_size
        # Restart the timer: each new size will reset the single-shot timer
        # to fire after the defined interval. This means the reload only
        # happens when the user stops zooming.
        self._thumb_reload_timer.start()

    def _do_thumb_reload(self):
        """Perform a throttled reload of thumbnails if needed."""
        # If no pending size or no folder, do nothing
        if self._pending_thumb_size is None or self.current_folder is None:
            return
        new_size = self._pending_thumb_size
        self._pending_thumb_size = None
        # Reload only when the user has zoomed in beyond the previously
        # loaded thumbnail size. Scaling down thumbnails is inexpensive,
        # so we avoid reloading in that case. This ensures high-resolution
        # thumbnails are loaded when zooming in but prevents unnecessary
        # reloads when zooming out or making minor size adjustments.
        if self.last_loaded_thumb_size:
            if new_size <= self.last_loaded_thumb_size:
                return
        # Remember current selection paths to restore later
        selected_items = self.list_widget.selectedItems()
        restore_paths: list[str] = []
        for item in selected_items:
            path_str = item.data(Qt.UserRole)
            if path_str:
                restore_paths.append(path_str)
        if restore_paths:
            self._restore_selection_paths = restore_paths
        # Update last loaded size
        self.last_loaded_thumb_size = new_size
        # Trigger reload of grid with new thumbnail size
        self.load_folder_grid(self.current_folder)

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
        # Undo 기록을 위해 이번 이동에서 처리한 파일 쌍을 모읍니다.
        action_moves: list[tuple[Path, Path]] = []
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

            # 이동 정보 기록: (dest_path, src_path)
            action_moves.append((dst, src))

            # 실제 파일을 이동한 후 리스트에서 항목을 페이드 아웃시키면서 제거합니다.
            self.animate_item_removal(item)

        # 이동한 항목이 있는 경우 undo 스택에 기록합니다. 새 이동이 발생하면 redo 스택을 비웁니다.
        if action_moves:
            self.undo_stack.append(action_moves)
            # New user action clears the redo history
            self.redo_stack.clear()

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
        # 이전 워커 스레드 정리
        self._stop_thumb_thread()
        # 스레드 풀을 안전하게 종료합니다. 대기하지 않고 현재 실행 중인 작업을 취소합니다.
        try:
            self.thumb_executor.shutdown(wait=False, cancel_futures=True)  # Python 3.9+
        except TypeError:
            # Python 3.8에서는 cancel_futures 인자를 지원하지 않습니다.
            self.thumb_executor.shutdown(wait=False)
        super().closeEvent(event)

    # --------------------------------------------------------
    # 듀얼 모드 토글
    # --------------------------------------------------------
    def toggle_dual_mode(self, checked: bool):
        """
        듀얼 모드 토글. 켜면 프리뷰 영역을 새로운 창으로 분리하고, 끄면 다시 합칩니다.
        checked: True -> 듀얼 모드 활성화, False -> 비활성화
        """
        if checked:
            # 이미 듀얼 모드이면 무시
            if self.dual_mode_enabled:
                return
            # 프리뷰 스플리터를 오른쪽 패널에서 분리
            if self.splitter_right is not None:
                try:
                    self.right_layout.removeWidget(self.splitter_right)
                except Exception:
                    pass
                self.splitter_right.setParent(None)
            # 새로운 창 생성
            self.dual_window = QMainWindow(self)
            self.dual_window.setWindowTitle("프리뷰")
            self.dual_window.setCentralWidget(self.splitter_right)
            # 적절한 초기 크기를 설정합니다
            try:
                size = self.splitter_right.size()
                if size.width() > 0 and size.height() > 0:
                    self.dual_window.resize(size)
                else:
                    self.dual_window.resize(600, 600)
            except Exception:
                self.dual_window.resize(600, 600)
            self.dual_window.show()
            # 왼쪽 그리드가 전체 너비를 차지하도록 스플리터 크기를 조정합니다.
            if hasattr(self, 'splitter_main'):
                total_width = self.width()
                self.splitter_main.setSizes([total_width, 0])
            # 버튼 텍스트 변경
            self.btn_dual_mode.setText("단일 모드")
            self.dual_mode_enabled = True
        else:
            # 이미 비활성화된 경우 무시
            if not self.dual_mode_enabled:
                return
            # 프리뷰 영역을 듀얼 창에서 제거하고 다시 오른쪽 패널로 복원
            if self.dual_window is not None:
                try:
                    self.dual_window.setCentralWidget(None)
                    self.dual_window.close()
                except Exception:
                    pass
                self.dual_window = None
            if self.splitter_right is not None:
                self.splitter_right.setParent(self.right_widget)
                self.right_layout.addWidget(self.splitter_right)
            # 스플리터 크기를 기본 비율로 복원
            if hasattr(self, 'splitter_main'):
                total_width = self.width()
                left_width = int(total_width * 0.7)
                right_width = total_width - left_width
                self.splitter_main.setSizes([left_width, right_width])
            # 버튼 텍스트 복원
            self.btn_dual_mode.setText("듀얼 모드")
            self.dual_mode_enabled = False
        # Update language-dependent text
        self.update_language()

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
