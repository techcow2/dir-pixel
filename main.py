import sys
import os
import requests
import io
from PIL import Image
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QLabel, QLineEdit, QTextEdit, QTableWidget, QAbstractItemView,
    QTableWidgetItem, QFileDialog, QProgressBar, QMessageBox, QHeaderView, QSizePolicy
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QPixmap

class ImageGeneratorThread(QThread):
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    finished_all = pyqtSignal()
    error_occurred = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, source_folder, output_folder, prompts, image_extensions):
        super().__init__()
        self.source_folder = source_folder
        self.output_folder = output_folder
        self.prompts = prompts  # dict: filename -> prompt
        self.image_extensions = image_extensions
        self.files = self.get_image_files()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.cancelled.emit()

    def get_image_files(self):
        files = []
        for filename in os.listdir(self.source_folder):
            if any(filename.lower().endswith(ext) for ext in self.image_extensions):
                files.append(filename)
        return files

    def run(self):
        total = len(self.files)
        if total == 0:
            self.status_updated.emit("No image files found.")
            self.finished_all.emit()
            return

        for i, filename in enumerate(self.files):
            if self._cancelled:
                self.status_updated.emit("Generation cancelled.")
                self.cancelled.emit()
                return

            try:
                prompt = self.prompts.get(filename, self.prompts.get('global', ''))
                if filename not in self.prompts and prompt:
                    prompt += f" - unique variation for {filename}"
                if not prompt:
                    self.status_updated.emit(f"Skipping {filename}: No prompt provided.")
                    continue

                url = f"https://pollinations.ai/p/{prompt}?nologo=true"
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    name_without_ext = os.path.splitext(filename)[0]
                    original_ext = os.path.splitext(filename)[1].lower()
                    if original_ext in ['.jpg', '.jpeg']:
                        # Convert PNG to JPG
                        image = Image.open(io.BytesIO(response.content))
                        output_path = os.path.join(self.output_folder, f"{name_without_ext}.jpg")
                        image.convert('RGB').save(output_path, 'JPEG', quality=95)
                        self.status_updated.emit(f"Generated {name_without_ext}.jpg")
                    else:
                        # Save as PNG
                        output_path = os.path.join(self.output_folder, f"{name_without_ext}.png")
                        with open(output_path, 'wb') as f:
                            f.write(response.content)
                        self.status_updated.emit(f"Generated {name_without_ext}.png")
                else:
                    self.status_updated.emit(f"Failed to generate {filename}: HTTP {response.status_code}")
            except Exception as e:
                self.error_occurred.emit(f"Error generating {filename}: {str(e)}")

            self.progress_updated.emit(int((i + 1) / total * 100))

        if not self._cancelled:
            self.finished_all.emit()
        else:
            self.status_updated.emit("Generation cancelled.")
            self.cancelled.emit()

class ImageReplacerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DirPixel")
        self.resize(900, 900)
        self.setMinimumSize(800, 600)
        self.center()
        self.source_folder = ""
        # Support PNG and JPG files, convert generated PNG to matching format
        self.image_extensions = ['.png', '.jpg', '.jpeg']
        self.init_ui()
        self.apply_styles()

    def center(self):
        qr = self.frameGeometry()
        cp = QApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # App title header
        title_label = QLabel("DirPixel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("""
            color: #007bff;
            margin-bottom: 30px;
            font-family: 'Segoe UI';
            font-size: 28pt;
            font-weight: bold;
        """)
        main_layout.addWidget(title_label)

        # Folder Selection Group
        folder_group = QGroupBox("Folder Selection")
        folder_layout = QVBoxLayout(folder_group)
        folder_layout.setContentsMargins(15, 15, 15, 15)

        hbox = QHBoxLayout()
        self.folder_label = QLabel("No folder selected")
        self.folder_label.setWordWrap(True)
        self.select_folder_btn = QPushButton("Select Folder")
        self.select_folder_btn.clicked.connect(self.select_folder)
        hbox.addWidget(self.folder_label)
        hbox.addWidget(self.select_folder_btn)
        folder_layout.addLayout(hbox)
        main_layout.addWidget(folder_group)

        # Prompt Configuration Group
        prompt_group = QGroupBox("Prompt Configuration")
        prompt_layout = QVBoxLayout(prompt_group)
        prompt_layout.setContentsMargins(15, 15, 15, 15)
        prompt_layout.setSpacing(10)

        # Global prompt
        global_prompt_label = QLabel("Global Prompt (optional):")
        self.global_prompt_edit = QLineEdit()
        self.global_prompt_edit.setPlaceholderText("Enter a base prompt to use for all images (e.g., 'professional slide illustration')")
        prompt_layout.addWidget(global_prompt_label)
        prompt_layout.addWidget(self.global_prompt_edit)
        self.global_prompt_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Per-file prompts table
        table_label = QLabel("Custom Prompts per File:")
        table_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        prompt_layout.addWidget(table_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Preview", "Filename", "Custom Prompt"])
        self.table.setColumnWidth(0, 80)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(300)
        self.table.itemClicked.connect(self.on_item_clicked)
        prompt_layout.addWidget(self.table)
        main_layout.addWidget(prompt_group)

        # Generation Controls Group
        controls_group = QGroupBox("Generation")
        controls_layout = QVBoxLayout(controls_group)
        controls_layout.setContentsMargins(15, 15, 15, 15)

        self.generate_btn = QPushButton("Generate Images")
        self.generate_btn.clicked.connect(self.start_generation)
        self.generate_btn.setEnabled(False)
        self.generate_btn.setMinimumHeight(40)
        self.generate_btn.setMaximumWidth(200)
        controls_layout.addWidget(self.generate_btn)

        self.cancel_btn = QPushButton("Cancel Generation")
        self.cancel_btn.clicked.connect(self.cancel_generation)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.setMaximumWidth(200)
        self.cancel_btn.setStyleSheet("background-color: #dc3545; color: white;")
        controls_layout.addWidget(self.cancel_btn)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        controls_layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("Ready to generate images.")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        controls_layout.addWidget(self.status_label)
        main_layout.addWidget(controls_group)

        main_layout.addStretch()

        # Footer with developer info and close button
        footer_layout = QHBoxLayout()
        footer_label = QLabel("© 2025 Island Applications")
        footer_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        footer_label.setStyleSheet("color: #6c757d; font-size: 12px; padding: 10px;")
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #a71e2a;
            }
        """)
        footer_layout.addWidget(footer_label)
        footer_layout.addStretch()
        footer_layout.addWidget(close_btn)
        main_layout.addLayout(footer_layout)

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #dee2e6;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #212529;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                color: #fff;
            }
            QLineEdit {
                padding: 8px 12px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                font-size: 14px;
                background-color: white;
                color: black;
            }
            QLineEdit:focus {
                border-color: #80bdff;
            }
            QLabel {
                color: #212529;
                font-size: 13px;
            }
            QTableWidget {
                gridline-color: #dee2e6;
                background-color: white;
                alternate-background-color: #f8f9fa;
                selection-background-color: #007bff;
                border: 1px solid #dee2e6;
                border-radius: 4px;
            }
            QTableWidget::item {
                padding: 8px;
                font-size: 12px;
                color: #212529;
            }
            QTableWidget::item:selected {
                color: white;
            }
            QHeaderView::section {
                background-color: #e9ecef;
                padding: 8px;
                border: 1px solid #dee2e6;
                font-weight: 600;
                color: #212529;
                font-size: 13px;
            }
            QProgressBar {
                border: 1px solid #dee2e6;
                border-radius: 4px;
                text-align: center;
                background-color: #f8f9fa;
                color: #212529;
                font-size: 12px;
            }
            QProgressBar::chunk {
                background-color: #007bff;
                border-radius: 3px;
            }
            QMessageBox {
                background-color: white;
                color: black;
                font-size: 14px;
            }
            QMessageBox QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #0056b3;
            }
            QMessageBox QPushButton:pressed {
                background-color: #004085;
            }
        """)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.source_folder = folder
            self.folder_label.setText(folder)
            self.load_files()
            self.generate_btn.setEnabled(True)

    def load_files(self):
        files = []
        if os.path.exists(self.source_folder):
            for filename in os.listdir(self.source_folder):
                if any(filename.lower().endswith(ext) for ext in self.image_extensions):
                    files.append(filename)

        self.table.setRowCount(len(files))
        for i, filename in enumerate(files):
            # Preview
            preview_label = QLabel()
            preview_label.setFixedSize(50, 50)
            preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            full_path = os.path.join(self.source_folder, filename)
            if os.path.exists(full_path):
                pixmap = QPixmap(full_path).scaled(50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                preview_label.setPixmap(pixmap)
            self.table.setCellWidget(i, 0, preview_label)

            # Filename
            self.table.setItem(i, 1, QTableWidgetItem(filename))
            item1 = self.table.item(i, 1)
            item1.setFlags(item1.flags() & ~Qt.ItemFlag.ItemIsEditable)

            # Custom Prompt
            self.table.setItem(i, 2, QTableWidgetItem(""))
            self.table.setRowHeight(i, 50)

        self.status_label.setText(f"Loaded {len(files)} image files. Provide prompts and click Generate.")

    def start_generation(self):
        if not self.source_folder:
            QMessageBox.warning(self, "Error", "Please select a folder first.")
            return

        output_folder = os.path.join(self.source_folder, "generated_images")
        os.makedirs(output_folder, exist_ok=True)

        # Collect prompts
        prompts = {'global': self.global_prompt_edit.text().strip()}
        for row in range(self.table.rowCount()):
            filename_item = self.table.item(row, 1)
            prompt_item = self.table.item(row, 2)
            if filename_item and prompt_item:
                custom_prompt = prompt_item.text().strip()
                if custom_prompt:
                    prompts[filename_item.text()] = custom_prompt

        if not prompts['global'] and all(not prompt for prompt in prompts.values() if prompt != 'global'):
            QMessageBox.warning(self, "Error", "Please provide at least a global prompt or custom prompts.")
            return

        self.generate_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.cancel_btn.setVisible(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        self.thread = ImageGeneratorThread(self.source_folder, output_folder, prompts, self.image_extensions)
        self.thread.progress_updated.connect(self.progress_bar.setValue)
        self.thread.status_updated.connect(self.status_label.setText)
        self.thread.finished_all.connect(self.generation_finished)
        self.thread.error_occurred.connect(self.handle_error)
        self.thread.cancelled.connect(self.generation_cancelled)
        self.thread.start()

    def on_item_clicked(self, item):
        if item and item.column() == 2:
            self.table.editItem(item)

    def generation_finished(self):
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Generation completed!")
        output_folder = os.path.join(self.source_folder, "generated_images")
        QMessageBox.information(self, "Success", f"Images generated in {output_folder}")
        os.startfile(output_folder)
        if hasattr(self, 'thread'):
            del self.thread

    def generation_cancelled(self):
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Generation cancelled.")
        if hasattr(self, 'thread'):
            del self.thread

    def cancel_generation(self):
        if hasattr(self, 'thread') and self.thread.isRunning():
            self.thread.cancel()
            self.status_label.setText("Cancelling generation...")

    def handle_error(self, error_msg):
        self.generate_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.progress_bar.setVisible(False)
        self.status_label.setText("Error occurred")
        QMessageBox.critical(self, "Error", error_msg)
        if hasattr(self, 'thread'):
            del self.thread

    def closeEvent(self, event):
        if hasattr(self, 'thread') and isinstance(self.thread, QThread) and self.thread.isRunning():
            self.thread.cancel()
            self.thread.wait(3000)  # Wait up to 3 seconds
            if self.thread.isRunning():
                self.thread.terminate()
                self.thread.wait()
            if hasattr(self, 'thread'):
                del self.thread
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageReplacerApp()
    window.show()
    sys.exit(app.exec())
