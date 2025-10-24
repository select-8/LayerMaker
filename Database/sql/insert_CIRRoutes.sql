WITH params AS (
  SELECT
    'default'          AS portal_code,
    'CIRROUTES_WMS'       AS layer_key,
    'wms'    AS layer_type,
    'C I R Routes'           AS title,
    'labels'     AS label_class,
    '{"opacity":0.9}' AS openlayers_json,
    'CIRRoutes'        AS type_name,
    'CIRRoutesId'        AS order_by
)

-- 1) Layers
INSERT INTO Layers (
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
FROM params;

-- 2) LayerServerOptions (WMS)
WITH params AS (
  SELECT
    'default'   AS portal_code,
    'CIRROUTES_WMS' AS layer_key,
    'CIRRoutesId' AS order_by,
    'CIRRoutes'  AS type_name
)
INSERT INTO LayerServerOptions (LayerId, wmsLayers, "orderBy")
SELECT
  L.LayerId, params.type_name, params.order_by
FROM params
JOIN Layers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);

-- 3) Styles (optional)
WITH params AS (
  SELECT 'default' AS portal_code, 'CIRROUTES_WMS' AS layer_key
)
INSERT INTO LayerStyles (LayerId, name, title, isDefault, displayOrder)
SELECT L.LayerId, 'default', 'Default', 1, 1
FROM params
JOIN Layers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);
