import sqlite3
import yaml
import os


# Helper: get schema columns
def get_table_columns(conn, table_name):
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]

# Load YAML
def load_yaml(yaml_path):
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# Main import logic
def import_yaml_to_db(yaml_data, db_path, layer_name):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Get LayerId
        cursor.execute("SELECT LayerId FROM Layers WHERE Name = ?", (layer_name,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Layer '{layer_name}' not found in Layers table")

        layer_id = row["LayerId"]
        print(f"LayerId for '{layer_name}': {layer_id}")

        # 1. Import mdata
        print("--- Importing mdata ---")
        mdata_schema = get_table_columns(conn, "GridMData")
        mdata_yaml = yaml_data[layer_name].get("mdata", {})

        # Map YAML keys to DB columns
        mdata_map = {
            "id": "IdField",
            "getid": "GetId",
            "service": "Service",
            "window": "Window",
            "model": "Model",
            "help_page": "HelpPage",
            "controller": "Controller",
            "isSwitch": "IsSwitch",
            "isSpatial": "IsSpatial",
            "excel_exporter": "ExcelExporter",
            "shp_exporter": "ShpExporter",
        }

        # Validate keys
        for key in mdata_yaml.keys():
            if key not in mdata_map and key != "editable" and key != "sorters":
                print(f"[mdata] WARNING: Unmapped key in YAML: '{key}'")

        # Determine if any column is editable
        columns_yaml = yaml_data[layer_name].get("columns", {})
        has_editable_columns = any(
            col_data.get("edit", {}).get("editable")
            for col_data in columns_yaml.values()
        )

        # Always insert new row
        insert_mdata_sql = """
        INSERT INTO GridMData
            (LayerId, IdField, GetId, Service, Window, Model, HelpPage, Controller, IsSwitch, IsSpatial, ExcelExporter, ShpExporter, HasEditableColumns)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        cursor.execute(
            insert_mdata_sql,
            (
                layer_id,
                mdata_yaml.get("id"),
                mdata_yaml.get("getid"),
                mdata_yaml.get("service"),
                mdata_yaml.get("window"),
                mdata_yaml.get("model"),
                mdata_yaml.get("help_page"),
                mdata_yaml.get("controller"),
                1 if mdata_yaml.get("isSwitch") else 0,
                1 if mdata_yaml.get("isSpatial") else 0,
                1 if mdata_yaml.get("excel_exporter") else 0,
                1 if mdata_yaml.get("shp_exporter") else 0,
                1 if has_editable_columns else 0,
            ),
        )

        # Import filters
        print("--- Importing filters ---")
        filters_schema = get_table_columns(conn, "GridFilterDefinitions")
        filters_yaml = yaml_data[layer_name].get("filters", [])

        cursor.execute("DELETE FROM GridFilterDefinitions WHERE LayerId = ?", (layer_id,))

        insert_filter_sql = """
        INSERT INTO GridFilterDefinitions
            (LayerId, DataIndex, Store, StoreId, IdField, LabelField, LocalField)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        for filter_entry in filters_yaml:
            filter_data = filter_entry.get("filter", {})
            for key in filter_data.keys():
                if key not in ["data_index", "store", "store_id", "id_field", "label_field", "local_field"]:
                    print(f"[filters] WARNING: Unmapped key in YAML: '{key}'")

            cursor.execute(
                insert_filter_sql,
                (
                    layer_id,
                    filter_data.get("data_index"),
                    filter_data.get("store"),
                    filter_data.get("store_id"),
                    filter_data.get("id_field"),
                    filter_data.get("label_field"),
                    filter_data.get("local_field"),
                ),
            )

        conn.commit()



##########################################################################

        ### 3. Import columns
        print("--- Importing columns ---")
        columns_schema = get_table_columns(conn, "GridColumns")
        column_edit_schema = get_table_columns(conn, "GridColumnEdit")

        columns_yaml = yaml_data[layer_name].get("columns", {})

        # Pre-fetch GridColumnId for each column
        cursor.execute("SELECT GridColumnId, ColumnName FROM GridColumns WHERE LayerId = ?", (layer_id,))
        column_id_map = {r["ColumnName"]: r["GridColumnId"] for r in cursor.fetchall()}

        insert_column_sql = """
        INSERT INTO GridColumns
            (LayerId, ColumnName, Text, Renderer, ExType, InGrid, Hidden, NullText, NullValue, Zeros, NoFilter, Flex, CustomListValues, Editable, IndexValue, YesText, NoText)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        update_column_sql = """
        UPDATE GridColumns SET
            Text = ?,
            Renderer = ?,
            ExType = ?,
            InGrid = ?,
            Hidden = ?,
            NullText = ?,
            NullValue = ?,
            Zeros = ?,
            NoFilter = ?,
            Flex = ?,
            CustomListValues = ?,
            Editable = ?,
            IndexValue = ?,
            YesText = ?,
            NoText = ?
        WHERE GridColumnId = ?
        """

        insert_edit_sql = """
        INSERT OR REPLACE INTO GridColumnEdit
            (GridColumnId, GroupEditIdProperty, GroupEditDataProp, EditServiceUrl, EditUserRole)
        VALUES (?, ?, ?, ?, ?)
        """

        for col_name, col_data in columns_yaml.items():
            grid_column_id = column_id_map.get(col_name)

            # Validate keys
            for key in col_data.keys():
                if key not in ["flex", "inGrid", "hidden", "index", "text", "extype", "renderer", "edit", "customList", "nullText", "nullValue", "zeros", "noFilter", "nulltext", "nullvalue"]:
                    #print(f"[columns] WARNING: Unmapped key in YAML for column '{col_name}': '{key}'")
                    pass

            # Handle renderer/extype fallback logic
            extype = col_data.get("extype")
            renderer = col_data.get("renderer")

            # Case 1: renderer key exists but is null -> use extype
            if "renderer" in col_data and renderer is None:
                renderer = extype

            # Case 2: renderer and extype keys are both missing -> use legacy keys
            if "renderer" not in col_data and "extype" not in col_data:
                legacy_type = col_data.get("type")
                legacy_wfstype = col_data.get("wfstype")
                extype = legacy_type
                if legacy_wfstype:
                    renderer = "number" if legacy_wfstype.lower() == "integer" else legacy_wfstype

            # Save GridColumns
            custom_list_str = ",".join(col_data.get("customList", [])) if "customList" in col_data else ""

            if not grid_column_id:
                # Insert new column
                cursor.execute(
                    insert_column_sql,
                    (
                        layer_id,
                        col_name,
                        col_data.get("text"),
                        renderer,
                        extype,
                        1 if col_data.get("inGrid") else 0,
                        1 if col_data.get("hidden") else 0,
                        col_data.get("nullText") or col_data.get("nulltext"),
                        col_data.get("nullValue") or col_data.get("nullvalue"),
                        col_data.get("zeros"),
                        1 if col_data.get("noFilter") else 0,
                        col_data.get("flex"),
                        custom_list_str,
                        1 if col_data.get("edit", {}).get("editable") else 0,
                        col_data.get("index"),
                        col_data.get("yestext"),
                        col_data.get("notext")
                    ),
                )
                # Get new GridColumnId
                grid_column_id = cursor.lastrowid
                column_id_map[col_name] = grid_column_id
            else:
                # Update existing column
                cursor.execute(
                    update_column_sql,
                    (
                        col_data.get("text"),
                        renderer,
                        extype,
                        1 if col_data.get("inGrid") else 0,
                        1 if col_data.get("hidden") else 0,
                        col_data.get("nullText") or col_data.get("nulltext"),
                        col_data.get("nullValue") or col_data.get("nullvalue"),
                        col_data.get("zeros"),
                        1 if col_data.get("noFilter") else 0,
                        col_data.get("flex"),
                        custom_list_str,
                        1 if col_data.get("edit", {}).get("editable") else 0,
                        col_data.get("index"),
                        col_data.get("yestext"),
                        col_data.get("notext"),
                        grid_column_id,
                    ),
                )

            # Save GridColumnEdit if edit section present AND editable == True
            if "edit" in col_data:
                edit_data = col_data["edit"]

                if edit_data.get("editable"):
                    for key in edit_data.keys():
                        if key not in ["groupEditIdProperty", "groupEditDataProp", "editServiceUrl", "editUserRole", "editable"]:
                            print(f"[column_edit] WARNING: Unmapped key in YAML for column '{col_name}': '{key}'")

                    cursor.execute(
                        insert_edit_sql,
                        (
                            grid_column_id,
                            edit_data.get("groupEditIdProperty"),
                            edit_data.get("groupEditDataProp"),
                            edit_data.get("editServiceUrl"),
                            edit_data.get("editUserRole"),
                        ),
                    )

###########################################################################

        ### 4. Import sorters
        print("--- Importing sorters ---")
        sorters_schema = get_table_columns(conn, "GridSorters")

        # Clear existing sorters
        cursor.execute("DELETE FROM GridSorters WHERE LayerId = ?", (layer_id,))

        sorters_yaml = mdata_yaml.get("sorters", [])
        insert_sorter_sql = """
        INSERT INTO GridSorters (LayerId, Property, Direction, SortOrder)
        VALUES (?, ?, ?, ?)
        """

        for order_index, sorter_entry in enumerate(sorters_yaml):
            sorter_data = sorter_entry.get("sorter", {})

            for key in sorter_data.keys():
                if key not in ["field", "direction"]:
                    print(f"[sorters] WARNING: Unmapped key in YAML: '{key}'")

            cursor.execute(
                insert_sorter_sql,
                (
                    layer_id,
                    sorter_data.get("field"),
                    sorter_data.get("direction"),
                    order_index,
                ),
            )

        ### Commit all changes
        conn.commit()
        print("--- Import complete ---")

    except Exception as e:
        print(f"ERROR during import: {str(e)}")
        conn.rollback()

    finally:
        conn.close()

if __name__ == "__main__":
    GRID_YAMLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app2", "grid_yamls"))
    DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Database", "MapMakerDB.db"))
    # Clear Grid tables and reset sequences once before starting import
    print("--- Clearing all Grid... tables before import ---")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    tables_to_clear = [
        "GridColumnEdit",
        "GridColumns",
        "GridFilterDefinitions",
        "GridMData",
        "GridSorters"
    ]
    for table in tables_to_clear:
        cursor.execute(f"DELETE FROM {table}")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
    conn.commit()
    conn.close()

    # Import each YAML layer
    for filename in os.listdir(GRID_YAMLS_DIR):
        if filename.endswith(".yaml"):
            yaml_path = os.path.join(GRID_YAMLS_DIR, filename)
            yaml_data = load_yaml(yaml_path)
            layer_name = list(yaml_data.keys())[0]

            # Check if layer exists in Layers table
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM Layers WHERE Name = ?", (layer_name,))
            exists = cursor.fetchone()[0] > 0
            conn.close()

            if not exists:
                print(f"Skipping '{layer_name}': not found in Layers table")
                continue

            print(f"--- Importing layer '{layer_name}' from '{filename}' ---")
            import_yaml_to_db(yaml_data, DB_PATH, layer_name)



