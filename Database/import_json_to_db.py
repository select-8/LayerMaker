# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
import_json_to_db.py

Load one or more normalised JSON layer-config files into an SQLite DB,
scoped by a portal code: default, editor, nta_default, tii_default.

- Assumes DB created by create_db_clean.sql (portal-aware schema).
- Creates the portal row if missing.
- Writes GlobalDefaults and LayerTypeDefaults for that portal (replaces existing).
- Inserts/updates Layers, LayerServerOptions, LayerXYZOptions, LayerStyles.
- Builds SwitchLayerChildren after all layers are present (so FKs resolve).
- Keeps 1 row per (portalId, layerKey).

Usage:
  python import_json_to_db.py --db LayerConfig.db --portal default --json default.json [--json other.json]

Only stdlib used.
"""
import argparse
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_PORTALS = {"default","editor","nta_default","tii_default"}

def as_bool(x):
    return None if x is None else (1 if bool(x) else 0)

def json_or_none(x):
    return None if x in (None, "", []) else json.dumps(x, separators=(",", ":"))

def ensure_portal(conn: sqlite3.Connection, code: str) -> int:
    cur = conn.execute("SELECT PortalId FROM Portals WHERE code=?", (code,))
    row = cur.fetchone()
    if row:
        return row[0]
    conn.execute("INSERT INTO Portals(code, title) VALUES (?, ?)", (code, code.title()))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

def upsert_defaults(conn: sqlite3.Connection, portal_id: int, defaults: Dict[str, Any]):
    layer_type_keys = {"wms","wfs","xyz","switchlayer","arcgisrest"}
    conn.execute("DELETE FROM GlobalDefaults WHERE portalId=?", (portal_id,))
    conn.execute("DELETE FROM LayerTypeDefaults WHERE portalId=?", (portal_id,))
    for k, v in defaults.items():
        if k in layer_type_keys and isinstance(v, dict):
            conn.execute(
                "INSERT INTO LayerTypeDefaults(portalId, layerType, defaultsJSON) VALUES (?,?,?)",
                (portal_id, k, json.dumps(v, separators=(",", ":"))),
            )
        else:
            conn.execute(
                "INSERT INTO GlobalDefaults(portalId, key, valueJSON) VALUES (?,?,?)",
                (portal_id, k, json.dumps(v, separators=(",", ":"))),
            )

def parse_url_tokenize(url: str) -> Tuple[str, Optional[str]]:
    if not isinstance(url, str):
        return url, None
    low = url.lower()
    if "access_token=" in low:
        try:
            base, query = url.split("?", 1)
        except ValueError:
            base, query = url, ""
        parts = query.split("&") if query else []
        token = None
        new_parts = []
        for p in parts:
            if p.startswith("access_token="):
                token = p.split("=", 1)[1]
                new_parts.append("access_token={MAPBOX_TOKEN}")
            else:
                new_parts.append(p)
        new_query = "&".join(new_parts)
        new_url = base + ("?" + new_query if new_query else "")
        return new_url, token
    return url, None

def upsert_layer_core(conn: sqlite3.Connection, portal_id: int, L: Dict[str, Any]) -> int:
    layerKey = L["layerKey"]
    layerType = L["layerType"]
    cols = {
        "title": L.get("title"),
        "gridXType": L.get("gridXType"),
        "idProperty": L.get("idProperty"),
        "featureType": L.get("featureType") if layerType == "wfs" else None,
        "geomFieldName": L.get("geomFieldName") if layerType == "wfs" else None,
        "labelClassName": L.get("labelClassName"),
        "legendWidth": L.get("legendWidth"),
        "visibilityDefault": as_bool(L.get("visibility")),
        "vectorFeaturesMinScale": L.get("vectorFeaturesMinScale"),
        "featureInfoWindow": as_bool(L.get("featureInfoWindow")),
        "hasMetadata": as_bool(L.get("hasMetadata")),
        "isBaseLayer": as_bool(L.get("isBaseLayer")),
        "qtip": L.get("qtip"),
        "openLayersJSON": json_or_none(L.get("openLayers")),
        "tooltipsJSON": json_or_none(L.get("tooltipsConfig")),
        "groupingJSON": json_or_none(L.get("grouping")),
    }
    conn.execute(
        """
        INSERT INTO Layers (portalId, layerKey, layerType, title, gridXType, idProperty, featureType, geomFieldName,
                            labelClassName, legendWidth, visibilityDefault, vectorFeaturesMinScale, featureInfoWindow,
                            hasMetadata, isBaseLayer, qtip, openLayersJSON, tooltipsJSON, groupingJSON)
        VALUES (:portalId, :layerKey, :layerType, :title, :gridXType, :idProperty, :featureType, :geomFieldName,
                :labelClassName, :legendWidth, COALESCE(:visibilityDefault,0), :vectorFeaturesMinScale, :featureInfoWindow,
                :hasMetadata, :isBaseLayer, :qtip, :openLayersJSON, :tooltipsJSON, :groupingJSON)
        ON CONFLICT(portalId, layerKey) DO UPDATE SET
          layerType=excluded.layerType,
          title=excluded.title,
          gridXType=excluded.gridXType,
          idProperty=excluded.idProperty,
          featureType=excluded.featureType,
          geomFieldName=excluded.geomFieldName,
          labelClassName=excluded.labelClassName,
          legendWidth=excluded.legendWidth,
          visibilityDefault=excluded.visibilityDefault,
          vectorFeaturesMinScale=excluded.vectorFeaturesMinScale,
          featureInfoWindow=excluded.featureInfoWindow,
          hasMetadata=excluded.hasMetadata,
          isBaseLayer=excluded.isBaseLayer,
          qtip=excluded.qtip,
          openLayersJSON=excluded.openLayersJSON,
          tooltipsJSON=excluded.tooltipsJSON,
          groupingJSON=excluded.groupingJSON
        """,
        {
            "portalId": portal_id,
            "layerKey": layerKey,
            "layerType": layerType,
            **cols
        },
    )
    row = conn.execute("SELECT LayerId FROM Layers WHERE portalId=? AND layerKey=?", (portal_id, layerKey)).fetchone()
    return row[0]

def upsert_server_options(conn: sqlite3.Connection, layer_id: int, so: Dict[str, Any]):
    if not so:
        conn.execute("DELETE FROM LayerServerOptions WHERE LayerId=?", (layer_id,))
        return
    wmsLayers = so.get("layers")
    orderBy  = so.get("ORDERBY") or so.get("orderBy")
    propname = so.get("propertyname")
    version  = so.get("version")
    maxRes   = so.get("maxResolution")
    conn.execute(
        """
        INSERT INTO LayerServerOptions (LayerId, wmsLayers, "orderBy", propertyName, "version", maxResolution)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(LayerId) DO UPDATE SET
          wmsLayers=excluded.wmsLayers,
          "orderBy"=excluded."orderBy",
          propertyName=excluded.propertyName,
          "version"=excluded."version",
          maxResolution=excluded.maxResolution
        """,
        (layer_id, wmsLayers, orderBy, propname, version, maxRes),
    )

def upsert_xyz_options(conn: sqlite3.Connection, layer_id: int, layer_obj: Dict[str, Any]):
    url = layer_obj.get("url")
    if not url:
        conn.execute("DELETE FROM LayerXYZOptions WHERE LayerId=?", (layer_id,))
        return
    url_tpl, token = parse_url_tokenize(url)
    ol = layer_obj.get("openLayers") or {}
    projection = ol.get("projection")
    tileSize   = ol.get("tileSize")
    attribution= ol.get("attribution")
    extentJSON = json_or_none(ol.get("extent"))
    tileGrid   = json_or_none(ol.get("tileGrid"))
    conn.execute(
        """
        INSERT INTO LayerXYZOptions (LayerId, urlTemplate, accessToken, projection, tileSize, attributionHTML, extentJSON, tileGridJSON)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(LayerId) DO UPDATE SET
          urlTemplate=excluded.urlTemplate,
          accessToken=COALESCE(excluded.accessToken, LayerXYZOptions.accessToken),
          projection=excluded.projection,
          tileSize=excluded.tileSize,
          attributionHTML=excluded.attributionHTML,
          extentJSON=excluded.extentJSON,
          tileGridJSON=excluded.tileGridJSON
        """,
        (layer_id, url_tpl, token, projection, tileSize, attribution, extentJSON, tileGrid),
    )

def replace_styles(conn: sqlite3.Connection, layer_id: int, styles: List[Dict[str, Any]]):
    conn.execute("DELETE FROM LayerStyles WHERE LayerId=?", (layer_id,))
    if not styles:
        return
    order = 1
    for s in styles:
        name = s.get("name")
        if not name:
            continue
        title = s.get("title") or name
        labelRule = s.get("labelRule")
        legendUrl = s.get("legendUrl")
        isDefault = 1 if s is styles[0] else 0
        conn.execute(
            "INSERT INTO LayerStyles (LayerId, name, title, labelRule, legendUrl, isDefault, displayOrder) VALUES (?,?,?,?,?,?,?)",
            (layer_id, name, title, labelRule, legendUrl, isDefault, order),
        )
        order += 1

def import_layers(conn: sqlite3.Connection, portal_id: int, layers: List[Dict[str, Any]]):
    id_by_key: Dict[str, int] = {}
    for L in layers:
        lid = upsert_layer_core(conn, portal_id, L)
        id_by_key[L["layerKey"]] = lid
        if L["layerType"] in ("wms","wfs","arcgisrest"):
            upsert_server_options(conn, lid, L.get("serverOptions") or {})
            replace_styles(conn, lid, L.get("styles") or [])
        elif L["layerType"] == "xyz":
            upsert_xyz_options(conn, lid, L)
    for L in layers:
        if L["layerType"] != "switchlayer":
            continue
        parent_id = id_by_key[L["layerKey"]]
        conn.execute("DELETE FROM SwitchLayerChildren WHERE ParentLayerId=?", (parent_id,))
        children = L.get("layers") or []
        pos = 1
        for child in children:
            ck = child["layerKey"]
            if ck not in id_by_key:
                child_id = upsert_layer_core(conn, portal_id, child)
                id_by_key[ck] = child_id
                if child["layerType"] in ("wms","wfs","arcgisrest"):
                    upsert_server_options(conn, child_id, child.get("serverOptions") or {})
                    replace_styles(conn, child_id, child.get("styles") or [])
                elif child["layerType"] == "xyz":
                    upsert_xyz_options(conn, child_id, child)
            else:
                child_id = id_by_key[ck]
            conn.execute(
                "INSERT INTO SwitchLayerChildren (ParentLayerId, ChildLayerId, position) VALUES (?,?,?)",
                (parent_id, child_id, pos),
            )
            pos += 1

def import_file(conn: sqlite3.Connection, portal_id: int, path: str):
    # Use utf-8-sig to handle BOM-ed JSON files (common on Windows)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            doc = json.load(f)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Failed to parse JSON '{path}': {e}. If this file has comments/trailing commas, remove them.")
    defaults = doc.get("defaults") or {}
    upsert_defaults(conn, portal_id, defaults)
    layers = doc.get("layers") or []
    import_layers(conn, portal_id, layers)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to SQLite DB")
    ap.add_argument("--portal", required=True, help="Portal code: default|editor|nta_default|tii_default")
    ap.add_argument("--json", action="append", required=True, help="Path to a JSON file (repeatable)")
    args = ap.parse_args()

    if args.portal not in ALLOWED_PORTALS:
        raise SystemExit("Invalid --portal. Allowed: " + ", ".join(sorted(ALLOWED_PORTALS)))

    conn = sqlite3.connect(args.db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        portal_id = ensure_portal(conn, args.portal)
        conn.execute("BEGIN")
        for p in args.json:
            import_file(conn, portal_id, p)
        conn.execute("COMMIT")
        print("Imported {} file(s) into portal '{}' (PortalId={}).".format(len(args.json), args.portal, portal_id))
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
