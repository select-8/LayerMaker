BEGIN TRANSACTION;

WITH params AS (
  SELECT
    'default'            AS portal_code,
    'RIBGEOMS_WMS' AS layer_key,
    'CRM'       AS style_name,
    'Combined Risk Measure'    AS style_title,
    NULL                 AS display_order
),
layer AS (
  SELECT jl.LayerId AS layer_id
  FROM JsonLayers jl
  WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
    AND jl.layerKey = (SELECT layer_key FROM params)
  LIMIT 1
),
ord AS (
  SELECT COALESCE(
           (SELECT display_order FROM params),
           COALESCE((SELECT MAX(s.displayOrder) FROM JsonLayerStyles s WHERE s.LayerId = (SELECT layer_id FROM layer)), 0) + 1
         ) AS final_order
)
INSERT OR IGNORE INTO JsonLayerStyles (LayerId, name, title, displayOrder)
SELECT (SELECT layer_id FROM layer),
       (SELECT style_name FROM params),
       (SELECT style_title FROM params),
       (SELECT final_order FROM ord);

COMMIT;