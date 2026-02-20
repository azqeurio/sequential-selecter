from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, 
    QPushButton, QListWidget, QListWidgetItem, QCheckBox
)
from PySide6.QtCore import Qt
from .styles import DARK_STYLE

class FilterDialog(QDialog):
    def __init__(self, parent, rating_manager):
        super().__init__(parent)
        self.setWindowTitle("Filter Images")
        self.resize(400, 500)
        self.rating_manager = rating_manager
        self.setStyleSheet(DARK_STYLE)
        
        self.filtered_files = [] # Result

        self._setup_ui()
        self._load_filter_options()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Rating Filter
        layout.addWidget(QLabel("Minimum Rating:"))
        self.combo_rating = QComboBox()
        self.combo_rating.addItems(["Any", "1 Star", "2 Stars", "3 Stars", "4 Stars", "5 Stars"])
        layout.addWidget(self.combo_rating)

        # Date Filter
        layout.addWidget(QLabel("Date:"))
        self.combo_date = QComboBox()
        self.combo_date.addItem("Any")
        layout.addWidget(self.combo_date)

        # Camera Filter
        layout.addWidget(QLabel("Camera:"))
        self.combo_camera = QComboBox()
        self.combo_camera.addItem("Any")
        layout.addWidget(self.combo_camera)

        # Apply Button
        btn_layout = QHBoxLayout()
        self.btn_apply = QPushButton("Apply Filter")
        self.btn_apply.clicked.connect(self.apply_filter)
        self.btn_apply.setStyleSheet("background-color: #4CAF50; color: white;")
        btn_layout.addWidget(self.btn_apply)
        
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.clicked.connect(self.reset_filters)
        self.btn_reset.setStyleSheet("background-color: #FF5555; color: white;")
        btn_layout.addWidget(self.btn_reset)

        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)

    def _load_filter_options(self):
        dates, cameras = self.rating_manager.get_unique_filters()
        self.combo_date.addItems(dates)
        self.combo_camera.addItems(cameras)

    def apply_filter(self):
        min_rating_idx = self.combo_rating.currentIndex() # 0=Any, 1=1 Star...
        target_date = self.combo_date.currentText()
        target_camera = self.combo_camera.currentText()
        
        # If all "Any" are selected, we should perhaps return None to indicate "Show All"
        # including unrated images.
        if min_rating_idx == 0 and target_date == "Any" and target_camera == "Any":
            self.filtered_files = None
            self.accept()
            return

        all_ratings = self.rating_manager.load_ratings()
        self.filtered_files = []
        
        for r in all_ratings:
            # Rating Check
            if min_rating_idx > 0:
                if r['rating'] < min_rating_idx:
                    continue
            
            # Date Check
            if target_date != "Any" and r['date'] != target_date:
                continue
                
            # Camera Check
            if target_camera != "Any" and r['camera'] != target_camera:
                continue
                
            self.filtered_files.append(r['filename'])
            
        self.accept()

    def reset_filters(self):
        # Reset all dropdowns and close dialog (None = "show all" in MainWindow)
        self.combo_rating.setCurrentIndex(0)
        self.combo_date.setCurrentIndex(0)
        self.combo_camera.setCurrentIndex(0)
        self.filtered_files = None
        self.accept()

    def get_filtered_files(self):
        return self.filtered_files
