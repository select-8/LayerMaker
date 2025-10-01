from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt, QCoreApplication, QTimer
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QTableWidgetItem, QProgressDialog, QHeaderView, QColorDialog, QDialog
from grid_generator.grid_from_db import GridGenerator
from app2 import settings
from wfs_to_db import WFSToDB
from layer_select_dialog import LayerSelectDialog
import mappyfile
from view import Ui_MainWindow
#from colour_picker import ColourPickerApp
import logging
import pprint
import traceback
import sqlite3
from tabulate import tabulate


logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=4)


class MainWindowUIClass(QtWidgets.QMainWindow, Ui_MainWindow):
    def __init__(self, controller=None):
        super().__init__()
        self.controller = controller
        self.current_filepath = None
        self.setupUi(self)
        self.setup_column_ui()
        self.setup_buttons()
        #self.resize_some_ui_objects()
        self.setup_metadata_connections()
        self.connect_signals()
        self.set_sorters_table_dimensions()
        self.is_loading = False

        # populate CB_ColumnUnit from DB
        self.populate_unit_combo()
        # populate CB_EditorRole from DB
        self.populate_editor_roles()

    def setup_buttons(self):
        """Connect buttons to controller methods."""
        self.BTN_LAYERSELECT.clicked.connect(self.open_layer_selector)
        self.BTN_GENERATEGRID.clicked.connect(self.generate_grid)
        self.BTN_COLUMNSAVE.clicked.connect(self.save_column_data)
        self.BTN_ADDLISTROWS.clicked.connect(self.set_table_rows)
        self.BTN_SAVETODB.clicked.connect(self.save_current_layer_to_db)
        self.BTN_GETMAPFILE.clicked.connect(self.openmapfile_filehandler)
        self.BTN_ADDTODB.clicked.connect(self.add_new_columns)
        self.BTN_GENDB.clicked.connect(self.add_new_layer_to_db)
        self.BTN_SAVESORTER.clicked.connect(self.save_sorter)
        self.BTN_DELETESORTER.clicked.connect(self.delete_selected_sorter)
        self.BTN_SAVELISTFILTER.clicked.connect(self.save_new_filter)
        self.BTN_DELETELISTFILTER.clicked.connect(self.delete_selected_filter)
        self.BTN_UPDATELISTFILTER.clicked.connect(self.update_selected_filter)
        self.BTN_COLOURPICKER.clicked.connect(self.openColorDialog)

    def resize_some_ui_objects(self):
        # Called in populate_ui() after populating
        #self.resize(1400, 900)
        self.SPLIT_LEFT.setSizes([750, 200, 50])
        self.SPLIT_COLUMNS.setSizes([300, 600])
        # self.SPLIT_COLUMNS.setStretchFactor(0, 3)   # left
        # self.SPLIT_COLUMNS.setStretchFactor(1, 7)   # right
        self.BTN_COLUMNSAVE.setMaximumHeight(40)

        self.CB_ColumnUnit.setPlaceholderText("Select unit...")

        hdr = self.TW_SORTERS.horizontalHeader()
        # # Fixed width for a column
        # hdr.resizeSection(0, 100)     # column 0 -> 150 px
        # hdr.resizeSection(1, 100)     # column 1 -> 300 px
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

    def openColorDialog(self):
        # Open the colour dialog directly
        colour = QColorDialog.getColor()

        if colour.isValid():
            # Extract colour name (HEX)
            colour_name = colour.name()  # e.g., "#FF5733"
            
            # Extract RGB values
            rgb_values = (colour.red(), colour.green(), colour.blue())  # (255, 87, 51)

            # For debugging or other purposes, print the extracted values
            print(f"Colour Name (HEX): {colour_name}")
            print(f"RGB Values: {rgb_values}")

    def connect_signals(self):
        """Connect signals to slots with proper signal management"""
        # Disconnect all first to prevent duplicate connections
        try:
            self.controller.data_updated.disconnect()
            self.controller.filter_selected.disconnect()
            self.LW_CurrentListFilters.itemSelectionChanged.disconnect()
            self.LW_filters.itemSelectionChanged.disconnect()
        except TypeError:
            pass  # No connections exist yet

        # Reconnect signals with proper order
        self.controller.data_updated.connect(
            self.handle_data_updated
        )  # Central handler
        self.controller.filter_selected.connect(self.populate_filter_widgets)

        self.LW_CurrentListFilters.itemSelectionChanged.connect(
            self.handle_filter_selection
        )

        # Column signals (connected after initial data load)
        if hasattr(self.controller, "columns_with_data"):
            self.LW_filters.itemSelectionChanged.connect(
                self.update_column_properties_ui
            )

    def setup_metadata_connections(self):
        """Connect all metadata fields with proper change tracking"""
        # Text fields
        text_fields = {
            'window': self.LE_Window,
            'model': self.LE_Model,
            'help_page': self.LE_Help,
            'controller': self.LE_Controller
        }
    
        for field, widget in text_fields.items():
            widget.textChanged.connect(self._create_metadata_updater(field, str))
    
        # Combo boxes
        self.CB_service.currentTextChanged.connect(
            self._create_metadata_updater('service', str))
    
        # Checkboxes
        checkboxes = {
            'isSpatial': self.CBX_IsSpatial,
            'excel_exporter': self.CBX_Excel,
            'shp_exporter': self.CBX_Shapefile,
            'isSwitch': self.CBX_IsSwitch,
            #'editable': self.CBX_Editable
        }
    
        for field, widget in checkboxes.items():
            widget.stateChanged.connect(
                self._create_metadata_updater(field, bool))
    
        # Special cases
        self.CB_ID.currentTextChanged.connect(
            self._create_metadata_updater('id', str))
        self.CB_GETID.currentTextChanged.connect(
            self._create_metadata_updater('getid', str))

    def _create_metadata_updater(self, field_name, type_converter):
        def updater(value):
            if self.is_loading:
                return  # Prevent overwriting mdata during load
            if hasattr(self.controller, 'active_mdata'):
                try:
                    if isinstance(value, str) and not value.strip():
                        self.controller.active_mdata[field_name] = None
                    else:
                        self.controller.active_mdata[field_name] = type_converter(value)
                except (ValueError, TypeError):
                    self.controller.active_mdata[field_name] = None
        return updater

    def set_sorters_table_dimensions(self):
        header = self.TW_SORTERS.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.TW_SORTERS.setColumnWidth(0, 200)

    def handle_data_updated(self, data):
        """Central handler for data updates"""
        #print("handle_data_updated called with data:")  # Debugging
        #pp.pprint(data)

        if data.get("status") == "loaded":
            # Full UI load (after YAML file opened)
            self.refresh_ui(data)  # This will include column + filter population
            return

        # For filter updates/adds/deletes, avoid overwriting unsaved mdata
        if self.is_loading:
            print("Skipping UI metadata update during protected load")
            return

        if "active_filters" in data:
            self.populate_filter_list(data)

    def openmapfile_filehandler(self):
        print("MapDir: ", self.controller.mapfiles_dir)
        fname = QFileDialog.getOpenFileName(
            self,
            "Open file",
            self.controller.mapfiles_dir,
            "map Files (*.map)",
        )
        print("mapfile fname", fname)
        if fname and fname[0] != "":
            self.get_layer_list_from_mapfile_and_populate_listwidget(fname[0])

    def get_layer_list_from_mapfile_and_populate_listwidget(self, mapfile_path):
        mapfile = mappyfile.open(mapfile_path)
        layers = mapfile["layers"]
        layer_names = [layer["name"] for layer in layers]
        self.CB_MAPLAYERS.clear()
        self.CB_MAPLAYERS.addItems(layer_names)

    # def populate_unit_combo(self):
    #     """Populate CB_ColumnUnit dynamically from GridColumnRenderers table."""
    #     with sqlite3.connect(self.controller.db_path) as conn:
    #         conn.row_factory = sqlite3.Row
    #         cursor = conn.cursor()
    #         cursor.execute("SELECT DisplayName FROM GridColumnRenderers ORDER BY DisplayName;")
    #         rows = cursor.fetchall()

    #     self.CB_ColumnUnit.clear()
    #     for row in rows:
    #         self.CB_ColumnUnit.addItem(row["DisplayName"])

    def populate_unit_combo(self):
        """Populate CB_ColumnUnit with DisplayName, store (id, renderer, exType) as itemData."""
        with sqlite3.connect(self.controller.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT GridColumnRendererId, Renderer, ExType, DisplayName
                FROM GridColumnRenderers
                ORDER BY DisplayName
            """)
            rows = cur.fetchall()

        self.CB_ColumnUnit.clear()
        for r in rows:
            payload = (r["GridColumnRendererId"], r["Renderer"], r["ExType"])
            self.CB_ColumnUnit.addItem(r["DisplayName"], payload)


    def populate_ui(self):
        # Update the UI from active data
        self.set_layer_label()

        # Ensure active_columns is a list (fallback to empty list if None)
        active_columns = self.controller.active_columns or []

        print(tabulate(sorted(self.controller.active_mdata.items()),
                       headers=["Key", "Value"],
                       tablefmt="grid",
                       colalign=("left", "center")))

        self.set_combo_box(
            self.CB_ID,
            active_columns,  # Now guaranteed to be a list
            self.controller.active_mdata.get("IdField", ""),
        )

        self.populate_combo_boxes()
        self.populate_line_edits()
        self.populate_checkboxes()
        self.resize_some_ui_objects()

    def set_layer_label(self):
        self.ActiveLayer_label_2.setText(self.controller.active_layer)

    def set_active_columns_noorder(self):
        self.active_columns_without_order = (
            self.controller.active_columns or []
        )  # Fallback to empty list
        self.active_columns_without_order.insert(0, None)  # blank item first
        return self.active_columns_without_order

    def populate_combo_boxes(self):
        # """Debug combo box population"""
        # print("\n=== DEBUG populate_combo_boxes() ===")
        # print(f"active_columns: {self.controller.active_columns}")
        # print(f"active_mdata id: {self.controller.active_mdata.get('id')}")
        # print(f"active_mdata getid: {self.controller.active_mdata.get('getid')}")

        """Populate combo boxes with active columns."""
        # Get active columns with None handling
        active_columns = self.controller.active_columns or []
        active_columns_with_no_order = [
            ""
        ] + active_columns  # Use empty string instead of None

        # Populate combo boxes
        self.set_combo_box(
            self.CB_ID,
            active_columns_with_no_order,
            self.controller.active_mdata.get("id", ""),
        )
        self.set_combo_box(
            self.CB_GETID,
            active_columns_with_no_order,
            self.controller.active_mdata.get("getid", ""),
        )

        # Populate CB_service safely
        service_value = self.controller.active_mdata.get("Service", "")
        # print("Service value:", service_value)  # Debugging)
        self.CB_service.setCurrentText(str(service_value) if service_value else "")

        self.LE_IDPROPERTY.clear()
        self.LE_DATAPROPERTY.clear()
        self.LE_EDITURL.clear()
        # Handle edit fields if available
        for col_name, col_data in self.controller.columns_with_data.items():
            if "edit" in col_data and col_data["edit"] is not None:
                #print(col_data)
                # self.CB_EditColumn.setCurrentText(col_name)
                self.LE_DATAPROPERTY.setText(
                    col_data["edit"].get("groupEditIdProperty", "")
                )
                self.LE_IDPROPERTY.setText(
                    col_data["edit"].get("groupEditDataProp", "")
                )
                self.LE_EDITURL.setText(col_data["edit"].get("editServiceUrl", ""))
                break

        # Populate CB_SelectLocalField and CB_SelectDataIndex
        self.set_combo_box(self.CB_SelectLocalField, active_columns_with_no_order, "")
        self.set_combo_box(self.CB_SelectDataIndex, active_columns_with_no_order, "")

        # Set sorters
        self.set_sorters()

    def populate_line_edits(self):
        
        """Load metadata into UI with proper null handling"""
        if not hasattr(self.controller, "active_mdata"):
            return

        mdata = self.controller.active_mdata

        #print("Setting LE_Window to:", mdata.get("Window"))

        # Block signals during initial population
        self.LE_Window.blockSignals(True)
        self.LE_Model.blockSignals(True)
        self.LE_Help.blockSignals(True)
        self.LE_Controller.blockSignals(True)

        try:
            self.LE_Window.setText(mdata.get("Window") or "")
            self.LE_Model.setText(mdata.get("Model") or "")
            self.LE_Help.setText(mdata.get("HelpPage") or "")
            self.LE_Controller.setText(mdata.get("Controller") or "")
        finally:
            # Restore signal handling
            self.LE_Window.blockSignals(False)
            self.LE_Model.blockSignals(False)
            self.LE_Help.blockSignals(False)
            self.LE_Controller.blockSignals(False)

    def populate_checkboxes(self):
        #pp.pprint(self.controller.active_mdata)
        self.set_checkbox(self.CBX_IsSwitch, self.controller.active_mdata["IsSwitch"])
        self.set_checkbox(
            self.CBX_Excel, self.controller.active_mdata["ExcelExporter"]
        )
        self.set_checkbox(self.CBX_IsSpatial, self.controller.active_mdata["IsSpatial"])
        self.set_checkbox(
            self.CBX_Shapefile, self.controller.active_mdata["ShpExporter"]
        )

    def set_checkbox(self, checkbox, condition):
        checkbox.setChecked(True if condition else False)

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

    def add_new_sorter_to_tablewidget_on_save(self,field,direction,count):

        # Insert a new row at the end of the table
        self.TW_SORTERS.insertRow(count)

        # Create QTableWidgetItem instances for the new data
        sorter_item = QTableWidgetItem(field)
        direction_item = QTableWidgetItem(direction)

        # Set the items in the respective columns of the new row
        self.TW_SORTERS.setItem(count, 0, sorter_item)      # Column 0 for sorter
        self.TW_SORTERS.setItem(count, 1, direction_item)   # Column 1 for direction

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

    def populate_filter_list(self, data):
        """Populate the QListWidget with active filters."""
        self.LW_CurrentListFilters.clear()

        active_filters = data.get(
            "active_filters"
        )  # Safely get the key, defaulting to None

        if active_filters:  # Ensure active_filters is not None or empty
            for filter_data in active_filters:
                #print('filter_data')
                #pp.pprint(filter_data)
                self.LW_CurrentListFilters.addItem(filter_data["localField"])
        else:
            print("Warning: 'active_filters' is missing or None")

    def handle_filter_selection(self):
        """Handle selection of a filter in the QListWidget."""
        selected_item = self.LW_CurrentListFilters.currentItem()
        print('selected item: ', selected_item)
        if selected_item:
            filter_name = selected_item.text()
            print(f"Selected filter: {filter_name}")  # Debugging
            self.controller.select_filter(filter_name)  # Delegate to the Controller

    def populate_filter_widgets(self, filter_data):
        print("populate_filter_widgets called")  # Debugging
        """Populate widgets with data from the selected filter."""
        #pp.pprint(filter_data)
        #filter_info = filter_data["filter"]
        #print('populate_filter_widgets', filter_info)
        self.CB_SelectLocalField.setCurrentText(filter_data["localField"])
        self.CB_SelectDataIndex.setCurrentText(filter_data["dataIndex"])
        self.LE_InputIDField.setText(filter_data["idField"])
        self.LE_InputLabelField.setText(filter_data["labelField"])
        self.LE_InputStore.setText(filter_data["store"])
        self.LE_InputStoreID.setText(filter_data["storeId"])

    def save_new_filter(self):
        new_filter = {
            "dataIndex": self.CB_SelectDataIndex.currentText(),
            "idField": self.LE_InputIDField.text(),
            "labelField": self.LE_InputLabelField.text(),
            "localField": self.CB_SelectLocalField.currentText(),
            "store": self.LE_InputStore.text(),
            "storeId": self.LE_InputStoreID.text(),
        }
        self.controller.add_filter(new_filter)

    def delete_selected_filter(self):
        """Delete the selected filter from active_filters and update UI."""
        selected_item = self.LW_CurrentListFilters.currentItem()
        if not selected_item:
            print("No filter selected to delete.")
            return

        name = selected_item.text()
        print(f"Deleting filter: {name}")

        # Remove from active_filters
        self.controller.active_filters = [
            f for f in self.controller.active_filters
            if f["localField"] != name
        ]

        # Remove from ListWidget
        row = self.LW_CurrentListFilters.currentRow()
        self.LW_CurrentListFilters.takeItem(row)

        print(f"Filter '{name}' deleted.")

    def update_selected_filter(self):
        """Update the currently selected filter in the active_filters list and update UI."""
        selected_item = self.LW_CurrentListFilters.currentItem()
        if not selected_item:
            print("No filter selected to update.")
            return

        original_field = selected_item.text()
        print(f"Updating filter: {original_field}")

        # Build updated filter dict with new model (flat structure)
        updated_filter = {
            "dataIndex": self.CB_SelectDataIndex.currentText(),
            "idField": self.LE_InputIDField.text(),
            "labelField": self.LE_InputLabelField.text(),
            "localField": self.CB_SelectLocalField.currentText(),
            "store": self.LE_InputStore.text(),
            "storeId": self.LE_InputStoreID.text(),
        }

        # Update in controller.active_filters
        updated = False
        for i, f in enumerate(self.controller.active_filters):
            if f["localField"] == original_field:
                print(f"Found matching filter in active_filters, updating index {i}")
                self.controller.active_filters[i] = updated_filter
                updated = True
                break

        if not updated:
            print("Warning: selected filter not found in active_filters!")

        # Update the list widget item text so future selection works correctly
        selected_row = self.LW_CurrentListFilters.currentRow()
        self.LW_CurrentListFilters.item(selected_row).setText(updated_filter["localField"])

        print("Filter updated successfully.")

    def setup_column_ui(self):
        """Initialize column list with proper state handling"""
        # Clear existing
        self.LW_filters.clear()
        self.LW_SavedColumns.clear()

        # Block signals during setup
        self.LW_filters.blockSignals(True)

        try:
            # Safely get column names
            column_names = []
            if hasattr(self.controller, "columns_with_data"):
                column_names = (
                    self.controller.get_column_names()
                )  # Now returns list directly
            #print("CN", column_names)

            self.LW_filters.addItems(column_names)

            # Set default state
            if column_names:
                self.LW_filters.setCurrentRow(0)
                self.update_column_properties_ui()
            else:
                self.clear_column_ui()

        except Exception as e:
            print(f"Column UI setup error: {e}")
            self.clear_column_ui()
        finally:
            self.LW_filters.blockSignals(False)

    def populate_editor_roles(self):
        db_path = self.controller.db_path
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT RoleName FROM EditorRoles ORDER BY RoleName;")
            rows = cursor.fetchall()

        # Debugging output
        # print("populate_editor_roles -> found roles:", [r["RoleName"] for r in rows])
        # print("CB_EditorRole before add:", self.CB_EditorRole.count())

        self.CB_EditorRole.clear()
        self.CB_EditorRole.addItem("")  # blank
        for row in rows:
            self.CB_EditorRole.addItem(row["RoleName"])

        # print("CB_EditorRole after add:", self.CB_EditorRole.count())

    def update_column_properties_ui(self):
        """Safely update column properties with full error handling and partial population support."""
        current_file_layer = self.ActiveLayer_label_2.text()
        if not current_file_layer or current_file_layer != self.controller.active_layer:
            return  # Abort if file changed during processing

        try:
            selected = self.LW_filters.currentItem()
            if not selected:
                self.clear_column_ui()
                return

            column_name = selected.text()
            column_data = self.controller.get_column_data(column_name)
            # print(f'update_column_properties_ui(), column_data for {column_name}')
            # pp.pprint(column_data)

            # If no data found for column, clear UI
            if column_data is None:
                print(f"No column data found for '{column_name}', clearing inputs")
                self.clear_column_ui()
                return

            #print(f"Populating column: {column_name} with data: {column_data}")

            # Populate available fields safely
            #self.LB_ColumnIndex.setText(column_name)
            self.LE_ColumnDisplayText.setText(column_data.get("text") or "")
            self.DSB_ColumnFlex.setValue(float(column_data.get("flex") or 0.0))
            self.LE_NullText.setText(column_data.get("nulltext") or "")

            # Lookup DisplayName from GridColumnRenderers
            # renderer = column_data.get("renderer") or ""
            # ex_type = column_data.get("exType") or ""
            # if renderer and ex_type:
            #     try:
            #         with sqlite3.connect(self.controller.db_path) as conn:
            #             conn.row_factory = sqlite3.Row
            #             cursor = conn.cursor()
            #             cursor.execute("""
            #                 SELECT DisplayName
            #                 FROM GridColumnRenderers
            #                 WHERE LOWER(Renderer) = ? AND LOWER(ExType) = ?
            #             """, (renderer.lower().strip(), ex_type.lower().strip()))
            #             result = cursor.fetchone()
            #             if result:
            #                 self.CB_ColumnUnit.setCurrentText(result["DisplayName"])
            #             else:
            #                 self.CB_ColumnUnit.setCurrentIndex(0)
            #     except sqlite3.Error as db_err:
            #         print(f"Database error while fetching DisplayName: {db_err}")
            #         self.CB_ColumnUnit.setCurrentIndex(0)
            # else:
            #     self.CB_ColumnUnit.setCurrentIndex(0)

            renderer_id = column_data.get("GridColumnRendererId")
            if renderer_id:
                ix = -1
                for i in range(self.CB_ColumnUnit.count()):
                    rid, _r, _x = self.CB_ColumnUnit.itemData(i)
                    if rid == renderer_id:
                        ix = i; break
                self.CB_ColumnUnit.setCurrentIndex(ix if ix >= 0 else 0)
            else:
                self.CB_ColumnUnit.setCurrentIndex(0)

            # Update checkboxes safely
            self.CBX_ColumnInGrid.setChecked(bool(column_data.get("inGrid", False)))
            self.CBX_ColumnHidden.setChecked(bool(column_data.get("hidden", False)))
            self.CBX_NoFilter.setChecked(bool(column_data.get("noFilter", False)))

            # Handle special cases safely
            self.handle_special_column_cases(column_data)

        except Exception as e:
            print(f"Column update failed: {e}")
            self.clear_column_ui()

    def handle_special_column_cases(self, column_data):
        """Handle zeros, customList, and edit metadata safely."""

        # Handle zeros
        if (column_data.get("renderer") in ("double", "meters")):
            zeros_val = column_data.get("zeros")
            if isinstance(zeros_val, str):
                zeros_val = self.convert_str_zeros_to_int_for_form_populate(zeros_val)
            self.DSB_Zeros.setValue(zeros_val if zeros_val is not None else 2)
        else:
            self.DSB_Zeros.clear()

        # Handle customList
        custom_list = column_data.get("customList")
        if isinstance(custom_list, list):
            self.TW_CustomList.setRowCount(len(custom_list))
            self.SB_CustomList.setValue(len(custom_list))
            for row, item in enumerate(custom_list):
                self.TW_CustomList.setItem(row, 0, QTableWidgetItem(str(item)))
        else:
            self.TW_CustomList.setRowCount(0)
            self.SB_CustomList.setValue(0)

        # Handle edit data
        edit_data = column_data.get("edit")
        if isinstance(edit_data, dict):
            self.set_checkbox(self.CBX_Editable, edit_data.get("editable", False))
            self.LE_IDPROPERTY.setText(edit_data.get("groupEditDataProp") or "")
            self.LE_DATAPROPERTY.setText(edit_data.get("groupEditIdProperty") or "")
            self.LE_EDITURL.setText(edit_data.get("editServiceUrl") or "")

            role_name = edit_data.get("editUserRole") or ""
            index = self.CB_EditorRole.findText(role_name, Qt.MatchFixedString)
            self.CB_EditorRole.setCurrentIndex(index if index >= 0 else 0)
        else:
            # Reset edit fields if no edit data
            self.LE_IDPROPERTY.clear()
            self.LE_DATAPROPERTY.clear()
            self.LE_EDITURL.clear()
            self.CB_EditorRole.setCurrentIndex(0)
            self.CBX_Editable.setChecked(False)

    def add_new_columns(self):
        """
        Check if new columns have been added to a View
        and update the yaml accordingly.
        """
        # 1. Show the progress dialog
        progress = QProgressDialog(
            "Checking WFS...", None, 0, 0, self  # No cancel button
        )
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setRange(0, 100)
        progress.show()

        # 2. Perform WFS call with slight delay to allow UI update
        QtCore.QTimer.singleShot(
            100,
            lambda: self._execute_generation_of_add_new_columns(
                self.controller, settings.WFS_URL, progress
            ),
        )

    def _execute_generation_of_add_new_columns(self, controller, url, progress):
        try:
            importer = WFSToDB(
                controller.db_path,
                url,
                timeout=settings.WFS_READ_TIMEOUT,
                connect_timeout=settings.WFS_CONNECT_TIMEOUT,
                retries=settings.WFS_RETRY_ATTEMPTS,
                backoff_factor=settings.WFS_RETRY_BACKOFF,
            )
            added = importer.sync_new_columns(controller.active_layer)

            if not added:
                QMessageBox.information(self, "No changes", "No new columns found.")
                progress.close()
                return

            # Reload layer from DB so UI reflects the newly inserted columns
            controller.read_db(controller.active_layer)
            self.populate_ui()

            # Tell the user what was added
            QMessageBox.information(self, "Columns added", ", ".join(sorted(added)))
        except Exception as e:
            QMessageBox.critical(self, "WFS sync failed", str(e))
        finally:
            progress.setValue(100)
            progress.close()

    def remove_selected_custom_list_item(self):
        """Remove the selected item from TW_CustomList and update SB_CustomList."""
        selected_row = self.TW_CustomList.currentRow()
        if selected_row < 0:
            print("No CustomList item selected to delete.")
            return

        # Remove row from table
        self.TW_CustomList.removeRow(selected_row)

        # Update SB_CustomList value
        current_count = self.SB_CustomList.value()
        new_count = max(current_count - 1, 0)
        self.SB_CustomList.setValue(new_count)

        # If count is now 0 -> fully clear table
        if new_count == 0:
            self.TW_CustomList.setRowCount(0)

        print(f"CustomList item at row {selected_row} deleted.")

    def save_column_data(self):
        """Simplified save handler using collect_column_data_from_ui()"""
        try:
            # 1. Validate selection
            if not self.LW_filters.currentItem():
                QMessageBox.warning(
                    self, "No Selection", "Please select a column first"
                )
                return

            # 2. Collect data (includes null/empty handling)
            column_name = self.LW_filters.currentItem().text()
            column_data = self.collect_column_data_from_ui()
            # print('save_column_data')
            # pp.pprint(column_data)
            if not column_data:
                raise ValueError("Invalid column data")

            if not self.validate_column_data(column_data):
                return

            # 3. Save via controller
            if self.controller.update_column_data(column_name, column_data):
                self.update_saved_columns_list()  # Refresh UI if needed
            else:
                QMessageBox.warning(self, "Error", "Failed to save column data")

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Save failed: {str(e)}")
            print(f"Save error: {traceback.format_exc()}")

    def get_ordered_listwidget_items(self):
        """Extracts items from QListWidget in order of their index."""
        return [self.LW_filters.item(i).text() for i in range(self.LW_filters.count())]

    def generate_grid(self):
        """Save form data before generating a grid"""
        try:
            self.save_current_layer_to_db()
        except Exception as e:
            print(f"Warning: failed to save current layer before generating grid: {e}")

            """Generate grid for the currently selected layer."""
        try:
            layer_name = self.controller.active_layer
            db_path = self.controller.db_path

            if not layer_name or not db_path:
                QMessageBox.warning(self, "Missing Info", "No layer or database selected.")
                return

            py_root = self.controller.project_directory
            js_root = self.controller.js_root_folder

            gridgen = GridGenerator(py_root, js_root)
            gridgen.generate_grid(layer_name, db_path)

            QMessageBox.information(self, "Success", f"Grid generated for {layer_name}")

        except Exception as e:
            print("generate_grid error:")
            print(traceback.format_exc())
            QMessageBox.critical(self, "Grid Error", str(e))

    def validate_column_data(self, data):
        """Example validation"""
        if not data.get("renderer"):
            QMessageBox.warning(self, "Validation", "Renderer type is required")
            return False
        if data.get("flex", 0) < 0:
            QMessageBox.warning(self, "Validation", "Flex cannot be negative")
            return False
        return True

    def collect_column_data_from_ui(self):
        """
        Collects data from the column editing UI for the currently selected column.

        Builds a dictionary representing the column's configuration, including:
        - Display text, flex size, renderer/extype mapping
        - Grid visibility options
        - Null value settings
        - Custom list entries (if any)
        - Edit settings (editable flag, edit ID property, data prop, URL, user role)

        Returns:
            dict: A dictionary representing the column data to save, or None on failure.
        """
        try:
            current_item = self.LW_filters.currentItem()
            if not current_item:
                return None

            column_name = current_item.text()
            original_data = self.controller.get_column_data(column_name) or {}

            # renderer, extype = self.controller.get_unit_mappings_out(
            #     self.CB_ColumnUnit.currentText()
            # )

            is_edit = self.CBX_Editable.checkState() == 2
            idx = self.CB_ColumnUnit.currentIndex()
            payload = self.CB_ColumnUnit.itemData(idx) or (None, None, None)
            renderer_id, renderer, extype = payload

            new_data = {
                "flex": float(self.DSB_ColumnFlex.value()),
                "text": self.LE_ColumnDisplayText.text().strip() or None,
                "renderer": (renderer or "").strip(),
                "exType": (extype or "").strip(),
                "GridColumnRendererId": renderer_id,
                "inGrid": self.CBX_ColumnInGrid.isChecked(),
                "hidden": self.CBX_ColumnHidden.isChecked(),
                "index": column_name,
                "nulltext": self.LE_NullText.text().strip() or '',
                "nullvalue": int(self.DSB_NullVal.value()) if self.DSB_NullVal.value() != 0 else None,
                "zeros": int(self.DSB_Zeros.value()) if self.DSB_Zeros.isEnabled() and self.DSB_Zeros.value() > 0 else None,
                "noFilter": self.CBX_NoFilter.isChecked(),
            }

            
            custom_list = self.get_custom_list_values()
            if custom_list:
                new_data["customList"] = custom_list
            else:
                self.TW_CustomList.clear()
                self.SB_CustomList.setValue(0)

            dataprop = self.LE_IDPROPERTY.text() or None
            endpoint = self.LE_DATAPROPERTY.text() or None
            edit_service_url = self.LE_EDITURL.text() or None
            edit_role = self.CB_EditorRole.currentText() or None

            new_data["edit"] = {
                "editable": is_edit,
                "groupEditIdProperty": endpoint,
                "groupEditDataProp": dataprop,
                "editServiceUrl": edit_service_url,
                "editUserRole": edit_role,
            }

            # print('NEW DATA')
            # print(new_data)

            return {k: v for k, v in new_data.items() if v is not None}

        except Exception as e:
            print(f"Error collecting column data: {e}")
            return None

    def set_combo_box(self, combo_box, items, current_value):
        """Safely populate a combo box with validation"""
        combo_box.clear()

        # Ensure items is always a list and convert all items to strings
        safe_items = []
        if items is not None:
            safe_items = [str(item) if item is not None else "" for item in items]

        combo_box.addItems(safe_items)

        # Handle current value safely
        if current_value is not None:
            current_text = str(current_value)
            if current_text in safe_items:
                combo_box.setCurrentText(current_text)
            else:
                combo_box.setCurrentIndex(0)  # Default to first item
        else:
            combo_box.setCurrentIndex(0)  # Default to first item

    def clear_all_ui(self):
        """Reset all UI elements"""
        # Clear metadata fields
        self.LE_Window.clear()
        self.LE_Model.clear()
        self.LE_Help.clear()
        self.LE_Controller.clear()

        self.CB_S1.clear()

        # Reset checkboxes
        self.CBX_Editable.setChecked(False)
        self.CBX_IsSwitch.setChecked(False)
        self.CBX_Excel.setChecked(False)
        self.CBX_IsSpatial.setChecked(False)
        self.CBX_Shapefile.setChecked(False)

        # Clear column UI
        self.clear_column_ui()

        # Clear filters
        self.LW_CurrentListFilters.clear()
        self.LE_InputIDField.clear()
        self.LE_InputLabelField.clear()
        self.LE_InputStore.clear()
        self.LE_InputStoreID.clear()

        self.CB_SelectLocalField.setCurrentIndex(0)
        self.CB_SelectDataIndex.setCurrentIndex(0)

        self.LW_filters.clear()
        self.LW_SavedColumns.clear()
        self.LE_ColumnDisplayText.clear()

        self.CB_MAPLAYERS.clear()

    def clear_column_ui(self):
        """Reset column-specific fields"""
        #self.LB_ColumnIndex.clear()
        self.LE_ColumnDisplayText.clear()
        self.DSB_ColumnFlex.setValue(0.0)
        self.CB_ColumnUnit.setCurrentIndex(0)
        self.LE_NullText.clear()
        self.DSB_Zeros.clear()
        self.TW_CustomList.setRowCount(0)
        self.SB_CustomList.setValue(0)
        self.CBX_ColumnInGrid.setChecked(False)
        self.CBX_ColumnHidden.setChecked(False)
        self.CBX_NoFilter.setChecked(False)
        self.LW_SavedColumns.clear()
        # self.CB_EditColumn.clear()
        self.LE_IDPROPERTY.clear()
        self.LE_DATAPROPERTY.clear()
        self.LE_EDITURL.clear()
        self.CB_EditorRole.setCurrentIndex(0)
        self.CBX_Editable.setChecked(False)
        self.LE_Window.clear()
        self.LE_Model.clear()

    def refresh_ui(self, data):
        # print("\n=== DEBUG refresh_ui() ===")
        # print(f"active_columns: {self.controller.active_columns}")
        # print(f"active_mdata: {self.controller.active_mdata}")
        # print(f"columns_with_data keys: {list(self.controller.columns_with_data.keys())}")
        # print('DATA 1')
        # pp.pprint(data)
        """Full UI refresh with new data"""
        self.clear_all_ui()
        self.setup_column_ui()
        self.populate_editor_roles()
        # Set basic info
        self.ActiveLayer_label_2.setText(data.get("active_layer", ""))

        # Clear and repopulate columns list
        self.LW_filters.clear()
        self.LW_SavedColumns.clear()
        self.controller.saved_columns = {}  # Reset saved column tracker
        # print('DATA 2')
        # pp.pprint(data)
        # Load columns
        if "columns" in data:
            # Block signals during bulk update
            self.LW_filters.blockSignals(True)
            column_names = list(data["columns"].keys())
            self.LW_filters.addItems(column_names)
            self.LW_filters.blockSignals(False)

            # Only connect signals after data is fully loaded
            if column_names:
                self.LW_filters.setCurrentRow(0)

        # Load other data
        self.populate_line_edits()
        self.populate_checkboxes()
        self.populate_filter_list(data)

    def convert_str_zeros_to_int_for_form_populate(self, zeros_val):
        if isinstance(zeros_val, str):
            return len(zeros_val.split(".")[1])
        else:
            return zeros_val

    def set_table_rows(self):
        spin = self.SB_CustomList.value()
        self.TW_CustomList.setRowCount(spin)

    def get_custom_list_values(self):
        """Extract custom list values from table"""
        values = []
        for row in range(self.TW_CustomList.rowCount()):
            item = self.TW_CustomList.item(row, 0)
            if item and item.text().strip():
                values.append(item.text().strip())
        return values if values else None

    def update_saved_columns_list(self):
        """Refresh the saved columns list"""
        self.LW_SavedColumns.clear()
        if hasattr(self.controller, "saved_columns"):
            self.LW_SavedColumns.addItems(self.controller.saved_columns.keys())

    def _update_active_mdata_from_ui(self):
        if self.is_loading:
            print("Skipping metadata update during load")
            return

        if not hasattr(self.controller, 'active_mdata'):
            return

        print("Updating active_mdata from UI")  # Optional debug

        self.controller.active_mdata.update({
            "Window":        self.LE_Window.text() or None,
            "Model":         self.LE_Model.text() or None,
            "HelpPage":      self.LE_Help.text() or None,
            "Controller":    self.LE_Controller.text() or None,
            "Service":       self.CB_service.currentText() or None,
            "IdField":       self.CB_ID.currentText() or None,
            "GetId":         self.CB_GETID.currentText() or None,
            "IsSpatial":     1 if self.CBX_IsSpatial.isChecked() else 0,
            "ExcelExporter": 1 if self.CBX_Excel.isChecked() else 0,
            "ShpExporter":   1 if self.CBX_Shapefile.isChecked() else 0,
            "IsSwitch":      1 if self.CBX_IsSwitch.isChecked() else 0,
        })

    def open_layer_selector(self):
        db_path = self.controller.db_path
        dialog = LayerSelectDialog(db_path, parent=self)
        if dialog.exec_() == QDialog.Accepted:
            selected_layer = dialog.selected_layer
            if selected_layer:
                print(f"Loading layer: {selected_layer}")
                self.controller.read_db(selected_layer)
                self.populate_ui()

    def save_current_layer_to_db(self):
        print("Saving current layer to DB...")  # Optional debug

        # Push form fields for currently selected column into memory
        self.save_column_data()

        # Push UI values for layer-level metadata
        self._update_active_mdata_from_ui()

        # Push the current LW_filters order to the controller
        try:
            ordered_columns = self.get_ordered_listwidget_items()
            self.controller.update_display_order_from_ui(ordered_columns)
        except Exception as e:
            print(f"Warning: could not capture DisplayOrder from UI: {e}")

        # Save everything to DB
        try:
            db_path = self.controller.db_path
            self.controller.save_layer_atomic(db_path)
            QtWidgets.QMessageBox.information(self, "Saved", "Layer saved successfully.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Save failed", str(e))

    def add_new_layer_to_db(self):
        """
        Create a brand-new layer in the DB from the selected Mapfile layer name,
        using the WFS schema to build GridColumns, then refresh the UI.
        """
        try:
            # 0) Get the layer name from the dropdown the mapfile filled
            layer_name = self.CB_MAPLAYERS.currentText().strip()
            if not layer_name:
                QtWidgets.QMessageBox.warning(self, "Select a layer", "Pick a layer from CB_MAPLAYERS first.")
                return

            # 1) Show a simple progress dialog (non-cancelable)
            progress = QProgressDialog("Importing layer from WFS...", None, 0, 0, self)
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.setRange(0, 100)
            progress.show()
            QtWidgets.QApplication.processEvents()

            # 2) Run the importer
            # Use the same WFS endpoint you�ve been using elsewhere
            wfs_url = settings.WFS_URL  # centralised in app2.settings
            importer = WFSToDB(
                self.controller.db_path,
                wfs_url,
                timeout=settings.WFS_READ_TIMEOUT,
                connect_timeout=settings.WFS_CONNECT_TIMEOUT,
                retries=settings.WFS_RETRY_ATTEMPTS,
                backoff_factor=settings.WFS_RETRY_BACKOFF,
            )

            # This inserts the row in Layers + GridMData and all GridColumns
            importer.run(layer_name)

            # 3) Refresh controller + UI from DB so the new layer shows everywhere
            self.controller.read_db(layer_name)   # emits data_updated -> refreshes UI
            #self.populate_ui()                    # safe to call; ensures widgets are filled

            progress.setValue(100)
            progress.close()
            QtWidgets.QMessageBox.information(self, "Success", f"Layer '{layer_name}' added to the database.")

        except Exception as e:
            try:
                progress.close()
            except Exception:
                pass
            QtWidgets.QMessageBox.critical(self, "WFS import failed", str(e))
            print("add_new_layer_to_db error:")
            print(traceback.format_exc())

