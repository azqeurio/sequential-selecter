import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    PIL_OK = True
except Exception:
    PIL_OK = False

try:
    import exifread
    EXIFREAD_OK = True
except Exception:
    EXIFREAD_OK = False

from .utils import sanitize

RAW_EXT = {
    ".arw", ".cr2", ".cr3", ".nef", ".orf", ".rw2", ".raf", ".dng", ".srw", ".pef", ".tif", ".tiff"
}
PROC_EXT = {".jpg", ".jpeg", ".heic", ".heif", ".png"}

def which_exiftool() -> str | None:
    """Return the path to the exiftool executable if available, otherwise None."""
    return shutil.which("exiftool")

def parse_dt_str(s: str) -> datetime | None:
    """Convert an EXIF date string into a :class:`datetime` object."""
    s = s.strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z"):
        try:
            dt = datetime.strptime(s, fmt)
            # Remove timezone information if present
            return dt.replace(tzinfo=None)
        except Exception:
            continue
    return None

def exif_from_pillow(path: Path):
    """Extract date, camera and lens metadata using Pillow."""
    if not PIL_OK:
        return None, None, None
    try:
        with Image.open(path) as im:  # type: ignore
            exif = im.getexif()
            if not exif:
                return None, None, None
            # Find date/time string
            dto = None
            for key in (36867, 306):  # DateTimeOriginal, DateTime
                if key in exif:
                    dto = parse_dt_str(str(exif.get(key)))
                    if dto:
                        break
            model = str(exif.get(0x0110) or "")  # Model
            lens = str(exif.get(0xA434) or "")  # LensModel
            return dto, (model or None), (lens or None)
    except Exception:
        return None, None, None

def exif_from_exifread(path: Path):
    """Extract EXIF metadata using the :mod:`exifread` module."""
    if not EXIFREAD_OK:
        return None, None, None
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False, stop_tag="UNDEF", strict=True)  # type: ignore
        dto = None
        for key in ("EXIF DateTimeOriginal", "Image DateTime"):
            if key in tags:
                dto = parse_dt_str(str(tags[key]))
                if dto:
                    break
        model = None
        for key in ("Image Model", "EXIF Model"):
            if key in tags:
                model = str(tags[key]).strip()
                break
        lens = None
        for key in ("EXIF LensModel", "EXIF LensSpecification", "EXIF LensMake", "MakerNote LensType"):
            if key in tags:
                lens = str(tags[key]).strip()
                break
        return dto, model or None, lens or None
    except Exception:
        return None, None, None

def exif_from_exiftool(path: Path):
    """Extract EXIF metadata using the external ``exiftool`` executable."""
    exe = which_exiftool()
    if not exe:
        return None, None, None
    try:
        # Call exiftool to extract only essential fields (model, make, lens, date)
        cmd = [exe, "-json", "-S", "-Model", "-Make", "-LensModel", "-Lens", "-DateTimeOriginal", str(path)]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        data = json.loads(out.decode("utf-8", errors="ignore"))[0] if out else {}
        dto = None
        if "DateTimeOriginal" in data:
            dto = parse_dt_str(str(data.get("DateTimeOriginal")))
        model = data.get("Model") or ""
        make = data.get("Make") or ""
        if make and model and make not in model:
            model = f"{make} {model}"
        lens = data.get("LensModel") or data.get("Lens") or ""
        return dto, (model or None), (lens or None)
    except Exception:
        return None, None, None

def extract_meta(path: Path) -> dict:
    """
    Extract date, camera, lens and file type information from the given file.
    """
    dto = cam = lens = None
    # pillow
    d1, c1, l1 = exif_from_pillow(path)
    if d1:
        dto = d1
    if c1:
        cam = c1
    if l1:
        lens = l1
    # exifread
    d2, c2, l2 = exif_from_exifread(path)
    if not dto and d2:
        dto = d2
    if not cam and c2:
        cam = c2
    if not lens and l2:
        lens = l2
    # exiftool
    d3, c3, l3 = exif_from_exiftool(path)
    if not dto and d3:
        dto = d3
    if not cam and c3:
        cam = c3
    if not lens and l3:
        lens = l3
    # fallback
    if dto is None:
        try:
            dto = datetime.fromtimestamp(path.stat().st_mtime)
        except Exception:
            dto = datetime.now()
    year = f"{dto:%Y}"
    month = f"{dto:%Y-%m}"
    date = f"{dto:%Y-%m-%d}"
    cam = sanitize(cam or "Unknown Camera")
    lens = sanitize(lens or "Unknown Lens")
    ext = path.suffix.lower()
    if ext in RAW_EXT:
        kind = "raw"
    elif ext in PROC_EXT:
        kind = "jpg"
    else:
        kind = "other"
    return {
        "path": path,
        "dt": dto,
        "year": year,
        "month": month,
        "date": date,
        "camera": cam,
        "lens": lens,
        "kind": kind,
    }
