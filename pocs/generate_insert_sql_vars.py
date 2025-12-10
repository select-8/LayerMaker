# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Generate a CTE-based SQL script (INSERTs only) for a layer using global variables.

- Uses TYPENAME and LAYERTYPE.
- LAYER_KEY = TYPENAME + '_' + normalized LAYERTYPE (e.g., 'switch' -> 'switchlayer').
- TITLE = spaced CamelCase TYPENAME (e.g., 'ThisIsMyTypeName' -> 'This Is My Type Name').
- Output file defaults to insert_{TYPENAME}.sql.
- Emits server options INSERT only when LAYERTYPE == 'wms'.
"""
import sys
import re
from typing import List, Tuple
import os

# ---------------------------
# CONFIG — edit these values
# ---------------------------
PORTAL: str = "default"
TYPENAME: str = "CIRIncidents"     # e.g., 'ThisIsMyTypeName'
LAYERTYPE: str = "wms"                 # one of: wms, wfs, xyz, switch, arcgisrest

LABEL_CLASS: str = "labels"            # optional (can be None)
OPENLAYERS_JSON: str = '{"opacity":0.9}'   # optional JSON string, or None

# For WMS only:
ORDER_BY: str = "CIRIncidentId"   # ORDERBY value (optional)

# Styles: list of (name, title). First item isDefault=1, others 0.
STYLES: List[Tuple[str, str]] = [
    ("default", "Default")
]

# If empty, defaults to f"insert_{TYPENAME}.sql"
OUTPUT_PATH: str = ""

# ---------------------------
# Derived values
# ---------------------------
def normalize_layer_type(t: str) -> str:
    t = (t or "").strip().lower()
    if t == "switch":
        return "switchlayer"
    return t

def spaced_title_from_typename(typename: str) -> str:
    # Insert spaces before capitals (not at start), e.g., "ThisIsMyTypeName" -> "This Is My Type Name"
    return re.sub(r"(?<!^)([A-Z])", r" \1", typename or "").strip()

N_LAYER_TYPE = normalize_layer_type(LAYERTYPE)
TITLE = spaced_title_from_typename(TYPENAME)
LAYER_KEY = f"{TYPENAME}_{N_LAYER_TYPE}".upper()
if not OUTPUT_PATH:
    OUTPUT_PATH = os.path.join('sql',f"insert_{TYPENAME}.sql")

# ---------------------------
# Helpers
# ---------------------------
def sql_literal(value: str) -> str:
    """Return a single-quoted SQL literal with single quotes escaped; if None -> NULL."""
    if value is None:
        return "NULL"
    return "'" + value.replace("'", "''") + "'"

def build_params_block() -> str:
    return f"""WITH params AS (
  SELECT
    {sql_literal(PORTAL)}          AS portal_code,
    {sql_literal(LAYER_KEY)}       AS layer_key,
    {sql_literal(N_LAYER_TYPE)}    AS layer_type,
    {sql_literal(TITLE)}           AS title,
    {sql_literal(LABEL_CLASS)}     AS label_class,
    {sql_literal(OPENLAYERS_JSON)} AS openlayers_json,
    {sql_literal(TYPENAME)}        AS type_name,
    {sql_literal(ORDER_BY)}        AS order_by
)"""

def build_layers_insert() -> str:
    return """INSERT INTO Layers (
  portalId, layerKey, layerType, title,
  labelClassName, visibilityDefault, openLayersJSON
)
SELECT
  (SELECT PortalId FROM Portals WHERE code = params.portal_code),
  params.layer_key,
  params.layer_type,
  params.title,
  params.label_class,
  0,
  params.openlayers_json
FROM params;"""

def build_server_options_insert_wms() -> str:
    # Self-contained CTE; do NOT try to reference an earlier WITH 'params' (SQLite CTEs are per-statement)
    return f"""WITH params AS (
  SELECT
    {sql_literal(PORTAL)}   AS portal_code,
    {sql_literal(LAYER_KEY)} AS layer_key,
    {sql_literal(ORDER_BY)} AS order_by,
    {sql_literal(TYPENAME)}  AS type_name
)
INSERT INTO LayerServerOptions (LayerId, wmsLayers, "orderBy")
SELECT
  L.LayerId, params.type_name, params.order_by
FROM params
JOIN Layers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);"""


def build_style_insert(name: str, title: str, is_default: int, order: int) -> str:
    return f"""WITH params AS (
  SELECT {sql_literal(PORTAL)} AS portal_code, {sql_literal(LAYER_KEY)} AS layer_key
)
INSERT INTO LayerStyles (LayerId, name, title, isDefault, displayOrder)
SELECT L.LayerId, {sql_literal(name)}, {sql_literal(title)}, {is_default}, {order}
FROM params
JOIN Layers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);"""

def build_sql() -> str:
    parts: List[str] = []
    parts.append(build_params_block())
    parts.append("")
    parts.append("-- 1) Layers")
    parts.append(build_layers_insert())
    if N_LAYER_TYPE == "wms":
        parts.append("")
        parts.append("-- 2) LayerServerOptions (WMS)")
        parts.append(build_server_options_insert_wms())

    if STYLES:
        parts.append("")
        parts.append("-- 3) Styles (optional)")
        for idx, (name, title) in enumerate(STYLES, start=1):
            parts.append(build_style_insert(name, title, 1 if idx == 1 else 0, idx))

    return "\n".join(parts) + "\n"

def main():
    sql = build_sql()
    if OUTPUT_PATH:
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(sql)
        print(f"Wrote {OUTPUT_PATH}")
    else:
        sys.stdout.write(sql)

if __name__ == "__main__":
    main()
