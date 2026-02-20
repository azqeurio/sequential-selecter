import os
import csv
from pathlib import Path
from PIL import Image, ExifTags

class RatingManager:
    def __init__(self, folder_path: Path):
        self.folder_path = folder_path
        self.ratings_file = folder_path / "ratings.csv"
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not self.ratings_file.exists():
            with open(self.ratings_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["Filename", "Rating", "Date", "Camera"])

    def save_rating(self, filename: str, rating: int, date: str = "", camera: str = ""):
        rows = []
        updated = False
        
        # Read existing
        if self.ratings_file.exists():
            with open(self.ratings_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    rows.append(header)
                for row in reader:
                    if len(row) > 0 and row[0] == filename:
                        # Update
                        rows.append([filename, str(rating), date, camera])
                        updated = True
                    else:
                        rows.append(row)
        
        if not updated:
            rows.append([filename, str(rating), date, camera])

        # Write back
        with open(self.ratings_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)

    def load_ratings(self) -> list[dict]:
        ratings = []
        if self.ratings_file.exists():
            try:
                with open(self.ratings_file, 'r', newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader, None) # Skip header
                    for row in reader:
                        if len(row) >= 2:
                            r_data = {
                                "filename": row[0],
                                "rating": int(row[1]),
                                "date": row[2] if len(row) > 2 else "",
                                "camera": row[3] if len(row) > 3 else ""
                            }
                            ratings.append(r_data)
            except Exception as e:
                print(f"Error loading ratings: {e}")
        return ratings

    def get_unique_filters(self):
        ratings = self.load_ratings()
        dates = set()
        cameras = set()
        for r in ratings:
            if r['date']: dates.add(r['date'])
            if r['camera']: cameras.add(r['camera'])
        return sorted(list(dates)), sorted(list(cameras))

    def get_rating(self, filename: str) -> int:
        """Get the current rating for a file, or 0 if unrated."""
        for r in self.load_ratings():
            if r['filename'] == filename:
                return r['rating']
        return 0

    def remove_rating(self, filename: str):
        """Remove the rating for a specific file."""
        rows = []
        if self.ratings_file.exists():
            with open(self.ratings_file, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    rows.append(header)
                for row in reader:
                    if len(row) > 0 and row[0] == filename:
                        continue  # Skip this row (remove rating)
                    rows.append(row)
        with open(self.ratings_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(rows)

    def clear_all_ratings(self):
        """Remove all ratings (reset CSV to just header)."""
        with open(self.ratings_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Filename", "Rating", "Date", "Camera"])

def get_image_metadata(path: Path):
    date_str = ""
    camera_str = ""
    try:
        img = Image.open(path)
        exif = img._getexif()
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
