-- Enable foreign keys (just in case)
PRAGMA foreign_keys = ON;

-- 1) Remove switchlayer child links (if this layer is a parent)
DELETE FROM SwitchLayerChildren
WHERE ParentLayerId = (
  SELECT LayerId FROM Layers
  WHERE layerKey='CIRINCIDENTS_WMS'
);

-- 2) Remove switchlayer parent links (if this layer is a child)
DELETE FROM SwitchLayerChildren
WHERE ChildLayerId = (
  SELECT LayerId FROM Layers
  WHERE layerKey='CIRINCIDENTS_WMS'
);

-- 3) Remove styles for this layer
DELETE FROM LayerStyles
WHERE LayerId = (
  SELECT LayerId FROM Layers
  WHERE layerKey='CIRINCIDENTS_WMS'
);

-- 4) Remove WMS/WFS/ArcGIS/XYZ options
DELETE FROM LayerServerOptions
WHERE LayerId = (
  SELECT LayerId FROM Layers
  WHERE layerKey='CIRINCIDENTS_WMS'
);

DELETE FROM LayerXYZOptions
WHERE LayerId = (
  SELECT LayerId FROM Layers
  WHERE layerKey='CIRINCIDENTS_WMS'
);

-- 5) Finally, remove the layer itself
DELETE FROM Layers
WHERE layerKey='CIRINCIDENTS_WMS';

-- Optional sanity check
SELECT layerKey FROM Layers WHERE layerKey='CIRINCIDENTS_WMS';
