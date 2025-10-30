from jinja2 import Environment, FileSystemLoader
import os
import logging
import pprint
import json as JSON
from pathlib import Path
import sqlite3
from tabulate import tabulate

logger = logging.getLogger(__name__)
logging.getLogger("urllib3").setLevel(logging.WARNING)

pp = pprint.PrettyPrinter(indent=4)


class GridGenerationError(Exception):
    """Raised when grid generation fails for a specific, user-visible reason."""
    pass


class GridGenerator:
    def __init__(self, py_project_folder, js_project_folder, project_name="Pms"):
        self.py_project_folder = py_project_folder
        self.js_project_folder = js_project_folder
        self.project_name = project_name
        self.template_dir = str(Path(__file__).parent / "templates")

    def get_grid_details(self, layer_name, db_path):
        """
        Load column/filter/mdata details for the specified layer directly from the database.
        Uses LocalField to correctly map list filters to their respective grid columns.
        """
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

            # Load mdata
            cursor.execute("SELECT * FROM GridMData WHERE LayerId = ?", (layer_id,))
            mdata_row = cursor.fetchone()
            mdata = {key: mdata_row[key] for key in mdata_row.keys()} if mdata_row else {}

            # Load filters and use LocalField as key
            cursor.execute("""
                SELECT
                    gfd.*,
                    gc.ColumnName
                FROM GridColumns gc
                LEFT JOIN GridFilterDefinitions gfd
                    ON gc.GridFilterDefinitionId = gfd.GridFilterDefinitionId
                WHERE gc.LayerId = ?
            """, (layer_id,))
            filters = cursor.fetchall()

            print("Filter row keys:", list(filters[0].keys()) if filters else "no rows")

            filters_by_column = {
                ((row["LocalField"] or row["ColumnName"] or "").strip().lower()): {
                    "store": row["Store"],
                    "storeId": row["StoreId"],
                    "idField": row["IdField"],
                    "labelField": row["LabelField"],
                    "dataIndex": row["DataIndex"],
                }
                for row in filters
                if row["GridFilterDefinitionId"] is not None
            }

            # Load columns — ordered by DisplayOrder if present (NULLs last), else by name
            cursor.execute("PRAGMA table_info(GridColumns)")
            gc_cols = {row["name"] for row in cursor.fetchall()}
            has_display_order = "DisplayOrder" in gc_cols

            if has_display_order:
                column_data_sql = """
                    SELECT
                      gc.*,
                      r.Renderer AS Renderer,
                      r.ExType   AS ExType,
                      gft.Code   AS FilterType
                    FROM GridColumns AS gc
                    LEFT JOIN GridColumnRenderers AS r
                      ON r.GridColumnRendererId = gc.GridColumnRendererId
                    LEFT JOIN GridFilterTypes AS gft
                      ON gc.GridFilterTypeId = gft.GridFilterTypeId
                    WHERE gc.LayerId = ?
                    ORDER BY
                      CASE WHEN gc.DisplayOrder IS NULL THEN 1 ELSE 0 END,
                      gc.DisplayOrder,
                      gc.GridColumnId
                """
            else:
                column_data_sql = """
                    SELECT
                      gc.*,
                      r.Renderer AS Renderer,
                      r.ExType   AS ExType,
                      gft.Code   AS FilterType
                    FROM GridColumns AS gc
                    LEFT JOIN GridColumnRenderers AS r
                      ON r.GridColumnRendererId = gc.GridColumnRendererId
                    LEFT JOIN GridFilterTypes AS gft
                      ON gc.GridFilterTypeId = gft.GridFilterTypeId
                    WHERE gc.LayerId = ?
                    ORDER BY lower(gc.ColumnName)
                """
            cursor.execute(column_data_sql, (layer_id,))
            columns_rows = cursor.fetchall()

            # Load column edits with role names
            cursor.execute("""
                SELECT gce.*, er.RoleName
                FROM GridColumnEdit gce
                LEFT JOIN EditorRoles er
                    ON gce.EditorRoleId = er.EditorRoleId
            """)
            column_edit_rows = cursor.fetchall()
            column_edit_map = {
                row["GridColumnId"]: {
                    "groupEditIdProperty": row["GroupEditIdProperty"],
                    "groupEditDataProp": row["GroupEditDataProp"],
                    "editServiceUrl": row["EditServiceUrl"],
                    "editUserRole": row["RoleName"],
                }
                for row in column_edit_rows
            }

            visible_columns = {}
            field_types = {}

            for row in columns_rows:
                if not row["InGrid"]:
                    continue

                original_col_name = row["ColumnName"].strip()  # Preserve case for ExtJS
                normalized_col_name = original_col_name.lower()  # Only for internal mapping

                col = {
                    "text": row["Text"],
                    "renderer": row["Renderer"],
                    "exType": row["ExType"],
                    "nullText": row["NullText"],
                    "nullValue": row["NullValue"],
                    "zeros": row["Zeros"],
                    "noFilter": bool(row["NoFilter"]),
                    "filterType": row["FilterType"],
                    "flex": row["Flex"],
                    "hidden": bool(row["Hidden"]),
                    "editable": bool(row["Editable"]),
                    "customListValues": row["CustomListValues"],
                    "dataIndex": original_col_name  # Use original case for ExtJS
                }

                if normalized_col_name in filters_by_column:
                    col["filter"] = filters_by_column[normalized_col_name]

                raw_vals = row["CustomListValues"]  # DB is a CSV string
                items = []
                if isinstance(raw_vals, str) and raw_vals.strip():
                    items = [v.strip() for v in raw_vals.split(",") if v.strip()]

                if items:
                    col["customList"] = items

                # (Optionally drop the old field from output so templates don't rely on it)
                #col.pop("customListValues", None)

                is_editable = bool(row["Editable"])
                if is_editable and row["GridColumnId"] in column_edit_map:
                    col["groupEditable"] = True
                    col["editMeta"] = column_edit_map[row["GridColumnId"]]
                else:
                    col["groupEditable"] = False

                visible_columns[normalized_col_name] = col
                field_types[original_col_name] = row["ExType"]

            # Inject additional metadata
            mdata["Layer"] = layer_name
            mdata["Editable"] = any(col.get("editable") for col in visible_columns.values())

            # Load sorters
            cursor.execute("SELECT * FROM GridSorters WHERE LayerId = ?", (layer_id,))
            sorter_rows = cursor.fetchall()
            sorters = [
                {
                    "dataIndex": row["Property"],
                    "sortDirection": row["Direction"],
                    "sortOrder": row["SortOrder"]
                }
                for row in sorter_rows
            ]

            return visible_columns, mdata, field_types, sorters, filters_by_column

        finally:
            conn.close()



    def build_model_requires(self, mdata, columns, filters):
        """Determine required JS classes for the grid"""
        stores = {
            "Ext.grid.plugin.Exporter",
            "Ext.exporter.excel.Xlsx",
            "CpsiMapview.controller.grid.Grid",
            "Ext.grid.filters.filter.Date",
        }

        # Look in filters for store references
        for filt in filters.values():
            store_id = filt.get("store")
            if store_id:
                stores.add(f"{self.project_name}.store.{store_id}")

        # If grid is editable, add editing plugins
        if mdata.get("Editable"):
            stores.update({
                "Pms.util.GroupEditGridController",
                "GeoExt.selection.FeatureCheckboxModel",
            })

        controller_val = mdata.get("Controller", "")
        if "pms_Combined" in controller_val:
            controller_name = controller_val.split("_")[1]
            stores.add(f"Pms.view.grids.controllers.{controller_name}Controller")

        if controller_val == "pms_la16grid":
            stores.update({
                "Pms.view.la16.grid.GridController",
                "Pms.view.la16.grid.PhaseColumn"
            })

        return sorted(stores)

    def render_template(self, columns, mdata, field_types, stores, sorters):
        """Render the grid template with Jinja2"""
        env = Environment(
            loader=FileSystemLoader(self.template_dir),
            extensions=["jinja2.ext.do"],
            trim_blocks=False,
            lstrip_blocks=False,
        )
        template = env.get_template("main.template")
        safe_mdata = {k: ("" if v is None else v) for k, v in (mdata or {}).items()}
        return template.render(
            project=self.project_name,
            columns=columns,
            mdata=safe_mdata,
            fields=field_types,
            stores=stores,
            sorters=sorters
        )


    def generate_grid(self, layer_name, db_path):
        """Generate grid JS for a single feature type."""
        try:
            columns, mdata, field_types, sorters, filters = self.get_grid_details(layer_name, db_path)

            

            merged_count = 0
            missing_count = 0

            # Merge filters into their corresponding column dicts
            for local_field, v in filters.items():
                col = columns.get(local_field)
                if col:
                    if col.get("filterType") == "list":
                        col["filter"] = {
                            "dataIndex": v["dataIndex"],
                            "labelField": v["labelField"],
                            "idField": v["idField"],
                            "store": v["storeId"]
                        }
                        print(f"[Filter Merged] Column '{local_field}' linked to list filter.")
                        merged_count += 1
                    else:
                        print(f"[Filter Skipped] Column '{local_field}' has non-list filter type: {col.get('filterType')}")
                else:
                    print(f"[Filter Missing] No matching column found for LocalField '{local_field}'.")
                    missing_count += 1

            print(f"[Summary] Filters merged: {merged_count}, Filters with missing columns: {missing_count}")

            stores = self.build_model_requires(mdata, columns, filters)

            #pp.pprint(columns)

            js_code = self.render_template(columns, mdata, field_types, stores, sorters)

            output_dir = os.path.join(self.js_project_folder, "app", "view", "grids")
            os.makedirs(output_dir, exist_ok=True)

            outfile = os.path.join(output_dir, f"{layer_name}Grid.js")
            with open(outfile, "w", encoding="utf-8", newline="\n") as f:
                f.write(js_code + "\n")
            print('')
            logger.info(f"Successfully generated grid for {layer_name}")

            summary_data = []
            for col_key, col in columns.items():
                summary_data.append([
                    col.get("dataIndex", col_key),
                    col.get("text", ""),
                    col.get("filterType", ""),
                    col.get("renderer", ""),
                    col.get("exType", ""),
                    col.get("filter", {}).get("dataIndex", "") if col.get("filterType") == "list" else "",
                    "Yes" if col.get("editable") else "No"
                ])

            print(f"\nGrid Column Summary for layer: {layer_name}")
            print(tabulate(summary_data, headers=[
                "Column", "Display Name", "Filter Type", "Renderer", "ExtType", "FilterDataIndex", "Editable"
            ]))


            return True

        except Exception as e:
            logger.error(f"Failed to generate grid for {layer_name}: {str(e)}")
            raise GridGenerationError(f"Grid generation failed: {str(e)}")


    def generate_grids(self, feature_types=None):
        """Generate grids for multiple feature types"""
        if not feature_types:
            feature_types = self.get_feature_types()

        results = {}
        for ft in feature_types:
            try:
                success = self.generate_grid(ft)
                results[ft] = success
            except GridGenerationError as e:
                results[ft] = False
                logger.error(str(e))

        return results
