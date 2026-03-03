import os
import sys
import yaml
import pprint
import traceback
import logging
import sqlite3
from wfs_to_db import WFSToDB
# import settings  # redundant - superseded by 'from app2 import settings' below
from PyQt5.QtGui import QFont

# Ensure project root is importable when running as a script
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PyQt5 import QtCore, QtWidgets
from app2.main_window import MainWindowUIClass
from app2 import settings

logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=4)

# --- Filter type helper ---
FILTER_CODES = {
    "string",
    "number",
    "boolean",
    "date",
    "list",
    "custom_list",
    "number_no_eq",
    "float",
    "float_no_eq",
}


def _lookup_filter_type_id(conn, code: str) -> int:
    code = (code or "").strip().lower()
    if code not in FILTER_CODES:
        raise ValueError(f"Unknown GridFilterTypes.Code: {code}")
    cur = conn.execute(
        "SELECT GridFilterTypeId FROM GridFilterTypes WHERE Code = ?",
        (code,)
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"GridFilterTypes not seeded with code: {code}")
    return int(row[0])


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

        # TODO, use settings.py instead of hardcoding DB path
        self.db_path = os.path.abspath(os.path.join(self.project_directory, "..", "Database", "MapMakerDB.db"))

    def read_layer_from_db(self, layer_name, db_path):
        """
        Load columns, mdata, filters, and sorters for the given layer from the database.
        Updated to support normalized filters (shared definitions).
        Includes GridFilterDefinitions.StoreFilter (optional).

        Runtime filter dict keys (code keys):
          localField, dataIndex, idField, labelField, storeLocation, storeId, storeFilter, columnName
        """
        import sqlite3

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

            # Load columns + join filter defs/types
            cursor.execute("""
                SELECT
                    gc.*,
                    gcr.Renderer AS Renderer,
                    gcr.ExType AS ExType,
                    gfd.GridFilterDefinitionId,
                    gfd.Store, gfd.StoreId, gfd.IdField, gfd.LabelField, gfd.LocalField, gfd.DataIndex,
                    gfd.StoreFilter,
                    gft.GridFilterTypeId,
                    gft.Code AS FilterTypeCode
                FROM GridColumns gc
                LEFT JOIN GridColumnRenderers gcr 
                    ON gc.GridColumnRendererId = gcr.GridColumnRendererId
                LEFT JOIN GridFilterDefinitions gfd
                    ON gc.GridFilterDefinitionId = gfd.GridFilterDefinitionId
                LEFT JOIN GridFilterTypes gft
                    ON gft.GridFilterTypeId = gc.GridFilterTypeId
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
                    "filterType": (row["FilterTypeCode"] or row["ExType"] or "string"),
                    "filterTypeId": row["GridFilterTypeId"],
                    "flex": row["Flex"],
                    "customList": row["CustomListValues"].split(",") if row["CustomListValues"] else [],
                    "edit": None,
                }

                # Attach edit metadata
                cursor.execute("SELECT * FROM GridColumnEdit WHERE GridColumnId = ?", (row["GridColumnId"],))
                edit_row = cursor.fetchone()
                is_editable = bool(row["Editable"])
                if edit_row:
                    # Fetch role name via FK
                    role_name = None
                    if edit_row["EditorRoleId"]:
                        cursor.execute(
                            "SELECT RoleName FROM EditorRoles WHERE EditorRoleId = ?",
                            (edit_row["EditorRoleId"],)
                        )
                        role_result = cursor.fetchone()
                        if role_result:
                            role_name = role_result["RoleName"]

                    col["edit"] = {
                        "groupEditIdProperty": edit_row["GroupEditIdProperty"],
                        "groupEditDataProp": edit_row["GroupEditDataProp"],
                        "editServiceUrl": edit_row["EditServiceUrl"],
                        "editUserRole": role_name,
                        "editable": is_editable,
                    }

                self.saved_columns[row["ColumnName"]] = col

                # Attach filter (if exists)
                if row["GridFilterDefinitionId"]:
                    filters.append({
                        "localField": row["LocalField"],
                        "dataIndex": row["DataIndex"],
                        "idField": row["IdField"],
                        "labelField": row["LabelField"],
                        "storeLocation": row["Store"],      # DB Store -> storeLocation
                        "storeId": row["StoreId"],
                        "storeFilter": row["StoreFilter"],  # optional
                        "columnName": row["ColumnName"],
                    })

            # Load mdata
            cursor.execute("SELECT * FROM GridMData WHERE LayerId = ?", (layer_id,))
            mdata_row = cursor.fetchone()
            mdata = {key: mdata_row[key] for key in mdata_row.keys()} if mdata_row else {}

            # Load sorters
            cursor.execute("SELECT * FROM GridSorters WHERE LayerId = ? ORDER BY SortOrder", (layer_id,))
            self.active_sorters = [
                {
                    "dataIndex": r["Property"],
                    "sortDirection": r["Direction"],
                    "sortOrder": r["SortOrder"],
                }
                for r in cursor.fetchall()
            ]

            # Keep controller state consistent
            self.active_filters = filters

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
                self.save_columns_to_db(conn=conn)
                self.save_filters_to_db(conn=conn)
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

    def add_missing_columns_for_layer(self, layer_name: str):
        """
        Use WFSToDB.sync_new_columns to add any new WFS fields for this layer
        into GridColumns. Returns the list of column names added.
        """
        name = (layer_name or "").strip()
        if not name:
            raise ValueError("Layer name is empty in add_missing_columns_for_layer")

        wfs_url = settings.WFS_URL
        importer = WFSToDB(
            self.db_path,
            wfs_url,
            timeout=getattr(settings, "WFS_READ_TIMEOUT", 180),
            connect_timeout=getattr(settings, "WFS_CONNECT_TIMEOUT", 45),
            retries=getattr(settings, "WFS_RETRY_ATTEMPTS", 3),
            backoff_factor=getattr(settings, "WFS_RETRY_BACKOFF", 1.5),
        )
        added = importer.sync_new_columns(name)
        logging.getLogger(__name__).info(
            "[SYNC] add_missing_columns_for_layer(%s) added: %s", name, added
        )
        return added

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
                # Merge UI changes into in-memory state
                self.columns_with_data[column_name].update(new_data)
                # Keep customList explicitly in sync (empty list means "no custom list")
                self.columns_with_data[column_name]["customList"] = new_data.get("customList", [])

                # saved_columns should always hold the full, merged state for DB saves
                self.saved_columns[column_name] = dict(self.columns_with_data[column_name])
                return True
            return False
        except Exception:
            logger.exception("Data update error")
            return False

    def add_filter(self, new_filter: dict):
        """
        Add a new filter to active_filters.
        Accepts either runtime code keys OR DB-style keys, but stores only runtime code keys:
          localField, dataIndex, idField, labelField, storeLocation, storeId, storeFilter (optional)
        """
        if not isinstance(new_filter, dict):
            return False

        # Normalize DB-style keys to runtime keys if needed
        if ("LocalField" in new_filter) or ("DataIndex" in new_filter) or ("StoreId" in new_filter) or ("StoreFilter" in new_filter):
            new_filter = {
                "localField": (new_filter.get("LocalField") or "").strip(),
                "dataIndex": (new_filter.get("DataIndex") or "").strip(),
                "idField": (new_filter.get("IdField") or "").strip(),
                "labelField": (new_filter.get("LabelField") or "").strip(),
                "storeLocation": (new_filter.get("Store") or "").strip(),
                "storeId": (new_filter.get("StoreId") or "").strip(),
                "storeFilter": (new_filter.get("StoreFilter") or "").strip() or None,
            }
        else:
            # Runtime keys path
            new_filter = {
                "localField": (new_filter.get("localField") or "").strip(),
                "dataIndex": (new_filter.get("dataIndex") or "").strip(),
                "idField": (new_filter.get("idField") or "").strip(),
                "labelField": (new_filter.get("labelField") or "").strip(),
                "storeLocation": (new_filter.get("storeLocation") or "").strip(),
                "storeId": (new_filter.get("storeId") or "").strip(),
                "storeFilter": (new_filter.get("storeFilter") or "").strip() or None,
            }

        local_field = new_filter.get("localField")
        if not local_field:
            return False

        # Ensure list exists
        if not hasattr(self, "active_filters") or self.active_filters is None:
            self.active_filters = []

        existing = {f.get("localField") for f in self.active_filters if f.get("localField")}
        if local_field in existing:
            return False

        self.active_filters.append(new_filter)
        return True

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

            return True

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

    def save_filters_to_db(self, db_path=None, conn=None):
        """
        Persist active_filters to GridFilterDefinitions and link/unlink GridColumns.

        Runtime keys expected in self.active_filters:
          localField, dataIndex, idField, labelField, storeLocation, storeId, storeFilter (optional)

        DB columns:
          DataIndex, Store, StoreId, IdField, LabelField, LocalField, StoreFilter
        """
        import sqlite3

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

            # Ensure controller has filters list
            active_filters = getattr(self, "active_filters", []) or []

            # 1) Active localFields (what should remain linked after this save)
            active_local_fields = {f.get("localField") for f in active_filters if f.get("localField")}

            # 2) Upsert + link by localField (ColumnName)
            for fdef in active_filters:
                store_filter = (fdef.get("storeFilter") or "").strip()
                store_filter = store_filter if store_filter else None

                # Required keys (fail fast with a readable error)
                required = ["dataIndex", "idField", "labelField", "localField", "storeLocation", "storeId"]
                missing = [k for k in required if not (fdef.get(k) or "").strip()]
                if missing:
                    raise ValueError(f"Filter missing required keys {missing}: {fdef}")

                params = (
                    fdef["dataIndex"],
                    fdef["storeLocation"],  # -> DB Store
                    fdef["storeId"],        # -> DB StoreId
                    fdef["idField"],
                    fdef["labelField"],
                    fdef["localField"],
                    store_filter,           # -> DB StoreFilter (optional)
                )

                # Insert definition if it doesn't exist (StoreFilter is part of identity)
                cursor.execute("""
                    INSERT INTO GridFilterDefinitions
                        (DataIndex, Store, StoreId, IdField, LabelField, LocalField, StoreFilter)
                    SELECT ?, ?, ?, ?, ?, ?, ?
                    WHERE NOT EXISTS (
                        SELECT 1 FROM GridFilterDefinitions
                        WHERE DataIndex = ? AND Store = ? AND StoreId = ?
                          AND IdField = ? AND LabelField = ? AND LocalField = ?
                          AND COALESCE(StoreFilter, '') = COALESCE(?, '')
                    )
                """, params + params)

                # Link column to the (existing/new) definition using localField (ColumnName)
                cursor.execute("""
                    UPDATE GridColumns
                    SET GridFilterDefinitionId = (
                        SELECT GridFilterDefinitionId FROM GridFilterDefinitions
                        WHERE DataIndex = ? AND Store = ? AND StoreId = ?
                          AND IdField = ? AND LabelField = ? AND LocalField = ?
                          AND COALESCE(StoreFilter, '') = COALESCE(?, '')
                    )
                    WHERE LayerId = ? AND ColumnName = ?
                """, params + (layer_id, fdef["localField"]))

                # Ensure filter type is 'list' and clear any custom values
                cursor.execute("""
                    UPDATE GridColumns
                    SET GridFilterTypeId = (SELECT GridFilterTypeId FROM GridFilterTypes WHERE Code='list'),
                        CustomListValues = NULL
                    WHERE LayerId = ? AND ColumnName = ?
                """, (layer_id, fdef["localField"]))

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
                cursor.execute("""
                    UPDATE GridColumns
                    SET GridFilterDefinitionId = NULL
                    WHERE LayerId = ? AND GridFilterDefinitionId IS NOT NULL
                """, (layer_id,))

            # After unlink, fall back to column ExType (string|number|boolean|date)
            cursor.execute("""
                UPDATE GridColumns
                SET GridFilterTypeId = (
                    SELECT GridFilterTypeId
                    FROM GridFilterTypes
                    WHERE Code = CASE
                        WHEN LOWER(
                            COALESCE(
                                (SELECT gcr.ExType
                                   FROM GridColumnRenderers gcr
                                  WHERE gcr.GridColumnRendererId = GridColumns.GridColumnRendererId),
                                'string'
                            )
                        ) = 'float'
                            THEN 'float_no_eq'
                        ELSE LOWER(
                            COALESCE(
                                (SELECT gcr.ExType
                                   FROM GridColumnRenderers gcr
                                  WHERE gcr.GridColumnRendererId = GridColumns.GridColumnRendererId),
                                'string'
                            )
                        )
                    END
                )
                WHERE LayerId = ?
                  AND GridFilterDefinitionId IS NULL
                  AND GridFilterTypeId IS NULL;
            """, (layer_id,))

            # 4) GC: remove orphaned filter definitions (unused anywhere)
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
                print(f"Saved {len(active_filters)} filters for layer '{self.active_layer}' to DB.")
        finally:
            if manage_conn:
                conn.close()

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

    def save_columns_to_db(self, db_path=None, conn=None):
        """
        Save current column configs (self.saved_columns / self.columns_with_data) into GridColumns,
        and upsert GridColumnEdit rows when present.

        DisplayOrder:
          - If self._display_order_map is set (from the UI order), persist it to GridColumns.DisplayOrder.
          - Do not overwrite DisplayOrder later using stale in-memory values.

        Notes:
          - If a GridFilterDefinitionId is linked in DB, force GridFilterTypeId to 'list' (do not trust UI state).
        """
        import sqlite3

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

            # Choose source of truth
            cols = self.saved_columns or self.columns_with_data or {}
            if not isinstance(cols, dict):
                raise ValueError("columns state is not a dict")

            # Pre-fetch GridColumnId by ColumnName for this layer
            cursor.execute(
                "SELECT GridColumnId, ColumnName FROM GridColumns WHERE LayerId = ?",
                (layer_id,)
            )
            column_id_map = {r["ColumnName"]: r["GridColumnId"] for r in cursor.fetchall()}

            # Detect if DisplayOrder exists
            cursor.execute("PRAGMA table_info(GridColumns)")
            gc_cols = {r["name"] for r in cursor.fetchall()}
            has_display_order = "DisplayOrder" in gc_cols

            # 1) Persist DisplayOrder from UI ordering, if we have it
            if has_display_order and getattr(self, "_display_order_map", None):
                for col_name, disp in self._display_order_map.items():
                    gcid = column_id_map.get(col_name)
                    if gcid:
                        cursor.execute(
                            "UPDATE GridColumns SET DisplayOrder = ? WHERE GridColumnId = ?",
                            (int(disp), int(gcid))
                        )

            # Helper lookups
            def _get_renderer_id(renderer_name: str):
                name = (renderer_name or "").strip()
                if not name:
                    return None
                cursor.execute(
                    "SELECT GridColumnRendererId FROM GridColumnRenderers WHERE Renderer = ?",
                    (name,)
                )
                r = cursor.fetchone()
                return r["GridColumnRendererId"] if r else None

            def _get_editor_role_id(role_name: str):
                name = (role_name or "").strip()
                if not name:
                    return None
                cursor.execute(
                    "SELECT EditorRoleId FROM EditorRoles WHERE RoleName = ?",
                    (name,)
                )
                r = cursor.fetchone()
                return r["EditorRoleId"] if r else None

            # Local helper for filter type lookup (assumes you already have this elsewhere)
            def _lookup_filter_type_id(_conn, code: str):
                cur = _conn.cursor()
                cur.execute("SELECT GridFilterTypeId FROM GridFilterTypes WHERE Code = ?", (code,))
                rr = cur.fetchone()
                return rr["GridFilterTypeId"] if rr else None

            saved_count = 0

            for column_name, col in cols.items():
                if not column_name:
                    continue

                # Renderer
                renderer_id = col.get("GridColumnRendererId")
                if not renderer_id:
                    renderer_id = _get_renderer_id(col.get("renderer"))

                ft = (col.get("filterType") or "").strip().lower()

                # If switching to custom_list, it cannot remain linked to a GridFilterDefinitionId
                if ft == "custom_list":
                    cursor.execute(
                        "UPDATE GridColumns SET GridFilterDefinitionId = NULL WHERE LayerId = ? AND ColumnName = ?",
                        (layer_id, column_name)
                    )

                # If the column has a GridFilterDefinitionId linked in DB, force GridFilterTypeId='list'
                cursor.execute(
                    "SELECT GridFilterDefinitionId FROM GridColumns WHERE LayerId = ? AND ColumnName = ?",
                    (layer_id, column_name)
                )
                link_row = cursor.fetchone()
                has_list_filter_link = bool(link_row and link_row["GridFilterDefinitionId"])

                filter_type_id = None
                if has_list_filter_link:
                    filter_type_id = _lookup_filter_type_id(conn, "list")
                else:
                    # fall back to in-memory filterType if present
                    ft = (col.get("filterType") or "").strip().lower()
                    if ft:
                        filter_type_id = _lookup_filter_type_id(conn, ft)

                # CustomListValues
                custom_list_values = None
                if (col.get("filterType") or "").strip().lower() == "custom_list":
                    cl = col.get("customList") or []
                    if isinstance(cl, list):
                        custom_list_values = ",".join([str(x).strip() for x in cl if str(x).strip()])
                    else:
                        custom_list_values = str(cl)

                # Upsert GridColumns (NOTE: no DisplayOrder here, we already persisted it above)
                grid_column_id = column_id_map.get(column_name)

                if grid_column_id:
                    cursor.execute("""
                        UPDATE GridColumns
                        SET
                            Text = ?,
                            Flex = ?,
                            Hidden = ?,
                            InGrid = ?,
                            NoFilter = ?,
                            NullText = ?,
                            NullValue = ?,
                            Zeros = ?,
                            CustomListValues = ?,
                            GridColumnRendererId = ?,
                            GridFilterTypeId = COALESCE(?, GridFilterTypeId)
                        WHERE GridColumnId = ?
                    """, (
                        col.get("text"),
                        col.get("flex"),
                        1 if col.get("hidden") else 0,
                        1 if col.get("inGrid") else 0,
                        1 if col.get("noFilter") else 0,
                        col.get("nullText"),
                        col.get("nullValue"),
                        col.get("zeros"),
                        custom_list_values,
                        renderer_id,
                        filter_type_id,
                        grid_column_id,
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO GridColumns
                            (LayerId, ColumnName, Text, Flex, Hidden, InGrid, NoFilter,
                             NullText, NullValue, Zeros, CustomListValues,
                             GridColumnRendererId, GridFilterTypeId, DisplayOrder)
                        VALUES
                            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        layer_id,
                        column_name,
                        col.get("text"),
                        col.get("flex"),
                        1 if col.get("hidden") else 0,
                        1 if col.get("inGrid") else 0,
                        1 if col.get("noFilter") else 0,
                        col.get("nullText"),
                        col.get("nullValue"),
                        col.get("zeros"),
                        custom_list_values,
                        renderer_id,
                        filter_type_id,
                        int(self._display_order_map.get(column_name, 999999)) if getattr(self, "_display_order_map", None) else None,
                    ))
                    grid_column_id = cursor.lastrowid
                    column_id_map[column_name] = grid_column_id

                # Upsert GridColumnEdit if present
                edit = col.get("edit")
                if isinstance(edit, dict):
                    editor_role_id = _get_editor_role_id(edit.get("editUserRole"))

                    cursor.execute(
                        "SELECT GridColumnEditId FROM GridColumnEdit WHERE GridColumnId = ?",
                        (grid_column_id,)
                    )
                    erow = cursor.fetchone()

                    if erow:
                        cursor.execute("""
                            UPDATE GridColumnEdit
                            SET
                                GroupEditIdProperty = ?,
                                GroupEditDataProp = ?,
                                EditServiceUrl = ?,
                                EditorRoleId = ?
                            WHERE GridColumnId = ?
                        """, (
                            edit.get("groupEditIdProperty"),
                            edit.get("groupEditDataProp"),
                            edit.get("editServiceUrl"),
                            editor_role_id,
                            grid_column_id,
                        ))
                    else:
                        cursor.execute("""
                            INSERT INTO GridColumnEdit
                                (GridColumnId, GroupEditIdProperty, GroupEditDataProp, EditServiceUrl, EditorRoleId)
                            VALUES
                                (?, ?, ?, ?, ?)
                        """, (
                            grid_column_id,
                            edit.get("groupEditIdProperty"),
                            edit.get("groupEditDataProp"),
                            edit.get("editServiceUrl"),
                            editor_role_id,
                        ))

                saved_count += 1

            if manage_conn:
                conn.commit()
                print(f"Saved {saved_count} columns for layer '{self.active_layer}' to DB.")

        finally:
            if manage_conn:
                conn.close()

    def delete_column(self, column_name: str) -> bool:
            """
            Fully remove a column and its related data (edits, filters, etc.) from the database.
            Returns True on success, False on failure.
            """
            if not column_name:
                return False

            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            cursor = conn.cursor()

            try:
                # Get LayerId
                cursor.execute("SELECT LayerId FROM Layers WHERE Name = ?", (self.active_layer,))
                row = cursor.fetchone()
                if not row:
                    raise ValueError(f"Layer '{self.active_layer}' not found in Layers table.")
                layer_id = row["LayerId"]

                # Get GridColumnId for the target column
                cursor.execute(
                    "SELECT GridColumnId, GridFilterDefinitionId FROM GridColumns WHERE LayerId = ? AND ColumnName = ?",
                    (layer_id, column_name),
                )
                col_row = cursor.fetchone()
                if not col_row:
                    print(f"Column '{column_name}' not found in GridColumns for layer '{self.active_layer}'.")
                    return False

                grid_column_id = col_row["GridColumnId"]
                grid_filter_def_id = col_row["GridFilterDefinitionId"]

                # Remove related GridColumnEdit entry
                cursor.execute("DELETE FROM GridColumnEdit WHERE GridColumnId = ?", (grid_column_id,))

                # Delete the column itself
                cursor.execute("DELETE FROM GridColumns WHERE GridColumnId = ?", (grid_column_id,))

                # Optional: clean up orphaned GridFilterDefinitions
                if grid_filter_def_id:
                    cursor.execute("""
                        DELETE FROM GridFilterDefinitions
                        WHERE GridFilterDefinitionId = ?
                          AND GridFilterDefinitionId NOT IN (
                              SELECT DISTINCT GridFilterDefinitionId FROM GridColumns WHERE GridFilterDefinitionId IS NOT NULL
                          )
                    """, (grid_filter_def_id,))

                conn.commit()

                # Update internal state
                self.columns_with_data.pop(column_name, None)
                self.saved_columns.pop(column_name, None)
                self.active_columns = list(self.columns_with_data.keys())
                self.active_filters = [
                    f for f in self.active_filters if f["localField"] != column_name
                ]

                print(f"Column '{column_name}' removed from layer '{self.active_layer}'.")
                return True

            except Exception:
                conn.rollback()
                print(traceback.format_exc())
                return False
            finally:
                conn.close()

def main():
    """Application entry point: initializes and shows the main window."""
    import sys

    logging.basicConfig(level=logging.DEBUG)

    app = QtWidgets.QApplication(sys.argv)
    font = QFont("Roboto", 10)   # 9 or 10 is sane for tool UIs
    app.setFont(font)
    controller = Controller(None)
    main_window = MainWindowUIClass(controller)
    controller.main_window = main_window

    main_window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
