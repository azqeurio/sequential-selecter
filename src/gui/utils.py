from PIL import Image
from PySide6.QtGui import QImage, QPixmap

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
    try:
        data = img.tobytes("raw", img.mode)
        qimg = QImage(data, w, h, w * bpp, fmt)
        return qimg.copy()
    except Exception:
        # Fallback for weird modes or errors
        return QImage()
