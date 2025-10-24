# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
generate_json_from_db.py

Export a normalised JSON config (defaults + layers) from the SQLite DB for a given portal.

- Includes portal-scoped defaults (GlobalDefaults + LayerTypeDefaults).
- Emits only TOP-LEVEL layers; children show only inside their switchlayer.
- WMS/WFS/ArcGISREST: adds serverOptions + styles[] (array form).
- WFS: also includes featureType + geomFieldName when present.
- XYZ: substitutes {MAPBOX_TOKEN} in urlTemplate with accessToken (if present).
- Prunes fields that equal per-type defaults to keep layers minimal.
- Pretty-prints the JSON (indent=2).
- Orders top-level layers by layerType, then layerKey (alphabetical).
"""
import argparse, json, sqlite3
from typing import Any, Dict, List, Optional

CORE_TYPES = {"wms","wfs","xyz","arcgisrest"}

def json_loads_or_none(s: Optional[str]):
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None

def deep_equal(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()): return False
        return all(deep_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): return False
        return all(deep_equal(x, y) for x, y in zip(a, b))
    return a == b

def remove_defaults(obj: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in obj.items():
        if k not in defaults:
            out[k] = v; continue
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
    pid = conn.execute("SELECT PortalId FROM Portals WHERE code=?", (portal_code,)).fetchone()
    if not pid:
        raise SystemExit(f"Portal '{portal_code}' not found.")
    portal_id = pid[0]
    defaults: Dict[str, Any] = {}
    for r in conn.execute("SELECT key, valueJSON FROM GlobalDefaults WHERE portalId=?", (portal_id,)):
        defaults[r[0]] = json_loads_or_none(r[1])
    for r in conn.execute("SELECT layerType, defaultsJSON FROM LayerTypeDefaults WHERE portalId=?", (portal_id,)):
        parsed = json_loads_or_none(r[1]) or {}
        if not isinstance(parsed, dict):
            raise SystemExit(f"LayerTypeDefaults.{r[0]} is not a JSON object for portal '{portal_code}'.")
        defaults[r[0]] = parsed
    # Require defaults for the concrete layer types we use
    missing = [t for t in ("wms","wfs","xyz","arcgisrest") if t not in defaults]
    if missing:
        raise SystemExit("Missing per-type defaults: " + ", ".join(missing))
    return defaults, portal_id

def build_styles(conn, layer_id: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in conn.execute(        """        SELECT name, title, labelRule, legendUrl
        FROM LayerStyles
        WHERE LayerId=?
        ORDER BY displayOrder, name
        """, (layer_id,)
    ):
        item: Dict[str, Any] = {"name": r[0], "title": r[1]}
        if r[2]: item["labelRule"] = r[2]
        if r[3]: item["legendUrl"] = r[3]
        out.append(item)
    return out

def build_layer(conn, row, type_defaults: Dict[str, Any]) -> Dict[str, Any]:
    lt = row["layerType"]
    obj: Dict[str, Any] = {"layerType": lt, "layerKey": row["layerKey"]}
    # common
    if row["title"]: obj["title"] = row["title"]
    if row["gridXType"]: obj["gridXType"] = row["gridXType"]
    if row["idProperty"]: obj["idProperty"] = row["idProperty"]
    if row["labelClassName"]: obj["labelClassName"] = row["labelClassName"]
    if row["legendWidth"] is not None: obj["legendWidth"] = row["legendWidth"]
    if row["visibilityDefault"] is not None: obj["visibility"] = bool(row["visibilityDefault"])  # to boolean
    if row["vectorFeaturesMinScale"] is not None: obj["vectorFeaturesMinScale"] = row["vectorFeaturesMinScale"]
    if row["featureInfoWindow"] is not None: obj["featureInfoWindow"] = bool(row["featureInfoWindow"])  # bool
    if row["hasMetadata"] is not None: obj["hasMetadata"] = bool(row["hasMetadata"])  # bool
    if row["isBaseLayer"] is not None: obj["isBaseLayer"] = bool(row["isBaseLayer"])  # bool
    if row["qtip"]: obj["qtip"] = row["qtip"]
    ol = json_loads_or_none(row["openLayersJSON"])
    if isinstance(ol, dict) and ol: obj["openLayers"] = ol
    tips = json_loads_or_none(row["tooltipsJSON"])
    if isinstance(tips, list) and tips: obj["tooltipsConfig"] = tips
    grp = json_loads_or_none(row["groupingJSON"])
    if isinstance(grp, dict) and grp: obj["grouping"] = grp

    if lt in ("wms","wfs","arcgisrest"):
        so = conn.execute(            "SELECT wmsLayers, \"orderBy\", propertyName, \"version\", maxResolution FROM LayerServerOptions WHERE LayerId=?",
            (row["LayerId"],)
        ).fetchone()
        if so:
            so_obj: Dict[str, Any] = {}
            if so[0]: so_obj["layers"] = so[0]
            if so[1]: so_obj["ORDERBY"] = so[1]
            if so[2]: so_obj["propertyname"] = so[2]
            if so[3]: so_obj["version"] = so[3]
            if so[4] is not None: so_obj["maxResolution"] = so[4]
            if so_obj: obj["serverOptions"] = so_obj
        if lt == "wfs":
            if row["featureType"]: obj["featureType"] = row["featureType"]
            if row["geomFieldName"]: obj["geomFieldName"] = row["geomFieldName"]
        st = build_styles(conn, row["LayerId"])
        if st: obj["styles"] = st

    elif lt == "xyz":
        xo = conn.execute(            "SELECT urlTemplate, accessToken, projection, tileSize, attributionHTML, extentJSON, tileGridJSON FROM LayerXYZOptions WHERE LayerId=?",
            (row["LayerId"],)
        ).fetchone()
        if xo:
            url, token = xo[0], xo[1]
            if url and "{MAPBOX_TOKEN}" in url and token:
                url = url.replace("{MAPBOX_TOKEN}", token)
            obj["url"] = url
            ol2 = obj.get("openLayers", {})
            if xo[2]: ol2["projection"] = xo[2]
            if xo[3] is not None: ol2["tileSize"] = xo[3]
            if xo[4]: ol2["attribution"] = xo[4]
            ext = json_loads_or_none(xo[5]); tg = json_loads_or_none(xo[6])
            if ext: ol2["extent"] = ext
            if tg:  ol2["tileGrid"] = tg
            if ol2: obj["openLayers"] = ol2

    elif lt == "switchlayer":
        children: List[Dict[str, Any]] = []
        cur = conn.execute(            """            SELECT L.*
            FROM SwitchLayerChildren C
            JOIN Layers L ON L.LayerId = C.ChildLayerId
            WHERE C.ParentLayerId = ?
            ORDER BY C.position
            """, (row["LayerId"],)
        )
        for ch in cur.fetchall():
            children.append(build_layer(conn, ch, type_defaults))
        obj["layers"] = children

    td = type_defaults.get(lt, {})
    obj = remove_defaults(obj, td)
    return obj

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

    # Order by layerType first, then layerKey alphabetically
    cur = conn.execute(        """        SELECT *
        FROM Layers
        WHERE portalId=?
          AND LayerId NOT IN (SELECT ChildLayerId FROM SwitchLayerChildren)
        ORDER BY layerType, layerKey
        """, (portal_id,)
    )
    layers_out: List[Dict[str, Any]] = [build_layer(conn, row, type_defaults) for row in cur.fetchall()]

    doc = {"defaults": defaults, "layers": layers_out}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")  # trailing newline for POSIX friendliness

    print(f"Wrote {args.out} with {len(layers_out)} top-level layers for portal '{args.portal}'.")

if __name__ == "__main__":
    main()
