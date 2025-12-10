WITH params AS (
  SELECT
    'default'          AS portal_code,
    'ROUTECHAINAGES_WMS'       AS layer_key,
    'wms'    AS layer_type,
    'Route Chainages'           AS title,
    1     AS label_class_id,
    '{"opacity":0.9}' AS openlayers_json,
    'RouteChainages'        AS type_name,
    'RouteId'        AS order_by
)

-- 1) Layers
INSERT INTO JsonLayers (
  portalId, layerKey, layerType, title,
  labelClassId, visibility, openLayersJSON
)
SELECT
  (SELECT PortalId FROM Portals WHERE code = params.portal_code),
  params.layer_key,
  params.layer_type,
  params.title,
  params.label_class_id,
  0,
  params.openlayers_json
FROM params;

-- 2) LayerServerOptions (WMS)
WITH params AS (
  SELECT
    'default'   AS portal_code,
    'ROUTECHAINAGES_WMS' AS layer_key,
    'RouteId' AS order_by,
    'RouteChainages'  AS type_name
)
INSERT INTO JsonLayerWmsOptions (LayerId, layers, "orderBy")
SELECT
  L.LayerId, params.type_name, params.order_by
FROM params
JOIN JsonLayers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);

-- 3) Styles (optional)
WITH params AS (
  SELECT 'default' AS portal_code, 'ROUTECHAINAGES_WMS' AS layer_key
)
INSERT INTO JsonLayerStyles (LayerId, name, title, displayOrder)
SELECT L.LayerId, 'Default', 'Default', 1
FROM params
JOIN JsonLayers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);
 
-- -- 4) Styles (optional)
--WITH params AS (
--  SELECT 'default' AS portal_code, 'PSCITODELETE_WMS' AS layer_key
--)
--INSERT INTO JsonLayerStyles (LayerId, name, title,  displayOrder)
--SELECT L.LayerId, 'Visual_CR_Ratings', 'Rating', 1
--FROM params
--JOIN JsonLayers L
--  ON L.layerKey = params.layer_key
-- AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);
