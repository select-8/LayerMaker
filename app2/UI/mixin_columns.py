# app2/UI/mixin_columns.py
from PyQt5.QtWidgets import QMessageBox
import traceback
from app2.UI.mixin_listfilters import ListFiltersMixin

class ColumnsMixin:
    @staticmethod
    def _get_edit_widgets(owner):
        le_id = getattr(owner, "LE_IDPROPERTY", None)
        le_data = getattr(owner, "LE_DATAPROPERTY", None)
        le_editurl = getattr(owner, "LE_EDITURL", None) or getattr(owner, "LE_EDIT_SERVICE", None)
        cb_role = getattr(owner, "CB_EditorRole", None)
        cb_editable = getattr(owner, "CB_EditColumn", None) or getattr(owner, "CBX_Editable", None)
        return le_id, le_data, le_editurl, cb_role, cb_editable

    @staticmethod
    def _validate_edit_before_save(owner) -> bool:
        try:
            # Column name for friendlier errors
            item = owner.LW_filters.currentItem()
            col_name = item.text() if item else "selected column"

            le_id, le_data, le_editurl, cb_role, cb_editable = ColumnsMixin._get_edit_widgets(owner)
            if cb_editable is None:
                return True

            checked = cb_editable.isChecked()
            idprop = (le_id.text().strip() if le_id else "")
            dataprop = (le_data.text().strip() if le_data else "")
            editurl = (le_editurl.text().strip() if le_editurl else "")
            role = (cb_role.currentText().strip() if cb_role else "")

            all_filled = all([idprop, dataprop, editurl, role])
            any_filled = any([idprop, dataprop, editurl, role])

            if checked and not all_filled:
                QMessageBox.warning(
                    owner,
                    "Missing Edit Details",
                    f"Edit Column is enabled for **{col_name}**, but some required fields are empty.\n\n"
                    "Please fill: ID Property, Data Property, Edit Service URL, and Role."
                )
                return False

            if not checked and any_filled:
                QMessageBox.warning(
                    owner,
                    "Incomplete Edit Configuration",
                    f"You entered edit details for **{col_name}** but “Edit Column” is not enabled.\n\n"
                    "Either enable “Edit Column” and complete all fields, or clear the edit fields."
                )
                return False

            return True
        except Exception as e:
            print("Validation error:", e)
            return True

    @staticmethod
    def update_column_properties_ui(owner):
        """Safely update column properties with full error handling and partial population support."""
        current_file_layer = owner.ActiveLayer_label_2.text()
        if not current_file_layer or current_file_layer != owner.controller.active_layer:
            return  # Abort if file changed during processing

        try:
            selected = owner.LW_filters.currentItem()
            if not selected:
                owner.clear_column_ui()
                return

            column_name = selected.text()
            column_data = owner.controller.get_column_data(column_name)
            # print(f'update_column_properties_ui(), column_data for {column_name}')
            # pp.pprint(column_data)

            # If no data found for column, clear UI
            if column_data is None:
                print(f"No column data found for '{column_name}', clearing inputs")
                owner.clear_column_ui()
                return

            #print(f"Populating column: {column_name} with data: {column_data}")

            # Populate available fields safely
            #self.LB_ColumnIndex.setText(column_name)
            owner.LE_ColumnDisplayText.setText(column_data.get("text") or "")
            owner.DSB_ColumnFlex.setValue(float(column_data.get("flex") or 0.0))
            owner.LE_NullText.setText(column_data.get("nullText") or column_data.get("NullText") or "")

            nv = column_data.get("nullValue", column_data.get("NullValue"))
            owner.DSB_NullVal.setValue(int(nv) if nv is not None else 0)

            renderer_id = column_data.get("GridColumnRendererId")
            if renderer_id:
                ix = -1
                for i in range(owner.CB_ColumnUnit.count()):
                    rid, _r, _x = owner.CB_ColumnUnit.itemData(i)
                    if rid == renderer_id:
                        ix = i; break
                owner.CB_ColumnUnit.setCurrentIndex(ix if ix >= 0 else 0)
            else:
                owner.CB_ColumnUnit.setCurrentIndex(0)

            # Update checkboxes safely
            owner.CBX_ColumnInGrid.setChecked(bool(column_data.get("inGrid", False)))
            owner.CBX_ColumnHidden.setChecked(bool(column_data.get("hidden", False)))
            owner.CBX_NoFilter.setChecked(bool(column_data.get("noFilter", False)))

            # Handle special cases safely
            owner.handle_special_column_cases(column_data)

            # --- NEW: Sync List Filter widgets with the selected column ---
            try:
                column_name = selected.text()
                active_filters = getattr(owner.controller, "active_filters", []) or []
                # Find a list filter whose localField matches the selected column
                match = next((f for f in active_filters if f.get("localField") == column_name), None)

                if match:
                    ListFiltersMixin.populate_filter_widgets(owner, match)
                else:
                    # Always clear the list-only fields when there's no saved list filter
                    owner.LE_InputIDField.clear()
                    owner.LE_InputLabelField.clear()
                    owner.LE_InputStore.clear()
                    owner.LE_InputStoreID.clear()

                    # Keep both combos aligned with the selected column (don’t reset to blank)
                    owner.CB_SelectLocalField.setCurrentText(column_name)
                    owner.CB_SelectDataIndex.setCurrentText(column_name)
            except Exception as e:
                print(f"List filter sync failed: {e}")
                ListFiltersMixin.clear_list_filter_widgets(owner)


        except Exception as e:
            print(f"Column update failed: {e}")
            owner.clear_column_ui()

    @staticmethod
    def get_ordered_listwidget_items(owner):
        """Extracts items from QListWidget in order of their index."""
        return [owner.LW_filters.item(i).text() for i in range(owner.LW_filters.count())]

    @staticmethod
    def collect_column_data_from_ui(owner):
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
            current_item = owner.LW_filters.currentItem()
            if not current_item:
                return None

            column_name = current_item.text()
            original_data = owner.controller.get_column_data(column_name) or {}

            is_edit = owner.CBX_Editable.checkState() == 2
            idx = owner.CB_ColumnUnit.currentIndex()
            payload = owner.CB_ColumnUnit.itemData(idx) or (None, None, None)
            renderer_id, renderer, extype = payload

            new_data = {
                "flex": float(owner.DSB_ColumnFlex.value()),
                "text": owner.LE_ColumnDisplayText.text().strip() or None,
                "renderer": (renderer or "").strip(),
                "exType": (extype or "").strip(),
                "GridColumnRendererId": renderer_id,
                "inGrid": owner.CBX_ColumnInGrid.isChecked(),
                "hidden": owner.CBX_ColumnHidden.isChecked(),
                "index": column_name,
                "NullText": owner.LE_NullText.text().strip() or None,
                "NullValue": (None if owner.DSB_NullVal.value() == 0 else int(owner.DSB_NullVal.value())),
                "zeros": int(owner.DSB_Zeros.value()) if owner.DSB_Zeros.isEnabled() and owner.DSB_Zeros.value() > 0 else None,
                "noFilter": owner.CBX_NoFilter.isChecked(),
            }

            
            custom_list = owner.get_custom_list_values()
            if custom_list:
                new_data["customList"] = custom_list
            else:
                owner.TW_CustomList.clear()
                owner.SB_CustomList.setValue(0)

            idprop   = owner.LE_IDPROPERTY.text() or None
            dataprop = owner.LE_DATAPROPERTY.text() or None
            edit_service_url = owner.LE_EDITURL.text() or None
            edit_role = owner.CB_EditorRole.currentText() or None

            new_data["edit"] = {
                "editable": is_edit,
                "groupEditIdProperty": idprop,
                "groupEditDataProp": dataprop,
                "editServiceUrl": edit_service_url,
                "editUserRole": edit_role,
            }

            return {k: v for k, v in new_data.items() if v is not None}

        except Exception as e:
            print(f"Error collecting column data: {e}")
            return None

    @staticmethod
    def validate_column_data(owner, data):
        """Validation for a single column edit before saving."""
        # Existing validations
        if not data.get("renderer"):
            QMessageBox.warning(owner, "Validation", "Renderer type is required")
            return False
        if data.get("flex", 0) < 0:
            QMessageBox.warning(owner, "Validation", "Flex cannot be negative")
            return False

        # --- New: block both list filter and custom list on the same column ---
        # Which column is currently being saved?
        current_item = owner.LW_filters.currentItem()
        col_name = current_item.text() if current_item else None

        # Is there a LIST filter linked to this column right now?
        active_filters = getattr(owner.controller, "active_filters", []) or []
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
                owner,
                "Cannot Save Filters",
                f"Column {col_name or 'Selected column'} has both a list and custom filter defined, "
                f"please remove one before saving."
            )
            return False

        return True

    @staticmethod
    def save_column_data(owner):
        """Simplified save handler using collect_column_data_from_ui()"""
        try:
            # 1. Validate selection
            if not owner.LW_filters.currentItem():
                QMessageBox.warning(
                    owner, "No Selection", "Please select a column first"
                )
                return

            # 2. Collect data (includes null/empty handling)
            column_name = owner.LW_filters.currentItem().text()
            column_data = ColumnsMixin.collect_column_data_from_ui(owner)
            # print('save_column_data')
            # pp.pprint(column_data)
            if not column_data:
                raise ValueError("Invalid column data")

            if not ColumnsMixin.validate_column_data(owner, column_data):
                return

            # 3. Save via controller
            if owner.controller.update_column_data(column_name, column_data):
                owner.update_saved_columns_list()  # Refresh UI if needed
            else:
                QMessageBox.warning(owner, "Error", "Failed to save column data")

        except Exception as e:
            QMessageBox.critical(owner, "Error", f"Save failed: {str(e)}")
            print(f"Save error: {traceback.format_exc()}")
