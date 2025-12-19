-- LayerConfig_v3 bootstrap reset (Tab3 tree NOT imported, but must be cleared to satisfy FK restrictions)
PRAGMA foreign_keys=OFF;

DELETE FROM PortalTreeNodes;
DELETE FROM PortalSwitchLayerChildren;
DELETE FROM PortalSwitchLayers;
DELETE FROM PortalLayers;

DELETE FROM ServiceLayerFields;
DELETE FROM ServiceLayerStyles;
DELETE FROM ServiceLayers;

DELETE FROM MapServerLayerFields;
DELETE FROM MapServerLayerStyles;
DELETE FROM MapServerLayers;

DELETE FROM Portals;

PRAGMA foreign_keys=ON;
VACUUM;
