
------------------------------------------------------------
-- 2. Mock data
------------------------------------------------------------

-- Portals
INSERT INTO Portals (PortalId, PortalKey, PortalTitle) VALUES
    (1, 'default',     'Default Portal'),
    (2, 'editor',      'Editor Portal'),
    (3, 'nta_default', 'NTA Default Portal'),
    (4, 'tii_default', 'TII Default Portal');

-- MapServerLayers (datasets)
INSERT INTO MapServerLayers
    (MapServerLayerId, MapLayerName,        BaseLayerKey,         GridXType,                       GeometryType, DefaultGeomFieldName, DefaultLabelClassName, DefaultOpacity, Notes)
VALUES
    (1, 'RoadSchedulePublic', 'ROADSCHEDULEPUBLIC', 'pms_roadschedulepublicgrid', 'LINESTRING', 'msGeometry', 'labels', 0.75, NULL),
    (2, 'ATINetwork',         'ATINETWORK',         'pms_atinetworkgrid',         'LINESTRING', 'msGeometry', 'labels', 0.75, NULL);

-- ServiceLayers (WMS / WFS for each dataset)
INSERT INTO ServiceLayers
    (ServiceLayerId, MapServerLayerId, ServiceType, LayerKey,                      FeatureType,          IdPropertyName, GeomFieldName, LabelClassName, Opacity, OpenLayersJson,                 ServerOptionsJson)
VALUES
    (1, 1, 'WMS', 'ROADSCHEDULEPUBLIC_WMS',    'RoadSchedulePublic', 'SegmentId', 'msGeometry', 'labels', 0.75, '{"projection":"EPSG:2157"}', '{"buffer":0}'),
    (2, 1, 'WFS', 'ROADSCHEDULEPUBLIC_VECTOR', 'RoadSchedulePublic', 'SegmentId', 'msGeometry', 'labels', 0.75, '{"projection":"EPSG:2157"}', '{"paging":true}'),
    (3, 2, 'WMS', 'ATINETWORK_WMS',            'ATINetwork',         'LinkId',    'msGeometry', 'labels', 0.75, '{"projection":"EPSG:2157"}', NULL),
    (4, 2, 'WFS', 'ATINETWORK_VECTOR',         'ATINetwork',         'LinkId',    'msGeometry', 'labels', 0.75, '{"projection":"EPSG:2157"}', NULL);

-- Fields for RoadSchedulePublic
INSERT INTO MapServerLayerFields
    (FieldId, MapServerLayerId, FieldName,      FieldType, IncludeInPropertyCsv, IsIdProperty, DisplayOrder)
VALUES
    (1, 1, 'SegmentId',     'integer', 1, 1, 1),
    (2, 1, 'RoadClass',     'string',  1, 0, 2),
    (3, 1, 'RoadNumber',    'string',  1, 0, 3),
    (4, 1, 'LocalAuthority','string',  1, 0, 4);

-- Fields for ATINetwork
INSERT INTO MapServerLayerFields
    (FieldId, MapServerLayerId, FieldName,   FieldType, IncludeInPropertyCsv, IsIdProperty, DisplayOrder)
VALUES
    (5, 2, 'LinkId',     'integer', 1, 1, 1),
    (6, 2, 'RouteId',    'string',  1, 0, 2),
    (7, 2, 'Carriageway','string',  1, 0, 3);

-- Styles for RoadSchedulePublic (groups from mapfile, excluding "labels")
INSERT INTO MapServerLayerStyles
    (StyleId, MapServerLayerId, GroupName, StyleTitle,          DisplayOrder)
VALUES
    (1, 1, 'NP',    'National Primary',   1),
    (2, 1, 'NS',    'National Secondary', 2),
    (3, 1, 'LOCAL', 'Local Roads',        3);

-- Styles for ATINetwork
INSERT INTO MapServerLayerStyles
    (StyleId, MapServerLayerId, GroupName,   StyleTitle,                         DisplayOrder)
VALUES
    (4, 2, 'ATIMain',      'Active Travel Main Network',     1),
    (5, 2, 'ATISecondary', 'Active Travel Secondary Network',2);

-- Portal tree:
-- default → WMS layers
-- editor  → WFS (VECTOR) layers
-- nta_default / tii_default → just roots for now

-- default portal tree
INSERT INTO PortalTreeNodes
    (PortalTreeNodeId, PortalId, ParentNodeId, IsFolder, FolderTitle,                 LayerKey,                    DisplayOrder, Glyph,   CheckedDefault, ExpandedDefault, Tooltip)
VALUES
    (1,  1, NULL, 1, 'Layers',                 NULL,                        0, NULL,   1, 1, NULL),
    (2,  1, 1,    1, 'Road Network Layers',    NULL,                        1, 'road', 1, 1, NULL),
    (3,  1, 1,    1, 'Active Travel Infrastructure', NULL,                  2, 'bike', 1, 0, NULL),
    (4,  1, 2,    0, NULL, 'ROADSCHEDULEPUBLIC_WMS',                        1, 'line', 1, 0, 'Road schedule (WMS)'),
    (5,  1, 3,    0, NULL, 'ATINETWORK_WMS',                                1, 'bike', 1, 0, 'ATI network (WMS)');

-- editor portal tree
INSERT INTO PortalTreeNodes
    (PortalTreeNodeId, PortalId, ParentNodeId, IsFolder, FolderTitle,                 LayerKey,                      DisplayOrder, Glyph,   CheckedDefault, ExpandedDefault, Tooltip)
VALUES
    (6,  2, NULL, 1, 'Layers',                 NULL,                          0, NULL,   1, 1, NULL),
    (7,  2, 6,    1, 'Road Network Layers',    NULL,                          1, 'road', 1, 1, NULL),
    (8,  2, 6,    1, 'Active Travel Infrastructure', NULL,                    2, 'bike', 1, 0, NULL),
    (9,  2, 7,    0, NULL, 'ROADSCHEDULEPUBLIC_VECTOR',                       1, 'line', 1, 0, 'Road schedule (vector WFS)'),
    (10, 2, 8,    0, NULL, 'ATINETWORK_VECTOR',                                1, 'bike', 1, 0, 'ATI network (vector WFS)');

-- nta_default portal – empty tree scaffold
INSERT INTO PortalTreeNodes
    (PortalTreeNodeId, PortalId, ParentNodeId, IsFolder, FolderTitle, LayerKey, DisplayOrder, Glyph, CheckedDefault, ExpandedDefault, Tooltip)
VALUES
    (11, 3, NULL, 1, 'Layers', NULL, 0, NULL, 1, 1, NULL);

-- tii_default portal – empty tree scaffold
INSERT INTO PortalTreeNodes
    (PortalTreeNodeId, PortalId, ParentNodeId, IsFolder, FolderTitle, LayerKey, DisplayOrder, Glyph, CheckedDefault, ExpandedDefault, Tooltip)
VALUES
    (12, 4, NULL, 1, 'Layers', NULL, 0, NULL, 1, 1, NULL);
