SELECT
  L.LayerId,
  L.layerKey,
  L.layerType,
  L.title,
  S.wmsLayers,
  S."orderBy",
  S."version",
  S.maxResolution,
  St.name AS styleName,
  St.title AS styleTitle,
  St.isDefault
FROM Layers L
LEFT JOIN LayerServerOptions S ON L.LayerId = S.LayerId
LEFT JOIN LayerStyles St ON L.LayerId = St.LayerId
WHERE L.layerKey='THISISMYTYPENAME_WMS'
  AND L.portalId=(SELECT PortalId FROM Portals WHERE code='default')
ORDER BY St.displayOrder;