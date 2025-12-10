BEGIN TRANSACTION;

/* 1) Flip JsonLayers to WFS + fix the layerKey suffix */
UPDATE JsonLayers
SET
  layerType = 'wfs',
  layerKey  = REPLACE(layerKey, '_WMS', '_VECTOR'),

  /* 2) Core vector metadata (tweak if your schema differs) */
  idProperty      = 'CIRIncidentId',
  geomFieldName   = 'msGeometry',
  noCluster       = 1,  -- set to 0 if you prefer clustering
  tooltipsConfigJSON = '[' ||
    '{"alias":"Type","property":"Type"},' ||
    '{"alias":"Name","property":"Name"},' ||
    '{"alias":"Source ID","property":"SourceID"}' ||
  ']'
WHERE LayerId = 53;

/* 3) Ensure a JsonLayerWfsOptions row exists and is correct */
INSERT INTO JsonLayerWfsOptions (LayerId, featureType, propertyName, version, maxResolution)
VALUES
  (
    53,
    'CIRIncidents',
    'CIRIncidentId,Name,SourceID,LocalAuthorityId,ShortName,Type',
    NULL,
    NULL
  )
ON CONFLICT(LayerId) DO UPDATE SET
  featureType  = excluded.featureType,
  propertyName = excluded.propertyName,
  version      = excluded.version,
  maxResolution= excluded.maxResolution;
  
 /* Labels */
 UPDATE JsonLayerStyles SET labelRule = 'labels' WHERE LayerId = 53;

COMMIT;
