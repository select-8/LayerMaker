INSERT INTO Layers (
  LayerId, layerKey, layerType, title, isBaseLayer, visibilityDefault, openLayersJSON
) VALUES (
  101, 'OSM_BACKGROUND', 'xyz', 'OSM', 1, 0,
  '{"projection":"EPSG:3857","tileSize":512,"transitionEffect":"resize","attribution":"<a href=''https://www.mapbox.com/about/maps/'' target=''_blank''>&copy; Mapbox &copy; OpenStreetMap</a> <a class=''mapbox-improve-map'' href=''https://www.mapbox.com/map-feedback/'' target=''_blank''>Improve this map</a>"}'
);

-- XYZ options
INSERT INTO LayerXYZOptions (
  LayerId, urlTemplate, projection
) VALUES (
  101, '//api.mapbox.com/styles/v1/mapbox/streets-v11/tiles/{z}/{x}/{y}?access_token={MAPBOX_TOKEN}', 'EPSG:3857'
);

-- Layers
INSERT INTO Layers (
  LayerId, layerKey, layerType, title, gridXType, visibilityDefault
) VALUES (
  201, 'PROJECTS_WMS', 'wms', 'Projects', 'pms_projectsgrid', 0
);

-- WMS options
INSERT INTO LayerServerOptions (
  LayerId, wmsLayers, "orderBy"
) VALUES (
  201, 'Projects', 'SysStartTime ASC, ProjectId ASC'
);

-- Styles (array form)
INSERT INTO LayerStyles (LayerId, name, title, isDefault, displayOrder)
VALUES
  (201, 'ProjectType', 'Project Types', 1, 1),
  (201, 'ProjectPhase', 'Project Phases', 0, 2);
  
 -- Layers
INSERT INTO Layers (
  LayerId, layerKey, layerType, title, gridXType, idProperty, featureType, geomFieldName, visibilityDefault
) VALUES (
  301, 'LA16POINTS_VECTOR', 'wfs', 'LA16 Points', 'pms_la16pointsgrid', 'LA16SurveyId', 'LA16Points', 'msGeometry', 0
);

-- WFS options
INSERT INTO LayerServerOptions (
  LayerId, propertyName, "version"
) VALUES (
  301, 'LA16SurveyId,PhaseId,Year,PhaseName,IsManagedRoute,IsManagedRouteText', '2.0.0'
);

-- Styles (array form)
INSERT INTO LayerStyles (LayerId, name, title, labelRule, isDefault, displayOrder)
VALUES
  (301, 'Phase', 'Phase', 'labels', 1, 1),
  (301, 'Year', 'Year', 'labels', 0, 2);
  
  -- Parent switchlayer
INSERT INTO Layers (
  LayerId, layerKey, layerType, title, vectorFeaturesMinScale, visibilityDefault
) VALUES (
  401, 'LIGHT_UNIT_SWITCH_LAYER', 'switchlayer', 'Lighting', 20000, 0
);

-- Compose the switchlayer from child layers (positions define order)
INSERT INTO SwitchLayerChildren (ParentLayerId, ChildLayerId, position)
VALUES
  (401, 201, 1),  -- PROJECTS_WMS as first child (example)
  (401, 301, 2);  -- LA16POINTS_VECTOR as second child (example)
  
 -- Global defaults (top-level under "defaults")
INSERT INTO GlobalDefaults(key, valueJSON) VALUES
  ('styleSwitcherBelowNode','true')
ON CONFLICT(key) DO UPDATE SET valueJSON=excluded.valueJSON;

-- Per-layer-type defaults (nested under "defaults")
INSERT INTO LayerTypeDefaults(layerType, defaultsJSON) VALUES
  ('xyz','{"openLayers":{"projection":"EPSG:2157","transitionEffect":"resize","visibility":false},"isBaseLayer":true}')
ON CONFLICT(layerType) DO UPDATE SET defaultsJSON=excluded.defaultsJSON;

INSERT INTO LayerTypeDefaults(layerType, defaultsJSON) VALUES
  ('wms','{"dateFormat":"Y-m-d","url":"/mapserver2/?","featureInfoWindow":true,"hasMetadata":true,"isBaseLayer":false,"requestMethod":"POST","openLayers":{"maxResolution":1222.99245234375,"opacity":0.9,"projection":"EPSG:2157","visibility":false,"singleTile":true}}')
ON CONFLICT(layerType) DO UPDATE SET defaultsJSON=excluded.defaultsJSON;

INSERT INTO LayerTypeDefaults(layerType, defaultsJSON) VALUES
  ('wfs','{"url":"/mapserver2/?","noCluster":true,"serverOptions":{"version":"2.0.0","maxResolution":1222.99245234375},"openLayers":{"visibility":false,"projection":"EPSG:2157"}}')
ON CONFLICT(layerType) DO UPDATE SET defaultsJSON=excluded.defaultsJSON;

INSERT INTO LayerTypeDefaults(layerType, defaultsJSON) VALUES
  ('arcgisrest','{"openLayers":{"singleTile":false,"visibility":false}}')
ON CONFLICT(layerType) DO UPDATE SET defaultsJSON=excluded.defaultsJSON;

INSERT INTO LayerTypeDefaults(layerType, defaultsJSON) VALUES
  ('switchlayer','{}')
ON CONFLICT(layerType) DO UPDATE SET defaultsJSON=excluded.defaultsJSON;
