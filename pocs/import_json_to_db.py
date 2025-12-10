# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
import_json_to_db.py

Imports portal JSON configs (default/editor/nta_default/tii_default) into the
normalised JSON tables:

- Portals
- JsonGlobalDefaults
- JsonLayerTypeDefaults
- JsonLabelClasses
- JsonLayers
- JsonLayerWmsOptions
- JsonLayerWfsOptions
- JsonLayerArcGisRestOptions
- JsonLayerXyzOptions
- JsonLayerStyles
- JsonSwitchLayerChildren
"""

import argparse
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_PORTALS = {"default", "editor", "nta_default", "tii_default"}
LAYER_TYPE_KEYS = {"wms", "wfs", "xyz", "switchlayer", "arcgisrest"}


def as_bool(x: Any) -> Optional[int]:
    if x is None:
        return None
    return 1 if bool(x) else 0


def json_or_none(x: Any) -> Optional[str]:
    if x in (None, "", [], {}):
        return None
    return json.dumps(x, separators=(",", ":"))


# ---------------------------------------------------------------------
# portal + defaults
# ---------------------------------------------------------------------

def ensure_portal(conn: sqlite3.Connection, code: str) -> int:
    cur = conn.execute("SELECT PortalId FROM Portals WHERE code=?", (code,))
    row = cur.fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO Portals(code, title) VALUES (?, ?)",
        (code, code.replace("_", " ").title())
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def upsert_defaults(conn: sqlite3.Connection, portal_id: int, defaults: Dict[str, Any]):
    # clear existing for that portal
    conn.execute("DELETE FROM JsonGlobalDefaults WHERE portalId=?", (portal_id,))
    conn.execute("DELETE FROM JsonLayerTypeDefaults WHERE portalId=?", (portal_id,))

    for key, val in defaults.items():
        if key in LAYER_TYPE_KEYS and isinstance(val, dict):
            conn.execute(
                "INSERT INTO JsonLayerTypeDefaults(portalId, layerType, defaultsJSON) VALUES (?,?,?)",
                (portal_id, key, json.dumps(val, separators=(",", ":")))
            )
        else:
            conn.execute(
                "INSERT INTO JsonGlobalDefaults(portalId, key, valueJSON) VALUES (?,?,?)",
                (portal_id, key, json.dumps(val, separators=(",", ":")))
            )

    # make sure switchlayer exists
    cur = conn.execute(
        "SELECT 1 FROM JsonLayerTypeDefaults WHERE portalId=? AND layerType='switchlayer'",
        (portal_id,)
    )
    if not cur.fetchone():
        switchlayer_defaults = {
            "vectorFeaturesMinScale": 20000,
            "visibility": False,
            "featureInfoWindow": True,
        }
        conn.execute(
            "INSERT INTO JsonLayerTypeDefaults(portalId, layerType, defaultsJSON) VALUES (?,?,?)",
            (portal_id, "switchlayer", json.dumps(switchlayer_defaults, separators=(",", ":")))
        )


# ---------------------------------------------------------------------
# label classes
# ---------------------------------------------------------------------

def ensure_label_class(conn: sqlite3.Connection, name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    cur = conn.execute("SELECT LabelClassId FROM JsonLabelClasses WHERE name=?", (name,))
    row = cur.fetchone()
    if row:
        return row[0]
    conn.execute("INSERT INTO JsonLabelClasses(name) VALUES (?)", (name,))
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ---------------------------------------------------------------------
# layer core
# ---------------------------------------------------------------------

def upsert_layer_core(conn: sqlite3.Connection, portal_id: int, L: Dict[str, Any]) -> int:
    layer_key = L["layerKey"]
    layer_type = L["layerType"]

    label_class_id = ensure_label_class(conn, L.get("labelClassName"))

    cols = {
        "title": L.get("title"),
        "gridXType": L.get("gridXType"),
        "helpPage": L.get("helpPage"),
        "view": L.get("view"),
        "idProperty": L.get("idProperty"),
        "geomFieldName": L.get("geomFieldName"),
        "labelClassId": label_class_id,
        "noCluster": as_bool(L.get("noCluster")),
        "visibility": as_bool(L.get("visibility")),
        "featureInfoWindow": as_bool(L.get("featureInfoWindow")),
        "vectorFeaturesMinScale": L.get("vectorFeaturesMinScale"),
        "legendWidth": L.get("legendWidth"),
        "openLayersJSON": json_or_none(L.get("openLayers")),
        "groupingJSON": json_or_none(L.get("grouping")),
        "tooltipsConfigJSON": json_or_none(L.get("tooltipsConfig")),
        # from original JSONs
        "url": L.get("url"),
        "legendUrl": L.get("legendUrl"),
        "requestMethod": L.get("requestMethod"),
    }

    cur = conn.execute(
        "SELECT LayerId FROM JsonLayers WHERE PortalId=? AND layerKey=?",
        (portal_id, layer_key)
    )
    row = cur.fetchone()
    if row:
        layer_id = row[0]
        conn.execute(
            """
            UPDATE JsonLayers
               SET layerType=?,
                   title=?,
                   gridXType=?,
                   helpPage=?,
                   view=?,
                   idProperty=?,
                   geomFieldName=?,
                   labelClassId=?,
                   noCluster=?,
                   visibility=?,
                   featureInfoWindow=?,
                   vectorFeaturesMinScale=?,
                   legendWidth=?,
                   openLayersJSON=?,
                   groupingJSON=?,
                   tooltipsConfigJSON=?,
                   url=?,
                   legendUrl=?,
                   requestMethod=?
             WHERE LayerId=?
            """,
            (
                layer_type,
                cols["title"],
                cols["gridXType"],
                cols["helpPage"],
                cols["view"],
                cols["idProperty"],
                cols["geomFieldName"],
                cols["labelClassId"],
                cols["noCluster"],
                cols["visibility"],
                cols["featureInfoWindow"],
                cols["vectorFeaturesMinScale"],
                cols["legendWidth"],
                cols["openLayersJSON"],
                cols["groupingJSON"],
                cols["tooltipsConfigJSON"],
                cols["url"],
                cols["legendUrl"],
                cols["requestMethod"],
                layer_id,
            ),
        )
        return layer_id

    conn.execute(
        """
        INSERT INTO JsonLayers (
            PortalId, layerKey, layerType,
            title, gridXType, helpPage, view,
            idProperty, geomFieldName, labelClassId,
            noCluster, visibility, featureInfoWindow,
            vectorFeaturesMinScale, legendWidth,
            openLayersJSON, groupingJSON, tooltipsConfigJSON,
            url, legendUrl, requestMethod
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            portal_id,
            layer_key,
            layer_type,
            cols["title"],
            cols["gridXType"],
            cols["helpPage"],
            cols["view"],
            cols["idProperty"],
            cols["geomFieldName"],
            cols["labelClassId"],
            cols["noCluster"],
            cols["visibility"],
            cols["featureInfoWindow"],
            cols["vectorFeaturesMinScale"],
            cols["legendWidth"],
            cols["openLayersJSON"],
            cols["groupingJSON"],
            cols["tooltipsConfigJSON"],
            cols["url"],
            cols["legendUrl"],
            cols["requestMethod"],
        ),
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


# ---------------------------------------------------------------------
# server options writers
# ---------------------------------------------------------------------

def write_wms_options(conn: sqlite3.Connection, layer_id: int, L: Dict[str, Any]):
    so = L.get("serverOptions") or {}
    ol = L.get("openLayers") or {}
    conn.execute("DELETE FROM JsonLayerWmsOptions WHERE LayerId=?", (layer_id,))
    conn.execute(
        """
        INSERT INTO JsonLayerWmsOptions(
            LayerId, layers, orderBy, styles,
            version, maxResolution, requestMethod, dateFormat
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        (
            layer_id,
            so.get("layers"),
            so.get("ORDERBY") or so.get("orderBy"),
            so.get("styles"),
            so.get("version"),
            so.get("maxResolution") or ol.get("maxResolution"),
            L.get("requestMethod") or L.get("requestmethod") or "POST",
            L.get("dateFormat") or "Y-m-d",
        ),
    )


def write_wfs_options(conn: sqlite3.Connection, layer_id: int, L: Dict[str, Any]):
    so = L.get("serverOptions") or {}
    conn.execute("DELETE FROM JsonLayerWfsOptions WHERE LayerId=?", (layer_id,))
    conn.execute(
        """
        INSERT INTO JsonLayerWfsOptions(
            LayerId, featureType, propertyName,
            version, maxResolution
        ) VALUES (?,?,?,?,?)
        """,
        (
            layer_id,
            L.get("featureType"),
            so.get("propertyname"),
            so.get("version"),
            so.get("maxResolution"),
        ),
    )


def write_arcgisrest_options(conn: sqlite3.Connection, layer_id: int, L: Dict[str, Any]):
    url = L.get("url")
    conn.execute("DELETE FROM JsonLayerArcGisRestOptions WHERE LayerId=?", (layer_id,))
    conn.execute(
        "INSERT INTO JsonLayerArcGisRestOptions(LayerId, url) VALUES (?, ?)",
        (layer_id, url),
    )


def parse_url_tokenize(url: str) -> Tuple[str, Optional[str]]:
    if not isinstance(url, str):
        return url, None
    low = url.lower()
    if "access_token=" in low:
        base, _, qs = url.partition("?")
        token = None
        new_parts = []
        if qs:
            for part in qs.split("&"):
                if part.startswith("access_token="):
                    token = part.split("=", 1)[1]
                    new_parts.append("access_token={MAPBOX_TOKEN}")
                else:
                    new_parts.append(part)
        new_url = base
        if new_parts:
            new_url = base + "?" + "&".join(new_parts)
        return new_url, token
    return url, None


def write_xyz_options(conn: sqlite3.Connection, layer_id: int, L: Dict[str, Any]):
    url = L.get("url")
    conn.execute("DELETE FROM JsonLayerXyzOptions WHERE LayerId=?", (layer_id,))
    if not url:
        return
    url_tpl, token = parse_url_tokenize(url)
    ol = L.get("openLayers") or {}
    conn.execute(
        """
        INSERT INTO JsonLayerXyzOptions(
            LayerId, urlTemplate, accessToken, projection,
            tileSize, attributionHTML, extentJSON, tileGridJSON, isBaseLayer
        ) VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            layer_id,
            url_tpl,
            token,
            ol.get("projection"),
            ol.get("tileSize"),
            ol.get("attribution"),
            json_or_none(ol.get("extent")),
            json_or_none(ol.get("tileGrid")),
            as_bool(L.get("isBaseLayer")),
        ),
    )


# ---------------------------------------------------------------------
# styles
# ---------------------------------------------------------------------

def replace_styles(conn: sqlite3.Connection, layer_id: int, styles: List[Dict[str, Any]]):
    if not styles:
        return
    order = 1
    for s in styles:
        name = s.get("name")
        if not name:
            continue
        title = s.get("title") or name
        label_rule = s.get("labelRule")
        legend_url = s.get("legendUrl")

        conn.execute(
            """
            INSERT INTO JsonLayerStyles (
                LayerId, name, title, labelRule, legendUrl, displayOrder
            ) VALUES (?,?,?,?,?,?)
            ON CONFLICT(LayerId, name) DO UPDATE SET
                title=excluded.title,
                labelRule=excluded.labelRule,
                legendUrl=excluded.legendUrl,
                displayOrder=excluded.displayOrder
            """,
            (layer_id, name, title, label_rule, legend_url, order),
        )
        order += 1




# ---------------------------------------------------------------------
# main import passes
# ---------------------------------------------------------------------

def import_layers(conn: sqlite3.Connection, portal_id: int, layers: List[Dict[str, Any]]):
    layer_id_by_key: Dict[str, int] = {}

    # pass 1: create/update all
    for L in layers:
        layer_id = upsert_layer_core(conn, portal_id, L)
        layer_id_by_key[L["layerKey"]] = layer_id

        lt = L["layerType"]
        if lt == "wms":
            write_wms_options(conn, layer_id, L)
            replace_styles(conn, layer_id, L.get("styles") or [])
        elif lt == "wfs":
            write_wfs_options(conn, layer_id, L)
            replace_styles(conn, layer_id, L.get("styles") or [])
        elif lt == "arcgisrest":
            write_arcgisrest_options(conn, layer_id, L)
            replace_styles(conn, layer_id, L.get("styles") or [])
        elif lt == "xyz":
            write_xyz_options(conn, layer_id, L)
        elif lt == "switchlayer":
            # options come from JsonLayerTypeDefaults
            pass

    # pass 2: build switchlayer children
    for L in layers:
        if L.get("layerType") != "switchlayer":
            continue
        parent_id = layer_id_by_key[L["layerKey"]]
        conn.execute("DELETE FROM JsonSwitchLayerChildren WHERE ParentLayerId=?", (parent_id,))
        children = L.get("layers") or []
        pos = 1
        for child in children:
            ck = child["layerKey"]

            if ck not in layer_id_by_key:
                # brand new child: create everything
                child_id = upsert_layer_core(conn, portal_id, child)
                layer_id_by_key[ck] = child_id
                lt2 = child["layerType"]
                if lt2 == "wms":
                    write_wms_options(conn, child_id, child)
                    replace_styles(conn, child_id, child.get("styles") or [])
                elif lt2 == "wfs":
                    write_wfs_options(conn, child_id, child)
                    replace_styles(conn, child_id, child.get("styles") or [])
                elif lt2 == "arcgisrest":
                    write_arcgisrest_options(conn, child_id, child)
                    replace_styles(conn, child_id, child.get("styles") or [])
                elif lt2 == "xyz":
                    write_xyz_options(conn, child_id, child)
            else:
                # child already exists as a top-level layer (created in pass 1)
                # -> just link it, skip options/styles to avoid UNIQUE collisions
                child_id = layer_id_by_key[ck]

            # create or re-create the link
            conn.execute(
                "INSERT INTO JsonSwitchLayerChildren (ParentLayerId, ChildLayerId, position) VALUES (?,?,?)",
                (parent_id, child_id, pos),
            )
            pos += 1



def import_file(conn: sqlite3.Connection, portal_id: int, path: str):
    with open(path, "r", encoding="utf-8-sig") as f:
        doc = json.load(f)

    defaults = doc.get("defaults") or {}
    upsert_defaults(conn, portal_id, defaults)

    layers = doc.get("layers") or []
    import_layers(conn, portal_id, layers)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--portal", required=True)
    ap.add_argument("--json", action="append", required=True)
    args = ap.parse_args()

    if args.portal not in ALLOWED_PORTALS:
        raise SystemExit("Invalid --portal. Allowed: " + ", ".join(sorted(ALLOWED_PORTALS)))

    conn = sqlite3.connect(args.db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        portal_id = ensure_portal(conn, args.portal)

        started_tx = False
        if not conn.in_transaction:
            conn.execute("BEGIN")
            started_tx = True

        for p in args.json:
            import_file(conn, portal_id, p)

        if started_tx:
            conn.execute("COMMIT")
        print(f"Imported {len(args.json)} file(s) into portal '{args.portal}' (PortalId={portal_id}).")
    except Exception:
        if 'started_tx' in locals() and started_tx:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
