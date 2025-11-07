# app2/UI/mixin_sorters.py
from PyQt5.QtWidgets import QHeaderView, QTableWidgetItem, QMessageBox
from PyQt5.QtCore import QTimer

class ListFiltersMixin:
    @staticmethod
    def populate_filter_widgets(owner, filter_data: dict):
        """Populate widgets with data from the selected filter."""

        owner.CB_SelectLocalField.setCurrentText(filter_data["localField"])
        owner.CB_SelectDataIndex.setCurrentText(filter_data["dataIndex"])
        owner.LE_InputIDField.setText(filter_data["idField"])
        owner.LE_InputLabelField.setText(filter_data["labelField"])
        owner.LE_InputStore.setText(filter_data["store"])
        owner.LE_InputStoreID.setText(filter_data["storeId"])
    
    @staticmethod
    def clear_list_filter_widgets(owner):
        """Clear List Filter input widgets."""
        # Combo boxes to first/blank entry
        owner.CB_SelectLocalField.setCurrentIndex(0)
        owner.CB_SelectDataIndex.setCurrentIndex(0)

        # Line edits to empty
        owner.LE_InputIDField.clear()
        owner.LE_InputLabelField.clear()
        owner.LE_InputStore.clear()
        owner.LE_InputStoreID.clear()

    @staticmethod
    def _get_filter_for_column(owner, column_name: str):
        """Return the active filter dict whose localField == column_name, else None."""
        active = getattr(owner.controller, "active_filters", []) or []
        for f in active:
            if f.get("localField") == column_name:
                return f
        return None

    @staticmethod
    def _populate_listfilter_for_column(owner, column_name: str):
        if not column_name:
            return
        match = ListFiltersMixin._get_filter_for_column(owner, column_name)
        if match:
            ListFiltersMixin.populate_filter_widgets(owner, match)
        else:
            ListFiltersMixin.clear_list_filter_widgets(owner)
            owner.CB_SelectLocalField.setCurrentText(column_name)
            owner.CB_SelectDataIndex.setCurrentText(column_name)

    @staticmethod
    def on_local_field_activated(owner, local_field: str):
        """

        """
        if getattr(owner, "is_loading", False) or not local_field:
            return
        if owner.LW_filters.count() == 0:
            return

        # mark source as user Local Field change
        owner._from_local_field = True

        # snap combos to what the user picked
        owner.CB_SelectLocalField.setCurrentText(local_field)
        owner.CB_SelectDataIndex.setCurrentText(local_field)

        # select the matching column in LW_filters (triggers update_column_properties_ui)
        for i in range(owner.LW_filters.count()):
            if owner.LW_filters.item(i).text() == local_field:
                owner.LW_filters.setCurrentRow(i)
                break

        # reset the flag after the selection-driven update runs
        QTimer.singleShot(0, lambda: setattr(owner, "_from_local_field", False))

    @staticmethod
    def save_new_filter(owner):
        local_field = owner.CB_SelectLocalField.currentText().strip()
        data_index  = owner.CB_SelectDataIndex.currentText().strip()
        id_field    = owner.LE_InputIDField.text().strip()
        label_field = owner.LE_InputLabelField.text().strip()
        store       = owner.LE_InputStore.text().strip()
        store_id    = owner.LE_InputStoreID.text().strip()

        if not all([local_field, data_index, id_field, label_field, store, store_id]):
            QMessageBox.warning(
                owner,
                "Incomplete list filter",
                "Please fill Local Field, Data Index, ID Field, Label Field, Store, and Store ID."
            )
            return

        new_filter = {
            "dataIndex": data_index,
            "idField": id_field,
            "labelField": label_field,
            "localField": local_field,
            "store": store,
            "storeId": store_id,
        }
        added = owner.controller.add_filter(new_filter)

        if added:
            QMessageBox.information(
                owner,
                "List filter added",
                f"A list filter for '{new_filter['localField']}' has been added.",
            )
        else:
            # Optional, but probably useful feedback
            QMessageBox.warning(
                owner,
                "Filter exists",
                f"A list filter for '{new_filter['localField']}' already exists.",
            )

    @staticmethod
    def update_selected_filter(owner):
            """Update the currently selected list filter (by Local Field)."""
            local_field = owner.CB_SelectLocalField.currentText().strip()
            data_index = owner.CB_SelectDataIndex.currentText().strip()
            id_field = owner.LE_InputIDField.text().strip()
            label_field = owner.LE_InputLabelField.text().strip()
            store = owner.LE_InputStore.text().strip()
            store_id = owner.LE_InputStoreID.text().strip()

            if not local_field:
                QMessageBox.warning(owner, "No selection", "Select a Local Field to update.")
                return

            # Require all 6 controls (same rule as save)
            missing = []
            if not local_field: missing.append("Local Field")
            if not data_index: missing.append("Data Index")
            if not id_field: missing.append("ID Field")
            if not label_field: missing.append("Label Field")
            if not store: missing.append("Store")
            if not store_id: missing.append("Store ID")
            if missing:
                QMessageBox.warning(
                    owner,
                    "Incomplete list filter",
                    "List filters require all fields:\n- " + "\n- ".join(missing),
                )
                return

            # Find existing filter for this Local Field
            af = getattr(owner.controller, "active_filters", []) or []
            filt = next((f for f in af if f.get("localField") == local_field), None)
            if not filt:
                QMessageBox.warning(owner, "Not found", f"No existing filter for '{local_field}' to update.")
                return

            # Update fields in-place
            filt["localField"] = local_field
            filt["dataIndex"] = data_index
            filt["idField"] = id_field
            filt["labelField"] = label_field
            filt["store"] = store
            filt["storeId"] = store_id

            # Optional: refresh the widgets (keeps UI consistent)
            ListFiltersMixin.populate_filter_widgets(owner, filt)

    @staticmethod
    def delete_selected_filter(owner):
        """Delete the filter tied to the currently selected column."""
        current_item = owner.LW_filters.currentItem()
        if not current_item:
            print("No column selected to delete its filter.")
            return

        col_name = current_item.text()
        pre = len(owner.controller.active_filters or [])
        owner.controller.active_filters = [
            f for f in (owner.controller.active_filters or [])
            if f.get("localField") != col_name
        ]
        post = len(owner.controller.active_filters or [])
        if post < pre:
            ListFiltersMixin.clear_list_filter_widgets(owner)
            print(f"Filter for '{col_name}' deleted.")

            QMessageBox.information(
                owner,
                "List filter added",
                f"A list filter for '{col_name}' has been deleted.",
            )
        else:
            print(f"No filter found for '{col_name}'.")
            QMessageBox.warning(
                owner,
                "Filter exists",
                f"There is no list filter for '{col_name}'.",
            )