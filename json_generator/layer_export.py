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
    Returns a list of dicts for all ServiceLayers that belong to this portal
    via PortalLayers, joined with MapServerLayers.
    """
    cur = conn.execute(
        """
        SELECT
            sl.ServiceLayerId,
            sl.LayerKey,
            sl.ServiceType,
            sl.FeatureType,
            sl.IdPropertyName,
            sl.GeomFieldName,
            sl.LabelClassName,
            sl.Opacity,
            sl.OpenLayersJson,
            sl.ServerOptionsJson,
            sl.GridXType,
            sl.ProjectionOverride,
            sl.OpacityOverride,
            sl.NoClusterOverride,
            sl.FeatureInfoWindowOverride,
            sl.Grouping,
            sl.IsUserConfigurable,
            m.MapServerLayerId,
            m.MapLayerName,
            m.BaseLayerKey,
            m.GridXType AS MapGridXType,
            m.GeometryType,
            m.DefaultGeomFieldName,
            m.DefaultLabelClassName,
            m.DefaultOpacity
        FROM PortalLayers pl
        JOIN ServiceLayers sl
          ON sl.ServiceLayerId = pl.ServiceLayerId
        JOIN MapServerLayers m
          ON m.MapServerLayerId = sl.MapServerLayerId
        WHERE pl.PortalId = ?
          AND pl.IsEnabled = 1
        ORDER BY sl.LayerKey
        """,
        (portal_id,),
    )

    rows = []
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
    switch_map = _load_switch_layers(conn, portal_id)

    layers: Dict[str, Any] = {}

    for row in svc_rows:
        layer_key = row["LayerKey"]
        service_layer_id = row["ServiceLayerId"]

        # Base defaults
        default_label = row["DefaultLabelClassName"] or "labels"
        default_opacity = row["DefaultOpacity"] if row["DefaultOpacity"] is not None else 0.75
        default_geom_field = row["DefaultGeomFieldName"] or "msGeometry"

        # Effective values with overrides
        projection = row["ProjectionOverride"]  # you can later plug global default if None
        opacity = row["OpacityOverride"] if row["OpacityOverride"] is not None else default_opacity
        no_cluster = None
        if row["NoClusterOverride"] is not None:
            no_cluster = bool(row["NoClusterOverride"])

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
                style_entry["labelRule"] = default_label
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

        # Parse JSON overrides for serverOptions / openLayers
        server_opts_override = {}
        raw_server_opts = row["ServerOptionsJson"]
        if raw_server_opts:
            try:
                server_opts_override = json.loads(raw_server_opts)
            except Exception:
                # keep raw if it's not JSON, just so it doesn't vanish
                server_opts_override = {"_raw": raw_server_opts}

        openlayers_override = {}
        raw_openlayers = row["OpenLayersJson"]
        if raw_openlayers:
            try:
                openlayers_override = json.loads(raw_openlayers)
            except Exception:
                openlayers_override = {"_raw": raw_openlayers}


        layers[layer_key] = {
            "layerKey": layer_key,
            "serviceType": row["ServiceType"].upper(),
            "mapLayerName": row["MapLayerName"],
            "geometryType": row["GeometryType"],
            "gridXType": row["GridXType"] or row["MapGridXType"],
            "defaults": {
                "labelClassName": default_label,
                "opacity": default_opacity,
                "geomFieldName": default_geom_field,
            },
            "overrides": {
                "projection": projection,
                "opacity": opacity if opacity != default_opacity else None,
                "noCluster": no_cluster,
            },
            "fields": {
                "idProperty": id_prop,
                "propertyNames": property_names,
                "tooltips": tooltips,
            },
            "styles": styles,
            "grouping": grouping,
            # raw JSON overrides from ServiceLayers
            "serverOptionsOverride": server_opts_override,
            "openLayersOverride": openlayers_override,
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

    # 3) Emit switchlayers themselves
    for switch_key, sw in model.get("switchLayers", {}).items():
        layers_out.append(_build_switch_layer_entry(switch_key, sw, defaults))

    return {
        "defaults": defaults,
        "layers": layers_out,
    }

def _build_wms_layer_entry(
    layer_key: str, layer: Dict[str, Any], defaults: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Map canonical WMS layer -> PMS-style WMS layer entry.

    We only put per-layer specifics here. Global defaults like
    requestMethod/dateFormat/url live in defaults.wms.
    """
    layer_defaults = layer.get("defaults") or {}
    overrides = layer.get("overrides") or {}

    entry: Dict[str, Any] = {
        "layerType": "wms",
        "layerKey": layer_key,
        "gridXType": layer.get("gridXType"),
    }

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

    # Merge in explicit serverOptions overrides from DB
    server_opts_override = layer.get("serverOptionsOverride") or {}
    # If somebody stored something non-dict, just keep it under _raw
    if isinstance(server_opts_override, dict):
        # overlay DB overrides on top of our base
        server_opts.update(
            {k: v for k, v in server_opts_override.items() if k not in ("layers",)}
        )
    else:
        server_opts["_override_raw"] = server_opts_override

    entry["serverOptions"] = server_opts

    # Label handling – WMS uses labelClassName at layer level
    label_class = layer_defaults.get("labelClassName") or "labels"
    entry["labelClassName"] = label_class

    # OpenLayers: start from explicit JSON overrides, then apply derived overrides
    openlayers_override = layer.get("openLayersOverride") or {}
    ol: Dict[str, Any] = {}

    if isinstance(openlayers_override, dict):
        ol.update(openlayers_override)
    else:
        ol["_override_raw"] = openlayers_override

    # Projection override: ServiceLayers.ProjectionOverride -> openLayers.projection
    proj_override = (layer.get("overrides") or {}).get("projection")
    if proj_override:
        ol["projection"] = proj_override

    # Opacity override: only if different from per-layer default
    default_opacity = layer_defaults.get("opacity")
    opacity_override = (layer.get("overrides") or {}).get("opacity")
    if opacity_override is not None and opacity_override != default_opacity:
        ol["opacity"] = opacity_override

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
    """
    layer_defaults = layer.get("defaults") or {}
    overrides = layer.get("overrides") or {}
    fields = layer.get("fields") or {}

    entry: Dict[str, Any] = {
        "layerType": "wfs",
        "layerKey": layer_key,
        "gridXType": layer.get("gridXType"),
        # featureType is the MapServer LAYER NAME / FeatureType
        "featureType": layer.get("mapLayerName"),
        "geomFieldName": layer_defaults.get("geomFieldName") or "msGeometry",
        "idProperty": fields.get("idProperty"),
    }

    # serverOptions
    wfs_defaults = defaults.get("wfs") or {}
    server_opts: Dict[str, Any] = {}

    property_names = list(fields.get("propertyNames") or [])
    id_prop = fields.get("idProperty")
    if id_prop and id_prop not in property_names:
        property_names.insert(0, id_prop)

    if property_names:
        server_opts["propertyname"] = ",".join(property_names)

    if server_opts:
        entry["serverOptions"] = server_opts


    # Styles – include labelRule when present
    styles = []
    for s in layer.get("styles") or []:
        se = {
            "name": s.get("name"),
            "title": s.get("title"),
        }
        if s.get("labelRule"):
            se["labelRule"] = s["labelRule"]
        styles.append(se)
    if styles:
        entry["styles"] = styles

    # tooltipsConfig from canonical tooltips
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

    # noCluster: override or fallback to defaults.wfs.noCluster
    base_no_cluster = wfs_defaults.get("noCluster")
    override_no_cluster = overrides.get("noCluster")
    if override_no_cluster is not None or base_no_cluster is not None:
        entry["noCluster"] = (
            bool(override_no_cluster)
            if override_no_cluster is not None
            else bool(base_no_cluster)
        )

    # Grouping – same structure as in default.json, usually a dict
    grouping = layer.get("grouping")
    if grouping:
        entry["grouping"] = grouping

    # OpenLayers: start from explicit JSON overrides, then apply projection override
    openlayers_override = layer.get("openLayersOverride") or {}
    ol: Dict[str, Any] = {}

    if isinstance(openlayers_override, dict):
        ol.update(openlayers_override)
    else:
        ol["_override_raw"] = openlayers_override

    proj_override = (layer.get("overrides") or {}).get("projection")
    if proj_override:
        ol["projection"] = proj_override

    if ol:
        entry["openLayers"] = ol

    return entry

def _build_switch_layer_entry(
    switch_key: str, sw: Dict[str, Any], defaults: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Map canonical switch layer -> PMS-style switchlayer entry.
    """
    entry: Dict[str, Any] = {
        "layerType": "switchlayer",
        "layerKey": switch_key,
        "layers": list(sw.get("childrenLayerKeys") or []),
    }

    vmin = sw.get("vectorFeaturesMinScale")
    if vmin is not None:
        entry.setdefault("openLayers", {})["vectorFeaturesMinScale"] = vmin

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

def build_layer_json_document(model: Dict[str, Any]) -> Dict[str, Any]:
    """
    Take the canonical portal layer model and return a PMS-style
    layer JSON document:

        {
          "defaults": { ... },
          "layers": [ ... ]
        }
    """
    portal_key = model.get("portalKey")
    defaults = _build_defaults_block(portal_key or "")

    layers_out: List[Dict[str, Any]] = []

    for layer_key, layer in model.get("layers", {}).items():
        service_type = (layer.get("serviceType") or "").upper()
        if service_type == "WMS":
            layers_out.append(_build_wms_layer_entry(layer_key, layer, defaults))
        elif service_type == "WFS":
            layers_out.append(_build_wfs_layer_entry(layer_key, layer, defaults))
        else:
            # XYZ / arcgisrest handled separately later
            continue

    # switchlayers come from the switchLayers block
    for switch_key, sw in model.get("switchLayers", {}).items():
        layers_out.append(_build_switch_layer_entry(switch_key, sw, defaults))

    return {
        "defaults": defaults,
            "layers": layers_out,
    }

