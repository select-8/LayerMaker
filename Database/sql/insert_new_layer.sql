-- 👇 Set your parameters here
WITH params AS (
  SELECT
    'default'          AS portal_code,     -- portal
    'TESTLAYER_WMS'    AS layer_key,       -- layerKey to create
    'Test Layer'       AS title,           -- human title
    'labels'           AS label_class,     -- optional
    '{"opacity":0.9}'  AS openlayers_json, -- optional JSON
    'TestLayer'      AS wms_layers,      -- server layer name
    'id'               AS order_by        -- ORDERBY (optional)
)

-- 1) Layers
INSERT INTO Layers (
  portalId, layerKey, layerType, title,
  labelClassName, visibilityDefault, openLayersJSON
)
SELECT
  (SELECT PortalId FROM Portals WHERE code = params.portal_code),
  params.layer_key,
  'wms',
  params.title,
  params.label_class,
  0,
  params.openlayers_json
FROM params;

-- 2) LayerServerOptions
WITH params AS (
  SELECT
    'default'          AS portal_code,
    'TESTLAYER_WMS'    AS layer_key,
    'TestLayer'      AS wms_layers,
    'id'               AS order_by
)
INSERT INTO LayerServerOptions (LayerId, wmsLayers, "orderBy")
SELECT
  L.LayerId, params.wms_layers, params.order_by
FROM params
JOIN Layers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);

-- 3) Styles (optional — add as many INSERTs as you like)
WITH params AS (
  SELECT 'default' AS portal_code, 'TESTLAYER_WMS' AS layer_key
)
INSERT INTO LayerStyles (LayerId, name, title, isDefault, displayOrder)
SELECT L.LayerId, 'default', 'Default', 1, 1
FROM params
JOIN Layers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);

WITH params AS (
  SELECT 'default' AS portal_code, 'TESTLAYER_WMS' AS layer_key
)
INSERT INTO LayerStyles (LayerId, name, title, isDefault, displayOrder)
SELECT L.LayerId, 'Owner', 'Owner', 0, 2
FROM params
JOIN Layers L
  ON L.layerKey = params.layer_key
 AND L.portalId = (SELECT PortalId FROM Portals WHERE code = params.portal_code);
