PRAGMA foreign_keys = ON;
BEGIN TRANSACTION;

-- 1) PortalTreeNodes must go first because FK is RESTRICT on LayerKey -> ServiceLayers.LayerKey
DELETE FROM PortalTreeNodes
WHERE LayerKey IN (
    SELECT LayerKey
    FROM ServiceLayers
    WHERE MapServerLayerId = :MapServerLayerId
);

-- 2) Switch children referencing those service layers
DELETE FROM PortalSwitchLayerChildren
WHERE ServiceLayerId IN (
    SELECT ServiceLayerId
    FROM ServiceLayers
    WHERE MapServerLayerId = :MapServerLayerId
);

-- 3) PortalLayers referencing those service layers
DELETE FROM PortalLayers
WHERE ServiceLayerId IN (
    SELECT ServiceLayerId
    FROM ServiceLayers
    WHERE MapServerLayerId = :MapServerLayerId
);

-- 4) Service-layer styles/fields (cascades would handle these, but explicit is fine)
DELETE FROM ServiceLayerStyles
WHERE ServiceLayerId IN (
    SELECT ServiceLayerId
    FROM ServiceLayers
    WHERE MapServerLayerId = :MapServerLayerId
);

DELETE FROM ServiceLayerFields
WHERE ServiceLayerId IN (
    SELECT ServiceLayerId
    FROM ServiceLayers
    WHERE MapServerLayerId = :MapServerLayerId
);

-- 5) ServiceLayers
DELETE FROM ServiceLayers
WHERE MapServerLayerId = :MapServerLayerId;

-- 6) MapServer layer styles/fields
DELETE FROM MapServerLayerStyles
WHERE MapServerLayerId = :MapServerLayerId;

DELETE FROM MapServerLayerFields
WHERE MapServerLayerId = :MapServerLayerId;

-- 7) MapServerLayers
DELETE FROM MapServerLayers
WHERE MapServerLayerId = :MapServerLayerId;

COMMIT;
