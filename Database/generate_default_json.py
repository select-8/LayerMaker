# -*- coding: utf-8 -*-
#!/usr/bin/env python3

"""
generate_default_json.py

Read a MapMaker layer-config SQLite DB and emit a normalised default.json:
- defaults = GlobalDefaults + LayerTypeDefaults (wms/wfs/xyz/switchlayer/arcgisrest)
- layers built from Layers + LayerServerOptions/LayerXYZOptions + LayerStyles + SwitchLayerChildren
- optional environment overrides (EnvironmentOverrides) for global, layerType, and layer scopes
- layer objects are pruned of any keys equal to their layer-type defaults

Usage:
  python generate_default_json.py --db path/to/config.db --out default.json [--env prod]

Only stdlib is used.
"""

import argparse
import json
import sqlite3
from typing import Any, Dict, List, Optional, Tuple, Iterable
import sys

def json_loads_or_none(s: Optional[str]) -> Optional[Any]:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s

def deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v
    return dst

def deep_equal(a: Any, b: Any) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(deep_equal(x, y) for x, y in zip(a, b))
    return a == b

def remove_defaults(obj: Any, defaults: Any) -> Any:
    if not isinstance(obj, dict) or not isinstance(defaults, dict):
        return obj
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

def ensure_styles_array(rows: Iterable[Tuple[str, str, Optional[str], Optional[str], int, int]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name, title, label_rule, legend_url, is_default, display_order in rows:
        item: Dict[str, Any] = {"name": name, "title": title}
        if label_rule:
            item["labelRule"] = label_rule
        if legend_url:
            item["legendUrl"] = legend_url
        out.append(item)
    return out

def load_defaults(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Return the 'defaults' dict exactly as stored in the DB (no env required)."""
    defaults: Dict[str, Any] = {}

    # Global defaults -> top-level keys under "defaults"
    cur = conn.execute("SELECT key, valueJSON FROM GlobalDefaults")
    for key, valueJSON in cur.fetchall():
        defaults[key] = json_loads_or_none(valueJSON)

    # Per-layer-type defaults -> nested objects under "defaults"
    cur = conn.execute("SELECT layerType, defaultsJSON FROM LayerTypeDefaults")
    for layer_type, defaultsJSON in cur.fetchall():
        parsed = json_loads_or_none(defaultsJSON) or {}
        if not isinstance(parsed, dict):
            raise ValueError(f"LayerTypeDefaults.{layer_type} is not a JSON object")
        defaults[layer_type] = parsed

    # Hard check: make sure the key layer types exist
    required_types = {"wms","wfs","xyz","switchlayer","arcgisrest"}
    missing = sorted(t for t in required_types if t not in defaults)
    if missing:
        raise ValueError(f"Missing per-type defaults in LayerTypeDefaults: {', '.join(missing)}")

    return defaults

def fetch_layer_rows(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    # Only top-level layers: exclude any layer that is referenced as a child of a switchlayer
    cur = conn.execute(
        """
        SELECT *
        FROM Layers
        WHERE LayerId NOT IN (SELECT ChildLayerId FROM SwitchLayerChildren)
        ORDER BY layerKey
        """
    )
    return cur.fetchall()
def fetch_server_options(conn: sqlite3.Connection, layer_id: int) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM LayerServerOptions WHERE LayerId=?", (layer_id,))
    return cur.fetchone()

def fetch_xyz_options(conn: sqlite3.Connection, layer_id: int) -> Optional[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM LayerXYZOptions WHERE LayerId=?", (layer_id,))
    return cur.fetchone()

def fetch_styles(conn: sqlite3.Connection, layer_id: int) -> List[Tuple[str, str, Optional[str], Optional[str], int, int]]:
    cur = conn.execute(
        "SELECT name, title, labelRule, legendUrl, isDefault, displayOrder "
        "FROM LayerStyles WHERE LayerId=? ORDER BY displayOrder, name",
        (layer_id,),
    )
    return list(cur.fetchall())

def fetch_children(conn: sqlite3.Connection, parent_id: int) -> List[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT C.position, L.* "
        "FROM SwitchLayerChildren C JOIN Layers L ON L.LayerId = C.ChildLayerId "
        "WHERE C.ParentLayerId = ? ORDER BY C.position",
        (parent_id,),
    )
    return cur.fetchall()

def env_layer_overrides(conn: sqlite3.Connection, env: Optional[str], layer_key: str) -> Optional[Dict[str, Any]]:
    if not env:
        return None
    cur = conn.execute(
        "SELECT overridesJSON FROM EnvironmentOverrides "
        "WHERE envName = ? AND scope = 'layer' AND scopeId = ?",
        (env, layer_key),
    )
    row = cur.fetchone()
    if not row:
        return None
    return json_loads_or_none(row[0]) or {}

def build_layer_object(conn: sqlite3.Connection,
                       row: sqlite3.Row,
                       type_defaults: Dict[str, Any],
                       env: Optional[str]) -> Dict[str, Any]:
    layer_type = row["layerType"]
    layer_key = row["layerKey"]

    obj: Dict[str, Any] = {
        "layerType": layer_type,
        "layerKey": layer_key,
    }

    if row["gridXType"]:
        obj["gridXType"] = row["gridXType"]
    if row["idProperty"]:
        obj["idProperty"] = row["idProperty"]
    if row["labelClassName"]:
        obj["labelClassName"] = row["labelClassName"]
    if row["legendWidth"] is not None:
        obj["legendWidth"] = row["legendWidth"]
    if row["visibilityDefault"] is not None:
        obj["visibility"] = bool(row["visibilityDefault"])
    if row["vectorFeaturesMinScale"] is not None:
        obj["vectorFeaturesMinScale"] = row["vectorFeaturesMinScale"]
    if row["featureInfoWindow"] is not None:
        obj["featureInfoWindow"] = bool(row["featureInfoWindow"])
    if row["hasMetadata"] is not None:
        obj["hasMetadata"] = bool(row["hasMetadata"])
    if row["isBaseLayer"] is not None:
        obj["isBaseLayer"] = bool(row["isBaseLayer"])
    if row["qtip"]:
        obj["qtip"] = row["qtip"]

    ol = json_loads_or_none(row["openLayersJSON"])
    if isinstance(ol, dict) and ol:
        obj["openLayers"] = ol
    tips = json_loads_or_none(row["tooltipsJSON"])
    if isinstance(tips, list) and tips:
        obj["tooltipsConfig"] = tips
    grouping = json_loads_or_none(row["groupingJSON"])
    if isinstance(grouping, dict) and grouping:
        obj["grouping"] = grouping

    if layer_type in ("wms", "wfs", "arcgisrest"):
        so = fetch_server_options(conn, row["LayerId"])
        if so:
            so_obj: Dict[str, Any] = {}
            if so["wmsLayers"]:
                so_obj["layers"] = so["wmsLayers"]
            if so["orderBy"]:
                so_obj["ORDERBY"] = so["orderBy"]
            if so["propertyName"]:
                so_obj["propertyname"] = so["propertyName"]
            if so["version"]:
                so_obj["version"] = so["version"]
            if so["maxResolution"] is not None:
                so_obj["maxResolution"] = so["maxResolution"]
            if so_obj:
                obj["serverOptions"] = so_obj

        if layer_type == "wfs":
            if row["featureType"]:
                obj["featureType"] = row["featureType"]
            if row["geomFieldName"]:
                obj["geomFieldName"] = row["geomFieldName"]

        styles = ensure_styles_array(fetch_styles(conn, row["LayerId"]))
        if styles:
            obj["styles"] = styles

    elif layer_type == "xyz":
        xo = fetch_xyz_options(conn, row["LayerId"])
        if xo:
            obj["url"] = xo["urlTemplate"]
            # Inject access token if present
            token = xo["accessToken"]
            if token and isinstance(obj.get("url"), str):
                url = obj["url"]
                # If url already has a placeholder, replace it
                if "{MAPBOX_TOKEN}" in url:
                    url = url.replace("{MAPBOX_TOKEN}", token)
                else:
                    # Append as a query param only if not present already
                    if "access_token=" not in url:
                        sep = "&" if "?" in url else "?"
                        url = f"{url}{sep}access_token={token}"
                obj["url"] = url
            ol2: Dict[str, Any] = {}
            if xo["projection"]:
                ol2["projection"] = xo["projection"]
            if xo["tileSize"] is not None:
                ol2["tileSize"] = xo["tileSize"]
            if xo["attributionHTML"]:
                ol2["attribution"] = xo["attributionHTML"]
            extent = json_loads_or_none(xo["extentJSON"])
            if extent:
                if "openLayers" not in obj:
                    obj["openLayers"] = {}
                obj["openLayers"]["extent"] = extent
            tilegrid = json_loads_or_none(xo["tileGridJSON"])
            if tilegrid:
                if "openLayers" not in obj:
                    obj["openLayers"] = {}
                obj["openLayers"]["tileGrid"] = tilegrid
            if ol2:
                obj["openLayers"] = deep_merge(obj.get("openLayers", {}), ol2)

    elif layer_type == "switchlayer":
        children = fetch_children(conn, row["LayerId"])
        child_objs: List[Dict[str, Any]] = []
        for ch in children:
            child_obj = build_layer_object(conn, ch, type_defaults, env=None)
            td = type_defaults.get(child_obj["layerType"], {})
            child_objs.append(remove_defaults(child_obj, td))
        obj["layers"] = child_objs

    patch = env_layer_overrides(conn, env, layer_key)
    if isinstance(patch, dict) and patch:
        deep_merge(obj, patch)

    td = type_defaults.get(layer_type, {})
    obj = remove_defaults(obj, td)

    return obj

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to SQLite config DB")
    ap.add_argument("--out", required=True, help="Output default.json path")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)

    # 1) Load defaults (required). If absent or malformed, raise and stop.
    defaults = load_defaults(conn)

    # 2) Build a quick map of layer-type defaults for pruning
    type_defaults: Dict[str, Any] = {
        k: v for k, v in defaults.items()
        if isinstance(v, dict) and k in ("wms","wfs","xyz","switchlayer","arcgisrest")
    }

    # 3) Build all top-level layers (children handled recursively)
    rows = fetch_layer_rows(conn)
    layers_out: List[Dict[str, Any]] = []
    for row in rows:
        obj = build_layer_object(conn, row, type_defaults, env=None)  # env=None always
        layers_out.append(obj)

    # 4) Emit JSON: keep layers minimal; include full defaults exactly as in DB
    output = {"defaults": defaults, "layers": layers_out}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print("Wrote {} with {} layers.".format(args.out, len(layers_out)))

if __name__ == "__main__":
    sys.exit(main())
