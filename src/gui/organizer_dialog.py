from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QObject
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
        
        # Default tokens (Translated)
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
        
        # Action
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("작업:"))
        self.bg_action = QButtonGroup(self)
        rb_copy = QRadioButton("복사 (Copy)")
        rb_move = QRadioButton("이동 (Move)")
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
