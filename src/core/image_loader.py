import io
from pathlib import Path
import rawpy
from PIL import Image, ImageOps
import pillow_heif

def load_pil_image(path: Path, max_size: int | None = None) -> Image.Image | None:
    ext = path.suffix.lower()
    img = None

    try:
        # 1. HEIC / HEIF
        if ext in {".heif", ".heic"}:
            heif_file = pillow_heif.read_heif(str(path))
            img = Image.frombytes(
                heif_file.mode,
                heif_file.size,
                heif_file.data,
                "raw"
            )
        
        # 2. RAW Formats (ARW, CR2, CR3, NEF, ORF, RAF, DNG, etc.)
        elif ext in {".arw", ".cr2", ".cr3", ".nef", ".rw2", ".orf", ".raf", ".dng", ".srw"}:
            try:
                with rawpy.imread(str(path)) as raw:
                    # Priority 1: Extract Embedded Thumbnail (Fastest)
                    try:
                        thumb = raw.extract_thumb()
                        if thumb.format == rawpy.ThumbFormat.JPEG:
                            img = Image.open(io.BytesIO(thumb.data))
                        elif thumb.format == rawpy.ThumbFormat.BITMAP:
                            img = Image.fromarray(thumb.data)
                        
                        # RESOLUTION CHECK: Discard thumb if too small
                        if img is not None and max_size is not None:
                             w, h = img.size
                             if max(w, h) < max_size:
                                 img = None 
                    except Exception:
                        pass
                    
                    # Priority 2: Postprocess (Slow / Fallback)
                    if img is None:
                        # Adaptive Quality: Use half_size only if sufficient
                        # Typical RAW is ~6000px. Half is ~3000px.
                        use_half = True
                        if max_size is not None and max_size > 3000:
                            use_half = False
                        
                        img = Image.fromarray(raw.postprocess(
                            use_camera_wb=True,
                            no_auto_bright=True,
                            bright=1.0,
                            user_sat=None,
                            output_bps=8,
                            half_size=use_half
                        ))
            except Exception:
                pass

        # 3. Standard Formats (JPG, PNG, WebP...)
        else:
            img = Image.open(str(path))
            img.load() 

        # 4. Final Fallback
        if img is None:
            img = Image.open(str(path))
            img.load()

        # Handle EXIF Orientation
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Resize for Thumbnail
        if max_size is not None and img is not None:
            w, h = img.size
            if w > max_size or h > max_size:
                img.thumbnail((max_size, max_size), Image.LANCZOS)
                
    except Exception:
        return None

    return img
