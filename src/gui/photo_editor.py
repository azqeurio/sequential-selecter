import json
from pathlib import Path
from PIL import Image

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox, QFrame,
    QProgressBar, QScrollArea, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QCheckBox, QListWidget, QListWidgetItem, QGraphicsItem, QGraphicsPathItem
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QSize, QTimer, QThread
from PySide6.QtGui import QPixmap, QImage, QColor, QPen, QBrush, QPainter, QIcon, QPainterPath, QKeySequence

from ..core.image_loader import load_pil_image
from ..core.image_editor import PhotoEditor
from ..core.xmp_parser import parse_xmp_preset
from .utils import pil_to_qimage
from .widgets import ProSliderWidget


class ResizableCropBox(QGraphicsItem):
    """An interactive crop box with 8-handle resizing and moving."""
    def __init__(self, scene_ref, parent=None):
        super().__init__(parent)
        self.scene_ref = scene_ref
        self.setAcceptHoverEvents(True)
        self.setFlags(QGraphicsItem.ItemSendsGeometryChanges)
        self._rect = QRectF()
        
        self.grab_margin = 15
        self.active_handle = None
        self.start_rect = None
        self.start_pos = None

    def boundingRect(self):
        return self._rect

    def rect(self):
        return self._rect
        
    def setRect(self, rect):
        if self._rect != rect:
            self.prepareGeometryChange()
            self._rect = rect
            self.update()

    def paint(self, painter, option, widget=None):
        # Draw Lightroom-style crop box
        pen = QPen(QColor(255, 255, 255, 220), 2, Qt.SolidLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(self._rect)
        
        # Rule of thirds lines
        w = self._rect.width()
        h = self._rect.height()
        if w > 30 and h > 30:
            thin_pen = QPen(QColor(255, 255, 255, 100), 1, Qt.DashLine)
            thin_pen.setCosmetic(True)
            painter.setPen(thin_pen)
            x = self._rect.x()
            y = self._rect.y()
            painter.drawLine(x + w/3, y, x + w/3, y + h)
            painter.drawLine(x + 2*w/3, y, x + 2*w/3, y + h)
            painter.drawLine(x, y + h/3, x + w, y + h/3)
            painter.drawLine(x, y + 2*h/3, x + w, y + 2*h/3)

    def _get_handle(self, pos):
        rect = self.rect()
        x, y = pos.x(), pos.y()
        rx, ry, rw, rh = rect.x(), rect.y(), rect.width(), rect.height()
        m = self.grab_margin
        
        left = abs(x - rx) <= m
        right = abs(x - (rx + rw)) <= m
        top = abs(y - ry) <= m
        bottom = abs(y - (ry + rh)) <= m
        
        if top and left: return 'topleft'
        if top and right: return 'topright'
        if bottom and left: return 'bottomleft'
        if bottom and right: return 'bottomright'
        if top: return 'top'
        if bottom: return 'bottom'
        if left: return 'left'
        if right: return 'right'
        
        if rect.contains(pos): return 'center'
        return None

    def hoverMoveEvent(self, event):
        handle = self._get_handle(event.pos())
        if handle in ['topleft', 'bottomright']:
            self.setCursor(Qt.SizeFDiagCursor)
        elif handle in ['topright', 'bottomleft']:
            self.setCursor(Qt.SizeBDiagCursor)
        elif handle in ['left', 'right']:
            self.setCursor(Qt.SizeHorCursor)
        elif handle in ['top', 'bottom']:
            self.setCursor(Qt.SizeVerCursor)
        elif handle == 'center':
            self.setCursor(Qt.SizeAllCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.active_handle = self._get_handle(event.pos())
            if self.active_handle:
                self.start_rect = self.rect()
                self.start_pos = event.pos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.active_handle:
            dp = event.pos() - self.start_pos
            rect = QRectF(self.start_rect)
            
            img_rect = self.scene_ref.pixmap_item.boundingRect()
            
            if 'left' in self.active_handle: rect.setLeft(min(rect.left() + dp.x(), rect.right() - 20))
            elif 'right' in self.active_handle: rect.setRight(max(rect.right() + dp.x(), rect.left() + 20))
            if 'top' in self.active_handle: rect.setTop(min(rect.top() + dp.y(), rect.bottom() - 20))
            elif 'bottom' in self.active_handle: rect.setBottom(max(rect.bottom() + dp.y(), rect.top() + 20))
                
            if self.active_handle == 'center':
                dx, dy = dp.x(), dp.y()
                if rect.left() + dx < 0: dx = -rect.left()
                if rect.right() + dx > img_rect.width(): dx = img_rect.width() - rect.right()
                if rect.top() + dy < 0: dy = -rect.top()
                if rect.bottom() + dy > img_rect.height(): dy = img_rect.height() - rect.bottom()
                rect.translate(dx, dy)
                
            rect = rect.intersected(img_rect)
            self.setRect(rect)
            self.scene_ref._update_dim_overlay(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.active_handle:
            self.active_handle = None
            self.scene_ref._emit_crop()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class CropScene(QGraphicsScene):
    crop_changed = Signal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap_item = QGraphicsPixmapItem()
        self.addItem(self.pixmap_item)
        
        self.dim_overlay = self.addPath(QPainterPath())
        self.dim_overlay.setBrush(QBrush(QColor(0, 0, 0, 160)))
        self.dim_overlay.setPen(Qt.NoPen)
        self.dim_overlay.setZValue(1)
        self.dim_overlay.hide()
        
        self.crop_box = ResizableCropBox(self)
        self.crop_box.setZValue(2)
        self.crop_box.hide()
        self.addItem(self.crop_box)
        
        self.rotation_grid = QGraphicsPathItem()
        self.rotation_grid.setPen(QPen(QColor(255, 255, 255, 180), 1, Qt.DashLine))
        self.rotation_grid.setZValue(3)
        self.rotation_grid.hide()
        self.addItem(self.rotation_grid)
        
        self.is_drawing_new = False
        self.start_pos = QPointF()

    def show_rotation_grid(self):
        img_rect = self.pixmap_item.boundingRect()
        if img_rect.width() == 0 or img_rect.height() == 0:
            return
            
        path = QPainterPath()
        w, h = img_rect.width(), img_rect.height()
        
        # Draw 3x3 grid lines
        for i in range(1, 3):
            # Vertical lines
            x = (w / 3) * i
            path.moveTo(x, 0)
            path.lineTo(x, h)
            # Horizontal lines
            y = (h / 3) * i
            path.moveTo(0, y)
            path.lineTo(w, y)
            
        self.rotation_grid.setPath(path)
        self.rotation_grid.show()

    def hide_rotation_grid(self):
        self.rotation_grid.hide()

    def _update_dim_overlay(self, crop_rect):
        img_rect = self.pixmap_item.boundingRect()
        path = QPainterPath()
        path.addRect(img_rect)
        path.addRect(crop_rect)
        path.setFillRule(Qt.OddEvenFill)
        self.dim_overlay.setPath(path)

    def _emit_crop(self):
        rect = self.crop_box.rect()
        img_rect = self.pixmap_item.boundingRect()
        
        if img_rect.width() > 0 and img_rect.height() > 0 and rect.width() > 10 and rect.height() > 10:
            left_p = int((rect.left() / img_rect.width()) * 100)
            right_p = int(((img_rect.width() - rect.right()) / img_rect.width()) * 100)
            top_p = int((rect.top() / img_rect.height()) * 100)
            bottom_p = int(((img_rect.height() - rect.bottom()) / img_rect.height()) * 100)
            
            self.crop_changed.emit(top_p, bottom_p, left_p, right_p)
        else:
            self.crop_box.hide()
            self.dim_overlay.hide()
            self.crop_changed.emit(0, 0, 0, 0)

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform())
        if item == self.crop_box:
            super().mousePressEvent(event)
            return
            
        if event.button() == Qt.LeftButton:
            self.is_drawing_new = True
            self.start_pos = event.scenePos()
            self.crop_box.setRect(QRectF(self.start_pos, self.start_pos))
            self._update_dim_overlay(self.crop_box.rect())
            self.crop_box.show()
            self.dim_overlay.show()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_drawing_new:
            end_pos = event.scenePos()
            img_rect = self.pixmap_item.boundingRect()
            
            x1 = max(0, min(self.start_pos.x(), end_pos.x()))
            y1 = max(0, min(self.start_pos.y(), end_pos.y()))
            x2 = min(img_rect.width(), max(self.start_pos.x(), end_pos.x()))
            y2 = min(img_rect.height(), max(self.start_pos.y(), end_pos.y()))
            
            rect = QRectF(x1, y1, x2 - x1, y2 - y1)
            self.crop_box.setRect(rect)
            self._update_dim_overlay(rect)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_drawing_new:
            self.is_drawing_new = False
            self._emit_crop()
            return
        super().mouseReleaseEvent(event)


class RenderWorker(QThread):
    """
    Background worker for mathematically applying High-Res edits.
    Prevents UI freezing when releasing sliders.
    """
    result_ready = Signal(QImage)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = None
        self.params = None
        self.lut = None
        
    def setup(self, image, params, lut):
        self.image = image
        self.params = params
        self.lut = lut
        
    def run(self):
        if self.image and self.params:
            try:
                edited = PhotoEditor.apply_edits(self.image, self.params, self.lut)
                qimg = pil_to_qimage(edited)
                self.result_ready.emit(qimg)
            except Exception as e:
                print(f"RenderWorker error: {e}")


class DenoiseWorker(QThread):
    """Background worker for AI noise reduction.
    Optimized for RTX 3060 12GB (~15s for 5220x3912).
    Supports CUDA, Apple MPS, and CPU.
    """
    progress = Signal(int)       # 0-100
    status = Signal(str)         # Status text
    finished_ok = Signal(object, object, str)  # full_img, proxy_img, method_name
    finished_err = Signal(str)   # error message
    
    # SCUNet first (pure denoiser = fastest), then upscale-based fallbacks
    MODELS = {
        'scunet': {
            'url': 'https://github.com/cszn/KAIR/releases/download/v1.0/scunet_color_real_psnr.pth',
            'file': 'scunet_color_real_psnr.pth',
            'name': 'SCUNet',
        },
        'swin2sr': {
            'url': 'https://github.com/mv-lab/swin2sr/releases/download/v0.0.1/Swin2SR_RealworldSR_X4_64_BSRGAN_PSNR.pth',
            'file': 'Swin2SR_RealworldSR_X4_64_BSRGAN_PSNR.pth',
            'name': 'Swin2SR',
        },
        'realesrgan': {
            'url': 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth',
            'file': 'RealESRGAN_x4plus.pth',
            'name': 'Real-ESRGAN',
        },
    }
    MODEL_ORDER = ['scunet', 'swin2sr', 'realesrgan']
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_img = None
        self.proxy_img = None
    
    def setup(self, full_pil, proxy_pil):
        self.full_img = full_pil
        self.proxy_img = proxy_pil
    
    @staticmethod
    def _get_device():
        """Detect best available device: CUDA > MPS > CPU."""
        import torch
        if torch.cuda.is_available():
            return torch.device('cuda'), f" [CUDA: {torch.cuda.get_device_name(0)}]"
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            return torch.device('mps'), " [MPS: Apple Silicon]"
        return torch.device('cpu'), " [CPU]"
    
    def _ensure_model(self, key):
        """Download model if not present, return path."""
        import urllib.request
        model_dir = Path.home() / ".ssc_models"
        model_dir.mkdir(exist_ok=True)
        info = self.MODELS[key]
        path = model_dir / info['file']
        if not path.exists():
            self.status.emit(f"{info['name']}: Downloading weights...")
            self.progress.emit(10)
            urllib.request.urlretrieve(info['url'], str(path))
        return path
    
    def _denoise_with_spandrel(self, model_key, full_cv, dev_info):
        """Run inference on FULL image only, derive proxy by downscale.
        Optimized for RTX 3060 12GB: ~15s for 5220x3912.
        """
        import torch
        import spandrel
        import numpy as np
        
        info = self.MODELS[model_key]
        model_name = info['name']
        
        self.status.emit(f"{model_name}: Loading model...{dev_info}")
        self.progress.emit(15)
        
        weight_path = self._ensure_model(model_key)
        device, _ = self._get_device()
        use_cuda = device.type == 'cuda'
        
        model_desc = spandrel.ModelLoader().load_from_file(str(weight_path))
        
        # FP16: CUDA only (MPS doesn't support it well)
        use_half = False
        if use_cuda:
            try:
                model_desc.to(device).half().eval()
                use_half = True
                self.status.emit(f"{model_name}: FP16{dev_info}")
            except Exception:
                model_desc.to(device).eval()
                self.status.emit(f"{model_name}: FP32{dev_info}")
        else:
            model_desc.to(device).eval()
            self.status.emit(f"{model_name}: FP32{dev_info}")
        
        self.progress.emit(20)
        scale = model_desc.scale if hasattr(model_desc, 'scale') else 1
        is_upscale = scale > 1
        
        # Large tiles for denoise-only on 12GB; smaller for 4x upscalers
        if use_cuda:
            tile_size = 384 if is_upscale else 1024
        elif device.type == 'mps':
            tile_size = 384 if is_upscale else 768
        else:
            tile_size = 256
        
        # --- Process FULL image only (derive proxy later) ---
        self.status.emit(f"{model_name}: Processing full resolution...{dev_info}")
        h, w = full_cv.shape[:2]
        img_f = full_cv.astype(np.float32) / 255.0
        img_t = torch.from_numpy(img_f).permute(2, 0, 1).unsqueeze(0).to(device)
        if use_half:
            img_t = img_t.half()
        
        if h > tile_size * 1.2 or w > tile_size * 1.2:
            result = self._tiled_inference(model_desc, img_t, tile_size, device, use_half, scale)
        else:
            pad_h = (8 - h % 8) % 8
            pad_w = (8 - w % 8) % 8
            if pad_h > 0 or pad_w > 0:
                img_t = torch.nn.functional.pad(img_t, (0, pad_w, 0, pad_h), mode='reflect')
            with torch.no_grad():
                if use_cuda and use_half:
                    with torch.amp.autocast('cuda'):
                        result = model_desc(img_t)
                else:
                    result = model_desc(img_t)
            result = result[:, :, :h*scale, :w*scale]
        
        out_np = result.float().squeeze(0).permute(1, 2, 0).cpu().numpy()
        out_np = np.clip(out_np * 255, 0, 255).astype(np.uint8)
        
        if is_upscale:
            import cv2
            out_np = cv2.resize(out_np, (w, h), interpolation=cv2.INTER_LANCZOS4)
        
        del img_t, result
        if use_cuda:
            torch.cuda.empty_cache()
        self.progress.emit(88)
        
        # Derive proxy by downscaling (no double inference)
        import cv2
        proxy_h = min(h, 2000)
        ratio = proxy_h / h
        proxy_w = int(w * ratio)
        proxy_cv = cv2.resize(out_np, (proxy_w, proxy_h), interpolation=cv2.INTER_AREA)
        
        del model_desc
        if use_cuda:
            torch.cuda.empty_cache()
            vram = torch.cuda.max_memory_allocated() / 1024**3
            self.status.emit(f"{model_name}: Done (VRAM peak {vram:.1f}GB){dev_info}")
        else:
            self.status.emit(f"{model_name}: Done{dev_info}")
        self.progress.emit(92)
        
        return out_np, proxy_cv, f"{model_name}{dev_info}"
    
    def _tiled_inference(self, model, img_t, tile_size, device, use_half, scale):
        """Process image in tiles with per-tile progress. Optimized for 12GB VRAM."""
        import torch
        _, _, h, w = img_t.shape
        overlap = 32
        step = tile_size - overlap
        
        out = torch.zeros(1, 3, h * scale, w * scale, device='cpu')
        weight_map = torch.zeros(1, 1, h * scale, w * scale, device='cpu')
        
        tiles_y = list(range(0, h, step))
        tiles_x = list(range(0, w, step))
        total_tiles = len(tiles_y) * len(tiles_x)
        tile_idx = 0
        
        for y in tiles_y:
            for x in tiles_x:
                tile_idx += 1
                y_end = min(y + tile_size, h)
                x_end = min(x + tile_size, w)
                tile = img_t[:, :, y:y_end, x:x_end]
                
                th, tw = tile.shape[2], tile.shape[3]
                pad_h = (8 - th % 8) % 8
                pad_w = (8 - tw % 8) % 8
                if pad_h > 0 or pad_w > 0:
                    tile = torch.nn.functional.pad(tile, (0, pad_w, 0, pad_h), mode='reflect')
                
                with torch.no_grad():
                    if use_half and device.type == 'cuda':
                        with torch.amp.autocast('cuda'):
                            tile_out = model(tile)
                    else:
                        tile_out = model(tile)
                
                tile_out = tile_out[:, :, :th*scale, :tw*scale].float().cpu()
                out[:, :, y*scale:y_end*scale, x*scale:x_end*scale] += tile_out
                weight_map[:, :, y*scale:y_end*scale, x*scale:x_end*scale] += 1
                
                del tile, tile_out
                if device.type == 'cuda':
                    torch.cuda.empty_cache()
                
                pct = 20 + int((tile_idx / total_tiles) * 65)
                self.progress.emit(pct)
                self.status.emit(f"Tile {tile_idx}/{total_tiles}...")
        
        weight_map = weight_map.clamp(min=1)
        out = out / weight_map
        return out.to(device)
    
    def run(self):
        import numpy as np
        try:
            full_cv = np.array(self.full_img.convert('RGB'))
            
            # Detect device
            dev_info = " [CPU]"
            try:
                _, dev_info = self._get_device()
            except Exception:
                pass
            
            method_used = None
            result_full = None
            result_proxy = None
            
            # Try spandrel (SCUNet > Swin2SR > Real-ESRGAN)
            try:
                import torch
                import spandrel
                
                for model_key in self.MODEL_ORDER:
                    if method_used:
                        break
                    try:
                        self.status.emit(f"Trying {self.MODELS[model_key]['name']}...")
                        result_full, result_proxy, method_used = self._denoise_with_spandrel(
                            model_key, full_cv, dev_info)
                    except Exception as e:
                        import traceback
                        print(f"[AI Denoise] {self.MODELS[model_key]['name']} failed: {e}")
                        traceback.print_exc()
                        self.status.emit(f"{self.MODELS[model_key]['name']} skipped")
                        self.progress.emit(8)
                        continue
            except ImportError as e:
                self.status.emit(f"spandrel not available")
            
            # Fallback: NLMeans+
            if method_used is None:
                try:
                    import cv2
                    self.status.emit("NLMeans+: Processing...")
                    self.progress.emit(20)
                    d = cv2.fastNlMeansDenoisingColored(full_cv, None, h=12, hForColorComponents=12,
                                                        templateWindowSize=7, searchWindowSize=21)
                    result_full = cv2.edgePreservingFilter(d, flags=2, sigma_s=40, sigma_r=0.35)
                    self.progress.emit(85)
                    h, w = result_full.shape[:2]
                    ph = min(h, 2000)
                    pw = int(w * (ph / h))
                    result_proxy = cv2.resize(result_full, (pw, ph), interpolation=cv2.INTER_AREA)
                    method_used = "NLMeans+"
                    self.progress.emit(92)
                except ImportError:
                    self.finished_err.emit(
                        "AI Denoise requires:\npip install torch spandrel\n\n"
                        "Or at minimum: pip install opencv-python")
                    return
            
            self.status.emit(f"{method_used}: Applying...")
            self.progress.emit(95)
            full_pil = Image.fromarray(result_full)
            proxy_pil = Image.fromarray(result_proxy)
            self.finished_ok.emit(full_pil, proxy_pil, method_used)
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.finished_err.emit(str(e))


class SetupWorker(QThread):
    """Background worker to install AI packages and download models."""
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(bool, str)  # success, message
    
    def run(self):
        import subprocess, sys, urllib.request
        results = []
        
        # Step 1: Install torch
        try:
            import torch
            gpu = f" (CUDA: {torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else " (CPU)"
            self.status.emit(f"PyTorch {torch.__version__}{gpu} OK")
            results.append(f"torch: {torch.__version__}{gpu}")
        except ImportError:
            self.status.emit("Installing PyTorch (may take several minutes)...")
            self.progress.emit(5)
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", 
                    "torch", "torchvision", "--index-url", 
                    "https://download.pytorch.org/whl/cu121"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                results.append("torch: Installed (CUDA 12.1)")
            except Exception:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", 
                        "torch", "torchvision"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                    results.append("torch: Installed (CPU)")
                except Exception as e:
                    results.append(f"torch: FAILED ({e})")
        self.progress.emit(30)
        
        # Step 2: Install spandrel (lightweight model loader)
        try:
            import spandrel
            self.status.emit("spandrel already installed")
            results.append("spandrel: OK")
        except ImportError:
            self.status.emit("Installing spandrel...")
            self.progress.emit(35)
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "spandrel"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                results.append("spandrel: Installed")
            except Exception as e:
                results.append(f"spandrel: FAILED ({e})")
        self.progress.emit(45)
        
        # Step 3-5: Download model weights
        model_dir = Path.home() / ".ssc_models"
        model_dir.mkdir(exist_ok=True)
        
        models = [
            ("Swin2SR", "Swin2SR_RealworldSR_X4_64_BSRGAN_PSNR.pth",
             "https://github.com/mv-lab/swin2sr/releases/download/v0.0.1/Swin2SR_RealworldSR_X4_64_BSRGAN_PSNR.pth",
             "~12MB"),
            ("SCUNet", "scunet_color_real_psnr.pth",
             "https://github.com/cszn/KAIR/releases/download/v1.0/scunet_color_real_psnr.pth",
             "~7MB"),
            ("Real-ESRGAN", "RealESRGAN_x4plus.pth",
             "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
             "~64MB"),
        ]
        
        for i, (name, filename, url, size) in enumerate(models):
            pct = 50 + (i * 15)
            path = model_dir / filename
            if path.exists():
                self.status.emit(f"{name} model already downloaded")
                results.append(f"{name}: OK")
            else:
                self.status.emit(f"Downloading {name} ({size})...")
                self.progress.emit(pct)
                try:
                    urllib.request.urlretrieve(url, str(path))
                    results.append(f"{name}: Downloaded")
                except Exception as e:
                    results.append(f"{name}: FAILED ({e})")
            self.progress.emit(pct + 10)
        
        self.progress.emit(100)
        summary = "\n".join(results)
        all_ok = all("FAILED" not in r for r in results)
        self.finished.emit(all_ok, summary)


class ZoomableGraphicsView(QGraphicsView):
    """QGraphicsView with Ctrl+Wheel zoom support, centered on cursor."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._zoom_factor = 1.0
        self._is_user_zoomed = False
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHint(QPainter.SmoothPixmapTransform)

    def wheelEvent(self, event):
        # Zoom with Ctrl+Wheel or plain Wheel (no modifier needed for editor)
        zoom_in = event.angleDelta().y() > 0
        factor = 1.15 if zoom_in else 1 / 1.15
        new_zoom = self._zoom_factor * factor
        if 0.05 <= new_zoom <= 20.0:
            self._zoom_factor = new_zoom
            self._is_user_zoomed = True
            self.scale(factor, factor)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        """Double-click to reset zoom to fit."""
        if event.button() == Qt.LeftButton:
            self._is_user_zoomed = False
            self._zoom_factor = 1.0
            self.resetTransform()
            scene_items = self.scene().items()
            if scene_items:
                self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def reset_zoom(self):
        self._zoom_factor = 1.0
        self._is_user_zoomed = False
        self.resetTransform()


class PhotoEditorWidget(QWidget):
    request_close = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #1a1a1c;")
        
        self.current_paths = []
        self.active_path = None
        self._syncing_edits = False
        
        self.preview_pil_image = None
        self.proxy_pil_image = None
        
        self.edit_params = {
            'exposure': 0, 'contrast': 0, 'saturation': 0, 'temperature': 0, 'tint': 0,
            'highlights': 0, 'shadows': 0, 'whites': 0, 'blacks': 0, 'vignette': 0,
            'crop_top': 0, 'crop_bottom': 0, 'crop_left': 0, 'crop_right': 0,
            'rotate': 0, 'flip_h': False, 'flip_v': False
        }
        self.lut_filter = None
        self.lut_path = ""
        
        # Undo/Redo History
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._max_history = 50
        self._last_pushed_params: dict | None = None  # Avoid duplicate pushes
        
        self.sync_checkboxes = {}
        
        self.render_worker = RenderWorker(self)
        self.render_worker.result_ready.connect(self._on_high_res_rendered)
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self._setup_top_bar()
        
        work_layout = QHBoxLayout()
        self.layout.addLayout(work_layout)
        
        # Left Panel
        self.preview_container = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_container)
        self.preview_layout.setContentsMargins(10, 10, 10, 10)
        
        self.scene = CropScene()
        self.scene.crop_changed.connect(self._on_crop_drawn)
        
        self.view = ZoomableGraphicsView(self.scene)
        self.view.setBackgroundBrush(QBrush(QColor("#1e1e1e")))
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setRenderHint(QPainter.SmoothPixmapTransform)
        self.view.setFrameShape(QFrame.NoFrame)
        self.preview_layout.addWidget(self.view, 1)
        
        # Filmstrip
        self.filmstrip = QListWidget()
        self.filmstrip.setFlow(QListWidget.LeftToRight)
        self.filmstrip.setFixedHeight(120)
        self.filmstrip.setIconSize(QSize(100, 100))
        self.filmstrip.setSpacing(5)
        self.filmstrip.setStyleSheet("""
            QListWidget { background: #151515; border: 1px solid #333; border-radius: 8px; padding: 5px; }
            QListWidget::item { border-radius: 4px; border: 2px solid transparent; }
            QListWidget::item:selected { border: 2px solid #4CAF50; background: #222; }
            QListWidget::item:hover { background: #2a2a2a; }
        """)
        self.filmstrip.itemClicked.connect(self._on_filmstrip_clicked)
        self.preview_layout.addWidget(self.filmstrip)
        
        work_layout.addWidget(self.preview_container, 1)
        
        # Right Panel
        self._setup_right_panel(work_layout)
        
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(lambda: self._trigger_high_res_render())

    def _setup_top_bar(self):
        self.top_bar = QFrame(self)
        self.top_bar.setStyleSheet("background-color: rgba(30, 30, 32, 0.7); border-bottom: 1px solid rgba(255,255,255,0.1);")
        self.top_bar.setFixedHeight(50)
        
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)
        
        self.btn_close = QPushButton("Done Editing")
        self.btn_close.setFixedHeight(32)
        self.btn_close.setStyleSheet("QPushButton { background: rgba(50, 150, 250, 0.2); border: 1px solid #3296fa; color: #3296fa; border-radius: 6px; padding: 4px 16px; font-weight: bold; } QPushButton:hover { background: rgba(50, 150, 250, 0.4); }")
        self.btn_close.clicked.connect(self.request_close.emit)
        top_layout.addWidget(self.btn_close)
        
        self.btn_reset_all = QPushButton("Reset to Original")
        self.btn_reset_all.setFixedHeight(32)
        self.btn_reset_all.setStyleSheet("QPushButton { background: rgba(255, 100, 100, 0.2); border: 1px solid #ff6464; color: #ff6464; border-radius: 6px; padding: 4px 16px; font-weight: bold; } QPushButton:hover { background: rgba(255, 100, 100, 0.4); }")
        self.btn_reset_all.clicked.connect(self.reset_all_edits)
        top_layout.addWidget(self.btn_reset_all)
        
        # Undo / Redo Buttons
        undo_redo_style = """QPushButton {
            background: rgba(255, 255, 255, 0.08); border: 1px solid #555;
            color: #ccc; border-radius: 6px; padding: 4px 12px; font-weight: bold; font-size: 14px;
        } QPushButton:hover { background: rgba(255,255,255,0.15); color: white; }
        QPushButton:disabled { color: #444; border-color: #333; }"""
        
        self.btn_undo = QPushButton("↩ Undo")
        self.btn_undo.setFixedHeight(32)
        self.btn_undo.setStyleSheet(undo_redo_style)
        self.btn_undo.setShortcut(QKeySequence("Ctrl+Z"))
        self.btn_undo.setToolTip("Undo last edit (Ctrl+Z)")
        self.btn_undo.setEnabled(False)
        self.btn_undo.clicked.connect(self.undo_edit)
        top_layout.addWidget(self.btn_undo)
        
        self.btn_redo = QPushButton("Redo ↪")
        self.btn_redo.setFixedHeight(32)
        self.btn_redo.setStyleSheet(undo_redo_style)
        self.btn_redo.setShortcut(QKeySequence("Ctrl+Y"))
        self.btn_redo.setToolTip("Redo last edit (Ctrl+Y)")
        self.btn_redo.setEnabled(False)
        self.btn_redo.clicked.connect(self.redo_edit)
        top_layout.addWidget(self.btn_redo)
        
        top_layout.addStretch()
        
        self.btn_load_preset = QPushButton("📁 Load Preset")
        self.btn_load_preset.setFixedHeight(32)
        self.btn_load_preset.setStyleSheet("QPushButton { background: rgba(50, 150, 250, 0.15); border: 1px solid #3296fa; color: #8ac4ff; border-radius: 6px; padding: 4px 14px; font-weight: bold; } QPushButton:hover { background: rgba(50, 150, 250, 0.3); }")
        self.btn_load_preset.setToolTip("Load LUT (.cube), XMP, or JSON preset")
        self.btn_load_preset.clicked.connect(self._load_unified_preset)
        top_layout.addWidget(self.btn_load_preset)
        
        self.btn_save_preset = QPushButton("💾 Save Preset")
        self.btn_save_preset.setFixedHeight(32)
        self.btn_save_preset.setStyleSheet("QPushButton { background: rgba(100, 200, 100, 0.15); border: 1px solid #4CAF50; color: #81c784; border-radius: 6px; padding: 4px 14px; font-weight: bold; } QPushButton:hover { background: rgba(100, 200, 100, 0.3); }")
        self.btn_save_preset.clicked.connect(self.save_preset)
        top_layout.addWidget(self.btn_save_preset)
        
        self.layout.addWidget(self.top_bar)

    def _setup_right_panel(self, parent_layout):
        self.tools_panel = QFrame()
        self.tools_panel.setFixedWidth(380)
        self.tools_panel.setStyleSheet("""
            background-color: #1e1e20;
            border-left: 1px solid rgba(255,255,255,0.08);
            color: #E0E0E0;
        """)
        parent_layout.addWidget(self.tools_panel)
        
        self.tool_layout = QVBoxLayout(self.tools_panel)
        self.tool_layout.setSpacing(6)
        self.tool_layout.setContentsMargins(0, 0, 0, 8)
        
        scroll_edit = QScrollArea()
        scroll_edit.setWidgetResizable(True)
        scroll_edit.setStyleSheet("border: none; background: transparent;")
        inner_edit = QWidget()
        inner_edit.setStyleSheet("background: transparent;")
        inner_edit_layout = QVBoxLayout(inner_edit)
        inner_edit_layout.setSpacing(4)
        inner_edit_layout.setContentsMargins(12, 8, 12, 8)
        scroll_edit.setWidget(inner_edit)
        self.tool_layout.addWidget(scroll_edit, 1)
        
        def _section_header(title, parent_lay):
            """Create a clean section header with accent border."""
            header = QLabel(title)
            header.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                    font-weight: bold;
                    color: #aaaaaa;
                    letter-spacing: 1.5px;
                    padding: 8px 10px 4px 10px;
                    border-left: 3px solid #4CAF50;
                    margin-top: 8px;
                    background: rgba(255,255,255,0.02);
                    border-radius: 0px;
                }
            """)
            parent_lay.addWidget(header)
            return header

        def make_pro_slider(name, key, parent_lay):
            lay = QHBoxLayout()
            chk = QCheckBox()
            chk.setToolTip(f"Sync {name}")
            chk.setChecked(True)
            self.sync_checkboxes[key] = chk
            lay.addWidget(chk)
            
            sl = ProSliderWidget(name, -100, 100, 0)
            sl.valueChanged.connect(lambda v, k=key: self._on_pro_slider_changed(k, v))
            lay.addWidget(sl, 1)
            parent_lay.addLayout(lay)
            return sl

        _section_header("TRANSFORMS", inner_edit_layout)
        flip_lay = QHBoxLayout()
        chk_sync_flip = QCheckBox()
        chk_sync_flip.setChecked(True)
        chk_sync_flip.setToolTip("Sync Flips in Batch Export")
        self.sync_checkboxes['flips'] = chk_sync_flip
        flip_lay.addWidget(chk_sync_flip)
        
        btn_flip_h = QPushButton("↔") 
        btn_flip_h.setToolTip("Flip Horizontal")
        btn_flip_h.setCheckable(True)
        btn_flip_h.setFixedSize(40, 30)
        btn_flip_h.setStyleSheet("QPushButton { font-weight: bold; font-size: 16px; background: #2a2a2e; border: 1px solid #444; border-radius: 6px; } QPushButton:checked { background: #4CAF50; border-color: #4CAF50; } QPushButton:hover { background: #383840; }")
        
        btn_flip_v = QPushButton("↕") 
        btn_flip_v.setToolTip("Flip Vertical")
        btn_flip_v.setCheckable(True)
        btn_flip_v.setFixedSize(40, 30)
        btn_flip_v.setStyleSheet("QPushButton { font-weight: bold; font-size: 16px; background: #2a2a2e; border: 1px solid #444; border-radius: 6px; } QPushButton:checked { background: #4CAF50; border-color: #4CAF50; } QPushButton:hover { background: #383840; }")
        
        def on_flip():
            self._push_undo()
            self.edit_params['flip_h'] = btn_flip_h.isChecked()
            self.edit_params['flip_v'] = btn_flip_v.isChecked()
            self._render_proxy()
            self._trigger_high_res_render()
            
        btn_flip_h.toggled.connect(on_flip)
        btn_flip_v.toggled.connect(on_flip)
        self.btn_flip_h = btn_flip_h
        self.btn_flip_v = btn_flip_v
        
        flip_lay.addWidget(btn_flip_h)
        flip_lay.addWidget(btn_flip_v)
        flip_lay.addStretch()
        inner_edit_layout.addLayout(flip_lay)
        
        # Rotation -45 to 45
        rot_header_lay = QHBoxLayout()
        rot_lbl = QLabel("ROTATE & AUTO-LEVEL")
        rot_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #888; letter-spacing: 1px; padding-left: 4px;")
        rot_header_lay.addWidget(rot_lbl)
        self.btn_auto_level = QPushButton("Auto Level")
        self.btn_auto_level.setFixedHeight(24)
        self.btn_auto_level.setStyleSheet("QPushButton { font-weight: bold; font-size: 10px; background: #2a2a2e; border: 1px solid #444; border-radius: 4px; padding: 2px 10px; } QPushButton:hover { background: #4CAF50; border-color: #4CAF50; }")
        self.btn_auto_level.clicked.connect(self._auto_level_rotation)
        rot_header_lay.addStretch()
        rot_header_lay.addWidget(self.btn_auto_level)
        inner_edit_layout.addLayout(rot_header_lay)
        
        self.sl_rot = make_pro_slider("Angle", "rotate", inner_edit_layout)
        self.sl_rot._min = -45
        self.sl_rot._max = 45
        self.sl_rot._default = 0
        self.sl_rot.sliderPressed.connect(self.scene.show_rotation_grid)
        self.sl_rot.sliderReleased.connect(self.scene.hide_rotation_grid)
        
        # Upright (Perspective Correction)
        upright_lbl = QLabel("UPRIGHT")
        upright_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #888; letter-spacing: 1px; padding-left: 4px; margin-top: 4px;")
        inner_edit_layout.addWidget(upright_lbl)
        
        upright_lay = QHBoxLayout()
        upright_btn_style = """
            QPushButton {
                font-size: 10px; font-weight: bold;
                background: #2a2a2e; border: 1px solid #444;
                border-radius: 4px; padding: 4px 10px;
                color: #ccc;
            }
            QPushButton:hover { background: #4CAF50; border-color: #4CAF50; color: white; }
        """
        for mode_name, mode_key in [("Level", "level"), ("Vertical", "vertical"), 
                                      ("Full", "full"), ("Auto", "auto")]:
            btn = QPushButton(mode_name)
            btn.setFixedHeight(26)
            btn.setStyleSheet(upright_btn_style)
            btn.clicked.connect(lambda checked, m=mode_key: self._apply_upright(m))
            upright_lay.addWidget(btn)
        inner_edit_layout.addLayout(upright_lay)
        
        # Crop section
        crop_header_lay = QHBoxLayout()
        crop_lbl = QLabel("CROP")
        crop_lbl.setStyleSheet("font-size: 10px; font-weight: bold; color: #888; letter-spacing: 1px; padding-left: 4px;")
        crop_header_lay.addWidget(crop_lbl)
        crop_hint = QLabel("Draw & drag handles")
        crop_hint.setStyleSheet("font-size: 9px; color: #555; margin-top: 6px;")
        crop_header_lay.addWidget(crop_hint)
        crop_header_lay.addStretch()
        inner_edit_layout.addLayout(crop_header_lay)
        
        crop_btn_lay = QHBoxLayout()
        chk_sync_crop = QCheckBox()
        chk_sync_crop.setChecked(True)
        chk_sync_crop.setToolTip("Sync Crop in Batch Export")
        self.sync_checkboxes['crop'] = chk_sync_crop
        crop_btn_lay.addWidget(chk_sync_crop)
        
        btn_reset_crop = QPushButton("Reset Crop")
        btn_reset_crop.setStyleSheet("QPushButton { background: #2a2a2e; border: 1px solid #444; border-radius: 4px; padding: 4px 10px; } QPushButton:hover { background: #383840; }")
        btn_reset_crop.clicked.connect(self.reset_crop)
        crop_btn_lay.addWidget(btn_reset_crop)
        crop_btn_lay.addStretch()
        inner_edit_layout.addLayout(crop_btn_lay)
        
        _section_header("BASIC", inner_edit_layout)
        self.sl_exp = make_pro_slider("Exposure", "exposure", inner_edit_layout)
        self.sl_con = make_pro_slider("Contrast", "contrast", inner_edit_layout)
        self.sl_sat = make_pro_slider("Saturation", "saturation", inner_edit_layout)
        self.sl_temp = make_pro_slider("Temp", "temperature", inner_edit_layout)
        self.sl_tint = make_pro_slider("Tint", "tint", inner_edit_layout)
        
        _section_header("TONE", inner_edit_layout)
        self.sl_hl = make_pro_slider("Highlights", "highlights", inner_edit_layout)
        self.sl_shad = make_pro_slider("Shadows", "shadows", inner_edit_layout)
        self.sl_wh = make_pro_slider("Whites", "whites", inner_edit_layout)
        self.sl_bl = make_pro_slider("Blacks", "blacks", inner_edit_layout)
        
        _section_header("DETAIL", inner_edit_layout)
        self.sl_clarity = make_pro_slider("Clarity", "clarity", inner_edit_layout)
        self.sl_dehaze = make_pro_slider("Dehaze", "dehaze", inner_edit_layout)
        self.sl_sharp = make_pro_slider("Sharpness", "sharpness", inner_edit_layout)
        
        _section_header("NOISE REDUCTION", inner_edit_layout)
        self.sl_nr = make_pro_slider("NR Strength", "noise_reduction", inner_edit_layout)
        self.sl_nr._min = 0
        self.sl_nr._max = 100
        self.sl_nr._default = 0
        
        ai_nr_lay = QHBoxLayout()
        self.btn_ai_denoise = QPushButton("AI Denoise")
        self.btn_ai_denoise.setFixedHeight(28)
        self.btn_ai_denoise.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: bold;
                background: rgba(150, 100, 255, 0.15);
                border: 1px solid #9c64ff;
                color: #c9a0ff;
                border-radius: 4px; padding: 4px 12px;
            }
            QPushButton:hover { background: rgba(150, 100, 255, 0.35); color: white; }
            QPushButton:disabled { background: rgba(80, 60, 120, 0.15); color: #665599; }
        """)
        self.btn_ai_denoise.setToolTip("Apply AI-based noise reduction (one-shot, modifies source)")
        self.btn_ai_denoise.clicked.connect(self._apply_ai_denoise)
        ai_nr_lay.addWidget(self.btn_ai_denoise)
        
        self.btn_undo_destructive = QPushButton("Undo")
        self.btn_undo_destructive.setFixedHeight(28)
        self.btn_undo_destructive.setStyleSheet("""
            QPushButton {
                font-size: 10px; font-weight: bold;
                background: rgba(255, 150, 50, 0.15);
                border: 1px solid #ff9632;
                color: #ffb070;
                border-radius: 4px; padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(255, 150, 50, 0.35); color: white; }
            QPushButton:disabled { background: transparent; border-color: #444; color: #555; }
        """)
        self.btn_undo_destructive.setToolTip("Undo AI Denoise / Upright (restore original)")
        self.btn_undo_destructive.setEnabled(False)
        self.btn_undo_destructive.clicked.connect(self._undo_destructive)
        ai_nr_lay.addWidget(self.btn_undo_destructive)
        ai_nr_lay.addStretch()
        inner_edit_layout.addLayout(ai_nr_lay)
        
        # AI Denoise progress
        self.denoise_status_lbl = QLabel("")
        self.denoise_status_lbl.setStyleSheet("font-size: 10px; color: #9c64ff; padding-left: 4px;")
        self.denoise_status_lbl.hide()
        inner_edit_layout.addWidget(self.denoise_status_lbl)
        
        self.denoise_progress = QProgressBar()
        self.denoise_progress.setFixedHeight(4)
        self.denoise_progress.setStyleSheet("""
            QProgressBar { border: none; background: #2a2a2e; border-radius: 2px; }
            QProgressBar::chunk { background: #9c64ff; border-radius: 2px; }
        """)
        self.denoise_progress.hide()
        inner_edit_layout.addWidget(self.denoise_progress)
        
        # Initialize denoise worker
        self.denoise_worker = DenoiseWorker(self)
        self.denoise_worker.progress.connect(self._on_denoise_progress)
        self.denoise_worker.status.connect(self._on_denoise_status)
        self.denoise_worker.finished_ok.connect(self._on_denoise_done)
        self.denoise_worker.finished_err.connect(self._on_denoise_error)
        
        # AI Setup button
        self.btn_ai_setup = QPushButton("Install AI Models")
        self.btn_ai_setup.setFixedHeight(24)
        self.btn_ai_setup.setStyleSheet("""
            QPushButton {
                font-size: 10px;
                background: transparent;
                border: 1px dashed #555;
                color: #888;
                border-radius: 4px; padding: 2px 8px;
            }
            QPushButton:hover { border-color: #9c64ff; color: #c9a0ff; }
            QPushButton:disabled { color: #555; }
        """)
        self.btn_ai_setup.setToolTip("Install torch + basicsr and download SCUNet/DnCNN models")
        self.btn_ai_setup.clicked.connect(self._install_ai_models)
        inner_edit_layout.addWidget(self.btn_ai_setup)
        
        # Initialize setup worker
        self.setup_worker = SetupWorker(self)
        self.setup_worker.progress.connect(self._on_denoise_progress)
        self.setup_worker.status.connect(self._on_denoise_status)
        self.setup_worker.finished.connect(self._on_setup_finished)
        
        _section_header("EFFECTS", inner_edit_layout)
        self.sl_vig = make_pro_slider("Vignette", "vignette", inner_edit_layout)
        
        _section_header("PRESET", inner_edit_layout)
        preset_info_lay = QHBoxLayout()
        self.lbl_preset = QLabel("No preset loaded")
        self.lbl_preset.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        preset_info_lay.addWidget(self.lbl_preset)
        preset_info_lay.addStretch()
        inner_edit_layout.addLayout(preset_info_lay)
        inner_edit_layout.addStretch()
        
        # Batch Control
        self.btn_export = QPushButton("Export All Selected")
        self.btn_export.setFixedHeight(40)
        self.btn_export.setStyleSheet("QPushButton { background: #4CAF50; color: white; border-radius: 6px; padding: 4px 12px; font-weight: bold; font-size: 14px; } QPushButton:hover { background: #43a047; }")
        self.btn_export.clicked.connect(self.run_batch_export)
        self.tool_layout.addWidget(self.btn_export)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("QProgressBar { border-radius: 4px; background: #333; } QProgressBar::chunk { background: #4CAF50; border-radius: 4px; }")
        self.progress_bar.hide()
        self.tool_layout.addWidget(self.progress_bar)

    def load_images(self, paths):
        if not paths: return
        self.current_paths = paths
        
        self.filmstrip.clear()
        for p in paths:
            item = QListWidgetItem()
            img = load_pil_image(p, max_size=150)
            if img:
                qimg = pil_to_qimage(img)
                pm = QPixmap.fromImage(qimg).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                item.setIcon(QIcon(pm))
            item.setData(Qt.UserRole, str(p))
            self.filmstrip.addItem(item)
            
        self.filmstrip.setCurrentRow(0)
        self._load_active_image(paths[0])

    def _on_filmstrip_clicked(self, item):
        path = Path(item.data(Qt.UserRole))
        if path != self.active_path:
            self._load_active_image(path)

    def _load_active_image(self, path):
        self.active_path = path
        self.view.reset_zoom()
        
        # Load full resolution for sharp zoom quality
        img = load_pil_image(path, max_size=None)
        proxy = load_pil_image(path, max_size=800)
        
        if img and proxy:
            self.preview_pil_image = img.copy()
            self.proxy_pil_image = proxy.copy()
            self._trigger_high_res_render()

    def reset_all_edits(self):
        self._push_undo()
        self.edit_params = {
            'exposure': 0, 'contrast': 0, 'saturation': 0, 'temperature': 0, 'tint': 0,
            'highlights': 0, 'shadows': 0, 'whites': 0, 'blacks': 0, 'vignette': 0,
            'clarity': 0, 'dehaze': 0, 'sharpness': 0, 'noise_reduction': 0,
            'crop_top': 0, 'crop_bottom': 0, 'crop_left': 0, 'crop_right': 0,
            'rotate': 0, 'flip_h': False, 'flip_v': False
        }
        self.lut_filter = None
        self.lut_path = ""
        self._sync_sidebar_from_params()
        self._update_visual_crop_box()
        self._render_proxy()
        self._trigger_high_res_render()

    def _push_undo(self):
        """Push current edit_params onto the undo stack (with deduplication)."""
        snapshot = self.edit_params.copy()
        # Avoid pushing duplicate states (e.g. rapid slider drags)
        if self._last_pushed_params == snapshot:
            return
        self._last_pushed_params = snapshot
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._max_history:
            self._undo_stack.pop(0)
        # Clear redo stack on new action (standard UX)
        self._redo_stack.clear()
        self._update_undo_buttons()

    def _update_undo_buttons(self):
        self.btn_undo.setEnabled(len(self._undo_stack) > 0)
        self.btn_redo.setEnabled(len(self._redo_stack) > 0)

    def undo_edit(self):
        if not self._undo_stack:
            return
        # Save current state to redo stack
        self._redo_stack.append(self.edit_params.copy())
        # Restore previous state
        self.edit_params = self._undo_stack.pop()
        self._last_pushed_params = None
        self._sync_sidebar_from_params()
        self._update_visual_crop_box()
        self._render_proxy()
        self._trigger_high_res_render()
        self._update_undo_buttons()

    def redo_edit(self):
        if not self._redo_stack:
            return
        # Save current state to undo stack
        self._undo_stack.append(self.edit_params.copy())
        # Restore redo state
        self.edit_params = self._redo_stack.pop()
        self._last_pushed_params = None
        self._sync_sidebar_from_params()
        self._update_visual_crop_box()
        self._render_proxy()
        self._trigger_high_res_render()
        self._update_undo_buttons()

    def _on_crop_drawn(self, top, bottom, left, right):
        self.edit_params['crop_top'] = top
        self.edit_params['crop_bottom'] = bottom
        self.edit_params['crop_left'] = left
        self.edit_params['crop_right'] = right
        
    def reset_crop(self):
        self.edit_params['crop_top'] = 0
        self.edit_params['crop_bottom'] = 0
        self.edit_params['crop_left'] = 0
        self.edit_params['crop_right'] = 0
        self.scene.crop_box.hide()
        self.scene.dim_overlay.hide()

    def _on_pro_slider_changed(self, key, value):
        if not self._syncing_edits and self.proxy_pil_image:
            # Push current state to undo stack before changing
            self._push_undo()
            self.edit_params[key] = value
            # Render fast proxy immediately
            self._render_proxy()
            # Debounce high res render
            self.render_timer.start(250)

    def _update_visual_crop_box(self):
        img_rect = self.scene.pixmap_item.boundingRect()
        if img_rect.width() > 0 and img_rect.height() > 0:
            top = self.edit_params.get('crop_top', 0)
            bot = self.edit_params.get('crop_bottom', 0)
            left = self.edit_params.get('crop_left', 0)
            right = self.edit_params.get('crop_right', 0)
            
            x1 = (left / 100.0) * img_rect.width()
            y1 = (top / 100.0) * img_rect.height()
            x2 = img_rect.width() - ((right / 100.0) * img_rect.width())
            y2 = img_rect.height() - ((bot / 100.0) * img_rect.height())
            
            if top==0 and bot==0 and left==0 and right==0:
                self.scene.crop_box.hide()
                self.scene.dim_overlay.hide()
            else:
                rect = QRectF(x1, y1, x2 - x1, y2 - y1)
                self.scene.crop_box.setRect(rect)
                self.scene._update_dim_overlay(rect)
                self.scene.crop_box.show()
                self.scene.dim_overlay.show()

    def _render_proxy(self):
        if not self.proxy_pil_image: return
        
        # Fast render using Numpy
        preview_params = self.edit_params.copy()
        # Visual crop so we zero out actual crop for background processing
        preview_params['crop_top'] = 0
        preview_params['crop_bottom'] = 0
        preview_params['crop_left'] = 0
        preview_params['crop_right'] = 0
        
        edited = PhotoEditor.apply_edits(self.proxy_pil_image, preview_params, self.lut_filter)
        qimg = pil_to_qimage(edited)
        pm = QPixmap.fromImage(qimg)
        
        # When setting proxy, we keep the original scene bounding rect if possible to avoid jumping
        if self.preview_pil_image and 'last_w' in dir(self):
            # Scale up to high-res size for seamless transition
            pm = pm.scaled(self.last_w, self.last_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            
        self.scene.pixmap_item.setPixmap(pm)
        self.view.setSceneRect(self.scene.pixmap_item.boundingRect())
        
        # Only fit on high-res loads to prevent jitter
        if not hasattr(self, 'last_w'):
            self.view.fitInView(self.scene.pixmap_item, Qt.KeepAspectRatio)

    def _trigger_high_res_render(self):
        if not self.preview_pil_image: return
        
        preview_params = self.edit_params.copy()
        preview_params['crop_top'] = 0
        preview_params['crop_bottom'] = 0
        preview_params['crop_left'] = 0
        preview_params['crop_right'] = 0
        
        # Start worker
        self.render_worker.setup(self.preview_pil_image, preview_params, self.lut_filter)
        self.render_worker.start()

    def _on_high_res_rendered(self, qimg):
        pm = QPixmap.fromImage(qimg)
        self.last_w = pm.width()
        self.last_h = pm.height()
        
        self.scene.pixmap_item.setPixmap(pm)
        self.view.setSceneRect(self.scene.pixmap_item.boundingRect())
        self._update_visual_crop_box()
        # Only fit to view if user hasn't manually zoomed
        if not self.view._is_user_zoomed:
            self.view.fitInView(self.scene.pixmap_item, Qt.KeepAspectRatio)

    def _auto_level_rotation(self):
        """Lightroom-grade auto horizon leveling using probabilistic Hough transform
        with length-weighted angle averaging."""
        try:
            import cv2
            import numpy as np
            
            if self.proxy_pil_image is None: return
            
            img_cv = np.array(self.proxy_pil_image.convert('L'))
            h, w = img_cv.shape
            
            # Multi-scale edge detection for robustness
            edges1 = cv2.Canny(img_cv, 30, 100, apertureSize=3)
            edges2 = cv2.Canny(img_cv, 50, 200, apertureSize=3)
            edges = cv2.bitwise_or(edges1, edges2)
            
            # Use probabilistic Hough — gives line segments with start/end points
            min_line_length = max(w, h) * 0.08  # Lines must be at least 8% of image
            max_line_gap = max(w, h) * 0.02
            lines = cv2.HoughLinesP(edges, 1, np.pi / 360, 80,
                                     minLineLength=int(min_line_length),
                                     maxLineGap=int(max_line_gap))
            
            if lines is not None and len(lines) > 0:
                angles = []
                weights = []
                
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                    angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                    
                    # Only near-horizontal lines (within ±15° of horizontal)
                    if abs(angle) <= 15 or abs(abs(angle) - 180) <= 15:
                        # Normalize angle to -15..+15 range
                        if abs(angle) > 90:
                            angle = angle - 180 if angle > 0 else angle + 180
                        angles.append(angle)
                        weights.append(length)  # Weight by line length
                
                if angles:
                    angles = np.array(angles)
                    weights = np.array(weights)
                    
                    # Reject outliers using IQR
                    q1, q3 = np.percentile(angles, [25, 75])
                    iqr = q3 - q1
                    mask = (angles >= q1 - 1.5 * iqr) & (angles <= q3 + 1.5 * iqr)
                    angles = angles[mask]
                    weights = weights[mask]
                    
                    if len(angles) > 0:
                        # Weighted average for precision
                        weighted_angle = np.average(angles, weights=weights)
                        correction = -weighted_angle
                        
                        # Clamp to slider range
                        correction = max(-45, min(45, correction))
                        self.sl_rot.setValue(int(round(correction)))
                        return
            
            # Fallback: no strong lines found
            QMessageBox.information(self, "Auto Level", 
                "Could not detect a clear horizon line.\nTry on an image with visible horizon or straight edges.")
                    
        except ImportError:
            QMessageBox.warning(self, "Missing Dependency", 
                "Auto-Level requires OpenCV.\nRun: pip install opencv-python")

    def _apply_upright(self, mode='auto'):
        """Apply perspective correction (Upright).
        Modes: 'level' (horizon only), 'vertical' (verticals only), 
               'full' (both), 'auto' (auto-detect best)
        """
        try:
            import cv2
            import numpy as np
            
            if self.preview_pil_image is None: return

            self._save_source_backup()

            # Work on proxy for speed, apply result to full
            img_cv = np.array(self.proxy_pil_image.convert('RGB'))
            gray = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            
            edges = cv2.Canny(gray, 50, 150, apertureSize=3)
            min_len = int(max(w, h) * 0.1)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 360, 80,
                                     minLineLength=min_len,
                                     maxLineGap=int(max(w, h) * 0.02))
            
            if lines is None or len(lines) == 0:
                QMessageBox.information(self, "Upright", "No clear lines detected for perspective correction.")
                return
            
            h_angles = []  # Horizontal line angles
            h_weights = []
            v_angles = []  # Vertical line angles
            v_weights = []
            
            for line in lines:
                x1, y1, x2, y2 = line[0]
                length = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                
                # Horizontal lines: within ±20° of 0° or ±180°
                if abs(angle) <= 20 or abs(abs(angle) - 180) <= 20:
                    norm_angle = angle
                    if abs(norm_angle) > 90:
                        norm_angle = norm_angle - 180 if norm_angle > 0 else norm_angle + 180
                    h_angles.append(norm_angle)
                    h_weights.append(length)
                # Vertical lines: within ±20° of ±90°
                elif abs(abs(angle) - 90) <= 20:
                    v_angle = angle - 90 if angle > 0 else angle + 90
                    v_angles.append(v_angle)
                    v_weights.append(length)
            
            # Calculate corrections
            h_correction = 0
            v_correction = 0
            
            if h_angles and mode in ('level', 'full', 'auto'):
                h_arr = np.array(h_angles)
                h_w = np.array(h_weights)
                # IQR outlier removal
                if len(h_arr) > 2:
                    q1, q3 = np.percentile(h_arr, [25, 75])
                    iqr = q3 - q1
                    mask = (h_arr >= q1 - 1.5 * iqr) & (h_arr <= q3 + 1.5 * iqr)
                    h_arr, h_w = h_arr[mask], h_w[mask]
                if len(h_arr) > 0:
                    h_correction = np.average(h_arr, weights=h_w)
            
            if v_angles and mode in ('vertical', 'full', 'auto'):
                v_arr = np.array(v_angles)
                v_w = np.array(v_weights)
                if len(v_arr) > 2:
                    q1, q3 = np.percentile(v_arr, [25, 75])
                    iqr = q3 - q1
                    mask = (v_arr >= q1 - 1.5 * iqr) & (v_arr <= q3 + 1.5 * iqr)
                    v_arr, v_w = v_arr[mask], v_w[mask]
                if len(v_arr) > 0:
                    v_correction = np.average(v_arr, weights=v_w)
            
            # Build perspective transform
            # Rotation for horizon leveling
            rot_angle = -h_correction
            
            # Perspective for vertical correction (keystone)
            # Vertical tilt creates a trapezoidal distortion
            v_shift = np.tan(np.radians(v_correction)) * 0.15  # Scale factor
            
            # Source and destination points for perspective transform
            src_pts = np.float32([
                [0, 0], [w, 0], [w, h], [0, h]
            ])
            
            if mode == 'level':
                # Just rotation
                self.sl_rot.setValue(int(round(max(-45, min(45, rot_angle)))))
                return
            elif mode == 'vertical':
                # Vertical perspective only
                offset = int(w * abs(v_shift))
                if v_correction > 0:  # Converging at top
                    dst_pts = np.float32([
                        [offset, 0], [w - offset, 0], [w, h], [0, h]
                    ])
                else:  # Converging at bottom
                    dst_pts = np.float32([
                        [0, 0], [w, 0], [w - offset, h], [offset, h]
                    ])
            elif mode in ('full', 'auto'):
                # Both rotation + vertical perspective
                offset_v = int(w * abs(v_shift))
                if v_correction > 0:
                    dst_pts = np.float32([
                        [offset_v, 0], [w - offset_v, 0], [w, h], [0, h]
                    ])
                else:
                    dst_pts = np.float32([
                        [0, 0], [w, 0], [w - offset_v, h], [offset_v, h]
                    ])
                # Apply rotation via slider (combined with perspective)
                self.sl_rot.setValue(int(round(max(-45, min(45, rot_angle)))))
            
            if mode != 'level':
                # Apply perspective warp to both proxy and full
                M = cv2.getPerspectiveTransform(src_pts, dst_pts)
                
                # Apply to full resolution
                full_cv = np.array(self.preview_pil_image.convert('RGB'))
                fh, fw = full_cv.shape[:2]
                # Scale the transform matrix for full resolution
                scale_x, scale_y = fw / w, fh / h
                S = np.array([[scale_x, 0, 0], [0, scale_y, 0], [0, 0, 1]], dtype=np.float64)
                S_inv = np.array([[1/scale_x, 0, 0], [0, 1/scale_y, 0], [0, 0, 1]], dtype=np.float64)
                M_full = S @ M @ S_inv
                
                warped_full = cv2.warpPerspective(full_cv, M_full, (fw, fh),
                                                   borderMode=cv2.BORDER_REFLECT)
                self.preview_pil_image = Image.fromarray(warped_full)
                
                # Apply to proxy
                warped_proxy = cv2.warpPerspective(
                    np.array(self.proxy_pil_image.convert('RGB')), M, (w, h),
                    borderMode=cv2.BORDER_REFLECT)
                self.proxy_pil_image = Image.fromarray(warped_proxy)
                
                self._render_proxy()
                self._trigger_high_res_render()
                
        except ImportError:
            QMessageBox.warning(self, "Missing Dependency", 
                "Upright requires OpenCV.\nRun: pip install opencv-python")

    def _save_source_backup(self):
        """Save backup of current source images for undo."""
        self._source_backup = {
            'preview': self.preview_pil_image.copy(),
            'proxy': self.proxy_pil_image.copy()
        }
        self.btn_undo_destructive.setEnabled(True)
    
    def _undo_destructive(self):
        """Restore source images from backup."""
        if hasattr(self, '_source_backup') and self._source_backup:
            self.preview_pil_image = self._source_backup['preview'].copy()
            self.proxy_pil_image = self._source_backup['proxy'].copy()
            self._source_backup = None
            self.btn_undo_destructive.setEnabled(False)
            self._render_proxy()
            self._trigger_high_res_render()

    def _apply_ai_denoise(self):
        """Start AI denoise in background thread."""
        if self.preview_pil_image is None: return
        if self.denoise_worker.isRunning(): return
        
        self._save_source_backup()
        
        # Show progress UI
        self.btn_ai_denoise.setEnabled(False)
        self.btn_ai_denoise.setText("Processing...")
        self.denoise_status_lbl.setText("Detecting best available model...")
        self.denoise_status_lbl.show()
        self.denoise_progress.setValue(0)
        self.denoise_progress.show()
        
        # Start worker
        self.denoise_worker.setup(self.preview_pil_image.copy(), self.proxy_pil_image.copy())
        self.denoise_worker.start()
    
    def _on_denoise_progress(self, val):
        self.denoise_progress.setValue(val)
    
    def _on_denoise_status(self, text):
        self.denoise_status_lbl.setText(text)
    
    def _on_denoise_done(self, full_pil, proxy_pil, method):
        self.preview_pil_image = full_pil
        self.proxy_pil_image = proxy_pil
        self._render_proxy()
        self._trigger_high_res_render()
        
        self.denoise_progress.setValue(100)
        self.denoise_status_lbl.setText(f"Done — {method}")
        self.btn_ai_denoise.setEnabled(True)
        self.btn_ai_denoise.setText("AI Denoise")
        
        # Auto-hide progress after 3s
        QTimer.singleShot(3000, self._hide_denoise_progress)
    
    def _on_denoise_error(self, msg):
        self.btn_ai_denoise.setEnabled(True)
        self.btn_ai_denoise.setText("AI Denoise")
        self.denoise_status_lbl.setText("Failed")
        self._source_backup = None
        self.btn_undo_destructive.setEnabled(False)
        QTimer.singleShot(2000, self._hide_denoise_progress)
        QMessageBox.warning(self, "AI Denoise Error", msg)
    
    def _hide_denoise_progress(self):
        self.denoise_progress.hide()
        self.denoise_status_lbl.hide()

    def _install_ai_models(self):
        """Start background installation of AI packages and model downloads."""
        if self.setup_worker.isRunning(): return
        
        self.btn_ai_setup.setEnabled(False)
        self.btn_ai_setup.setText("Installing...")
        self.denoise_status_lbl.setText("Starting AI setup...")
        self.denoise_status_lbl.show()
        self.denoise_progress.setValue(0)
        self.denoise_progress.show()
        
        self.setup_worker.start()
    
    def _on_setup_finished(self, success, summary):
        self.btn_ai_setup.setEnabled(True)
        self.btn_ai_setup.setText("Install AI Models")
        self.denoise_progress.setValue(100)
        
        if success:
            self.denoise_status_lbl.setText("AI setup complete")
        else:
            self.denoise_status_lbl.setText("Setup completed with errors")
        
        QTimer.singleShot(3000, self._hide_denoise_progress)
        
        title = "AI Setup Complete" if success else "AI Setup - Partial"
        QMessageBox.information(self, title, summary)

    def _load_unified_preset(self):
        """Unified loader: auto-detects LUT (.cube), XMP, or JSON preset."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Preset", "", 
            "All Presets (*.cube *.xmp *.json);;LUT Files (*.cube);;XMP Presets (*.xmp);;JSON Presets (*.json)"
        )
        if not path: return
        
        ext = Path(path).suffix.lower()
        
        if ext == '.cube':
            # LUT file
            self.lut_path = path
            self.lut_filter = PhotoEditor.load_cube_lut(path)
            self.lbl_preset.setText(f"🎨 LUT: {Path(path).stem[:20]}")
            self.lbl_preset.setStyleSheet("color: #81c784; font-size: 10px; font-weight: bold;")
            self._render_proxy()
            self._trigger_high_res_render()
            
        elif ext == '.xmp':
            # Lightroom XMP
            mapped = parse_xmp_preset(path)
            if mapped:
                self.edit_params.update(mapped)
                self._sync_sidebar_from_params()
                self.lbl_preset.setText(f"📷 XMP: {Path(path).stem[:20]}")
                self.lbl_preset.setStyleSheet("color: #8ac4ff; font-size: 10px; font-weight: bold;")
                self._trigger_high_res_render()
            else:
                QMessageBox.warning(self, "Warning", "Could not parse XMP parameters.")
                
        elif ext == '.json':
            # JSON preset
            try:
                with open(path, 'r') as f:
                    preset = json.load(f)
                default_edits = {
                    'exposure': 0, 'contrast': 0, 'saturation': 0, 'temperature': 0, 'tint': 0,
                    'highlights': 0, 'shadows': 0, 'whites': 0, 'blacks': 0, 'vignette': 0,
                    'clarity': 0, 'dehaze': 0, 'sharpness': 0,
                    'crop_top': 0, 'crop_bottom': 0, 'crop_left': 0, 'crop_right': 0,
                    'rotate': 0, 'flip_h': False, 'flip_v': False
                }
                self.edit_params = preset.get("edit_params", default_edits)
                self.lut_path = preset.get("lut_path", "")
                if self.lut_path and Path(self.lut_path).exists():
                    self.lut_filter = PhotoEditor.load_cube_lut(self.lut_path)
                else:
                    self.lut_filter = None
                    self.lut_path = ""
                self._sync_sidebar_from_params()
                self.lbl_preset.setText(f"⚙️ JSON: {Path(path).stem[:20]}")
                self.lbl_preset.setStyleSheet("color: #ffb74d; font-size: 10px; font-weight: bold;")
                self._trigger_high_res_render()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load preset: {e}")

    def _sync_sidebar_from_params(self):
        self._syncing_edits = True
        
        self.sl_exp.setValue(self.edit_params.get('exposure', 0))
        self.sl_con.setValue(self.edit_params.get('contrast', 0))
        self.sl_sat.setValue(self.edit_params.get('saturation', 0))
        self.sl_temp.setValue(self.edit_params.get('temperature', 0))
        self.sl_tint.setValue(self.edit_params.get('tint', 0))
        
        self.sl_hl.setValue(self.edit_params.get('highlights', 0))
        self.sl_shad.setValue(self.edit_params.get('shadows', 0))
        self.sl_wh.setValue(self.edit_params.get('whites', 0))
        self.sl_bl.setValue(self.edit_params.get('blacks', 0))
        self.sl_vig.setValue(self.edit_params.get('vignette', 0))
        
        self.sl_clarity.setValue(self.edit_params.get('clarity', 0))
        self.sl_dehaze.setValue(self.edit_params.get('dehaze', 0))
        self.sl_sharp.setValue(self.edit_params.get('sharpness', 0))
        self.sl_nr.setValue(self.edit_params.get('noise_reduction', 0))
        
        self.sl_rot.setValue(self.edit_params.get('rotate', 0))
        
        self.btn_flip_h.blockSignals(True)
        self.btn_flip_v.blockSignals(True)
        self.btn_flip_h.setChecked(self.edit_params.get('flip_h', False))
        self.btn_flip_v.setChecked(self.edit_params.get('flip_v', False))
        self.btn_flip_h.blockSignals(False)
        self.btn_flip_v.blockSignals(False)
        
        if self.lut_path:
            self.lbl_preset.setText(f"🎨 LUT: {Path(self.lut_path).stem[:20]}")
            self.lbl_preset.setStyleSheet("color: #81c784; font-size: 10px; font-weight: bold;")
        else:
            self.lbl_preset.setText("No preset loaded")
            self.lbl_preset.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
            
        self._syncing_edits = False
        self._update_visual_crop_box()

    def save_preset(self):
        preset = {
            "edit_params": self.edit_params,
            "lut_path": self.lut_path
        }
        path, _ = QFileDialog.getSaveFileName(self, "Save Edit Preset", "edit_preset.json", "JSON (*.json)")
        if path:
            with open(path, 'w') as f:
                json.dump(preset, f, indent=4)
            QMessageBox.information(self, "Saved", "Preset saved successfully.")
            


    def get_synced_params(self):
        synced_params = {}
        for key, chk in self.sync_checkboxes.items():
            if not chk.isChecked(): continue
            if key == 'lut': continue
            if key == 'crop':
                synced_params['crop_top'] = self.edit_params.get('crop_top', 0)
                synced_params['crop_bottom'] = self.edit_params.get('crop_bottom', 0)
                synced_params['crop_left'] = self.edit_params.get('crop_left', 0)
                synced_params['crop_right'] = self.edit_params.get('crop_right', 0)
            elif key == 'flips':
                synced_params['flip_h'] = self.edit_params.get('flip_h', False)
                synced_params['flip_v'] = self.edit_params.get('flip_v', False)
            else:
                synced_params[key] = self.edit_params.get(key, 0)
        return synced_params

    def run_batch_export(self):
        if not self.current_paths: return
        
        out_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory")
        if not out_dir: return
        out_dir = Path(out_dir)
        
        self.btn_export.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setMaximum(len(self.current_paths))
        self.progress_bar.setValue(0)
        
        synced_params = self.get_synced_params()
        sync_lut = self.sync_checkboxes.get('lut', QCheckBox()).isChecked()
        lut_to_apply = self.lut_filter if sync_lut else None
        
        success = 0; fail = 0
        
        for i, path in enumerate(self.current_paths):
            try:
                img = load_pil_image(path)
                if img:
                    final_params = {
                        'exposure': 0, 'contrast': 0, 'saturation': 0, 'temperature': 0, 'tint': 0,
                        'highlights': 0, 'shadows': 0, 'whites': 0, 'blacks': 0, 'vignette': 0,
                        'clarity': 0, 'dehaze': 0, 'sharpness': 0, 'noise_reduction': 0,
                        'crop_top': 0, 'crop_bottom': 0, 'crop_left': 0, 'crop_right': 0,
                        'rotate': 0, 'flip_h': False, 'flip_v': False
                    }
                    final_params.update(synced_params)
                    
                    edited = PhotoEditor.apply_edits(img, final_params, lut_to_apply)
                    
                    if any(final_params[k] > 0 for k in ['crop_top', 'crop_bottom', 'crop_left', 'crop_right']):
                        c_top = final_params['crop_top'] / 100.0
                        c_bot = final_params['crop_bottom'] / 100.0
                        c_left = final_params['crop_left'] / 100.0
                        c_right = final_params['crop_right'] / 100.0
                        
                        w, h = edited.size
                        left = int(w * c_left); top = int(h * c_top)
                        right = int(w * (1.0 - c_right)); bottom = int(h * (1.0 - c_bot))
                        if right > left and bottom > top:
                            edited = edited.crop((left, top, right, bottom))

                    out_path = out_dir / f"{path.stem}_edited.jpg"
                    edited.save(str(out_path), "JPEG", quality=95)
                    success += 1
                else: fail += 1
            except Exception as e:
                print(f"Edit export error on {path.name}: {e}")
                fail += 1
                
            self.progress_bar.setValue(i + 1)
            
        QMessageBox.information(self, "Export Complete", f"Successfully exported {success} images.\nFailed: {fail}")
        self.btn_export.setEnabled(True)
        self.progress_bar.hide()
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Only auto-fit if user hasn't manually zoomed (prevents zoom reset on monitor change)
        if self.preview_pil_image and not self.view._is_user_zoomed:
            self.view.fitInView(self.scene.pixmap_item, Qt.KeepAspectRatio)
