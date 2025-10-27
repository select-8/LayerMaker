from PyQt5 import QtCore, QtWidgets
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QTableWidgetItem, QProgressDialog, QHeaderView, QColorDialog, QDialog

import os, logging, pprint, traceback, sqlite3, mappyfile

from app2.view import Ui_MainWindow
from app2 import settings
from app2.settings import REPO_ROOT
from app2.wfs_to_db import WFSToDB
from grid_generator.grid_from_db import GridGenerator
from layer_generator.layer_window import MapfileWiring
from app2.UI.mixin_metadata import MetadataMixin
from app2.UI.mixin_sorters import SortersMixin
from app2.UI.mixin_listfilters import ListFiltersMixin
from tabulate import tabulate


logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=4)


class MainWindowUIClass(QtWidgets.QMainWindow):
    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.is_loading = True
        self.current_filepath = None

        # ---- build the UI via composition ----
        ui = Ui_MainWindow()
        ui.setupUi(self)

        # Because we changed the method for how the app connects to the UI.
        # Previously, Ui_MainWindow was inherited directly, so all widgets were
        # already attributes of self. Now, we create an instance of Ui_MainWindow
        # and call setupUi(self), this loop grafts the widgets to self.
        for name, value in ui.__dict__.items():
            if not name.startswith("__") and not hasattr(self, name):
                setattr(self, name, value)
                # Now we can continue to use self.<widgetname> as before.

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
        self.BTN_LAYERSELECT.clicked.connect(self.open_layer_selector)
        self.BTN_GENERATEGRID.clicked.connect(self.generate_grid)
        self.BTN_COLUMNSAVE.clicked.connect(self.save_column_data)
        self.BTN_ADDLISTROWS.clicked.connect(self.set_table_rows)
        self.BTN_SAVETODB.clicked.connect(self.save_current_layer_to_db)
        self.BTN_GETMAPFILE.clicked.connect(self.openmapfile_filehandler)
        self.BTN_ADDTODB.clicked.connect(self.add_new_columns)
        self.BTN_GENDB.clicked.connect(self.add_new_layer_to_db)
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

    def resize_some_ui_objects(self):
        # Called in populate_ui() after populating
        self.SPLIT_LEFT.setSizes([750, 200, 50])
        self.SPLIT_COLUMNS.setSizes([300, 600])
        self.BTN_COLUMNSAVE.setMaximumHeight(40)
        self.CB_ColumnUnit.setPlaceholderText("Select unit...")

        hdr = self.TW_SORTERS.horizontalHeader()
        hdr.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)

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
            self.LW_filters.itemSelectionChanged.connect(self.update_column_properties_ui)


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
            self.controller.active_filters = data.get("active_filters") or []
            current_item = self.LW_filters.currentItem()
            col = current_item.text() if current_item else None
            if col:
                ListFiltersMixin._populate_listfilter_for_column(self, col)
            else:
                ListFiltersMixin.clear_list_filter_widgets(self)

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

        MetadataMixin.populate_combo_boxes(self)
        MetadataMixin.populate_line_edits(self)
        MetadataMixin.populate_checkboxes(self)
        SortersMixin.set_sorters(self)
        self.resize_some_ui_objects()
        QtCore.QTimer.singleShot(0, self.update_column_properties_ui)

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
                #self.update_column_properties_ui()
            else:
                self.clear_column_ui()

        except Exception as e:
            print(f"Column UI setup error: {e}")
            self.clear_column_ui()
        finally:
            self.LW_filters.blockSignals(False)
            QtCore.QTimer.singleShot(0, self.update_column_properties_ui)

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
            self.LE_NullText.setText(column_data.get("nullText") or column_data.get("NullText") or "")

            nv = column_data.get("nullValue", column_data.get("NullValue"))
            self.DSB_NullVal.setValue(int(nv) if nv is not None else 0)

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

            # --- NEW: Sync List Filter widgets with the selected column ---
            try:
                column_name = selected.text()
                active_filters = getattr(self.controller, "active_filters", []) or []
                # Find a list filter whose localField matches the selected column
                match = next((f for f in active_filters if f.get("localField") == column_name), None)

                if match:
                    ListFiltersMixin.populate_filter_widgets(self, match)
                else:
                    # Always clear the list-only fields when there's no saved list filter
                    self.LE_InputIDField.clear()
                    self.LE_InputLabelField.clear()
                    self.LE_InputStore.clear()
                    self.LE_InputStoreID.clear()

                    # Keep both combos aligned with the selected column (don’t reset to blank)
                    self.CB_SelectLocalField.setCurrentText(column_name)
                    self.CB_SelectDataIndex.setCurrentText(column_name)
            except Exception as e:
                print(f"List filter sync failed: {e}")
                ListFiltersMixin.clear_list_filter_widgets(self)


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

    #---- Edit metadata helpers ----#
    def _get_edit_widgets(self):
        le_id      = getattr(self, "LE_IDPROPERTY", None)
        le_data    = getattr(self, "LE_DATAPROPERTY", None)
        le_editurl = getattr(self, "LE_EDITURL", None) or getattr(self, "LE_EDIT_SERVICE", None)
        # FIX: correct role widget name
        cb_role    = getattr(self, "CB_EditorRole", None)
        # FIX: prefer CB_EditColumn if present, else fallback to CBX_Editable
        cb_editable = getattr(self, "CB_EditColumn", None) or getattr(self, "CBX_Editable", None)
        return le_id, le_data, le_editurl, cb_role, cb_editable

    def _read_edit_values(self):
        le_id, le_data, le_editurl, cb_role, cb_editable = self._get_edit_widgets()
        role_val = None
        role_text = ""
        if cb_role is not None:
            if hasattr(cb_role, "currentData"):
                role_val = cb_role.currentData()
            role_text = cb_role.currentText() or ""
        return {
            "checked": bool(cb_editable and cb_editable.isChecked()),
            "idprop": (le_id.text().strip() if le_id else ""),
            "dataprop": (le_data.text().strip() if le_data else ""),
            "editurl": (le_editurl.text().strip() if le_editurl else ""),
            "role_val": role_val,
            "role_text": role_text.strip(),
        }

    def _is_role_selected(self, vals):
        # Treat placeholder/empty as not selected. Adjust placeholder to match yours if different.
        placeholder_texts = {"Select role", "Select Role", ""}
        return (vals["role_val"] not in (None, "", -1)) or (vals["role_text"] not in placeholder_texts)

    def _edit_inputs_all_filled(self, vals):
        return all([
            bool(vals["idprop"]),
            bool(vals["dataprop"]),
            bool(vals["editurl"]),
            self._is_role_selected(vals),
        ])

    def _edit_inputs_any_filled(self, vals):
        return any([
            bool(vals["idprop"]),
            bool(vals["dataprop"]),
            bool(vals["editurl"]),
            bool(vals["role_text"]),   # if role text changed from placeholder
            vals["role_val"] not in (None, "", -1),
        ])

    #---- Save handlers ----#
    def _validate_edit_before_save(self) -> bool:
        try:
            # Column name for friendlier errors
            item = self.LW_filters.currentItem()
            col_name = item.text() if item else "selected column"

            le_id, le_data, le_editurl, cb_role, cb_editable = self._get_edit_widgets()
            if cb_editable is None:
                return True

            checked  = cb_editable.isChecked()
            idprop   = (le_id.text().strip() if le_id else "")
            dataprop = (le_data.text().strip() if le_data else "")
            editurl  = (le_editurl.text().strip() if le_editurl else "")
            role     = (cb_role.currentText().strip() if cb_role else "")

            all_filled = all([idprop, dataprop, editurl, role])
            any_filled = any([idprop, dataprop, editurl, role])

            if checked and not all_filled:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Missing Edit Details",
                    f"“Edit Column” is enabled for **{col_name}**, but some required fields are empty.\n\n"
                    "Please fill: ID Property, Data Property, Edit Service URL, and Role."
                )
                return False

            if not checked and any_filled:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Incomplete Edit Configuration",
                    f"You entered edit details for **{col_name}** but “Edit Column” is not enabled.\n\n"
                    "Either enable “Edit Column” and complete all fields, or clear the edit fields."
                )
                return False

            return True
        except Exception as e:
            print("Validation error:", e)
            return True

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
        """Validation for a single column edit before saving."""
        # Existing validations
        if not data.get("renderer"):
            QMessageBox.warning(self, "Validation", "Renderer type is required")
            return False
        if data.get("flex", 0) < 0:
            QMessageBox.warning(self, "Validation", "Flex cannot be negative")
            return False

        # --- New: block both list filter and custom list on the same column ---
        # Which column is currently being saved?
        current_item = self.LW_filters.currentItem()
        col_name = current_item.text() if current_item else None

        # Is there a LIST filter linked to this column right now?
        active_filters = getattr(self.controller, "active_filters", []) or []
        has_list_link = bool(
            col_name and any(f.get("localField") == col_name for f in active_filters)
        )

        # Has the user provided a CUSTOM LIST for this save?
        custom_vals = data.get("CustomListValues") or data.get("customList") or []
        if isinstance(custom_vals, str):
            # tolerate CSV input; trim empties
            custom_vals = [v.strip() for v in custom_vals.split(",") if v.strip()]
        has_custom = len(custom_vals) > 0

        # If both are present, stop here with a clear message (your requested wording)
        if has_list_link and has_custom:
            QMessageBox.warning(
                self,
                "Cannot Save Filters",
                f"Column {col_name or 'Selected column'} has both a list and custom filter defined, "
                f"please remove one before saving."
            )
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
                "NullText": self.LE_NullText.text().strip() or None,
                "NullValue": (None if self.DSB_NullVal.value() == 0 else int(self.DSB_NullVal.value())),
                "zeros": int(self.DSB_Zeros.value()) if self.DSB_Zeros.isEnabled() and self.DSB_Zeros.value() > 0 else None,
                "noFilter": self.CBX_NoFilter.isChecked(),
            }

            
            custom_list = self.get_custom_list_values()
            if custom_list:
                new_data["customList"] = custom_list
            else:
                self.TW_CustomList.clear()
                self.SB_CustomList.setValue(0)

            idprop   = self.LE_IDPROPERTY.text() or None
            dataprop = self.LE_DATAPROPERTY.text() or None
            edit_service_url = self.LE_EDITURL.text() or None
            edit_role = self.CB_EditorRole.currentText() or None

            new_data["edit"] = {
                "editable": is_edit,
                "groupEditIdProperty": idprop,
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
        MetadataMixin.populate_line_edits(self)
        MetadataMixin.populate_checkboxes(self)

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
        from app2.layer_select_dialog import LayerSelectDialog
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

        # --- edit column validation guard ---
        if not self._validate_edit_before_save():
            return

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

