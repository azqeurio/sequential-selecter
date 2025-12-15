import os
import shutil
from pathlib import Path
from typing import Generator, Callable

from .metadata import extract_meta, RAW_EXT
from .utils import file_hash, unique_dest

IMAGE_EXT = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff",
    ".arw", ".cr2", ".cr3", ".nef", ".orf", ".rw2", ".raf", ".dng", ".srw", ".pef"
}

def walk_images(root: Path) -> Generator[Path, None, None]:
    """Traverse all image files under the root folder."""
    for dp, _, fns in os.walk(root):
        for fn in fns:
            p = Path(dp) / fn
            if p.suffix.lower() in IMAGE_EXT:
                yield p

class Sorter:
    def __init__(self, config: dict):
        self.config = config
        self.dest_root = Path(config.get("dest_root", "."))
        self.structure = config.get("structure", ["camera", "date", "kind"]) # ordered list of tokens
        self.action = config.get("action", "copy")  # copy | move
        self.policy = config.get("policy", "ask")
        self.skip_hash = config.get("skip_hash_dup", False)

        self.preview_plan: dict[Path, list[Path]] = {}
        self.conflicts: list[tuple[Path, Path]] = []

    def scan(self, src_root: Path, progress_cb: Callable[[int, int], None] | None = None) -> tuple[list[Path], list[dict]]:
        files = list(walk_images(src_root))
        metas = []
        total = len(files)
        
        for idx, f in enumerate(files):
            meta = extract_meta(f)
            metas.append(meta)
            if progress_cb:
                progress_cb(idx + 1, total)
        
        return files, metas

    def plan_sort(self, files: list[Path], metas: list[dict]) -> dict[Path, list[Path]]:
        """
        Generate a plan based on self.structure.
        structure example: ["year", "camera", "kind"] -> dest/2023/Canon/raw/file.ext
        """
        plan = {}
        self.conflicts = []

        for meta in metas:
            src_path = meta["path"]
            
            # Build target directory
            current_dir = self.dest_root
            
            for token in self.structure:
                val = ""
                key = token.lower()
                
                if key == "date":
                    val = meta.get("date", "Unknown Date")
                elif key == "year":
                    val = meta.get("year", "Unknown Year")
                elif key == "month":
                    # meta["month"] comes as YYYY-MM usually
                    val = meta.get("month", "Unknown Month")
                elif key == "camera":
                    val = meta.get("camera", "Unknown Camera")
                elif key == "lens":
                    val = meta.get("lens", "Unknown Lens")
                elif key == "kind":
                    # kind is raw, jpg, other
                    val = meta.get("kind", "other")
                elif key == "ext":
                     # extension grouping .jpg, .arw
                     val = meta["path"].suffix.lower().replace('.', '')
                
                # Sanitize to be safe for folder name
                # (meta values are already sanitized in metadata.py but double check empty)
                if not val: val = "Unknown"
                
                current_dir = current_dir / val
            
            if current_dir not in plan:
                plan[current_dir] = []
            plan[current_dir].append(src_path)
            
        self.preview_plan = plan
        return plan

    def execute_sort(self, plan: dict[Path, list[Path]], 
                     progress_cb: Callable[[str, int, int], None] | None = None,
                     ask_cb: Callable[[Path, Path], str] | None = None) -> dict:
        """
        Execute the plan.
        ask_cb: callback(src, dst) -> 'rename' | 'skip' | 'overwrite'
        """
        results = {"success": 0, "skipped": 0, "errors": 0}
        total_files = sum(len(srcs) for srcs in plan.values())
        processed = 0

        for dest_dir, srcs in plan.items():
            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                # Log error?
                results["errors"] += len(srcs)
                processed += len(srcs)
                continue

            for src in srcs:
                processed += 1
                dst = dest_dir / src.name

                # Hash check
                if self.skip_hash and dst.exists():
                    if file_hash(src) == file_hash(dst):
                        results["skipped"] += 1
                        if progress_cb: progress_cb(f"Skipped (hash): {src.name}", processed, total_files)
                        continue

                # Policy check
                decision = self.policy
                if dst.exists():
                    if self.policy == "ask" and ask_cb:
                        decision = ask_cb(src, dst)
                    
                    if decision == "skip":
                        results["skipped"] += 1
                        if progress_cb: progress_cb(f"Skipped: {src.name}", processed, total_files)
                        continue
                    elif decision == "rename":
                        dst = unique_dest(dest_dir, src.name)
                
                try:
                    if self.action == "move":
                        shutil.move(str(src), str(dst))
                    else:
                        shutil.copy2(str(src), str(dst))
                    results["success"] += 1
                    if progress_cb: progress_cb(f"Processed: {src.name}", processed, total_files)
                except Exception as e:
                    results["errors"] += 1
                    if progress_cb: progress_cb(f"Error: {e}", processed, total_files)

        return results
