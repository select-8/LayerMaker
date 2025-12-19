#!/usr/bin/env python3
"""
One-off bootstrap import into LayerConfig_v3.db schema from production portal *layer* JSONs.

What it does (this phase):
- Imports canonical WMS/WFS layers once (MapServerLayers + MapServerLayerStyles).
- Creates ServiceLayers for portal membership (PortalLayers) and switch wrappers (PortalSwitchLayers + children).
- ALWAYS ensures both WMS and WFS ServiceLayers exist for every canonical MapServer layer (stub rows if needed).
- Imports MapServerLayerFields from WFS serverOptions.propertyname CSV:
    IncludeInPropertyCsv = 1 for those fields
    IsIdProperty = 1 for the field named by idProperty (only one)
    DisplayOrder follows CSV order
    FieldType is set to "string" (placeholder, required by schema)
- Also seeds ServiceLayerFields (existing behaviour) from idProperty, propertyname CSV, tooltipsConfig.

What it skips (v3 cannot represent cleanly in this phase):
- Portal defaults
- xyz / arcgisrest layers
- Portal tree nodes (Tab 3). We can optionally wipe PortalTreeNodes if needed.

Critical schema issue (v3 as supplied):
- There is a UNIQUE index on MapServerLayerFields(MapServerLayerId, IsIdProperty).
  That makes it impossible to insert more than:
    one field with IsIdProperty=0, and one field with IsIdProperty=1
  which breaks propertyname CSV import.
- This script can fix it by replacing it with a partial unique index:
    UNIQUE(MapServerLayerId) WHERE IsIdProperty=1
  Use --fix-idproperty-index (default ON). Use --no-fix-idproperty-index to skip.

Usage:
  python bootstrap_v3_from_portal_layers.py --db LayerConfig_v3.db --layers-zip layers.zip --wipe-first
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


WMS = "WMS"
WFS = "WFS"

SUPPORTED_LAYER_TYPES = {"wms", "wfs", "switchlayer"}  # representable in v3 for this phase
SKIP_LAYER_TYPES = {"xyz", "arcgisrest"}              # not representable in v3


def read_json(path: str) -> Any:
    # tolerate BOM
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def dump_json_blob(obj: Any) -> str:
    # stable ordering for diffing
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def safe_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


def parse_propertyname_csv(server_options: Optional[dict]) -> List[str]:
    if not server_options:
        return []
    prop = server_options.get("propertyname")
    if not prop or not isinstance(prop, str):
        return []
    return [p.strip() for p in prop.split(",") if p.strip()]


def canonical_maplayer_name_from_layer(layer: Dict[str, Any]) -> Optional[str]:
    lt = layer.get("layerType")
    if lt == "wms":
        return (layer.get("serverOptions") or {}).get("layers")
    if lt == "wfs":
        return layer.get("featureType")
    return None


def service_type_from_layer(layer: Dict[str, Any]) -> Optional[str]:
    lt = layer.get("layerType")
    if lt == "wms":
        return WMS
    if lt == "wfs":
        return WFS
    return None


def derive_base_key(maplayer_name: str) -> str:
    # v3 uses BaseLayerKey, keep simple and deterministic
    return (maplayer_name or "").upper()


@dataclass
class PortalFiles:
    portal_key: str
    portal_title: str
    json_path: str


def load_portal_files_from_zip(layers_zip: str) -> List[PortalFiles]:
    # expected names per your production set
    mapping = {
        "default": "layers/default.json",
        "editor": "layers/editor.json",
        "nta_default": "layers/nta_default.json",
        "tii_default": "layers/tii_default.json",
    }

    tmp_dir = os.path.join(os.path.dirname(os.path.abspath(layers_zip)), "_layers_tmp_extract")
    if os.path.exists(tmp_dir):
        # nuke old extract
        for root, dirs, files in os.walk(tmp_dir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            for d in dirs:
                os.rmdir(os.path.join(root, d))
        os.rmdir(tmp_dir)

    os.makedirs(tmp_dir, exist_ok=True)

    with zipfile.ZipFile(layers_zip, "r") as z:
        z.extractall(tmp_dir)

    out: List[PortalFiles] = []
    for key, rel in mapping.items():
        path = os.path.join(tmp_dir, rel)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing expected portal JSON in zip: {rel}")
        out.append(PortalFiles(portal_key=key, portal_title=key, json_path=path))
    return out


def ensure_portal(cur: sqlite3.Cursor, portal_key: str, portal_title: str) -> int:
    cur.execute("SELECT PortalId FROM Portals WHERE PortalKey = ?", (portal_key,))
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute("INSERT INTO Portals(PortalKey, PortalTitle) VALUES(?,?)", (portal_key, portal_title))
    return int(cur.lastrowid)


def ensure_mapserver_layer(
    cur: sqlite3.Cursor,
    maplayer_name: str,
    gridxtype: str,
    label_class: str,
    geom_field: str,
    opacity: Optional[float]
) -> int:
    cur.execute("SELECT MapServerLayerId FROM MapServerLayers WHERE MapLayerName = ?", (maplayer_name,))
    row = cur.fetchone()
    if row:
        return int(row[0])

    base_key = derive_base_key(maplayer_name)
    geometry_type = "unknown"

    cur.execute(
        """
        INSERT INTO MapServerLayers(
            MapLayerName, BaseLayerKey, GridXType, GeometryType,
            DefaultGeomFieldName, DefaultLabelClassName, DefaultOpacity,
            LabelClassName, GeomFieldName, Opacity,
            IsXYZ, IsArcGisRest
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,0,0)
        """,
        (
            maplayer_name,
            base_key,
            gridxtype or "",
            geometry_type,
            geom_field or "msGeometry",
            label_class or "labels",
            opacity if opacity is not None else 0.75,
            None,
            None,
            None,
        )
    )
    return int(cur.lastrowid)


def ensure_service_layer(
    cur: sqlite3.Cursor,
    mapserver_layer_id: int,
    service_type: str,
    layer_key: str,
    feature_type: Optional[str],
    id_property: Optional[str],
    geom_field: Optional[str],
    label_class: Optional[str],
    opacity: Optional[float],
    openlayers: Optional[dict],
    server_options: Optional[dict],
    gridxtype: Optional[str],
    grouping: Optional[Any],
) -> int:
    # LayerKey is unique across DB
    cur.execute("SELECT ServiceLayerId FROM ServiceLayers WHERE LayerKey = ?", (layer_key,))
    row = cur.fetchone()
    if row:
        return int(row[0])

    grouping_out = grouping
    if isinstance(grouping_out, (dict, list)):
        grouping_out = dump_json_blob(grouping_out)

    cur.execute(
        """
        INSERT INTO ServiceLayers(
            MapServerLayerId, ServiceType, LayerKey,
            FeatureType, IdPropertyName, GeomFieldName, LabelClassName, Opacity,
            OpenLayersJson, ServerOptionsJson, GridXType, Grouping
        )
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            mapserver_layer_id,
            service_type,
            layer_key,
            feature_type,
            id_property,
            geom_field or "msGeometry",
            label_class or "labels",
            opacity if opacity is not None else 0.75,
            dump_json_blob(openlayers) if openlayers is not None else None,
            dump_json_blob(server_options) if server_options is not None else None,
            gridxtype,
            grouping_out,
        )
    )
    return int(cur.lastrowid)


def upsert_styles_for_mapserver(cur: sqlite3.Cursor, mapserver_layer_id: int, styles: List[dict]) -> None:
    # Insert-only: GROUP-based styles
    for i, st in enumerate(styles or []):
        name = st.get("name")
        title = st.get("title") or name
        if not name:
            continue
        cur.execute(
            "SELECT 1 FROM MapServerLayerStyles WHERE MapServerLayerId=? AND GroupName=?",
            (mapserver_layer_id, name),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO MapServerLayerStyles(MapServerLayerId, GroupName, StyleTitle, DisplayOrder, IsIncluded)
            VALUES(?,?,?,?,1)
            """,
            (mapserver_layer_id, name, title, i),
        )


def upsert_styles_for_service(cur: sqlite3.Cursor, service_layer_id: int, styles: List[dict]) -> None:
    for i, st in enumerate(styles or []):
        name = st.get("name")
        title = st.get("title") or name
        if not name:
            continue
        use_label_rule = 1 if st.get("labelRule") else 0
        cur.execute(
            "SELECT 1 FROM ServiceLayerStyles WHERE ServiceLayerId=? AND StyleName=?",
            (service_layer_id, name),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO ServiceLayerStyles(ServiceLayerId, StyleName, StyleTitle, UseLabelRule, StyleOrder)
            VALUES(?,?,?,?,?)
            """,
            (service_layer_id, name, title, use_label_rule, i),
        )


def upsert_service_fields(
    cur: sqlite3.Cursor,
    service_layer_id: int,
    id_property: Optional[str],
    tooltip_cfg: Optional[List[dict]],
    propertyname_fields: List[str],
) -> None:
    """
    v3 ServiceLayerFields seeding (existing behaviour).
    """
    field_meta: Dict[str, Dict[str, Any]] = {}

    def touch(fname: str) -> Dict[str, Any]:
        return field_meta.setdefault(fname, {"include": 0, "tooltip": 0, "alias": None, "order": None})

    if id_property:
        m = touch(id_property)
        m["include"] = 1
        m["order"] = 0

    for idx, f in enumerate(propertyname_fields, start=1):
        m = touch(f)
        m["include"] = 1
        if m["order"] is None:
            m["order"] = idx

    if tooltip_cfg:
        for idx, t in enumerate(tooltip_cfg, start=1000):
            prop = t.get("property")
            if not prop:
                continue
            m = touch(prop)
            m["tooltip"] = 1
            alias = t.get("alias")
            if alias:
                m["alias"] = alias
            if m["order"] is None:
                m["order"] = idx

    for fname, m in field_meta.items():
        cur.execute(
            "SELECT 1 FROM ServiceLayerFields WHERE ServiceLayerId=? AND FieldName=?",
            (service_layer_id, fname),
        )
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO ServiceLayerFields(
                ServiceLayerId, FieldName, FieldType,
                IncludeInPropertyname, IsTooltip, TooltipAlias, FieldOrder
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (service_layer_id, fname, None, int(m["include"]), int(m["tooltip"]), m["alias"], m["order"]),
        )


def get_next_field_id(cur: sqlite3.Cursor) -> int:
    cur.execute("SELECT COALESCE(MAX(FieldId), 0) FROM MapServerLayerFields")
    return int(cur.fetchone()[0]) + 1


def upsert_mapserver_fields_from_propertyname(
    cur: sqlite3.Cursor,
    mapserver_layer_id: int,
    field_names_in_order: List[str],
    id_property: Optional[str],
    next_field_id: int,
) -> int:
    """
    Insert MapServerLayerFields from WFS serverOptions.propertyname CSV.
    FieldType is required by schema, so we set "string" as placeholder.
    """
    # Insert-only by (MapServerLayerId, FieldName) unique index.
    for order, fname in enumerate(field_names_in_order or []):
        cur.execute(
            "SELECT 1 FROM MapServerLayerFields WHERE MapServerLayerId=? AND FieldName=?",
            (mapserver_layer_id, fname),
        )
        if cur.fetchone():
            continue

        is_id = 1 if (id_property and fname == id_property) else 0
        cur.execute(
            """
            INSERT INTO MapServerLayerFields(
                FieldId, MapServerLayerId, FieldName, FieldType,
                IncludeInPropertyCsv, IsIdProperty, DisplayOrder
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                next_field_id,
                mapserver_layer_id,
                fname,
                "string",
                1,
                is_id,
                order,
            ),
        )
        next_field_id += 1

    return next_field_id


def insert_portal_layer(cur: sqlite3.Cursor, portal_id: int, service_layer_id: int, is_enabled: int = 1) -> None:
    cur.execute(
        "SELECT 1 FROM PortalLayers WHERE PortalId=? AND ServiceLayerId=?",
        (portal_id, service_layer_id),
    )
    if cur.fetchone():
        return
    cur.execute(
        "INSERT INTO PortalLayers(PortalId, ServiceLayerId, IsEnabled) VALUES(?,?,?)",
        (portal_id, service_layer_id, is_enabled),
    )


def ensure_switch_layer(cur: sqlite3.Cursor, portal_id: int, switch_key: str,
                        vector_features_min_scale: Optional[int]) -> int:
    cur.execute(
        "SELECT PortalSwitchLayerId FROM PortalSwitchLayers WHERE PortalId=? AND SwitchKey=?",
        (portal_id, switch_key),
    )
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute(
        "INSERT INTO PortalSwitchLayers(PortalId, SwitchKey, VectorFeaturesMinScale) VALUES(?,?,?)",
        (portal_id, switch_key, vector_features_min_scale),
    )
    return int(cur.lastrowid)


def insert_switch_child(cur: sqlite3.Cursor, portal_switch_layer_id: int, service_layer_id: int) -> None:
    cur.execute(
        "SELECT 1 FROM PortalSwitchLayerChildren WHERE PortalSwitchLayerId=? AND ServiceLayerId=?",
        (portal_switch_layer_id, service_layer_id),
    )
    if cur.fetchone():
        return
    cur.execute(
        "INSERT INTO PortalSwitchLayerChildren(PortalSwitchLayerId, ServiceLayerId) VALUES(?,?)",
        (portal_switch_layer_id, service_layer_id),
    )


def index_exists(cur: sqlite3.Cursor, index_name: str) -> bool:
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (index_name,))
    return cur.fetchone() is not None


def fix_idproperty_unique_index(cur: sqlite3.Cursor) -> Tuple[bool, str]:
    """
    Replace UNIQUE(MapServerLayerId, IsIdProperty) with UNIQUE(MapServerLayerId) WHERE IsIdProperty=1
    so multiple non-id fields can exist.
    """
    idx_name = "idx_LayerFields_idProperty"
    if not index_exists(cur, idx_name):
        return False, "idx_LayerFields_idProperty not found, no change"

    # Inspect index definition
    cur.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (idx_name,))
    row = cur.fetchone()
    idx_sql = (row[0] or "") if row else ""

    # If it is already a partial index, leave it
    if "WHERE" in idx_sql.upper():
        return False, "idx_LayerFields_idProperty already partial, no change"

    # Drop and recreate as partial unique
    cur.execute(f"DROP INDEX IF EXISTS {idx_name}")
    cur.execute(
        f"CREATE UNIQUE INDEX {idx_name} ON MapServerLayerFields(MapServerLayerId) WHERE IsIdProperty = 1"
    )
    return True, "idx_LayerFields_idProperty replaced with partial unique index"


def ensure_unique_layer_key(cur: sqlite3.Cursor, desired_key: str) -> str:
    """
    ServiceLayers.LayerKey is UNIQUE across DB. If desired_key exists, append suffix _2, _3, ...
    """
    key = desired_key
    i = 2
    while True:
        cur.execute("SELECT 1 FROM ServiceLayers WHERE LayerKey=?", (key,))
        if not cur.fetchone():
            return key
        key = f"{desired_key}_{i}"
        i += 1


def ensure_both_service_types_for_all_mapserver_layers(cur: sqlite3.Cursor) -> int:
    """
    For every MapServerLayer, ensure a WMS and WFS ServiceLayer exists.
    Uses BaseLayerKey to derive stub keys: BASE_WMS and BASE_VECTOR.
    Does not invent FeatureType for WFS; leaves FeatureType and IdPropertyName NULL unless already known.
    Returns number of new ServiceLayers inserted.
    """
    inserted = 0

    cur.execute("SELECT MapServerLayerId, BaseLayerKey, DefaultGeomFieldName, DefaultLabelClassName, DefaultOpacity, GridXType FROM MapServerLayers")
    rows = cur.fetchall()

    for ms_id, base_key, geom_field, label_class, default_opacity, gridxtype in rows:
        ms_id = int(ms_id)
        base_key = (base_key or "").strip()
        if not base_key:
            continue

        # Check existing service rows for this MapServerLayerId
        cur.execute("SELECT ServiceType FROM ServiceLayers WHERE MapServerLayerId=?", (ms_id,))
        existing_types = {str(r[0]).upper() for r in cur.fetchall()}

        if WMS not in existing_types:
            key = ensure_unique_layer_key(cur, f"{base_key}_WMS")
            ensure_service_layer(
                cur,
                mapserver_layer_id=ms_id,
                service_type=WMS,
                layer_key=key,
                feature_type=None,
                id_property=None,
                geom_field=geom_field,
                label_class=label_class,
                opacity=default_opacity,
                openlayers=None,
                server_options=None,
                gridxtype=gridxtype,
                grouping=None,
            )
            inserted += 1

        if WFS not in existing_types:
            key = ensure_unique_layer_key(cur, f"{base_key}_VECTOR")
            ensure_service_layer(
                cur,
                mapserver_layer_id=ms_id,
                service_type=WFS,
                layer_key=key,
                feature_type=None,
                id_property=None,
                geom_field=geom_field,
                label_class=label_class,
                opacity=default_opacity,
                openlayers=None,
                server_options=None,
                gridxtype=gridxtype,
                grouping=None,
            )
            inserted += 1

    return inserted


def wipe_db(conn: sqlite3.Connection, wipe_tree_nodes: bool) -> None:
    # v3 FK constraints mean order matters.
    # PortalTreeNodes references ServiceLayers.LayerKey, so it can block wipes if present.
    conn.execute("PRAGMA foreign_keys=OFF")
    stmts = []
    if wipe_tree_nodes:
        stmts.append("DELETE FROM PortalTreeNodes")
    stmts.extend([
        "DELETE FROM PortalSwitchLayerChildren",
        "DELETE FROM PortalSwitchLayers",
        "DELETE FROM PortalLayers",
        "DELETE FROM ServiceLayerFields",
        "DELETE FROM ServiceLayerStyles",
        "DELETE FROM ServiceLayers",
        "DELETE FROM MapServerLayerFields",
        "DELETE FROM MapServerLayerStyles",
        "DELETE FROM MapServerLayers",
        "DELETE FROM Portals",
    ])
    for s in stmts:
        conn.execute(s)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()


def bootstrap(db_path: str, portal_files: List[PortalFiles], wipe_first: bool,
              wipe_tree_nodes: bool, fix_index: bool) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    cur = conn.cursor()

    if wipe_first:
        wipe_db(conn, wipe_tree_nodes=wipe_tree_nodes)

    index_note = None
    if fix_index:
        changed, msg = fix_idproperty_unique_index(cur)
        conn.commit()
        index_note = msg

    mapserver_id_by_name: Dict[str, int] = {}

    skipped_static = 0
    total_layers_seen = 0

    # Track any WFS field lists we see per canonical layer
    # key: MapLayerName (MapServer layer name), value: (field_list_in_order, id_property)
    wfs_fields_by_maplayer: Dict[str, Tuple[List[str], Optional[str]]] = {}

    # PASS 1: build MapServerLayers (and MapServer styles) from all WMS/WFS (including switch children)
    for pf in portal_files:
        doc = read_json(pf.json_path)
        ensure_portal(cur, pf.portal_key, pf.portal_title)

        for layer in doc.get("layers", []):
            total_layers_seen += 1
            lt = layer.get("layerType")

            if lt in SKIP_LAYER_TYPES:
                skipped_static += 1
                continue

            if lt not in SUPPORTED_LAYER_TYPES:
                continue

            to_process = []
            if lt == "switchlayer":
                to_process = layer.get("layers", [])
            else:
                to_process = [layer]

            for child in to_process:
                st = service_type_from_layer(child)
                name = canonical_maplayer_name_from_layer(child)
                if not st or not name:
                    continue

                gridxtype = child.get("gridXType") or ""
                label_class = child.get("labelClassName") or "labels"
                geom_field = child.get("geomFieldName") or "msGeometry"
                opacity = child.get("opacity")

                ms_id = mapserver_id_by_name.get(name)
                if ms_id is None:
                    ms_id = ensure_mapserver_layer(cur, name, gridxtype, label_class, geom_field, opacity)
                    mapserver_id_by_name[name] = ms_id

                # MapServer-level styles
                upsert_styles_for_mapserver(cur, ms_id, child.get("styles") or [])

                # Collect WFS propertyname fields for MapServerLayerFields import
                if st == WFS:
                    server_options = child.get("serverOptions") or {}
                    prop_fields = parse_propertyname_csv(server_options)
                    id_prop = child.get("idProperty")

                    if prop_fields:
                        prev = wfs_fields_by_maplayer.get(name)
                        if prev is None:
                            wfs_fields_by_maplayer[name] = (prop_fields, id_prop)
                        else:
                            # conservative merge: append any new fields, keep first-seen order
                            prev_fields, prev_id = prev
                            merged = list(prev_fields)
                            for f in prop_fields:
                                if f not in merged:
                                    merged.append(f)
                            # idProperty conflicts should be noted later, keep first-seen
                            wfs_fields_by_maplayer[name] = (merged, prev_id or id_prop)

    conn.commit()

    # PASS 1b: import MapServerLayerFields from collected WFS propertyname CSVs
    next_field_id = get_next_field_id(cur)
    idprop_conflicts: List[str] = []

    for maplayer_name, (field_list, id_prop) in wfs_fields_by_maplayer.items():
        ms_id = mapserver_id_by_name.get(maplayer_name)
        if not ms_id:
            continue

        # Basic sanity: if idProperty is not in propertyname list, still insert it as IsIdProperty=1 and include=1
        # but only if present (and not empty)
        if id_prop and id_prop not in field_list:
            field_list = list(field_list) + [id_prop]

        next_field_id = upsert_mapserver_fields_from_propertyname(
            cur,
            mapserver_layer_id=ms_id,
            field_names_in_order=field_list,
            id_property=id_prop,
            next_field_id=next_field_id,
        )

    conn.commit()

    # PASS 2: create ServiceLayers and portal membership and switch wrappers
    switch_wrappers = 0

    for pf in portal_files:
        doc = read_json(pf.json_path)
        portal_id = ensure_portal(cur, pf.portal_key, pf.portal_title)

        for layer in doc.get("layers", []):
            lt = layer.get("layerType")

            if lt in SKIP_LAYER_TYPES:
                continue

            if lt == "switchlayer":
                switch_key = layer.get("layerKey")
                if not switch_key:
                    continue
                vec_min_scale = safe_int(layer.get("vectorFeaturesMinScale"))
                sw_id = ensure_switch_layer(cur, portal_id, switch_key, vec_min_scale)
                switch_wrappers += 1

                for child in layer.get("layers", []):
                    st = service_type_from_layer(child)
                    name = canonical_maplayer_name_from_layer(child)
                    layer_key = child.get("layerKey")
                    if not st or not name or not layer_key:
                        continue

                    ms_id = mapserver_id_by_name[name]

                    service_id = ensure_service_layer(
                        cur,
                        mapserver_layer_id=ms_id,
                        service_type=st,
                        layer_key=layer_key,
                        feature_type=child.get("featureType"),
                        id_property=child.get("idProperty"),
                        geom_field=child.get("geomFieldName"),
                        label_class=child.get("labelClassName"),
                        opacity=child.get("opacity"),
                        openlayers=child.get("openLayers"),
                        server_options=child.get("serverOptions"),
                        gridxtype=child.get("gridXType"),
                        grouping=child.get("grouping"),
                    )

                    upsert_styles_for_service(cur, service_id, child.get("styles") or [])

                    prop_fields = parse_propertyname_csv(child.get("serverOptions"))
                    upsert_service_fields(cur, service_id, child.get("idProperty"), child.get("tooltipsConfig"), prop_fields)

                    # Switch child does not also get a PortalLayers row by default.
                    insert_switch_child(cur, sw_id, service_id)

            elif lt in {"wms", "wfs"}:
                st = service_type_from_layer(layer)
                name = canonical_maplayer_name_from_layer(layer)
                layer_key = layer.get("layerKey")
                if not st or not name or not layer_key:
                    continue

                ms_id = mapserver_id_by_name[name]

                service_id = ensure_service_layer(
                    cur,
                    mapserver_layer_id=ms_id,
                    service_type=st,
                    layer_key=layer_key,
                    feature_type=layer.get("featureType"),
                    id_property=layer.get("idProperty"),
                    geom_field=layer.get("geomFieldName"),
                    label_class=layer.get("labelClassName"),
                    opacity=layer.get("opacity"),
                    openlayers=layer.get("openLayers"),
                    server_options=layer.get("serverOptions"),
                    gridxtype=layer.get("gridXType"),
                    grouping=layer.get("grouping"),
                )

                upsert_styles_for_service(cur, service_id, layer.get("styles") or [])
                prop_fields = parse_propertyname_csv(layer.get("serverOptions"))
                upsert_service_fields(cur, service_id, layer.get("idProperty"), layer.get("tooltipsConfig"), prop_fields)

                is_enabled = 0 if layer.get("visibility") is False else 1
                insert_portal_layer(cur, portal_id, service_id, is_enabled=is_enabled)

    conn.commit()

    # PASS 3: ensure both WMS and WFS ServiceLayers exist for every MapServerLayer
    # This is your "can be added as WMS/WFS even if only defined as WMS in JSON" rule.
    new_stub_services = ensure_both_service_types_for_all_mapserver_layers(cur)
    conn.commit()

    def scalar(q: str) -> int:
        cur.execute(q)
        return int(cur.fetchone()[0])

    result = {
        "db": db_path,
        "portals": scalar("SELECT COUNT(*) FROM Portals"),
        "mapserver_layers": scalar("SELECT COUNT(*) FROM MapServerLayers"),
        "service_layers": scalar("SELECT COUNT(*) FROM ServiceLayers"),
        "portal_layers": scalar("SELECT COUNT(*) FROM PortalLayers"),
        "switch_wrappers": scalar("SELECT COUNT(*) FROM PortalSwitchLayers"),
        "switch_children": scalar("SELECT COUNT(*) FROM PortalSwitchLayerChildren"),
        "mapserver_styles": scalar("SELECT COUNT(*) FROM MapServerLayerStyles"),
        "service_styles": scalar("SELECT COUNT(*) FROM ServiceLayerStyles"),
        "service_fields": scalar("SELECT COUNT(*) FROM ServiceLayerFields"),
        "mapserver_fields": scalar("SELECT COUNT(*) FROM MapServerLayerFields"),
        "skipped_static_layers": skipped_static,
        "total_layers_seen": total_layers_seen,
        "new_stub_services": new_stub_services,
        "notes": [
            "Portal defaults and xyz/arcgisrest layers are skipped, v3 schema cannot represent them.",
            "PortalTreeNodes not imported (Tab 3).",
        ],
    }
    if index_note:
        result["index_note"] = index_note

    conn.close()
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True, help="Path to LayerConfig_v3.db (or your current db file)")
    p.add_argument("--layers-zip", required=True, help="Path to layers.zip containing portal layer JSONs")
    p.add_argument("--wipe-first", action="store_true", help="Wipe v3 tables before import")
    p.add_argument("--wipe-tree-nodes", action="store_true",
                   help="Also wipe PortalTreeNodes (only needed if they exist and block FK deletes)")
    p.add_argument("--no-fix-idproperty-index", action="store_true",
                   help="Do NOT replace idx_LayerFields_idProperty with partial unique index")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()

    portal_files = load_portal_files_from_zip(args.layers_zip)

    summary = bootstrap(
        db_path=args.db,
        portal_files=portal_files,
        wipe_first=args.wipe_first,
        wipe_tree_nodes=args.wipe_tree_nodes,
        fix_index=(not args.no_fix_idproperty_index),
    )

    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
