# -*- coding: utf-8 -*-
#!/usr/bin/env python3

import argparse
import json
import sqlite3
from typing import Any, Dict, List, Optional

CORE_TYPES = {"wms", "wfs", "xyz", "arcgisrest", "switchlayer"}


def json_loads_or_none(s: Optional[str]):
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def deep_equal(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(deep_equal(x, y) for x, y in zip(a, b))
    return a == b


def remove_defaults(obj: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        if k not in defaults:
            out[k] = v
            continue
        dv = defaults[k]
        if isinstance(v, dict) and isinstance(dv, dict):
            pruned = remove_defaults(v, dv)
            if pruned:
                out[k] = pruned
        else:
            if not deep_equal(v, dv):
                out[k] = v
    return out


def load_defaults(conn: sqlite3.Connection, portal_code: str):
    conn.row_factory = sqlite3.Row

    row = conn.execute("SELECT PortalId FROM Portals WHERE code=?", (portal_code,)).fetchone()
    if not row:
        raise SystemExit("Portal '%s' not found." % portal_code)
    portal_id = row["PortalId"]

    defaults: Dict[str, Any] = {}

    # global defaults (prefixed table)
    for r in conn.execute(
        "SELECT key, valueJSON FROM JsonGlobalDefaults WHERE portalId=?",
        (portal_id,),
    ):
        defaults[r["key"]] = json_loads_or_none(r["valueJSON"])

    # layer-type defaults (prefixed table)
    for r in conn.execute(
        "SELECT layerType, defaultsJSON FROM JsonLayerTypeDefaults WHERE portalId=?",
        (portal_id,),
    ):
        parsed = json_loads_or_none(r["defaultsJSON"]) or {}
        if not isinstance(parsed, dict):
            raise SystemExit(
                "JsonLayerTypeDefaults.%s is not a JSON object for portal '%s'."
                % (r["layerType"], portal_code)
            )
        defaults[r["layerType"]] = parsed

    # we can warn if any of the usual types are missing
    needed = ("wms", "wfs", "xyz", "arcgisrest", "switchlayer")
    missing = [t for t in needed if t not in defaults]
    if missing:
        print("Warning, missing per-type defaults for: %s" % ", ".join(missing))

    return defaults, portal_id


def label_name_for(conn: sqlite3.Connection, label_class_id: Optional[int]) -> Optional[str]:
    if label_class_id is None:
        return None
    r = conn.execute(
        "SELECT name FROM JsonLabelClasses WHERE LabelClassId=?",
        (label_class_id,),
    ).fetchone()
    return r["name"] if r else None


def build_styles(conn: sqlite3.Connection, layer_id: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in conn.execute(
        """
        SELECT name, title, labelRule, legendUrl
        FROM JsonLayerStyles
        WHERE LayerId=?
        ORDER BY displayOrder, name
        """,
        (layer_id,),
    ):
        item: Dict[str, Any] = {"name": r["name"], "title": r["title"]}
        if r["labelRule"]:
            item["labelRule"] = r["labelRule"]
        if r["legendUrl"]:
            item["legendUrl"] = r["legendUrl"]
        out.append(item)
    return out


def build_wms(conn: sqlite3.Connection, layer_id: int) -> Optional[Dict[str, Any]]:
    r = conn.execute(
        """
        SELECT layers, orderBy, styles, version, maxResolution, requestMethod, dateFormat
        FROM JsonLayerWmsOptions
        WHERE LayerId=?
        """,
        (layer_id,),
    ).fetchone()
    if not r:
        return None
    so: Dict[str, Any] = {}
    if r["layers"]:
        so["layers"] = r["layers"]
    if r["orderBy"]:
        # JSON had ORDERBY in places, but we store orderBy in db
        so["ORDERBY"] = r["orderBy"]
    if r["styles"]:
        so["styles"] = r["styles"]
    if r["version"]:
        so["version"] = r["version"]
    if r["maxResolution"] is not None:
        so["maxResolution"] = r["maxResolution"]
    if r["requestMethod"]:
        so["requestMethod"] = r["requestMethod"]
    if r["dateFormat"]:
        so["dateFormat"] = r["dateFormat"]
    return so


def build_wfs(conn: sqlite3.Connection, layer_id: int):
    r = conn.execute(
        """
        SELECT featureType, propertyName, version, maxResolution
        FROM JsonLayerWfsOptions
        WHERE LayerId=?
        """,
        (layer_id,),
    ).fetchone()
    if not r:
        return None, None
    so: Dict[str, Any] = {}
    if r["propertyName"]:
        so["propertyname"] = r["propertyName"]
    if r["version"]:
        so["version"] = r["version"]
    if r["maxResolution"] is not None:
        so["maxResolution"] = r["maxResolution"]
    return so, r["featureType"]


def build_arcgisrest(conn: sqlite3.Connection, layer_id: int) -> Optional[Dict[str, Any]]:
    r = conn.execute(
        "SELECT url FROM JsonLayerArcGisRestOptions WHERE LayerId=?",
        (layer_id,),
    ).fetchone()
    if not r:
        return None
    return {"url": r["url"]}


def build_xyz(conn: sqlite3.Connection, layer_id: int, base_openlayers: Optional[Dict[str, Any]]):
    r = conn.execute(
        """
        SELECT urlTemplate, accessToken, projection, tileSize, attributionHTML, extentJSON, tileGridJSON, isBaseLayer
        FROM JsonLayerXyzOptions
        WHERE LayerId=?
        """,
        (layer_id,),
    ).fetchone()
    if not r:
        return None, base_openlayers

    url = r["urlTemplate"]
    token = r["accessToken"]
    if url and "{MAPBOX_TOKEN}" in url and token:
        url = url.replace("{MAPBOX_TOKEN}", token)

    # merge openLayers
    ol = dict(base_openlayers) if isinstance(base_openlayers, dict) else {}
    if r["projection"]:
        ol["projection"] = r["projection"]
    if r["tileSize"] is not None:
        ol["tileSize"] = r["tileSize"]
    if r["attributionHTML"]:
        ol["attribution"] = r["attributionHTML"]
    ext = json_loads_or_none(r["extentJSON"])
    tg = json_loads_or_none(r["tileGridJSON"])
    if ext:
        ol["extent"] = ext
    if tg:
        ol["tileGrid"] = tg
    if r["isBaseLayer"] is not None:
        # original JSON usually had isBaseLayer on layer itself
        pass

    return {"url": url}, (ol if ol else base_openlayers)


def build_layer(conn: sqlite3.Connection, row: sqlite3.Row, type_defaults: Dict[str, Any]) -> Dict[str, Any]:
    lt = row["layerType"]
    out: Dict[str, Any] = {
        "layerType": lt,
        "layerKey": row["layerKey"],
    }

    if row["title"]:
        out["title"] = row["title"]
    if row["gridXType"]:
        out["gridXType"] = row["gridXType"]
    if row["idProperty"]:
        out["idProperty"] = row["idProperty"]

    label_name = label_name_for(conn, row["labelClassId"])
    if label_name:
        out["labelClassName"] = label_name

    if row["legendWidth"] is not None:
        out["legendWidth"] = row["legendWidth"]
    if row["visibility"] is not None:
        out["visibility"] = bool(row["visibility"])
    if row["vectorFeaturesMinScale"] is not None:
        out["vectorFeaturesMinScale"] = row["vectorFeaturesMinScale"]
    if row["featureInfoWindow"] is not None:
        out["featureInfoWindow"] = bool(row["featureInfoWindow"])

    ol_base = json_loads_or_none(row["openLayersJSON"])
    if isinstance(ol_base, dict) and ol_base:
        out["openLayers"] = dict(ol_base)

    tips = json_loads_or_none(row["tooltipsConfigJSON"])
    if isinstance(tips, list) and tips:
        out["tooltipsConfig"] = tips

    grp = json_loads_or_none(row["groupingJSON"])
    if isinstance(grp, dict) and grp:
        out["grouping"] = grp

    if lt == "wms":
        so = build_wms(conn, row["LayerId"])
        if so:
            out["serverOptions"] = so
        styles = build_styles(conn, row["LayerId"])
        if styles:
            out["styles"] = styles

    elif lt == "wfs":
        so, ft = build_wfs(conn, row["LayerId"])
        if so:
            out["serverOptions"] = so
        if ft:
            out["featureType"] = ft
        if row["geomFieldName"]:
            out["geomFieldName"] = row["geomFieldName"]
        styles = build_styles(conn, row["LayerId"])
        if styles:
            out["styles"] = styles

    elif lt == "arcgisrest":
        so = build_arcgisrest(conn, row["LayerId"])
        if so:
            out.update(so)
        styles = build_styles(conn, row["LayerId"])
        if styles:
            out["styles"] = styles

    elif lt == "xyz":
        xo, new_ol = build_xyz(conn, row["LayerId"], out.get("openLayers"))
        if xo:
            out.update(xo)
        if new_ol:
            out["openLayers"] = new_ol

    elif lt == "switchlayer":
        children: List[Dict[str, Any]] = []
        cur = conn.execute(
            """
            SELECT L.*
            FROM JsonSwitchLayerChildren C
            JOIN JsonLayers L ON L.LayerId = C.ChildLayerId
            WHERE C.ParentLayerId = ?
            ORDER BY C.position
            """,
            (row["LayerId"],),
        )
        for ch in cur.fetchall():
            children.append(build_layer(conn, ch, type_defaults))
        out["layers"] = children

    # prune by per-type defaults
    td = type_defaults.get(lt, {})
    if isinstance(td, dict) and td:
        out = remove_defaults(out, td)

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--portal", required=True, help="Portal code: default|editor|nta_default|tii_default")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    defaults, portal_id = load_defaults(conn, args.portal)
    type_defaults = {k: v for k, v in defaults.items() if isinstance(v, dict) and k in CORE_TYPES}

    # top level layers are layers that are not children
    cur = conn.execute(
        """
        SELECT *
        FROM JsonLayers
        WHERE PortalId=?
          AND LayerId NOT IN (SELECT ChildLayerId FROM JsonSwitchLayerChildren)
        ORDER BY layerType, layerKey
        """,
        (portal_id,),
    )
    layers_out: List[Dict[str, Any]] = [build_layer(conn, row, type_defaults) for row in cur.fetchall()]

    doc = {
        "defaults": defaults,
        "layers": layers_out,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        "Wrote %s with %d top-level layers for portal '%s'."
        % (args.out, len(layers_out), args.portal)
    )


if __name__ == "__main__":
    main()
