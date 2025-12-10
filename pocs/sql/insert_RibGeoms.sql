BEGIN TRANSACTION;

-- 1) INSERT JsonLayers if missing
WITH params AS (
  SELECT
    'default'                  AS portal_code,      -- Portals.code
    'RIBGEOMS_WMS'             AS layer_key,        -- e.g. 'CIRINCIDENTS_WMS'
    'wms'                      AS layer_type,
    'Risk-Based Geometric Design' AS title,
    'labels'                   AS label_class_name, -- JsonLabelClasses.name
    '{"opacity":0.9}'          AS openLayersJSON,   -- exact camelCase
    'RibGeoms'                 AS wms_layers,       -- WMS LAYERS / typeName
    'ID'                       AS order_by          -- or NULL
)
INSERT INTO JsonLayers (
  PortalId, layerKey, layerType, title,
  labelClassId, visibility, openLayersJSON
)
SELECT
  (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params)),
  (SELECT layer_key FROM params),
  (SELECT layer_type FROM params),
  (SELECT title FROM params),
  (SELECT LabelClassId FROM JsonLabelClasses WHERE name = (SELECT label_class_name FROM params)),
  0,
  (SELECT openLayersJSON FROM params)
WHERE NOT EXISTS (
  SELECT 1 FROM JsonLayers jl
  WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
    AND jl.layerKey = (SELECT layer_key FROM params)
);

-- 2) UPDATE JsonLayers (if it exists)
WITH params AS (
  SELECT
    'default'                  AS portal_code,
    'RIBGEOMS_WMS'             AS layer_key,
    'wms'                      AS layer_type,
    'Risk-Based Geometric Design' AS title,
    'labels'                   AS label_class_name,
    '{"opacity":0.9}'          AS openLayersJSON
)
UPDATE JsonLayers
SET
  layerType      = (SELECT layer_type FROM params),
  title          = (SELECT title FROM params),
  labelClassId   = (SELECT LabelClassId FROM JsonLabelClasses WHERE name = (SELECT label_class_name FROM params)),
  openLayersJSON = (SELECT openLayersJSON FROM params)
WHERE PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
  AND layerKey = (SELECT layer_key FROM params);

-- 3) UPDATE JsonLayerWmsOptions
WITH params AS (
  SELECT
    'default'      AS portal_code,
    'RIBGEOMS_WMS' AS layer_key,
    'RibGeoms'     AS wms_layers,
    'ID'           AS order_by
)
UPDATE JsonLayerWmsOptions
SET
  layers    = (SELECT wms_layers FROM params),
  "orderBy" = (SELECT order_by   FROM params)
WHERE LayerId = (
  SELECT jl.LayerId
  FROM JsonLayers jl
  WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
    AND jl.layerKey = (SELECT layer_key FROM params)
  LIMIT 1
);

-- 4) INSERT JsonLayerWmsOptions if missing
WITH params AS (
  SELECT
    'default'      AS portal_code,
    'RIBGEOMS_WMS' AS layer_key,
    'RibGeoms'     AS wms_layers,
    'ID'           AS order_by
)
INSERT INTO JsonLayerWmsOptions (LayerId, layers, "orderBy")
SELECT
  (SELECT jl.LayerId
   FROM JsonLayers jl
   WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
     AND jl.layerKey = (SELECT layer_key FROM params)
   LIMIT 1),
  (SELECT wms_layers FROM params),
  (SELECT order_by   FROM params)
WHERE NOT EXISTS (
  SELECT 1 FROM JsonLayerWmsOptions w
  WHERE w.LayerId = (
    SELECT jl.LayerId
    FROM JsonLayers jl
    WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
      AND jl.layerKey = (SELECT layer_key FROM params)
    LIMIT 1
  )
);

-- 5) Ensure a 'Default' style exists
WITH params AS (
  SELECT 'default' AS portal_code, 'RIBGEOMS_WMS' AS layer_key
)
INSERT INTO JsonLayerStyles (LayerId, name, title, displayOrder)
SELECT
  (SELECT jl.LayerId
   FROM JsonLayers jl
   WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
     AND jl.layerKey = (SELECT layer_key FROM params)
   LIMIT 1),
  'Default', 'Default', 1
WHERE NOT EXISTS (
  SELECT 1
  FROM JsonLayerStyles s
  WHERE s.LayerId = (
          SELECT jl.LayerId
          FROM JsonLayers jl
          WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
            AND jl.layerKey = (SELECT layer_key FROM params)
          LIMIT 1
       )
    AND s.name = 'Default'
);

COMMIT;
