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

        # StoreLocation is DB column "Store"
        store_location = ListFiltersMixin._get_val(filter_data, "Store", "storeLocation")

        store_id = ListFiltersMixin._get_val(filter_data, "StoreId", "storeId")
        store_filter = ListFiltersMixin._get_val(filter_data, "StoreFilter", "storeFilter")

        owner.CB_SelectLocalField.setCurrentText(local_field)
        owner.CB_SelectDataIndex.setCurrentText(data_index)
        owner.LE_InputIDField.setText(id_field or "")
        owner.LE_InputLabelField.setText(label_field or "")

        # Populate StoreLocation (DB: Store)
        if hasattr(owner, "LE_InputStoreLocation"):
            owner.LE_InputStoreLocation.setText(store_location or "")
        else:
            # Back-compat if UI still uses the old name
            if hasattr(owner, "LE_InputStore"):
                owner.LE_InputStore.setText(store_location or "")

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

        if hasattr(owner, "LE_InputStoreLocation"):
            owner.LE_InputStoreLocation.clear()
        else:
            if hasattr(owner, "LE_InputStore"):
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

        # StoreLocation (DB column Store)
        if hasattr(owner, "LE_InputStoreLocation"):
            store_location = owner.LE_InputStoreLocation.text().strip()
        else:
            store_location = owner.LE_InputStore.text().strip() if hasattr(owner, "LE_InputStore") else ""

        store_id = owner.LE_InputStoreID.text().strip()

        store_filter = ""
        if hasattr(owner, "LE_InputStoreFilter"):
            store_filter = owner.LE_InputStoreFilter.text().strip()

        # Mandatory fields (StoreFilter optional)
        if not all([local_field, data_index, id_field, label_field, store_location, store_id]):
            QMessageBox.warning(
                owner,
                "Incomplete list filter",
                "Please fill Local Field, Data Index, ID Field, Label Field, Store Location, and Store ID."
            )
            return

        # Use RUNTIME keys (the only thing controller.save_filters_to_db reads)
        new_filter = {
            "localField": local_field,
            "dataIndex": data_index,
            "idField": id_field,
            "labelField": label_field,
            "storeLocation": store_location,
            "storeId": store_id,
        }

        # Optional StoreFilter
        if store_filter.strip():
            new_filter["storeFilter"] = store_filter.strip()

        added = owner.controller.add_filter(new_filter)

        if not added:
            QMessageBox.warning(
                owner,
                "Filter exists",
                f"A list filter for '{local_field}' already exists in this layer session.\nUse Update Filter if you want to change it.",
            )
            return

        # Model B: persist immediately (this is where the new GridFilterDefinitions row gets created)
        try:
            owner.controller.save_filters_to_db(db_path=owner.controller.db_path)
        except Exception as exc:
            QMessageBox.critical(owner, "Save failed", f"Could not save list filter:\n{exc}")
            return

        QMessageBox.information(
            owner,
            "List filter added",
            f"A list filter for '{local_field}' has been added.",
        )

    @staticmethod
    def update_selected_filter(owner):
        local_field = owner.CB_SelectLocalField.currentText().strip()
        data_index = owner.CB_SelectDataIndex.currentText().strip()
        id_field = owner.LE_InputIDField.text().strip()
        label_field = owner.LE_InputLabelField.text().strip()

        # StoreLocation (DB column Store)
        if hasattr(owner, "LE_InputStoreLocation"):
            store_location = owner.LE_InputStoreLocation.text().strip()
        else:
            store_location = owner.LE_InputStore.text().strip() if hasattr(owner, "LE_InputStore") else ""

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
        if not store_location:
            missing.append("Store Location")
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
        filt = next((f for f in af if f.get("localField") == local_field), None)

        # Back-compat: if anything old slipped in
        if not filt:
            filt = next((f for f in af if f.get("LocalField") == local_field), None)

        if not filt:
            QMessageBox.warning(owner, "Not found", f"No existing filter for '{local_field}' to update.")
            return

        # Update the EXISTING dict using RUNTIME KEYS (the controller saves these)
        filt["localField"] = local_field
        filt["dataIndex"] = data_index
        filt["idField"] = id_field
        filt["labelField"] = label_field
        filt["storeLocation"] = store_location
        filt["storeId"] = store_id
        filt["storeFilter"] = store_filter.strip() or None

        # Clean out DB-style keys if present, stop the “two-key” bug permanently
        for k in ("LocalField", "DataIndex", "IdField", "LabelField", "Store", "StoreId", "StoreFilter"):
            filt.pop(k, None)

        # Model B: persist immediately
        try:
            owner.controller.save_filters_to_db(db_path=owner.controller.db_path)
        except Exception as exc:
            QMessageBox.critical(owner, "Update failed", f"Could not save filter changes:\n{exc}")
            return

        QMessageBox.information(
            owner,
            "List filter updated",
            f"List filter for '{local_field}' has been updated.",
        )

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
