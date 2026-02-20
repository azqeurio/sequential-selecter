from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QObject, QSettings
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFileDialog, QComboBox, QCheckBox, QGroupBox, QProgressBar,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QTabWidget,
    QTextEdit, QRadioButton, QButtonGroup, QListWidget, QListWidgetItem
)
from ..core.sorter import Sorter
from ..i18n.translations import TRANSLATIONS
from .styles import DARK_STYLE

class Worker(QObject):
    progress = Signal(str, int, int) # status, current, total
    finished = Signal()
    error = Signal(str)
    
    # For Scan
    scan_result = Signal(object, object) # files, metas

    # For Sort
    sort_result = Signal(object) # results dict

    def __init__(self, sorter, mode='scan'):
        super().__init__()
        self.sorter = sorter
        self.mode = mode
        self.src_root = None
        self.plan = None
        self._mutex = QObject() # dummy

    def run_scan(self):
        try:
            files, metas = self.sorter.scan(self.src_root, self._emit_progress)
            self.scan_result.emit(files, metas)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def run_sort(self):
        try:
            # We use a simple callback wrapper
            res = self.sorter.execute_sort(self.plan, self._emit_progress_sort)
            self.sort_result.emit(res)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()

    def _emit_progress(self, current, total):
        self.progress.emit("Scanning...", current, total)

    def _emit_progress_sort(self, status, current, total):
        self.progress.emit(status, current, total)


class OrganizerWidget(QWidget):
    # Emit signal when done or closed if we want main window to know
    finished = Signal() 

    def __init__(self, parent=None, language='ko'):
        super().__init__(parent)
        self.lang = language
        self.tr = TRANSLATIONS.get(language, TRANSLATIONS['en'])
        
        self.sorter_config = {
            "dest_root": "",
            "structure": ["date", "camera", "kind"],
            "action": "copy",
            "policy": "rename", # Default safe policy
            "skip_hash_dup": False
        }
        
        self.current_files = []
        self.current_metas = []
        self.current_plan = {}
        
        self.worker_thread = None
        
        # External widget references (will be set by main window)
        self.ext_tree: QTreeWidget | None = None
        self.ext_log: QTextEdit | None = None
        self.ext_progress: QProgressBar | None = None

        self._load_settings() # Load before UI setup
        self._setup_ui()
        # Style sheet will be inherited or set by parent, but we can enforce dark style for components
        # self.setStyleSheet(DARK_STYLE) 
        
    def set_external_widgets(self, tree: QTreeWidget, log_text: QTextEdit, progress: QProgressBar):
        self.ext_tree = tree
        self.ext_log = log_text
        self.ext_progress = progress
        
        # Setup tree columns if needed
        if self.ext_tree:
            self.ext_tree.setHeaderLabels(["Folder", "Files"])

    def _t(self, key):
        return self.tr.get(key, key)

    def _load_settings(self):
        settings = QSettings("SSC", "Organizer")
        
        # Load Structure
        # We store as list of dicts: [{"key": "date", "checked": True}, ...]
        # Simple string list is easier if order is just keys, but we need check state.
        # Let's use QSettings arrays or just a JSON string if simple.
        # Actually, QSettings supports lists.
        # Let's use a simple format: "key:1" or "key:0" string list.
        
        saved_structure = settings.value("structure", [])
        
        # Default if empty (First Run)
        if not saved_structure:
            # Requested Defaults: Camera, Year, Month, Date, Kind (Checked), Lens (Unchecked)
            saved_structure = [
                "camera:1",
                "year:1",
                "month:1",
                "date:1",
                "kind:1",
                "lens:0"
            ]
        
        # Parse
        parsed_data = []
        seen_keys = set()
        for item in saved_structure:
            if ":" in item:
                key, state = item.split(":", 1)
                parsed_data.append((key, state == "1"))
                seen_keys.add(key)
        
        # Add any missing keys (future proofing)
        all_keys = {
            "date": "날짜 (YYYY-MM-DD)",
            "camera": "카메라 모델",
            "kind": "파일 종류 (RAW/JPG)",
            "year": "연도 (YYYY)",
            "month": "월 (YYYY-MM)",
            "lens": "렌즈 모델"
        }
        
        for key in all_keys:
            if key not in seen_keys:
                parsed_data.append((key, False))
        
        # Store for _setup_ui to use
        self._initial_structure = parsed_data

    def _save_settings(self):
        settings = QSettings("SSC", "Organizer")
        
        # Build list
        data = []
        for i in range(self.list_structure.count()):
            item = self.list_structure.item(i)
            key = item.data(Qt.UserRole)
            checked = "1" if item.checkState() == Qt.Checked else "0"
            data.append(f"{key}:{checked}")
            
        settings.setValue("structure", data)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Settings Panel (Always visible)
        self.settings_panel = QWidget()
        self._setup_settings_panel(self.settings_panel)
        main_layout.addWidget(self.settings_panel)
        
        # Bottom Buttons
        btn_layout = QHBoxLayout()
        self.btn_scan = QPushButton("스캔 시작")
        self.btn_scan.clicked.connect(self.start_scan)
        self.btn_start = QPushButton("이동 시작")
        self.btn_start.clicked.connect(self.start_sort)
        self.btn_start.setEnabled(False)
        
        self.btn_close = QPushButton("닫기") 
        self.btn_close.clicked.connect(self.finished.emit)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_scan)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_close)
        main_layout.addLayout(btn_layout)

    def _setup_settings_panel(self, parent):
        layout = QVBoxLayout(parent)
        
        # Source
        src_grp = QGroupBox("원본 폴더 선택")
        src_layout = QHBoxLayout()
        self.lbl_src = QLabel("선택된 폴더 없음")
        btn_src = QPushButton("...")
        btn_src.setFixedWidth(40)
        btn_src.clicked.connect(self.browse_src)
        src_layout.addWidget(self.lbl_src)
        src_layout.addWidget(btn_src)
        src_grp.setLayout(src_layout)
        layout.addWidget(src_grp)
        
        # Dest
        dst_grp = QGroupBox("타겟 폴더 선택")
        dst_layout = QHBoxLayout()
        self.lbl_dst = QLabel("선택된 폴더 없음")
        btn_dst = QPushButton("...")
        btn_dst.setFixedWidth(40)
        btn_dst.clicked.connect(self.browse_dst)
        dst_layout.addWidget(self.lbl_dst)
        dst_layout.addWidget(btn_dst)
        dst_grp.setLayout(dst_layout)
        layout.addWidget(dst_grp)
        
        # Options
        opt_grp = QGroupBox("설정")
        opt_layout = QVBoxLayout()
        
        # Sorting Structure (Reorderable List)
        lbl_struct = QLabel("폴더 구조 (드래그하여 순서 변경):")
        opt_layout.addWidget(lbl_struct)
        
        self.list_structure = QListWidget()
        self.list_structure.setDragDropMode(QListWidget.InternalMove)
        # Expansion Fix: Use Minimum Height and remove fixed limit
        self.list_structure.setMinimumHeight(400) 
        
        # Use loaded structure
        # Map keys back to labels
        key_label_map = {
            "date": "날짜 (YYYY-MM-DD)",
            "camera": "카메라 모델",
            "kind": "파일 종류 (RAW/JPG)",
            "year": "연도 (YYYY)",
            "month": "월 (YYYY-MM)",
            "lens": "렌즈 모델"
        }

        # Use self._initial_structure populated in _load_settings
        if hasattr(self, '_initial_structure'):
             for key, checked in self._initial_structure:
                 label = key_label_map.get(key, key)
                 item = QListWidgetItem(label)
                 item.setData(Qt.UserRole, key)
                 item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                 self.list_structure.addItem(item)
        else:
             # Fallback (Should not happen if _load_settings called)
             tokens = [
                ("날짜 (YYYY-MM-DD)", "date", True),
                ("카메라 모델", "camera", True),
                ("파일 종류 (RAW/JPG)", "kind", True),
                ("연도 (YYYY)", "year", False),
                ("월 (YYYY-MM)", "month", False),
                ("렌즈 모델", "lens", False),
             ]
             for label, key, checked in tokens:
                item = QListWidgetItem(label)
                item.setData(Qt.UserRole, key)
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                self.list_structure.addItem(item)
            
        opt_layout.addWidget(self.list_structure)
        
        # Preview Label
        self.lbl_preview = QLabel("예상 경로: ...")
        self.lbl_preview.setStyleSheet("color: #4CAF50; font-weight: bold; margin-top: 5px;")
        self.lbl_preview.setWordWrap(True)
        opt_layout.addWidget(self.lbl_preview)

        # Connect signals for live preview
        # Connect signals for live preview AND persistence
        self.list_structure.model().rowsMoved.connect(self._update_preview)
        self.list_structure.model().rowsMoved.connect(self._save_settings) # Auto-save on reorder
        
        self.list_structure.itemChanged.connect(self._update_preview)
        self.list_structure.itemChanged.connect(self._save_settings) # Auto-save on check/uncheck

        # Action
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("작업:"))
        self.bg_action = QButtonGroup(self)
        rb_copy = QRadioButton("복사 (Copy)")
        rb_move = QRadioButton("이동 (Move)")
        
        # Style for Green Indicator
        rb_style = """
            QRadioButton::indicator:checked {
                background-color: #4CAF50;
                border: 2px solid #4CAF50;
                border-radius: 6px;
                image: none;
            }
            QRadioButton::indicator:unchecked {
                background-color: transparent;
                border: 2px solid #888;
                border-radius: 6px;
            }
            QRadioButton::indicator {
                width: 12px;
                height: 12px;
            }
        """
        rb_copy.setStyleSheet(rb_style)
        rb_move.setStyleSheet(rb_style)

        rb_copy.setChecked(True)
        self.bg_action.addButton(rb_copy, 1)
        self.bg_action.addButton(rb_move, 2)
        row3.addWidget(rb_copy)
        row3.addWidget(rb_move)
        opt_layout.addLayout(row3)
        
        # Policy
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("중복 처리:"))
        self.combo_policy = QComboBox()
        self.combo_policy.addItem("이름 변경 (Rename)", "rename") 
        self.combo_policy.addItem("건너뛰기 (Skip)", "skip")
        row4.addWidget(self.combo_policy)
        opt_layout.addLayout(row4)
        
        opt_grp.setLayout(opt_layout)
        layout.addWidget(opt_grp)
        

        
        layout.addStretch()
        
        # Trigger initial update
        self._update_preview()

    def log(self, msg):
        if self.ext_log:
            self.ext_log.append(msg)
        else:
            print(f"[Organizer Log] {msg}")

    def browse_src(self):
        d = QFileDialog.getExistingDirectory(self, self._t("select_folder"))
        if d:
            self.lbl_src.setText(d)
            self.btn_start.setEnabled(False)

    def browse_dst(self):
        d = QFileDialog.getExistingDirectory(self, self._t("dest_folder"))
        if d:
            self.lbl_dst.setText(d)
            self.sorter_config["dest_root"] = d

    def _update_config(self):
        # Build structure list from checked items in order
        structure = []
        for i in range(self.list_structure.count()):
            item = self.list_structure.item(i)
            if item.checkState() == Qt.Checked:
                structure.append(item.data(Qt.UserRole))
        
        self.sorter_config["structure"] = structure
        self.sorter_config["action"] = "move" if self.bg_action.checkedId() == 2 else "copy"
        self.sorter_config["policy"] = self.combo_policy.currentData()

    def _update_preview(self, *args):
        # Generate dummy path based on current customized structure
        parts = []
        dest_root = self.lbl_dst.text()
        if not dest_root or dest_root == "선택된 폴더 없음":
            dest_root = "Target"
        else:
            dest_root = Path(dest_root).name
        
        parts.append(dest_root)

        for i in range(self.list_structure.count()):
            item = self.list_structure.item(i)
            if item.checkState() == Qt.Checked:
                key = item.data(Qt.UserRole)
                if key == "date": val = "2023-12-25"
                elif key == "year": val = "2023"
                elif key == "month": val = "2023-12"
                elif key == "camera": val = "OM-1"
                elif key == "lens": val = "M.Zuiko_12-40mm_Pro"
                elif key == "kind": val = "RAW"
                elif key == "ext": val = "ORF"
                else: val = "Unknown"
                parts.append(val)
        
        parts.append("P123456.ORF")
        preview_str = " / ".join(parts)
        self.lbl_preview.setText(f"예상 경로: {preview_str}")

    def start_scan(self):
        src = self.lbl_src.text()
        if not src or not Path(src).exists():
            QMessageBox.warning(self, "Error", self._t("error_invalid_folder") if "error_invalid_folder" in self.tr else "Invalid Folder")
            return
            
        self._update_config()
        self.log("Starting scan...")
        self.log("Starting scan...")
        # self.tabs.setCurrentIndex(2) # External log handling
        
        self.sorter = Sorter(self.sorter_config)
        self.thread = QThread()
        self.worker = Worker(self.sorter, mode='scan')
        self.worker.src_root = Path(src)
        self.worker.moveToThread(self.thread)
        self.worker_thread = self.thread # Keep ref
        
        self.thread.started.connect(self.worker.run_scan)
        self.worker.progress.connect(self.update_progress)
        self.worker.scan_result.connect(self.on_scan_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._on_thread_finished)
        
        self.thread.start()
        self.btn_scan.setEnabled(False)
    
    def _on_thread_finished(self):
        self.worker_thread = None

    def update_progress(self, status, current, total):
        if self.ext_progress:
            self.ext_progress.setFormat("%v / %m (%p%)")
            self.ext_progress.setMaximum(total)
            self.ext_progress.setValue(current)

    def on_scan_finished(self, files, metas):
        self.current_files = files
        self.current_metas = metas
        self.log(f"Scan complete. Found {len(files)} files.")
        
        self.current_plan = self.sorter.plan_sort(files, metas)
        self._populate_tree(self.current_plan)
        
        self.btn_scan.setEnabled(True)
        self.btn_start.setEnabled(True)
        # self.tabs.setCurrentIndex(1) # External preview handling

    def _populate_tree(self, plan):
        if not self.ext_tree: return
        self.ext_tree.clear()
        for folder, files in plan.items():
            item = QTreeWidgetItem(self.ext_tree)
            item.setText(0, str(folder))
            item.setText(1, f"{len(files)} files")
            
    def start_sort(self):
        if not self.current_plan:
            return
        
        ret = QMessageBox.question(self, "Confirm", f"Execute {self.sorter_config['action']}?")
        if ret != QMessageBox.Yes:
            return
            
        self.log("Starting sort...")
        # self.tabs.setCurrentIndex(2)
        
        self.thread = QThread()
        self.worker = Worker(self.sorter, mode='sort')
        self.worker.plan = self.current_plan
        self.worker.moveToThread(self.thread)
        self.worker_thread = self.thread
        
        self.thread.started.connect(self.worker.run_sort)
        self.worker.progress.connect(self.update_progress)
        self.worker.sort_result.connect(self.on_sort_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._on_thread_finished)
        
        self.thread.start()
        self.btn_start.setEnabled(False)

    def on_sort_finished(self, result):
        self.log("Sort complete.")
        self.log(str(result))
        QMessageBox.information(self, "Done", "Sorting complete!")
        self.btn_start.setEnabled(True)
