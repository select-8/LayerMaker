import os
import sys
import yaml
import pprint
import traceback
import logging
import sqlite3

# Ensure project root is importable when running as a script
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt5 import QtCore, QtWidgets
from main_window import MainWindowUIClass
from app2 import settings

logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=4)


class Controller(QtCore.QObject):
    # Signals to communicate with the UI
    data_updated = QtCore.pyqtSignal(dict)
    filter_selected = QtCore.pyqtSignal(dict)
    #mapfile_layer_selected = QtCore.pyqtSignal(dict)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        # Internal state tracking
        self.active_mdata = dict()
        self.active_columns = list()
        self.active_layer = str()
        self.active_id = str()
        self.columns_with_data = dict()
        self.saved_columns = dict()
        self.active_filters = list()
        self._display_order_map = {} 

        # Set project paths
        self.project_directory = os.path.dirname(os.path.abspath(__file__))
        self.config_dir = os.path.join(self.project_directory, "configs")

        # Specific config files
        self.unitMappings = os.path.join(self.config_dir, "unitMappings.yaml")

        # External paths (normalized for cross-platform)
        self.pms_maps_folder = os.fspath(settings.PMS_MAPS_DIR)
        print('')
        print('self.pms_maps_folder:', self.pms_maps_folder)
        self.js_root_folder = os.fspath(settings.PMS_JS_ROOT)
        print('self.js_root_folder:', self.js_root_folder)
        print('')
        self.mapfiles_dir = os.fspath(settings.MAPFILES_DIR)

        self.current_file = ""
        self.db_path = os.path.abspath(os.path.join(self.project_directory, "..", "Database", "MapMakerDB.db"))

    def read_layer_from_db(self, layer_name, db_path):
        """
        Load columns, mdata, filters, and sorters for the given layer from the database.
        Updated to support normalized filters (shared definitions).
        """
        self.active_layer = layer_name

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Lookup LayerId
            cursor.execute("SELECT LayerId FROM Layers WHERE Name = ?", (self.active_layer,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Layer '{self.active_layer}' not found in Layers table")

            layer_id = row["LayerId"]

            # Load columns with Renderer and ExType
            cursor.execute("""
                SELECT
                    gc.*,
                    gcr.Renderer AS Renderer,
                    gcr.ExType AS ExType,
                    gfd.GridFilterDefinitionId,
                    gfd.Store, gfd.StoreId, gfd.IdField, gfd.LabelField, gfd.LocalField, gfd.DataIndex
                FROM GridColumns gc
                LEFT JOIN GridColumnRenderers gcr 
                    ON gc.GridColumnRendererId = gcr.GridColumnRendererId
                LEFT JOIN GridFilterDefinitions gfd
                    ON gc.GridFilterDefinitionId = gfd.GridFilterDefinitionId
                WHERE gc.LayerId = ?
                ORDER BY
                CASE WHEN gc.DisplayOrder IS NULL THEN 1 ELSE 0 END,  -- nulls last
                gc.DisplayOrder,
                gc.GridColumnId
            """, (layer_id,))

            self.saved_columns = {}
            filters = []
            for row in cursor.fetchall():
                
                col = {
                    "text": row["Text"],
                    "displayOrder": row["DisplayOrder"],
                    "renderer": row["Renderer"] or "string",
                    "exType": row["ExType"] or "string",
                    "GridColumnRendererId": row["GridColumnRendererId"],
                    "inGrid": bool(row["InGrid"]),
                    "hidden": bool(row["Hidden"]),
                    "nullText": row["NullText"],
                    "nullValue": row["NullValue"],
                    "zeros": row["Zeros"],
                    "noFilter": bool(row["NoFilter"]),
                    "filterType": row["FilterType"],
                    "flex": row["Flex"],
                    "customList": row["CustomListValues"].split(",") if row["CustomListValues"] else [],
                    "edit": None,
                }

                # Attach edit metadata
                cursor.execute("SELECT * FROM GridColumnEdit WHERE GridColumnId = ?", (row["GridColumnId"],))
                edit_row = cursor.fetchone()
                if edit_row:
                    # Fetch role name via FK
                    role_name = None
                    if edit_row["EditorRoleId"]:
                        cursor.execute("SELECT RoleName FROM EditorRoles WHERE EditorRoleId = ?", 
                                       (edit_row["EditorRoleId"],))
                        role_result = cursor.fetchone()
                        if role_result:
                            role_name = role_result["RoleName"]

                    col["edit"] = {
                        "groupEditIdProperty": edit_row["GroupEditIdProperty"],
                        "groupEditDataProp": edit_row["GroupEditDataProp"],
                        "editServiceUrl": edit_row["EditServiceUrl"],
                        "editUserRole": role_name,
                        "editable": True,
                    }


                self.saved_columns[row["ColumnName"]] = col

                # Attach filter (if exists)
                if row["GridFilterDefinitionId"]:
                    filters.append({
                        "dataIndex": row["DataIndex"],
                        "store": row["Store"],
                        "storeId": row["StoreId"],
                        "idField": row["IdField"],
                        "labelField": row["LabelField"],
                        "localField": row["LocalField"],
                        "columnName": row["ColumnName"]
                    })

            # Load mdata
            cursor.execute("SELECT * FROM GridMData WHERE LayerId = ?", (layer_id,))
            mdata_row = cursor.fetchone()
            mdata = {key: mdata_row[key] for key in mdata_row.keys()} if mdata_row else {}

            # print('Filters From DB')
            # pp.pprint(filters)

            # Load sorters
            cursor.execute("SELECT * FROM GridSorters WHERE LayerId = ? ORDER BY SortOrder", (layer_id,))
            self.active_sorters = [
                {
                    "dataIndex": row["Property"],
                    "sortDirection": row["Direction"],
                    "sortOrder": row["SortOrder"],
                }
                for row in cursor.fetchall()
            ]

            return {
                "status": "loaded",
                "active_layer": self.active_layer,
                "columns": self.saved_columns,
                "mdata": mdata,
                "active_filters": filters,
            }
        finally:
            conn.close()

    def read_db(self, layer_name):
        """Load layer definition from sqlite DB, update internal state, and notify UI."""
        try:
            # Path to your DB (adjust if needed)
            db_path = os.path.join(self.project_directory, "..", "Database", "MapMakerDB.db")

            # Call our new loader
            result = self.read_layer_from_db(layer_name, db_path)

            # Update controller state
            self.current_file = ""  # Optional: clear current YAML file
            self.active_layer = result["active_layer"]
            self.active_mdata = result["mdata"]
            self.columns_with_data = result["columns"]
            self.active_columns = list(self.columns_with_data.keys())
            self.active_filters = result["active_filters"]

            # for f in self.active_filters:
            #     print(f)

            # Notify UI
            self.data_updated.emit(result)

        except Exception as e:
            logger.exception("Error loading layer from DB")
            self.data_updated.emit({
                "status": "error",
                "error": str(e),
            })

    def save_layer_atomic(self, db_path):
        """
        Save filters, columns, and metadata in a single transaction.
        If any step fails, nothing is written.
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:  # atomic commit/rollback
                # Call the refactored versions that accept an existing connection
                self.save_sorters_to_db(conn=conn)
                self.save_filters_to_db(conn=conn)
                self.save_columns_to_db(conn=conn)
                self.save_mdata_to_db(conn=conn)
            print("Layer saved atomically.")
        finally:
            conn.close()

    def get_column_names(self):
        """Return a list of available column names."""
        return list(self.columns_with_data.keys())

    def get_column_data(self, column_name):
        """Return configuration data for a specific column."""
        return self.columns_with_data.get(column_name, {})

    def update_display_order_from_ui(self, ordered_names):
        """
        Accept the current visual order of columns (list of ColumnName strings)
        and keep a 1-based mapping for saving.
        """
        if not ordered_names:
            self._display_order_map = {}
            return
        self._display_order_map = {name: idx + 1 for idx, name in enumerate(ordered_names)}


    def update_column_data(self, column_name, new_data):
        """Apply UI changes to a column configuration."""
        try:
            if column_name in self.columns_with_data:
                self.columns_with_data[column_name].update(new_data)
                # Ensure customList is explicitly updated to avoid stale UI state
                self.columns_with_data[column_name]["customList"] = new_data.get("customList", [])
                self.saved_columns[column_name] = new_data
                return True
            return False
        except Exception:
            logger.exception("Data update error")
            return False

    def add_filter(self, new_filter):
        """Add a filter to the active list if it's not a duplicate."""
        existing = {f["localField"] for f in self.active_filters}
        if new_filter["localField"] not in existing:
            self.active_filters.append(new_filter)

        self.data_updated.emit({
            "status": "filter_added",
            "active_filters": self.active_filters,
        })

    def delete_filter_by_local_field(self, field_name):
        """Remove a filter by its local field name."""
        before = len(self.active_filters)

        self.active_filters = [
            f for f in self.active_filters if f["localField"] != field_name
        ]
        after = len(self.active_filters)

        if before != after:
            if hasattr(self.main_window, "_update_active_mdata_from_ui"):
                self.main_window._update_active_mdata_from_ui()

            self.data_updated.emit({
                "status": "filter_deleted",
                "active_filters": self.active_filters,
            })

    def update_filter(self, original_field, new_filter):
        """Update an existing filter's definition."""
        updated = False
        for idx, f in enumerate(self.active_filters):
            if f["localField"] == original_field:
                self.active_filters[idx] = new_filter
                updated = True
                break

        if updated:
            if hasattr(self.main_window, "_update_active_mdata_from_ui"):
                self.main_window._update_active_mdata_from_ui()

            self.data_updated.emit({
                "status": "filter_updated",
                "active_filters": self.active_filters,
            })

    def select_filter(self, filter_name):
        """Trigger UI population for a selected filter."""
        for filter_data in self.active_filters:
            if filter_data["localField"] == filter_name:
                logger.debug(f"Emitting filter_selected for: {filter_name}")
                self.filter_selected.emit(filter_data)
                break

    def save_mdata_to_db(self, db_path=None, conn=None):
        """
        Save the current active_mdata to the GridMData table in the database.
        """
        manage_conn = conn is None
        if manage_conn:
            if not db_path:
                raise ValueError("db_path is required when no connection is provided")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()

        print(f"mdata keys: {sorted(self.active_mdata.keys())}")

        try:
            # Lookup LayerId
            cursor.execute("SELECT LayerId FROM Layers WHERE Name = ?", (self.active_layer,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Layer '{self.active_layer}' not found in Layers table")

            layer_id = row["LayerId"]

            # Build update statement
            update_sql = """
            UPDATE GridMData SET
                Window = ?,
                Model = ?,
                HelpPage = ?,
                Controller = ?,
                Service = ?,
                IdField = ?,
                GetId = ?,
                IsSpatial = ?,
                ExcelExporter = ?,
                ShpExporter = ?,
                IsSwitch = ?
            WHERE LayerId = ?
            """

            cursor.execute(
                update_sql,
                (
                self.active_mdata.get("Window"),
                self.active_mdata.get("Model"),
                self.active_mdata.get("HelpPage"),
                self.active_mdata.get("Controller"),
                self.active_mdata.get("Service"),
                self.active_mdata.get("IdField"),
                self.active_mdata.get("GetId"),
                1 if self.active_mdata.get("IsSpatial") else 0,
                1 if self.active_mdata.get("ExcelExporter") else 0,
                1 if self.active_mdata.get("ShpExporter") else 0,
                1 if self.active_mdata.get("IsSwitch") else 0,
                layer_id,
            ),
            )
            if manage_conn:
                conn.commit()
                print(f"Saved mdata for layer '{self.active_layer}' to DB.")

        finally:
            if manage_conn:
                conn.close()

    def save_sorters_to_db(self, db_path=None, conn=None):
        """
        Save the current active_sorters to the GridSorters table in the database.
        """
        manage_conn = conn is None
        if manage_conn:
            if not db_path:
                raise ValueError("db_path is required when no connection is provided")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()

        try:
            # Lookup LayerId
            cursor.execute("SELECT LayerId FROM Layers WHERE Name = ?", (self.active_layer,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Layer '{self.active_layer}' not found in Layers table")

            layer_id = row["LayerId"]

            # Clear existing sorters for this layer
            cursor.execute("DELETE FROM GridSorters WHERE LayerId = ?", (layer_id,))

            # Insert current sorters
            insert_sql = """
            INSERT INTO GridSorters (LayerId, Property, Direction, SortOrder)
            VALUES (?, ?, ?, ?)
            """

            for sorter in self.active_sorters:
                cursor.execute(
                    insert_sql,
                    (
                        layer_id,
                        sorter["dataIndex"],
                        sorter["sortDirection"],
                        sorter["sortOrder"],
                    ),
                )
            if manage_conn:
                conn.commit()
                print(f"Saved {len(self.active_sorters)} sorters for layer '{self.active_layer}' to DB.")

        finally:
            if manage_conn:
                conn.close()

    def save_filters_to_db(self, db_path=None, conn=None):
        """
        Persist active_filters to GridFilterDefinitions and link/unlink GridColumns.
        - Upsert each active filter definition.
        - Link columns by ColumnName == localField.
        - Unlink any columns in this layer whose localField was removed.
        - (Optional) Garbage-collect orphaned GridFilterDefinitions.
        """
        manage_conn = conn is None
        if manage_conn:
            if not db_path:
                raise ValueError("db_path is required when no connection is provided")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()

        try:
            # 0) LayerId
            cursor.execute("SELECT LayerId FROM Layers WHERE Name = ?", (self.active_layer,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Layer '{self.active_layer}' not found in Layers table")
            layer_id = row["LayerId"]

            # 1) Active localFields (what should remain linked after this save)
            active_local_fields = {
                f["localField"] for f in self.active_filters if f.get("localField")
            }

            # 2) Upsert + link by localField (ColumnName)
            for fdef in self.active_filters:
                params = (
                    fdef["dataIndex"],
                    fdef["store"],
                    fdef["storeId"],
                    fdef["idField"],
                    fdef["labelField"],
                    fdef["localField"],
                )

                # Insert definition if it doesn't exist
                cursor.execute("""
                    INSERT INTO GridFilterDefinitions (DataIndex, Store, StoreId, IdField, LabelField, LocalField)
                    SELECT ?, ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM GridFilterDefinitions
                        WHERE DataIndex = ? AND Store = ? AND StoreId = ?
                          AND IdField = ? AND LabelField = ? AND LocalField = ?
                    )
                """, params + params)

                # Link column to the (existing/new) definition using localField
                cursor.execute("""
                    UPDATE GridColumns
                    SET GridFilterDefinitionId = (
                        SELECT GridFilterDefinitionId FROM GridFilterDefinitions
                        WHERE DataIndex = ? AND Store = ? AND StoreId = ?
                          AND IdField = ? AND LabelField = ? AND LocalField = ?
                    )
                    WHERE LayerId = ? AND ColumnName = ?
                """, params + (layer_id, fdef["localField"]))

            # 3) Unlink columns whose filter was removed this session
            if active_local_fields:
                placeholders = ",".join("?" * len(active_local_fields))
                cursor.execute(f"""
                    UPDATE GridColumns
                    SET GridFilterDefinitionId = NULL
                    WHERE LayerId = ?
                      AND GridFilterDefinitionId IS NOT NULL
                      AND ColumnName NOT IN ({placeholders})
                """, (layer_id, *active_local_fields))
            else:
                # No filters left, clear all links for this layer
                cursor.execute("""
                    UPDATE GridColumns
                    SET GridFilterDefinitionId = NULL
                    WHERE LayerId = ? AND GridFilterDefinitionId IS NOT NULL
                """, (layer_id,))

            # 4) Optional GC: remove orphaned filter definitions (unused anywhere)
            cursor.execute("""
                DELETE FROM GridFilterDefinitions
                WHERE GridFilterDefinitionId NOT IN (
                    SELECT DISTINCT GridFilterDefinitionId
                    FROM GridColumns
                    WHERE GridFilterDefinitionId IS NOT NULL
                )
            """)
            if manage_conn:
                conn.commit()
                print(f"Saved {len(self.active_filters)} filters for layer '{self.active_layer}' to DB.")
        finally:
            if manage_conn:
                conn.close()

    def save_columns_to_db(self, db_path=None, conn=None):
        """
        Save the current saved_columns to the GridColumns and GridColumnEdit tables.
        - Prefer GridColumnRendererId coming from the UI payload.
        - Fall back to resolving renderer by text if no ID provided.
        - If a GridFilterDefinitionId is present, force FilterType = 'list'.
        - If present in schema: set IndexValue = ColumnName (and update ExType/Renderer text).
        """
        manage_conn = conn is None
        if manage_conn:
            if not db_path:
                raise ValueError("db_path is required when no connection is provided")
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
        cursor = conn.cursor()

        try:
            # LayerId
            cursor.execute("SELECT LayerId FROM Layers WHERE Name = ?", (self.active_layer,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Layer '{self.active_layer}' not found in Layers table")
            layer_id = row["LayerId"]

            # Pre-fetch column ids
            cursor.execute("SELECT GridColumnId, ColumnName FROM GridColumns WHERE LayerId = ?", (layer_id,))
            column_id_map = {r["ColumnName"]: r["GridColumnId"] for r in cursor.fetchall()}

            # Detect optional columns on GridColumns
            cursor.execute("PRAGMA table_info(GridColumns)")
            gc_cols = {r["name"] for r in cursor.fetchall()}
            has_indexvalue = "IndexValue" in gc_cols
            has_extype     = "ExType" in gc_cols
            has_renderer_t = "Renderer" in gc_cols  # textual renderer column (if exists)
            has_displayord = "DisplayOrder" in gc_cols

            # ---- persist DisplayOrder from the UI list ----
            if has_displayord and getattr(self, "_display_order_map", None):
                # Update every column present in the map. Unlisted columns (if any) are pushed to the end
                # in their current order by assigning a high DisplayOrder so new ones append behind.
                # Primary path: update those we received from UI.
                for col_name, disp in self._display_order_map.items():
                    gcid = column_id_map.get(col_name)
                    if gcid:
                        cursor.execute(
                            "UPDATE GridColumns SET DisplayOrder = ? WHERE GridColumnId = ?",
                            (int(disp), gcid)
                        )

            for col_name, col_data in self.saved_columns.items():
                grid_column_id = column_id_map.get(col_name)
                if not grid_column_id:
                    print(f"Warning: Column '{col_name}' not found in GridColumns for this layer. Skipping.")
                    continue

                # Custom list CSV
                custom_list = col_data.get("customList")
                custom_list_str = ",".join(custom_list) if custom_list else None

                # --- Determine renderer id + filter type ---
                # Prefer payload
                renderer_id = col_data.get("GridColumnRendererId")
                filter_type = (col_data.get("filterType") or col_data.get("exType"))

                # Fallback: resolve by renderer string like before
                if renderer_id is None:
                    renderer_txt = (col_data.get("renderer") or "").strip()
                    if renderer_txt:
                        normalized = renderer_txt.lower()
                        cursor.execute("""
                            SELECT GridColumnRendererId, ExType
                            FROM GridColumnRenderers
                            WHERE LOWER(TRIM(Renderer)) = ?
                            LIMIT 1
                        """, (normalized,))
                        match = cursor.fetchone()
                        if match:
                            renderer_id = match["GridColumnRendererId"]
                            # If UI didn't provide a filter type, derive from renderer ExType
                            if not filter_type:
                                filter_type = match["ExType"]
                        else:
                            print(f"Warning: No GridColumnRendererId found for renderer '{renderer_txt}'")

                # If editable and no filter type yet, assume 'list'
                if not filter_type and col_data.get("edit", {}).get("editable"):
                    filter_type = "list"

                # Preserve existing GridFilterDefinitionId unless explicitly cleared by UI
                cursor.execute("SELECT GridFilterDefinitionId FROM GridColumns WHERE GridColumnId = ?", (grid_column_id,))
                existing_filter_row = cursor.fetchone()
                existing_filter_id = existing_filter_row["GridFilterDefinitionId"] if existing_filter_row else None
                if existing_filter_id and col_data.get("GridFilterDefinitionId") is None:
                    col_data["GridFilterDefinitionId"] = existing_filter_id

                # If it has a filter definition, coerce FilterType='list'
                if col_data.get("GridFilterDefinitionId") and (filter_type or "").lower() != "list":
                    filter_type = "list"

                # Determine if we must clear the link (non-list types cannot hold a definition)
                clear_filter_id = (filter_type or "").lower() != "list"

                # --- Build dynamic UPDATE (include optional fields if they exist) ---
                update_fields = {
                    "Text": col_data.get("text"),
                    "InGrid": 1 if col_data.get("inGrid") else 0,
                    "Hidden": 1 if col_data.get("hidden") else 0,
                    "NullText": col_data.get("nullText"),
                    "NullValue": col_data.get("nullValue"),
                    "Zeros": col_data.get("zeros"),
                    "NoFilter": 1 if col_data.get("noFilter") else 0,
                    "Flex": col_data.get("flex"),
                    "CustomListValues": custom_list_str,
                    "Editable": col_data.get("edit", {}).get("editable"),
                    "FilterType": filter_type,
                    "GridColumnRendererId": renderer_id,
                    "GridFilterDefinitionId": None if clear_filter_id else col_data.get("GridFilterDefinitionId"),
                }

                # Optional columns, only if present in DB schema
                if has_indexvalue:
                    update_fields["IndexValue"] = col_name
                if has_extype:
                    update_fields["ExType"] = (col_data.get("exType") or "").strip() or None
                if has_renderer_t:
                    update_fields["Renderer"] = (col_data.get("renderer") or "").strip() or None

                set_sql = ", ".join(f"{k} = ?" for k in update_fields.keys())
                params = list(update_fields.values()) + [grid_column_id]

                cursor.execute(f"""
                    UPDATE GridColumns SET
                        {set_sql}
                    WHERE GridColumnId = ?
                """, params)

                # --- GridColumnEdit upsert/cleanup ---
                cursor.execute("SELECT GridColumnEditId FROM GridColumnEdit WHERE GridColumnId = ?", (grid_column_id,))
                row = cursor.fetchone()

                edit_data = col_data.get("edit")
                if edit_data and edit_data.get("editable"):
                    role_name = edit_data.get("editUserRole")
                    editor_role_id = None
                    if role_name:
                        cursor.execute("SELECT EditorRoleId FROM EditorRoles WHERE RoleName = ?", (role_name,))
                        role_row = cursor.fetchone()
                        if role_row:
                            editor_role_id = role_row["EditorRoleId"]

                    if row:
                        cursor.execute("""
                            UPDATE GridColumnEdit SET
                                GroupEditIdProperty = ?,
                                GroupEditDataProp = ?,
                                EditServiceUrl = ?,
                                EditorRoleId = ?
                            WHERE GridColumnId = ?
                        """, (
                            edit_data.get("groupEditIdProperty"),
                            edit_data.get("groupEditDataProp"),
                            edit_data.get("editServiceUrl"),
                            editor_role_id,
                            grid_column_id,
                        ))
                    else:
                        cursor.execute("""
                            INSERT INTO GridColumnEdit
                                (GridColumnId, GroupEditIdProperty, GroupEditDataProp, EditServiceUrl, EditorRoleId)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            grid_column_id,
                            edit_data.get("groupEditIdProperty"),
                            edit_data.get("groupEditDataProp"),
                            edit_data.get("editServiceUrl"),
                            editor_role_id,
                        ))
                else:
                    if row:
                        cursor.execute("DELETE FROM GridColumnEdit WHERE GridColumnId = ?", (grid_column_id,))

            if manage_conn:
                conn.commit()
                print(f"Saved {len(self.saved_columns)} columns for layer '{self.active_layer}' to DB.")
        finally:
            if manage_conn:
                conn.close()


def main():
    """Application entry point: initializes and shows the main window."""
    import sys

    logging.basicConfig(level=logging.DEBUG)

    app = QtWidgets.QApplication(sys.argv)
    controller = Controller(None)
    main_window = MainWindowUIClass(controller)
    controller.main_window = main_window

    main_window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
