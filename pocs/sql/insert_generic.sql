BEGIN TRANSACTION;

-- 1) UPDATE style if it already exists (change title/order safely)
WITH params AS (
  SELECT
    'default'            AS portal_code,    -- Portals.code
    'YOUR_LAYER_KEY_WMS' AS layer_key,      -- e.g., 'CIRINCIDENTS_WMS'
    'NewStyleName'       AS style_name,     -- PK part with LayerId
    'New Style Title'    AS style_title,
    NULL                 AS display_order   -- put an integer, or NULL to auto-pick later
)
UPDATE JsonLayerStyles
SET
  title        = (SELECT style_title FROM params),
  displayOrder = COALESCE(
                    (SELECT display_order FROM params),
                    displayOrder
                 )
WHERE LayerId = (
        SELECT jl.LayerId
        FROM JsonLayers jl
        WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
          AND jl.layerKey = (SELECT layer_key FROM params)
        LIMIT 1
      )
  AND name = (SELECT style_name FROM params);

-- 2) INSERT style if missing (auto displayOrder if NULL)
WITH params AS (
  SELECT
    'default'            AS portal_code,
    'YOUR_LAYER_KEY_WMS' AS layer_key,
    'NewStyleName'       AS style_name,
    'New Style Title'    AS style_title,
    NULL                 AS display_order   -- NULL = auto next; else fixed integer
),
layer_cte AS (
  SELECT jl.LayerId AS layer_id
  FROM JsonLayers jl
  WHERE jl.PortalId = (SELECT PortalId FROM Portals WHERE code = (SELECT portal_code FROM params))
    AND jl.layerKey = (SELECT layer_key FROM params)
  LIMIT 1
),
order_cte AS (
  SELECT
    CASE
      WHEN (SELECT display_order FROM params) IS NOT NULL THEN
        (SELECT display_order FROM params)
      ELSE
        COALESCE( (SELECT MAX(s.displayOrder) FROM JsonLayerStyles s WHERE s.LayerId = (SELECT layer_id FROM layer_cte)), 0 ) + 1
    END AS final_order
)
INSERT INTO JsonLayerStyles (LayerId, name, title, displayOrder)
SELECT
  (SELECT layer_id FROM layer_cte),
  (SELECT style_name FROM params),
  (SELECT style_title FROM params),
  (SELECT final_order FROM order_cte)
WHERE NOT EXISTS (
  SELECT 1
  FROM JsonLayerStyles s
  WHERE s.LayerId = (SELECT layer_id FROM layer_cte)
    AND s.name    = (SELECT style_name FROM params)
);

COMMIT;
