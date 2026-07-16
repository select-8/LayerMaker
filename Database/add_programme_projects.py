"""
Add and configure all 56 ProgrammeProjects layers in MapMakerDB.db.

Reference layer: ProgrammeProjectsRI_CurrentYear (LayerId=277, MapServerLayerId=148)

Tasks:
  1. Insert 53 missing layers (MapServerLayers, Layers, ServiceLayers, MapServerLayerFields)
  2. Grid config for 54 layers (53 new + fix _Plus1): GridMData + GridColumns
  3. Styles for 54 MapServerLayerIds + fix _LastYear styles
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "MapMakerDB.db")

NEW_LAYER_NAMES = [
    "ProgrammeProjectsRI_Plus2",
    "ProgrammeProjectsRM_LastYear",
    "ProgrammeProjectsRM_CurrentYear",
    "ProgrammeProjectsRM_Plus1",
    "ProgrammeProjectsRM_Plus2",
    "ProgrammeProjectsSRM_LastYear",
    "ProgrammeProjectsSRM_CurrentYear",
    "ProgrammeProjectsSRM_Plus1",
    "ProgrammeProjectsSRM_Plus2",
    "ProgrammeProjectsDG_LastYear",
    "ProgrammeProjectsDG_CurrentYear",
    "ProgrammeProjectsDG_Plus1",
    "ProgrammeProjectsDG_Plus2",
    "ProgrammeProjectsCIS_LastYear",
    "ProgrammeProjectsCIS_CurrentYear",
    "ProgrammeProjectsCIS_Plus1",
    "ProgrammeProjectsCIS_Plus2",
    "ProgrammeProjectsLIS_LastYear",
    "ProgrammeProjectsLIS_CurrentYear",
    "ProgrammeProjectsLIS_Plus1",
    "ProgrammeProjectsLIS_Plus2",
    "ProgrammeProjectsDR_LastYear",
    "ProgrammeProjectsDR_CurrentYear",
    "ProgrammeProjectsDR_Plus1",
    "ProgrammeProjectsDR_Plus2",
    "ProgrammeProjectsOR_LastYear",
    "ProgrammeProjectsOR_CurrentYear",
    "ProgrammeProjectsOR_Plus1",
    "ProgrammeProjectsOR_Plus2",
    "ProgrammeProjectsOther_LastYear",
    "ProgrammeProjectsOther_CurrentYear",
    "ProgrammeProjectsOther_Plus1",
    "ProgrammeProjectsOther_Plus2",
    "ProgrammeProjectsSG_LastYear",
    "ProgrammeProjectsSG_CurrentYear",
    "ProgrammeProjectsSG_Plus1",
    "ProgrammeProjectsSG_Plus2",
    "ProgrammeProjectsSRLR_LastYear",
    "ProgrammeProjectsSRLR_CurrentYear",
    "ProgrammeProjectsSRLR_Plus1",
    "ProgrammeProjectsSRLR_Plus2",
    "ProgrammeProjectsCCAR_LastYear",
    "ProgrammeProjectsCCAR_CurrentYear",
    "ProgrammeProjectsCCAR_Plus1",
    "ProgrammeProjectsCCAR_Plus2",
    "ProgrammeProjectsFN_LastYear",
    "ProgrammeProjectsFN_CurrentYear",
    "ProgrammeProjectsFN_Plus1",
    "ProgrammeProjectsFN_Plus2",
    "ProgrammeProjectsCIPRATPAV_LastYear",
    "ProgrammeProjectsCIPRATPAV_CurrentYear",
    "ProgrammeProjectsCIPRATPAV_Plus1",
    "ProgrammeProjectsCIPRATPAV_Plus2",
]

REF_LAYER_ID = 277          # ProgrammeProjectsRI_CurrentYear
REF_MSL_ID   = 148          # ProgrammeProjectsRI_CurrentYear MapServerLayerId
PLUS1_LAYER_ID = 279        # ProgrammeProjectsRI_Plus1 (already in DB, needs fixing)
PLUS1_MSL_ID   = 150        # ProgrammeProjectsRI_Plus1 MapServerLayerId
LASTYEAR_MSL_ID = 149       # ProgrammeProjectsRI_LastYear MapServerLayerId


def run():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")

    try:
        with conn:
            _task1_add_layers(conn)
            _task2_grid_config(conn)
            _task3_styles(conn)
        print("Done. Running verification counts...")
        _verify(conn)
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


# ---------------------------------------------------------------------------
# Task 1 — Add 53 missing layers
# ---------------------------------------------------------------------------

def _task1_add_layers(conn):
    print(f"\n--- Task 1: adding {len(NEW_LAYER_NAMES)} new layers ---")

    # 1a. MapServerLayers
    conn.executemany(
        """
        INSERT OR IGNORE INTO MapServerLayers
            (MapLayerName, BaseLayerKey, GridXType, GeometryType,
             Opacity, NoCluster, LabelClassName, Projection)
        VALUES (?, UPPER(?), 'pms_' || LOWER(?) || 'grid', 'LINESTRING',
                0.75, 1, 'labels', 'EPSG:2157')
        """,
        [(n, n, n) for n in NEW_LAYER_NAMES],
    )
    print(f"  MapServerLayers: {conn.execute('SELECT changes()').fetchone()[0]} inserted")

    # 1b. Layers
    conn.executemany(
        "INSERT OR IGNORE INTO Layers (Name) VALUES (?)",
        [(n,) for n in NEW_LAYER_NAMES],
    )
    print(f"  Layers: {conn.execute('SELECT changes()').fetchone()[0]} inserted")

    # 1c. ServiceLayers — WMS then WFS
    conn.executemany(
        """
        INSERT OR IGNORE INTO ServiceLayers
            (MapServerLayerId, ServiceType, LayerKey, FeatureType, IdPropertyName, GeomFieldName)
        SELECT msl.MapServerLayerId, 'WMS', UPPER(?) || '_WMS', ?, 'ProjectFundingId', 'msGeometry'
        FROM MapServerLayers msl WHERE msl.MapLayerName = ?
        """,
        [(n, n, n) for n in NEW_LAYER_NAMES],
    )
    conn.executemany(
        """
        INSERT OR IGNORE INTO ServiceLayers
            (MapServerLayerId, ServiceType, LayerKey, FeatureType, IdPropertyName, GeomFieldName)
        SELECT msl.MapServerLayerId, 'WFS', UPPER(?) || '_VECTOR', ?, 'ProjectFundingId', 'msGeometry'
        FROM MapServerLayers msl WHERE msl.MapLayerName = ?
        """,
        [(n, n, n) for n in NEW_LAYER_NAMES],
    )
    svc_count = conn.execute(
        "SELECT COUNT(*) FROM ServiceLayers WHERE LayerKey LIKE 'PROGRAMMEPROJECTS%'"
    ).fetchone()[0]
    print(f"  ServiceLayers total for ProgrammeProjects: {svc_count}")

    # 1d. MapServerLayerFields — copy 97 fields from reference to each new MapServerLayerId
    conn.execute(
        f"""
        INSERT OR IGNORE INTO MapServerLayerFields
            (MapServerLayerId, FieldName, FieldType,
             IncludeInPropertyCsv, IsIdProperty, DisplayOrder)
        SELECT
            msl.MapServerLayerId,
            src.FieldName, src.FieldType,
            src.IncludeInPropertyCsv, src.IsIdProperty, src.DisplayOrder
        FROM MapServerLayerFields src
        CROSS JOIN MapServerLayers msl
        WHERE src.MapServerLayerId = {REF_MSL_ID}
          AND msl.MapLayerName IN ({_placeholders(NEW_LAYER_NAMES)})
        """,
        NEW_LAYER_NAMES,
    )
    print(f"  MapServerLayerFields: {conn.execute('SELECT changes()').fetchone()[0]} inserted")


# ---------------------------------------------------------------------------
# Task 2 — Grid config
# ---------------------------------------------------------------------------

def _task2_grid_config(conn):
    print("\n--- Task 2: grid config ---")

    # 2a. Fix _Plus1 MapServerLayers and ServiceLayers
    conn.execute(
        "UPDATE MapServerLayers SET LabelClassName = 'labels', Projection = 'EPSG:2157' "
        f"WHERE MapServerLayerId = {PLUS1_MSL_ID}"
    )
    conn.execute(
        "UPDATE ServiceLayers SET FeatureType = 'ProgrammeProjectsRI_Plus1', "
        f"IdPropertyName = 'ProjectFundingId' WHERE MapServerLayerId = {PLUS1_MSL_ID}"
    )
    print("  _Plus1 MapServerLayers + ServiceLayers fixed")

    # Collect target LayerIds: all new layers + _Plus1
    target_ids = _get_layer_ids(conn, NEW_LAYER_NAMES) + [PLUS1_LAYER_ID]
    print(f"  Target LayerIds for grid config: {len(target_ids)}")

    # 2b. GridMData
    conn.executemany(
        f"""
        INSERT OR IGNORE INTO GridMData
            (LayerId, IdField, Service, Window, Model, HelpPage,
             Controller, GetId, IsSwitch, IsSpatial, ExcelExporter, ShpExporter)
        SELECT
            ?, IdField, Service, Window, Model, HelpPage,
            Controller, GetId, IsSwitch, IsSpatial, ExcelExporter, ShpExporter
        FROM GridMData WHERE LayerId = {REF_LAYER_ID}
        """,
        [(lid,) for lid in target_ids],
    )
    print(f"  GridMData: {conn.execute('SELECT changes()').fetchone()[0]} inserted")

    # 2c. GridColumns (100 columns × 54 layers)
    conn.executemany(
        f"""
        INSERT OR IGNORE INTO GridColumns
            (LayerId, ColumnName, Text, DisplayOrder, InGrid, Hidden,
             NullText, NullValue, Zeros, NoFilter, Flex, CustomListValues,
             Editable, GridColumnRendererId, GridFilterTypeId,
             GridFilterDefinitionId, SortIndex, BooleanOptionId)
        SELECT
            ?, ColumnName, Text, DisplayOrder, InGrid, Hidden,
            NullText, NullValue, Zeros, NoFilter, Flex, CustomListValues,
            Editable, GridColumnRendererId, GridFilterTypeId,
            GridFilterDefinitionId, SortIndex, BooleanOptionId
        FROM GridColumns WHERE LayerId = {REF_LAYER_ID}
        """,
        [(lid,) for lid in target_ids],
    )
    print(f"  GridColumns: {conn.execute('SELECT changes()').fetchone()[0]} inserted")


# ---------------------------------------------------------------------------
# Task 3 — Styles
# ---------------------------------------------------------------------------

def _task3_styles(conn):
    print("\n--- Task 3: styles ---")

    # 3a. New layers + _Plus1: copy 17 styles from reference
    new_msl_ids = _get_msl_ids(conn, NEW_LAYER_NAMES) + [PLUS1_MSL_ID]
    conn.executemany(
        f"""
        INSERT OR IGNORE INTO MapServerLayerStyles
            (MapServerLayerId, GroupName, StyleTitle, DisplayOrder, IsIncluded)
        SELECT ?, GroupName, StyleTitle, DisplayOrder, IsIncluded
        FROM MapServerLayerStyles WHERE MapServerLayerId = {REF_MSL_ID}
        """,
        [(mid,) for mid in new_msl_ids],
    )
    print(f"  MapServerLayerStyles inserted: {conn.execute('SELECT changes()').fetchone()[0]}")

    # 3b. Fix _LastYear: delete the disabled Default placeholder
    conn.execute(
        f"DELETE FROM MapServerLayerStyles "
        f"WHERE MapServerLayerId = {LASTYEAR_MSL_ID} AND GroupName = 'Default'"
    )
    print(f"  _LastYear Default style deleted")

    # 3c. Fix _LastYear: add 3 missing styles from reference
    conn.execute(
        f"""
        INSERT OR IGNORE INTO MapServerLayerStyles
            (MapServerLayerId, GroupName, StyleTitle, DisplayOrder, IsIncluded)
        SELECT {LASTYEAR_MSL_ID}, GroupName, StyleTitle, DisplayOrder, IsIncluded
        FROM MapServerLayerStyles
        WHERE MapServerLayerId = {REF_MSL_ID}
          AND GroupName IN ('EngineersArea', 'LicensingArea', 'MunicipalDistrict')
        """
    )
    print(f"  _LastYear missing styles added: {conn.execute('SELECT changes()').fetchone()[0]}")


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def _verify(conn):
    checks = [
        ("Layers",            "SELECT COUNT(*) FROM Layers WHERE Name LIKE 'ProgrammeProjects%'",                                56),
        ("MapServerLayers",   "SELECT COUNT(*) FROM MapServerLayers WHERE MapLayerName LIKE 'ProgrammeProjects%'",               56),
        ("ServiceLayers",     "SELECT COUNT(*) FROM ServiceLayers WHERE LayerKey LIKE 'PROGRAMMEPROJECTS%'",                    112),
        ("GridMData",         "SELECT COUNT(*) FROM GridMData gm JOIN Layers l ON gm.LayerId = l.LayerId WHERE l.Name LIKE 'ProgrammeProjects%'", 56),
        ("Styles per layer",  "SELECT COUNT(DISTINCT MapServerLayerId) FROM MapServerLayerStyles s JOIN MapServerLayers msl ON s.MapServerLayerId = msl.MapServerLayerId WHERE msl.MapLayerName LIKE 'ProgrammeProjects%' GROUP BY msl.MapServerLayerId HAVING COUNT(*) = 17", 56),
    ]
    print()
    all_ok = True
    for label, sql, expected in checks:
        rows = conn.execute(sql).fetchall()
        actual = rows[0][0] if rows and len(rows) == 1 else len(rows)
        ok = actual == expected
        all_ok = all_ok and ok
        print(f"  {'✓' if ok else '✗'} {label}: {actual} (expected {expected})")

    col_counts = conn.execute(
        "SELECT l.Name, COUNT(gc.GridColumnId) cnt "
        "FROM GridColumns gc JOIN Layers l ON gc.LayerId = l.LayerId "
        "WHERE l.Name LIKE 'ProgrammeProjects%' "
        "GROUP BY l.LayerId HAVING cnt != 100"
    ).fetchall()
    if col_counts:
        print(f"  ✗ GridColumns: {len(col_counts)} layers do NOT have 100 columns:")
        for row in col_counts:
            print(f"      {row['Name']}: {row['cnt']}")
        all_ok = False
    else:
        print("  ✓ GridColumns: all 56 layers have 100 columns")

    print(f"\n{'All checks passed.' if all_ok else 'Some checks FAILED — review above.'}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _placeholders(items):
    return ",".join("?" * len(items))


def _get_layer_ids(conn, names):
    rows = conn.execute(
        f"SELECT LayerId FROM Layers WHERE Name IN ({_placeholders(names)})", names
    ).fetchall()
    return [r[0] for r in rows]


def _get_msl_ids(conn, names):
    rows = conn.execute(
        f"SELECT MapServerLayerId FROM MapServerLayers WHERE MapLayerName IN ({_placeholders(names)})", names
    ).fetchall()
    return [r[0] for r in rows]


if __name__ == "__main__":
    run()
