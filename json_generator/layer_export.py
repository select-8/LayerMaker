import os
import json
import sqlite3
from typing import Dict, Any, List, Optional

def _get_portal_id(conn: sqlite3.Connection, portal_key: str) -> int:
    cur = conn.execute(
        "SELECT PortalId FROM Portals WHERE PortalKey = ?", (portal_key,)
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"PortalKey '{portal_key}' not found in Portals")
    return row[0]

def _load_switch_layers(
    conn: sqlite3.Connection, portal_id: int
) -> Dict[str, Dict[str, Any]]:
    """
    Returns mapping:
        switchKey -> {
            "vectorFeaturesMinScale": int | None,
            "childrenLayerKeys": [layerKey, ...]
        }
    """
    # PortalSwitchLayers is per portal
    cur = conn.execute(
        """
        SELECT
            psl.PortalSwitchLayerId,
            psl.SwitchKey,
            psl.VectorFeaturesMinScale
        FROM PortalSwitchLayers psl
        WHERE psl.PortalId = ?
        """,
        (portal_id,),
    )
    switch_rows = cur.fetchall()

    result: Dict[str, Dict[str, Any]] = {}
    if not switch_rows:
        return result

    # Map switchId -> (switchKey, minScale)
    switch_by_id = {
        row[0]: {
            "switchKey": row[1],
            "vectorFeaturesMinScale": row[2],
        }
        for row in switch_rows
    }

    # Children
    cur = conn.execute(
        """
        SELECT
            pslc.PortalSwitchLayerId,
            sl.LayerKey,
            pslc.ChildOrder
        FROM PortalSwitchLayerChildren pslc
        JOIN ServiceLayers sl
          ON sl.ServiceLayerId = pslc.ServiceLayerId
        JOIN PortalSwitchLayers psl
          ON psl.PortalSwitchLayerId = pslc.PortalSwitchLayerId
        WHERE psl.PortalId = ?
        """,
        (portal_id,),
    )
    children_rows = cur.fetchall()
 

    # print("DEBUG _load_switch_layers switch_rows:", [(r[0], r[1]) for r in switch_rows])
    # print("DEBUG _load_switch_layers children_rows:", children_rows[:10], "count:", len(children_rows))
    # print("DEBUG _load_switch_layers types:",
    #       "switch_ids:", [(type(r[0]), r[0]) for r in switch_rows],
    #       "child_switch_ids:", [(type(r[0]), r[0]) for r in children_rows[:5]])


    children_by_switch_id: Dict[int, List[str]] = {}
    for switch_id, layer_key, child_order in children_rows:
        children_by_switch_id.setdefault(switch_id, []).append((child_order, layer_key))

    for switch_id, meta in switch_by_id.items():
        children_pairs = children_by_switch_id.get(switch_id, [])
        children_keys = [lk for _, lk in sorted(children_pairs, key=lambda x: x[0] or 0)]
        result[meta["switchKey"]] = {
            "vectorFeaturesMinScale": meta["vectorFeaturesMinScale"],
            "childrenLayerKeys": children_keys,
        }
    
    return result

def _load_portal_service_layers(
    conn: sqlite3.Connection, portal_id: int
) -> List[Dict[str, Any]]:
    """
    Returns a list of dicts for all ServiceLayers that belong to this portal,
    either:
      - directly via PortalLayers, or
      - indirectly as children of PortalSwitchLayers via PortalSwitchLayerChildren

    Joined with MapServerLayers.
    """
    cur = conn.execute(
        """
        WITH PortalServiceLayerIds AS (
            -- Direct membership
            SELECT pl.ServiceLayerId
            FROM PortalLayers pl
            WHERE pl.PortalId = ?

            UNION

            -- Switch children membership
            SELECT c.ServiceLayerId
            FROM PortalSwitchLayers psl
            JOIN PortalSwitchLayerChildren c
              ON c.PortalSwitchLayerId = psl.PortalSwitchLayerId
            WHERE psl.PortalId = ?
        )
        SELECT
            sl.ServiceLayerId,
            sl.LayerKey,
            sl.ServiceType,
            sl.FeatureType,
            sl.IdPropertyName,
            sl.GeomFieldName,
            sl.GridXType,
            sl.Grouping,
            sl.IsUserConfigurable,

            m.MapServerLayerId,
            m.MapLayerName,
            m.BaseLayerKey,
            m.GridXType AS MapGridXType,
            m.GeometryType,
            m.DefaultGeomFieldName,

            m.Projection      AS MapProjection,
            m.Opacity         AS MapOpacity,
            m.LabelClassName  AS MapLabelClassName,
            m.GeomFieldName   AS MapGeomFieldName,
            m.NoCluster       AS MapNoCluster
        FROM PortalServiceLayerIds pids
        JOIN ServiceLayers sl
          ON sl.ServiceLayerId = pids.ServiceLayerId
        JOIN MapServerLayers m
          ON m.MapServerLayerId = sl.MapServerLayerId
        ORDER BY sl.LayerKey
        """,
        (portal_id, portal_id),
    )

    rows: List[Dict[str, Any]] = []
    cols = [d[0] for d in cur.description]
    for r in cur.fetchall():
        rows.append(dict(zip(cols, r)))
    return rows

def _load_service_fields(
    conn: sqlite3.Connection, service_layer_id: int
) -> List[Dict[str, Any]]:
    """
    ServiceLayerFields: per-service propertynames & tooltips.
    """
    cur = conn.execute(
        """
        SELECT
            FieldName,
            FieldType,
            IncludeInPropertyname,
            IsTooltip,
            TooltipAlias,
            FieldOrder
        FROM ServiceLayerFields
        WHERE ServiceLayerId = ?
        ORDER BY COALESCE(FieldOrder, 0), FieldName
        """,
        (service_layer_id,),
    )
    rows = []
    cols = [d[0] for d in cur.description]
    for r in cur.fetchall():
        rows.append(dict(zip(cols, r)))
    return rows

def _load_service_styles(
    conn: sqlite3.Connection, service_layer_id: int
) -> List[Dict[str, Any]]:
    """
    ServiceLayerStyles: per-service style list, with UseLabelRule flag.
    """
    cur = conn.execute(
        """
        SELECT
            StyleName,
            StyleTitle,
            UseLabelRule,
            StyleOrder
        FROM ServiceLayerStyles
        WHERE ServiceLayerId = ?
        ORDER BY COALESCE(StyleOrder, 0), StyleName
        """,
        (service_layer_id,),
    )
    rows = []
    cols = [d[0] for d in cur.description]
    for r in cur.fetchall():
        rows.append(dict(zip(cols, r)))
    return rows

def _load_xyz_layers_from_file() -> List[Dict[str, Any]]:
    """
    Load canonical XYZ layer entries from xyz_layers.json.
    Expected shape:
      { "layers": [ {layerType:"xyz", layerKey:..., ...}, ... ] }
    """
    # layer_export.py lives in json_generator/, xyz_layers.json should sit beside it
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "xyz_layers.json")

    with open(path, "r", encoding="utf-8") as f:
        doc = json.load(f)

    layers = doc.get("layers") or []
    # Keep only xyz entries, ignore anything else if file grows later
    out = []
    for l in layers:
        if isinstance(l, dict) and (l.get("layerType") or "").lower() == "xyz":
            out.append(l)
    return out

def _inject_xyz_layers(layers_out: List[Dict[str, Any]]) -> None:
    """
    Append canonical XYZ layers, skipping duplicates by layerKey.
    Mutates layers_out.
    """
    existing_keys = {l.get("layerKey") for l in layers_out if isinstance(l, dict)}
    for xyz in _load_xyz_layers_from_file():
        k = xyz.get("layerKey")
        if k and k not in existing_keys:
            layers_out.append(xyz)
            existing_keys.add(k)

def build_portal_layer_model(
    conn: sqlite3.Connection, portal_key: str
) -> Dict[str, Any]:
    """
    Canonical in-memory model for all layers in a portal.
    Structure:
      {
        "portalKey": ...,
        "layers": { layerKey -> layerInfo },
        "switchLayers": { switchKey -> switchInfo }
      }
    """
    portal_id = _get_portal_id(conn, portal_key)
    svc_rows = _load_portal_service_layers(conn, portal_id)
    #print("DEBUG svc_rows contains FWDLINES_WMS:", any(r.get("LayerKey") == "FWDLINES_WMS" for r in svc_rows))
    switch_map = _load_switch_layers(conn, portal_id)

    layers: Dict[str, Any] = {}

    for row in svc_rows:
        layer_key = row["LayerKey"]
        service_layer_id = row["ServiceLayerId"]

        default_geom_field = row["DefaultGeomFieldName"] or "msGeometry"

        label_class = (row.get("MapLabelClassName") or "").strip()
        if not label_class:
            label_class = "labels"

        projection = row["MapProjection"]
        layer_opacity = row["MapOpacity"] if row["MapOpacity"] is not None else 0.75

        no_cluster = row.get("MapNoCluster")
        if no_cluster is None:
            no_cluster = 1
        no_cluster = bool(int(no_cluster))

        # Fields
        service_fields = _load_service_fields(conn, service_layer_id)
        property_names = [
            f["FieldName"]
            for f in service_fields
            if f.get("IncludeInPropertyname")
        ]
        tooltips = [
            {
                "field": f["FieldName"],
                "alias": f.get("TooltipAlias") or f["FieldName"],
            }
            for f in service_fields
            if f.get("IsTooltip")
        ]
        # If IdPropertyName is NULL, exporter can fall back to first property or MapServerLayerFields later.
        id_prop = row["IdPropertyName"]

        # Styles
        service_styles = _load_service_styles(conn, service_layer_id)
        styles = []
        for s in service_styles:
            style_entry: Dict[str, Any] = {
                "name": s["StyleName"],
                "title": s["StyleTitle"],
            }
            # For WFS, UseLabelRule controls labelRule
            if row["ServiceType"].upper() == "WFS" and s.get("UseLabelRule"):
                style_entry["labelRule"] = label_class
            styles.append(style_entry)

        # Parse grouping JSON if present
        grouping = None
        raw_grouping = row["Grouping"]
        if raw_grouping:
            try:
                grouping = json.loads(raw_grouping)
            except Exception:
                # If it isn't valid JSON, keep the raw value so at least it's visible
                grouping = raw_grouping

        layers[layer_key] = {
            "layerKey": layer_key,
            "serviceType": row["ServiceType"].upper(),
            "mapLayerName": row["MapLayerName"],
            "geometryType": row["GeometryType"],
            "gridXType": row["GridXType"] or row["MapGridXType"],
            "defaults": {
                "geomFieldName": default_geom_field
            },
            "overrides": {
                "labelClassName": label_class,
                "projection": projection,
                "opacity": layer_opacity,
                "noCluster": no_cluster,
            },
            "fields": {
                "idProperty": id_prop,
                "propertyNames": property_names,
                "tooltips": tooltips,
            },
            "styles": styles,
            "grouping": grouping
        }

    return {
        "portalKey": portal_key,
        "layers": layers,
        "switchLayers": switch_map,
    }

def _build_defaults_block(portal_key: str) -> Dict[str, Any]:
    """
    Return the 'defaults' block for the layer JSON document.

    For now, this is a static copy of the main PMS default.json defaults,
    reused for all portals. Later you can move this into LayerConfig_v3
    (e.g. per-portal defaults tables).
    """
    return {
        "styleSwitcherBelowNode": True,
        "wms": {
            "dateFormat": "Y-m-d",
            "url": "/mapserver2/?",
            "featureInfoWindow": True,
            "hasMetadata": True,
            "isBaseLayer": False,
            "requestMethod": "POST",
            "openLayers": {
                "maxResolution": 1222.99245234375,
                "opacity": 0.9,
                "projection": "EPSG:2157",
                "visibility": False,
                "singleTile": True,
            },
        },
        "wfs": {
            "url": "/mapserver2/?",
            "noCluster": True,
            "serverOptions": {
                "version": "2.0.0",
                "maxResolution": 1222.99245234375,
            },
            "openLayers": {
                "visibility": False,
                "projection": "EPSG:2157",
                "opacity": 0.9,
            },
        },
        "xyz": {
            "openLayers": {
                "projection": "EPSG:2157",
                "transitionEffect": "resize",
                "visibility": False,
            },
            "isBaseLayer": True,
        },
        "switchlayer": {
            "vectorFeaturesMinScale": 20000,
            "visibility": False,
            "featureInfoWindow": True,
        },
        "arcgisrest": {
            "openLayers": {
                "singleTile": False,
                "visibility": False,
            },
        },
    }

def build_layer_json_document(model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Take the canonical portal layer model and return a PMS-style
    layer JSON document:

        {
          "defaults": { ... },
          "layers": [ ... ]
        }

    Any WMS/WFS layer that is used as a child in a switchlayer for this
    portal is NOT emitted as a standalone layer entry. It is represented
    only via the switchlayer.
    """
    portal_key = model.get("portalKey")
    defaults = _build_defaults_block(portal_key or "")

    layers_out: List[Dict[str, Any]] = []

    # 1) Collect all child layerKeys that participate in a switchlayer
    switched_children: set[str] = set()
    for sw in model.get("switchLayers", {}).values():
        for child_key in sw.get("childrenLayerKeys") or []:
            if child_key:
                switched_children.add(child_key)

    # 2) Emit WMS / WFS layers, skipping any that are switch children
    for layer_key, layer in model.get("layers", {}).items():
        service_type = (layer.get("serviceType") or "").upper()

        if layer_key in switched_children:
            # This layer is represented via a switchlayer in this portal.
            # Do not emit it as a standalone WMS/WFS.
            continue

        if service_type == "WMS":
            layers_out.append(_build_wms_layer_entry(layer_key, layer, defaults))
        elif service_type == "WFS":
            layers_out.append(_build_wfs_layer_entry(layer_key, layer, defaults))
        else:
            # XYZ / arcgisrest / etc. can be handled later
            continue

    layers_by_key = model.get("layers", {})

    #print("DEBUG build_layer_json_document switchLayers keys:", list(model.get("switchLayers", {}).keys()))
    #print("DEBUG build_layer_json_document layer keys sample:", list(model.get("layers", {}).keys())[:10])

    for switch_key, sw in model.get("switchLayers", {}).items():
        kids = sw.get("childrenLayerKeys") or []
        #print("DEBUG switch", switch_key, "kids:", len(kids), "example:", kids[:3])
        layers_out.append(_build_switch_layer_entry(switch_key, sw, defaults, layers_by_key))

    # 3) Inject canonical XYZ layers for all portals
    _inject_xyz_layers(layers_out)

    return {
        "defaults": defaults,
        "layers": layers_out,
    }

def _build_wms_layer_entry(
    layer_key: str, layer: Dict[str, Any], defaults: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Map canonical WMS layer -> PMS-style WMS layer entry.

    Emit only values that differ from defaults, to keep JSON minimal.
    """
    overrides = layer.get("overrides") or {}

    entry: Dict[str, Any] = {
        "layerType": "wms",
        "layerKey": layer_key,
        "gridXType": layer.get("gridXType"),
    }

    # serverOptions (always need layers)
    server_opts: Dict[str, Any] = {
        "layers": layer.get("mapLayerName"),
    }

    # Per-layer styles -> name/title + optional simple styles string
    styles = []
    for s in layer.get("styles") or []:
        styles.append(
            {
                "name": s.get("name"),
                "title": s.get("title"),
            }
        )
    if styles:
        entry["styles"] = styles
        if len(styles) == 1 and styles[0].get("name"):
            server_opts["styles"] = styles[0]["name"]

    entry["serverOptions"] = server_opts

    # labelClassName: only emit if not default
    label_class = (overrides.get("labelClassName") or "").strip() or "labels"
    if label_class != "labels":
        entry["labelClassName"] = label_class

    # openLayers: only emit if differs from defaults.wms.openLayers
    wms_defaults = defaults.get("wms") or {}
    wms_ol_defaults = (wms_defaults.get("openLayers") or {}) if isinstance(wms_defaults.get("openLayers"), dict) else {}

    default_proj = (wms_ol_defaults.get("projection") or "").strip() or "EPSG:2157"
    default_opacity = wms_ol_defaults.get("opacity")

    proj = (overrides.get("projection") or "").strip()
    opacity = overrides.get("opacity")

    ol: Dict[str, Any] = {}

    if proj and proj != default_proj:
        ol["projection"] = proj

    if opacity is not None:
        try:
            op_f = float(opacity)
            if default_opacity is None or op_f != float(default_opacity):
                ol["opacity"] = op_f
        except Exception:
            # If it's junk, better to omit than emit invalid JSON values
            pass

    if ol:
        entry["openLayers"] = ol

    # Grouping (niche)
    grouping = layer.get("grouping")
    if grouping:
        entry["grouping"] = grouping

    return entry

def _build_wfs_layer_entry(
    layer_key: str, layer: Dict[str, Any], defaults: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Map canonical WFS layer -> PMS-style WFS layer entry.

    Emit only values that differ from defaults, to keep JSON minimal.
    """
    overrides = layer.get("overrides") or {}
    fields = layer.get("fields") or {}

    entry: Dict[str, Any] = {
        "layerType": "wfs",
        "layerKey": layer_key,
        "gridXType": layer.get("gridXType"),
        "featureType": layer.get("mapLayerName"),
        "geomFieldName": (layer.get("defaults") or {}).get("geomFieldName") or "msGeometry",
        "idProperty": fields.get("idProperty"),
    }

    # serverOptions.propertyname
    server_opts: Dict[str, Any] = {}
    property_names = list(fields.get("propertyNames") or [])
    id_prop = fields.get("idProperty")
    if id_prop and id_prop not in property_names:
        property_names.insert(0, id_prop)
    if property_names:
        server_opts["propertyname"] = ",".join(property_names)
        entry["serverOptions"] = server_opts

    # noCluster: only emit if differs from defaults.wfs.noCluster
    wfs_defaults = defaults.get("wfs") or {}
    default_no_cluster = wfs_defaults.get("noCluster")

    override_no_cluster = overrides.get("noCluster")
    eff_no_cluster = None
    if override_no_cluster is not None:
        eff_no_cluster = bool(override_no_cluster)
    elif default_no_cluster is not None:
        eff_no_cluster = bool(default_no_cluster)

    if eff_no_cluster is not None and (default_no_cluster is None or eff_no_cluster != bool(default_no_cluster)):
        entry["noCluster"] = eff_no_cluster

    # Styles – if UseLabelRule was set in DB model, we expect style dicts to carry a marker.
    # But you currently pass in s.get("labelRule") sometimes, so we enforce the correct value here.
    label_class = (overrides.get("labelClassName") or "").strip() or "labels"

    styles_out = []
    for s in layer.get("styles") or []:
        se = {
            "name": s.get("name"),
            "title": s.get("title"),
        }

        # If this style should emit labelRule (UseLabelRule=1), set it to the layer's label class.
        # We treat presence of s["labelRule"] as the marker that UseLabelRule=1.
        if s.get("labelRule") is not None:
            se["labelRule"] = label_class

        styles_out.append(se)

    if styles_out:
        entry["styles"] = styles_out

    # tooltipsConfig
    tooltips = fields.get("tooltips") or []
    if tooltips:
        tcfg = []
        for t in tooltips:
            prop = t.get("field")
            alias = t.get("alias")
            if not prop:
                continue
            item = {"property": prop}
            if alias and alias != prop:
                item["alias"] = alias
            tcfg.append(item)
        if tcfg:
            entry["tooltipsConfig"] = tcfg

    # Grouping
    grouping = layer.get("grouping")
    if grouping:
        entry["grouping"] = grouping

    # openLayers: only emit if differs from defaults.wfs.openLayers
    wfs_ol_defaults = (wfs_defaults.get("openLayers") or {}) if isinstance(wfs_defaults.get("openLayers"), dict) else {}
    default_proj = (wfs_ol_defaults.get("projection") or "").strip() or "EPSG:2157"
    default_opacity = wfs_ol_defaults.get("opacity")  # normally None for WFS in your defaults

    proj = (overrides.get("projection") or "").strip()
    opacity = overrides.get("opacity")

    ol: Dict[str, Any] = {}

    if proj and proj != default_proj:
        ol["projection"] = proj

    if opacity is not None:
        try:
            op_f = float(opacity)
            # Only emit if defaults has opacity and differs, or if you *really* want to allow WFS opacity.
            # This keeps you aligned with production-style minimal output.
            if default_opacity is not None:
                if op_f != float(default_opacity):
                    ol["opacity"] = op_f
            else:
                # defaults has no WFS opacity, so treat as "don't emit" unless you later decide otherwise
                pass
        except Exception:
            pass

    if ol:
        entry["openLayers"] = ol

    return entry

def _build_switch_layer_entry(
    switch_key: str,
    sw: Dict[str, Any],
    defaults: Dict[str, Any],
    layers_by_key: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Map canonical switch layer -> PMS-style switchlayer entry.
    """
    #print("DEBUG _build_switch_layer_entry", switch_key, "kids:", sw.get("childrenLayerKeys"))
    # Build full child layer objects (WMS + WFS) under the switch wrapper
    children_out = []
    for child_key in (sw.get("childrenLayerKeys") or []):
        #print("DEBUG switch child lookup", child_key, "found:", child_key in layers_by_key)
        child = layers_by_key.get(child_key)
        if not child:
            continue

        st = (child.get("serviceType") or "").upper()
        if st == "WMS":
            children_out.append(_build_wms_layer_entry(child_key, child, defaults))
        elif st == "WFS":
            children_out.append(_build_wfs_layer_entry(child_key, child, defaults))

    entry = {
        "layerType": "switchlayer",
        "layerKey": switch_key,
        "layers": children_out,
    }

    # Default visibility / featureInfoWindow etc. are handled via defaults.switchlayer
    return entry

def export_portal_layer_json(
    conn: sqlite3.Connection,
    portal_key: str,
    output_path: str,
) -> None:
    """
    High-level exporter: build canonical model from DB, then turn it into
    a PMS-style layer JSON document ({ "defaults": ..., "layers": [...] })
    and write it to disk.
    """
    model = build_portal_layer_model(conn, portal_key)
    doc = build_layer_json_document(model)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write("\n")

