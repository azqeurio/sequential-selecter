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
                             # If thumb is significantly smaller than requested, fallback
                             if max(w, h) < max_size:
                                 print(f"DEBUG: Discarding thumb {w}x{h} for max_size {max_size}")
                                 img = None 
                    except Exception:
                        pass
                    
                    # Priority 2: Postprocess (Slow / Fallback)
                    if img is None:
                        # Adaptive Quality: Use half_size only if sufficient
                        # Typical RAW is ~6000px. Half is ~3000px.
                        # If max_size > 3000, we need full size.
                        use_half = True
                        if max_size is not None and max_size > 3000:
                            use_half = False
                        
                        print(f"DEBUG: Postprocessing RAW. MaxSize: {max_size}, Half: {use_half}")
                        img = Image.fromarray(raw.postprocess(
                            use_camera_wb=True,
                            no_auto_bright=True,
                            bright=1.0, # Default brightness
                            user_sat=None,
                            output_bps=8,
                            half_size=use_half
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
        print(f"Error loading {path.name}: {e}")
        return None

    if img:
        print(f"DEBUG: Loaded {path.name}, Size: {img.size}")
    return img
