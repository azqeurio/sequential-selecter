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
                    except Exception:
                        pass
                    
                    # Priority 2: Postprocess (Slow / Fallback)
                    if img is None:
                        # Use lower quality for thumbnails to save CPU
                        # half_size=True reduces dimension by half (4x faster)
                        img = Image.fromarray(raw.postprocess(
                            use_camera_wb=True,
                            no_auto_bright=True,
                            bright=1.0, # Default brightness
                            user_sat=None,
                            output_bps=8,
                            half_size=True # Critical for performance
                        ))
            except Exception as e:
                print(f"RAW load failed for {path}: {e}")
                pass

        # 3. Standard Formats (JPG, PNG, WebP...)
        else:
            img = Image.open(str(path))
            # Force load to check for integrity
            img.load() 

        # 4. Final Fallback (Try opening as standard image if not touched yet)
        if img is None:
            img = Image.open(str(path))
            img.load()

        # Handle EXIF Orientation
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Resize for Thumbnail (Lanczos for quality, but considering speed)
        # If max_size is small, we can use Bilinear for speed during scroll
        if max_size is not None and img is not None:
            # Aspect Ratio Calculation
            w, h = img.size
            if w > max_size or h > max_size:
                # Use thumbnail() method which modifies in-place
                # Image.BILINEAR is significantly faster than BICUBIC/LANCZOS with acceptable quality for thumbnails
                img.thumbnail((max_size, max_size), Image.BILINEAR)
                
    except Exception as e:
        # print(f"Error loading {path.name}: {e}")
        return None

    return img
