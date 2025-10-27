# app2/UI/mixin_sorters.py
from PyQt5.QtWidgets import QHeaderView, QTableWidgetItem

class SortersMixin:
    @staticmethod
    def set_sorters_table_dimensions(self):
        header = self.TW_SORTERS.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.TW_SORTERS.setColumnWidth(0, 200)

    @staticmethod
    def set_sorters(self):
        # Define sorter boxes for CB_S1 and CB_SD1 only
        sorter_boxes = [
            (self.CB_S1, self.CB_SD1),
        ]

        # Retrieve active columns without order
        active_columns_with_no_order = self.set_active_columns_noorder()

        # Add items to the combo boxes
        for combo_box, _ in sorter_boxes:
            combo_box.clear()  # Clear existing items
            combo_box.addItems(active_columns_with_no_order)

        # Retrieve sorters data from active_sorters
        sorters = self.controller.active_sorters

        # Clear the table widget
        self.TW_SORTERS.setRowCount(0)

        if sorters:
            self.TW_SORTERS.setRowCount(len(sorters))  # Set the number of rows
            self.TW_SORTERS.setColumnCount(2)  # Set two columns: 'field' and 'direction'
            self.TW_SORTERS.setHorizontalHeaderLabels(['Field', 'Direction'])

            # Populate the table with sorter data
            for row, sorter in enumerate(sorters):
                field_item = QTableWidgetItem(sorter["dataIndex"])
                direction_item = QTableWidgetItem(sorter["sortDirection"])
                self.TW_SORTERS.setItem(row, 0, field_item)
                self.TW_SORTERS.setItem(row, 1, direction_item)

            # Update combo boxes with first sorter (if exists)
            if len(sorters) > 0:
                sorter = sorters[0]
                field_box, direction_box = sorter_boxes[0]
                field_box.setCurrentText(sorter["dataIndex"])
                direction_box.setCurrentText(sorter["sortDirection"])

    @staticmethod
    def add_new_sorter_to_tablewidget_on_save(self,field,direction,count):

        # Insert a new row at the end of the table
        self.TW_SORTERS.insertRow(count)

        # Create QTableWidgetItem instances for the new data
        sorter_item = QTableWidgetItem(field)
        direction_item = QTableWidgetItem(direction)

        # Set the items in the respective columns of the new row
        self.TW_SORTERS.setItem(count, 0, sorter_item)      # Column 0 for sorter
        self.TW_SORTERS.setItem(count, 1, direction_item)   # Column 1 for direction

    @staticmethod
    def save_sorter(self):
        # Retrieve the current text from the combo boxes
        sorter_to_save = self.CB_S1.currentText()
        direction_to_save = self.CB_SD1.currentText()
        # Determine the current number of rows in the table
        current_row_count = self.TW_SORTERS.rowCount()

        self.add_new_sorter_to_tablewidget_on_save(
            sorter_to_save,
            direction_to_save,
            current_row_count
            )

        sorter = {'sorter': {'direction':direction_to_save, 'field': sorter_to_save } }

        self.controller.active_sorters.append({
            "dataIndex": sorter_to_save,
            "sortDirection": direction_to_save,
            "sortOrder": current_row_count
        })

    @staticmethod
    def delete_selected_sorter(self):
        """Delete the selected sorter from active_sorters and update UI."""
        selected_row = self.TW_SORTERS.currentRow()
        if selected_row < 0:
            print("No sorter selected to delete.")
            return

        # Get field name and direction from selected row
        field_item = self.TW_SORTERS.item(selected_row, 0)
        direction_item = self.TW_SORTERS.item(selected_row, 1)
        if not field_item or not direction_item:
            print("Invalid sorter row selected.")
            return

        field = field_item.text()
        direction = direction_item.text()

        print(f"Deleting sorter: field={field}, direction={direction}")

        # Remove from active_sorters
        self.controller.active_sorters = [
            s for s in self.controller.active_sorters
            if not (s["dataIndex"] == field and s["sortDirection"] == direction)
        ]

        # Remove from table widget
        self.TW_SORTERS.removeRow(selected_row)

        print(f"Sorter '{field} ({direction})' deleted.")