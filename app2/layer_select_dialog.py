from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QListWidget, QAbstractItemView, QPushButton, QMessageBox
)
import sqlite3

class LayerSelectDialog(QDialog):
    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Layer")

        self.db_path = db_path
        self.selected_layer = None

        # Layouts
        main_layout = QVBoxLayout()
        button_layout = QHBoxLayout()

        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search layers...")
        self.search_box.textChanged.connect(self.filter_layers)
        main_layout.addWidget(self.search_box)

        # Layer list
        self.layer_list = QListWidget()
        main_layout.addWidget(self.layer_list)

        # Buttons
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

        # Connections
        self.ok_button.clicked.connect(self.accept_selection)
        self.cancel_button.clicked.connect(self.reject)

        # Load layers from DB
        self.load_layers()

    def load_layers(self):
        """Load layer names from the database into the list widget."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT Name FROM Layers ORDER BY Name ASC")
            rows = cursor.fetchall()
            conn.close()

            self.layer_list.clear()
            for row in rows:
                layer_name = row[0]
                self.layer_list.addItem(layer_name)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load layers:\n{str(e)}")

    def filter_layers(self, text):
        """Filter the layer list based on search box input."""
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            item.setHidden(text.lower() not in item.text().lower())

    def accept_selection(self):
        """Handle OK button -> return selected layer."""
        selected_item = self.layer_list.currentItem()
        if selected_item:
            self.selected_layer = selected_item.text()
            self.accept()
        else:
            QMessageBox.warning(self, "No Selection", "Please select a layer.")


class BulkLayerSelectDialog(QDialog):
    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Layers to Generate")
        self.setMinimumSize(400, 500)

        self.db_path = db_path
        self.selected_layers = []

        main_layout = QVBoxLayout()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search layers...")
        self.search_box.textChanged.connect(self.filter_layers)
        main_layout.addWidget(self.search_box)

        self.layer_list = QListWidget()
        self.layer_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        main_layout.addWidget(self.layer_list)

        select_layout = QHBoxLayout()
        self.select_all_button = QPushButton("Select All")
        self.deselect_all_button = QPushButton("Deselect All")
        self.select_all_button.clicked.connect(self.select_all)
        self.deselect_all_button.clicked.connect(self.deselect_all)
        select_layout.addWidget(self.select_all_button)
        select_layout.addWidget(self.deselect_all_button)
        main_layout.addLayout(select_layout)

        button_layout = QHBoxLayout()
        self.ok_button = QPushButton("Generate")
        self.cancel_button = QPushButton("Cancel")
        self.ok_button.clicked.connect(self.accept_selection)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)
        self.load_layers()

    def load_layers(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT Name FROM Layers ORDER BY Name ASC")
            rows = cursor.fetchall()
            conn.close()
            self.layer_list.clear()
            for row in rows:
                self.layer_list.addItem(row[0])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load layers:\n{str(e)}")

    def filter_layers(self, text):
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            item.setHidden(text.lower() not in item.text().lower())

    def select_all(self):
        for row in range(self.layer_list.count()):
            item = self.layer_list.item(row)
            if not item.isHidden():
                item.setSelected(True)

    def deselect_all(self):
        self.layer_list.clearSelection()

    def accept_selection(self):
        self.selected_layers = [
            self.layer_list.item(i).text()
            for i in range(self.layer_list.count())
            if self.layer_list.item(i).isSelected()
        ]
        if not self.selected_layers:
            QMessageBox.warning(self, "No Selection", "Please select at least one layer.")
            return
        self.accept()
