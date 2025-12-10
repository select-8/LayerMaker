BEGIN TRANSACTION;

WITH params AS (
  SELECT
    'default'            AS portal_code,    -- Portals.code
    'RIBGEOMS_WMS' AS layer_key,      -- e.g. 'CIRINCIDENTS_WMS'
    'Default'  AS style_name      -- e.g. 'Alternative'
)
DELETE FROM JsonLayerStyles
WHERE LayerId = (
        SELECT jl.LayerId
        FROM JsonLayers jl
        WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
          AND jl.layerKey = (SELECT layer_key FROM params)
        LIMIT 1
      )
  AND name = (SELECT style_name FROM params);

COMMIT;
