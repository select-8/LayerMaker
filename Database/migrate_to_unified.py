"""
migrate_to_unified.py
---------------------
Phase 3 migration: imports all LayerConfig_v4 tables into MapMakerDB,
creating a single unified database.

Linking key:
    MapMakerDB.Layers.Name  ==  LayerConfig.MapServerLayers.MapLayerName

Safe to run multiple times (idempotent).
Run from the project root:
    python Database/migrate_to_unified.py
"""

import os
import sys
import shutil
import sqlite3
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

MM_DB  = SCRIPT_DIR / "MapMakerDB.db"
LC_DB  = REPO_ROOT / "json_generator" / "LayerConfig_v4.db"
MM_BAK = SCRIPT_DIR / "MapMakerDB_pre_migration.db"
LC_BAK = REPO_ROOT / "json_generator" / "LayerConfig_v4_pre_migration.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _col_exists(cur, table, column):
    cur.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())


def _table_exists(cur, table):
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    )
    return cur.fetchone() is not None


def _row_count(cur, table):
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def step1_backup():
    print("Step 1: Backing up databases...")
    for src, dst in [(MM_DB, MM_BAK), (LC_DB, LC_BAK)]:
        if not dst.exists():
            shutil.copy2(src, dst)
            print(f"  {src.name}  ->  {dst.name}")
        else:
            print(f"  Backup already exists: {dst.name}  (skipped)")


def step2_extend_portals(mm, lc):
    """Add TreeTitle to Portals and populate from LayerConfig."""
    print("\nStep 2: Extending Portals with TreeTitle...")
    mm_cur = mm.cursor()
    if not _col_exists(mm_cur, "Portals", "TreeTitle"):
        mm_cur.execute("ALTER TABLE Portals ADD COLUMN TreeTitle TEXT")
        print("  Added TreeTitle column")
    else:
        print("  TreeTitle column already exists (skipped)")

    for row in lc.execute("SELECT PortalId, TreeTitle FROM Portals").fetchall():
        mm_cur.execute(
            "UPDATE Portals SET TreeTitle = ? WHERE PortalId = ?",
            (row["TreeTitle"], row["PortalId"]),
        )
    mm.commit()
    print("  TreeTitle values populated")


def step3_import_mapserver_layers(mm, lc):
    """
    Create MapServerLayers in MapMakerDB and import all rows from LayerConfig.
    Then add MapServerLayerId FK column to Layers and populate by name match.
    """
    print("\nStep 3: Importing MapServerLayers...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "MapServerLayers"):
        mm_cur.execute("""
            CREATE TABLE MapServerLayers (
                MapServerLayerId      INTEGER PRIMARY KEY,
                MapLayerName          TEXT    NOT NULL,
                BaseLayerKey          TEXT    NOT NULL,
                GridXType             TEXT    NOT NULL,
                GeometryType          TEXT    NOT NULL,
                DefaultGeomFieldName  TEXT    NOT NULL DEFAULT 'msGeometry',
                LabelClassName        TEXT,
                GeomFieldName         TEXT,
                Opacity               REAL    NOT NULL DEFAULT 0.75,
                Projection            TEXT,
                NoCluster             INTEGER NOT NULL DEFAULT 1,
                IsXYZ                 INTEGER NOT NULL DEFAULT 0,
                IsArcGisRest          INTEGER NOT NULL DEFAULT 0,
                MaxScale              INTEGER
            )
        """)
        print("  Created MapServerLayers table")
    else:
        print("  MapServerLayers table already exists (skipped)")

    existing_ids = {
        r[0] for r in mm_cur.execute(
            "SELECT MapServerLayerId FROM MapServerLayers"
        ).fetchall()
    }
    rows = lc.execute("SELECT * FROM MapServerLayers").fetchall()
    inserted = 0
    for row in rows:
        if row["MapServerLayerId"] not in existing_ids:
            mm_cur.execute("""
                INSERT INTO MapServerLayers
                    (MapServerLayerId, MapLayerName, BaseLayerKey, GridXType,
                     GeometryType, DefaultGeomFieldName, LabelClassName,
                     GeomFieldName, Opacity, Projection, NoCluster, IsXYZ,
                     IsArcGisRest, MaxScale)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row["MapServerLayerId"], row["MapLayerName"], row["BaseLayerKey"],
                row["GridXType"], row["GeometryType"], row["DefaultGeomFieldName"],
                row["LabelClassName"], row["GeomFieldName"], row["Opacity"],
                row["Projection"], row["NoCluster"], row["IsXYZ"],
                row["IsArcGisRest"], row["MaxScale"],
            ))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing_ids)} already present)")

    # Add FK column to Layers
    if not _col_exists(mm_cur, "Layers", "MapServerLayerId"):
        mm_cur.execute(
            "ALTER TABLE Layers ADD COLUMN MapServerLayerId INTEGER "
            "REFERENCES MapServerLayers(MapServerLayerId)"
        )
        print("  Added MapServerLayerId FK column to Layers")
    else:
        print("  Layers.MapServerLayerId already exists (skipped)")

    # Populate FK by name match
    mm_cur.execute("""
        UPDATE Layers
        SET MapServerLayerId = (
            SELECT MapServerLayerId FROM MapServerLayers
            WHERE MapLayerName = Layers.Name
        )
        WHERE MapServerLayerId IS NULL
    """)
    mm.commit()

    linked = mm_cur.execute(
        "SELECT COUNT(*) FROM Layers WHERE MapServerLayerId IS NOT NULL"
    ).fetchone()[0]
    unlinked = mm_cur.execute(
        "SELECT COUNT(*) FROM Layers WHERE MapServerLayerId IS NULL"
    ).fetchone()[0]
    print(f"  Layers linked:   {linked}")
    print(f"  Layers unlinked: {unlinked}  (report/schedule layers - expected)")


def step4_import_mapserver_layer_fields(mm, lc):
    print("\nStep 4: Importing MapServerLayerFields...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "MapServerLayerFields"):
        mm_cur.execute("""
            CREATE TABLE MapServerLayerFields (
                FieldId                  INTEGER PRIMARY KEY,
                MapServerLayerId         INTEGER NOT NULL
                    REFERENCES MapServerLayers(MapServerLayerId),
                FieldName                TEXT    NOT NULL,
                FieldType                TEXT    NOT NULL,
                IncludeInPropertyCsv     INTEGER NOT NULL DEFAULT 0,
                IsIdProperty             INTEGER NOT NULL DEFAULT 0,
                DisplayOrder             INTEGER NOT NULL DEFAULT 0
            )
        """)
        print("  Created MapServerLayerFields table")
    else:
        print("  MapServerLayerFields already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute("SELECT FieldId FROM MapServerLayerFields").fetchall()
    }
    rows = lc.execute("SELECT * FROM MapServerLayerFields").fetchall()
    inserted = sum(1 for row in rows if row["FieldId"] not in existing)
    for row in rows:
        if row["FieldId"] not in existing:
            mm_cur.execute("""
                INSERT INTO MapServerLayerFields
                    (FieldId, MapServerLayerId, FieldName, FieldType,
                     IncludeInPropertyCsv, IsIdProperty, DisplayOrder)
                VALUES (?,?,?,?,?,?,?)
            """, (
                row["FieldId"], row["MapServerLayerId"], row["FieldName"],
                row["FieldType"], row["IncludeInPropertyCsv"],
                row["IsIdProperty"], row["DisplayOrder"],
            ))
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step5_import_mapserver_layer_styles(mm, lc):
    print("\nStep 5: Importing MapServerLayerStyles...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "MapServerLayerStyles"):
        mm_cur.execute("""
            CREATE TABLE MapServerLayerStyles (
                StyleId          INTEGER PRIMARY KEY,
                MapServerLayerId INTEGER NOT NULL
                    REFERENCES MapServerLayers(MapServerLayerId),
                GroupName        TEXT    NOT NULL,
                StyleTitle       TEXT    NOT NULL,
                DisplayOrder     INTEGER NOT NULL DEFAULT 0,
                IsIncluded       INTEGER NOT NULL DEFAULT 1
            )
        """)
        print("  Created MapServerLayerStyles table")
    else:
        print("  MapServerLayerStyles already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute("SELECT StyleId FROM MapServerLayerStyles").fetchall()
    }
    rows = lc.execute("SELECT * FROM MapServerLayerStyles").fetchall()
    inserted = 0
    for row in rows:
        if row["StyleId"] not in existing:
            mm_cur.execute("""
                INSERT INTO MapServerLayerStyles
                    (StyleId, MapServerLayerId, GroupName, StyleTitle,
                     DisplayOrder, IsIncluded)
                VALUES (?,?,?,?,?,?)
            """, (
                row["StyleId"], row["MapServerLayerId"], row["GroupName"],
                row["StyleTitle"], row["DisplayOrder"], row["IsIncluded"],
            ))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step6_import_service_layers(mm, lc):
    print("\nStep 6: Importing ServiceLayers...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "ServiceLayers"):
        mm_cur.execute("""
            CREATE TABLE ServiceLayers (
                ServiceLayerId       INTEGER PRIMARY KEY,
                MapServerLayerId     INTEGER
                    REFERENCES MapServerLayers(MapServerLayerId),
                ServiceType          TEXT    NOT NULL,
                LayerKey             TEXT    NOT NULL,
                FeatureType          TEXT,
                IdPropertyName       TEXT,
                GeomFieldName        TEXT    NOT NULL DEFAULT 'msGeometry',
                GridXType            TEXT,
                Grouping             TEXT,
                IsUserConfigurable   INTEGER NOT NULL DEFAULT 1,
                WfsMaxScale          INTEGER
            )
        """)
        print("  Created ServiceLayers table")
    else:
        print("  ServiceLayers already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute("SELECT ServiceLayerId FROM ServiceLayers").fetchall()
    }
    rows = lc.execute("SELECT * FROM ServiceLayers").fetchall()
    inserted = 0
    for row in rows:
        if row["ServiceLayerId"] not in existing:
            mm_cur.execute("""
                INSERT INTO ServiceLayers
                    (ServiceLayerId, MapServerLayerId, ServiceType, LayerKey,
                     FeatureType, IdPropertyName, GeomFieldName, GridXType,
                     Grouping, IsUserConfigurable, WfsMaxScale)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row["ServiceLayerId"], row["MapServerLayerId"], row["ServiceType"],
                row["LayerKey"], row["FeatureType"], row["IdPropertyName"],
                row["GeomFieldName"], row["GridXType"], row["Grouping"],
                row["IsUserConfigurable"], row["WfsMaxScale"],
            ))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step7_import_service_layer_fields(mm, lc):
    print("\nStep 7: Importing ServiceLayerFields...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "ServiceLayerFields"):
        mm_cur.execute("""
            CREATE TABLE ServiceLayerFields (
                FieldId                  INTEGER PRIMARY KEY,
                ServiceLayerId           INTEGER NOT NULL
                    REFERENCES ServiceLayers(ServiceLayerId),
                FieldName                TEXT    NOT NULL,
                FieldType                TEXT,
                IncludeInPropertyname    INTEGER NOT NULL DEFAULT 0,
                IsTooltip                INTEGER NOT NULL DEFAULT 0,
                TooltipAlias             TEXT,
                FieldOrder               INTEGER
            )
        """)
        print("  Created ServiceLayerFields table")
    else:
        print("  ServiceLayerFields already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute("SELECT FieldId FROM ServiceLayerFields").fetchall()
    }
    rows = lc.execute("SELECT * FROM ServiceLayerFields").fetchall()
    inserted = 0
    for row in rows:
        if row["FieldId"] not in existing:
            mm_cur.execute("""
                INSERT INTO ServiceLayerFields
                    (FieldId, ServiceLayerId, FieldName, FieldType,
                     IncludeInPropertyname, IsTooltip, TooltipAlias, FieldOrder)
                VALUES (?,?,?,?,?,?,?,?)
            """, (
                row["FieldId"], row["ServiceLayerId"], row["FieldName"],
                row["FieldType"], row["IncludeInPropertyname"], row["IsTooltip"],
                row["TooltipAlias"], row["FieldOrder"],
            ))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step8_import_service_layer_styles(mm, lc):
    print("\nStep 8: Importing ServiceLayerStyles...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "ServiceLayerStyles"):
        mm_cur.execute("""
            CREATE TABLE ServiceLayerStyles (
                StyleId          INTEGER PRIMARY KEY,
                ServiceLayerId   INTEGER NOT NULL
                    REFERENCES ServiceLayers(ServiceLayerId),
                StyleName        TEXT    NOT NULL,
                StyleTitle       TEXT    NOT NULL,
                UseLabelRule     INTEGER NOT NULL DEFAULT 0,
                StyleOrder       INTEGER
            )
        """)
        print("  Created ServiceLayerStyles table")
    else:
        print("  ServiceLayerStyles already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute("SELECT StyleId FROM ServiceLayerStyles").fetchall()
    }
    rows = lc.execute("SELECT * FROM ServiceLayerStyles").fetchall()
    inserted = 0
    for row in rows:
        if row["StyleId"] not in existing:
            mm_cur.execute("""
                INSERT INTO ServiceLayerStyles
                    (StyleId, ServiceLayerId, StyleName, StyleTitle,
                     UseLabelRule, StyleOrder)
                VALUES (?,?,?,?,?,?)
            """, (
                row["StyleId"], row["ServiceLayerId"], row["StyleName"],
                row["StyleTitle"], row["UseLabelRule"], row["StyleOrder"],
            ))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step9_import_portal_layers(mm, lc):
    print("\nStep 9: Importing PortalLayers...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "PortalLayers"):
        mm_cur.execute("""
            CREATE TABLE PortalLayers (
                PortalLayerId  INTEGER PRIMARY KEY,
                PortalId       INTEGER NOT NULL
                    REFERENCES Portals(PortalId),
                ServiceLayerId INTEGER NOT NULL
                    REFERENCES ServiceLayers(ServiceLayerId)
            )
        """)
        print("  Created PortalLayers table")
    else:
        print("  PortalLayers already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute("SELECT PortalLayerId FROM PortalLayers").fetchall()
    }
    rows = lc.execute("SELECT * FROM PortalLayers").fetchall()
    inserted = 0
    for row in rows:
        if row["PortalLayerId"] not in existing:
            mm_cur.execute("""
                INSERT INTO PortalLayers (PortalLayerId, PortalId, ServiceLayerId)
                VALUES (?,?,?)
            """, (row["PortalLayerId"], row["PortalId"], row["ServiceLayerId"]))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step10_import_portal_switch_layers(mm, lc):
    print("\nStep 10: Importing PortalSwitchLayers...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "PortalSwitchLayers"):
        mm_cur.execute("""
            CREATE TABLE PortalSwitchLayers (
                PortalSwitchLayerId       INTEGER PRIMARY KEY,
                PortalId                  INTEGER NOT NULL
                    REFERENCES Portals(PortalId),
                SwitchKey                 TEXT    NOT NULL,
                VectorFeaturesMinScale    INTEGER
            )
        """)
        print("  Created PortalSwitchLayers table")
    else:
        print("  PortalSwitchLayers already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute(
            "SELECT PortalSwitchLayerId FROM PortalSwitchLayers"
        ).fetchall()
    }
    rows = lc.execute("SELECT * FROM PortalSwitchLayers").fetchall()
    inserted = 0
    for row in rows:
        if row["PortalSwitchLayerId"] not in existing:
            mm_cur.execute("""
                INSERT INTO PortalSwitchLayers
                    (PortalSwitchLayerId, PortalId, SwitchKey, VectorFeaturesMinScale)
                VALUES (?,?,?,?)
            """, (
                row["PortalSwitchLayerId"], row["PortalId"],
                row["SwitchKey"], row["VectorFeaturesMinScale"],
            ))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step11_import_portal_switch_layer_children(mm, lc):
    print("\nStep 11: Importing PortalSwitchLayerChildren...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "PortalSwitchLayerChildren"):
        mm_cur.execute("""
            CREATE TABLE PortalSwitchLayerChildren (
                PortalSwitchLayerChildId  INTEGER PRIMARY KEY,
                PortalSwitchLayerId       INTEGER NOT NULL
                    REFERENCES PortalSwitchLayers(PortalSwitchLayerId),
                ServiceLayerId            INTEGER NOT NULL
                    REFERENCES ServiceLayers(ServiceLayerId),
                ChildOrder                INTEGER
            )
        """)
        print("  Created PortalSwitchLayerChildren table")
    else:
        print("  PortalSwitchLayerChildren already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute(
            "SELECT PortalSwitchLayerChildId FROM PortalSwitchLayerChildren"
        ).fetchall()
    }
    rows = lc.execute("SELECT * FROM PortalSwitchLayerChildren").fetchall()
    inserted = 0
    for row in rows:
        if row["PortalSwitchLayerChildId"] not in existing:
            mm_cur.execute("""
                INSERT INTO PortalSwitchLayerChildren
                    (PortalSwitchLayerChildId, PortalSwitchLayerId,
                     ServiceLayerId, ChildOrder)
                VALUES (?,?,?,?)
            """, (
                row["PortalSwitchLayerChildId"], row["PortalSwitchLayerId"],
                row["ServiceLayerId"], row["ChildOrder"],
            ))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step12_import_portal_tree_nodes(mm, lc):
    print("\nStep 12: Importing PortalTreeNodes...")
    mm_cur = mm.cursor()

    if not _table_exists(mm_cur, "PortalTreeNodes"):
        mm_cur.execute("""
            CREATE TABLE PortalTreeNodes (
                PortalTreeNodeId  INTEGER PRIMARY KEY,
                PortalId          INTEGER NOT NULL
                    REFERENCES Portals(PortalId),
                ParentNodeId      INTEGER,
                IsFolder          INTEGER NOT NULL,
                FolderTitle       TEXT,
                LayerKey          TEXT,
                DisplayOrder      INTEGER NOT NULL DEFAULT 0,
                Glyph             TEXT,
                CheckedDefault    INTEGER,
                ExpandedDefault   INTEGER,
                Tooltip           TEXT,
                FolderId          TEXT,
                LayerTitle        TEXT
            )
        """)
        print("  Created PortalTreeNodes table")
    else:
        print("  PortalTreeNodes already exists (skipped)")

    existing = {
        r[0] for r in mm_cur.execute(
            "SELECT PortalTreeNodeId FROM PortalTreeNodes"
        ).fetchall()
    }
    rows = lc.execute("SELECT * FROM PortalTreeNodes").fetchall()
    inserted = 0
    for row in rows:
        if row["PortalTreeNodeId"] not in existing:
            mm_cur.execute("""
                INSERT INTO PortalTreeNodes
                    (PortalTreeNodeId, PortalId, ParentNodeId, IsFolder,
                     FolderTitle, LayerKey, DisplayOrder, Glyph,
                     CheckedDefault, ExpandedDefault, Tooltip, FolderId, LayerTitle)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                row["PortalTreeNodeId"], row["PortalId"], row["ParentNodeId"],
                row["IsFolder"], row["FolderTitle"], row["LayerKey"],
                row["DisplayOrder"], row["Glyph"], row["CheckedDefault"],
                row["ExpandedDefault"], row["Tooltip"], row["FolderId"],
                row["LayerTitle"],
            ))
            inserted += 1
    mm.commit()
    print(f"  Imported {inserted} rows  ({len(existing)} already present)")


def step13_verify(mm):
    """Print a summary of the unified database."""
    cur = mm.cursor()
    print("\nStep 13: Verification summary")
    print("-" * 50)
    tables = [
        "Layers", "MapServerLayers", "MapServerLayerFields", "MapServerLayerStyles",
        "ServiceLayers", "ServiceLayerFields", "ServiceLayerStyles",
        "Portals", "PortalLayers", "PortalSwitchLayers",
        "PortalSwitchLayerChildren", "PortalTreeNodes",
        "GridColumns", "GridMData", "GridSorters", "GridFilterDefinitions",
    ]
    for t in tables:
        if _table_exists(cur, t):
            print(f"  {t:35} {_row_count(cur, t):>6} rows")
        else:
            print(f"  {t:35}  MISSING")

    # Check link quality
    linked = cur.execute(
        "SELECT COUNT(*) FROM Layers WHERE MapServerLayerId IS NOT NULL"
    ).fetchone()[0]
    total = cur.execute("SELECT COUNT(*) FROM Layers").fetchone()[0]
    print(f"\n  Layers with MapServerLayerId linked: {linked}/{total}")

    print("\nLegacy tables still present (not yet retired):")
    for t in ["PortalMapLayers", "LayerPortals", "CanonicalMapLayers"]:
        if _table_exists(cur, t):
            print(f"  {t:35} {_row_count(cur, t):>6} rows  <- retire after validation")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not MM_DB.exists():
        sys.exit(f"ERROR: MapMakerDB not found at {MM_DB}")
    if not LC_DB.exists():
        sys.exit(f"ERROR: LayerConfig_v4 not found at {LC_DB}")

    print("=" * 60)
    print("LayerMaker DB Migration — Phase 3")
    print(f"  Source:  {LC_DB}")
    print(f"  Target:  {MM_DB}")
    print("=" * 60)

    step1_backup()

    mm = sqlite3.connect(MM_DB)
    mm.row_factory = sqlite3.Row
    lc = sqlite3.connect(LC_DB)
    lc.row_factory = sqlite3.Row

    try:
        step2_extend_portals(mm, lc)
        step3_import_mapserver_layers(mm, lc)
        step4_import_mapserver_layer_fields(mm, lc)
        step5_import_mapserver_layer_styles(mm, lc)
        step6_import_service_layers(mm, lc)
        step7_import_service_layer_fields(mm, lc)
        step8_import_service_layer_styles(mm, lc)
        step9_import_portal_layers(mm, lc)
        step10_import_portal_switch_layers(mm, lc)
        step11_import_portal_switch_layer_children(mm, lc)
        step12_import_portal_tree_nodes(mm, lc)
        step13_verify(mm)
        print("\nMigration complete.")
    finally:
        mm.close()
        lc.close()


if __name__ == "__main__":
    main()
