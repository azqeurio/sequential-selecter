import os
import hashlib
from pathlib import Path

def sanitize(name: str) -> str:
    """Sanitize a string so it is safe for use as a folder or file name."""
    if not name:
        return "Unknown"
    safe_chars = []
    for ch in name.strip():
        if ch.isalnum() or ch in " ._-()+[]#/":
            safe_chars.append(ch)
        else:
            safe_chars.append(" ")
    s = " ".join("".join(safe_chars).split())
    trimmed = s[:120] if len(s) > 120 else s
    return trimmed or "Unknown"

def unique_dest(dest_dir: Path, name: str) -> Path:
    """Generate a destination file path that will not collide with existing files."""
    base, ext = os.path.splitext(name)
    cand = dest_dir / name
    i = 1
    while cand.exists():
        cand = dest_dir / f"{base}_{i}{ext}"
        i += 1
    return cand

def file_hash(path: Path, chunk_size: int = 1 << 20) -> str:
    """Compute the SHA-1 hash of a file (reads in chunks for efficiency)."""
    sha1 = hashlib.sha1()
    try:
        with open(path, "rb") as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                sha1.update(data)
        return sha1.hexdigest()
    except Exception:
        return ""
