import os
import csv
from pathlib import Path
from PIL import Image, ExifTags

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
                            self._cache[row[0]] = {
                                "filename": row[0],
                                "rating": int(row[1]),
                                "date": row[2] if len(row) > 2 else "",
                                "camera": row[3] if len(row) > 3 else ""
                            }
            except Exception as e:
                print(f"Error loading ratings: {e}")

    def save_rating(self, filename: str, rating: int, date: str = "", camera: str = ""):
        self._ensure_cache()
        # Update cache
        self._cache[filename] = {
            "filename": filename,
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
            rows.append([data["filename"], str(data["rating"]), data["date"], data["camera"]])
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
            if r['date']: dates.add(r['date'])
            if r['camera']: cameras.add(r['camera'])
        return sorted(list(dates)), sorted(list(cameras))

    def get_rating(self, filename: str) -> int:
        """Get the current rating for a file, or 0 if unrated. O(1) dict lookup."""
        self._ensure_cache()
        data = self._cache.get(filename)
        return data['rating'] if data else 0

    def remove_rating(self, filename: str):
        """Remove the rating for a specific file."""
        self._ensure_cache()
        if filename in self._cache:
            del self._cache[filename]
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
