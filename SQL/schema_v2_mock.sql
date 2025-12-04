-- Enable FK support in SQLite
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

------------------------------------------------------------
-- 1. Lookups: Portals and ServiceTypes
------------------------------------------------------------

CREATE TABLE Portals (
    PortalId    INTEGER PRIMARY KEY,
    PortalKey   TEXT NOT NULL UNIQUE,  -- 'default', 'editor', ...
    Name        TEXT NOT NULL
);

CREATE TABLE ServiceTypes (
    ServiceTypeId INTEGER PRIMARY KEY,
    Code          TEXT NOT NULL UNIQUE  -- 'wms', 'wfs', 'arcgisrest'
);

INSERT INTO Portals (PortalId, PortalKey, Name) VALUES
  (1, 'default', 'Default portal'),
  (2, 'editor',  'Editor portal');

INSERT INTO ServiceTypes (ServiceTypeId, Code) VALUES
  (1, 'wms'),
  (2, 'wfs');

------------------------------------------------------------
-- 2. MapServerLayers: canonical datasets
------------------------------------------------------------

CREATE TABLE MapServerLayers (
    MapServerLayerId   INTEGER PRIMARY KEY,
    MapLayerName       TEXT NOT NULL UNIQUE,  -- MapServer / featureType name
    BaseLayerKey       TEXT NOT NULL,        -- base for UI keys, e.g. 'ROADSCHEDULEPUBLIC'
    Description        TEXT,
    GeometryType       TEXT,
    DefaultViewName    TEXT,
    DefaultIdProperty  TEXT,
    DefaultGeomField   TEXT,
    Notes              TEXT
);

INSERT INTO MapServerLayers
    (MapServerLayerId, MapLayerName,        BaseLayerKey,            Description)
VALUES
    (1, 'RoadSchedulePublic', 'ROADSCHEDULEPUBLIC', 'Road schedule master'),
    (2, 'TrafficCounters',    'TRAFFICCOUNTERS',    'Traffic counter points'),
    (3, 'PavementDefects',    'PAVEMENTDEFECTS',    'Pavement defects');

------------------------------------------------------------
-- 3. ServiceLayers: WMS/WFS per dataset (portal-agnostic)
------------------------------------------------------------

CREATE TABLE ServiceLayers (
    ServiceLayerId     INTEGER PRIMARY KEY,
    MapServerLayerId   INTEGER NOT NULL,
    ServiceTypeId      INTEGER NOT NULL,
    CanonicalLayerKey  TEXT NOT NULL,        -- e.g. 'ROADSCHEDULEPUBLIC_WMS'
    FeatureType        TEXT,                 -- WFS: featureType; WMS: NULL
    IdProperty         TEXT,
    GeomFieldName      TEXT,
    ServerOptionsJson  TEXT,
    OpenLayersJson     TEXT,
    FOREIGN KEY (MapServerLayerId) REFERENCES MapServerLayers(MapServerLayerId),
    FOREIGN KEY (ServiceTypeId)    REFERENCES ServiceTypes(ServiceTypeId),
    UNIQUE (MapServerLayerId, ServiceTypeId)
);

-- Dataset 1: RoadSchedulePublic
--  - WMS: used in default
--  - WFS: used only in editor
INSERT INTO ServiceLayers
    (ServiceLayerId, MapServerLayerId, ServiceTypeId,
     CanonicalLayerKey,              FeatureType,          IdProperty,     GeomFieldName, ServerOptionsJson)
VALUES
    (1, 1, 1, 'ROADSCHEDULEPUBLIC_WMS',   NULL,                 'SegmentId', 'msGeometry',
        '{"layers":"RoadSchedulePublic"}'),
    (2, 1, 2, 'ROADSCHEDULEPUBLIC_VECTOR','RoadSchedulePublic', 'SegmentId', 'msGeometry',
        '{"featureType":"RoadSchedulePublic"}');

-- Dataset 2: TrafficCounters
--  - WMS: used in default and editor
--  - WFS: used in editor (standalone, no switch)
INSERT INTO ServiceLayers
    (ServiceLayerId, MapServerLayerId, ServiceTypeId,
     CanonicalLayerKey,             FeatureType,        IdProperty,          GeomFieldName, ServerOptionsJson)
VALUES
    (3, 2, 1, 'TRAFFICCOUNTERS_WMS',   NULL,               'TrafficCounterId', 'msGeometry',
        '{"layers":"TrafficCounters"}'),
    (4, 2, 2, 'TRAFFICCOUNTERS_VECTOR','TrafficCounters',  'TrafficCounterId', 'msGeometry',
        '{"featureType":"TrafficCounters"}');

-- Dataset 3: PavementDefects
--  - WMS: used in default
--  - WMS+WFS: used only via switch in editor (no standalone entries)
INSERT INTO ServiceLayers
    (ServiceLayerId, MapServerLayerId, ServiceTypeId,
     CanonicalLayerKey,              FeatureType,         IdProperty,  GeomFieldName, ServerOptionsJson)
VALUES
    (5, 3, 1, 'PAVEMENTDEFECTS_WMS',   NULL,               'DefectId', 'msGeometry',
        '{"layers":"PavementDefects"}'),
    (6, 3, 2, 'PAVEMENTDEFECTS_VECTOR','PavementDefects',  'DefectId', 'msGeometry',
        '{"featureType":"PavementDefects"}');

------------------------------------------------------------
-- 4. PortalLayers: how each service appears per portal
------------------------------------------------------------

CREATE TABLE PortalLayers (
    PortalLayerId           INTEGER PRIMARY KEY,
    PortalId                INTEGER NOT NULL,
    ServiceLayerId          INTEGER NOT NULL,
    LayerKey                TEXT NOT NULL,       -- normally same as CanonicalLayerKey
    GridXType               TEXT,
    LabelClassName          TEXT,
    HelpPage                TEXT,
    VisibilityDefault       INTEGER,             -- 0/1
    DisplayOrder            INTEGER,
    ServerOptionsOverrideJson  TEXT,
    OpenLayersOverrideJson     TEXT,
    FOREIGN KEY (PortalId)       REFERENCES Portals(PortalId),
    FOREIGN KEY (ServiceLayerId) REFERENCES ServiceLayers(ServiceLayerId),
    UNIQUE (PortalId, ServiceLayerId)
);

-- Scenario 1: RoadSchedulePublic
--  default: WMS only
INSERT INTO PortalLayers
    (PortalLayerId, PortalId, ServiceLayerId, LayerKey,
     GridXType,               LabelClassName,        HelpPage,
     VisibilityDefault, DisplayOrder)
VALUES
    (1, 1, 1, 'ROADSCHEDULEPUBLIC_WMS',
        'pms_roadschedulegrid', 'RoadScheduleLabels', 'roadschedule-help',
        0, 10);

--  editor: WFS only (no WMS entry)
INSERT INTO PortalLayers
    (PortalLayerId, PortalId, ServiceLayerId, LayerKey,
     GridXType,               LabelClassName,        HelpPage,
     VisibilityDefault, DisplayOrder)
VALUES
    (2, 2, 2, 'ROADSCHEDULEPUBLIC_VECTOR',
        'pms_roadschedulegrid', 'RoadScheduleLabels', 'roadschedule-help',
        0, 10);

-- Scenario 2: TrafficCounters
--  default: WMS
INSERT INTO PortalLayers
    (PortalLayerId, PortalId, ServiceLayerId, LayerKey,
     GridXType,            LabelClassName,       HelpPage,
     VisibilityDefault, DisplayOrder)
VALUES
    (3, 1, 3, 'TRAFFICCOUNTERS_WMS',
        'pms_trafficgrid', 'TrafficLabels', 'traffic-help',
        0, 20);

--  editor: WMS and WFS as separate standalone layers (no switch)
INSERT INTO PortalLayers
    (PortalLayerId, PortalId, ServiceLayerId, LayerKey,
     GridXType,            LabelClassName,       HelpPage,
     VisibilityDefault, DisplayOrder)
VALUES
    (4, 2, 3, 'TRAFFICCOUNTERS_WMS',
        'pms_trafficgrid', 'TrafficLabels', 'traffic-help',
        0, 20),
    (5, 2, 4, 'TRAFFICCOUNTERS_VECTOR',
        'pms_trafficgrid', 'TrafficLabels', 'traffic-help',
        0, 21);

-- Scenario 3: PavementDefects
--  default: WMS only
INSERT INTO PortalLayers
    (PortalLayerId, PortalId, ServiceLayerId, LayerKey,
     GridXType,               LabelClassName,        HelpPage,
     VisibilityDefault, DisplayOrder)
VALUES
    (6, 1, 5, 'PAVEMENTDEFECTS_WMS',
        'pms_defectsgrid', 'DefectLabels', 'defects-help',
        0, 30);

--  editor: PavementDefects appears ONLY via a switch (no PortalLayers rows
--          for ServiceLayerId 5 or 6 here)

------------------------------------------------------------
-- 5. Switch layers: editor-only switch for PavementDefects
------------------------------------------------------------

CREATE TABLE PortalSwitchLayers (
    SwitchId              INTEGER PRIMARY KEY,
    PortalId              INTEGER NOT NULL,
    SwitchKey             TEXT NOT NULL,
    VectorFeaturesMinScale INTEGER,
    VisibilityDefault     INTEGER,
    FeatureInfoWindow     INTEGER,
    FOREIGN KEY (PortalId) REFERENCES Portals(PortalId),
    UNIQUE (PortalId, SwitchKey)
);

CREATE TABLE PortalSwitchChildren (
    SwitchChildId     INTEGER PRIMARY KEY,
    SwitchId          INTEGER NOT NULL,
    ServiceLayerId    INTEGER NOT NULL,
    ChildOrder        INTEGER,
    IsDefaultVector   INTEGER,  -- 1 for the vector/WFS child if you want
    FOREIGN KEY (SwitchId)       REFERENCES PortalSwitchLayers(SwitchId),
    FOREIGN KEY (ServiceLayerId) REFERENCES ServiceLayers(ServiceLayerId)
);

-- Editor: PavementDefects switch combining WMS+WFS
INSERT INTO PortalSwitchLayers
    (SwitchId, PortalId, SwitchKey,
     VectorFeaturesMinScale, VisibilityDefault, FeatureInfoWindow)
VALUES
    (1, 2, 'PAVEMENTDEFECTS_SWITCH',
        20000, 0, 1);

INSERT INTO PortalSwitchChildren
    (SwitchChildId, SwitchId, ServiceLayerId, ChildOrder, IsDefaultVector)
VALUES
    -- child 1: WMS
    (1, 1, 5, 1, 0),
    -- child 2: WFS (marked as default vector)
    (2, 1, 6, 2, 1);

COMMIT;
