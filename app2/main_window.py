from PyQt5 import QtCore, QtWidgets, uic
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QTableWidgetItem, QProgressDialog, QHeaderView, QColorDialog, QDialog
from PyQt5.QtGui import QPalette

import os, logging, pprint, traceback, sqlite3, mappyfile

#from app2.view import Ui_MainWindow
from app2 import settings
from app2.settings import REPO_ROOT, LAYERMAKER_UI_PATH
from app2.wfs_to_db import WFSToDB
from grid_generator.grid_from_db import GridGenerator
from layer_generator.layer_window import MapfileWiring
from app2.UI.mixin_metadata import MetadataMixin
from app2.UI.mixin_sorters import SortersMixin
from app2.UI.mixin_listfilters import ListFiltersMixin
from app2.UI.mixin_dialogs import DialogsMixin
from app2.UI.mixin_services import ServicesMixin
from app2.UI.mixin_columns import ColumnsMixin
from tabulate import tabulate


logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=4)


class MainWindowUIClass(QtWidgets.QMainWindow):
    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.is_loading = True
        self.current_filepath = None

        # # ---- build the UI via composition ----
        # ui = Ui_MainWindow()
        # ui.setupUi(self)

        # # Because we changed the method for how the app connects to the UI.
        # # Previously, Ui_MainWindow was inherited directly, so all widgets were
        # # already attributes of self. Now, we create an instance of Ui_MainWindow
        # # and call setupUi(self), this loop grafts the widgets to self.
        # for name, value in ui.__dict__.items():
        #     if not name.startswith("__") and not hasattr(self, name):
        #         setattr(self, name, value)
        #         # Now we can continue to use self.<widgetname> as before.

        uic.loadUi(LAYERMAKER_UI_PATH, self)

        # ---- set active layer label style as distinct ----
        font = self.ActiveLayer_label_2.font()
        font.setPointSize(15)
        self.ActiveLayer_label_2.setFont(font)
        self.ActiveLayer_label_2.setStyleSheet("""
            font-weight: bold;
            letter-spacing: 1.5px;
            color: #FF69B4;
        """)

        print("UI loaded, has LE_Window:", hasattr(self, "LE_Window"))
        # ---- wire metadata AFTER widgets exist ----
        MetadataMixin.setup_metadata_connections(self)

        # ---- your existing startup ----
        template_dir = os.path.join(REPO_ROOT, "layer_generator")
        self.mapfile = MapfileWiring(
            ui=self,
            template_dir=template_dir,
            out_dir=template_dir,
            template_name="layer.template",
        )

        self.setup_column_ui()
        self.setup_buttons()
        self.connect_signals()

        SortersMixin.set_sorters_table_dimensions(self)

        self.is_loading = False
        self._from_local_field = False

        self.populate_unit_combo()
        self.populate_editor_roles()

    def setup_buttons(self):
        """Connect buttons to controller methods."""
        self.BTN_LAYERSELECT.clicked.connect(lambda: DialogsMixin.open_layer_selector(self))
        self.BTN_GENERATEGRID.clicked.connect(lambda: ServicesMixin.generate_grid(self))
        self.BTN_COLUMNSAVE.clicked.connect(lambda: ColumnsMixin.save_column_data(self))
        self.BTN_ADDLISTROWS.clicked.connect(self.set_table_rows)
        self.BTN_SAVETODB.clicked.connect(self.save_current_layer_to_db)
        self.BTN_GETMAPFILE.clicked.connect(lambda: DialogsMixin.openmapfile_filehandler(self))
        self.BTN_ADDTODB.clicked.connect(lambda: ServicesMixin.add_new_columns(self))
        self.BTN_COLUMNREMOVE.clicked.connect(lambda: ColumnsMixin.remove_selected_column(self))
        self.BTN_GENDB.clicked.connect(lambda: ServicesMixin.add_new_layer_to_db(self))
        self.BTN_SAVESORTER.clicked.connect(lambda: SortersMixin.save_sorter(self))
        self.BTN_DELETESORTER.clicked.connect(lambda: SortersMixin.delete_selected_sorter(self))
        self.BTN_SAVELISTFILTER.clicked.connect(lambda: ListFiltersMixin.save_new_filter(self))
        self.BTN_DELETELISTFILTER.clicked.connect(lambda: ListFiltersMixin.delete_selected_filter(self))
        self.BTN_UPDATELISTFILTER.clicked.connect(lambda: ListFiltersMixin.update_selected_filter(self))

        self.BTN_COLOURPICKER.clicked.connect(self.openColorDialog)

    # ---- debug helpers ----
    def _install_edit_spies(self):
        self._spy_lineedit(self.LE_DATAPROPERTY, "LE_DATAPROPERTY")
        self._spy_lineedit(self.LE_IDPROPERTY, "LE_IDPROPERTY")

    def _spy_lineedit(self, le, name):
        import traceback
        # avoid double-wrapping
        if getattr(le, "_spy_wrapped", False):
            return
        orig_setText = le.setText
        def wrapped_setText(text):
            print(f"[SET] {name} <- {text!r}")
            print("".join(traceback.format_stack(limit=6)))
            return orig_setText(text)
        le.setText = wrapped_setText
        le._spy_wrapped = True
        le.textChanged.connect(lambda t: print(f"[SIG] {name}.textChanged -> {t!r}"))
        le.editingFinished.connect(lambda: print(f"[SIG] {name}.editingFinished (final={le.text()!r})"))

    # def resize_some_ui_objects(self):
    #     # Called in populate_ui() after populating
    #     self.SPLIT_LEFT.setSizes([750, 200, 50])
    #     self.SPLIT_COLUMNS.setSizes([300, 600])
    #     self.BTN_COLUMNSAVE.setMaximumHeight(40)
    #     self.CB_ColumnUnit.setPlaceholderText("Select unit...")

    #     hdr = self.TW_SORTERS.horizontalHeader()
    #     hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
    #     hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

    def openColorDialog(self):
        # Open the colour dialog directly
        colour = QColorDialog.getColor()

        if colour.isValid():
            # Extract colour name (HEX)
            colour_name = colour.name()  
            
            # Extract RGB values
            rgb_values = (colour.red(), colour.green(), colour.blue()) 

            # For debugging or other purposes, print the extracted values
            print(f"Colour Name (HEX): {colour_name}")
            print(f"RGB Values: {rgb_values}")

    def connect_signals(self):
        """Connect signals to slots with proper signal management"""
        # Disconnect all first to prevent duplicate connections
        try:
            self.controller.data_updated.disconnect()
        except Exception:
            pass
        try:
            self.controller.filter_selected.disconnect()
        except Exception:
            pass
        try:
            self.LW_filters.itemSelectionChanged.disconnect()
        except Exception:
            pass

        # Reconnect
        self.controller.data_updated.connect(self.handle_data_updated)
        self.controller.filter_selected.connect(lambda f: ListFiltersMixin.populate_filter_widgets(self, f))
        # Auto-select the matching column in LW_filters when user picks Local Field
        self.CB_SelectLocalField.activated[str].connect(lambda s: ListFiltersMixin.on_local_field_activated(self, s))

        if hasattr(self.controller, "columns_with_data"):
            self.LW_filters.itemSelectionChanged.connect(lambda: ColumnsMixin.update_column_properties_ui(self))

    def handle_data_updated(self, data):
        """Central handler for data updates"""
        #print("handle_data_updated called with data:")  # Debugging
        #pp.pprint(data)

        if data.get("status") == "loaded":
            # Full UI load (after YAML file opened)
            self.is_loading = True
            try:
                self.refresh_ui(data)  # This will include column + filter population
            finally:
                self.is_loading = False
            return

        # For filter updates/adds/deletes, avoid overwriting unsaved mdata
        if self.is_loading:
            print("Skipping UI metadata update during protected load")
            return

        if "active_filters" in data:
            self.controller.active_filters = data.get("active_filters") or []
            current_item = self.LW_filters.currentItem()
            col = current_item.text() if current_item else None
            if col:
                ListFiltersMixin._populate_listfilter_for_column(self, col)
            else:
                ListFiltersMixin.clear_list_filter_widgets(self)

    def populate_unit_combo(self):
        """Populate CB_ColumnUnit with DisplayName, store (id, renderer, exType) as itemData."""
        print(self.controller.db_path)
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
        try:
            self.is_loading = True
            #self.set_layer_label()

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

            MetadataMixin.populate_combo_boxes(self)
            MetadataMixin.populate_line_edits(self)
            MetadataMixin.populate_checkboxes(self)
            SortersMixin.set_sorters(self)
            #self.resize_some_ui_objects()
            QtCore.QTimer.singleShot(0, lambda: ColumnsMixin.update_column_properties_ui(self))
        finally:
            self.is_loading = False

    def set_layer_label(self):
        self.ActiveLayer_label_2.setText(self.controller.active_layer)

    def set_active_columns_noorder(self):
        self.active_columns_without_order = (
            self.controller.active_columns or []
        )  # Fallback to empty list
        self.active_columns_without_order.insert(0, None)  # blank item first
        return self.active_columns_without_order

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
                #ColumnsMixin.update_column_properties_ui(self)
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

    def handle_special_column_cases(self, column_data):
        """Handle zeros, customList, and edit metadata safely."""

        # # Handle zeros
        # if (column_data.get("renderer") in ("double", "meters")):
        #     zeros_val = column_data.get("zeros")
        #     if isinstance(zeros_val, str):
        #         zeros_val = self.convert_str_zeros_to_int_for_form_populate(zeros_val)
        #     self.DSB_Zeros.setValue(zeros_val if zeros_val is not None else 2)
        # else:
        #     self.DSB_Zeros.clear()

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
            MetadataMixin.set_checkbox(self.CBX_Editable, edit_data.get("editable", False))
            self.LE_IDPROPERTY.setText(edit_data.get("groupEditIdProperty") or "")
            self.LE_DATAPROPERTY.setText(edit_data.get("groupEditDataProp") or "")
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
        #Column basics
        self.LE_ColumnDisplayText.clear()
        self.DSB_ColumnFlex.setValue(0.0)
        self.CB_ColumnUnit.setCurrentIndex(0)
        self.LE_NullText.clear()
        self.DSB_Zeros.clear()
        self.DSB_NullVal.clear()
        self.CBX_ColumnInGrid.setChecked(False)
        self.CBX_ColumnHidden.setChecked(False)
        self.CBX_NoFilter.setChecked(False)

        # No need to rest this
        # self.LW_SavedColumns.clear()

        # Custom list
        self.TW_CustomList.setRowCount(0)
        self.SB_CustomList.setValue(0)
        # Edit controls
        self.LE_IDPROPERTY.clear()
        self.LE_DATAPROPERTY.clear()
        self.LE_EDITURL.clear()
        self.CB_EditorRole.setCurrentIndex(0)
        self.CBX_Editable.setChecked(False)

    def refresh_ui(self, data):
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
        MetadataMixin.populate_line_edits(self)
        MetadataMixin.populate_checkboxes(self)
        MetadataMixin.populate_combo_boxes(self)

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

    def save_current_layer_to_db(self):
        print("Saving current layer to DB...")  # Optional debug

        # --- edit column validation guard ---
        if not ColumnsMixin._validate_edit_before_save(self):
            return

        # Push form fields for currently selected column into memory
        ColumnsMixin.save_column_data(self)

        # Push UI values for layer-level metadata
        self._update_active_mdata_from_ui()

        # Push the current LW_filters order to the controller
        try:
            ordered_columns = ColumnsMixin.get_ordered_listwidget_items(self)
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



