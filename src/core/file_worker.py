
import shutil
import os
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, Slot

class FileOperationWorker(QObject):
    """
    Worker class for performing file operations in a background thread.
    """
    finished = Signal()
    error = Signal(str)
    progress = Signal(int, int) # current, total
    
    def __init__(self, operations: list[tuple[Path, Path]], op_type='move'):
        """
        :param operations: List of (source, destination) tuples
        :param op_type: 'move' or 'copy'
        """
        super().__init__()
        self.operations = operations
        self.op_type = op_type
        self._abort = False

    @Slot()
    def run(self):
        total = len(self.operations)
        for i, (src, dest) in enumerate(self.operations):
            if self._abort:
                break
            
            try:
                # Ensure destination directory exists
                dest.parent.mkdir(parents=True, exist_ok=True)
                
                # Handle collision logic (simple rename for safety is usually good, 
                # but caller might have already handled it. We'll duplicate check just in case here too?)
                # actually, caller usually checks. But let's be safe.
                final_dest = dest
                if final_dest.exists():
                     base = final_dest.stem
                     ext = final_dest.suffix
                     count = 1
                     while final_dest.exists():
                         final_dest = final_dest.with_name(f"{base}_copy_{count}{ext}")
                         count += 1
                
                if self.op_type == 'move':
                    shutil.move(str(src), str(final_dest))
                elif self.op_type == 'copy':
                    shutil.copy2(str(src), str(final_dest))
                
                self.progress.emit(i + 1, total)
                
            except Exception as e:
                self.error.emit(f"Failed to {self.op_type} {src.name}: {e}")
        
        self.finished.emit()

    def abort(self):
        self._abort = True
