from PyQt5.QtWidgets import QMessageBox
from PyQt5.QtCore import QTimer


class ListFiltersMixin:
    @staticmethod
    def _get_val(d: dict, *keys, default=""):
        """Return first non-empty value found for any key in keys."""
        if not d:
            return default
        for k in keys:
            v = d.get(k, None)
            if v is None:
                continue
            # Keep 0 if ever used, but here values are strings
            if isinstance(v, str):
                if v.strip() != "":
                    return v
            else:
                return v
        return default

    @staticmethod
    def _set_val(d: dict, key: str, value):
        """Set dict value, remove key if value is empty/None."""
        if value is None:
            d.pop(key, None)
            return
        if isinstance(value, str) and value.strip() == "":
            d.pop(key, None)
            return
        d[key] = value

    @staticmethod
    def populate_filter_widgets(owner, filter_data: dict):
        """Populate widgets with data from the selected filter."""
        local_field = ListFiltersMixin._get_val(filter_data, "LocalField", "localField")
        data_index = ListFiltersMixin._get_val(filter_data, "DataIndex", "dataIndex")
        id_field = ListFiltersMixin._get_val(filter_data, "IdField", "idField")
        label_field = ListFiltersMixin._get_val(filter_data, "LabelField", "labelField")
        store = ListFiltersMixin._get_val(filter_data, "Store", "store")
        store_id = ListFiltersMixin._get_val(filter_data, "StoreId", "storeId")
        store_filter = ListFiltersMixin._get_val(filter_data, "StoreFilter", "storeFilter")

        owner.CB_SelectLocalField.setCurrentText(local_field)
        owner.CB_SelectDataIndex.setCurrentText(data_index)
        owner.LE_InputIDField.setText(id_field or "")
        owner.LE_InputLabelField.setText(label_field or "")
        owner.LE_InputStore.setText(store or "")
        owner.LE_InputStoreID.setText(store_id or "")

        if hasattr(owner, "LE_InputStoreFilter"):
            owner.LE_InputStoreFilter.setText(store_filter or "")

    @staticmethod
    def clear_list_filter_widgets(owner):
        """Clear List Filter input widgets."""
        owner.CB_SelectLocalField.setCurrentIndex(0)
        owner.CB_SelectDataIndex.setCurrentIndex(0)
        owner.LE_InputIDField.clear()
        owner.LE_InputLabelField.clear()
        owner.LE_InputStore.clear()
        owner.LE_InputStoreID.clear()

        if hasattr(owner, "LE_InputStoreFilter"):
            owner.LE_InputStoreFilter.clear()

    @staticmethod
    def _get_filter_for_column(owner, column_name: str):
        """Return the active filter dict whose LocalField/localField == column_name, else None."""
        active = getattr(owner.controller, "active_filters", []) or []
        for f in active:
            lf = f.get("LocalField", None)
            if lf is None:
                lf = f.get("localField", None)
            if lf == column_name:
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
        if getattr(owner, "is_loading", False) or not local_field:
            return
        if owner.LW_filters.count() == 0:
            return

        owner._from_local_field = True

        owner.CB_SelectLocalField.setCurrentText(local_field)
        owner.CB_SelectDataIndex.setCurrentText(local_field)

        for i in range(owner.LW_filters.count()):
            if owner.LW_filters.item(i).text() == local_field:
                owner.LW_filters.setCurrentRow(i)
                break

        QTimer.singleShot(0, lambda: setattr(owner, "_from_local_field", False))

    @staticmethod
    def save_new_filter(owner):
        local_field = owner.CB_SelectLocalField.currentText().strip()
        data_index = owner.CB_SelectDataIndex.currentText().strip()
        id_field = owner.LE_InputIDField.text().strip()
        label_field = owner.LE_InputLabelField.text().strip()
        store = owner.LE_InputStore.text().strip()
        store_id = owner.LE_InputStoreID.text().strip()

        store_filter = ""
        if hasattr(owner, "LE_InputStoreFilter"):
            store_filter = owner.LE_InputStoreFilter.text().strip()

        # Keep the original 6 mandatory
        if not all([local_field, data_index, id_field, label_field, store, store_id]):
            QMessageBox.warning(
                owner,
                "Incomplete list filter",
                "Please fill Local Field, Data Index, ID Field, Label Field, Store, and Store ID."
            )
            return

        new_filter = {
            "LocalField": local_field,
            "DataIndex": data_index,
            "IdField": id_field,
            "LabelField": label_field,
            "Store": store,
            "StoreId": store_id,
        }

        # Optional StoreFilter
        if store_filter.strip():
            new_filter["StoreFilter"] = store_filter.strip()

        added = owner.controller.add_filter(new_filter)

        if added:
            QMessageBox.information(
                owner,
                "List filter added",
                f"A list filter for '{new_filter['LocalField']}' has been added.",
            )
        else:
            QMessageBox.warning(
                owner,
                "Filter exists",
                f"A list filter for '{new_filter['LocalField']}' already exists.",
            )

    @staticmethod
    def update_selected_filter(owner):
        local_field = owner.CB_SelectLocalField.currentText().strip()
        data_index = owner.CB_SelectDataIndex.currentText().strip()
        id_field = owner.LE_InputIDField.text().strip()
        label_field = owner.LE_InputLabelField.text().strip()
        store = owner.LE_InputStore.text().strip()
        store_id = owner.LE_InputStoreID.text().strip()

        store_filter = ""
        if hasattr(owner, "LE_InputStoreFilter"):
            store_filter = owner.LE_InputStoreFilter.text().strip()

        if not local_field:
            QMessageBox.warning(owner, "No selection", "Select a Local Field to update.")
            return

        missing = []
        if not data_index:
            missing.append("Data Index")
        if not id_field:
            missing.append("ID Field")
        if not label_field:
            missing.append("Label Field")
        if not store:
            missing.append("Store")
        if not store_id:
            missing.append("Store ID")
        if missing:
            QMessageBox.warning(
                owner,
                "Incomplete list filter",
                "List filters require all fields:\n- " + "\n- ".join(missing),
            )
            return

        af = getattr(owner.controller, "active_filters", []) or []
        filt = next(
            (f for f in af if (f.get("LocalField") or f.get("localField")) == local_field),
            None
        )
        if not filt:
            QMessageBox.warning(owner, "Not found", f"No existing filter for '{local_field}' to update.")
            return

        # Canonical DB-style keys
        filt["LocalField"] = local_field
        filt["DataIndex"] = data_index
        filt["IdField"] = id_field
        filt["LabelField"] = label_field
        filt["Store"] = store
        filt["StoreId"] = store_id

        if store_filter.strip():
            filt["StoreFilter"] = store_filter.strip()
        else:
            filt.pop("StoreFilter", None)

        ListFiltersMixin.populate_filter_widgets(owner, filt)

    @staticmethod
    def delete_selected_filter(owner):
        current_item = owner.LW_filters.currentItem()
        if not current_item:
            print("No column selected to delete its filter.")
            return

        col_name = current_item.text()
        pre = len(getattr(owner.controller, "active_filters", []) or [])
        owner.controller.active_filters = [
            f for f in (getattr(owner.controller, "active_filters", []) or [])
            if (f.get("LocalField") or f.get("localField")) != col_name
        ]
        post = len(getattr(owner.controller, "active_filters", []) or [])

        if post < pre:
            ListFiltersMixin.clear_list_filter_widgets(owner)
            QMessageBox.information(
                owner,
                "List filter deleted",
                f"A list filter for '{col_name}' has been deleted.",
            )
        else:
            QMessageBox.warning(
                owner,
                "Not found",
                f"There is no list filter for '{col_name}'.",
            )
