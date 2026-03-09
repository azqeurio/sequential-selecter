import csv
from pathlib import Path
from PIL import Image


class RatingManager:
    def __init__(self, folder_path: Path):
        self.folder_path = folder_path
        self.ratings_file = folder_path / "ratings.csv"
        self._cache: dict[str, dict] | None = None  # Lazy-loaded cache
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not self.ratings_file.exists():
            with open(self.ratings_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Filename", "Rating", "Date", "Camera"])

    def _normalize_key(self, file_ref: str | Path) -> str:
        """Build a stable key for an image path (folder-relative when possible)."""
        p = file_ref if isinstance(file_ref, Path) else Path(file_ref)
        try:
            if p.is_absolute():
                rel = p.resolve().relative_to(self.folder_path.resolve())
                key = rel.as_posix()
            else:
                key = p.as_posix()
        except Exception:
            key = p.name
        return key or p.name

    def key_for_path(self, path: Path) -> str:
        return self._normalize_key(path)

    def _ensure_cache(self):
        """Lazily load ratings into memory cache."""
        if self._cache is not None:
            return
        self._cache = {}
        if self.ratings_file.exists():
            try:
                with open(self.ratings_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader, None)  # Skip header
                    for row in reader:
                        if len(row) >= 2:
                            key = row[0]
                            self._cache[key] = {
                                "key": key,
                                "filename": Path(key).name,
                                "rating": int(row[1]),
                                "date": row[2] if len(row) > 2 else "",
                                "camera": row[3] if len(row) > 3 else ""
                            }
            except Exception as e:
                print(f"Error loading ratings: {e}")

    def save_rating(self, file_ref: str | Path, rating: int, date: str = "", camera: str = ""):
        self._ensure_cache()
        key = self._normalize_key(file_ref)
        # Update cache
        self._cache[key] = {
            "key": key,
            "filename": Path(key).name,
            "rating": rating,
            "date": date,
            "camera": camera
        }
        # Write all to disk
        self._write_cache_to_disk()

    def _write_cache_to_disk(self):
        """Flush the cache to the CSV file."""
        rows = [["Filename", "Rating", "Date", "Camera"]]
        for data in self._cache.values():
            rows.append([data["key"], str(data["rating"]), data["date"], data["camera"]])
        with open(self.ratings_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)

    def load_ratings(self) -> list[dict]:
        self._ensure_cache()
        return list(self._cache.values())

    def get_unique_filters(self):
        self._ensure_cache()
        dates = set()
        cameras = set()
        for r in self._cache.values():
            if r['date']:
                dates.add(r['date'])
            if r['camera']:
                cameras.add(r['camera'])
        return sorted(list(dates)), sorted(list(cameras))

    def get_rating(self, file_ref: str | Path) -> int:
        """Get the current rating for a file, or 0 if unrated. O(1) dict lookup."""
        self._ensure_cache()
        key = self._normalize_key(file_ref)
        data = self._cache.get(key)

        # Backward compatibility: older ratings.csv used bare filename only.
        if data is None and "/" in key:
            data = self._cache.get(Path(key).name)

        return data['rating'] if data else 0

    def remove_rating(self, file_ref: str | Path):
        """Remove the rating for a specific file."""
        self._ensure_cache()
        key = self._normalize_key(file_ref)

        removed = False
        if key in self._cache:
            del self._cache[key]
            removed = True
        elif "/" in key:
            fallback_key = Path(key).name
            if fallback_key in self._cache:
                del self._cache[fallback_key]
                removed = True

        if removed:
            self._write_cache_to_disk()

    def clear_all_ratings(self):
        """Remove all ratings (reset CSV to just header)."""
        self._cache = {}
        with open(self.ratings_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Filename", "Rating", "Date", "Camera"])


def get_image_metadata(path: Path):
    date_str = ""
    camera_str = ""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if exif:
                # Date
                # 36867 is DateTimeOriginal, 306 is DateTime
                date_val = exif.get(36867) or exif.get(306)
                if date_val:
                    # Format: YYYY:MM:DD HH:MM:SS -> YYYY-MM-DD
                    date_str = str(date_val).split(' ')[0].replace(':', '-')

                # Camera
                # 271 is Make, 272 is Model
                make = exif.get(271, "")
                model = exif.get(272, "")
                camera_str = f"{make} {model}".strip()
    except Exception:
        pass
    return date_str, camera_str


