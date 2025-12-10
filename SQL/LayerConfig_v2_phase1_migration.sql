PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

-------------------------------------------------------------------------------
-- 1. Extend MapServerLayers (anchor per MapServer LAYER)
-------------------------------------------------------------------------------
-- GeometryType already exists per your error, so DO NOT add it again.

-- If these two already exist, comment them out and rerun.
ALTER TABLE MapServerLayers
  ADD COLUMN IsXYZ INTEGER NOT NULL DEFAULT 0;        -- 1 = XYZ / base map

ALTER TABLE MapServerLayers
  ADD COLUMN IsArcGisRest INTEGER NOT NULL DEFAULT 0; -- 1 = ArcGIS REST layer


-------------------------------------------------------------------------------
-- 2. Extend ServiceLayers (per MapServer layer + service type: WMS/WFS/XYZ/etc)
-------------------------------------------------------------------------------
-- ServiceType already exists, so DO NOT add it again.
-- LabelClassName also already exists, so DO NOT add it again.

-- If GridXType already exists, comment this out and rerun.
ALTER TABLE ServiceLayers
  ADD COLUMN GridXType TEXT;

-- Overrides for defaults (NULL means: "use global defaults")
ALTER TABLE ServiceLayers
  ADD COLUMN ProjectionOverride TEXT;    -- e.g. 'EPSG:2157'

ALTER TABLE ServiceLayers
  ADD COLUMN OpacityOverride REAL;       -- e.g. 0.75, 0.9

-- WFS only: if NULL, we assume global default noCluster=true
ALTER TABLE ServiceLayers
  ADD COLUMN NoClusterOverride INTEGER;  -- 0 = false, 1 = true, NULL = default

-- If we ever need to turn featureInfoWindow off for a specific layer
ALTER TABLE ServiceLayers
  ADD COLUMN FeatureInfoWindowOverride INTEGER;  -- 0 = false, 1 = true, NULL = default

-- For the oddball layer that uses a 'grouping' key
ALTER TABLE ServiceLayers
  ADD COLUMN Grouping TEXT;

-- For locking out XYZ/ArcGISREST from the UI etc.
ALTER TABLE ServiceLayers
  ADD COLUMN IsUserConfigurable INTEGER NOT NULL DEFAULT 1;


-------------------------------------------------------------------------------
-- 3. Styles per ServiceLayer (used for WMS and WFS)
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ServiceLayerStyles (
    StyleId           INTEGER PRIMARY KEY,
    ServiceLayerId    INTEGER NOT NULL,
    StyleName         TEXT    NOT NULL,   -- 'd1average', 'default', etc
    StyleTitle        TEXT    NOT NULL,   -- 'FWD D1 Lines', etc
    UseLabelRule      INTEGER NOT NULL DEFAULT 0,  -- 1 = emit labelRule, WFS only
    StyleOrder        INTEGER,
    FOREIGN KEY (ServiceLayerId) REFERENCES ServiceLayers(ServiceLayerId)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ServiceLayerStyles_ServiceLayerId
    ON ServiceLayerStyles (ServiceLayerId);


-------------------------------------------------------------------------------
-- 4. Fields per ServiceLayer (WFS only)
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS ServiceLayerFields (
    FieldId                 INTEGER PRIMARY KEY,
    ServiceLayerId          INTEGER NOT NULL,
    FieldName               TEXT    NOT NULL,   -- 'SegmentId', 'RoadNumber', etc
    FieldType               TEXT,               -- 'string', 'int', etc (optional)
    IncludeInPropertyname   INTEGER NOT NULL DEFAULT 0, -- 1 = include in propertyname
    IsTooltip               INTEGER NOT NULL DEFAULT 0, -- 1 = used in tooltips
    TooltipAlias            TEXT,               -- label for tooltip (if any)
    FieldOrder              INTEGER,            -- order in CSV / propertyname list
    FOREIGN KEY (ServiceLayerId) REFERENCES ServiceLayers(ServiceLayerId)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ServiceLayerFields_ServiceLayerId
    ON ServiceLayerFields (ServiceLayerId);


-------------------------------------------------------------------------------
-- 5. Portal <-> ServiceLayer mapping (which services a portal uses)
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS PortalLayers (
    PortalLayerId    INTEGER PRIMARY KEY,
    PortalId         INTEGER NOT NULL,
    ServiceLayerId   INTEGER NOT NULL,
    IsEnabled        INTEGER NOT NULL DEFAULT 1,
    UNIQUE (PortalId, ServiceLayerId),
    FOREIGN KEY (PortalId)       REFERENCES Portals(PortalId)
        ON DELETE CASCADE,
    FOREIGN KEY (ServiceLayerId) REFERENCES ServiceLayers(ServiceLayerId)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_PortalLayers_PortalId
    ON PortalLayers (PortalId);

CREATE INDEX IF NOT EXISTS idx_PortalLayers_ServiceLayerId
    ON PortalLayers (ServiceLayerId);


-------------------------------------------------------------------------------
-- 6. Switchlayer definitions per portal
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS PortalSwitchLayers (
    PortalSwitchLayerId     INTEGER PRIMARY KEY,
    PortalId                INTEGER NOT NULL,
    SwitchKey               TEXT    NOT NULL,    -- e.g. 'LIGHT_UNIT_SWITCH_LAYER'
    VectorFeaturesMinScale  INTEGER,             -- overrides default, NULL = use default
    UNIQUE (PortalId, SwitchKey),
    FOREIGN KEY (PortalId) REFERENCES Portals(PortalId)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_PortalSwitchLayers_PortalId
    ON PortalSwitchLayers (PortalId);


-------------------------------------------------------------------------------
-- 7. Switchlayer children – link WMS/WFS services to a switchlayer
-------------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS PortalSwitchLayerChildren (
    PortalSwitchLayerChildId  INTEGER PRIMARY KEY,
    PortalSwitchLayerId       INTEGER NOT NULL,
    ServiceLayerId            INTEGER NOT NULL,   -- WMS or WFS child
    ChildOrder                INTEGER,            -- order in the 'layers' array
    UNIQUE (PortalSwitchLayerId, ServiceLayerId),
    FOREIGN KEY (PortalSwitchLayerId) REFERENCES PortalSwitchLayers(PortalSwitchLayerId)
        ON DELETE CASCADE,
    FOREIGN KEY (ServiceLayerId) REFERENCES ServiceLayers(ServiceLayerId)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_PortalSwitchLayerChildren_PortalSwitchLayerId
    ON PortalSwitchLayerChildren (PortalSwitchLayerId);

CREATE INDEX IF NOT EXISTS idx_PortalSwitchLayerChildren_ServiceLayerId
    ON PortalSwitchLayerChildren (ServiceLayerId);

COMMIT;
